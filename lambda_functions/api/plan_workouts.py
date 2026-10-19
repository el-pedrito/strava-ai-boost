"""``GET /plan/workouts``: the remaining Campus sessions as Apple ``.workout`` files.

Plan: ``docs/design/apple-watch-workouts.md`` section C. The router branch lives in
``api/dashboard_api.py``; this module holds the logic so the branch stays small.

Owner gate: the Campus table has no user key (one athlete by construction), so the
endpoint is restricted to the Cognito ``custom:strava_id`` claim equal to
``CAMPUS_OWNER_STRAVA_ID``. Anything else, including the variable being unset, is a
403. ``_get_user_id`` is never used here: its DEFAULT_USER_ID fallback would open the
plan to any authenticated user without the claim.

No metric is recorded in this module (``tests/unit/test_metrics_flush.py``: a helper
calling ``add_metric`` would force every Lambda handler to flush). Counters are
returned to the caller, which emits them under its own ``@metrics.log_metrics``.

Campus text and file bytes are never logged.
"""

from __future__ import annotations

import base64
import json
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import groupby
from typing import Any, Dict, List, Optional, Tuple

from shared import campus_next, campus_workout
from shared.campus_status import STATUS_DONE, STATUS_SKIP, effective_status

MAX_ITEMS = 120
# Aggregate size of the serialized items. Far below the 6 MB Lambda response limit.
# Worst case per item with both Campus texts at their cap: 2 x 2000 chars x 4 UTF-8
# bytes (16 KB) + an 8 KB file in base64 (~11 KB) + small fields, about 28 KB. Nine
# synced weeks of ~5 sessions therefore stay near 1.3 MB even in that worst case, and
# real rows (a few hundred chars of text) are tens of KB. Kept at 2 MB: it still only
# bites on corrupt data, and leaves 3x headroom for the Lambda envelope's escaping.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
# Cap, in characters, of each Campus text copied to an item (``description``,
# ``coach_advice``). Real texts are a few hundred characters.
MAX_TEXT_CHARS = 2000

METRIC_MAP_FAILED = "WorkoutMapFailed"

ATHLETE_CONTEXT_KEY = "athlete-context"
_CLOSED_STATUSES = frozenset({STATUS_DONE, STATUS_SKIP})


def is_owner(claim: str, owner: Optional[str]) -> bool:
    """True only for a non-empty claim exactly equal to a non-empty configured owner.

    The claim is compared as issued (no stripping); only the env value is trimmed.
    """
    claim = claim if isinstance(claim, str) else ""
    owner = owner.strip() if isinstance(owner, str) else ""
    return bool(claim) and bool(owner) and claim == owner


# --------------------------------------------------------------- week boundary
#
# The EU DST rule below is hand-coded. Its oracle is
# ``tests/unit/test_plan_workouts_api.py::TestWeekBoundary::test_paris_date_matches_iana_over_two_years``
# (30-minute sweep against IANA ``Europe/Paris``): run it after any change here, and it is
# the test that will flag a future change of the EU rule.

def _last_sunday_utc(year: int, month: int) -> datetime:
    """01:00 UTC on the last Sunday of ``month``: the EU DST switch instant."""
    first_next = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc)
    last_day = first_next - timedelta(days=1)
    sunday = last_day - timedelta(days=(last_day.weekday() + 1) % 7)
    return sunday.replace(hour=1)


def paris_date(now_utc: datetime):
    """Calendar date in Europe/Paris (EU rule: CEST between the last Sundays of March
    and October at 01:00 UTC, CET otherwise).

    Coded instead of ``zoneinfo``: the Lambda image does not guarantee the IANA
    database and the project adds no ``tzdata`` dependency for one offset.
    """
    now_utc = now_utc.astimezone(timezone.utc)
    summer = _last_sunday_utc(now_utc.year, 3) <= now_utc < _last_sunday_utc(now_utc.year, 10)
    return (now_utc + timedelta(hours=2 if summer else 1)).date()


