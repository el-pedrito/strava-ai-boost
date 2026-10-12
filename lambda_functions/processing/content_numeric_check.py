"""Lap paces and strength loads stated in the content, checked against the athlete's data.

Why this exists
---------------
Between August and October 2026 the athlete corrected the published description by hand
for two families of wrong numbers that the content guard let through:

* **Lap paces.** Five times the text attributed to a block a pace no lap carries, e.g.
  "un bloc a 4:41/km" when the lap ``average_speed`` gives 4:33/km.
* **Strength loads swapped between exercises.** He wrote "split squat 2 kettlebells 16kg"
  and "mollet 12kg"; the text put 12 kg on the split squat.

Both are computable: the pace from ``average_speed`` (never ``max_speed``, see
``shared/lap_facts.py``), the load from what he typed. So they are checked in code.

Both detectors ABSTAIN rather than guess. A pace is only checked when the sentence
attributes it to a lap-like unit (or lists several block paces), and never when its
clause frames it as a target, a zone, an average, an Enduraw adjusted pace or a record.
A load is only checked when its clause names exactly the exercise family it attaches to
and the athlete stated a load for that family. Temperatures are deliberately out of
scope: the three wrong ones came from Enduraw's own report, not from the generation.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from shared.strength_exercises import (
    CANONICAL_STRENGTH_EXERCISES,
    _ALIAS_GROUPS,
)

# ---------------------------------------------------------------------------
# Text normalisation (length-preserving, so spans map back to the original)
# ---------------------------------------------------------------------------


def _fold(text: str) -> str:
    """Lower-case, accent-free, same length as ``text``: indexes stay aligned."""
    out = []
    for char in text.lower():
        base = unicodedata.normalize("NFKD", char)
        base = "".join(c for c in base if not unicodedata.combining(c)) or " "
        out.append(base[0])
    return "".join(out)


# ---------------------------------------------------------------------------
# Lap paces
# ---------------------------------------------------------------------------

# Tolerance between a cited pace and a lap pace. 4:33 vs 4:34 is the same lap rounded
# differently (the lap pace is truncated, the model may round). 3 s rather than the 5 s
# first specified: at 5 s, a wrong "4:41" next to a real 4:37 lap would pass, which is
# exactly the audited block case (laps 4:33 / 4:34 / 4:37, text 4:41).
PACE_TOLERANCE_S = 3

_PACE_TOKEN = re.compile(
    r"(?<![\d:'])(\d{1,2})[:'](\d{2})(?![\d:])(\s*(?:min)?\s*/\s*km\b)?", re.IGNORECASE
)
# Separators that chain block paces: "4:33, 4:34 puis 4:37/km", "4:33 / 4:34".
_CHAIN_GAP = re.compile(r"^\s*(?:[,;]\s*(?:puis|et)?|puis|et|/)\s*$", re.IGNORECASE)
# Separators that make a range: "4:30-4:40/km", "4:30 a 4:40/km".
_RANGE_GAP = re.compile(r"^\s*(?:-|–|à|a)\s*$", re.IGNORECASE)

_LAP_WORDS = re.compile(
    r"\b(?:laps?|tours?|blocs?|intervalles?|series?|efforts?|fractions?|fractionne\w*"
    r"|reps?|repetitions?|sprints?)\b"
)

# Clause words that make a pace something other than a lap's actual pace.
_PACE_EXCLUSIONS = re.compile(
    r"\b(?:cibles?|objectifs?|prevue?s?|visee?s?|viser|visait|plan|consigne|target"
    r"|zones?|ef|endurance fondamentale|semi|marathon|specifique|seuil|vma"
    r"|enduraw|ajustee?s?|corrigee?s?|gap|moyenne|moyen|globale?|ensemble|total"
    r"|pr|records?|best|meilleure?s?|derniere fois|precedente?|semaine derniere"
    r"|contre|vs|entre)\b"
)
# Best-effort phrasing: "1K en 4:32", "5 km en 22:10".
_BEST_EFFORT_PREFIX = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:k|km|m|mi)\s+en\s*$")

_CLAUSE_SEP = re.compile(r"[,;()\[\]]")


def lap_paces_seconds(laps_data: Optional[list]) -> Optional[List[int]]:
    """Pace of every lap in seconds per km, from ``average_speed`` only.

    ``max_speed`` is never read: it is a GPS peak (see shared/lap_facts.py).
    """
    if not laps_data:
        return None
    paces: List[int] = []
    for lap in laps_data:
        if not isinstance(lap, dict):
            continue
        raw = lap.get("average_speed")
        try:
            speed = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            speed = None
        if speed and speed > 0:
            # Truncated like shared.lap_facts._format_pace, so "4:33" here is the same
            # string the model was handed.
            paces.append(int(1000.0 / speed))
    return paces or None


def _fmt(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def _pace_groups(sentence: str) -> List[Dict[str, Any]]:
    """Chained pace tokens of one sentence, with their span and range flag."""
    tokens = list(_PACE_TOKEN.finditer(sentence))
    groups: List[Dict[str, Any]] = []
    current: List[re.Match] = []
    is_range = False
    for token in tokens:
        if current:
            gap = sentence[current[-1].end():token.start()]
            if _CHAIN_GAP.match(gap):
                current.append(token)
                continue
            if _RANGE_GAP.match(gap):
                current.append(token)
                is_range = True
                continue
            groups.append({"tokens": current, "range": is_range})
        current, is_range = [token], False
    if current:
        groups.append({"tokens": current, "range": is_range})
    # A group is a pace group only if one of its tokens carries "/km".
    return [g for g in groups if any(t.group(3) for t in g["tokens"])]


def _clause_window(folded: str, start: int, end: int) -> Tuple[int, int]:
    left = 0
    for match in _CLAUSE_SEP.finditer(folded, 0, start):
        left = match.end()
    right_match = _CLAUSE_SEP.search(folded, end)
    right = right_match.start() if right_match else len(folded)
    return left, right


def check_lap_paces(sentence: str, lap_paces: Optional[List[int]]) -> List[str]:
    """Paces attributed to a lap/block that no lap carries, and impossible paces."""
    problems: List[str] = []
    folded = _fold(sentence)
    groups = _pace_groups(sentence)
    if not groups:
        return problems
    has_lap_word = bool(_LAP_WORDS.search(folded))

    for group in groups:
        tokens = group["tokens"]
        # Seconds >= 60 are never a pace, whatever the framing.
        checkable: List[Tuple[str, int]] = []
        for token in tokens:
            seconds = int(token.group(2))
            text = f"{token.group(1)}:{token.group(2)}"
            if seconds >= 60:
                problems.append(f"allure {text}/km invalide (secondes >= 60)")
                continue
            checkable.append((text, int(token.group(1)) * 60 + seconds))

        if not lap_paces or group["range"]:
            continue
        start, end = tokens[0].start(), tokens[-1].end()
        if not (has_lap_word or len(tokens) >= 2):
            continue
        left, right = _clause_window(folded, start, end)
        if _PACE_EXCLUSIONS.search(folded[left:right]):
            continue
        if _BEST_EFFORT_PREFIX.search(folded[left:start]):
            continue
        listed = ", ".join(_fmt(p) for p in lap_paces[:25])
        for text, value in checkable:
            if not any(abs(value - lap) <= PACE_TOLERANCE_S for lap in lap_paces):
                problems.append(
                    f"allure {text}/km ne correspond à aucun lap (laps: {listed})"
                )
    return problems


# ---------------------------------------------------------------------------
# Strength loads
# ---------------------------------------------------------------------------

# Families the athlete names that the canonical vocabulary does not cover. Same family
# rule as shared/campus_structure.py: "fente" and "split squat" are one movement, and a
# calf load covers every calf exercise.
_LOCAL_FAMILIES: Tuple[Tuple[str, str], ...] = (
    ("split squat", "fente"),
    ("fentes", "fente"),
    ("fente", "fente"),
    ("extensions de mollet", "mollet"),
    ("extension de mollet", "mollet"),
    ("mollets", "mollet"),
    ("mollet", "mollet"),
    ("calf", "mollet"),
    ("swings", "swing"),
    ("swing", "swing"),
    ("gainage", "gainage"),
)


def _build_family_terms() -> List[Tuple[str, str]]:
    terms: Dict[str, str] = {}
    for name in CANONICAL_STRENGTH_EXERCISES:
        terms[" ".join(re.sub(r"[^a-z0-9]+", " ", _fold(name)).split())] = name
    for canonical, aliases in _ALIAS_GROUPS:
        for alias in aliases:
            terms[" ".join(re.sub(r"[^a-z0-9]+", " ", _fold(alias)).split())] = canonical
    for term, family in _LOCAL_FAMILIES:
        terms[term] = family
    # The canonical "Mollets"/"Fentes"/"Gainage" fold into the local family keys.
    for term, family in list(terms.items()):
        for local_term, local_family in _LOCAL_FAMILIES:
            if term == local_term:
                terms[term] = local_family
    # Longest first, so "split squat" wins over "squat" and "dc halteres" over "dc".
    return sorted(terms.items(), key=lambda item: -len(item[0]))


_FAMILY_TERMS = _build_family_terms()
_FAMILY_PATTERNS = [
    (re.compile(r"(?<![a-z0-9])" + re.escape(term).replace(r"\ ", r"[^a-z0-9]+") + r"(?![a-z0-9])"), family)
    for term, family in _FAMILY_TERMS
    if len(term) >= 2
]

# "16kg", "16 kg", "@70kg", "40/c", "40 kg/c", "55/cote". Not "4x8".
_KG_VALUE = re.compile(
    r"(?<![\dx×.,])(\d{1,3}(?:[.,]\d+)?)\s*(?:(kg)\b\s*(/\s*c(?:ot[eé])?\b)?|(/\s*c(?:ot[eé])?\b))",
    re.IGNORECASE,
)
_LOAD_CLAUSE_SEP = re.compile(r"[,;()\[\]\n+]|\s(?:et|puis|-|/)\s|\.\s")
# A kg in such a clause is not the load of the exercise performed today.
_LOAD_EXCLUSIONS = re.compile(
    r"\b(?:volume|tonnage|total|cumul\w*|souleve\w*|poids du corps|pdc|corps"
    r"|derniere?|precedente?|semaine|avant|contre|vs|record|pr|objectif|cible"
    r"|prochaine?|viser|vise|progression|passe|monte\w*)\b"
)


def _family_mentions(folded: str) -> List[Tuple[int, int, str]]:
    taken: List[Tuple[int, int, str]] = []
    for pattern, family in _FAMILY_PATTERNS:
        for match in pattern.finditer(folded):
            if any(match.start() < e and s < match.end() for s, e, _ in taken):
                continue
            taken.append((match.start(), match.end(), family))
    return sorted(taken)


def _clauses(text: str) -> List[Tuple[int, int]]:
    spans, cursor = [], 0
    for match in _LOAD_CLAUSE_SEP.finditer(text):
        spans.append((cursor, match.start()))
        cursor = match.end()
    spans.append((cursor, len(text)))
    return [(s, e) for s, e in spans if e > s]


def _kg_by_family(text: str, apply_exclusions: bool) -> List[Tuple[str, float, str]]:
    """``(family, kg, clause)`` for every kg attached to one family in its clause.

    The returned clause is the folded one (accent-free, lower-case).
    """
    out: List[Tuple[str, float, str]] = []
    if not isinstance(text, str) or not text:
        return out
    folded = _fold(text)
    mentions = _family_mentions(folded)
    for start, end in _clauses(folded):
        clause_mentions = [m for m in mentions if start <= m[0] and m[1] <= end]
        families = {m[2] for m in clause_mentions}
        if len(families) != 1:
            # Zero: no exercise named. Several: attribution is ambiguous (supersets
            # "A - B 15-35"), so abstain.
            continue
        clause = folded[start:end]
        if apply_exclusions and _LOAD_EXCLUSIONS.search(clause):
            continue
        family = next(iter(families))
        for match in _KG_VALUE.finditer(text, start, end):
            try:
                value = float(match.group(1).replace(",", "."))
            except ValueError:
                continue
            if value > 0:
                out.append((family, value, clause.strip()))
    return out


def _family_of(name: str) -> Optional[str]:
    mentions = _family_mentions(_fold(name))
    return mentions[0][2] if mentions else None


# Families logged with two implements (shared/campus_structure._DUAL_IMPLEMENT_STEMS):
# "Fentes ketle 20kg" is 20 kg in each hand, 40 moved.
_DUAL_FAMILIES = {"fente"}
# The athlete's own marks of a per-side or two-implement load.
_PER_SIDE = re.compile(
    r"/\s*c(?:ote)?\b|par cote|par main|chacune?|chaque|\b(?:2|deux)\s*(?:x\s*)?"
    r"(?:kettle\w*|ketle\w*|kb|halteres?|kettlebells?)\b"
)

# family -> {"values": [...], "flex": bool}. ``flex`` means the load is per side or per
# implement, so the doubled (total moved) and halved readings are both correct.
FamilyLoads = Dict[str, Dict[str, Any]]


def athlete_family_loads(
    athlete_description: Optional[str],
    resolved_rows: Optional[List[Dict[str, Any]]] = None,
) -> Optional[FamilyLoads]:
    """Loads the athlete stated, per exercise family.

    His own text is the primary source. The Campus rows from ``resolve_exercise_loads``
    only fill families his text did not yield: that resolver keys on the free-text term
    before "kg", so "Split squat 2 kettlebells 16kg" yields the term "s", which then
    matches EVERY exercise name by containment and put 16 kg on the calf too. Trusting it
    over the text would re-create the very swap this check exists to catch.
    """
    loads: FamilyLoads = {}
    for family, value, clause in _kg_by_family(athlete_description or "", False):
        entry = loads.setdefault(family, {"values": [], "flex": family in _DUAL_FAMILIES})
        entry["values"].append(value)
        if _PER_SIDE.search(clause):
            entry["flex"] = True
    from_text = set(loads)
    for row in resolved_rows or []:
        if not isinstance(row, dict) or row.get("load_kg") in (None, ""):
            continue
        family = _family_of(str(row.get("exercise") or ""))
        try:
            value = float(row["load_kg"])
        except (TypeError, ValueError):
            continue
        if family and value > 0 and family not in from_text:
            entry = loads.setdefault(family, {"values": [], "flex": family in _DUAL_FAMILIES})
            entry["values"].append(value)
    return loads or None


def _allowed(entry: Dict[str, Any]) -> List[float]:
    # Per side / per implement only: "40/c" is 40 kg per side or 80 moved, "2 kettlebells
    # 16kg" is 16 each or 32 moved. For a plain load the doubling is NOT allowed, or a
    # 70 kg claimed on a 35 kg military press would pass as "35 x 2".
    allowed = set()
    for value in entry["values"]:
        allowed.add(value)
        if entry["flex"]:
            allowed.update({value * 2, value / 2})
    return sorted(allowed)


def _kg(value: float) -> str:
    return f"{value:g}"


def check_strength_loads(sentence: str, family_loads: Optional[FamilyLoads]) -> List[str]:
    """Loads attached to an exercise family that differ from what the athlete wrote."""
    problems: List[str] = []
    if not family_loads:
        return problems
    for family, value, clause in _kg_by_family(sentence, True):
        entry = family_loads.get(family)
        if not entry or not entry.get("values"):
            continue
        allowed = _allowed(entry)
        if _PER_SIDE.search(clause) and not entry["flex"]:
            # The text says "per side" where the athlete did not: halving is the only
            # reading that can still be his load, so accept it rather than guess.
            allowed = sorted(set(allowed) | {v / 2 for v in entry["values"]})
        if any(abs(value - ok) < 0.01 for ok in allowed):
            continue
        noted = ", ".join(f"{_kg(v)} kg" for v in sorted(set(entry["values"])))
        problems.append(
            f"charge {_kg(value)} kg attribuée à {family} alors que l'athlète a noté "
            f"{noted} pour cet exercice"
        )
    return problems
