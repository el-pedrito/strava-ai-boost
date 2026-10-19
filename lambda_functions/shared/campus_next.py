"""The single "next Campus session" rule, shared by ``/home/summary`` and ``/plan/workouts``.

Home and Plan used to pick the next session each in their own way: Plan dropped the
rows without intervals and chose the week from a client-side date, Home kept every
row of the server-side Paris week. A first session without intervals was then "today"
on Home and absent from Plan, which highlighted the following one. Both endpoints now
call ``next_open_session`` on the raw rows they read, before any display filtering.

Rule:
- the week is the ISO week of today's Europe/Paris date, i.e. the rows whose
  partition key is ``week-YYYY-Www``. When no row carries that key (the sync has not
  written the week yet), the rows flagged ``is_current_week`` are used instead;
- inside that week, rows are in Campus order (``training_index``);
- the next session is the first one whose ``effective_status`` is neither done nor
  skipped. The shape of its intervals does not matter.
"""

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional

from shared.campus_status import STATUS_DONE, STATUS_SKIP, effective_status
from shared.iso_week import iso_week_label

_CLOSED = frozenset({STATUS_DONE, STATUS_SKIP})


def _training_index(row: Dict[str, Any]) -> int:
    try:
        return int(row.get('training_index', 0) or 0)
    except (TypeError, ValueError):
        return 0


def week_partition(today_paris: date) -> str:
    """Partition key of the Campus week holding ``today_paris``: ``week-YYYY-Www``."""
    label = iso_week_label(datetime.combine(today_paris, datetime.min.time()).isoformat())
    return f"week-{label}"


def current_week_rows(rows: Iterable[Dict[str, Any]], today_paris: date) -> List[Dict[str, Any]]:
    """The rows of the current Paris ISO week, in Campus order (see module rule)."""
    week_rows = [r for r in rows if str(r.get('session_date', '')).startswith('week-')]
    partition = week_partition(today_paris)
    current = [r for r in week_rows if r.get('session_date') == partition]
    if not current:
        current = [r for r in week_rows if r.get('is_current_week') is True]
    return sorted(current, key=_training_index)


def is_closed(row: Dict[str, Any]) -> bool:
    """True when the session is done or skipped (``effective_status``)."""
    return effective_status(row) in _CLOSED


def next_open_session(rows: Iterable[Dict[str, Any]], today_paris: date) -> Optional[Dict[str, Any]]:
    """The first open session of the current Paris ISO week, or None."""
    for row in current_week_rows(rows, today_paris):
        if not is_closed(row):
            return row
    return None
