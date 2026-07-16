"""Deterministic evaluators for prompt regression testing.

Pure functions over generated content (title/description). No AWS, no LLM.
See docs/design/regression-evals.md.

BANNED_CLICHES must stay in sync with the "Expressions bannies" section of
src/agents/embedded_prompts.py — enforced by a unit test (each entry must
appear verbatim, after normalization, in the prompt source). Do NOT rebuild
the prompt from this list: the prompt text is the source of truth.
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional

# Core stems of the banned expressions (substring match after normalization).
# Shorter stems intentionally catch the prompt's variants
# (e.g. "la machine" catches "la machine est lancée" / "machine bien huilée").
BANNED_CLICHES: List[str] = [
    "le corps se réveille",
    "corps s'est réveillé",
    "la machine",
    "machine bien huilée",
    "les jambes se sont libérées",
    "les jambes se délient",
    "rythme de croisière",
    "le moteur tourne",
    "moteur qui ronronne",
    "fusée sur pattes",
    "les kilomètres défilent",
    "le corps répond présent",
    "chaque foulée trouvait naturellement son rythme",
    "comme une horloge suisse",
    "le pilote automatique",
    "les sensations étaient au rendez-vous",
    "tout tournait rond",
]

GENERIC_TITLES: List[str] = [
    "course à pied",
    "course a pied le matin",
    "morning run",
    "afternoon run",
    "evening run",
    "lunch run",
    "activity",
    "workout",
    "entraînement",
    "séance de sport",
    "sortie vélo",
    "ride",
    "run",
]

_FR_STOPWORDS = {
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "à",
    "pour", "avec", "sur", "dans", "pas", "plus", "mais", "c'est",
    "j'ai", "je", "au", "aux", "ça", "cette", "bien", "tout",
}
_EN_STOPWORDS = {
    "the", "and", "of", "with", "was", "this", "that", "for", "but",
    "have", "had", "not", "are", "you", "your", "from", "it's",
}

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001FAFF"
    "\u2600-\u27BF"
    "\u2B00-\u2BFF"
    "\uFE0F"
    "]",
    flags=re.UNICODE,
)

_EMOJI_POLICY_MAX = {
    "none": 0,
    "minimal": 2,
    "moderate": 5,
    "enthusiastic": 99,
}


def normalize(text: str) -> str:
    """Lowercase, strip accents, unify apostrophes — for robust matching."""
    text = text.lower().replace("\u2019", "'")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _result(criterion: str, severity: str, passed: bool, detail: str = "") -> Dict[str, Any]:
    return {"criterion": criterion, "severity": severity, "passed": passed, "detail": detail}


def check_banned_cliches(text: str) -> Dict[str, Any]:
    """fail — none of the banned gen-AI sport clichés may appear."""
    norm = normalize(text)
    hits = [c for c in BANNED_CLICHES if normalize(c) in norm]
    return _result(
        "no_banned_cliche", "fail", not hits,
        f"found: {hits}" if hits else "",
    )


def check_forbidden_dashes(text: str) -> Dict[str, Any]:
    """warn — raw LLM output should avoid em/en dashes (code strip is a safety net)."""
    count = text.count("\u2014") + text.count("\u2013")
    return _result(
        "no_forbidden_dashes", "warn", count == 0,
        f"{count} em/en dash(es) in raw output" if count else "",
    )


def check_spaced_hyphen(text: str) -> Dict[str, Any]:
    """warn — no ' - ' clause separator (list bullets at line start are fine)."""
    hits = [m.start() for m in re.finditer(r"(?<!\n)(?<!^) - ", text)]
    return _result(
        "no_spaced_hyphen", "warn", not hits,
        f"{len(hits)} spaced hyphen(s)" if hits else "",
    )


def check_length(description: str, max_chars: int) -> Dict[str, Any]:
    """fail — description must stay within the fixture's length budget."""
    return _result(
        "length_within_pref", "fail", len(description) <= max_chars,
        f"{len(description)} chars > {max_chars}" if len(description) > max_chars else f"{len(description)} chars",
    )


def check_emoji_policy(text: str, policy: str) -> Dict[str, Any]:
    """warn — emoji count must respect the fixture's preference."""
    max_allowed = _EMOJI_POLICY_MAX.get(policy, 99)
    count = len(_EMOJI_RE.findall(text))
    return _result(
        "emoji_policy", "warn", count <= max_allowed,
        f"{count} emojis (policy {policy} allows {max_allowed})",
    )


def check_parsed_ok(title: Optional[str], description: Optional[str]) -> Dict[str, Any]:
    """fail — agent output must parse into non-empty title and description."""
    ok = bool(title and title.strip()) and bool(description and description.strip())
    return _result(
        "json_parseable", "fail", ok,
        "" if ok else f"title={bool(title)}, description={bool(description)}",
    )


def check_title_not_generic(title: str) -> Dict[str, Any]:
    """warn — title must not be a generic Strava default."""
    norm = normalize(title.strip())
    generic = any(norm == normalize(g) for g in GENERIC_TITLES)
    return _result(
        "title_not_generic", "warn", not generic,
        f"generic title: {title!r}" if generic else "",
    )


def check_language(text: str, language: str) -> Dict[str, Any]:
    """fail — simple stopword heuristic; only meaningful for fr fixtures."""
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿ']+", normalize(text))
    fr = sum(1 for w in words if w in {normalize(s) for s in _FR_STOPWORDS})
    en = sum(1 for w in words if w in _EN_STOPWORDS)
    if language == "fr":
        passed = fr > en
        detail = f"fr_stopwords={fr}, en_stopwords={en}"
    else:
        passed = True
        detail = f"language {language}: not checked"
    return _result("language_is_french", "fail", passed, detail)


def evaluate_output(
    title: Optional[str],
    description: Optional[str],
    eval_config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Run all criteria for one fixture output. Returns a list of result dicts."""
    results = [check_parsed_ok(title, description)]
    if not results[0]["passed"]:
        return results

    full_text = f"{title}\n{description}"
    results.extend([
        check_banned_cliches(full_text),
        check_forbidden_dashes(full_text),
        check_spaced_hyphen(full_text),
        check_length(description or "", int(eval_config.get("max_chars", 2800))),
        check_emoji_policy(full_text, eval_config.get("emoji_policy", "moderate")),
        check_title_not_generic(title or ""),
        check_language(full_text, eval_config.get("language", "fr")),
    ])
    return results
