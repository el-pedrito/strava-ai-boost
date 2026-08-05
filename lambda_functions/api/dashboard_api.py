"""
Dashboard API Lambda Function

Provides dashboard data for the local web interface including:
- Activity processing statistics
- Engagement metrics
- Recent activity history
- System performance metrics
"""

import json
import os
from typing import Dict, Any, List, Optional
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, timezone, date
from shared.campus_status import STATUS_DONE, effective_status
from shared.strength_exercises import canonicalize_exercise_name
from shared.responses import (
    CORS_HEADERS_READ as CORS_HEADERS,
    create_success_response,
    create_error_response,
)
from shared.logger import get_logger, inject_correlation_id, metrics, MetricUnit
import time

logger = get_logger("dashboard_api")

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
_cloudwatch = None


def _get_cloudwatch():
    global _cloudwatch
    if _cloudwatch is None:
        _cloudwatch = boto3.client('cloudwatch')
    return _cloudwatch

# Environment variables
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']
USER_CONFIG_TABLE = os.environ['USER_CONFIG_TABLE']
COACHING_SESSIONS_TABLE = os.environ['COACHING_SESSIONS_TABLE']
DEFAULT_USER_ID = os.environ.get('DEFAULT_USER_ID', '')
# Coach endpoints fail closed without an authenticated Strava identity. A
# DEFAULT_USER_ID fallback is honored only when this flag is explicitly enabled
# for local dev/test (R1.3) and never overrides a real authenticated id.
COACH_ALLOW_DEFAULT_USER = os.environ.get(
    'COACH_ALLOW_DEFAULT_USER', ''
).strip().lower() in ('1', 'true', 'yes', 'on')
# Recovery snapshot freshness threshold in hours (R3.2, default 36h).
RECOVERY_STALE_THRESHOLD_HOURS = int(os.environ.get('RECOVERY_STALE_HOURS', '36'))


def _get_user_id(event: Dict[str, Any]) -> str:
    """Extract user_id from Cognito JWT claims or fall back to DEFAULT_USER_ID."""
    try:
        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        # custom:strava_id is set during OAuth callback (maps to Strava athlete ID)
        strava_id = claims.get('custom:strava_id', '')
        if strava_id:
            return strava_id
    except (AttributeError, TypeError):
        pass
    # Cognito sub is NOT usable as user_id (DynamoDB uses Strava athlete ID)
    return DEFAULT_USER_ID


def _get_strava_claim(event: Dict[str, Any]) -> str:
    """Return the Cognito custom:strava_id claim, or '' when absent."""
    try:
        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        return claims.get('custom:strava_id', '') or ''
    except (AttributeError, TypeError):
        return ''


def _resolve_coach_user_id(event: Dict[str, Any]) -> Optional[str]:
    """Resolve the Coach user id from the authenticated Cognito claim.

    Fails closed (returns None) when no `custom:strava_id` claim is present so
    protected Coach endpoints never fall back to an all-users scan (R1). A
    DEFAULT_USER_ID fallback is honored only when COACH_ALLOW_DEFAULT_USER is
    explicitly enabled for local dev/test, and never overrides a real claim.
    """
    strava_id = _get_strava_claim(event)
    if strava_id:
        return strava_id

    metrics.add_metric(name="CoachSummaryMissingUserClaim", unit=MetricUnit.Count, value=1)
    logger.warning("Coach summary request missing custom:strava_id claim; failing closed")

    if COACH_ALLOW_DEFAULT_USER and DEFAULT_USER_ID:
        logger.info("Using DEFAULT_USER_ID fallback for Coach (dev/test mode)")
        return DEFAULT_USER_ID
    return None


def _query_user_activities(user_id: str, since: datetime = None, projection: str = None) -> List[Dict[str, Any]]:
    """Query activities for the default user using GSI. Falls back to scan if no user_id."""
    table = dynamodb.Table(ACTIVITIES_TABLE)

    if user_id:
        kwargs: Dict[str, Any] = {
            "IndexName": "UserActivitiesIndex",
            "KeyConditionExpression": "user_id = :uid",
            "ExpressionAttributeValues": {":uid": user_id},
            "ScanIndexForward": False,  # newest first
        }
        if since:
            kwargs["KeyConditionExpression"] += " AND created_at >= :since"
            kwargs["ExpressionAttributeValues"][":since"] = since.isoformat()
        if projection:
            kwargs["ProjectionExpression"] = projection
        response = table.query(**kwargs)
        items = response.get("Items", [])
        while "LastEvaluatedKey" in response:
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = table.query(**kwargs)
            items.extend(response.get("Items", []))
        return items

    # Fallback: scan (no user_id configured)
    response = table.scan()
    items = response.get("Items", [])
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))
    if since:
        items = [i for i in items if i.get("created_at", "") >= since.isoformat()]
    return items


# Simple in-memory cache with TTL for performance optimization
_cache = {}
_cache_ttl = {}
CACHE_TTL_SECONDS = 300  # 5 minutes cache TTL

def get_cached_or_compute(cache_key: str, compute_func, *args, **kwargs):
    """Get data from cache or compute and cache it"""
    current_time = time.time()
    
    # Check if we have cached data that's still valid
    if cache_key in _cache and cache_key in _cache_ttl:
        if current_time < _cache_ttl[cache_key]:
            logger.info(f"Cache hit for {cache_key}")
            return _cache[cache_key]
    
    # Compute fresh data
    logger.info(f"Cache miss for {cache_key}, computing fresh data")
    result = compute_func(*args, **kwargs)
    
    # Cache the result
    _cache[cache_key] = result
    _cache_ttl[cache_key] = current_time + CACHE_TTL_SECONDS
    
    # Clean up old cache entries (simple cleanup)
    keys_to_remove = []
    for key, ttl in _cache_ttl.items():
        if current_time > ttl:
            keys_to_remove.append(key)
    for key in keys_to_remove:
        _cache.pop(key, None)
        _cache_ttl.pop(key, None)

    return result


