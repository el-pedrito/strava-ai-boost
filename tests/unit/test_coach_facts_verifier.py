"""Tests for the verifier checks against the newly computed facts.

Lots B, C and D put four facts in the coach context: the effort count and recovery mode
from the laps, the per-exercise progression direction, and whether a Campus session was
completed in full. The prompt declares them as the sole source, and this project has
documented three times that declaring is not enforcing:

  * ``coach_generator.py`` states it in its own comment ("It did not fix the last case");
  * on 2026-08-14 a regeneration failed and sentences had to be stripped;
  * on the same day the model paraphrased the athlete's text instead of the Campus plan
    it already held.

So each fact gets a check. Unlike a self-contradiction, these name the wrong half -- the
text disagrees with a computed figure -- so they can end in a strip.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from processing.coach_output_check import strip_false_claims, verify_weekly_claims  # noqa: E402

LAP_FACTS_SIX_EFFORTS = {
    "work_reps": {"count": 6, "durations_s": [34, 25, 15, 35, 25, 15]},
    "blocks": [{"repeat": 2, "pattern_s": [34, 25, 15]}],
    "recovery": {"count": 6, "mode": "active", "distances_m": [390, 417, 777, 408, 443, 755]},
}
LAP_FACTS_ACTIVE_RECOVERY = {
    "work_reps": {"count": 4, "durations_s": [299, 300, 300, 300]},
    "blocks": [{"repeat": 4, "pattern_s": [299]}],
    "recovery": {"count": 4, "mode": "active", "distances_m": [179, 200, 210, 229]},
}
BENCH_PROGRESSION = [
    {
        "exercise": "Développé couché",
        "classification": "progression",
        "delta_reps_at_top_load": 1,
        "current": {"top_load_kg": 90, "sets_at_top_load": 3, "reps_at_top_load": 25},
        "previous": {"top_load_kg": 90, "sets_at_top_load": 3, "reps_at_top_load": 24},
    }
]
CAMPUS_DONE_IN_FULL = {
    "fully_completed": True,
    "structure": {"blocks": 2, "rounds": [4, 4], "work_exercises": ["Split Squat", "Swing"]},
}


class TestEffortCountAgainstTheLaps:
    def test_five_efforts_on_a_six_effort_session(self):
        fb = {"strava_block": "8,5km d'endurance de force avec 5 fractions courtes (15-35sec)."}
        problems = verify_weekly_claims(
            fb, None, None, computed_facts={"lap_facts": LAP_FACTS_SIX_EFFORTS}
        )
        assert any("effort count" in p for p in problems), problems

    def test_the_right_count_passes(self):
        fb = {"strava_block": "8,5km d'endurance de force avec 6 fractions courtes."}
        assert (
            verify_weekly_claims(fb, None, None, computed_facts={"lap_facts": LAP_FACTS_SIX_EFFORTS})
            == []
        )

    def test_without_lap_facts_nothing_is_claimed(self):
        fb = {"strava_block": "8,5km avec 5 fractions courtes."}
        assert verify_weekly_claims(fb, None, None) == []


class TestRecoveryModeAgainstTheLaps:
    def test_passive_stated_on_active_recoveries(self):
        fb = {
            "detailed_analysis": (
                "4 blocs de 5min entrecoupes de recup passive : ton corps digere bien."
            )
        }
        problems = verify_weekly_claims(
            fb, None, None, computed_facts={"lap_facts": LAP_FACTS_ACTIVE_RECOVERY}
        )
        assert any("recovery mode" in p for p in problems), problems

    def test_active_stated_on_active_recoveries(self):
        fb = {"detailed_analysis": "4 blocs de 5min avec recup active de 2min."}
        assert (
            verify_weekly_claims(
                fb, None, None, computed_facts={"lap_facts": LAP_FACTS_ACTIVE_RECOVERY}
            )
            == []
        )


class TestProgressionDirectionAgainstTheComparison:
    def test_regression_wording_on_a_progression(self):
        """The 2026-08-14 inversion: one more rep at the same load, called a regression."""
        fb = {
            "detailed_analysis": (
                "Sur le developpe couche tu es en regression par rapport a la derniere seance."
            )
        }
        problems = verify_weekly_claims(
            fb, None, None, computed_facts={"exercise_comparisons": BENCH_PROGRESSION}
        )
        assert any("progression direction" in p for p in problems), problems

    def test_flancher_is_caught_too(self):
        fb = {"detailed_analysis": "Le developpe couche a flanche sur la derniere serie."}
        problems = verify_weekly_claims(
            fb, None, None, computed_facts={"exercise_comparisons": BENCH_PROGRESSION}
        )
        assert any("progression direction" in p for p in problems), problems

    def test_progression_wording_on_a_progression_passes(self):
        fb = {"detailed_analysis": "Le developpe couche progresse : une repetition de plus a 90kg."}
        assert (
            verify_weekly_claims(
                fb, None, None, computed_facts={"exercise_comparisons": BENCH_PROGRESSION}
            )
            == []
        )

    def test_a_decline_word_far_from_any_exercise_is_left_alone(self):
        """'la FC baisse' says nothing about a lift and must not be flagged."""
        fb = {"detailed_analysis": "Ta FC baisse plus vite entre les series, bon signe."}
        assert (
            verify_weekly_claims(
                fb, None, None, computed_facts={"exercise_comparisons": BENCH_PROGRESSION}
            )
            == []
        )


class TestBlockClaimsAgainstCompletion:
    def test_the_reversed_order_found_in_production_is_caught(self):
        """Published 2026-08-17 by the redeployed coach, on a session done in full.

        The first version of this detector required "reste" BEFORE "bloc", so it caught
        "il reste le bloc 2" and missed "Le Bloc 2 ... reste a faire". Reprocessing the
        real activity is what exposed it; no unit test had, because I wrote the fixtures
        from the errors I already knew.
        """
        sentence = (
            "Le Bloc 2 (gainage lateral, mollet statique) reste a faire pour completer "
            "la seance."
        )
        problems = verify_weekly_claims(
            {"detailed_analysis": sentence}, None, None, {"campus": CAMPUS_DONE_IN_FULL}
        )
        assert any("session completeness" in p for p in problems), problems

    def test_describing_a_block_that_was_done_still_passes(self):
        sentence = "Bloc 2 : swing 24kg, gainage lateral, mollet statique, 4 tours."
        assert (
            verify_weekly_claims(
                {"detailed_analysis": sentence}, None, None, {"campus": CAMPUS_DONE_IN_FULL}
            )
            == []
        )

    def test_announcing_a_remaining_block_on_a_completed_session(self):
        fb = {"recommendation_next": "Prochaine etape : le Bloc 2 avec gainage lateral."}
        problems = verify_weekly_claims(
            fb, None, None, computed_facts={"campus": CAMPUS_DONE_IN_FULL}
        )
        assert any("session completeness" in p for p in problems), problems

    def test_calling_the_session_block_one_of_two(self):
        fb = {"strava_block": "Seance Campus Coach : Renforcement (Bloc 1/2)."}
        problems = verify_weekly_claims(
            fb, None, None, computed_facts={"campus": CAMPUS_DONE_IN_FULL}
        )
        assert any("session completeness" in p for p in problems), problems

    def test_describing_the_two_blocks_done_passes(self):
        fb = {"strava_block": "Seance Renforcement complete : 2 blocs de 4 tours."}
        assert (
            verify_weekly_claims(fb, None, None, computed_facts={"campus": CAMPUS_DONE_IN_FULL})
            == []
        )

    def test_a_partial_session_may_mention_a_remaining_block(self):
        partial = {"fully_completed": False, "structure": {"blocks": 2}}
        fb = {"recommendation_next": "Prochaine etape : le Bloc 2."}
        assert verify_weekly_claims(fb, None, None, computed_facts={"campus": partial}) == []


class TestStripUsesTheNewChecks:
    def test_a_contradicted_fact_sentence_is_removable(self):
        fb = {"strava_block": "Belle seance. Avec 5 fractions courtes au programme."}
        cleaned, removed = strip_false_claims(
            fb, None, None, computed_facts={"lap_facts": LAP_FACTS_SIX_EFFORTS}
        )
        assert removed
        assert "Belle seance." in cleaned["strava_block"]


class TestBackwardCompatibility:
    def test_existing_three_argument_calls_still_work(self):
        assert verify_weekly_claims({"strava_block": "Rien a verifier."}, None, None) == []

    def test_malformed_facts_never_raise(self):
        fb = {"strava_block": "5 fractions courtes."}
        assert verify_weekly_claims(fb, None, None, computed_facts="nope") == []
        assert verify_weekly_claims(fb, None, None, computed_facts={"lap_facts": "nope"}) == []
