"""
Campus Coach Sync Lambda Function

Syncs training plan from Campus Coach REST API to DynamoDB.
Triggered by: EventBridge schedule (daily 05:00 UTC) or on-demand invoke.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
import requests
from shared.campus_status import (
    STATUS_DONE,
    STATUS_SKIP,
    STATUS_TODO,
    effective_status,
    normalize_status,
)
from shared.logger import get_logger

logger = get_logger("campus-coach-sync")

REGION = os.environ.get('AWS_REGION', 'eu-west-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
secretsmanager = boto3.client('secretsmanager', region_name=REGION)

COACHING_SESSIONS_TABLE = os.environ['COACHING_SESSIONS_TABLE']
SECRET_ARN = os.environ.get('SECRET_ARN', 'strava-ai-boost-campus-coach-credentials')
USER_CONFIG_TABLE = os.environ.get('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration')

API_BASE = os.environ.get("CAMPUS_COACH_API_URL", "https://api.campus.coach")

# Provider sync must never write these locally owned or legacy completion fields.
LOCAL_EXECUTION_FIELDS = frozenset({
    'local_status',
    'matched_activity_id',
    'match_score',
    'completed_at',
    'status',
})


def _is_module_enabled(user_id: str) -> bool:
    """Check if Campus Coach module is enabled for the user."""
    if not user_id:
        return True  # If no user_id, assume enabled (backward compat)
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        resp = table.get_item(Key={'user_id': user_id})
        item = resp.get('Item', {})
        modules_config = item.get('modules_config', {})
        campus_config = modules_config.get('campus_coach', {})
        enabled = campus_config.get('enabled', False)
        logger.info(f"Campus Coach module enabled={enabled} for user {user_id}")
        return enabled
    except Exception as e:
        logger.error(f"Failed to check module status: {e}, defaulting to enabled=True")
        return True  # On error, try to sync anyway


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler."""
    try:
        user_id = event.get('user_id') or os.environ.get('DEFAULT_USER_ID', '')

        # Check if Campus Coach module is enabled for this user
        if not _is_module_enabled(user_id):
            logger.info("Campus Coach module not enabled, skipping sync")
            return {'statusCode': 200, 'message': 'Module not enabled'}

        logger.info("Starting Campus Coach sync")

        credentials = _get_credentials()
        token = _login(credentials['username'], credentials['password'])

        # Fetch supplementary data (goal, profile, assiduity)
        table = dynamodb.Table(COACHING_SESSIONS_TABLE)
        _sync_athlete_context(token, table, user_id)

        now = datetime.now(timezone.utc)
        from_ms = int((now - timedelta(weeks=6)).timestamp() * 1000)
        to_ms = int((now + timedelta(weeks=6)).timestamp() * 1000)

        weeks = _fetch_plan(token, from_ms, to_ms)
        allowed_weeks = [w for w in weeks if w.get('access') == 'allowed']

        monday_current = _monday_of_iso_week(now)

        new_session_ids: set[str] = set()
        sessions_stored = 0

        for week in allowed_weeks:
            week_date = week['weekDate']  # timestamp ms
            week_iso = _to_iso_week(week_date)
            is_current = (week_date == int(monday_current.timestamp() * 1000))
            is_future = week_date > int(monday_current.timestamp() * 1000)
            context_data = week.get('context', {})
            paces = week.get('estimatedPaces', [])

            for idx, session in enumerate(week.get('sessions', [])):
                session_id = f"{week_date}_{idx}"
                session_date = f"week-{week_iso}"
                new_session_ids.add(f"{session_date}#{session_id}")

                stats = session.get('stats', {})
                item = {
                    'session_date': session_date,  # PK
                    'session_id': session_id,  # SK
                    'week_date': week_date,
                    'week_date_iso': week_iso,
                    'training_index': idx,
                    'title': session.get('displayName', ''),
                    'description': session.get('description', ''),
                    'coach_advice': session.get('coachAdvice', ''),
                    'sport': session.get('sport', ''),
                    'training_type': session.get('trainingType', ''),
                    'difficulty': int(session.get('difficulty', 0)),
                    'importance': session.get('importance', False),
                    # Provider-owned plan status, kept separate from local
                    # execution state so a daily sync never clobbers a session
                    # that was locally completed by the content pipeline.
                    'provider_status': session.get('status', 'todo'),
                    'is_current_week': is_current,
                    'is_future': is_future,
                    'intervals': _build_intervals(session, paces),
                    'target_pace_10km': _format_pace(_find_pace(paces, '10km')),
                    'target_pace_ef': _format_pace(_find_pace(paces, 'ef')),
                    'expected_distance_km': str(round(stats['expectedDistance'] / 1000, 1)) if stats.get('expectedDistance') else None,
                    'expected_duration_min': round(stats['expectedDuration'] / 60) if stats.get('expectedDuration') else None,
                    'cycle_theme': context_data.get('cycleTheme', ''),
                    'cycle_description': context_data.get('cycleDescription', ''),
                    'provider_synced_at': now.isoformat(),
                    'synced_at': now.isoformat(),  # legacy alias, kept for back-compat
                }
                # Merge provider-owned fields; never erase local execution state.
                _upsert_provider_session(table, item)
                sessions_stored += 1

        # Delete stale sessions
        deleted = _delete_stale_sessions(table, new_session_ids)

        summary = {
            'weeks_synced': len(allowed_weeks),
            'sessions_stored': sessions_stored,
            'sessions_deleted': deleted,
        }
        logger.info("Sync complete", extra=summary)
        return {'statusCode': 200, **summary}

    except Exception as e:
        logger.exception(f"Sync failed: {e}")
        return {'statusCode': 500, 'error': str(e)}