def get_coach_recaps(event: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """Get paginated weekly audio recaps or trigger generation."""
    method = event.get("httpMethod", "GET")

    if method == "POST":
        # On-demand generation: invoke the recap Lambda async
        lambda_client = boto3.client("lambda")
        lambda_client.invoke(
            FunctionName="StravaAIBoost-WeeklyAudioRecap",
            InvocationType="Event",
            Payload=json.dumps({"user_id": user_id, "force": False}),
        )
        return {"status": "generating", "message": "Recap generation started"}

    # GET: return paginated list of recaps
    recap_table_name = os.environ.get("RECAP_TABLE", "strava-ai-boost-weekly-recaps")
    recap_table = dynamodb.Table(recap_table_name)
    bucket = os.environ.get("AUDIO_DEBRIEF_BUCKET", "")

    try:
        resp = recap_table.query(
            KeyConditionExpression="user_id = :uid",
            ExpressionAttributeValues={":uid": user_id},
            ScanIndexForward=False,
            Limit=10,
        )
        items = resp.get("Items", [])

        # Generate presigned URLs for each recap
        recaps = []
        for item in items:
            s3_key = item.get("s3_key", "")
            url = ""
            if s3_key and bucket:
                try:
                    url = s3.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": bucket, "Key": s3_key},
                        ExpiresIn=3600,
                    )
                except Exception:
                    pass
            recaps.append({
                "week": item.get("week", ""),
                "generated_at": item.get("generated_at", ""),
                "duration_seconds": item.get("duration_seconds", 0),
                "activity_count": item.get("activity_count", 0),
                "audio_url": url,
            })

        return {"recaps": recaps, "count": len(recaps)}
    except ClientError as e:
        logger.warning(f"Failed to query recaps: {e}")
        return {"recaps": [], "count": 0}
    keys_to_remove = []
    for key, ttl in _cache_ttl.items():
        if current_time > ttl:
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        _cache.pop(key, None)
        _cache_ttl.pop(key, None)
    
    return result



def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for dashboard API endpoints
    
    Handles various dashboard data requests
    """
    user_id = _get_user_id(event)
    inject_correlation_id(logger, event)
    try:
        http_method = event.get('httpMethod', 'GET')
        path = event.get('path', '')
        query_params = event.get('queryStringParameters') or {}

        # Handle CORS preflight
        if http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': CORS_HEADERS.copy(),
                'body': json.dumps({'status': 'ok'})
            }

        # Validate request
        validation_error = validate_request(event)
        if validation_error:
            return create_error_response(400, validation_error)

        # Route requests based on path
        if '/dashboard/stats' in path:
            response_data = get_dashboard_stats(query_params, user_id)
            return create_success_response(response_data)
        elif '/dashboard/activities' in path:
            response_data = get_activity_history(query_params, user_id)
            return create_success_response(response_data)
        elif '/dashboard/system' in path:
            response_data = get_system_stats(user_id)
            return create_success_response(response_data)
        elif '/coach/summary' in path:
            coach_user_id = _resolve_coach_user_id(event)
            if not coach_user_id:
                return create_error_response(403, 'Forbidden: authenticated Strava identity required')
            response_data = get_coach_summary(coach_user_id)
            return create_success_response(response_data)
        elif '/coach/recaps' in path:
            response_data = get_coach_recaps(event, user_id)
            return create_success_response(response_data)
        else:
            return create_error_response(404, 'Endpoint not found')
        
    except ClientError as e:
        logger.error(f"Dashboard API AWS error: {str(e)}", exc_info=True)
        return create_error_response(500, 'Internal server error')
    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Dashboard API data error: {str(e)}", exc_info=True)
        return create_error_response(500, 'Internal server error')


def validate_request(event: Dict[str, Any]) -> str:
    """Validate incoming request"""
    try:
        # Check HTTP method
        http_method = event.get('httpMethod', '')
        if http_method not in ['GET', 'POST', 'OPTIONS']:
            return f'Method {http_method} not allowed'
        
        # Validate query parameters for dashboard requests
        query_params = event.get('queryStringParameters') or {}
        
        # Validate 'days' parameter if present
        if 'days' in query_params:
            try:
                days = int(query_params['days'])
                if days < 1 or days > 365:
                    return 'Days parameter must be between 1 and 365'
            except ValueError:
                return 'Days parameter must be a valid integer'
        
        # Validate pagination parameters
        if 'limit' in query_params:
            try:
                limit = int(query_params['limit'])
                if limit < 1 or limit > 100:
                    return 'Limit parameter must be between 1 and 100'
            except ValueError:
                return 'Limit parameter must be a valid integer'
        
        if 'offset' in query_params:
            try:
                offset = int(query_params['offset'])
                if offset < 0:
                    return 'Offset parameter must be non-negative'
            except ValueError:
                return 'Offset parameter must be a valid integer'
        
        return None  # No validation errors

    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Request validation error: {str(e)}")
        return f'Request validation failed: {str(e)}'


def get_dashboard_stats(query_params: Dict[str, str], user_id: str) -> Dict[str, Any]:
    """Get dashboard statistics and metrics with caching"""
    try:
        # Get time range from query params (default: last 30 days)
        days = int(query_params.get('days', '30'))
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Create cache keys based on parameters
        cache_key_base = f"dashboard_stats_{days}d"
        
        # Get activity processing statistics (cached)
        activity_stats = get_cached_or_compute(
            f"{cache_key_base}_activity_stats",
            get_activity_processing_stats,
            start_date, user_id
        )
        
        # Get system performance metrics (cached with shorter TTL)
        performance_metrics = get_cached_or_compute(
            f"{cache_key_base}_performance",
            get_performance_metrics
        )
        
        # Get module usage statistics (cached)
        module_stats = get_cached_or_compute(
            f"{cache_key_base}_module_stats",
            get_module_usage_stats,
            start_date, user_id
        )
        
        # Get engagement metrics (cached)
        engagement_metrics = get_cached_or_compute(
            f"{cache_key_base}_engagement",
            get_engagement_metrics,
            start_date, user_id
        )
        
        return {
            'time_range': {
                'days': days,
                'start_date': start_date.isoformat(),
                'end_date': datetime.utcnow().isoformat()
            },
            'activity_stats': activity_stats,
            'performance_metrics': performance_metrics,
            'module_stats': module_stats,
            'engagement_metrics': engagement_metrics,
            'last_updated': datetime.utcnow().isoformat(),
            'cache_enabled': True
        }
        
    except (ClientError, ValueError, TypeError) as e:
        logger.error(f"Failed to get dashboard stats: {str(e)}")
        raise


def get_activity_processing_stats(start_date: datetime, user_id: str) -> Dict[str, Any]:
    """Get activity processing statistics from DynamoDB using GSI for better performance"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Use GSI to query by processing status for better performance
        # Query completed activities
        completed_response = table.query(
            IndexName='ProcessingStatusIndex',
            KeyConditionExpression='processing_status = :status',
            ExpressionAttributeValues={
                ':status': 'completed',
                ':start_date': start_date.isoformat()
            },
            FilterExpression='created_at >= :start_date'
        )
        completed_activities = completed_response.get('Items', [])
        
        # Query failed activities
        failed_response = table.query(
            IndexName='ProcessingStatusIndex',
            KeyConditionExpression='processing_status = :status',
            ExpressionAttributeValues={
                ':status': 'failed',
                ':start_date': start_date.isoformat()
            },
            FilterExpression='created_at >= :start_date'
        )
        failed_activities = failed_response.get('Items', [])
        
        # Query processing activities
        processing_response = table.query(
            IndexName='ProcessingStatusIndex',
            KeyConditionExpression='processing_status = :status',
            ExpressionAttributeValues={
                ':status': 'processing',
                ':start_date': start_date.isoformat()
            },
            FilterExpression='created_at >= :start_date'
        )
        processing_activities = processing_response.get('Items', [])
        
        # Combine all activities for total count and type breakdown
        all_activities = completed_activities + failed_activities + processing_activities
        
        # Calculate statistics
        total_activities = len(all_activities)
        completed_count = len(completed_activities)
        failed_count = len(failed_activities)
        processing_count = len(processing_activities)
        
        success_rate = (completed_count / total_activities * 100) if total_activities > 0 else 0
        
        return {
            'total_activities': total_activities,
            'completed_activities': completed_count,
            'failed_activities': failed_count,
            'processing_activities': processing_count,
            'success_rate': round(success_rate, 1),
            'activity_types': get_activity_type_breakdown(all_activities),
            'query_method': 'gsi_optimized'
        }
        
    except ClientError as e:
        logger.error(f"Failed to get activity processing stats with GSI: {str(e)}")
        # Fallback to query helper
        logger.info("Falling back to UserActivitiesIndex query")

        try:
            recent_activities = _query_user_activities(user_id, since=start_date)
            
            # Calculate statistics
            total_activities = len(recent_activities)
            completed_activities = len([a for a in recent_activities if a.get('processing_status') == 'completed'])
            failed_activities = len([a for a in recent_activities if a.get('processing_status') == 'failed'])
            processing_activities = len([a for a in recent_activities if a.get('processing_status') == 'processing'])
            
            success_rate = (completed_activities / total_activities * 100) if total_activities > 0 else 0
            
            return {
                'total_activities': total_activities,
                'completed_activities': completed_activities,
                'failed_activities': failed_activities,
                'processing_activities': processing_activities,
                'success_rate': round(success_rate, 1),
                'activity_types': get_activity_type_breakdown(recent_activities),
                'query_method': 'scan_fallback'
            }
            
        except ClientError as fallback_error:
            logger.error(f"Fallback scan method also failed: {str(fallback_error)}")
            return {
                'total_activities': 0,
                'completed_activities': 0,
                'failed_activities': 0,
                'processing_activities': 0,
                'success_rate': 0,
                'activity_types': {},
                'query_method': 'error',
                'error': 'Query failed'
            }


