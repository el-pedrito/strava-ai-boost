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
# "3 courses", "1 run", and ordinals: "5e course en 7 jours" claims a count of 5.
# The ordinal escaped the cardinal-only pattern in production.
_RUN_COUNT = re.compile(
    rf"{_NUM}\s*(?:e|è?me|ère|er)?\s*(?:courses?|runs?|sorties?)\b", re.IGNORECASE
)
# "8 seances totales", "9 seances au total" -- total sessions of the week.
_TOTAL_COUNT = re.compile(
    rf"{_NUM}\s*séances?\s*(?:totales?|au\s+total|en\s+tout)", re.IGNORECASE
)
# Comparison connectors split a sentence into independently-scoped claims:
# "40km cette semaine vs 27km semaine derniere" holds a current-week claim AND a
# past-week claim. Gating on the whole sentence skipped both, and that is exactly
# how a wrong 40km got published. Each segment is now scoped on its own.
_COMPARE_SPLIT = re.compile(
    r"\bvs\.?\b|\bversus\b|\bcontre\b|par\s+rapport\s+[aà]", re.IGNORECASE
)
# "35km", "6,4 km". The trailing guard rejects "17-18km/h": \b fires on the slash, so a
# SPEED was being read as a distance and compared to the weekly total, which would strip
# the sentence describing the workout itself. Scoped to a following h (or the exotic
# "km·h") rather than any slash, so "21,8km / 3 runs" -- a slash used as a separator --
# is still read as a distance.
_KM = re.compile(rf"{_NUM}\s*km\b(?!\s*[/·]\s*h)", re.IGNORECASE)
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

# A claim is only checked when the sentence ties it to THIS week's completed totals.
# Without this, "26.5km la semaine derniere" would be compared against this week.
#
# The gate is an ALLOWLIST on purpose, and stays one. An unrecognised phrasing costs a
# missed check; a wrongly-recognised one strips correct coaching, and this module holds
# the second to be the worse failure. A broad stem match (`semaine|hebdo`) was tried and
# reverted: it admitted "la semaine prochaine tu as 4 courses", "ta moyenne hebdomadaire",
# "Semaine 32 : 4 courses" and a dozen more -- and since recommendation_next is in
# CHECKED_FIELDS, next-week prose is checked by construction, so that direction is not
# theoretical.
#
# What the allowlist must cover, from production: the coach published
# "Contexte hebdo : ... = 3 runs" against a computed 2, one sentence after the verifier
# had stripped that same error phrased "Cette semaine". So the "<noun> hebdo" and
# "hebdo :" shapes are recognised alongside the original four literals.
#
# Later production case: "5 courses en 5 jours (03-07/08) = 27km" against a computed 3.
# The agent dodged every "semaine"/"hebdo" marker by scoping the count to a rolling
# "en N jours" window, which the prompt explicitly forbids. Any "en N jours" or
# "ces N derniers jours" window is therefore recognised: the prompt bans stating such a
# window at all, so comparing it against the ISO-week total is always the right call.
_WEEK_SCOPE = re.compile(
    r"cette\s+semaine"
    r"|semaine\s+en\s+cours"
    r"|sur\s+la\s+semaine"
    r"|(?:ta|ma|sa)\s+semaine"
    r"|(?:contexte|bilan|r[eé]cap\w*|total|volume|charge|cumul)\s+hebdo\w*"
    r"|hebdo\w*\s*:"
    r"|en\s+\d+\s+jours?"
    r"|ces\s+\d+\s+derniers?\s+jours?",
    re.IGNORECASE,
)

