"""Lap facts, computed in code and handed to the coach.

Why this exists
---------------
The coach used to receive the raw laps and phrase the session from them. On 2026-08-15
it published "les 4 fractions actives (5min a 3:16/km)" while the real pace was 5:23 to
5:26. 3:16 is the ``max_speed`` of lap 1, 3.26 m/s, read as a decimal minute count:
0.26 x 60 = 16. No other field of that activity produces the value. The same feedback
called recoveries covering 179 to 229 m in two minutes "passive", and the next day the
coach announced five short efforts on a session holding six.

The prompt already forbade converting ``average_speed`` into a pace, and the activity
average was already formatted in code for exactly that reason. Neither covered
``max_speed``, and neither covered the laps.

Three rules
-----------
1. **Pace comes from ``average_speed`` alone**, formatted here. ``max_speed`` never
   reaches the model, in any form. It is a GPS peak: on 2026-08-16 the peak of a
   recovery lap (5.14 m/s) exceeded the average of every sprint (4.26 m/s), so it
   discriminates nothing, and lap 11 of 2026-08-15 carries a peak BELOW its own average,
   which is impossible.
2. **No bare speed value travels.** A float near 3 reads as a pace, which is the whole
   bug. Every exposed number carries its unit in its key.
3. **Work versus recovery is decided by relative contrast**, never by an absolute
   ``pace_zone`` threshold. The two audited sessions disagree on zones: the 16/08 efforts
   sit in zones 5 and 6, the 15/08 fractions in zone 2. A zone rule tuned on one would
   miss the other entirely.
"""

from __future__ import annotations

from statistics import median
from typing import Any, Dict, List, Optional

# A lap must clear both to count as an effort. Lap 11 of 2026-08-15 (12 m in 4 s at a
# nominal 3.10 m/s) is the reason: a GPS remnant is fast on paper and is not an effort.
MIN_EFFORT_SECONDS = 10.0
MIN_EFFORT_METRES = 40.0

# A lap is work when it is at least this much faster than the session median.
WORK_CONTRAST = 1.15

# A recovery covering more ground than this was jogged or walked, not stood still.
ACTIVE_RECOVERY_METRES = 50.0

# Tolerance when matching a repeated effort pattern: 34 s and 35 s are the same
# prescribed 35 s effort.
PATTERN_TOLERANCE = 0.25


def _to_float(raw: Any) -> Optional[float]:
    try:
        if raw is None:
            return None
        return float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _format_pace(speed_ms: Optional[float]) -> Optional[str]:
    """Seconds per kilometre from a speed in m/s, as ``mm:ss``."""
    if not speed_ms or speed_ms <= 0:
        return None
    total = 1000.0 / speed_ms
    return f"{int(total // 60)}:{int(total % 60):02d}"


def _detect_pattern(durations: List[int]) -> List[Dict[str, Any]]:
    """Smallest repeated period in a series of effort durations."""
    if not durations:
        return []
    count = len(durations)
    for period in range(1, count // 2 + 1):
        if count % period:
            continue
        reference = durations[:period]
        matches = True
        for position, value in enumerate(durations):
            expected = reference[position % period]
            if expected <= 0 or abs(value - expected) / expected > PATTERN_TOLERANCE:
                matches = False
                break
        if matches:
            return [{"repeat": count // period, "pattern_s": reference}]
    return [{"repeat": 1, "pattern_s": durations}]


def build_lap_facts(laps: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Per-lap pace and role, effort count, block structure and recovery mode."""
    empty: Dict[str, Any] = {
        "laps": [],
        "work_reps": {"count": 0, "durations_s": [], "paces": []},
        "blocks": [],
        "recovery": {"count": 0, "mode": None, "distances_m": [], "paces": []},
        "quality": {"aberrant_laps": [], "speed_fields_excluded": True},
    }
    if not isinstance(laps, list) or not laps:
        return empty

    parsed: List[Dict[str, Any]] = []
    aberrant: List[int] = []
    for position, lap in enumerate(laps, start=1):
        if not isinstance(lap, dict):
            continue
        index = int(_to_float(lap.get("lap_index")) or position)
        speed = _to_float(lap.get("average_speed"))
        peak = _to_float(lap.get("max_speed"))
        duration = _to_float(lap.get("moving_time"))
        distance = _to_float(lap.get("distance"))
        # A peak below the average cannot happen; the lap's data is unreliable.
        if speed is not None and peak is not None and peak < speed:
            aberrant.append(index)
        parsed.append(
            {
                "index": index,
                "_speed": speed,
                "duration_s": duration,
                "distance_m": distance,
                "pace_per_km": _format_pace(speed),
                "pace_zone": lap.get("pace_zone"),
                "avg_hr": lap.get("average_heartrate"),
                "role": "other",
                "_aberrant": index in aberrant,
            }
        )
    if not parsed:
        return empty

    speeds = [lap["_speed"] for lap in parsed if lap["_speed"]]
    if not speeds:
        return dict(empty, laps=[{k: v for k, v in lap.items() if not k.startswith("_")} for lap in parsed])
    reference = median(speeds)

    for lap in parsed:
        if lap["_aberrant"]:
            continue
        if (
            lap["_speed"]
            and lap["_speed"] >= reference * WORK_CONTRAST
            and (lap["duration_s"] or 0) >= MIN_EFFORT_SECONDS
            and (lap["distance_m"] or 0) >= MIN_EFFORT_METRES
        ):
            lap["role"] = "work"

    work_positions = [i for i, lap in enumerate(parsed) if lap["role"] == "work"]
    if work_positions:
        first, last = work_positions[0], work_positions[-1]
        # Order matters: a lap following an effort is a recovery even when it follows the
        # LAST one. Classifying by position first turned the fourth recovery of
        # 2026-08-15 into a cooldown and under-reported the recoveries by one.
        for i, lap in enumerate(parsed):
            if lap["role"] == "work":
                continue
            if i > 0 and parsed[i - 1]["role"] == "work":
                lap["role"] = "recovery"
            elif i < first:
                lap["role"] = "warmup"
            elif i > last:
                lap["role"] = "cooldown"

    work = [lap for lap in parsed if lap["role"] == "work"]
    recovery = [lap for lap in parsed if lap["role"] == "recovery"]
    durations = [int(lap["duration_s"]) for lap in work if lap["duration_s"]]

    recovery_distances = [int(lap["distance_m"]) for lap in recovery if lap["distance_m"]]
    mode: Optional[str] = None
    if recovery_distances:
        if all(distance > ACTIVE_RECOVERY_METRES for distance in recovery_distances):
            mode = "active"
        elif all(distance <= ACTIVE_RECOVERY_METRES for distance in recovery_distances):
            mode = "passive"
        else:
            mode = "mixed"

    return {
        "laps": [{k: v for k, v in lap.items() if not k.startswith("_")} for lap in parsed],
        "work_reps": {
            "count": len(work),
            "durations_s": durations,
            "paces": [lap["pace_per_km"] for lap in work],
        },
        "blocks": _detect_pattern(durations),
        "recovery": {
            "count": len(recovery),
            "mode": mode,
            "distances_m": recovery_distances,
            "paces": [lap["pace_per_km"] for lap in recovery],
        },
        "quality": {"aberrant_laps": aberrant, "speed_fields_excluded": True},
    }