def _build_strength_progression(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate strength_history entries into per-exercise progression series.

    Each entry may carry `parsed_sets` = [{exercise, sets, reps, weight_kg}].
    For every (day, exercise) we compute the top weight and the total volume
    (sets*reps*weight). Returns a list of exercises ordered by number of tracked
    sessions (most tracked first) so the frontend can surface the top ones:

        [{"exercise": str,
          "points": [{"date": "YYYY-MM-DD", "top_weight_kg": float|None, "volume_kg": float|None}],
          "sessions": int}]
    """
    by_exercise: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        date = (entry.get('date') or '')[:10]
        parsed = entry.get('parsed_sets') or []
        if not date or not isinstance(parsed, list):
            continue
        per_exercise_volume = {
            canonicalize_exercise_name(e.get('exercise') or ''): e.get('volume_kg')
            for e in (entry.get('per_exercise') or []) if isinstance(e, dict)
        }
        for s in parsed:
            if not isinstance(s, dict):
                continue
            raw_name = s.get('exercise')
            if not raw_name:
                continue
            name = canonicalize_exercise_name(raw_name)
            if not name:
                continue
            weight = s.get('weight_kg')
            # Volume comes from the figures the pipeline computed with
            # shared/strength_volume.py (bodyweight coefficients, unilateral
            # doubling, per-set detail). Recomputing it here from the flat
            # sets/reps/weight summary under-reported by 33% on a real session,
            # and would let the chart disagree with the coach on the same data.
            volume = per_exercise_volume.get(canonicalize_exercise_name(raw_name))
            if volume is None:
                # Legacy row written before the wiring: explicit-weight only.
                sets = s.get('sets') or 0
                reps = s.get('reps') or 0
                if weight is not None and sets and reps:
                    volume = round(float(weight) * int(sets) * int(reps), 1)
            point = {
                'date': date,
                'top_weight_kg': float(weight) if weight is not None else None,
                'volume_kg': volume,
            }
            by_exercise.setdefault(name, []).append(point)

    progression: List[Dict[str, Any]] = []
    for name, points in by_exercise.items():
        # One point per day: keep the max top_weight / summed volume if several
        # entries share a date (e.g. an exercise split across the description).
        per_day: Dict[str, Dict[str, Any]] = {}
        for p in points:
            d = p['date']
            cur = per_day.get(d)
            if cur is None:
                per_day[d] = dict(p)
                continue
            if p['top_weight_kg'] is not None:
                cur['top_weight_kg'] = max(cur['top_weight_kg'] or 0, p['top_weight_kg'])
            if p['volume_kg'] is not None:
                cur['volume_kg'] = round((cur['volume_kg'] or 0) + p['volume_kg'], 1)
        merged = sorted(per_day.values(), key=lambda x: x['date'])
        progression.append({
            'exercise': name,
            'points': merged,
            'sessions': len(merged),
        })

    progression.sort(key=lambda e: e['sessions'], reverse=True)
    return progression


def _detect_health_anomalies(recovery: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic health-anomaly rules over the recovery snapshot.

    Pure function on the already-computed Intervals.icu recovery data (no new
    integration). Returns a list of {id, severity, message} — additive, and
    empty when data is missing so it never produces false positives on partial
    data. Thresholds are centralized here for easy tuning.
    """
    if not recovery:
        return []

    # Freshness-dependent rules must not fire on stale recovery data (R3.6).
    if recovery.get('stale'):
        return []

    anomalies: List[Dict[str, Any]] = []

    rhr_delta = recovery.get('resting_hr_delta_7d')
    form = recovery.get('form')
    sleep_delta = recovery.get('sleep_delta_7d_min')
    vo2_delta = recovery.get('vo2max_delta_7d')

    # Under-recovery: resting HR trending clearly up over the last 7 days.
    if rhr_delta is not None and rhr_delta >= 5:
        anomalies.append({
            'id': 'resting_hr_up',
            'severity': 'warning',
            'message': f"FC de repos +{round(rhr_delta)} bpm sur 7 jours — signe de fatigue ou de sous-récupération. Envisage une journée plus calme.",
        })

    # Overload: very negative form (TSB).
    if form is not None and form < -20:
        anomalies.append({
            'id': 'form_low',
            'severity': 'warning',
            'message': f"Forme (TSB) à {round(form)} — charge très élevée par rapport à ta fraîcheur. Prudence sur l'intensité.",
        })

    # Sleep dropping meaningfully.
    if sleep_delta is not None and sleep_delta <= -45:
        anomalies.append({
            'id': 'sleep_down',
            'severity': 'info',
            'message': f"Sommeil en baisse ({round(sleep_delta)} min/nuit sur 7 jours) — la récupération peut en pâtir.",
        })

    # VO2max trending down.
    if vo2_delta is not None and vo2_delta <= -1:
        anomalies.append({
            'id': 'vo2max_down',
            'severity': 'info',
            'message': f"VO2max en baisse ({round(vo2_delta, 1)} sur 7 jours) — à surveiller si ça persiste.",
        })

    return anomalies


def _as_float(value: Any) -> Optional[float]:
    """Coerce a value to float, preserving 0 and returning None for missing/invalid."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_recovery(
    activities: List[Dict[str, Any]],
    now: Optional[datetime] = None,
    stale_threshold_hours: int = RECOVERY_STALE_THRESHOLD_HOURS,
) -> Optional[Dict[str, Any]]:
    """Extract recovery state from the most recent activity carrying Intervals.icu data.

    Adds freshness metadata (`as_of`, `fetched_at`, `source`, `stale`) and keeps
    current sleep separate from the 30-day average (R3). Numeric zero deltas are
    preserved as 0.0 and never coerced to None. Pure function: it reads only the
    activity dicts passed in and performs no I/O.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    for a in activities:
        icu_raw = a.get('intervals_icu_json')
        if not icu_raw:
            continue
        try:
            icu = json.loads(icu_raw) if isinstance(icu_raw, str) else icu_raw
            fitness = icu.get('fitness', {}) or {}
            trends = icu.get('trends', {}) or {}
            vo2 = trends.get('vo2max', {}) or {}
            rhr = trends.get('resting_hr', {}) or {}
            sleep = trends.get('sleep_duration', {}) or {}

            raw_date = a.get('start_date') or a.get('start_date_local') or a.get('created_at', '')
            as_of = None
            as_of_dt = None
            if raw_date:
                try:
                    as_of_dt = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
                    if as_of_dt.tzinfo is None:
                        as_of_dt = as_of_dt.replace(tzinfo=timezone.utc)
                    as_of = as_of_dt.date().isoformat()
                except (ValueError, TypeError, AttributeError):
                    as_of_dt = None
            # Unknown measurement time is stale by definition: freshness-based
            # advice must fail safe rather than fire on undated recovery data.
            stale = True
            if as_of_dt is not None:
                stale = (now - as_of_dt) > timedelta(hours=stale_threshold_hours)
            fetched_at = a.get('updated_at') or a.get('created_at') or raw_date or None

            return {
                'form': _as_float(fitness.get('form')),
                'ctl': _as_float(fitness.get('ctl')),
                'atl': _as_float(fitness.get('atl')),
                'resting_hr': fitness.get('resting_hr'),
                'hrv': fitness.get('hrv'),
                'vo2max': _as_float(vo2.get('current')),
                'vo2max_delta_7d': _as_float(vo2.get('delta_7d')),
                'resting_hr_delta_7d': _as_float(rhr.get('delta_7d')),
                'sleep_hours': None,
                # Legacy field kept for frontend compatibility (30-day average).
                'sleep_display': _format_sleep(sleep.get('avg_30d')),
                'sleep_delta_7d_min': _sleep_delta_minutes(sleep.get('delta_7d')),
                # Corrected, separated sleep fields (additive) — R3.3.
                'sleep_current_sec': _as_float(sleep.get('current')),
                'sleep_average_30d_sec': _as_float(sleep.get('avg_30d')),
                'sleep_delta_7d_sec': _as_float(sleep.get('delta_7d')),
                'sleep_current_display': _format_sleep(sleep.get('current')),
                'sleep_average_30d_display': _format_sleep(sleep.get('avg_30d')),
                # Freshness metadata — R3.1.
                'as_of': as_of,
                'fetched_at': fetched_at,
                'source': 'intervals_icu',
                'stale': stale,
            }
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    return None


def _format_sleep(seconds) -> Optional[str]:
    """Format sleep seconds as Xh:MM."""
    if seconds is None:
        return None
    try:
        total = int(float(seconds))
        h = total // 3600
        m = (total % 3600) // 60
        return f"{h}h{m:02d}"
    except (ValueError, TypeError):
        return None


def _sleep_delta_minutes(delta_seconds) -> Optional[int]:
    """Convert sleep delta (seconds) to minutes."""
    if delta_seconds is None:
        return None
    try:
        return round(float(delta_seconds) / 60)
    except (ValueError, TypeError):
        return None


def get_activity_type_breakdown(activities: List[Dict[str, Any]]) -> Dict[str, int]:
    """Get breakdown of activities by type"""
    type_counts = {}
    
    for activity in activities:
        activity_type = activity.get('activity_type', 'Unknown')
        type_counts[activity_type] = type_counts.get(activity_type, 0) + 1
    
    return type_counts


def get_performance_metrics() -> Dict[str, Any]:
    """Get system performance metrics from CloudWatch"""
    try:
        # Get Lambda function metrics for the last hour
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)
        
        # Get average duration for key Lambda functions
        lambda_functions = [
            'StravaAIBoost-WebhookHandler',
            'StravaAIBoost-ContentGenerator',
            'StravaAIBoost-ActivityFetcher'
        ]
        
        function_metrics = {}
        
        for function_name in lambda_functions:
            try:
                # Get average duration
                duration_response = _get_cloudwatch().get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Duration',
                    Dimensions=[
                        {
                            'Name': 'FunctionName',
                            'Value': function_name
                        }
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,  # 1 hour
                    Statistics=['Average']
                )
                
                avg_duration = 0
                if duration_response['Datapoints']:
                    avg_duration = duration_response['Datapoints'][0]['Average']
                
                # Get error count
                error_response = _get_cloudwatch().get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Errors',
                    Dimensions=[
                        {
                            'Name': 'FunctionName',
                            'Value': function_name
                        }
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=['Sum']
                )
                
                error_count = 0
                if error_response['Datapoints']:
                    error_count = error_response['Datapoints'][0]['Sum']
                
                function_metrics[function_name] = {
                    'avg_duration_ms': round(avg_duration, 2),
                    'error_count': int(error_count)
                }
                
            except ClientError as e:
                logger.warning(f"Failed to get metrics for {function_name}: {str(e)}")
                function_metrics[function_name] = {
                    'avg_duration_ms': 0,
                    'error_count': 0
                }
        
        return {
            'lambda_functions': function_metrics,
            'last_updated': datetime.utcnow().isoformat()
        }
        
    except ClientError as e:
        logger.error(f"Failed to get performance metrics: {str(e)}")
        return {
            'lambda_functions': {},
            'last_updated': datetime.utcnow().isoformat()
        }


