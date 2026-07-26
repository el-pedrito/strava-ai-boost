"""
Modules Processing

Handles module discovery, activation, and per-module processing
(Campus Coach session matching, Enduraw, etc.)
"""

import os
from typing import Dict, Any, Optional, List
from decimal import Decimal

import boto3
from shared.logger import get_logger

logger = get_logger("modules-processing")

REGION = os.environ.get('AWS_REGION', 'eu-west-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
COACHING_SESSIONS_TABLE = os.environ.get('COACHING_SESSIONS_TABLE', 'campus-coaching-sessions')


def get_active_modules(user_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get the list of active modules for the user from their configuration.

    Modules are config-driven: every ``module_id`` present in
    ``modules_config`` with ``enabled=True`` is considered active. Per-module
    processing is dispatched by name in :func:`apply_module_processing`.
    """
    try:
        modules_config = user_config.get('modules_config', {})
        active_modules = [
            {'name': module_id, 'config': config, 'enabled': True}
            for module_id, config in modules_config.items()
            if config.get('enabled', False)
        ]
        logger.info(f"Found {len(active_modules)} active modules")
        return active_modules

    except Exception as e:
        logger.error(f"Failed to get active modules: {str(e)}")
        return []


def apply_module_processing(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    modules: List[Dict[str, Any]],
    laps_data: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """Apply per-module processing, dispatched by module name.

    Campus Coach sessions are matched deterministically against the activity
    laps; Enduraw metrics are fetched upstream (activity_fetcher), so the
    Enduraw module is a pass-through here.
    """
    enhanced_modules = []

    for module in modules:
        try:
            enhanced_module = _apply_module(activity_data, module, laps_data)
            enhanced_modules.append(enhanced_module)
        except Exception as e:
            logger.error(f"Module {module.get('name', 'unknown')} processing failed: {str(e)}")
            module_with_error = module.copy()
            module_with_error['processing_error'] = str(e)
            enhanced_modules.append(module_with_error)

    return enhanced_modules


def _apply_module(
    activity_data: Dict[str, Any],
    module: Dict[str, Any],
    laps_data: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Dispatch processing for a single module by name."""
    try:
        module_name = module['name']

        if module_name == 'campus_coach' and module.get('enabled', False):
            return _apply_campus_coach_processing(activity_data, module, laps_data)
        # Enduraw and other modules are pass-through (data fetched upstream)
        return module

    except Exception as e:
        logger.error(f"Module {module.get('name', 'unknown')} processing failed: {str(e)}")
        module_with_error = module.copy()
        module_with_error['processing_error'] = str(e)
        return module_with_error


def _apply_campus_coach_processing(
    activity_data: Dict[str, Any],
    module: Dict[str, Any],
    laps_data: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Apply Campus Coach session matching.
    Pre-matches sessions deterministically using laps structure, then passes
    only the best match to the LLM for narrative enrichment.
    """
    try:
        logger.info("Retrieving Campus Coach sessions for deterministic matching...")

        activity_date = activity_data.get('start_date_local', activity_data.get('start_date', ''))
        duration_min = activity_data.get('moving_time', 0) / 60
        activity_type = activity_data.get('type', '').lower()

        sessions = _get_recent_campus_sessions(activity_date)

        enhanced_module = module.copy()

        if not sessions:
            enhanced_module['campus_coach_sessions'] = []
            enhanced_module['sessions_available'] = False
            enhanced_module['note'] = 'No recent Campus Coach sessions found'
            return enhanced_module

        # Pre-match: score each session against laps
        best_match = None
        best_score = 0.0
        laps = laps_data or activity_data.get('laps', [])

        for session in sessions:
            score = _score_session_match(session, laps, duration_min, activity_type)
            title = session.get('title', 'Unknown')
            logger.info(f"  Session '{title}' (id={session.get('session_id')}): score={score:.2f}")
            if score > best_score:
                best_score = score
                best_match = session

        if best_match and best_score >= 0.5:
            logger.info(f"✅ Pre-matched session: '{best_match.get('title')}' (score={best_score:.2f})")
            enhanced_module['campus_coach_sessions'] = [best_match]
            enhanced_module['matched_session'] = best_match
            enhanced_module['match_score'] = best_score
            enhanced_module['sessions_available'] = True
            enhanced_module['session_count'] = 1
        else:
            logger.info(f"No session matched above threshold (best={best_score:.2f})")
            enhanced_module['campus_coach_sessions'] = sessions
            enhanced_module['sessions_available'] = True
            enhanced_module['session_count'] = len(sessions)
            enhanced_module['note'] = 'No strong match found, passing all sessions to LLM'

        return enhanced_module

    except Exception as e:
        logger.error(f"Campus Coach processing error: {str(e)}")
        enhanced_module = module.copy()
        enhanced_module['campus_coach_sessions'] = []
        enhanced_module['sessions_available'] = False
        enhanced_module['error'] = str(e)
        return enhanced_module


def _score_session_match(
    session: Dict[str, Any],
    laps: List[Dict[str, Any]],
    activity_duration_min: float,
    activity_type: str
) -> float:
    """
    Score how well a campus session matches the activity laps.
    Returns 0.0-1.0. Higher = better match.
    """
    title = session.get('title', '').lower()
    intervals = session.get('intervals', [])

    # Rule out non-running sessions for running activities and vice versa
    is_renforcement = 'renforcement' in title or 'ppg' in title
    is_running_activity = activity_type in ('run', 'trail run', 'virtual run')

    if is_renforcement and is_running_activity:
        return 0.0
    if not is_renforcement and activity_type == 'weighttraining':
        return 0.0
    # WeightTraining matches Renforcement
    if is_renforcement and activity_type == 'weighttraining':
        return 0.8

    if not laps or not intervals:
        return 0.1

    # Extract session target duration from intervals
    session_duration_min = _extract_session_duration(intervals)
    if session_duration_min > 0:
        duration_ratio = min(activity_duration_min, session_duration_min) / max(activity_duration_min, session_duration_min)
    else:
        duration_ratio = 0.5

    # Count work intervals in session (excluding warm-up, cool-down, recovery)
    work_intervals = [i for i in intervals if i.get('type') == 'work']
    session_work_count = sum(i.get('repeat', 1) for i in work_intervals)

    # Detect interval structure from laps
    lap_structure = _analyze_lap_structure(laps)
    activity_fast_count = lap_structure['fast_lap_count']
    activity_has_warmup = lap_structure['has_warmup']
    activity_avg_fast_duration = lap_structure['avg_fast_duration_sec']

    # Score components
    score = 0.0

    # Duration match (0-0.3)
    score += duration_ratio * 0.3

    # Interval count match (0-0.4) — most important signal
    if session_work_count > 0 and activity_fast_count > 0:
        count_ratio = min(activity_fast_count, session_work_count) / max(activity_fast_count, session_work_count)
        score += count_ratio * 0.4
    elif session_work_count == 0 and activity_fast_count == 0:
        # Pure EF session matches pure EF activity
        score += 0.4
    elif session_work_count == 0 and activity_fast_count <= 1:
        # EF session, activity has maybe 1 fast lap (GPS noise)
        score += 0.3

    # Interval duration match (0-0.3)
    if work_intervals and activity_avg_fast_duration > 0:
        session_avg_duration = _avg_work_interval_duration(work_intervals)
        if session_avg_duration > 0:
            dur_ratio = min(activity_avg_fast_duration, session_avg_duration) / max(activity_avg_fast_duration, session_avg_duration)
            score += dur_ratio * 0.3

    return min(score, 1.0)


def _extract_session_duration(intervals: List[Dict[str, Any]]) -> float:
    """Extract total planned duration in minutes from session intervals."""
    total_sec = 0
    for interval in intervals:
        duration_str = interval.get('duration', '')
        repeat = interval.get('repeat', 1)
        sec = _parse_duration_to_seconds(duration_str)
        total_sec += sec * repeat
    return total_sec / 60


def _parse_duration_to_seconds(duration_str: str) -> float:
    """Parse duration string like '30 min', '2:30 min', '30 sec' to seconds."""
    if not duration_str:
        return 0
    duration_str = duration_str.strip().lower()
    if 'min' in duration_str:
        parts = duration_str.replace('min', '').strip()
        if ':' in parts:
            m, s = parts.split(':')
            return float(m) * 60 + float(s)
        return float(parts) * 60
    if 'sec' in duration_str:
        return float(duration_str.replace('sec', '').strip())
    return 0


def _avg_work_interval_duration(work_intervals: List[Dict[str, Any]]) -> float:
    """Average duration of work intervals in seconds."""
    durations = []
    for i in work_intervals:
        sec = _parse_duration_to_seconds(i.get('duration', ''))
        if sec > 0:
            durations.append(sec)
    return sum(durations) / len(durations) if durations else 0


def _analyze_lap_structure(laps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze laps to detect interval structure."""
    if not laps:
        return {'fast_lap_count': 0, 'has_warmup': False, 'avg_fast_duration_sec': 0}

    # Calculate pace for each lap
    paces = []
    for lap in laps:
        speed = lap.get('average_speed', 0)
        if isinstance(speed, str):
            speed = float(speed)
        if speed > 0:
            pace_sec_per_km = 1000 / speed
            paces.append({
                'pace': pace_sec_per_km,
                'duration': lap.get('moving_time', lap.get('elapsed_time', 0)),
                'distance': lap.get('distance', 0)
            })

    if not paces:
        return {'fast_lap_count': 0, 'has_warmup': False, 'avg_fast_duration_sec': 0}

    # Determine threshold: laps faster than median - 20sec/km are "fast"
    all_paces = [p['pace'] for p in paces]
    median_pace = sorted(all_paces)[len(all_paces) // 2]

    # Only consider variation if there's meaningful spread (>20 sec/km)
    pace_spread = max(all_paces) - min(all_paces)
    if pace_spread < 20:
        # Uniform pace = no intervals
        return {'fast_lap_count': 0, 'has_warmup': False, 'avg_fast_duration_sec': 0}

    fast_threshold = median_pace - 15  # 15 sec/km faster than median
    fast_laps = [p for p in paces if p['pace'] < fast_threshold]

    # Detect warmup: first lap is slow and long (>5min)
    has_warmup = False
    if paces and paces[0]['pace'] > median_pace and paces[0]['duration'] > 300:
        has_warmup = True

    avg_fast_duration = sum(l['duration'] for l in fast_laps) / len(fast_laps) if fast_laps else 0

    return {
        'fast_lap_count': len(fast_laps),
        'has_warmup': has_warmup,
        'avg_fast_duration_sec': avg_fast_duration
    }


def _get_recent_campus_sessions(activity_date: str = None) -> List[Dict[str, Any]]:
    """Get Campus Coach sessions for the current week, excluding already-done ones."""
    try:
        table = dynamodb.Table(COACHING_SESSIONS_TABLE)

        response = table.scan(
            FilterExpression='is_current_week = :cw',
            ExpressionAttributeValues={':cw': True}
        )

        sessions = response.get('Items', [])

        # Filter out sessions already marked as done
        sessions = [s for s in sessions if s.get('status') != 'Fait']

        def decimal_to_float(obj: Any) -> Any:
            if isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, dict):
                return {k: decimal_to_float(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [decimal_to_float(item) for item in obj]
            return obj

        sessions = decimal_to_float(sessions)

        logger.info(f"Retrieved {len(sessions)} Campus Coach sessions (excluded done)")
        return sessions

    except Exception as e:
        logger.error(f"Failed to retrieve Campus Coach sessions: {str(e)}")
        return []
