"""
Modules Processing

Handles module discovery, activation, and per-module processing
(Campus Coach session matching, Enduraw, etc.)
"""

import os
from typing import Dict, Any, Optional, List
from decimal import Decimal

import boto3
from shared.campus_status import STATUS_DONE, STATUS_SKIP, effective_status
from shared.iso_week import iso_week_label
from shared.logger import get_logger

logger = get_logger("modules-processing")

REGION = os.environ.get('AWS_REGION', 'eu-west-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
COACHING_SESSIONS_TABLE = os.environ.get('COACHING_SESSIONS_TABLE', 'campus-coaching-sessions')

# Upper bound when expanding a block/interval ``repeat`` into occurrences.
# ``repeat`` comes from an undocumented third-party API, so a malformed or
# absurd value must not be able to materialize an unbounded list inside a
# Lambda. Real sessions stay far below this (observed max: 9).
MAX_INTERVAL_REPEAT = 100

# Minimum score for an activity to be considered a match for a plan session.
# Below this the whole week is passed as context instead, and nothing is marked
# done. Shared by the content and coach branches through match_campus_session().
MATCH_THRESHOLD = 0.5


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

        enhanced_module = module.copy()
        result = match_campus_session(
            activity_data,
            laps=laps_data,
            current_activity_id=activity_data.get('id') or activity_data.get('activity_id'),
        )
        sessions = result['sessions']

        if not sessions:
            enhanced_module['campus_coach_sessions'] = []
            enhanced_module['sessions_available'] = False
            enhanced_module['note'] = 'No recent Campus Coach sessions found'
            return enhanced_module

        best_match = result['matched_session']
        best_score = result['match_score']

        if best_match:
            logger.info(f"Pre-matched session: '{best_match.get('title')}' (score={best_score:.2f})")
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


def match_campus_session(
    activity_data: Dict[str, Any],
    laps: Optional[List[Dict[str, Any]]] = None,
    current_activity_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministically match an activity against its week's Campus sessions.

    This is the single matcher used by BOTH pipeline branches. The content branch
    consumes it through :func:`_apply_campus_coach_processing`; the coach branch
    calls it directly so the coach is *told* which plan session the activity
    closes instead of inferring it from the narrative context.

    Sharing one matcher matters because the branches run in parallel: the content
    branch writes the completion marker, so a coach branch relying on the stored
    status would see the session as done or still to do depending on which branch
    won the race. Recomputing from laps is race-free and deterministic.

    Returns ``{'sessions', 'matched_session', 'match_score'}`` where
    ``matched_session`` is ``None`` below :data:`MATCH_THRESHOLD`.
    """
    activity_date = activity_data.get('start_date_local', activity_data.get('start_date', ''))
    duration_min = (activity_data.get('moving_time') or 0) / 60
    activity_type = (activity_data.get('type') or '').lower()

    sessions = _get_recent_campus_sessions(activity_date, current_activity_id)
    if not sessions:
        return {'sessions': [], 'matched_session': None, 'match_score': 0.0}

    effective_laps = laps if laps is not None else activity_data.get('laps', [])

    best_match: Optional[Dict[str, Any]] = None
    best_score = 0.0
    for session in sessions:
        score = _score_session_match(
            session, effective_laps, duration_min, activity_type, activity_data
        )
        logger.info(
            "  Session '%s' (id=%s, week=%s): score=%.2f",
            session.get('title', 'Unknown'),
            session.get('session_id'),
            session.get('week_date_iso'),
            score,
        )
        if score > best_score:
            best_score = score
            best_match = session

    return {
        'sessions': sessions,
        'matched_session': best_match if best_score >= MATCH_THRESHOLD else None,
        'match_score': best_score,
    }


# Wording the athlete uses to state that a gym activity WAS the planned
# session. Matched on his own text only (see _declares_campus_session).
_CAMPUS_MARKERS = ('campus', 'ppg')

# Negations placed near a marker: "pas le renfo campus", "sans ppg", "zappé le
# campus". Without this guard the marker alone would confirm a session the
# athlete explicitly says he did not do.
_NEGATIONS = ('pas ', 'sans ', 'zapp', 'skip', 'annul', 'reporte', 'raté', 'rate ')

# Markers of the athlete's OWN strength program (Upper A / Upper B / Rappel):
# gym movements that the running-specific Campus PPG does not prescribe. Their
# presence is evidence the session came from his own program.
# Kept as an explicit list rather than reusing shared/strength_exercises.py,
# whose canonicaliser expects a clean exercise name and not a free-form line
# like "low row mach 10x80 8x90".
_OWN_PROGRAM_MARKERS = (
    'traction', 'trac ', 'low row', 'tirage', 'dc barre', 'dc machine',
    'developpe', 'développé', 'press', 'ecarte', 'écarté', 'curl',
    'triceps', 'elev lat', 'élév lat', 'face pull', 'pull-over', 'pull over',
    'squat', 'souleve', 'soulevé',
)


def _activity_own_text(activity_data: Dict[str, Any]) -> str:
    """The athlete's own title + description, lowercased.

    Reads the ORIGINAL fields first. The generated description routinely contains
    "Séance Campus Coach ...", so reading an already-enhanced activity would make
    our own output confirm the match on reprocessing, a self-fulfilling loop.
    """
    parts = [
        activity_data.get('original_name'),
        activity_data.get('original_description'),
    ]
    if not any(parts):
        parts = [activity_data.get('name'), activity_data.get('description')]
    return ' '.join(str(p) for p in parts if p).lower()


def _declares_campus_session(activity_data: Dict[str, Any]) -> bool:
    """True when the athlete's own text states this was the planned session.

    A gym activity carries no laps to score against the planned PPG intervals, so
    the activity type alone cannot tell "my own Upper session" from "the PPG the
    plan prescribed". The athlete settles it by naming it, and that declaration is
    the strongest signal available, but it is one factor among several rather than
    a gate: a marker under negation does not count.
    """
    text = _activity_own_text(activity_data)
    for marker in _CAMPUS_MARKERS:
        idx = text.find(marker)
        while idx != -1:
            window = text[max(0, idx - 30):idx]
            if not any(neg in window for neg in _NEGATIONS):
                return True
            idx = text.find(marker, idx + 1)
    return False


def _mentions_own_program(activity_data: Dict[str, Any]) -> bool:
    """True when the text lists movements from the athlete's own gym program."""
    text = _activity_own_text(activity_data)
    return any(marker in text for marker in _OWN_PROGRAM_MARKERS)


def _score_gym_against_ppg(
    session: Dict[str, Any],
    activity_data: Dict[str, Any],
    activity_duration_min: float,
) -> float:
    """Weighted score for a gym activity against a planned PPG session.

    This used to be a flat 0.8, above MATCH_THRESHOLD, so *every* gym session
    silently closed the Campus PPG. It is now a combination of factors, because
    no single one is conclusive:

    * base 0.30, deliberately below the threshold: same activity type is not
      evidence, so the default is "context only, do not close the session";
    * +0.55 when the athlete names the session (the decisive factor, since only
      he knows);
    * -0.15 when the text lists his own program's movements, which points at his
      own session;
    * up to +0.15 for closeness to the planned duration, a weak corroboration.

    A declaration therefore carries the day even alongside a movement list (he may
    well write "renfo campus" and then log what he did), while movements without a
    declaration stay far below the threshold.
    """
    score = 0.30
    if _declares_campus_session(activity_data):
        score += 0.55
    if _mentions_own_program(activity_data):
        score -= 0.15
    planned = _session_target_duration_min(session)
    if planned > 0 and activity_duration_min > 0:
        ratio = min(planned, activity_duration_min) / max(planned, activity_duration_min)
        score += ratio * 0.15
    return max(0.0, min(score, 1.0))


def _score_session_match(
    session: Dict[str, Any],
    laps: List[Dict[str, Any]],
    activity_duration_min: float,
    activity_type: str,
    activity_data: Optional[Dict[str, Any]] = None,
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
    if is_renforcement and activity_type == 'weighttraining':
        return _score_gym_against_ppg(
            session, activity_data or {}, activity_duration_min
        )


    if not laps or not intervals:
        return 0.1

    # Normalize the interval schema once (tolerates the legacy flat form and
    # the new per-block form) into expanded occurrences.
    occurrences = _normalize_intervals(intervals)

    # Planned duration: provider value first, interval derivation as fallback.
    session_duration_min = _session_target_duration_min(session)
    if session_duration_min > 0:
        duration_ratio = min(activity_duration_min, session_duration_min) / max(activity_duration_min, session_duration_min)
    else:
        duration_ratio = 0.5

    # Count work intervals in session (excluding warm-up, cool-down, recovery).
    # Occurrences are already expanded by block/interval repeat, so the count is
    # the true number of hard efforts (no per-exercise repeat inflation).
    work_occurrences = [o for o in occurrences if o.get('type') == 'work']
    session_work_count = len(work_occurrences)

    # Detect interval structure from laps
    lap_structure = _analyze_lap_structure(laps)
    activity_fast_count = lap_structure['fast_lap_count']
    activity_has_warmup = lap_structure['has_warmup']
    activity_avg_fast_duration = lap_structure['avg_fast_duration_sec']

    # Score components
    score = 0.0

    # Duration match (0-0.3)
    score += duration_ratio * 0.3

    # Interval count match (0-0.4) - most important signal
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
    if work_occurrences and activity_avg_fast_duration > 0:
        session_avg_duration = _avg_work_interval_duration(work_occurrences)
        if session_avg_duration > 0:
            dur_ratio = min(activity_avg_fast_duration, session_avg_duration) / max(activity_avg_fast_duration, session_avg_duration)
            score += dur_ratio * 0.3

    return min(score, 1.0)


def _as_int(value: Any, default: int = 1) -> int:
    """Coerce a possibly Decimal/float/str repeat count to a positive int.

    Clamped to ``MAX_INTERVAL_REPEAT`` so a malformed provider value cannot
    drive an unbounded expansion in :func:`_normalize_intervals`.
    """
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n <= 0:
        return default
    if n > MAX_INTERVAL_REPEAT:
        logger.warning(
            "Interval repeat %s exceeds cap, clamping to %s",
            n, MAX_INTERVAL_REPEAT,
        )
        return MAX_INTERVAL_REPEAT
    return n


def _normalize_intervals(intervals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten campus-session intervals into per-occurrence interval units.

    Tolerates BOTH interval schemas, because the DynamoDB table keeps legacy
    rows in the old flat form until the next provider sync (05:00 UTC):

    - New per-block form: ``{'type': 'block', 'repeat': N, 'exercises': [...]}``
      -> each exercise is expanded ``N`` times, order preserved.
    - Legacy flat form: ``{'type': 'work'|'recovery'|..., 'duration', 'pace',
      optional 'repeat'}`` -> expanded ``repeat`` times (default 1).

    Returns a flat list of ``{'type', 'duration', 'pace'}`` occurrences with all
    block/interval repeats already expanded, so counting occurrences and summing
    durations is unambiguous and identical across both schemas.
    """
    occurrences: List[Dict[str, Any]] = []
    for entry in intervals or []:
        if not isinstance(entry, dict):
            continue
        if entry.get('type') == 'block':
            repeat = _as_int(entry.get('repeat', 1))
            exercises = entry.get('exercises', []) or []
            for _ in range(repeat):
                for exercise in exercises:
                    if isinstance(exercise, dict):
                        occurrences.append({
                            'type': exercise.get('type', 'work'),
                            'duration': exercise.get('duration', ''),
                            'pace': exercise.get('pace', ''),
                        })
        else:
            repeat = _as_int(entry.get('repeat', 1))
            for _ in range(repeat):
                occurrences.append({
                    'type': entry.get('type', 'work'),
                    'duration': entry.get('duration', ''),
                    'pace': entry.get('pace', ''),
                })
    return occurrences


def _extract_session_duration(intervals: List[Dict[str, Any]]) -> float:
    """Total planned duration in minutes, with block/interval repeats expanded."""
    total_sec = 0.0
    for occurrence in _normalize_intervals(intervals):
        total_sec += _parse_duration_to_seconds(occurrence.get('duration', ''))
    return total_sec / 60


def _session_target_duration_min(session: Dict[str, Any]) -> float:
    """Planned session duration in minutes, provider value first.

    ``expected_duration_min`` is supplied directly by the Campus API and is the
    authoritative figure. Deriving the duration from the interval list is only a
    fallback, and a lossy one: legacy rows omit the repeat factor on recoveries
    nested in a repeated block (Seuil 30 derives 30min against an actual 38min),
    and strength sessions carry repetitions rather than durations, so their
    intervals sum to almost nothing (9min against an actual 30min). Preferring
    the provider value keeps ``duration_ratio`` from penalising exactly the
    interval and strength sessions it is meant to score.
    """
    expected = session.get('expected_duration_min')
    if expected is not None:
        try:
            value = float(expected)
            if value > 0:
                return value
        except (TypeError, ValueError):
            logger.warning(
                "Unparseable expected_duration_min %r, deriving from intervals",
                expected,
            )
    return _extract_session_duration(session.get('intervals', []))


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


def _avg_work_interval_duration(work_occurrences: List[Dict[str, Any]]) -> float:
    """Average duration (seconds) over expanded work interval occurrences."""
    durations = []
    for occurrence in work_occurrences:
        sec = _parse_duration_to_seconds(occurrence.get('duration', ''))
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


def _get_recent_campus_sessions(
    activity_date: str = None,
    current_activity_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get candidate Campus Coach sessions for the activity's own ISO week.

    Scoping matters: the scorer discriminates weeks poorly, because two sessions
    that share a title across weeks differ only by their repeat count and target
    pace. A real 9x1min activity still scores 0.825 against the 7x1min plan of
    the previous week, well above the 0.5 match threshold. Selecting candidates
    by the activity's own week is therefore what keeps a wrong-week session from
    being matched confidently.

    Selecting on the ``is_current_week`` flag instead (the previous behaviour,
    which ignored ``activity_date`` entirely) mis-scoped every activity not
    processed inside its own week: a Sunday run processed on Monday, or any
    activity replayed from the DLQ, was scored against the plan of whatever week
    happened to be current at processing time.

    Falls back to the current-week flag when the activity's week has no synced
    plan (outside the provider's fetch window, or a week the subscription does
    not grant access to), so scoping never silently removes all candidates.

    The week-scoped read is a Query, not a Scan: ``session_date`` is the table's
    partition key and the sync writes it as ``week-YYYY-Www``, so a week maps
    exactly onto one partition. Only the current-week fallback still needs a Scan,
    because ``is_current_week`` is a plain attribute rather than a key.
    """
    try:
        table = dynamodb.Table(COACHING_SESSIONS_TABLE)

        activity_week = iso_week_label(activity_date)
        if activity_week:
            response = table.query(
                KeyConditionExpression='session_date = :sd',
                ExpressionAttributeValues={':sd': f'week-{activity_week}'},
            )
            sessions = response.get('Items', [])
            if not sessions:
                logger.warning(
                    "No Campus sessions synced for activity week %s, "
                    "falling back to current week",
                    activity_week,
                )
        else:
            logger.warning(
                "Could not derive ISO week from activity date %r, "
                "falling back to current week",
                activity_date,
            )
            sessions = []

        if not sessions:
            response = table.scan(
                FilterExpression='is_current_week = :cw',
                ExpressionAttributeValues={':cw': True},
            )
            sessions = response.get('Items', [])

        # Exclude sessions already completed or skipped, resolved through the
        # canonical status precedence (local -> legacy -> matched -> provider).
        # The raw legacy ``status`` field is stale and must never be read
        # directly to decide whether a session is done.
        #
        # One deliberate exception: the session already bound to the activity
        # being processed stays a candidate. The content branch marks a session
        # done as soon as it matches, so without this the coach branch would find
        # no candidate whenever it ran after the content branch, and the match
        # would depend on which parallel branch won the race.
        current_id = str(current_activity_id) if current_activity_id else None

        def _is_candidate(session: Dict[str, Any]) -> bool:
            if current_id and str(session.get('matched_activity_id') or '') == current_id:
                return True
            return effective_status(session) not in (STATUS_DONE, STATUS_SKIP)

        sessions = [s for s in sessions if _is_candidate(s)]

        def decimal_to_float(obj: Any) -> Any:
            if isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, dict):
                return {k: decimal_to_float(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [decimal_to_float(item) for item in obj]
            return obj

        sessions = decimal_to_float(sessions)

        logger.info(f"Retrieved {len(sessions)} Campus Coach sessions (excluded done/skip)")
        return sessions

    except Exception as e:
        logger.error(f"Failed to retrieve Campus Coach sessions: {str(e)}")
        return []
