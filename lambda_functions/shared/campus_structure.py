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

# Canonical movement family -> the stems that appear in the PLAN's exercise names.
# "fente" and "split squat" are the same movement (his own wording), which no shared
# table currently knows.
_FAMILY_STEMS: Dict[str, tuple] = {
    "mollet": ("mollet",),
    "split squat": ("fente", "split squat"),
    "swing": ("swing",),
    "gainage": ("gainage",),
}

# How the athlete WRITES each family -> canonical family. Matched as whole-token phrases,
# longest first. Deliberately no bare "squat", "split" or "quat": "Back squat 85kg" is not
# a split squat, and mapping it would double it. "split quat" is his own typo (2026-10-10).
_FAMILY_ALIASES: tuple = (
    ("split squat", "split squat"),
    ("split quat", "split squat"),
    ("fentes", "split squat"),
    ("fente", "split squat"),
    ("mollets", "mollet"),
    ("mollet", "mollet"),
    ("swings", "swing"),
    ("swing", "swing"),
    ("gainage", "gainage"),
)


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
# the split squat ("2x20 kg" for what he logs as "Fentes ketle 20kg"), and again on
# 2026-10-13 ("2 ketle de 24kg" = 48 kg). Kept as an explicit, citable table rather than
# a heuristic: guessing a doubling would silently overstate every tonnage. Applied ONCE:
# a written "2 ketle" confirms the doubling, it never makes it x4.
_DUAL_IMPLEMENT_FAMILIES = frozenset({"split squat"})

# Clause boundaries. A comma between two digits is a decimal ("12,5kg") and a slash is a
# boundary only when spaced, so "35kg/cote" and "40/c" stay whole.
_SEGMENT_SEP = re.compile(r"[\n\r;()]|(?<!\d),|,(?!\d)|\s/\s|\b(?:et|puis)\b")
_KG_VALUE = re.compile(r"(\d+(?:[.,]\d+)?)\s*kg")
_KG_RANGE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:kg)?\s*[-–→]\s*\d+(?:[.,]\d+)?\s*kg")
# Whole tokens that carry no exercise meaning: the implement and French fillers. Removed
# as TOKENS; the previous str.replace("kettlebell") turned "kettlebells" into "s", which
# then matched every plan exercise containing an "s".
_IMPLEMENT_TOKENS = frozenset(
    {"ketle", "ketles", "kettle", "kettles", "kettlebell", "kettlebells", "haltere", "halteres"}
)
_FILLER_TOKENS = frozenset(
    {"avec", "de", "du", "des", "pour", "sur", "et", "a", "la", "le", "les", "en", "charge", "deux"}
)
_COUNT_TOKEN = re.compile(r"^\d*x\d*$|^\d+$")
# A non-family term is kept only when one of its words is at least this long, so a
# leftover fragment can never become a key.
_MIN_TERM_TOKEN = 4


def _fold(text: Any) -> str:
    """Normalize and turn a hyphen between letters into a space ("split-squat")."""
    return re.sub(r"(?<=[a-z])-(?=[a-z])", " ", _normalize(text))


def _tokens(text: str) -> List[str]:
    return re.sub(r"[^a-z0-9]+", " ", text).split()


def _families_in(text: str) -> set:
    """Canonical families named in ``text``, by whole-token phrase, longest first."""
    padded = " " + " ".join(_tokens(_fold(text))) + " "
    found: set = set()
    for alias, family in _FAMILY_ALIASES:
        needle = " " + alias + " "
        if needle in padded:
            found.add(family)
            padded = padded.replace(needle, " ")
    return found


def _canonical_family(key: Any) -> Optional[str]:
    """Family of a loads-dict key, so legacy caller keys ("fente") keep resolving."""
    families = _families_in(str(key or ""))
    return next(iter(families)) if len(families) == 1 else None


def _plan_family(exercise_name: str) -> Optional[str]:
    """Family of a PLAN exercise. Containment is intentional here: "mollet" covers
    "Extension de Mollet" and "Mollet statique"."""
    target = _fold(exercise_name)
    for family, stems in _FAMILY_STEMS.items():
        if any(stem in target for stem in stems):
            return family
    return None


# Families planned PER LEG by Campus: the plan's reps are for one leg, both legs are done
# (athlete, 2026-10-13). Only the plan path uses this: his own free text is unchanged.
_PER_LEG_FAMILIES = frozenset({"split squat"})

# Canonical strength names (shared/strength_exercises) for the plan's REP-BASED family
# moves, so a Campus session continues the athlete's existing "Fentes" / "Mollets" series
# instead of opening "Split Squat avec charge additionnelle". Holds keep their plan name:
# a loaded hold has no tonnage and must not mark the counted family row as excluded.
_FAMILY_CANONICAL_NAME = {"split squat": "Fentes", "mollet": "Mollets"}


def _plan_sides(exercise_name: str) -> int:
    return 2 if _plan_family(exercise_name) in _PER_LEG_FAMILIES else 1