def get_module_usage_stats(start_date: datetime, user_id: str) -> Dict[str, Any]:
    """Get module usage statistics"""
    try:
        recent_activities = _query_user_activities(user_id, since=start_date)

        # Count module usage
        module_counts = {}
        total_with_modules = 0

        for activity in recent_activities:
            modules_used = activity.get('modules_used', [])
            if modules_used:
                total_with_modules += 1
                for module in modules_used:
                    module_counts[module] = module_counts.get(module, 0) + 1

        return {
            'total_activities_with_modules': total_with_modules,
            'module_usage': module_counts,
            'most_used_module': max(module_counts.items(), key=lambda x: x[1])[0] if module_counts else None
        }

    except ClientError as e:
        logger.error(f"Failed to get module usage stats: {str(e)}")
        return {
            'total_activities_with_modules': 0,
            'module_usage': {},
            'most_used_module': None
        }


def get_engagement_metrics(start_date: datetime, user_id: str) -> Dict[str, Any]:
    """Get engagement metrics from DynamoDB stored activity data"""
    try:
        recent_activities = _query_user_activities(user_id, since=start_date)

        total_kudos = 0
        total_comments = 0
        total_activities = len(recent_activities)
        enhanced_activities = 0
        baseline_kudos = 0
        baseline_comments = 0

        for activity in recent_activities:
            kudos = activity.get('kudos_count', 0)
            comments = activity.get('comment_count', 0)
            total_kudos += kudos
            total_comments += comments

            if activity.get('enhanced_title') or activity.get('enhanced_description'):
                enhanced_activities += 1
            else:
                baseline_kudos += kudos
                baseline_comments += comments

        avg_kudos_per_activity = total_kudos / total_activities if total_activities > 0 else 0
        avg_comments_per_activity = total_comments / total_activities if total_activities > 0 else 0

        # Calculate engagement improvement (enhanced vs baseline)
        engagement_improvement = 0
        if enhanced_activities > 0 and (total_activities - enhanced_activities) > 0:
            enhanced_kudos = total_kudos - baseline_kudos
            avg_enhanced_kudos = enhanced_kudos / enhanced_activities
            avg_baseline_kudos = baseline_kudos / (total_activities - enhanced_activities)

            if avg_baseline_kudos > 0:
                kudos_improvement = ((avg_enhanced_kudos - avg_baseline_kudos) / avg_baseline_kudos) * 100
                engagement_improvement = max(0, kudos_improvement)

        return {
            'total_kudos': total_kudos,
            'total_comments': total_comments,
            'avg_kudos_per_activity': round(avg_kudos_per_activity, 1),
            'avg_comments_per_activity': round(avg_comments_per_activity, 1),
            'engagement_improvement': round(engagement_improvement, 1),
            'enhanced_activities': enhanced_activities,
            'total_activities': total_activities,
            'data_source': 'dynamodb'
        }

    except (ClientError, ValueError, TypeError) as e:
        logger.error(f"Failed to get engagement metrics: {str(e)}")
        return {
            'total_kudos': 0,
            'total_comments': 0,
            'avg_kudos_per_activity': 0,
            'avg_comments_per_activity': 0,
            'engagement_improvement': 0,
            'enhanced_activities': 0,
            'total_activities': 0,
            'error': 'Failed to load engagement metrics'
        }


