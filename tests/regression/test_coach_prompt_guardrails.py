"""Anti-drift guard: both coach surfaces must carry the same Campus guardrails.

There are two coach prompts, and they are edited independently:

* ``src/agents/embedded_prompts.py`` drives the per-activity pipeline coach.
* ``src/coach_chat/prompts.py`` drives the conversational coach runtime, which
  reaches the same Campus data through its ``get_campus_plan`` tool.

Both are exposed to the same failure mode: the plan contains sessions that share
a title across weeks with different repeat counts and target paces, so a coach
that does not keep weeks apart will quote the wrong week's figures. The pipeline
coach was hardened first and the chat coach was initially missed, which is
exactly the drift this test exists to catch.

Assertions are on intent, matched through several alternative wordings, so
rephrasing a rule does not fail the build while *removing* it does.

No ``parametrize`` here on purpose: ``test_docs_sync._regression_test_count``
derives the suite size by counting test defs and assumes a single parametrized
test in this package. Looping inside the test also lets one failure report every
missing guardrail at once instead of stopping at the first.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

COACH_PROMPTS = {
    "pipeline": REPO_ROOT / "src" / "agents" / "embedded_prompts.py",
    "chat": REPO_ROOT / "src" / "coach_chat" / "prompts.py",
}

# Each guardrail maps to alternative patterns: at least one must be present.
GUARDRAILS = {
    "iso_week_format": [r"YYYY-Www", r"2026-W3\d"],
    "week_disambiguation": [r"semaine ISO", r"week_date_iso"],
    "no_cross_week_transposition": [
        r"transpose[rz]?\s+JAMAIS",
        r"[Nn]e transpose",
        r"aucun rapport avec la séance",
    ],
    "counts_come_from_laps": [r"laps"],
    "planned_vs_actual": [
        r"PRÉVU",
        r"prévu.{0,40}réalisé",
        r"réalisé.{0,40}prévu",
    ],
    "done_sessions_not_recommended": [
        r"done.{0,30}skip",
        r"déjà faite",
        r"terminée",
    ],
    # A rolling 7-day total presented as "this week" made the coach compare
    # 33km of rolling volume against 26.5km of a real ISO week and raise a
    # bogus +32% ramp-rate alert.
    "no_rolling_window_as_week": [
        r"7 jours glissants",
        r"fenêtre glissante",
        r"7 derniers jours",
    ],
}


def _prompt_strings(path: Path) -> str:
    """Concatenate the triple-quoted prompt literals declared in a module.

    Scoped to the literals rather than the raw file so that surrounding Python
    comments, which the model never sees, cannot satisfy or break an assertion.
    """
    text = path.read_text(encoding="utf-8")
    return "\n".join(re.findall(r'"""(.*?)"""', text, flags=re.DOTALL))


class TestCoachPromptGuardrails:
    def test_prompt_literals_are_extracted(self):
        """Guard the guard: an empty extraction would pass every check below."""
        for surface, path in COACH_PROMPTS.items():
            extracted = _prompt_strings(path)
            assert len(extracted) > 200, (
                f"{surface}: extracted only {len(extracted)} chars from "
                f"{path.relative_to(REPO_ROOT)}, the literal regex likely broke"
            )

    def test_both_coach_prompts_carry_every_campus_guardrail(self):
        """The pipeline coach and the chat coach must be hardened together."""
        offenders = []
        for surface, path in COACH_PROMPTS.items():
            prompt = _prompt_strings(path)
            for guardrail, patterns in sorted(GUARDRAILS.items()):
                if not any(re.search(p, prompt) for p in patterns):
                    offenders.append(
                        f"{surface} ({path.relative_to(REPO_ROOT)}): "
                        f"missing '{guardrail}', expected one of {patterns}"
                    )
        assert not offenders, (
            "Both coach prompts must keep weeks apart and derive counts from "
            "laps, otherwise the conversational coach reintroduces the "
            "week-mixing bug:\n" + "\n".join(offenders)
        )
