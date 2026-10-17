"""Shared wellness/activity reader helpers.

These helpers are used by several lots (the Intervals.icu activity fetcher, the
WellnessSync Lambda, and the home-summary readers), so they live here rather
than being duplicated. ``_wellness_hrv`` / ``_wellness_hrv_kind`` were moved out
of ``lambda_functions/processing/activity_fetcher.py`` (which still imports them
from here); the behaviour is unchanged.
"""

import json
from typing import Any, Dict, Optional


def wellness_hrv(w: Dict[str, Any]) -> Optional[float]:
    """HRV from an Intervals.icu wellness row: rMSSD (`hrv`) first, else SDNN.

    Apple Watch only measures SDNN, and HealthFit sends it to the separate
    `hrvSDNN` field, so reading `hrv` alone always gave None for this athlete.
    """
    if w.get('hrv') is not None:
        return w.get('hrv')
    return w.get('hrvSDNN')


def wellness_hrv_kind(w: Dict[str, Any]) -> Optional[str]:
    if w.get('hrv') is not None:
        return 'rmssd'
    if w.get('hrvSDNN') is not None:
        return 'sdnn'
    return None


def activity_local_date(item: Dict[str, Any]) -> str:
    """Return the activity's own local calendar date (YYYY-MM-DD).

    Source of truth is ``start_date_local`` (inside ``activity_data_json`` when
    not promoted to a top-level attribute), then ``start_date``. ``created_at``
    is deliberately NOT used: it is the processing timestamp and is reset to now
    on every reprocess (PLAN-v4 decision), so a reprocessed old activity would
    otherwise masquerade as recent. Returns '' when no date can be resolved.
    """
    local = item.get('start_date_local')
    if not local:
        raw = item.get('activity_data_json')
        if raw:
            try:
                ad = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(ad, dict):
                    local = ad.get('start_date_local') or ad.get('start_date')
            except (json.JSONDecodeError, TypeError, AttributeError):
                local = None
    if not local:
        local = item.get('start_date')
    if not local:
        return ''
    return str(local)[:10]


# Backward-compatible private alias (older imports/tests).
_activity_local_date = activity_local_date


def in_activity_window(item: Dict[str, Any], since: str, until: str) -> bool:
    """True when the activity's local date falls in [since, until] (inclusive).

    Dates are ``YYYY-MM-DD`` strings compared lexically (ISO dates sort as
    dates). An empty ``since``/``until`` leaves that side unbounded. An item with
    no resolvable local date is excluded.
    """
    d = activity_local_date(item)
    if not d:
        return False
    if since and d < since[:10]:
        return False
    if until and d > until[:10]:
        return False
    return True


# --------------------------------------------------------------- Paris date
#
# Hand-coded EU DST rule (same oracle as api.plan_workouts.paris_date), kept
# here so webhook Lambdas and readers get Paris calendar dates without a
# cross-package import and without a tzdata dependency the Lambda image does not
# guarantee.
from datetime import datetime, timedelta, timezone  # noqa: E402


def _last_sunday_utc(year: int, month: int) -> datetime:
    """01:00 UTC on the last Sunday of ``month``: the EU DST switch instant."""
    first_next = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc)
    last_day = first_next - timedelta(days=1)
    sunday = last_day - timedelta(days=(last_day.weekday() + 1) % 7)
    return sunday.replace(hour=1)


def paris_date(now_utc: datetime):
    """Calendar date in Europe/Paris (CEST between the last Sundays of March and
    October at 01:00 UTC, CET otherwise)."""
    now_utc = now_utc.astimezone(timezone.utc)
    summer = _last_sunday_utc(now_utc.year, 3) <= now_utc < _last_sunday_utc(now_utc.year, 10)
    return (now_utc + timedelta(hours=2 if summer else 1)).date()
