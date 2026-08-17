"""Campus PPG structure and volume, computed in code.

Why this exists
---------------
On 2026-08-14 the pipeline received the full plan of the "Renforcement" session in its
context -- two blocks, four rounds each, six named work exercises -- and published a
description that flattened it into the three loads the athlete had typed. It lost three
exercises (one of them loaded), announced "Bloc 1/2" because the athlete had written
"Partie 1 du jour" about his two SESSIONS that day, projected the second block as a
future session, and compared the 44 minutes actually done to the 30 planned minutes as
if those covered a single block. Meanwhile the strength history stored zero sets for the
session.

None of that was a data problem: the plan carries ``reps``, durations, round counts and
exercise names, and the athlete's loads make the volume computable. So the structure and
the volume are computed here and handed over as facts.

Three rules encode what the athlete confirmed about his own logging:

1. **A matched Campus session is done in full.** He performs every block and every
   round; he only types the loads. The number of blocks completed is therefore never
   inferred from his free text, which is why ``is_fully_completed`` reads the duration
   instead.
2. **A load applies to a movement FAMILY.** "Mollet ketle 12kg" covers both "Extension
   de Mollet" (block 1) and "Mollet statique" (block 2). The match is one-to-many.
3. **A loaded isometric is not tonnage.** "Mollet statique 40 sec" under 12 kg is real
   work that ``reps x load`` cannot express. It is reported as time under load and it
   forces ``volume_kg_incomplete``, per the project invariant that a partial volume
   stays explicit.

Reservation on the family table: ``canonicalize_exercise_name`` was tried first and
recognises none of these names (neither the plan's "Split Squat avec charge
additionnelle" nor the athlete's "Fentes"), so the mapping is local and explicit here
rather than built on a resolver that does not cover this vocabulary. Extending the
canonical vocabulary would let this table go away.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Movement families, as the athlete names them -> the stem that appears in the plan.
# "fente" and "split squat" are the same movement (his own wording), which no shared
# table currently knows.
_FAMILY_STEMS: Dict[str, tuple] = {
    "mollet": ("mollet",),
    "fente": ("fente", "split squat"),
    "split squat": ("fente", "split squat"),
    "swing": ("swing",),
    "gainage": ("gainage",),
}


def _normalize(value: Any) -> str:
    text = str(value or "").strip().lower()
    for accented, plain in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ô", "o")):
        text = text.replace(accented, plain)
    return text


def _parse_duration_seconds(raw: Any) -> Optional[float]:
    """'30 sec' -> 30, '1:30 min' -> 90. Returns None when nothing is stated."""
    text = _normalize(raw)
    if not text:
        return None
    clock = re.match(r"^(\d+):(\d{1,2})", text)
    if clock:
        return float(int(clock.group(1)) * 60 + int(clock.group(2)))
    number = re.match(r"^(\d+(?:[.,]\d+)?)", text)
    if not number:
        return None
    value = float(number.group(1).replace(",", "."))
    if "min" in text:
        return value * 60
    return value


def _to_float(raw: Any) -> Optional[float]:
    try:
        return float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _blocks(session: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the intervals as a list of blocks, tolerating the legacy flat shape."""
    intervals = (session or {}).get("intervals")
    if not isinstance(intervals, list) or not intervals:
        return []
    blocks: List[Dict[str, Any]] = []
    flat: List[Dict[str, Any]] = []
    for entry in intervals:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "block" and isinstance(entry.get("exercises"), list):
            repeat = _to_float(entry.get("repeat")) or 1
            blocks.append({"repeat": int(repeat), "exercises": entry["exercises"]})
        else:
            flat.append(entry)
    if flat:
        # A pre-block row: one implicit block performed once.
        blocks.append({"repeat": 1, "exercises": flat})
    return blocks