def ppg_history_sets(
    session: Optional[Dict[str, Any]],
    loads_kg: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """The Campus PLAN as strength-history sets, in the shape ``compute_session_volume`` reads.

    Athlete rule (2026-10-13): for a Campus renfo the sets and reps come from the plan and
    only the loads from his text. One item per exercise, in order of first appearance;
    one ``sets_detail`` entry per planned round (per occurrence in the legacy flat shape).
    Holds carry ``reps: None`` and ``duration_s``. ``sides`` marks the per-leg moves.
    """
    items: Dict[str, Dict[str, Any]] = {}
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
            family = _plan_family(name)
            label = _FAMILY_CANONICAL_NAME.get(family, name) if reps is not None else name
            load = _load_for(name, loads_kg)
            item = items.setdefault(
                label,
                {"exercise": label, "sides": _plan_sides(name), "sets_detail": []},
            )
            for _ in range(rounds):
                item["sets_detail"].append(
                    {
                        "reps": int(reps) if reps is not None else None,
                        "weight_kg": load,
                        "duration_s": hold_s if reps is None else None,
                    }
                )
    result: List[Dict[str, Any]] = []
    for item in items.values():
        detail = item["sets_detail"]
        loads = [s["weight_kg"] for s in detail if s["weight_kg"] is not None]
        reps_list = [s["reps"] for s in detail if s["reps"] is not None]
        result.append(
            {
                "exercise": item["exercise"],
                "sets": len(detail),
                "reps": max(set(reps_list), key=reps_list.count) if reps_list else None,
                "weight_kg": max(loads) if loads else None,
                "sides": item["sides"],
                # Plan loads are stored as the athlete wrote them, never doubled
                # from a per-side note: say so, so the page does not guess.
                "per_side": False,
                "sets_detail": detail,
            }
        )
    return result


def extract_athlete_loads(description: Optional[str]) -> Dict[str, float]:
    """Loads the athlete logged, keyed by canonical family (or by his own term).

    His wording changes a little every time ("Fentes ketle 20kg", "split squat 2
    kettlebells de 20kg", "Split quat avec 2 ketle de 16kg"), so the text is read clause
    by clause and a family is recognised by whole words, never by a fragment. Every
    ambiguous case abstains rather than guessing a load:

    - a range ("85-87,5kg") or two different values for one clause or family;
    - one load for two families in the same clause;
    - a term too short to mean anything once implements and fillers are dropped.

    A clause holding only a value ("puis 24kg") belongs to the family of the clause just
    before it, which is how "Swing 16kg puis 24kg" is recognised as a conflict. The
    dual-implement doubling is applied once, after the conflict check on raw values.
    """
    if not isinstance(description, str) or not description:
        return {}
    text = _fold(description)
    values: Dict[str, List[float]] = {}
    anchor: Optional[str] = None
    for segment in _SEGMENT_SEP.split(text):
        segment = segment.strip()
        if not segment:
            continue
        kg_matches = list(_KG_VALUE.finditer(segment))
        term_text = segment[: kg_matches[0].start()] if kg_matches else segment
        families = _families_in(term_text)
        family = next(iter(families)) if len(families) == 1 else None
        if not kg_matches:
            # A family named without a value still anchors a value-only clause after it.
            anchor = family
            continue
        if _KG_RANGE.search(segment) or len(families) > 1:
            anchor = None
            continue
        raw = [_to_float(m.group(1)) for m in kg_matches]
        raw = [value for value in raw if value is not None]
        if not raw:
            continue
        words = [
            token
            for token in _tokens(term_text)
            if token not in _IMPLEMENT_TOKENS
            and token not in _FILLER_TOKENS
            and not _COUNT_TOKEN.match(token)
        ]
        if family:
            values.setdefault(family, []).extend(raw)
            anchor = family
        elif not words:
            # Value-only clause: it continues the family named just before, if any.
            if anchor:
                values.setdefault(anchor, []).extend(raw)
        elif any(len(token) >= _MIN_TERM_TOKEN for token in words):
            values.setdefault(" ".join(words), []).extend(raw)
            anchor = None
        else:
            anchor = None

    loads: Dict[str, float] = {}
    for key, raw_values in values.items():
        if len(set(raw_values)) != 1:
            continue
        load = raw_values[0]
        if key in _DUAL_IMPLEMENT_FAMILIES:
            load *= 2
        loads[key] = load
    return loads


def _load_for(exercise_name: str, loads_kg: Optional[Dict[str, float]]) -> Optional[float]:
    """Load stated by the athlete for the family this exercise belongs to.

    Family keys resolve first, through the same alias table as the extraction, so a
    caller-supplied legacy key ("fente") still reaches the plan's "Split Squat". A
    non-family key matches only by whole words AND only an exercise that belongs to no
    family: "Squat 60kg" must never take the split squat's load.
    """
    if not loads_kg:
        return None
    target_family = _plan_family(exercise_name)
    if target_family:
        for key, raw_load in loads_kg.items():
            load = _to_float(raw_load)
            if load is not None and _canonical_family(key) == target_family:
                return load
        return None
    target_words = set(_tokens(_fold(exercise_name)))
    for key, raw_load in loads_kg.items():
        load = _to_float(raw_load)
        if load is None or _canonical_family(key):
            continue
        key_words = _tokens(_fold(key))
        if key_words and all(word in target_words for word in key_words):
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

    The split squat is planned PER LEG (athlete, 2026-10-13: "4 reps" = 4 per leg), so
    its sets, reps and volume count both legs. ``ppg_history_sets`` applies the same
    rule through ``sides``, so the coach's figure and the stored history agree.
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
            sides = _plan_sides(name)
            entry: Dict[str, Any] = {
                "exercise": name,
                "sets": rounds * sides,
                "sides": sides,
                "reps_per_set": reps,
                "hold_s": hold_s,
                "weight_kg": load,
                "volume_kg": 0.0,
                "time_under_load_s": 0.0,
            }
            total_sets += rounds * sides

            if reps is not None:
                total_reps += int(reps * rounds * sides)
                if load is not None:
                    entry["volume_kg"] = float(reps * rounds * sides * load)
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
