"""Canonical ISO week labelling.

Shared-contract rule: a week identity is always the ISO string form
``'YYYY-Www'`` (e.g. ``'2026-W32'``), never a bare integer. A bare week number
cannot be compared against the ``week_date_iso`` values written by the Campus
Coach sync, and mixing the two is what let the coach attribute a session to the
wrong week.
"""

from datetime import datetime
from typing import Optional


def iso_week_label(start_date: Optional[str]) -> str:
    """Return an ISO week label ``'YYYY-Www'`` from an ISO datetime string.

    Returns an empty string when the input is missing or unparseable, so callers
    can treat "unknown week" as a distinct, testable case rather than silently
    falling back to the current week.
    """
    if not start_date:
        return ''
    try:
        parsed = datetime.fromisoformat(str(start_date).replace('Z', '+00:00'))
    except (ValueError, AttributeError, TypeError):
        return ''
    iso = parsed.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"
