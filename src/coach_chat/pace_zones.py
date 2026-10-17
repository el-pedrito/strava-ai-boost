"""Local mirror of ``lambda_functions/shared/pace_zones.effective_pace_zones``.

The coach_chat runtime is deployed with ``direct_code_deploy`` and bundles only
``src/coach_chat/``, so it cannot import ``lambda_functions/shared/``. This file
reimplements the reader rule with the exact same precedence; the parity test in
``tests/unit/test_pace_zones.py`` fails as soon as the two disagree. Keep in sync.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Tuple

SOURCE_CAMPUS = "campus"
SOURCE_CAMPUS_STALE = "campus_stale"
SOURCE_MANUAL_LEGACY = "manual_legacy"
SOURCE_NONE = "none"


def _iso_week_monday(label: Any) -> Optional[date]:
    """Monday of an ISO week label ``'YYYY-Www'``, None when unparseable."""
    if not isinstance(label, str):
        return None
    try:
        year_text, week_text = label.split("-W")
        return date.fromisocalendar(int(year_text), int(week_text), 1)
    except (ValueError, TypeError):
        return None


def effective_pace_zones(
    config_item: Any, now: Optional[datetime] = None
) -> Tuple[Dict[str, Any], str]:
    """``(zones, source)``: Campus zones first, then the legacy manual zones, else none."""
    item = config_item if isinstance(config_item, dict) else {}
    campus = item.get("campus_pace_zones")
    if isinstance(campus, dict) and campus:
        monday = _iso_week_monday(item.get("campus_pace_zones_week"))
        today = (now or datetime.now(timezone.utc)).date()
        current_monday = date.fromisocalendar(*today.isocalendar()[:2], 1)
        stale = monday is None or (current_monday - monday).days > 7
        return campus, SOURCE_CAMPUS_STALE if stale else SOURCE_CAMPUS
    prefs = item.get("user_preferences")
    manual = prefs.get("pace_zones") if isinstance(prefs, dict) else None
    if isinstance(manual, dict) and manual:
        return manual, SOURCE_MANUAL_LEGACY
    return {}, SOURCE_NONE


# Mirror of shared.pace_zones.strip_structured_pace_fields (parity-tested).
STRUCTURED_INTERVAL_KEYS = frozenset({"pace_kind", "pace_slug", "pace_zone", "pace_value_s"})
STRUCTURED_SESSION_KEYS = frozenset({"estimated_paces"})
_STRUCTURED_KEYS = STRUCTURED_INTERVAL_KEYS | STRUCTURED_SESSION_KEYS


def strip_structured_pace_fields(value: Any) -> Any:
    """Copy of Campus plan data without the structured pace fields (model view)."""
    if isinstance(value, dict):
        return {
            k: strip_structured_pace_fields(v)
            for k, v in value.items()
            if k not in _STRUCTURED_KEYS
        }
    if isinstance(value, list):
        return [strip_structured_pace_fields(v) for v in value]
    return value