# A qualifier can turn a current-week phrasing into something else entirely, so these
# are vetoed before the allowlist is consulted:
#   plan      "la semaine prochaine tu as 4 courses au programme"
#   habit     "ta charge hebdo HABITUELLE", "ta moyenne hebdo", "une semaine TYPE",
#             "en semaine", "4 fois PAR semaine", "35km/semaine"
#   other wk  "Semaine 32 :", "la semaine DU 27/07", "il y a une semaine"
#   part wk   "en FIN DE semaine"
#   multi-wk  "sur ces 3 semaineS" (the plural also defeats \bhebdo on its own)
# Each entry here was a measured false positive, not a hypothetical.
_NOT_CURRENT_WEEK = re.compile(
    r"habituel\w*|moyenne|typique|semaine\s+type|d'habitude"
    r"|semaine\s+(?:prochaine|derni[eè]re|pr[eé]c[eé]dente|du\b|\d)"
    r"|(?:prochaine|derni[eè]re|pr[eé]c[eé]dente)\s+semaine"
    r"|il\s+y\s+a\s+(?:une?|\d+)\s+semaines?"
    r"|(?:par|chaque)\s+semaine|/\s*semaine|[àa]\s+la\s+semaine|sur\s+une\s+semaine"
    r"|(?:fin|d[eé]but|milieu)\s+de\s+semaine"
    r"|en\s+semaine"
    r"|semaines"
    r"|au\s+programme",
    re.IGNORECASE,
)

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
    if _NOT_CURRENT_WEEK.search(low):
        return False
    return bool(_WEEK_SCOPE.search(low))


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
    # and only trustworthy when the counts themselves are complete. A "remaining"
    # sentence is excluded too: "il te reste 3 courses cette semaine" counts sessions
    # still TO DO, so comparing it against runs DONE flags a correct sentence -- the
    # same trap already documented below for strength counts.
    #
    # Scoping is done at CLAIM level, not sentence level: the week scope may be
    # stated once for the whole sentence, but a comparison ("40km cette semaine vs
    # 27km semaine derniere") holds claims about two different weeks. Excluding the
    # whole sentence because it mentions the past week let a wrong current-week
    # figure through; only the segment that mentions the past week is skipped.
    low_sentence = sentence.lower()
    sentence_week_scope = bool(_WEEK_SCOPE.search(low_sentence))
    segments = [s for s in _COMPARE_SPLIT.split(sentence) if s and s.strip()]

    def _segment_disqualified(seg: str) -> bool:
        """A segment whose own text scopes it away from this week's totals.

        The disqualifiers (_NOT_CURRENT_WEEK: past weeks, averages, 'par semaine',
        'habituel'...) used to be evaluated on the whole sentence, which let
        '40km cette semaine vs 27km semaine derniere' escape entirely: the past
        marker of the SECOND claim shielded the FIRST one. Each comparison segment
        now answers for itself."""
        return bool(_NOT_CURRENT_WEEK.search(seg.lower())) or _mentions_past_week(seg)

    if sentence_week_scope and not counts_incomplete and not _mentions_remaining(sentence):
        for seg in segments:
            if _segment_disqualified(seg):
                continue
            for m in _RUN_COUNT.finditer(seg):
                compare("run count this week", _to_float(m.group(1)), done.get("runs"))
            for m in _KM.finditer(seg):
                compare("kilometres this week", _to_float(m.group(1)), done.get("run_km"), KM_TOLERANCE)
            for m in _TOTAL_COUNT.finditer(seg):
                compare("total sessions this week", _to_float(m.group(1)), done.get("total"))

    # A strength-session count is a weekly claim even without the marker: the
    # production lie was "2e seance muscu en 2 jours", which names no week.
    # "il reste 2 muscu perso" counts sessions still TO DO, not sessions done. The
    # first version compared it against done_this_week.strength and stripped a
    # correct sentence from a live output. Remaining claims are checked against
    # own_strength_program.remaining instead.
    own = (week_overview or {}).get("own_strength_program") or {}
    # A "muscu"/"renfo" count describes the athlete's OWN program, so it is checked
    # against done['muscu'] (own program only), never done['strength'] (which also
    # includes the Campus PPG). Comparing against strength let "3 muscu" pass on a
    # 2 muscu + 1 PPG week AND would now false-flag a correct "2 muscu".
    muscu_truth = done.get("muscu")
    if muscu_truth is None:
        muscu_truth = done.get("strength")
    if _mentions_remaining(sentence):
        for m in _STRENGTH_COUNT.finditer(sentence):
            compare(
                "remaining own strength sessions",
                _to_float(m.group(1)),
                own.get("remaining"),
            )
    elif not counts_incomplete and muscu_truth is not None:
        for seg in segments:
            if _mentions_past_week(seg):
                continue
            for m in _STRENGTH_COUNT.finditer(seg):
                compare("strength sessions this week", _to_float(m.group(1)), muscu_truth)

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
