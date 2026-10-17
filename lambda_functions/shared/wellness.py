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


def _activity_local_date(item: Dict[str, Any]) -> str:
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


def in_activity_window(item: Dict[str, Any], since: str, until: str) -> bool:
    """True when the activity's local date falls in [since, until] (inclusive).

    Dates are ``YYYY-MM-DD`` strings compared lexically (ISO dates sort as
    dates). An empty ``since``/``until`` leaves that side unbounded. An item with
    no resolvable local date is excluded.
    """
    d = _activity_local_date(item)
    if not d:
        return False
    if since and d < since[:10]:
        return False
    if until and d > until[:10]:
        return False
    return True