def current_week_start_ms(now_utc: datetime) -> int:
    """Monday 00:00 UTC (ms) of the ISO week holding today's Paris date.

    Same encoding as ``campus_coach_sync``'s ``week_date`` (Campus ``weekDate``).
    """
    today = paris_date(now_utc)
    monday = today - timedelta(days=today.weekday())
    start = datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000)


# --------------------------------------------------------------- row helpers

def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _int_or_none(value: Any) -> Optional[int]:
    number = _number(value)
    if number is None or number != int(number):
        return None
    return int(number)


def _duration_min(value: Any) -> Optional[float]:
    number = _number(value)
    if number is None:
        return None
    return int(number) if number == int(number) else number


def _str_or_none(value: Any) -> Optional[str]:
    """A Campus string made safe for JSON and UTF-8, or None for a non-string.

    DynamoDB can hold text that is not valid Unicode for the encoder (a lone surrogate
    from a broken upstream payload). ``json.dumps(ensure_ascii=False).encode("utf-8")``
    raises on it, so every copied string is re-encoded with replacement (``?``).
    """
    if not isinstance(value, str):
        return None
    return value.encode("utf-8", "replace").decode("utf-8")


def text_or_none(value: Any) -> Optional[str]:
    """A Campus free text (instructions, coach word) for display, or None.

    Sanitized like every copied string, trimmed, and capped at ``MAX_TEXT_CHARS``
    characters. Non-string, empty or blank values are None. The text is passed
    through as written (markdown bold, URLs): rendering is the client's job.
    """
    text = _str_or_none(value)
    if text is None:
        return None
    text = text.strip()[:MAX_TEXT_CHARS].rstrip()
    return text or None


def _week_key(row: Dict[str, Any]) -> float:
    # Present and finite on every row that passed ``_is_open``.
    week = _number(row.get("week_date"))
    return week if week is not None else math.inf


def _sort_key(row: Dict[str, Any]) -> Tuple[float, int, str]:
    """Numeric ``week_date`` (always present after ``_is_open``), then index, then id."""
    index = _int_or_none(row.get("training_index"))
    return (
        _week_key(row),
        index if index is not None else 10**9,
        _str_or_none(row.get("session_id")) or "",
    )


def scan_open_rows(table: Any) -> List[Dict[str, Any]]:
    """Every current or future row, all pages (``LastEvaluatedKey``)."""
    kwargs: Dict[str, Any] = {
        "FilterExpression": "is_current_week = :t OR is_future = :t",
        "ExpressionAttributeValues": {":t": True},
    }
    rows: List[Dict[str, Any]] = []
    while True:
        response = table.scan(**kwargs)
        rows.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            return rows
        kwargs["ExclusiveStartKey"] = last_key


def _is_open(row: Dict[str, Any], week_start_ms: int) -> bool:
    if row.get("session_date") == ATHLETE_CONTEXT_KEY:
        return False
    intervals = row.get("intervals")
    if not isinstance(intervals, list) or not intervals:
        return False
    week_date = _number(row.get("week_date"))
    if week_date is None or week_date < week_start_ms:
        return False
    return effective_status(row) not in _CLOSED_STATUSES


def _count_failure(counters: Dict[str, int]) -> None:
    counters[METRIC_MAP_FAILED] = counters.get(METRIC_MAP_FAILED, 0) + 1


def _row_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    """Display fields copied from the row, every string sanitized."""
    return {
        "session_id": _str_or_none(row.get("session_id")),
        "week_iso": _str_or_none(row.get("week_date_iso")),
        "training_index": _int_or_none(row.get("training_index")),
        "title": _str_or_none(row.get("title")),
        "training_type": _str_or_none(row.get("training_type")),
        "sport": _str_or_none(row.get("sport")),
        "duration_min": _duration_min(row.get("expected_duration_min")),
        "description": text_or_none(row.get("description")),
        "coach_advice": text_or_none(row.get("coach_advice")),
    }