def summarize_structure(session: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Blocks, rounds and every work exercise of the planned session."""
    blocks = _blocks(session)
    work_exercises: List[str] = []
    recovery: Optional[str] = None
    for block in blocks:
        for exercise in block["exercises"]:
            if not isinstance(exercise, dict):
                continue
            name = str(exercise.get("name") or "").strip()
            if exercise.get("type") == "recovery":
                if recovery is None and exercise.get("duration"):
                    recovery = str(exercise["duration"]).strip()
                continue
            if name and name not in work_exercises:
                work_exercises.append(name)
    return {
        "blocks": len(blocks),
        "rounds": [block["repeat"] for block in blocks],
        "work_exercises": work_exercises,
        "recovery_per_round": recovery,
        "expected_duration_min": (session or {}).get("expected_duration_min"),
    }


def is_fully_completed(
    session: Optional[Dict[str, Any]],
    actual_duration_min: Optional[float],
) -> Optional[bool]:
    """True when the session lasted at least as long as planned.

    The point is to refute "Bloc 1/2" and "prochaine etape : le Bloc 2" on a session
    that ran 44 minutes against 30 planned. Returns None when either duration is
    unknown, so the caller abstains rather than guesses.
    """
    planned = _to_float((session or {}).get("expected_duration_min"))
    actual = _to_float(actual_duration_min)
    if planned is None or actual is None or planned <= 0:
        return None
    return actual >= planned


# Families the athlete performs with TWO implements, so the load he writes is per
# implement and the load actually moved is double. Confirmed by him on 2026-08-17 for
# the split squat ("2x20 kg" for what he logs as "Fentes ketle 20kg"). Kept as an
# explicit, citable table rather than a heuristic: guessing a doubling would silently
# overstate every tonnage.
_DUAL_IMPLEMENT_STEMS = ("fente", "split squat")

_LOAD_LINE = re.compile(r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ '\-]{2,40}?)\s*(\d+(?:[.,]\d+)?)\s*kg", re.IGNORECASE)


def extract_athlete_loads(description: Optional[str]) -> Dict[str, float]:
    """Loads the athlete logged, keyed by the term he used.

    'Mollet ketle 12kg / Fentes ketle 20kg / Swing ketle 24kg' yields the three
    families, with the dual-implement doubling already applied where it is confirmed.
    """
    loads: Dict[str, float] = {}
    if not isinstance(description, str) or not description:
        return loads
    for match in _LOAD_LINE.finditer(description):
        term = _normalize(match.group(1))
        load = _to_float(match.group(2))
        if not term or load is None:
            continue
        # Keep the family word, dropping the equipment noise ("ketle", "kettlebell").
        for noise in ("ketle", "kettlebell", "kettle", "haltere", "halteres", "avec", "charge"):
            term = term.replace(noise, " ")
        term = " ".join(term.split())
        if not term:
            continue
        if any(stem in term for stem in _DUAL_IMPLEMENT_STEMS):
            load *= 2
        loads[term] = load
    return loads


def _load_for(exercise_name: str, loads_kg: Optional[Dict[str, float]]) -> Optional[float]:
    """Load stated by the athlete for the family this exercise belongs to.

    The family is looked up by CONTAINMENT, not by exact key. The athlete writes "Fentes"
    while the table keys on "fente", and an exact ``.get()`` silently fell through to the
    literal term, so "Fentes ketle 20kg" never reached the plan's "Split Squat". The
    doubling rule below already matched by containment, which is why the load was correctly
    doubled to 40 and then attached to nothing.
    """
    if not loads_kg:
        return None
    target = _normalize(exercise_name)
    for term, raw_load in loads_kg.items():
        load = _to_float(raw_load)
        if load is None:
            continue
        term_n = _normalize(term)
        stems: Optional[tuple] = None
        for key, family in _FAMILY_STEMS.items():
            if key in term_n:
                stems = family
                break
        for stem in stems or (term_n,):
            if stem and stem in target:
                return load
    return None


def resolve_exercise_loads(
    session: Optional[Dict[str, Any]],
    athlete_description: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """One row per work exercise, with the load resolved through the FAMILY rule.

    Exists because the family rule was implemented here and reached nobody: the content
    agent received the structure and the completion flag but not the loads, so on
    2026-08-17 it published "Mollet statique au poids du corps" while the athlete had
    logged "Mollet 12kg" for the calf family.

    ``bodyweight`` is stated explicitly rather than inferred from a null load, so a
    consumer never has to decide what a missing value means. The load is never guessed:
    only a load the athlete actually wrote, propagated across its family.
    """
    rows: List[Dict[str, Any]] = []
    loads = extract_athlete_loads(athlete_description)
    seen: set = set()
    # _blocks is the module's own reader: it tolerates the per-block, flat and legacy
    # interval shapes, so a row is produced whatever the sync wrote.
    for block in _blocks(session):
        for exercise in block["exercises"]:
            if not isinstance(exercise, dict):
                continue
            if exercise.get("type") not in (None, "work"):
                continue
            name = str(exercise.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            load = _load_for(name, loads)
            rows.append(
                {
                    "exercise": name,
                    "load_kg": load,
                    "bodyweight": load is None,
                    "reps": exercise.get("reps"),
                    "duration_s": _parse_duration_seconds(exercise.get("duration")),
                }
            )
    return rows


def compute_ppg_volume(
    session: Optional[Dict[str, Any]],
    loads_kg: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Volume of a Campus PPG session from the plan and the athlete's loads.

    A rep-based exercise yields tonnage. A hold yields time: under load when the
    athlete stated one for that family, as bodyweight time otherwise. Any loaded hold
    forces ``volume_kg_incomplete``, because its work is real but not expressible as
    ``reps x load``.
    """
    per_exercise: List[Dict[str, Any]] = []
    total_sets = 0
    total_reps = 0
    volume_kg = 0.0
    time_under_load = 0.0
    bodyweight_time = 0.0
    excluded: List[str] = []
    incomplete = False

    for block in _blocks(session):
        rounds = block["repeat"]
        for exercise in block["exercises"]:
            if not isinstance(exercise, dict) or exercise.get("type") == "recovery":
                continue
            name = str(exercise.get("name") or "").strip()
            if not name:
                continue
            reps = _to_float(exercise.get("reps"))
            hold_s = _parse_duration_seconds(exercise.get("duration"))
            load = _load_for(name, loads_kg)
            entry: Dict[str, Any] = {
                "exercise": name,
                "sets": rounds,
                "reps_per_set": reps,
                "hold_s": hold_s,
                "weight_kg": load,
                "volume_kg": 0.0,
                "time_under_load_s": 0.0,
            }
            total_sets += rounds

            if reps is not None:
                total_reps += int(reps * rounds)
                if load is not None:
                    entry["volume_kg"] = float(reps * rounds * load)
                    volume_kg += entry["volume_kg"]
                else:
                    # A rep-based exercise whose load the athlete did not state.
                    incomplete = True
                    excluded.append(name)
            elif hold_s is not None:
                if load is not None:
                    entry["time_under_load_s"] = float(hold_s * rounds)
                    time_under_load += entry["time_under_load_s"]
                    # Loaded hold: real work, no tonnage. Keep the total honest.
                    incomplete = True
                    excluded.append(name)
                else:
                    bodyweight_time += float(hold_s * rounds)
            else:
                incomplete = True
                excluded.append(name)

            per_exercise.append(entry)

    return {
        "per_exercise": per_exercise,
        "total_sets": total_sets,
        "total_reps": total_reps,
        "volume_kg": round(volume_kg, 1),
        "volume_kg_incomplete": incomplete,
        "time_under_load_s": time_under_load,
        "bodyweight_time_s": bodyweight_time,
        "excluded_exercises": excluded,
    }
