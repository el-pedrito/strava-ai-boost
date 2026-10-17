"""Pace zones: one source for every reader, one formatter for every pace text.

Campus Coach is the only source of pace zones (athlete decision 2026-10-17, see
``docs/design/campus-paces.md``). The sync writes them as TOP-LEVEL attributes of the
owner's user-config item (``campus_pace_zones``, ``campus_pace_zones_week``,
``campus_pace_zones_synced_at``). Readers never look at those attributes directly:
they call :func:`effective_pace_zones`, which falls back to the legacy manual
``user_preferences.pace_zones`` while the sync has written nothing.

Pure module: no boto3, no environment reads, no metrics.

The coach_chat runtime cannot import this file (its bundle is limited to
``src/coach_chat/``). It carries a local mirror, ``src/coach_chat/pace_zones.py``,
kept identical by a parity test in ``tests/unit/test_pace_zones.py``.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

SOURCE_CAMPUS = "campus"
SOURCE_CAMPUS_STALE = "campus_stale"
SOURCE_MANUAL_LEGACY = "manual_legacy"
SOURCE_NONE = "none"

# A Campus ``range`` pace runs from its value to this many seconds slower: the app
# shows "5:46 - 6:16 /km" for EF value 346 and "5:49 - 6:19" for 349 (6 screens,
# 2026-10-17). It is not value +/- dvalue. Slugs Campus shows as a range:
CAMPUS_RANGE_WIDTH_SEC = 30
CAMPUS_RANGE_SLUGS = frozenset({"ef"})

# Our zone key <- Campus estimatedPaces slug. The zone keys are the ones the
# classifier in processing/workout_analysis.py already knows.
CAMPUS_ZONE_SLUGS: Dict[str, str] = {
    "recovery": "slow",
    "ef": "ef",
    "aerobic": "aerobie",
    "tempo": "tempo",
    "sweet_spot": "sweet-spot",
    "seuil_60": "seuil60",
    "seuil_30": "seuil30",
    "allure_marathon": "marathon",
    "allure_semi": "half-marathon",
    "interval": "vma",
}


def _finite(value: Any) -> Optional[float]:
    """A finite float from int / float / Decimal / numeric string, else None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def fmt_pace(sec_per_km: Any) -> str:
    """``m:ss`` from seconds per km, rounded half-up to the nearest second.

    Half-up on purpose (``floor(x + 0.5)``): Python's ``round`` is half-even and
    would print 335.5 s as 5:35 instead of 5:36. Returns ``""`` for a value that is
    not a positive finite number.
    """
    number = _finite(sec_per_km)
    if number is None or number <= 0:
        return ""
    total = int(math.floor(number + 0.5))
    return f"{total // 60}:{total % 60:02d}"


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
    """``(zones, source)`` for one user-config item.

    The source is chosen by whether ``campus_pace_zones`` exists; the week only
    sets the label:

    - a non-empty ``campus_pace_zones`` map -> ``campus``, or ``campus_stale`` when
      its week is more than one ISO week behind ``now`` (module disabled or
      subscription over: the zones stay frozen). An unparseable week is stale too.
    - else a non-empty ``user_preferences.pace_zones`` map -> ``manual_legacy``.
    - else ``({}, "none")``.

    A missing, empty or non-dict ``campus_pace_zones`` counts as absent (a
    hand-edited rollback could leave an empty map behind).
    """
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


def build_campus_zones(estimated: Any) -> Optional[Dict[str, Dict[str, Any]]]:
    """Zone map from the session-level ``estimated_paces`` ({slug: {value, dvalue}}).

    ``min`` is the FAST bound, ``max`` the SLOW one, as ``m:ss`` text, which is the
    format of the legacy manual zones. Every mapped slug must be present and valid
    (finite value in 120..900 s/km, dvalue absent or ``>= 0``), otherwise None (the
    caller writes nothing): a partial map would silently mix Campus zones with
    missing ones.

    For a slug Campus shows as a range (:data:`CAMPUS_RANGE_SLUGS`, EF) the zone is
    exactly what the app displays: the whole-second value, then
    :data:`CAMPUS_RANGE_WIDTH_SEC` slower (348.8 -> 5:49-6:19). Every other slug
    (tempo, seuil, semi...) is a single value, ``min == max``, as the app shows it:
    no width is invented and dvalue is kept only as ``dvalue_s``.
    """
    if not isinstance(estimated, dict):
        return None
    zones: Dict[str, Dict[str, Any]] = {}
    for zone, slug in CAMPUS_ZONE_SLUGS.items():
        entry = estimated.get(slug)
        if not isinstance(entry, dict):
            return None
        value = _finite(entry.get("value"))
        dvalue = _finite(entry.get("dvalue"))
        # 2:00..15:00 /km, the same plausibility guard as the Watch mapper.
        if value is None or not 120 <= value <= 900:
            return None
        # Exactly what the Campus app displays: the whole-second value. A range slug
        # (EF) runs to +30 s; every other slug is a single value (min == max), as the
        # app shows it ("Allure Tempo 5:15"). No width is invented (athlete's rule,
        # 2026-10-17); the lap classifier matches single values by nearest pace.
        fast = float(math.floor(value + 0.5))
        slow = fast + CAMPUS_RANGE_WIDTH_SEC if slug in CAMPUS_RANGE_SLUGS else fast
        if dvalue is None:
            dvalue = 0.0
        if dvalue < 0:
            # A negative spread is corrupt provider data: write no zone at all.
            return None
        zones[zone] = {
            "min": fmt_pace(fast),
            "max": fmt_pace(slow),
            "slug": slug,
            "value_s": Decimal(str(round(value, 1))),
            "dvalue_s": Decimal(str(round(dvalue, 1))),
        }
    return zones


# Fields added by the paces sync (docs/design/campus-paces.md, A). They exist for
# the Watch mapper and the zone writer only. Per step: kind / slug / zoneKind /
# integer pace; per session: the week's estimatedPaces map.
STRUCTURED_INTERVAL_KEYS = frozenset({"pace_kind", "pace_slug", "pace_zone", "pace_value_s"})
STRUCTURED_SESSION_KEYS = frozenset({"estimated_paces"})
_STRUCTURED_KEYS = STRUCTURED_INTERVAL_KEYS | STRUCTURED_SESSION_KEYS


def strip_structured_pace_fields(value: Any) -> Any:
    """Copy of a Campus session / interval list without the structured pace fields.

    Model-visible projection to the pre-paces schema: every place where plan
    sessions or intervals reach a model (coach payload, content payload, coach_chat
    tool) goes through this, so a row written by the new sync and its legacy twin
    give the model the exact same input. The fields stay in DynamoDB for the Watch.

    Recursive (intervals nest under ``block.exercises``). Apply it to Campus plan
    data ONLY: laps carry a legitimate ``pace_zone`` that must not be dropped.
    Never mutates its input.
    """
    if isinstance(value, dict):
        return {
            k: strip_structured_pace_fields(v)
            for k, v in value.items()
            if k not in _STRUCTURED_KEYS
        }
    if isinstance(value, list):
        return [strip_structured_pace_fields(v) for v in value]
    return value
