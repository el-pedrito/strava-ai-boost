"""
Campus Coach Sync Lambda Function

Syncs training plan from Campus Coach REST API to DynamoDB.
Triggered by: EventBridge schedule (daily 05:00 UTC) or on-demand invoke.
"""

import json
import math
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
from botocore.exceptions import ClientError
from shared.logger import get_logger, metrics, MetricUnit
from shared.pace_zones import build_campus_zones

logger = get_logger("campus-coach-sync")

REGION = os.environ.get('AWS_REGION', 'eu-west-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
secretsmanager = boto3.client('secretsmanager', region_name=REGION)

COACHING_SESSIONS_TABLE = os.environ['COACHING_SESSIONS_TABLE']
SECRET_ARN = os.environ.get('SECRET_ARN', 'strava-ai-boost-campus-coach-credentials')
USER_CONFIG_TABLE = os.environ.get('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration')
# A3: home aggregates land in the wellness table under campus#* keys, keyed by
# the owner's Strava id. Empty owner -> never write (feature off).
WELLNESS_TABLE = os.environ.get('WELLNESS_TABLE', 'strava-ai-boost-wellness')
CAMPUS_OWNER_STRAVA_ID = os.environ.get('CAMPUS_OWNER_STRAVA_ID', '')

API_BASE = os.environ.get("CAMPUS_COACH_API_URL", "https://api.campus.coach")

# Provider sync must never write these locally owned execution fields.
# The legacy ``status`` attribute is intentionally NOT listed: it is a dead
# field (its completion info was migrated into ``local_status`` and
# ``effective_status`` no longer reads it), and the sync never emits a ``status``
# key anyway (it maps the provider's own status onto ``provider_status``).
LOCAL_EXECUTION_FIELDS = frozenset({
    'local_status',
    'matched_activity_id',
    'match_score',
    'completed_at',
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


def _zones_enabled() -> bool:
    """``CAMPUS_ZONES_ENABLED`` kill switch, off unless exactly ``"true"``.

    Read at call time (not import time) so a test or a config change needs no reload.
    """
    return os.environ.get('CAMPUS_ZONES_ENABLED', '') == 'true'


@metrics.log_metrics
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

        # Read-only diagnostic: report what the provider sends (field names and the
        # pace objects), write nothing. Lets an operator see fields the sync drops
        # without ever handling the Campus credentials. Invoke with
        # {"probe_schema": true}; the result is returned, never logged.
        if event.get('probe_schema'):
            return {'statusCode': 200, 'probe': _probe_schema(token)}

        # Fetch supplementary data (goal, profile, assiduity). Reuse the goal
        # it returns for the A3 home aggregates (no second goal/active call).
        table = dynamodb.Table(COACHING_SESSIONS_TABLE)
        goals = _sync_athlete_context(token, table, user_id)

        now = datetime.now(timezone.utc)
        from_ms = int((now - timedelta(weeks=6)).timestamp() * 1000)
        to_ms = int((now + timedelta(weeks=6)).timestamp() * 1000)

        weeks = _fetch_plan(token, from_ms, to_ms)
        allowed_weeks = [w for w in weeks if w.get('access') == 'allowed']

        monday_current = _monday_of_iso_week(now)

        new_session_ids: set[str] = set()
        sessions_stored = 0
        zones_written = False

        for week in allowed_weeks:
            week_date = week['weekDate']  # timestamp ms
            week_iso = _to_iso_week(week_date)
            is_current = (week_date == int(monday_current.timestamp() * 1000))
            is_future = week_date > int(monday_current.timestamp() * 1000)
            context_data = week.get('context', {})
            paces = week.get('estimatedPaces', [])
            estimated_paces = _parse_estimated_paces(paces)
            if is_current and _zones_enabled():
                zones_written = _write_campus_zones(estimated_paces, week_iso, now)

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
                    # {slug: {value, dvalue}} as Decimal, read by the Watch mapper for
                    # range alerts. None (skipped by the upsert) when the week has none.
                    'estimated_paces': estimated_paces or None,
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

        # A3: write the home aggregates to the wellness table. Non-blocking: a
        # failure here must never break the existing session sync.
        try:
            _store_home_campus(goals, allowed_weeks, now, monday_current)
        except Exception as home_exc:  # noqa: BLE001
            logger.warning(f"Home campus aggregates write failed (non-fatal): {home_exc}")

        summary = {
            'weeks_synced': len(allowed_weeks),
            'sessions_stored': sessions_stored,
            'sessions_deleted': deleted,
            'zones_written': zones_written,
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


def _sample(value: Any, depth: int = 0) -> Any:
    """A bounded copy of a provider payload: strings cut to 80 chars, lists to 3 items.

    Keeps every key (so unused fields are visible) without returning whole texts.
    """
    if depth > 8:
        return '...'
    if isinstance(value, dict):
        return {k: _sample(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        out = [_sample(v, depth + 1) for v in value[:3]]
        if len(value) > 3:
            out.append(f'... +{len(value) - 3} more')
        return out
    if isinstance(value, str) and len(value) > 80:
        return value[:80] + '...'
    return value


def _probe_schema(token: str) -> Dict[str, Any]:
    """Describe the provider payload: key sets and every distinct pace object shape.

    Pace objects and estimatedPaces are training data (target paces), returned in
    full so a range (min/max) can be spotted. Free text (descriptions) is not
    returned, only the key names.
    """
    now = datetime.now(timezone.utc)
    weeks = _fetch_plan(
        token,
        int((now - timedelta(weeks=1)).timestamp() * 1000),
        int((now + timedelta(weeks=3)).timestamp() * 1000),
    )
    week_keys, session_keys, block_keys, exercise_keys, pace_keys = (set() for _ in range(5))
    pace_samples: Dict[str, Any] = {}
    estimated: List[Any] = []
    for week in weeks:
        week_keys.update(week.keys())
        if not estimated and week.get('estimatedPaces'):
            estimated = week['estimatedPaces']
        for session in week.get('sessions', []) or []:
            session_keys.update(session.keys())
            for block in session.get('exercisesBlocks', []) or []:
                block_keys.update(block.keys())
                for exercise in block.get('exercises', []) or []:
                    exercise_keys.update(exercise.keys())
                    pace = exercise.get('pace') or {}
                    pace_keys.update(pace.keys())
                    shape = f"{pace.get('name')}|{','.join(sorted(pace.keys()))}"
                    pace_samples.setdefault(shape, pace)
    headers = {"Authorization": f"Bearer {token}"}
    extra: Dict[str, Any] = {}
    for name in ('goal/active', 'assiduity-status'):
        try:
            resp = requests.get(f"{API_BASE}/smart-training/{name}", headers=headers, timeout=10)
            body = resp.json() if resp.status_code == 200 else {}
            extra[name] = sorted(body.keys()) if isinstance(body, dict) else type(body).__name__
        except Exception as exc:  # diagnostic only
            extra[name] = f"error {type(exc).__name__}"
    sample_week = next((w for w in weeks if w.get('access') == 'allowed'), weeks[0] if weeks else {})
    goal_sample: Any = None
    try:
        resp = requests.get(f"{API_BASE}/smart-training/goal/active", headers=headers, timeout=10)
        goal_sample = _sample(resp.json()) if resp.status_code == 200 else None
    except Exception as exc:  # diagnostic only
        goal_sample = f"error {type(exc).__name__}"
    return {
        'weeks': len(weeks),
        'sample_week': _sample(sample_week),
        'goal_active_sample': goal_sample,
        'week_keys': sorted(week_keys),
        'session_keys': sorted(session_keys),
        'block_keys': sorted(block_keys),
        'exercise_keys': sorted(exercise_keys),
        'pace_keys': sorted(pace_keys),
        'pace_samples': list(pace_samples.values())[:40],
        'estimated_paces': estimated,
        'other_endpoints_keys': extra,
    }


def _monday_of_iso_week(dt: datetime) -> datetime:
    """Return Monday 00:00 UTC of the ISO week containing dt."""
    return (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def _to_iso_week(week_date_ms: int) -> str:
    """Convert timestamp ms to ISO week string like '2026-W21'."""
    dt = datetime.fromtimestamp(week_date_ms / 1000, tz=timezone.utc)
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


# --------------------------------------------------------------------- A3 home
#
# Home aggregates for GET /home/summary, written to the wellness table under
# campus#* keys. Separate from the coaching-sessions table on purpose: the
# session cleanup and three readers there treat any non `athlete-context` row as
# a session, so these must not live beside the sessions.

# Competitive race-pace slugs -> (contract distance label, distance in km).
_COMPETITIVE_SLUGS = {
    "5km": ("5km", 5.0),
    "10km": ("10km", 10.0),
    "half-marathon": ("half-marathon", 21.0975),
    "semi": ("half-marathon", 21.0975),
    "half": ("half-marathon", 21.0975),
    "21km": ("half-marathon", 21.0975),
    "marathon": ("marathon", 42.195),
    "42km": ("marathon", 42.195),
}


def _wellness_table():
    return dynamodb.Table(WELLNESS_TABLE)


def _finite(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float('inf'), float('-inf')) or f <= 0:
        return None
    return f


def _campus_competitive_paces(estimated: Any) -> Dict[str, Dict[str, Any]]:
    """Competitive race predictions from ``estimatedPaces``.

    Thin wrapper around the single parser ``_parse_estimated_paces`` (shared with
    feat/paces-be). That parser returns ``{slug: {value, dvalue}}`` for every
    slug; here we keep only the competitive race distances and turn each into
    ``{distance_label: {pace_s, dpace_s, time_s, range_s:[lo,hi]}}``.
    First slug per distance wins; ``time_s = value * distance_km``,
    ``range = (value +/- dvalue) * distance_km``.
    """
    parsed = _parse_estimated_paces(estimated)
    out: Dict[str, Dict[str, Any]] = {}
    # Walk the provider list order so the FIRST competitive entry for a distance
    # wins (same rule as the single parser), not the slug-map order.
    order = [p.get('slug') for p in estimated if isinstance(p, dict)] if isinstance(estimated, list) else []
    for slug in order:
        mapping = _COMPETITIVE_SLUGS.get(slug)
        if not mapping:
            continue
        label, dist_km = mapping
        if label in out:  # first slug for this distance wins
            continue
        entry = parsed.get(slug)
        if not entry:
            continue
        value = float(entry['value'])
        dvalue = float(entry['dvalue'])
        out[label] = {
            'pace_s': round(value),
            'dpace_s': round(dvalue),
            'time_s': round(value * dist_km),
            'range_s': [round((value - dvalue) * dist_km),
                        round((value + dvalue) * dist_km)],
        }
    return out


def _normalise_goal_type(goal_type: Any) -> str:
    """Normalise a raw Campus ``goalType`` to a prediction slug.

    The predictions are keyed by ``5km/10km/half-marathon/marathon``; the goal's
    ``type`` must match so the reader finds ``predicted_*``. Reuses the same slug
    map as the competitive paces.
    """
    if not isinstance(goal_type, str):
        return ''
    key = goal_type.strip().lower().replace('_', '-').replace(' ', '-')
    mapping = _COMPETITIVE_SLUGS.get(key)
    if mapping:
        return mapping[0]
    return goal_type


def _goal_item(goals: Optional[List[Dict[str, Any]]], now: datetime) -> Optional[Dict[str, Any]]:
    """Build the campus#goal item from the goal tri-state. ``None`` -> no write
    (return None), ``[]`` -> {active: false}, a goal -> the full card.

    Field paths are the real provider shapes (verified against a captured
    goal/active payload): the race name and targets live under
    ``sessionCompetitionInfo.sessionCompetition`` and its ``stats``
    (``expectedDuration`` seconds, ``expectedDistance`` already in km);
    weekly volume under ``simulatedWeeklyVolume.lowerBound/upperBound``;
    plan totals under ``stats.trainingsCount/trainingsDoneCount``.
    ``week_index`` is not here: it is the current week's ``goalDuration.index``,
    stored on the week item and copied into the card by the reader.
    """
    if goals is None:
        return None
    synced_at = now.isoformat()
    if not goals:
        return {'sk': 'campus#goal', 'active': False, 'synced_at': synced_at}

    g = goals[0] if isinstance(goals[0], dict) else {}
    stats = g.get('stats', {}) if isinstance(g.get('stats'), dict) else {}
    sci = g.get('sessionCompetitionInfo', {}) if isinstance(g.get('sessionCompetitionInfo'), dict) else {}
    sc = sci.get('sessionCompetition', {}) if isinstance(sci.get('sessionCompetition'), dict) else {}
    sc_stats = sc.get('stats', {}) if isinstance(sc.get('stats'), dict) else {}

    item: Dict[str, Any] = {
        'sk': 'campus#goal',
        'active': True,
        'synced_at': synced_at,
        'name': sc.get('displayName') or sc.get('name') or '',
        'type': _normalise_goal_type(g.get('goalType', '')),
        'competition_date': str(g.get('competitionDate', '')),
        'sessions_per_week': g.get('sessionsPerWeek'),
        'weeks_total': g.get('durationInWeeks'),
        'trainings_done': stats.get('trainingsDoneCount'),
        'trainings_total': stats.get('trainingsCount'),
    }
    td = _finite(sc_stats.get('expectedDuration'))
    if td is not None:
        item['target_duration_s'] = round(td)
    dist = _finite(sc_stats.get('expectedDistance'))  # already km
    if dist is not None:
        item['target_distance_km'] = round(dist, 3)
    vol = g.get('simulatedWeeklyVolume', {}) if isinstance(g.get('simulatedWeeklyVolume'), dict) else {}
    vol_low = _finite(vol.get('lowerBound'))
    vol_high = _finite(vol.get('upperBound'))
    if vol_low is not None:
        item['weekly_volume_low'] = round(vol_low)
    if vol_high is not None:
        item['weekly_volume_high'] = round(vol_high)
    # Drop None values (DynamoDB cannot store them).
    return {k: v for k, v in item.items() if v is not None}


def _week_stat_item(week: Dict[str, Any], now: datetime) -> Optional[Dict[str, Any]]:
    """campus#week#YYYY-Www from the real smart-training week shape.

    ``weekStats.expectedDistance/realDistance`` are ALREADY in km (do not divide
    by 1000); ``expectedDuration/realDuration`` are seconds. The week also
    carries ``goalDuration.index`` (plan week number), ``context.cycleTheme`` and
    ``coach.name``; the reader copies the current week's values into the goal
    card so there is one source for them.
    """
    week_date = week.get('weekDate')
    if week_date is None:
        return None
    week_iso = _to_iso_week(week_date)
    ws = week.get('weekStats', {}) if isinstance(week.get('weekStats'), dict) else {}
    gd = week.get('goalDuration', {}) if isinstance(week.get('goalDuration'), dict) else {}
    ctx = week.get('context', {}) if isinstance(week.get('context'), dict) else {}
    coach = week.get('coach', {}) if isinstance(week.get('coach'), dict) else {}
    item: Dict[str, Any] = {'sk': f'campus#week#{week_iso}', 'week': week_iso,
                            'synced_at': now.isoformat()}
    exp_dist = _finite(ws.get('expectedDistance'))
    real_dist = _finite(ws.get('realDistance'))
    exp_dur = _finite(ws.get('expectedDuration'))
    real_dur = _finite(ws.get('realDuration'))
    if exp_dist is not None:
        item['expected_distance_km'] = round(exp_dist, 1)
    if real_dist is not None:
        item['real_distance_km'] = round(real_dist, 1)
    if exp_dur is not None:
        item['expected_duration_s'] = round(exp_dur)
    if real_dur is not None:
        item['real_duration_s'] = round(real_dur)
    week_index = gd.get('index')
    if isinstance(week_index, int):
        item['week_index'] = week_index
    weeks_total = gd.get('durationInWeeks')
    if isinstance(weeks_total, int):
        item['weeks_total'] = weeks_total
    cycle_theme = ctx.get('cycleTheme')
    if cycle_theme:
        item['cycle_theme'] = cycle_theme
    coach_name = coach.get('name')
    if coach_name:
        item['coach_name'] = coach_name
    return item


def _store_home_campus(goals, allowed_weeks, now, monday_current) -> None:
    """Write campus#goal (tri-state), campus#pred#YYYY-Www (current week), and
    campus#week#YYYY-Www to the wellness table via UpdateItem (SET). Does nothing
    without an owner."""
    if not CAMPUS_OWNER_STRAVA_ID:
        logger.info("No CAMPUS_OWNER_STRAVA_ID; skipping home campus aggregates")
        return
    user_id = CAMPUS_OWNER_STRAVA_ID
    table = _wellness_table()

    goal_item = _goal_item(goals, now)
    if goal_item is not None:  # None means "could not read" -> keep previous item
        _put_campus_item(table, user_id, goal_item)

    current_ms = int(monday_current.timestamp() * 1000)
    for week in allowed_weeks:
        wk_item = _week_stat_item(week, now)
        if wk_item is not None:
            _put_campus_item(table, user_id, wk_item)

        # Predictions: one item per week, labelled with the SAME ISO week as the
        # sessions. Only the current ISO week's item is "current" to the reader.
        if week.get('weekDate') == current_ms:
            paces = _campus_competitive_paces(week.get('estimatedPaces', []))
            if paces:
                week_iso = _to_iso_week(week['weekDate'])
                pred_item = {
                    'sk': f'campus#pred#{week_iso}',
                    'source_week': week_iso,
                    'synced_at': now.isoformat(),
                    **paces,
                }
                _put_campus_item(table, user_id, pred_item)


def _put_campus_item(table: Any, user_id: str, item: Dict[str, Any]) -> None:
    """UpdateItem(SET) one campus#* home-aggregate row, keyed by (user_id, sk).

    SET of each computed attribute and REMOVE of every owned attribute that is now
    absent, so a value that disappears from Campus is never shown as current.
    The sort key is never in the expression (DynamoDB rejects updating a key).
    """
    attrs = _decimalize({k: v for k, v in item.items() if k != 'sk'})
    names: Dict[str, str] = {}
    values: Dict[str, Any] = {}
    set_parts = []
    for idx, (key, value) in enumerate(attrs.items()):
        names[f'#a{idx}'] = key
        values[f':a{idx}'] = value
        set_parts.append(f'#a{idx} = :a{idx}')
    remove_parts = []
    for idx, key in enumerate(sorted(_owned_campus_keys(item['sk']) - set(attrs))):
        names[f'#r{idx}'] = key
        remove_parts.append(f'#r{idx}')
    expr = 'SET ' + ', '.join(set_parts)
    if remove_parts:
        expr += ' REMOVE ' + ', '.join(remove_parts)
    table.update_item(
        Key={'user_id': user_id, 'sk': item['sk']},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


_GOAL_KEYS = {
    'active', 'synced_at', 'name', 'type', 'competition_date', 'sessions_per_week',
    'weeks_total', 'trainings_done', 'trainings_total', 'target_duration_s',
    'target_distance_km', 'weekly_volume_low', 'weekly_volume_high',
}
_WEEK_KEYS = {
    'week', 'synced_at', 'week_index', 'weeks_total', 'cycle_theme', 'coach_name',
    'expected_distance_km', 'real_distance_km', 'expected_duration_s', 'real_duration_s',
}
_PRED_KEYS = {'source_week', 'synced_at', '5km', '10km', 'half-marathon', 'marathon'}


def _owned_campus_keys(sk: str) -> set:
    """Attributes this sync owns on a campus#* row (REMOVEd when absent)."""
    if sk == 'campus#goal':
        return _GOAL_KEYS
    if sk.startswith('campus#week#'):
        return _WEEK_KEYS
    if sk.startswith('campus#pred#'):
        return _PRED_KEYS
    return set()


def _decimalize(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _decimalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimalize(v) for v in obj]
    return obj


def _find_pace(paces: List, slug: str) -> Optional[float]:
    """Find a pace value by slug from the estimatedPaces list."""
    if not paces:
        return None
    for p in paces:
        if isinstance(p, dict) and p.get('slug') == slug:
            return p.get('value')
    return None


def _finite_number(value: Any) -> Optional[float]:
    """A finite float from int / float / Decimal / numeric string, else None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _parse_estimated_paces(paces: Any) -> Dict[str, Dict[str, Decimal]]:
    """``week.estimatedPaces`` -> ``{slug: {value, dvalue}}`` (s/km, Decimal, 1 decimal).

    Strict first wins: the FIRST entry for a slug decides, valid or not. A later
    duplicate is always dropped (and counts ``CampusEstimatedPaceDuplicate``), even when
    the first one was invalid: the provider order is the only stable rule we have, and
    letting a second entry stand in for a broken first one would hide the problem.
    An entry whose value is not a finite number > 0, or whose dvalue is not a finite
    number >= 0, is ignored (its slug stays absent).
    """
    parsed: Dict[str, Dict[str, Decimal]] = {}
    if not isinstance(paces, list):
        return parsed
    seen: set[str] = set()
    for entry in paces:
        if not isinstance(entry, dict):
            continue
        slug = entry.get('slug')
        if not isinstance(slug, str) or not slug:
            continue
        if slug in seen:
            metrics.add_metric(name="CampusEstimatedPaceDuplicate", unit=MetricUnit.Count, value=1)
            continue
        seen.add(slug)
        value = _finite_number(entry.get('value'))
        dvalue = _finite_number(entry.get('dvalue'))
        if value is None or value <= 0 or dvalue is None or dvalue < 0:
            continue
        parsed[slug] = {
            'value': Decimal(str(round(value, 1))),
            'dvalue': Decimal(str(round(dvalue, 1))),
        }
    return parsed


def _write_campus_zones(
    estimated_paces: Dict[str, Dict[str, Decimal]], week_iso: str, now: datetime
) -> bool:
    """Write the current week's Campus zones on the OWNER's user-config item.

    Owner = ``DEFAULT_USER_ID`` only, never an event ``user_id``: the Campus account
    belongs to one athlete. Top-level attributes, one ``UpdateItem SET`` of the three,
    on an existing item only (``attribute_exists``), so a typo in the owner id never
    creates a stray row. Incomplete paces write nothing (``CampusZonesSkipped``): the
    readers keep the last full map. Never raises: a zone failure must not fail the sync.

    Rollback: turn ``CAMPUS_ZONES_ENABLED`` off and deploy FIRST, then
    ``REMOVE campus_pace_zones, campus_pace_zones_week, campus_pace_zones_synced_at``
    (in the other order the next scheduled sync writes them back).
    """
    owner = os.environ.get('DEFAULT_USER_ID', '')
    if not owner:
        logger.warning("Campus zones not written: DEFAULT_USER_ID is empty")
        metrics.add_metric(name="CampusZonesSkipped", unit=MetricUnit.Count, value=1)
        return False
    zones = build_campus_zones(estimated_paces)
    if not zones:
        logger.warning("Campus zones not written: estimatedPaces incomplete or invalid")
        metrics.add_metric(name="CampusZonesSkipped", unit=MetricUnit.Count, value=1)
        return False
    try:
        dynamodb.Table(USER_CONFIG_TABLE).update_item(
            Key={'user_id': owner},
            UpdateExpression='SET campus_pace_zones = :z, campus_pace_zones_week = :w, '
                             'campus_pace_zones_synced_at = :t',
            ConditionExpression='attribute_exists(user_id)',
            ExpressionAttributeValues={':z': zones, ':w': week_iso, ':t': now.isoformat()},
        )
    except ClientError as e:
        logger.warning("Campus zones write failed", extra={
            "error_code": e.response.get('Error', {}).get('Code', '')})
        metrics.add_metric(name="CampusZonesSkipped", unit=MetricUnit.Count, value=1)
        return False
    metrics.add_metric(name="CampusZonesWritten", unit=MetricUnit.Count, value=1)
    return True


def _pace_fields(pace_info: Dict[str, Any]) -> Dict[str, Any]:
    """Structured pace fields of one step, next to the unchanged ``pace`` string.

    ``pace_kind`` (range / single-value / abstract), ``pace_slug``, ``pace_zone``
    (provider ``zoneKind``) and ``pace_value_s``: the provider integer, under the same
    ``< 1000`` guard as the string (above it is an abstract placeholder, not a pace).
    Absent or wrong-typed fields are left out, never guessed.
    """
    fields: Dict[str, Any] = {}
    for key, source in (('pace_kind', 'kind'), ('pace_slug', 'slug'), ('pace_zone', 'zoneKind')):
        value = pace_info.get(source)
        if isinstance(value, str) and value:
            fields[key] = value
    value_s = _finite_number(pace_info.get('value'))
    if value_s is not None and 0 < value_s < 1000:
        fields['pace_value_s'] = int(value_s)
    return fields


def _format_pace(seconds_per_km: Optional[float]) -> Optional[str]:
    """Convert seconds/km to mm:ss/km string."""
    if not seconds_per_km:
        return None
    minutes = int(seconds_per_km) // 60
    seconds = int(seconds_per_km) % 60
    return f"{minutes}:{seconds:02d}/km"


def _coerce_repeat(value: Any, default: int = 1) -> int:
    """Coerce a block ``repeat`` (int/float/Decimal/str) to a positive int."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default


def _build_exercise_entry(
    exercise: Dict[str, Any], block_type: str
) -> Dict[str, Any]:
    """Build a single exercise interval entry ``{type, duration, pace}``.

    The repetition factor is intentionally NOT carried here: it belongs to the
    block (see :func:`_build_intervals`), not to the individual exercise.
    """
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

    entry: Dict[str, Any] = {'type': ex_type, 'duration': dur_str, 'pace': pace_str}
    if isinstance(pace_info, dict):
        entry.update(_pace_fields(pace_info))

    # Movement name (PPG/renfo: "Split Squat", "Gainage Frontal", ...). Dropping it
    # left strength sessions as empty {type:work, duration:'', pace:''} placeholders,
    # so the coach could never name the exercises done. Keep it when present.
    name = exercise.get('name')
    if name:
        entry['name'] = name

    # A PPG exercise's own ``repeat`` is its rep count (10, 12, ...), distinct from
    # the block ``repeat`` (the number of sets). Surfacing it as ``reps`` lets the
    # coach state "10 mollets" instead of a bare movement name. Recovery entries
    # carry repeat=1 and no meaningful rep count, so only work exercises get it.
    reps = exercise.get('repeat')
    if ex_type == 'work' and isinstance(reps, (int, float)) and reps > 1:
        entry['reps'] = int(reps)

    return entry


def _build_intervals(session: Dict, paces: List) -> List[Dict[str, Any]]:
    """Transform ``exercisesBlocks`` into a simplified interval list.

    The ``repeat`` factor is a property of the *block*, not of each exercise.
    Copying it onto every work exercise (the previous behaviour) let a reader
    (human or LLM) mistake the block repeat for a per-exercise repetition count,
    and inflated downstream work-interval counts for multi-exercise blocks.

    A repeated block (``repeat > 1``) is therefore emitted as a single block
    entry carrying its ``repeat`` and the ordered list of its ``exercises``::

        {'type': 'block', 'repeat': 9,
         'exercises': [{'type': 'work', 'duration': '1 min', 'pace': '...'},
                       {'type': 'recovery', 'duration': '1 min', 'pace': '...'}]}

    A non-repeated block (``repeat <= 1``) is flattened to one top-level entry
    per exercise (the historical shape), so single-pass sessions still read
    naturally::

        {'type': 'work', 'duration': '5 min', 'pace': '...'}

    Consumers must tolerate BOTH shapes (see
    ``modules_processing._normalize_intervals``): the DynamoDB table keeps
    legacy rows in the old flat form until the next provider sync.
    """
    intervals: List[Dict[str, Any]] = []
    blocks = session.get('exercisesBlocks', [])

    for block in blocks:
        block_type = block.get('blockType', 'work')
        repeat = _coerce_repeat(block.get('repeat', 1))

        exercises = [
            _build_exercise_entry(exercise, block_type)
            for exercise in block.get('exercises', [])
        ]
        if not exercises:
            continue

        if repeat > 1:
            intervals.append({
                'type': 'block',
                'repeat': repeat,
                'exercises': exercises,
            })
        else:
            intervals.extend(exercises)

    return intervals


def _upsert_provider_session(table: Any, item: Dict[str, Any]) -> None:
    """Merge provider-owned fields into a session row (never ``put_item``).

    Uses an update expression so local execution state written by the content
    pipeline (``local_status``, ``matched_activity_id``, ``match_score`` and
    ``completed_at``) survives the daily provider sync untouched. Creates the row
    if it does not yet exist.

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


def _sync_athlete_context(token: str, table: Any, user_id: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch and store supplementary athlete context from Campus Coach API.

    Returns the parsed goal/active payload (a list) ONLY on a 200 response, so
    the caller can tell the three states apart (A3 tri-state): ``None`` means the
    goal could not be read (non-200 or exception) and the previous home item must
    be kept; ``[]`` means "no active goal" and the home card goes inactive.
    """
    goals_result: Optional[List[Dict[str, Any]]] = None
    try:
        headers = {"Authorization": f"Bearer {token}"}

        # Active goal (race objective, progress)
        goal_resp = requests.get(f"{API_BASE}/smart-training/goal/active", headers=headers, timeout=10)
        if goal_resp.status_code == 200:
            parsed = goal_resp.json()
            if isinstance(parsed, list):
                goals = parsed
                goals_result = goals
            else:
                # A 200 whose body is not a list is an unexpected provider
                # response. Same outcome as before this change (it used to raise
                # on goals[0]): write nothing, keep both previous items.
                logger.warning("Campus goal/active returned a non-list body; skipping athlete context")
                return None
        else:
            goals = []

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
        return None
    return goals_result
