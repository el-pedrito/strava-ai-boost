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
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

# Text fields of the coach feedback that reach the athlete.
CHECKED_FIELDS: Tuple[str, ...] = ("strava_block", "detailed_analysis", "recommendation_next")

# Text fields of the CONTENT agent output. Same guards, different producer: the content
# agent had no output check at all, only the offline prompt regression, which is why its
# three errors of 2026-08-14 ("Bloc 1/2", the block 2 announced as remaining, the 44
# minutes compared to a single block) reached Strava untouched.
CONTENT_CHECKED_FIELDS: Tuple[str, ...] = ("title", "description")

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
# The accent is optional, as in _RUN_COUNT and _STRENGTH_COUNT: the deployed coach
# writes both graphies and an accent-only pattern silently skipped the check.
_TOTAL_COUNT = re.compile(
    rf"{_NUM}\s*(?:séances?|seances?)\s*(?:totales?|au\s+total|en\s+tout)", re.IGNORECASE
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


# --- Checks against the facts computed by lots B, C and D -------------------
#
# The prompt names these fields as the sole source. That is necessary and, as this
# module's header already records, not sufficient. Unlike a self-contradiction these
# checks name the wrong half, so they can end in a strip.

# "5 fractions courtes", "6 sprints", "4 efforts"
_EFFORTS_STATED = re.compile(
    rf"{_NUM}\s*(?:fractions?|sprints?|fractionn\w*|efforts?)", re.IGNORECASE
)
_PASSIVE_RECOVERY = re.compile(r"r[eé]cup\w*\s+passives?|passives?\s+r[eé]cup\w*", re.IGNORECASE)
# Words that assert a decline. Only flagged when an exercise is named in the same
# sentence: "ta FC baisse" says nothing about a lift and must survive.
_DECLINE_WORDS = re.compile(
    r"r[eé]gress\w*|recul\w*|flanch\w*|en\s+retrait|moins\s+bien|baisse\w*|chut[eé]\w*",
    re.IGNORECASE,
)
# "Bloc 2", "bloc 1/2", "premier bloc", "prochaine etape : le bloc".
# The last alternative covers the REVERSED order ("Le Bloc 2 ... reste a faire"), which the
# first version missed: it required the incompleteness word before "bloc", so the coach
# published exactly that shape on 2026-08-17 on a session done in full. It demands an
# explicit incompleteness phrase so that merely describing a block ("Bloc 2 : swing 24kg")
# stays untouched.
_REMAINING_BLOCK = re.compile(
    r"bloc\s*\d+\s*/\s*\d+|prochaine?\s+[eé]tape[^.\n]{0,30}bloc|reste[^.\n]{0,20}bloc"
    r"|premier\s+bloc|1er\s+bloc"
    r"|bloc\s*\d+[^.\n]{0,60}(?:reste\s+[aà]\s+faire|[aà]\s+faire|pas\s+encore"
    r"|[aà]\s+compl[eé]ter|pour\s+compl[eé]ter)",
    re.IGNORECASE,
)


# A TOTAL of seconds, in either word order ("328 secondes au total" / "au total 328
# secondes"). Requires an explicit totalling word: a bare duration is one exercise's hold
# ("Gainage Frontal 30 secondes") and must stay untouched. Minutes are excluded on purpose,
# because a total in minutes is the session length, which is checked against moving_time
# rather than against time under load.
_TOTALLING = r"(?:au\s+total|en\s+tout|cumul\w*|au\s+cumul)"
_SECONDS_TOTAL = re.compile(
    rf"(\d{{2,5}})\s*(?:secondes?|sec\b|s\b)[^.\n]{{0,40}}{_TOTALLING}"
    rf"|{_TOTALLING}[^.\n]{{0,40}}?(\d{{2,5}})\s*(?:secondes?|sec\b|s\b)",
    re.IGNORECASE,
)
# The athlete may hold slightly longer than planned, so accept a near match. What is
# rejected is a total matching none of the computed times.
_TIME_TOLERANCE = 0.10


def _check_seconds_total(
    sentence: str,
    computed_facts: Optional[Dict[str, Any]],
) -> List[str]:
    """Reject a stated total of seconds that matches no computed time.

    Closes the last space the facts left open: after the block and load fixes were verified
    live, the agent published "328 secondes au total" for calf work computing to 160 s,
    having silently estimated a seconds-per-rep value for an exercise counted in reps.
    """
    volume = ((computed_facts or {}).get("campus") or {}).get("computed_volume")
    if not isinstance(volume, dict):
        return []
    # NOT _to_float here: that helper parses TEXT and returns None on a real float
    # (_to_float(160.0) is None), which silently emptied the admissible list and made this
    # whole check a no-op. Numbers coming from the computed facts are already numbers.
    def _number(raw: Any) -> Optional[float]:
        if isinstance(raw, bool) or not isinstance(raw, (int, float, Decimal)):
            return None
        value = float(raw)
        return value if value > 0 else None

    loaded = _number(volume.get("time_under_load_s"))
    bodyweight = _number(volume.get("bodyweight_time_s"))
    admissible = [v for v in (loaded, bodyweight) if v]
    if loaded and bodyweight:
        admissible.append(loaded + bodyweight)
    if not admissible:
        return []

    for match in _SECONDS_TOTAL.finditer(sentence):
        stated = _to_float(match.group(1) or match.group(2))
        if stated is None or stated <= 0:
            continue
        if any(abs(stated - ok) <= max(ok * _TIME_TOLERANCE, 1.0) for ok in admissible):
            continue
        expected = " or ".join(f"{v:g}" for v in sorted(set(admissible)))
        return [
            f"time total: the text states {stated:g} s, the computed times are {expected} s"
        ]
    return []


def _check_against_facts(
    sentence: str,
    computed_facts: Optional[Dict[str, Any]],
) -> List[str]:
    """Return the mismatches between one sentence and the computed facts."""
    problems: List[str] = []
    if not isinstance(computed_facts, dict):
        return problems

    lap_facts = computed_facts.get("lap_facts")
    if isinstance(lap_facts, dict):
        work = lap_facts.get("work_reps")
        if isinstance(work, dict):
            truth = work.get("count")
            if isinstance(truth, (int, float)) and truth > 0:
                for match in _EFFORTS_STATED.finditer(sentence):
                    stated = _to_float(match.group(1))
                    if stated is not None and int(stated) != int(truth):
                        problems.append(
                            f"effort count: the text says {stated:g}, the laps hold {int(truth)}"
                        )
                        break
        recovery = lap_facts.get("recovery")
        if isinstance(recovery, dict) and recovery.get("mode") == "active":
            if _PASSIVE_RECOVERY.search(sentence):
                distances = recovery.get("distances_m") or []
                covered = f", {min(distances)} to {max(distances)} m covered" if distances else ""
                problems.append(
                    f"recovery mode: the text says passive, the laps say active{covered}"
                )

    comparisons = computed_facts.get("exercise_comparisons")
    if isinstance(comparisons, list) and _DECLINE_WORDS.search(sentence):
        low = sentence.lower()
        for comparison in comparisons:
            if not isinstance(comparison, dict):
                continue
            name = str(comparison.get("exercise") or "")
            if not name:
                continue
            # Match on the first significant word of the exercise, so "developpe couche"
            # is found however the coach spells the rest.
            head = _normalize_plain(name).split()
            if not head or head[0] not in _normalize_plain(low):
                continue
            classification = comparison.get("classification")
            if classification and classification != "regression":
                problems.append(
                    f"progression direction: the text states a decline on '{name}' "
                    f"while the computed classification is '{classification}'"
                )
                break

    campus = computed_facts.get("campus")
    if isinstance(campus, dict) and campus.get("fully_completed") is True:
        if _REMAINING_BLOCK.search(sentence):
            problems.append(
                "session completeness: the text presents a block as remaining or partial "
                "while the session was completed in full"
            )

    problems.extend(_check_seconds_total(sentence, computed_facts))

    return problems


def _normalize_plain(value: str) -> str:
    text = (value or "").lower()
    for accented, plain in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ô", "o")):
        text = text.replace(accented, plain)
    return text


def verify_weekly_claims(
    feedback: Optional[Dict[str, Any]],
    week_overview: Optional[Dict[str, Any]],
    strength_session: Optional[Dict[str, Any]] = None,
    computed_facts: Optional[Dict[str, Any]] = None,
    fields: Optional[Tuple[str, ...]] = None,
) -> List[str]:
    """List the figures stated in the feedback that contradict the computed ones.

    An empty list means every checked figure agrees, or that no checkable figure was
    stated. This never raises: a verifier that breaks the pipeline is worse than an
    unverified sentence.
    """
    problems: List[str] = []
    if not isinstance(feedback, dict):
        return problems

    for field in fields or CHECKED_FIELDS:
        text = feedback.get(field)
        if not isinstance(text, str) or not text:
            continue
        for sentence in split_sentences(text):
            for problem in _check_sentence(sentence, week_overview, strength_session):
                problems.append(f"{field}: {problem}")
            for problem in _check_against_facts(sentence, computed_facts):
                problems.append(f"{field}: {problem}")
    return problems


def strip_false_claims(
    feedback: Dict[str, Any],
    week_overview: Optional[Dict[str, Any]],
    strength_session: Optional[Dict[str, Any]] = None,
    computed_facts: Optional[Dict[str, Any]] = None,
    fields: Optional[Tuple[str, ...]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Remove the sentences carrying a contradicted figure.

    Last resort, used only when a regeneration has already failed. Removing one
    sentence costs a line of narrative; publishing a wrong count costs the trust in
    every other figure the coach states.

    Returns the cleaned feedback and the sentences that were removed.
    """
    removed: List[str] = []
    cleaned = dict(feedback)

    for field in fields or CHECKED_FIELDS:
        text = cleaned.get(field)
        if not isinstance(text, str) or not text:
            continue
        kept: List[str] = []
        for sentence in split_sentences(text):
            if _check_sentence(sentence, week_overview, strength_session) or _check_against_facts(
                sentence, computed_facts
            ):
                removed.append(sentence.strip())
            else:
                kept.append(sentence.strip())
        cleaned[field] = " ".join(kept).strip()

    return cleaned, removed


# ---------------------------------------------------------------------------
# Internal consistency
# ---------------------------------------------------------------------------
#
# The checks above compare the text to a computed figure. These compare the text to
# ITSELF, and that is the point: on 2026-08-14, 15 and 16 the pipeline published six
# statements that needed no data at all to be refuted, because the same feedback said
# the opposite a few lines away ("5 fractions courtes" next to "2 blocs de
# (35-25-15sec)", "2e Upper" next to "apres la PPG").
#
# Two deliberate limits:
#   * A self-contradiction does not say WHICH half is wrong, so these problems drive a
#     regeneration and are never fed to strip_false_claims. Removing the correct half
#     would be worse than publishing both.
#   * Every detector abstains rather than guesses. A range like "(15-35sec)" is not a
#     three-value block pattern, an unrecognised session word is not a session type,
#     and no reference date means no date claim.

_EFFORT_COUNT = re.compile(
    rf"{_NUM}\s*(?:fractions?|sprints?|fractionn\w*|efforts?)", re.IGNORECASE
)
# "2 blocs de sprints (35-25-15sec)": the parenthesis carries the per-block pattern.
_BLOCK_PATTERN = re.compile(rf"{_NUM}\s*blocs?[^(\n]{{0,40}}\(([^)]*)\)", re.IGNORECASE)

# Words that name a KIND of session. "seance"/"session" are excluded on purpose:
# "2e seance du jour apres la PPG" is correct and must not be flagged, only the
# specific "2e Upper ... apres la PPG" is.
_SESSION_TYPES = (
    "upper", "lower", "ppg", "muscu", "renfo", "course", "run", "sortie", "fractionne",
)
_ORDINAL_TYPE = re.compile(r"(\d+)\s*(?:e|[eè]?me)\s+([A-Za-zÀ-ÿ']+)", re.IGNORECASE)
_AFTER_TYPE = re.compile(
    r"apr[eè]s\s+(?:la\s+|le\s+|l'|les\s+)?([A-Za-zÀ-ÿ']+)", re.IGNORECASE
)

# "tes 2 muscu de la semaine (PPG Campus + cet Upper)" glosses a muscu count with an
# enumeration that includes the PPG, while the same feedback counts the PPG apart.
_MUSCU_ENUM = re.compile(rf"{_NUM}\s*muscu\w*[^(\n]{{0,40}}\(([^)]*)\)", re.IGNORECASE)
_PPG_COUNT = re.compile(rf"{_NUM}\s*ppg\b", re.IGNORECASE)

_REL_DAY = re.compile(
    r"\b(avant-hier|hier|aujourd'hui|demain)\b[^(\n]{0,25}\((\d{1,2})/(\d{1,2})\)",
    re.IGNORECASE,
)
_REL_DAY_OFFSET = {"avant-hier": -2, "hier": -1, "aujourd'hui": 0, "demain": 1}

_REST_HOURS = re.compile(
    rf"{_NUM}\s*h(?:eures?)?\s*(?:de\s*)?(?:r[eé]cup\w*|repos)", re.IGNORECASE
)
_END_OF_WEEK = re.compile(
    r"termine[rz]?\s+la\s+semaine|finir\s+la\s+semaine|boucler\s+la\s+semaine"
    r"|d'ici\s+dimanche",
    re.IGNORECASE,
)


def _normalize_type(word: str) -> str:
    low = (word or "").strip().strip("'").lower()
    for accented, plain in (("é", "e"), ("è", "e"), ("ê", "e")):
        low = low.replace(accented, plain)
    for known in _SESSION_TYPES:
        if low.startswith(known):
            return known
    return ""


def _parse_reference_date(activity_date: Optional[str]):
    if not activity_date or not isinstance(activity_date, str):
        return None
    try:
        return datetime.strptime(activity_date[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _check_effort_count(document: str) -> List[str]:
    """Compare a stated number of efforts to the block structure stated alongside."""
    problems: List[str] = []
    expected = None
    for match in _BLOCK_PATTERN.finditer(document):
        blocks = _to_float(match.group(1))
        values = re.findall(r"\d+", match.group(2) or "")
        # Two values are a range ("15-35sec"), not a per-block pattern.
        if blocks and len(values) >= 3:
            expected = int(blocks) * len(values)
            break
    if expected is None:
        return problems
    for match in _EFFORT_COUNT.finditer(document):
        stated = _to_float(match.group(1))
        if stated is not None and int(stated) != expected:
            problems.append(
                f"effort count: the text says {stated:g} efforts, the block structure "
                f"stated alongside gives {expected}"
            )
            break
    return problems


def _check_ordinal_type(sentence: str) -> List[str]:
    """'2e Upper ... apres la PPG' names a different type for the earlier session."""
    problems: List[str] = []
    after = _AFTER_TYPE.search(sentence)
    if not after:
        return problems
    previous = _normalize_type(after.group(1))
    if not previous:
        return problems
    for match in _ORDINAL_TYPE.finditer(sentence):
        rank = _to_float(match.group(1))
        current = _normalize_type(match.group(2))
        if not current or rank is None or rank < 2:
            continue
        if current != previous:
            problems.append(
                f"session ordinal: '{int(rank)}e {match.group(2)}' contradicts the "
                f"earlier session being a {previous}"
            )
            break
    return problems


def _check_taxonomy_enumeration(document: str) -> List[str]:
    """A muscu count glossed with an enumeration that includes the PPG."""
    problems: List[str] = []
    if not _PPG_COUNT.search(document):
        return problems
    for match in _MUSCU_ENUM.finditer(document):
        enumeration = (match.group(2) or "").lower()
        if "ppg" in enumeration:
            problems.append(
                "taxonomy: the PPG is counted apart from the muscu sessions elsewhere, "
                f"but listed inside them here ('{match.group(0).strip()}')"
            )
            break
    return problems


def _check_relative_day(sentence: str, activity_date: Optional[str]) -> List[str]:
    """'hier (11/08)' on a 14/08 activity names a day three days back."""
    problems: List[str] = []
    reference = _parse_reference_date(activity_date)
    if reference is None:
        return problems
    for match in _REL_DAY.finditer(sentence):
        word = match.group(1).lower()
        offset = _REL_DAY_OFFSET.get(word)
        if offset is None:
            continue
        try:
            day, month = int(match.group(2)), int(match.group(3))
        except (TypeError, ValueError):
            continue
        year = reference.year
        if month == 12 and reference.month == 1:
            year -= 1
        try:
            stated = date(year, month, day)
        except ValueError:
            continue
        if stated != reference + timedelta(days=offset):
            problems.append(
                f"relative day: '{word}' points to "
                f"{(reference + timedelta(days=offset)).strftime('%d/%m')} but the text "
                f"names {stated.strftime('%d/%m')}"
            )
            break
    return problems


def _check_rest_window(document: str, activity_date: Optional[str]) -> List[str]:
    """A rest window that cannot fit before the week the text says to finish."""
    problems: List[str] = []
    reference = _parse_reference_date(activity_date)
    if reference is None or not _END_OF_WEEK.search(document):
        return problems
    end_of_week = reference + timedelta(days=7 - reference.isoweekday())
    for match in _REST_HOURS.finditer(document):
        hours = _to_float(match.group(1))
        if hours is None:
            continue
        resume = reference + timedelta(hours=hours)
        if resume > end_of_week:
            problems.append(
                f"rest window: {hours:g}h of rest from "
                f"{reference.strftime('%d/%m')} resumes {resume.strftime('%d/%m')}, "
                f"after the week ends {end_of_week.strftime('%d/%m')}"
            )
            break
    return problems


def find_internal_contradictions(
    feedback: Optional[Dict[str, Any]],
    activity_date: Optional[str] = None,
    fields: Optional[Tuple[str, ...]] = None,
) -> List[str]:
    """List the statements the text contradicts on its own.

    Needs no computed figure. ``activity_date`` (``YYYY-MM-DD``) unlocks the two
    date-dependent checks; without it they stay silent rather than guess.

    Never raises: a verifier that breaks the pipeline is worse than an unverified
    sentence.
    """
    problems: List[str] = []
    if not isinstance(feedback, dict):
        return problems

    texts = [
        (field, feedback.get(field))
        for field in (fields or CHECKED_FIELDS)
        if isinstance(feedback.get(field), str) and feedback.get(field)
    ]
    if not texts:
        return problems

    document = "\n".join(text for _, text in texts)
    problems.extend(_check_effort_count(document))
    problems.extend(_check_taxonomy_enumeration(document))
    problems.extend(_check_rest_window(document, activity_date))

    for field, text in texts:
        for sentence in split_sentences(text):
            for problem in _check_ordinal_type(sentence):
                problems.append(f"{field}: {problem}")
            for problem in _check_relative_day(sentence, activity_date):
                problems.append(f"{field}: {problem}")

    return problems