def _internal_item(row: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback for a row whose item could not be built or serialized."""
    return {
        **_row_fields(row),
        "summary": None,
        "filename": "seance.workout",
        "encodable": False,
        "reason_code": campus_workout.REASON_INTERNAL,
    }


def _serialized_size(item: Dict[str, Any]) -> int:
    return len(json.dumps(item, ensure_ascii=False).encode("utf-8"))


def _item(row: Dict[str, Any], counters: Dict[str, int], range_alerts: bool = False) -> Dict[str, Any]:
    try:
        result = campus_workout.map_session(row, range_alerts=range_alerts)
    except Exception:  # noqa: BLE001 - one bad row must not fail the whole list
        _count_failure(counters)
        result = campus_workout.MapResult(False, campus_workout.REASON_INTERNAL)
    for name, value in (result.metrics or {}).items():
        counters[name] = counters.get(name, 0) + value

    try:
        filename = campus_workout.workout_filename(row)
    except Exception:  # noqa: BLE001 - same isolation as the mapping
        filename = "seance.workout"
    encodable = bool(result.encodable and result.bytes)
    item = {
        **_row_fields(row),
        "summary": _str_or_none(result.summary) if encodable else None,
        "filename": _str_or_none(filename) or "seance.workout",
        "encodable": encodable,
        "reason_code": None if encodable else (result.reason_code or campus_workout.REASON_INTERNAL),
    }
    if encodable:
        item["workout_b64"] = base64.b64encode(result.bytes).decode("ascii")
    return item


def _safe_item(
    row: Dict[str, Any], counters: Dict[str, int], range_alerts: bool = False,
) -> Tuple[Dict[str, Any], int]:
    """Item and its serialized size. The isolation covers the item build, the base64
    and the serialization: a malformed row becomes an ``internal`` item, never a 500.
    """
    try:
        item = _item(row, counters, range_alerts)
        return item, _serialized_size(item)
    except Exception:  # noqa: BLE001 - one bad row must not fail the whole list
        _count_failure(counters)
        item = _internal_item(row)
        return item, _serialized_size(item)


def workout_item(
    row: Dict[str, Any], counters: Dict[str, int], range_alerts: bool = False,
) -> Dict[str, Any]:
    """One session as a ``/plan/workouts`` item, with the same isolation: never raises.

    Public so ``/home/summary`` builds its next-session file with the exact same
    mapping, filename and failure handling (``WorkoutMapFailed`` in ``counters``).
    """
    item, _ = _safe_item(row, counters, range_alerts)
    return item


def build_plan_workouts(
    table: Any, now_utc: datetime, range_alerts: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """Payload ``{workouts, count, truncated, next_session_id}`` and the metric counters.

    ``next_session_id`` is the session ``/home/summary`` presents as next
    (``shared.campus_next.next_open_session``), or null. It can name a session that
    is not in ``workouts`` (no intervals, so no file): the client then highlights
    nothing rather than a different session.

    ``range_alerts``: the ``RANGE_ALERTS_ENABLED`` switch, read by the caller.

    Rows are sorted nearest week first and the ceilings are applied a whole week at a
    time: a week is either fully listed or not at all, so the kept items are exactly the
    nearest weeks (the UI says so). A single week above a ceiling (corrupt data only)
    therefore yields an empty, truncated list.
    """
    week_start_ms = current_week_start_ms(now_utc)
    raw_rows = scan_open_rows(table)
    # Same rule and same raw rows as /home/summary, BEFORE the display filter below
    # (``_is_open`` drops rows without intervals, which Home keeps).
    next_row = campus_next.next_open_session(raw_rows, paris_date(now_utc))
    next_session_id = _str_or_none(next_row.get("session_id")) if next_row else None
    rows = sorted((r for r in raw_rows if _is_open(r, week_start_ms)), key=_sort_key)

    counters: Dict[str, int] = {}
    workouts: List[Dict[str, Any]] = []
    size = 0
    truncated = False
    for _, week_rows in groupby(rows, key=_week_key):
        week = [_safe_item(row, counters, range_alerts) for row in week_rows]
        week_size = sum(item_size for _, item_size in week)
        if len(workouts) + len(week) > MAX_ITEMS or size + week_size > MAX_RESPONSE_BYTES:
            truncated = True
            break
        workouts.extend(item for item, _ in week)
        size += week_size
    payload = {
        "workouts": workouts,
        "count": len(workouts),
        "truncated": truncated,
        "next_session_id": next_session_id,
    }
    return payload, counters