def _get_credentials() -> Dict[str, str]:
    """Fetch credentials from Secrets Manager."""
    resp = secretsmanager.get_secret_value(SecretId=SECRET_ARN)
    return json.loads(resp['SecretString'])


def _login(email: str, password: str) -> str:
    """Authenticate and return JWT token."""
    resp = requests.post(
        f"{API_BASE}/account/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()['token']


def _fetch_plan(token: str, from_ms: int, to_ms: int) -> List[Dict]:
    """Fetch training plan weeks from Campus Coach API."""
    resp = requests.get(
        f"{API_BASE}/smart-training",
        params={"from": from_ms, "to": to_ms},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _monday_of_iso_week(dt: datetime) -> datetime:
    """Return Monday 00:00 UTC of the ISO week containing dt."""
    return (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def _to_iso_week(week_date_ms: int) -> str:
    """Convert timestamp ms to ISO week string like '2026-W21'."""
    dt = datetime.fromtimestamp(week_date_ms / 1000, tz=timezone.utc)
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _find_pace(paces: List, slug: str) -> Optional[float]:
    """Find a pace value by slug from the estimatedPaces list."""
    if not paces:
        return None
    for p in paces:
        if isinstance(p, dict) and p.get('slug') == slug:
            return p.get('value')
    return None


def _format_pace(seconds_per_km: Optional[float]) -> Optional[str]:
    """Convert seconds/km to mm:ss/km string."""
    if not seconds_per_km:
        return None
    minutes = int(seconds_per_km) // 60
    seconds = int(seconds_per_km) % 60
    return f"{minutes}:{seconds:02d}/km"


def _build_intervals(session: Dict, paces: List) -> List[Dict[str, Any]]:
    """Transform exercisesBlocks into simplified interval list."""
    intervals: List[Dict[str, Any]] = []
    blocks = session.get('exercisesBlocks', [])

    for block in blocks:
        block_type = block.get('blockType', 'work')
        repeat = block.get('repeat', 1)

        for exercise in block.get('exercises', []):
            if exercise.get('exerciseType') == 'recuperation' and block_type != 'cool-down':
                ex_type = 'recovery'
            elif block_type == 'warm-up':
                ex_type = 'warm-up'
            elif block_type == 'cool-down':
                ex_type = 'cool-down'
            else:
                ex_type = 'work'

            # Duration
            durations = exercise.get('durations', [])
            dur_str = ''
            if durations:
                d = durations[0]
                val = d.get('value', 0)
                unit = d.get('timeUnit', 'minutes')
                if unit == 'seconds':
                    dur_str = f"{val} sec" if val < 60 else f"{val // 60}:{val % 60:02d} min"
                elif unit == 'minutes':
                    dur_str = f"{val} min"
                else:
                    dur_str = f"{val} {unit}"

            # Pace
            pace_info = exercise.get('pace', {})
            pace_name = pace_info.get('name', '')
            pace_val = pace_info.get('value')
            pace_str = pace_name
            if pace_val and pace_val < 1000:
                pace_str = f"{pace_name} ({int(pace_val) // 60}:{int(pace_val) % 60:02d}/km)"

            entry: Dict[str, Any] = {
                'type': ex_type,
                'duration': dur_str,
                'pace': pace_str,
            }
            if repeat > 1 and ex_type == 'work':
                entry['repeat'] = repeat

            intervals.append(entry)

    return intervals


def _upsert_provider_session(table: Any, item: Dict[str, Any]) -> None:
    """Merge provider-owned fields into a session row (never ``put_item``).

    Uses an update expression so local execution state written by the content
    pipeline (``local_status``, ``matched_activity_id``, ``match_score``,
    ``completed_at`` and the legacy ``status``=Fait completion marker) survives
    the daily provider sync untouched. Creates the row if it does not yet exist.

    ``None`` values are skipped (DynamoDB cannot store them). Every attribute name
    goes through ``ExpressionAttributeNames`` to avoid DynamoDB reserved-word
    clashes (e.g. ``status``-adjacent names).
    """
    key = {'session_date': item['session_date'], 'session_id': item['session_id']}
    provider_fields = {
        k: v for k, v in item.items()
        if k not in ('session_date', 'session_id')
        and k not in LOCAL_EXECUTION_FIELDS
        and v is not None
    }
    if not provider_fields:
        return

    names: Dict[str, str] = {}
    values: Dict[str, Any] = {}
    assignments: List[str] = []
    for i, (field, value) in enumerate(provider_fields.items()):
        names[f'#f{i}'] = field
        values[f':v{i}'] = value
        assignments.append(f'#f{i} = :v{i}')

    table.update_item(
        Key=key,
        UpdateExpression='SET ' + ', '.join(assignments),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def _delete_stale_sessions(table: Any, current_ids: set[str]) -> int:
    """Delete sessions from DynamoDB that are no longer in the API response."""
    existing = {}
    scan_kwargs = {'ProjectionExpression': 'session_date, session_id'}
    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get('Items', []):
            if item.get('session_date') != 'athlete-context':
                key = f"{item['session_date']}#{item['session_id']}"
                existing[key] = item
        if 'LastEvaluatedKey' not in response:
            break
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']

    stale_keys = set(existing.keys()) - current_ids
    deleted = 0

    with table.batch_writer() as batch:
        for key in stale_keys:
            item = existing[key]
            batch.delete_item(Key={'session_date': item['session_date'], 'session_id': item['session_id']})
            deleted += 1

    if deleted:
        logger.info(f"Deleted {deleted} stale sessions")

    return deleted


def _sync_athlete_context(token: str, table: Any, user_id: str) -> None:
    """Fetch and store supplementary athlete context from Campus Coach API."""
    try:
        headers = {"Authorization": f"Bearer {token}"}

        # Active goal (race objective, progress)
        goal_resp = requests.get(f"{API_BASE}/smart-training/goal/active", headers=headers, timeout=10)
        goals = goal_resp.json() if goal_resp.status_code == 200 else []

        # Assiduity status
        assiduity_resp = requests.get(f"{API_BASE}/smart-training/assiduity-status", headers=headers, timeout=10)
        assiduity = assiduity_resp.json() if assiduity_resp.status_code == 200 else {}

        # User sport infos
        user_resp = requests.get(f"{API_BASE}/account/user-infos", headers=headers, timeout=10)
        user_infos = user_resp.json() if user_resp.status_code == 200 else {}

        # Build context item
        active_goal = goals[0] if goals else {}
        context_item = {
            'session_date': 'athlete-context',  # PK - special key
            'session_id': user_id,  # SK
            'synced_at': datetime.now(timezone.utc).isoformat(),
        }

        # Goal data
        if active_goal:
            stats = active_goal.get('stats', {})
            context_item['goal'] = {
                'type': active_goal.get('goalType', ''),
                'competition_date': str(active_goal.get('competitionDate', '')),
                'duration_weeks': str(active_goal.get('durationInWeeks', '')),
                'status': active_goal.get('status', ''),
                'trainings_total': str(stats.get('trainingsCount', 0)),
                'trainings_done': str(stats.get('trainingsDoneCount', 0)),
                'distance_total_km': str(round(stats.get('distanceTotal', 0), 1)),
                'time_total_min': str(round(stats.get('timeTotal', 0) / 60)),
            }

        # Assiduity
        if assiduity:
            context_item['assiduity'] = assiduity.get('assiduity', '')
            context_item['assiduity_sub_status'] = assiduity.get('assiduitySubStatus', '')

        # Sport profile
        sport_infos = user_infos.get('sportInfos', {})
        if sport_infos:
            exp = sport_infos.get('experience', {})
            context_item['sport_profile'] = {
                'sessions_per_week': str(exp.get('sessionsPerWeek', '')),
                'volume_per_week_km': str(exp.get('volumePerWeek', {}).get('minKm', '')),
                'priority': sport_infos.get('training', {}).get('priority', ''),
                'ppg_active': str(sport_infos.get('ppgPreferences', {}).get('active', False)),
                'injuries_minor': str(sport_infos.get('injuries', {}).get('minor', 0)),
                'injuries_major': str(sport_infos.get('injuries', {}).get('major', 0)),
            }

        # Subscription info
        end_of_sub = user_infos.get('endOfSub')
        if end_of_sub:
            context_item['subscription_end'] = str(end_of_sub)

        table.put_item(Item=context_item)
        logger.info("Athlete context synced successfully")

    except Exception as e:
        logger.warning(f"Failed to sync athlete context (non-fatal): {e}")