def get_activity_history(query_params: Dict[str, str], user_id: str) -> Dict[str, Any]:
    """Get recent activity history with processing details using GSI for better performance"""
    try:
        # Get pagination parameters
        limit = int(query_params.get('limit', '20'))
        offset = int(query_params.get('offset', '0'))
        status_filter = query_params.get('status')  # Optional status filter
        activity_id_filter = query_params.get('activity_id')  # Optional single activity lookup
        
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Fast path: direct lookup by activity_id
        if activity_id_filter:
            response = table.get_item(Key={'activity_id': activity_id_filter})
            item = response.get('Item')
            if not item:
                return {'activities': [], 'total_count': 0, 'returned_count': 0, 'offset': 0, 'limit': 1, 'has_more': False}
            all_activities = [item]
            # Skip pagination logic, jump to formatting
            paginated_activities = all_activities
        else:
            all_activities = []

            if status_filter:
                # Use GSI to query by specific status
                try:
                    response = table.query(
                        IndexName='ProcessingStatusIndex',
                        KeyConditionExpression='processing_status = :status',
                        ExpressionAttributeValues={':status': status_filter},
                        ScanIndexForward=False  # Sort by created_at descending
                    )
                    all_activities = response.get('Items', [])
                except Exception as gsi_error:
                    logger.warning(f"GSI query failed, falling back to query: {str(gsi_error)}")
                    all_activities = _query_user_activities(user_id)
            else:
                # Get all activities - try GSI approach first
                try:
                    # Query each status separately and combine
                    statuses = ['completed', 'failed', 'processing', 'queued']
                    for status in statuses:
                        try:
                            response = table.query(
                                IndexName='ProcessingStatusIndex',
                                KeyConditionExpression='processing_status = :status',
                                ExpressionAttributeValues={':status': status},
                                ScanIndexForward=False
                            )
                            all_activities.extend(response.get('Items', []))
                        except Exception:
                            # Skip this status if query fails
                            continue

                    # If no activities found via GSI, fallback to query helper
                    if not all_activities:
                        all_activities = _query_user_activities(user_id)

                except Exception as gsi_error:
                    logger.warning(f"GSI queries failed, falling back to query: {str(gsi_error)}")
                    all_activities = _query_user_activities(user_id)

            # Sort by created_at descending (in case GSI didn't sort properly)
            all_activities.sort(key=lambda x: x.get('created_at', ''), reverse=True)

            # Apply pagination
            paginated_activities = all_activities[offset:offset + limit]
        
        # Format activities for display
        formatted_activities = []
        for activity in paginated_activities:
            gen_metadata = activity.get('generation_metadata') or {}
            confidence = gen_metadata.get('confidence', 0)
            if hasattr(confidence, '__float__'):
                confidence = float(confidence)

            similarity = activity.get('similarity_score', '')
            if similarity and hasattr(similarity, '__float__'):
                similarity = float(similarity)
            elif similarity:
                try:
                    similarity = float(similarity)
                except (ValueError, TypeError):
                    similarity = 0

            formatted_activity = {
                'activity_id': activity.get('activity_id'),
                'original_name': activity.get('original_name', ''),
                'enhanced_title': activity.get('enhanced_title', ''),
                'enhanced_description': activity.get('enhanced_description', ''),
                'start_date': activity.get('start_date', ''),
                'activity_type': activity.get('activity_type', ''),
                'distance': activity.get('distance', 0),
                'moving_time': activity.get('moving_time', 0),
                'processing_status': activity.get('processing_status', ''),
                'modules_used': activity.get('modules_used', []),
                'created_at': activity.get('created_at', ''),
                'updated_at': activity.get('updated_at', ''),
                'error_message': activity.get('error_message', ''),
                'kudos_count': activity.get('kudos_count', 0),
                'comment_count': activity.get('comment_count', 0),
                'confidence': confidence,
                'description_modified': activity.get('description_modified', None),
                'similarity_score': similarity,
                'feedback_analyzed': activity.get('feedback_analyzed', False),
                'generated_at': gen_metadata.get('generated_at', ''),
            }

            # Extract map polyline from activity_data_json if available
            activity_data_raw = activity.get('activity_data_json')
            if activity_data_raw:
                try:
                    ad = json.loads(activity_data_raw) if isinstance(activity_data_raw, str) else activity_data_raw
                    polyline = (ad.get('map') or {}).get('summary_polyline')
                    if polyline:
                        formatted_activity['map'] = {'summary_polyline': polyline}
                    calories = ad.get('calories')
                    if calories:
                        formatted_activity['calories'] = float(calories)
                except (json.JSONDecodeError, TypeError, AttributeError):
                    pass
            formatted_activities.append(formatted_activity)
        
        return {
            'activities': formatted_activities,
            'total_count': len(all_activities),
            'returned_count': len(formatted_activities),
            'offset': offset,
            'limit': limit,
            'has_more': offset + limit < len(all_activities),
            'status_filter': status_filter,
            'query_method': 'gsi_optimized' if status_filter else 'gsi_combined'
        }
        
    except (ClientError, ValueError, TypeError) as e:
        logger.error(f"Failed to get activity history: {str(e)}")
        return {
            'activities': [],
            'total_count': 0,
            'returned_count': 0,
            'offset': 0,
            'limit': 0,
            'has_more': False,
            'error': 'Failed to load activities',
            'query_method': 'error'
        }



