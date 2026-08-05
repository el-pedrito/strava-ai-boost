"""Verify the figures the coach states against the figures the code computed.

Why this exists
---------------
Every weekly number left to the model was wrong in production, and every number
moved into code was right. The numbers are now computed in code, labelled, and the
prompt names them as the sole source. That fixed the cases where the model was
reading the wrong field.

It did not fix the last case: the model sometimes states a figure that exists in no
field at all. It reported "2e seance muscu en 2 jours (Upper B le 03/08)" when the
03/08 was a run, and contradicted itself three lines above. It reported "320 reps
au total" for a session of 238, wrapped in an invented "fun fact", when nothing
asked for a rep total. The value changed on every run, which is the signature of
fabrication rather than of a misread field.

No data fix and no prompt rule can remove that: there is no ambiguity left to
remove. So the output is checked against the computed figures before publication.

Design choices
--------------
* **Targeted, not general.** The patterns cover the claims that actually lied in
  production. A general-purpose numeric NLP checker would be far more code and far
  more false positives for no proven benefit. When the metric shows a new shape of
  lie, add that shape.
* **Never blocking.** A late coach beats no coach. The caller regenerates once, then
  falls back to removing the offending sentence, then publishes.
* **Removing a sentence beats publishing a false figure.** Dropping one claim costs
  the athlete a line of narrative; publishing a wrong count costs the trust in every
  other figure.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Text fields of the coach feedback that reach the athlete.
CHECKED_FIELDS: Tuple[str, ...] = ("strava_block", "detailed_analysis", "recommendation_next")

# Tolerance on kilometres: the coach may round 6.42 to 6.4 legitimately.
KM_TOLERANCE = 0.15

_NUM = r"(\d+(?:[.,]\d+)?)"

# "2 seances muscu", "2e seance de muscu", "4e muscu"
_STRENGTH_COUNT = re.compile(
    rf"{_NUM}\s*(?:e|è?me|ère|er)?\s*(?:séances?|seances?)?\s*(?:de\s+)?"
    r"(?:muscu\w*|renfo\w*)",
    re.IGNORECASE,
)
# "3 courses", "1 run"
_RUN_COUNT = re.compile(rf"{_NUM}\s*(?:courses?|runs?|sorties?)\b", re.IGNORECASE)
# "35km", "6,4 km"
_KM = re.compile(rf"{_NUM}\s*km\b", re.IGNORECASE)
# "il te reste 2", "il reste 4 seances"
_REMAINING = re.compile(rf"il\s+(?:te\s+)?reste\s+{_NUM}", re.IGNORECASE)
# "320 reps", "238 repetitions"
_REPS = re.compile(rf"{_NUM}\s*(?:reps?|répétitions?|repetitions?)\b", re.IGNORECASE)
# "25 series"
_SETS = re.compile(rf"{_NUM}\s*(?:séries?|series?)\b", re.IGNORECASE)
# Tonnage: "15370 kg soulevés", "15,4 tonnes"
_TONNAGE = re.compile(
    rf"{_NUM}\s*(?:kg|kilos?)\s*(?:au total|soulev|de volume)|{_NUM}\s*tonnes?",
    re.IGNORECASE,
)

# A claim is only checked when the sentence ties it to the current week. Without
# this, "26.5km la semaine derniere" would be compared against this week's total.
_CURRENT_WEEK_MARKERS = ("cette semaine", "sur la semaine", "ta semaine", "la semaine en cours")

# A sentence that names a PAST week is reporting weekly_breakdown, which legitimately
# holds other figures. Checking it against this week's counts produced a false
# positive on "La semaine derniere : 4 courses (26.5km), 2 muscu" -- correct text that
# would have been stripped. A verifier that flags correct sentences is worse than none:
# it removes good narrative and teaches the reader to ignore the warnings.
_PAST_WEEK_MARKERS = (
    "semaine derniere",
    "semaine dernière",
    "semaine precedente",
    "semaine précédente",
    "il y a 2 semaines",
    "il y a 3 semaines",
    "il y a 4 semaines",
    "les semaines precedentes",
    "les semaines précédentes",
)


def _to_float(raw: str) -> Optional[float]:
    try:
        return float(raw.replace(",", "."))
    except (ValueError, AttributeError):
        return None


def split_sentences(text: str) -> List[str]:
    """Split on sentence boundaries, keeping newline-separated fragments apart."""
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p for p in parts if p and p.strip()]


def _mentions_current_week(sentence: str) -> bool:
    low = sentence.lower()
    if _mentions_past_week(sentence):
        return False
    return any(marker in low for marker in _CURRENT_WEEK_MARKERS)


def _is_advisory(sentence: str) -> bool:
    """True when the sentence gives advice rather than stating a fact.

    "evite 2 seances muscu consecutives" carries a number but claims nothing about
    the week. The first version stripped exactly that sentence from a live output,
    removing useful coaching. Only factual claims are verifiable.
    """
    low = sentence.lower()
    return any(
        marker in low
        for marker in (
            "évite", "evite", "alterne", "essaie", "privilégie", "privilegie",
            "ne fais pas", "n'enchaîne", "n'enchaine", "limite-toi", "vise ",
            "pense à", "pense a", "garde ", "laisse ",
        )
    )


def _mentions_remaining(sentence: str) -> bool:
    """True when the sentence talks about sessions still to do, not sessions done."""
    low = sentence.lower()
    return any(
        marker in low
        for marker in ("il reste", "il te reste", "reste ", "a faire", "à faire", "restantes")
    )


def _mentions_past_week(sentence: str) -> bool:
    """True when the sentence explicitly scopes itself to an earlier week."""
    low = sentence.lower()
    return any(marker in low for marker in _PAST_WEEK_MARKERS)


def _check_sentence(
    sentence: str,
    week_overview: Optional[Dict[str, Any]],
    strength_session: Optional[Dict[str, Any]],
) -> List[str]:
    """Return the mismatches found in one sentence."""
    problems: List[str] = []
    if _is_advisory(sentence):
        return problems
    done = (week_overview or {}).get("done_this_week") or {}
    remaining = (week_overview or {}).get("campus_remaining") or {}
    counts_incomplete = bool((week_overview or {}).get("counts_incomplete"))

    def compare(label: str, claimed: Optional[float], truth: Any, tol: float = 0.0) -> None:
        if claimed is None or truth is None:
            return
        try:
            real = float(truth)
        except (TypeError, ValueError):
            return
        if abs(claimed - real) > tol:
            problems.append(
                f"{label}: the text says {claimed:g}, the computed figure is {real:g}"
            )

    # Weekly claims are only meaningful when the sentence scopes them to this week,
    # and only trustworthy when the counts themselves are complete.
    if _mentions_current_week(sentence) and not counts_incomplete:
        for m in _RUN_COUNT.finditer(sentence):
            compare("run count this week", _to_float(m.group(1)), done.get("runs"))
        for m in _KM.finditer(sentence):
            compare("kilometres this week", _to_float(m.group(1)), done.get("run_km"), KM_TOLERANCE)

    # A strength-session count is a weekly claim even without the marker: the
    # production lie was "2e seance muscu en 2 jours", which names no week.
    # "il reste 2 muscu perso" counts sessions still TO DO, not sessions done. The
    # first version compared it against done_this_week.strength and stripped a
    # correct sentence from a live output. Remaining claims are checked against
    # own_strength_program.remaining instead.
    own = (week_overview or {}).get("own_strength_program") or {}
    if _mentions_remaining(sentence):
        for m in _STRENGTH_COUNT.finditer(sentence):
            compare(
                "remaining own strength sessions",
                _to_float(m.group(1)),
                own.get("remaining"),
            )
    elif not counts_incomplete and done.get("strength") is not None and not _mentions_past_week(sentence):
        for m in _STRENGTH_COUNT.finditer(sentence):
            compare("strength sessions this week", _to_float(m.group(1)), done.get("strength"))

    for m in _REMAINING.finditer(sentence):
        compare("remaining plan sessions", _to_float(m.group(1)), remaining.get("count"))

    if strength_session:
        for m in _REPS.finditer(sentence):
            compare("total reps", _to_float(m.group(1)), strength_session.get("total_reps"))
        for m in _SETS.finditer(sentence):
            compare("total sets", _to_float(m.group(1)), strength_session.get("total_sets"))
        # Tonnage is only checked when the computed one is complete: a partial
        # tonnage legitimately differs from any number the coach could state.
        if not strength_session.get("volume_kg_incomplete"):
            for m in _TONNAGE.finditer(sentence):
                raw = m.group(1) or m.group(2)
                claimed = _to_float(raw) if raw else None
                if claimed is not None and "tonne" in m.group(0).lower():
                    claimed *= 1000
                compare("tonnage", claimed, strength_session.get("volume_kg"), 50.0)

    return problems


def verify_weekly_claims(
    feedback: Optional[Dict[str, Any]],
    week_overview: Optional[Dict[str, Any]],
    strength_session: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """List the figures stated in the feedback that contradict the computed ones.

    An empty list means every checked figure agrees, or that no checkable figure was
    stated. This never raises: a verifier that breaks the pipeline is worse than an
    unverified sentence.
    """
    problems: List[str] = []
    if not isinstance(feedback, dict):
        return problems

    for field in CHECKED_FIELDS:
        text = feedback.get(field)
        if not isinstance(text, str) or not text:
            continue
        for sentence in split_sentences(text):
            for problem in _check_sentence(sentence, week_overview, strength_session):
                problems.append(f"{field}: {problem}")
    return problems


def strip_false_claims(
    feedback: Dict[str, Any],
    week_overview: Optional[Dict[str, Any]],
    strength_session: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Remove the sentences carrying a contradicted figure.

    Last resort, used only when a regeneration has already failed. Removing one
    sentence costs a line of narrative; publishing a wrong count costs the trust in
    every other figure the coach states.

    Returns the cleaned feedback and the sentences that were removed.
    """
    removed: List[str] = []
    cleaned = dict(feedback)

    for field in CHECKED_FIELDS:
        text = cleaned.get(field)
        if not isinstance(text, str) or not text:
            continue
        kept: List[str] = []
        for sentence in split_sentences(text):
            if _check_sentence(sentence, week_overview, strength_session):
                removed.append(sentence.strip())
            else:
                kept.append(sentence.strip())
        cleaned[field] = " ".join(kept).strip()

    return cleaned, removed
