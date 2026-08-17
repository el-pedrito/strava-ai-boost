"""Tests for the content agent guard: verify, regenerate once, strip as a last resort.

Same order of recourse as the coach branch, for the same reason: a regenerated text is
whole, a stripped one is amputated. Strip is what remains when regeneration also fails,
because publishing a false figure is still the worst outcome.

The fixture is the description the content agent actually published on 2026-08-14 for the
Renfo Campus session, with its three errors ("Bloc 1/2", the block 2 announced as the next
step, and the 44 minutes compared against the whole session's 30).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from processing.content_guard import apply_content_guard  # noqa: E402

# The Campus session was performed IN FULL: two blocks of four rounds each.
RENFO_MODULES = [
    {
        "name": "campus_coach",
        "matched_session": {
            "title": "Renforcement",
            "expected_duration_min": 30,
            "intervals": [
                {
                    "type": "block",
                    "repeat": 4,
                    "exercises": [
                        {"type": "work", "name": "Fente", "reps": 8},
                        {"type": "work", "name": "Gainage frontal", "duration": 30},
                        {"type": "work", "name": "Mollet", "reps": 12},
                    ],
                },
                {
                    "type": "block",
                    "repeat": 4,
                    "exercises": [
                        {"type": "work", "name": "Gainage lateral", "duration": 30},
                        {"type": "work", "name": "Mollet statique", "duration": 30},
                    ],
                },
            ],
        },
    }
]
RENFO_ACTIVITY = {"moving_time": 2640, "start_date_local": "2026-08-14T18:12:00Z"}

FALSE_CONTENT = {
    "title": "Renfo Campus, bloc 1",
    "description": (
        "Seance Campus Coach : Renforcement (Bloc 1/2). "
        "44 minutes au total pour ce premier bloc, bien au-dela des 30 minutes prevues. "
        "Prochaine etape : le Bloc 2 avec gainage lateral et mollet statique."
    ),
}
TRUE_CONTENT = {
    "title": "Renfo Campus complet",
    "description": (
        "Seance Campus Coach : Renforcement, les deux blocs boucles. "
        "44 minutes pour 24 series, au-dela des 30 minutes prevues."
    ),
}


class TestCorrectContentIsLeftAlone:
    def test_no_problem_and_no_regeneration(self):
        calls = []

        def regenerate(problems):
            calls.append(problems)
            return None

        content, problems, removed = apply_content_guard(
            TRUE_CONTENT, RENFO_ACTIVITY, None, RENFO_MODULES, regenerate
        )
        assert problems == []
        assert removed == []
        assert calls == [], "a correct text must never cost a second LLM call"
        assert content == TRUE_CONTENT


class TestRegenerationIsTriedFirst:
    def test_the_problems_are_handed_to_the_regeneration(self):
        calls = []

        def regenerate(problems):
            calls.append(problems)
            return TRUE_CONTENT

        apply_content_guard(
            FALSE_CONTENT, RENFO_ACTIVITY, None, RENFO_MODULES, regenerate
        )
        assert len(calls) == 1
        assert any("session completeness" in p for p in calls[0]), calls

    def test_a_corrected_regeneration_is_kept_whole(self):
        content, problems, removed = apply_content_guard(
            FALSE_CONTENT, RENFO_ACTIVITY, None, RENFO_MODULES, lambda _p: TRUE_CONTENT
        )
        assert content == TRUE_CONTENT
        assert problems == []
        assert removed == [], "nothing may be stripped when regeneration succeeded"

    def test_regeneration_is_tried_only_once(self):
        calls = []

        def regenerate(problems):
            calls.append(problems)
            return FALSE_CONTENT

        apply_content_guard(
            FALSE_CONTENT, RENFO_ACTIVITY, None, RENFO_MODULES, regenerate
        )
        assert len(calls) == 1, "one retry, never a loop on the athlete's activity"


class TestStripIsTheLastResort:
    # A description carrying one false sentence among several: the realistic case, and the
    # only one where a strip actually repairs anything.
    MIXED_CONTENT = {
        "title": "Renfo Campus",
        "description": (
            "Seance Campus Coach : Renforcement (Bloc 1/2). "
            "44 minutes a 119bpm de moyenne, du travail propre."
        ),
    }

    def test_a_still_false_regeneration_is_stripped(self):
        content, problems, removed = apply_content_guard(
            FALSE_CONTENT, RENFO_ACTIVITY, None, RENFO_MODULES, lambda _p: self.MIXED_CONTENT
        )
        assert removed, "the contradicted sentence must be gone"
        assert "Bloc 1/2" not in content["description"]
        assert "119bpm" in content["description"]
        assert problems

    def test_a_failed_regeneration_strips_the_original(self):
        content, problems, removed = apply_content_guard(
            self.MIXED_CONTENT, RENFO_ACTIVITY, None, RENFO_MODULES, lambda _p: None
        )
        assert removed
        assert "Bloc 1/2" not in content["description"]

    def test_the_correct_sentence_survives_the_strip(self):
        content, _problems, removed = apply_content_guard(
            self.MIXED_CONTENT, RENFO_ACTIVITY, None, RENFO_MODULES, lambda _p: None
        )
        assert "119bpm" in content["description"], "a correct sentence must not be collateral"
        assert len(removed) == 1

    def test_a_strip_that_would_empty_a_field_is_refused(self):
        """Every sentence false: there is nothing to salvage, so nothing is removed.

        An empty description would wipe the athlete's text on Strava and an empty title is
        not a valid activity name. The problem stays reported instead.
        """
        content, problems, removed = apply_content_guard(
            FALSE_CONTENT, RENFO_ACTIVITY, None, RENFO_MODULES, lambda _p: None
        )
        assert content["description"].strip(), "an empty description is not publishable"
        assert content["title"].strip()
        assert problems, "the unresolved problem must remain visible"
        assert removed == [], "no partial claim of repair when nothing was repaired"


class TestTheRetryReachesTheAgent:
    """Without these, the retry is a silent reroll and the guard is decorative.

    The content agent reads each payload key explicitly, so a key it does not read is
    simply dropped. That is the failure mode this pins: the loop would still cost an LLM
    call, still look correct in the logs, and still have no reason to avoid the same error.
    """

    AGENT = Path(
        os.path.join(os.path.dirname(__file__), "..", "..", "src", "agents", "content_agent.py")
    ).read_text(encoding="utf-8")
    LAMBDA = Path(
        os.path.join(
            os.path.dirname(__file__), "..", "..",
            "lambda_functions", "processing", "content_generator.py",
        )
    ).read_text(encoding="utf-8")

    def test_the_lambda_sends_the_errors(self):
        assert "'verification_errors': verification_errors or None" in self.LAMBDA

    def test_the_agent_reads_them(self):
        assert "payload.get('verification_errors')" in self.AGENT

    def test_the_agent_appends_them_to_the_prompt(self):
        assert "CORRECTION OBLIGATOIRE" in self.AGENT

    def test_the_correction_is_appended_before_the_invocation(self):
        assert self.AGENT.index("CORRECTION OBLIGATOIRE") < self.AGENT.index("result = agent(prompt)")

    def test_the_lambda_sends_the_resolved_loads(self):
        assert "'campus_exercise_loads': campus_exercise_loads," in self.LAMBDA

    def test_the_agent_reads_and_renders_the_loads(self):
        assert "payload.get('campus_exercise_loads')" in self.AGENT
        assert "CHARGES PAR EXERCICE" in self.AGENT

    def test_the_family_rule_is_stated_to_the_agent(self):
        """The exact 2026-08-17 error: bodyweight claimed on a loaded family."""
        assert "TOUTE LA FAMILLE" in self.AGENT
        assert "au poids du corps" in self.AGENT


class TestTheGuardIsNeverBlocking:
    def test_a_raising_regeneration_returns_the_original(self):
        def regenerate(_problems):
            raise RuntimeError("AgentCore unavailable")

        content, problems, _removed = apply_content_guard(
            FALSE_CONTENT, RENFO_ACTIVITY, None, RENFO_MODULES, regenerate
        )
        # The original is stripped rather than lost: a partial text beats a false one,
        # and beats no publication at all.
        assert content["description"]
        assert problems

    def test_no_facts_means_no_verdict_rather_than_a_guess(self):
        content, problems, removed = apply_content_guard(
            FALSE_CONTENT, {}, None, [], lambda _p: None
        )
        assert problems == []
        assert removed == []
        assert content == FALSE_CONTENT
