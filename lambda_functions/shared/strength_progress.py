"""Per-exercise progression, decided in code.

Why this exists
---------------
On 2026-08-14 the coach read the raw ``strength_history`` and concluded that the bench
press had regressed, that the athlete had "flanche", and it invented a previous session
of "4x8 @90kg" to support the claim. The stored history said the opposite:

    11/08  80x10, 90x8, 90x8, 90x8   ->  3 work sets at 90, 24 reps at 90
    14/08  80x10, 90x8, 90x8, 90x9   ->  3 work sets at 90, 25 reps at 90

Same load, same sets, one more repetition. The data was correct, complete and inside the
eight-entry window the coach receives; only the reading was wrong. So the direction is
no longer inferred: it is computed here and handed over as a fact, and the prompt stops
asking the model to work it out.

Method, and its reservation
---------------------------
Comparison is anchored on the TOP LOAD, because that is what the athlete tracks (his
stated priority is the bench press and pull-ups). At equal top load the tie is broken on
the total repetitions performed at that load, with the set count reported alongside so
the figure stays auditable.

Reservation: this says nothing about a session where the athlete deliberately trades load
for volume, which is a legitimate progression that would show up here as a regression.
That is why the classification is a fact to state, never an instruction to judge, and why
"incomparable" exists rather than a forced verdict.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

PROGRESSION = "progression"
REGRESSION = "regression"
MAINTIEN = "maintien"
INCOMPARABLE = "incomparable"


def _to_float(raw: Any) -> Optional[float]:
    try:
        if raw is None:
            return None
        return float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _sets_detail(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Authoritative per-set detail, rebuilt from the flat shape when absent.

    ``sets_detail`` is the authoritative field, but rows written before it existed only
    carry ``{sets, reps, weight_kg}``. Rebuilding keeps those comparable instead of
    silently reporting them as having no history.
    """
    if not isinstance(entry, dict):
        return []
    detail = entry.get("sets_detail")
    if isinstance(detail, list) and detail:
        return [item for item in detail if isinstance(item, dict)]
    sets = _to_float(entry.get("sets"))
    reps = entry.get("reps")
    weight = entry.get("weight_kg")
    if not sets:
        return []
    return [{"reps": reps, "weight_kg": weight} for _ in range(int(sets))]


def _profile(sets_detail: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Top load of the exercise, and the work done at that load."""
    if not sets_detail:
        return None
    loads = [
        _to_float(item.get("weight_kg"))
        for item in sets_detail
        if isinstance(item, dict) and _to_float(item.get("weight_kg")) is not None
    ]
    if not loads:
        # Bodyweight movements carry no load to compare on.
        return None
    top = max(loads)
    at_top = [
        item
        for item in sets_detail
        if isinstance(item, dict) and _to_float(item.get("weight_kg")) == top
    ]
    reps_at_top = sum(int(_to_float(item.get("reps")) or 0) for item in at_top)
    return {
        "top_load_kg": top,
        "sets_at_top_load": len(at_top),
        "reps_at_top_load": reps_at_top,
        "total_sets": len(sets_detail),
    }


def compare_exercise(
    exercise: str,
    current_sets: Optional[List[Dict[str, Any]]],
    previous_sets: Optional[List[Dict[str, Any]]],
    previous_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare one exercise against its previous occurrence."""
    current = _profile(current_sets)
    previous = _profile(previous_sets)
    result: Dict[str, Any] = {
        "exercise": exercise,
        "current": current,
        "previous": None,
        "classification": INCOMPARABLE,
        "delta_reps_at_top_load": None,
    }
    if previous is not None:
        result["previous"] = dict(previous, date=previous_date)
    if current is None or previous is None:
        return result

    if current["top_load_kg"] > previous["top_load_kg"]:
        result["classification"] = PROGRESSION
    elif current["top_load_kg"] < previous["top_load_kg"]:
        result["classification"] = REGRESSION
    else:
        delta = current["reps_at_top_load"] - previous["reps_at_top_load"]
        result["delta_reps_at_top_load"] = delta
        if delta > 0:
            result["classification"] = PROGRESSION
        elif delta < 0:
            result["classification"] = REGRESSION
        else:
            result["classification"] = MAINTIEN
    if result["delta_reps_at_top_load"] is None:
        result["delta_reps_at_top_load"] = (
            current["reps_at_top_load"] - previous["reps_at_top_load"]
        )
    return result


def split_current_and_history(
    activity_id: Optional[str],
    entries: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Separate the current session from the earlier ones inside the history.

    The coach reads the strength history from DynamoDB, and the content branch appends
    the current session to it in parallel. So the current entry may or may not be there
    yet. Rather than racing, this reports what is actually present: when the entry for
    ``activity_id`` is found its totals become the authoritative ``strength_session``
    and the earlier entries become the comparison base; when it is absent both stay
    empty and the caller states nothing.
    """
    result: Dict[str, Any] = {"current": None, "earlier": [], "found": False}
    if not isinstance(entries, list) or not entries:
        return result
    target = str(activity_id or "")
    earlier: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if target and str(entry.get("activity_id") or "") == target:
            result["current"] = entry
            result["found"] = True
            continue
        earlier.append(entry)
    result["earlier"] = earlier
    return result


def build_exercise_comparisons(
    current_parsed_sets: Optional[List[Dict[str, Any]]],
    history_entries: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """One comparison per exercise of the current session.

    The previous occurrence is the most recent earlier entry that names the same
    exercise. History is expected oldest-first, as stored.
    """
    if not isinstance(current_parsed_sets, list):
        return []

    previous_by_exercise: Dict[str, Dict[str, Any]] = {}
    if isinstance(history_entries, list):
        for entry in history_entries:
            if not isinstance(entry, dict):
                continue
            parsed = entry.get("parsed_sets")
            if not isinstance(parsed, list):
                continue
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("exercise") or "").strip()
                detail = _sets_detail(item)
                if name and detail:
                    # Later entries overwrite earlier ones: the most recent wins.
                    previous_by_exercise[name] = {
                        "sets_detail": detail,
                        "date": entry.get("date"),
                    }

    comparisons: List[Dict[str, Any]] = []
    for item in current_parsed_sets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("exercise") or "").strip()
        if not name:
            continue
        previous = previous_by_exercise.get(name)
        comparisons.append(
            compare_exercise(
                name,
                _sets_detail(item),
                (previous or {}).get("sets_detail"),
                (previous or {}).get("date"),
            )
        )
    return comparisons