def get_system_stats(user_id: str) -> Dict[str, Any]:
    """Get system-wide statistics (total activities, success rate, queue depth)"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)

        # Get total activities count via GSI query
        if user_id:
            total_response = table.query(
                IndexName="UserActivitiesIndex",
                KeyConditionExpression="user_id = :uid",
                ExpressionAttributeValues={":uid": user_id},
                Select='COUNT'
            )
        else:
            total_response = table.scan(Select='COUNT')
        total_activities = total_response.get('Count', 0)

        # Get activities from last 24 hours for success rate
        cutoff_time = (datetime.now(tz=timezone.utc) - timedelta(hours=24)).isoformat()
        recent_activities = _query_user_activities(user_id, since=datetime.now(tz=timezone.utc) - timedelta(hours=24))

        total_recent = len(recent_activities)
        successful_recent = sum(1 for a in recent_activities if a.get('processing_status') == 'completed')

        success_rate = (successful_recent / total_recent * 100) if total_recent > 0 else 0

        # Get processing activities count via ProcessingStatusIndex
        processing_response = table.query(
            IndexName='ProcessingStatusIndex',
            KeyConditionExpression='processing_status = :status',
            ExpressionAttributeValues={':status': 'processing'},
            Select='COUNT'
        )
        processing_count = processing_response.get('Count', 0)
        
        # Get SQS queue depth if available
        queue_depth = 0
        dlq_depth = 0
        
        try:
            sqs = boto3.client('sqs')
            
            # Get processing queue URL from environment
            processing_queue_url = os.environ.get('PROCESSING_QUEUE_URL')
            dlq_url = os.environ.get('DLQ_URL')
            
            if processing_queue_url:
                queue_attrs = sqs.get_queue_attributes(
                    QueueUrl=processing_queue_url,
                    AttributeNames=['ApproximateNumberOfMessages']
                )
                queue_depth = int(queue_attrs['Attributes'].get('ApproximateNumberOfMessages', 0))
            
            if dlq_url:
                dlq_attrs = sqs.get_queue_attributes(
                    QueueUrl=dlq_url,
                    AttributeNames=['ApproximateNumberOfMessages']
                )
                dlq_depth = int(dlq_attrs['Attributes'].get('ApproximateNumberOfMessages', 0))
                
        except ClientError as e:
            logger.warning(f"Failed to get SQS queue depth: {e}")
        
        return {
            'total_activities': total_activities,
            'success_rate': round(success_rate, 1),
            'recent_activities_24h': total_recent,
            'successful_24h': successful_recent,
            'processing_count': processing_count,
            'queue_depth': queue_depth,
            'dlq_depth': dlq_depth,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except (ClientError, ValueError) as e:
        logger.error(f"Failed to get system stats: {str(e)}")
        return {
            'total_activities': 0,
            'success_rate': 0,
            'recent_activities_24h': 0,
            'successful_24h': 0,
            'processing_count': 0,
            'queue_depth': 0,
            'dlq_depth': 0,
            'error': 'Failed to load system stats'
        }


def _iso_week_start(d: date) -> date:
    """Return the Monday (ISO week start) of the week containing date `d`."""
    return d - timedelta(days=d.weekday())


def _bucket_weekly_trends(
    activities: List[Dict[str, Any]],
    now: datetime,
    num_weeks: int = 12,
) -> List[Dict[str, Any]]:
    """Bucket activities into `num_weeks` chronological WeeklyTrend objects.

    Buckets by Monday calendar date (not ISO week-number arithmetic), which
    handles year boundaries and ISO week 53 correctly. The last bucket is the
    current (in-progress) week and is marked `complete=False`; all earlier weeks
    are `complete=True`. Pure function: reads only the activity dicts, no I/O.
    """
    current_monday = _iso_week_start(now.date())
    week_starts = [current_monday - timedelta(weeks=(num_weeks - 1 - i)) for i in range(num_weeks)]
    index_by_monday = {ws: i for i, ws in enumerate(week_starts)}

    trends = [
        {
            'week_start': ws.isoformat(),
            'week_end': (ws + timedelta(days=6)).isoformat(),
            'complete': ws != current_monday,
            'run_km': 0.0,
            'run_duration_sec': 0.0,
            'runs': 0,
            'strength_sessions': 0,
            'other_sessions': 0,
        }
        for ws in week_starts
    ]

    for a in activities:
        raw_date = a.get('start_date') or a.get('start_date_local') or a.get('created_at', '')
        if not raw_date:
            continue
        try:
            dt = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
        except (ValueError, TypeError, AttributeError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        idx = index_by_monday.get(_iso_week_start(dt.date()))
        if idx is None:
            continue

        bucket = trends[idx]
        activity_type = a.get('activity_type', '')
        distance_m = float(a.get('distance', 0) or 0)
        moving_time_s = float(a.get('moving_time', 0) or 0)
        if activity_type == 'Run':
            bucket['runs'] += 1
            if distance_m > 0:
                bucket['run_km'] += distance_m / 1000
            if moving_time_s > 0:
                bucket['run_duration_sec'] += moving_time_s
        elif activity_type == 'WeightTraining':
            bucket['strength_sessions'] += 1
        else:
            bucket['other_sessions'] += 1

    for bucket in trends:
        bucket['run_km'] = round(bucket['run_km'], 1)
        bucket['run_duration_sec'] = round(bucket['run_duration_sec'])
    return trends


def _completed_week_volume_change(weekly_trends: List[Dict[str, Any]]) -> Optional[float]:
    """Percent run-volume change between the two most recent completed weeks.

    Returns None when fewer than two completed weeks exist or the earlier
    comparison week has zero volume (insufficient data — R2.5). The current
    in-progress week (`complete=False`) is never used as a comparison term.
    """
    completed = [w for w in weekly_trends if w.get('complete')]
    if len(completed) < 2:
        return None
    prev_week, last_week = completed[-2], completed[-1]
    prev_km = prev_week.get('run_km') or 0
    last_km = last_week.get('run_km') or 0
    if prev_km <= 0:
        return None
    return round((last_km - prev_km) / prev_km * 100, 1)


def get_coach_summary(user_id: str) -> Dict[str, Any]:
    """Get coach summary: recent feedback, training trends, and athlete profile."""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        config_table = dynamodb.Table(USER_CONFIG_TABLE)

        # Get athlete profile from user preferences (loaded with the resolved
        # authenticated user id — never overwritten with DEFAULT_USER_ID; R1.5).
        athlete_profile = ''
        try:
            if user_id:
                config_response = config_table.get_item(Key={'user_id': user_id})
                prefs = config_response.get('Item', {}).get('user_preferences', {})
                athlete_profile = prefs.get('athlete_profile', '')
        except ClientError:
            pass

        # Get recent activities (12 ISO weeks) sorted by date. The window is
        # aligned to the oldest bucket's Monday (minus a 1-day buffer for
        # created_at vs start_date skew) so all 12 weekly buckets are populated.
        now = datetime.now(tz=timezone.utc)
        oldest_monday = _iso_week_start(now.date()) - timedelta(weeks=11)
        start_date = datetime(
            oldest_monday.year, oldest_monday.month, oldest_monday.day,
            tzinfo=timezone.utc,
        ) - timedelta(days=1)

        recent = _query_user_activities(user_id, since=start_date)
        recent.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        # Recent feedback: last 5 activities with coach_feedback
        recent_feedback = []
        for a in recent:
            fb = a.get('coach_feedback')
            if fb:
                if isinstance(fb, str):
                    try:
                        fb = json.loads(fb)
                    except (json.JSONDecodeError, TypeError):
                        fb = None
                if fb:
                    recent_feedback.append({
                        'activity_id': a.get('activity_id', ''),
                        'date': a.get('created_at', '')[:10],
                        'title': a.get('enhanced_title') or a.get('original_name', 'Activité'),
                        'coach_feedback': fb,
                    })
            if len(recent_feedback) >= 5:
                break

        # Compute weekly trends (last 4 weeks)
        weekly_volume = [0.0] * 4
        sessions_per_week = [0] * 4
        weekly_moving_time = [0.0] * 4
        weekly_distance_for_pace = [0.0] * 4
        run_sessions_per_week = [0] * 4
        other_sessions_per_week = [0] * 4
        other_sessions_breakdown = {}  # {sport_type: count} for non-Run activities

        for a in recent:
            activity_date = a.get('start_date') or a.get('start_date_local') or a.get('created_at', '')
            if not activity_date:
                continue
            try:
                dt = datetime.fromisoformat(activity_date.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                # Bucket on whole ISO weeks (Monday start). Derive the offset from
                # the Monday dates rather than from bare week numbers: the old
                # `(year_delta * 52) + week_delta` arithmetic is wrong across an ISO
                # year boundary, because ISO years hold 52 or 53 weeks.
                current_monday = _iso_week_start(now.date())
                activity_monday = _iso_week_start(dt.date())
                week_idx = (current_monday - activity_monday).days // 7
                if week_idx < 0 or week_idx >= 4:
                    continue
                distance_m = float(a.get('distance', 0) or 0)
                moving_time_s = float(a.get('moving_time', 0) or 0)
                activity_type = a.get('activity_type', '')

                if activity_type == 'Run' and distance_m > 0:
                    weekly_volume[week_idx] += distance_m / 1000
                    run_sessions_per_week[week_idx] += 1
                    if moving_time_s > 0:
                        weekly_moving_time[week_idx] += moving_time_s
                        weekly_distance_for_pace[week_idx] += distance_m
                else:
                    other_sessions_per_week[week_idx] += 1
                    other_sessions_breakdown[activity_type] = other_sessions_breakdown.get(activity_type, 0) + 1
                sessions_per_week[week_idx] += 1
            except (ValueError, TypeError):
                continue

        # Compute avg pace per week (min/km)
        avg_pace_per_week = []
        for i in range(4):
            if weekly_distance_for_pace[i] > 0:
                pace_s_per_km = weekly_moving_time[i] / (weekly_distance_for_pace[i] / 1000)
                mins = int(pace_s_per_km // 60)
                secs = int(pace_s_per_km % 60)
                avg_pace_per_week.append(f"{mins}:{secs:02d}")
            else:
                avg_pace_per_week.append("-")

        # Reverse so oldest week is first (chronological order)
        weekly_volume.reverse()
        sessions_per_week.reverse()
        run_sessions_per_week.reverse()
        other_sessions_per_week.reverse()
        avg_pace_per_week.reverse()

        # Compute ramp rate (week-over-week volume change percentage)
        ramp_rate = None
        if len(weekly_volume) >= 2:
            prev_week = weekly_volume[-2]  # second to last (previous week)
            curr_week = weekly_volume[-1]  # last (current week)
            if prev_week > 0:
                ramp_rate = round((curr_week - prev_week) / prev_week * 100, 1)

        # Compute detailed pace metrics from laps
        interval_paces = []  # [{date, pace_sec, hr}] - work intervals only
        ef_paces = []  # [{date, pace_sec, hr}] - easy runs only

        for a in recent:
            created = a.get('created_at', '')[:10]
            laps_raw = a.get('laps_json')
            if not laps_raw:
                continue
            try:
                laps = json.loads(laps_raw) if isinstance(laps_raw, str) else laps_raw
            except (json.JSONDecodeError, TypeError):
                continue

            if not laps or len(laps) < 2:
                continue

            # Classify laps: compute median pace, fast laps = work intervals
            speeds = [float(l.get('average_speed', 0)) for l in laps if float(l.get('average_speed', 0)) > 0]
            if not speeds:
                continue
            median_speed = sorted(speeds)[len(speeds) // 2]

            fast_laps = [l for l in laps if float(l.get('average_speed', 0)) > median_speed * 1.15 and float(l.get('distance', 0)) > 200]
            slow_laps = [l for l in laps if float(l.get('average_speed', 0)) <= median_speed * 1.15 and float(l.get('distance', 0)) > 200]

            # If has fast laps (>15% faster than median) = interval session.
            # Aggregate fast laps into ONE point per session (mean pace +
            # mean HR weighted by distance) so the chart shows one dot per
            # workout instead of N overlapping dots on the same date.
            if len(fast_laps) >= 2:
                total_dist = 0.0
                total_time = 0.0
                hr_weighted = 0.0
                hr_dist = 0.0
                for fl in fast_laps:
                    sp = float(fl.get('average_speed', 0))
                    dist = float(fl.get('distance', 0))
                    if sp > 0 and dist > 0:
                        total_dist += dist
                        total_time += dist / sp
                        hr = fl.get('average_heartrate')
                        if hr is not None:
                            try:
                                hr_weighted += float(hr) * dist
                                hr_dist += dist
                            except (TypeError, ValueError):
                                pass
                if total_dist > 0 and total_time > 0:
                    interval_paces.append({
                        'date': created,
                        'pace_sec': round(total_time / (total_dist / 1000)),
                        'hr': round(hr_weighted / hr_dist) if hr_dist > 0 else None,
                    })
            # If mostly slow laps and low pace variance = EF session
            elif len(slow_laps) >= len(laps) * 0.7:
                total_dist = sum(float(l.get('distance', 0)) for l in laps)
                total_time = sum(float(l.get('moving_time', 0)) for l in laps)
                avg_hr = float(a.get('average_heartrate', 0) or 0)
                if total_dist > 0 and total_time > 0:
                    ef_paces.append({
                        'date': created,
                        'pace_sec': round(total_time / (total_dist / 1000)),
                        'hr': round(avg_hr) if avg_hr else None,
                    })

        # Format for frontend
        def _fmt_pace(sec):
            return f"{int(sec // 60)}:{int(sec % 60):02d}"

        interval_trend = [{'date': p['date'], 'pace': _fmt_pace(p['pace_sec']), 'pace_sec': p['pace_sec'], 'hr': p.get('hr')} for p in sorted(interval_paces, key=lambda x: x['date'])]
        ef_trend = [{'date': p['date'], 'pace': _fmt_pace(p['pace_sec']), 'pace_sec': p['pace_sec'], 'hr': p.get('hr')} for p in sorted(ef_paces, key=lambda x: x['date'])]

        # Compliance scoring: compare activities done vs Campus Coach plan
        compliance = None
        try:
            sessions_table = dynamodb.Table(COACHING_SESSIONS_TABLE)
            # Kept as a Scan: "current week" is identified here by the
            # is_current_week flag, which is a plain attribute rather than the
            # session_date partition key, so it cannot be a KeyCondition.
            # Deriving the calendar week from today's date and Querying that
            # partition instead would flip compliance to None whenever the
            # current week has not been synced yet (e.g. early Monday), changing
            # behaviour. The scan stays; only single-partition reads (a labelled
            # week, athlete-context) were converted to Query.
            resp = sessions_table.scan(
                FilterExpression="is_current_week = :cw",
                ExpressionAttributeValues={":cw": True},
            )
            current_week_sessions = resp.get("Items", [])

            # Fallback: old Browser Tool format (no is_current_week flag)
            if not current_week_sessions:
                all_resp = sessions_table.scan()
                all_items = all_resp.get("Items", [])
                if all_items and "week_number" in all_items[0]:
                    latest_week = max(all_items, key=lambda x: x.get("updated_at", "")).get("week_number", "")
                    current_week_sessions = [s for s in all_items if s.get("week_number") == latest_week]

            total_planned = len(current_week_sessions)
            if total_planned > 0:
                completed_count = sum(
                    1 for session in current_week_sessions
                    if effective_status(session) == STATUS_DONE
                )
                compliance = {
                    'planned': total_planned,
                    'completed': completed_count,
                    'percentage': min(round(completed_count / total_planned * 100), 100)
                }
        except Exception as e:
            logger.warning(f'Failed to compute compliance: {e}')

        # Fetch strength history for muscu trends
        strength_history = []
        try:
            config_response = config_table.get_item(Key={'user_id': user_id})
            sh = config_response.get('Item', {}).get('user_preferences', {}).get('strength_history', {})
            strength_history = sh.get('entries', [])
        except Exception:
            pass

        # Real current-week tally (post-reversal: last index = week in progress).
        # Computed live on every /coach/summary call so the frontend reflects the
        # actual sessions done this week instead of the frozen (sometimes
        # hallucinated) recommendation_next text.
        current_week = {
            'runs': run_sessions_per_week[-1] if run_sessions_per_week else 0,
            'run_km': round(weekly_volume[-1], 1) if weekly_volume else 0.0,
            'other': other_sessions_per_week[-1] if other_sessions_per_week else 0,
            'total': sessions_per_week[-1] if sessions_per_week else 0,
        }

        # Additive V2 correctness fields (R2): explicit 12-week WeeklyTrend
        # objects with date-based buckets, plus a completed-week-only volume
        # delta. Recovery is extracted once and reused (R3.4).
        weekly_trends = _bucket_weekly_trends(recent, now, num_weeks=12)
        volume_change_completed_weeks_pct = _completed_week_volume_change(weekly_trends)
        recovery = _extract_recovery(recent, now)

        return {
            'schema_version': 1,
            'athlete_profile': athlete_profile,
            'recent_feedback': recent_feedback,
            'current_week': current_week,
            'weekly_trends': weekly_trends,
            'volume_change_completed_weeks_pct': volume_change_completed_weeks_pct,
            'trends': {
                'weekly_volume_km': [round(v, 1) for v in weekly_volume],
                'sessions_per_week': sessions_per_week,
                'run_sessions_per_week': run_sessions_per_week,
                'other_sessions_per_week': other_sessions_per_week,
                'other_sessions_breakdown': other_sessions_breakdown,
                'avg_pace_per_week': avg_pace_per_week,
                'interval_paces': interval_trend[-20:],
                'ef_paces': ef_trend[-20:],
                'ramp_rate': ramp_rate,
                'compliance': compliance,
                'recovery': recovery,
                'health_anomalies': _detect_health_anomalies(recovery),
                'strength_history': strength_history[-20:],
                'strength_progression': _build_strength_progression(strength_history),
            }
        }

    except (ClientError, ValueError, TypeError) as e:
        logger.error(f"Failed to get coach summary: {str(e)}")
        return {
            'schema_version': 1,
            'athlete_profile': '',
            'recent_feedback': [],
            'weekly_trends': [],
            'volume_change_completed_weeks_pct': None,
            'trends': {
                'weekly_volume_km': [0, 0, 0, 0],
                'sessions_per_week': [0, 0, 0, 0],
                'avg_pace_per_week': ['-', '-', '-', '-'],
            }
        }
