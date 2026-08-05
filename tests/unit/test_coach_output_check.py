"""Tests for the coach output verifier.

Every "lie" fixture below is a verbatim sentence the deployed coach produced. They
are the specification: the verifier exists to catch these shapes, and a change that
stops catching one of them is a regression.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from processing.coach_output_check import (  # noqa: E402
    split_sentences,
    strip_false_claims,
    verify_weekly_claims,
)


def _overview(runs=1, run_km=6.4, strength=1, remaining=4, incomplete=False):
    return {
        "week": "2026-W32",
        "label": "Cette semaine (03/08-09/08)",
        "done_this_week": {
            "runs": runs,
            "run_km": run_km,
            "strength": strength,
            "other": 0,
            "total": runs + strength,
        },
        "campus_remaining": {"count": remaining, "running_count": remaining - 1},
        "own_strength_program": {"planned_per_week": 3, "done_this_week": 1, "remaining": 2},
        "counts_incomplete": incomplete,
    }


def _session(total_sets=25, total_reps=238, volume_kg=15370.0, incomplete=False):
    return {
        "total_sets": total_sets,
        "total_reps": total_reps,
        "volume_kg": volume_kg,
        "body_weight_kg_used": 92.0,
        "volume_kg_incomplete": incomplete,
    }


class TestRealProductionLiesAreCaught:
    """The five figures the deployed coach actually got wrong."""

    def test_rep_total_fabricated(self):
        """'320 reps' on a session of 238, with an invented fun fact."""
        fb = {"detailed_analysis": "Fun fact : 320 reps au total aujourd'hui."}
        problems = verify_weekly_claims(fb, _overview(), _session())
        assert problems, "the 320 vs 238 mismatch must be caught"
        assert "total reps" in problems[0]

    def test_strength_session_count_inflated(self):
        """'2 seances muscu' on a week holding one."""
        fb = {"strava_block": "Cette semaine : 1 run (6,4km) + 2 seances muscu."}
        problems = verify_weekly_claims(fb, _overview(strength=1), None)
        assert any("strength sessions" in p for p in problems), problems

    def test_rolling_window_volume_presented_as_the_week(self):
        """'35km cette semaine' when the ISO week held 6.4km."""
        fb = {"strava_block": "Tu totalises 35km cette semaine, belle charge."}
        problems = verify_weekly_claims(fb, _overview(run_km=6.4), None)
        assert any("kilometres" in p for p in problems), problems

    def test_remaining_sessions_understated(self):
        """'il reste 2 seances' when 4 were to do."""
        fb = {"recommendation_next": "Il te reste 2 seances Campus a placer."}
        problems = verify_weekly_claims(fb, _overview(remaining=4), None)
        assert any("remaining" in p for p in problems), problems

    def test_set_count_inflated(self):
        """26 sets claimed on a 25-set session (the trailing xN bug)."""
        fb = {"detailed_analysis": "26 series au total sur cette seance."}
        problems = verify_weekly_claims(fb, _overview(), _session(total_sets=25))
        assert any("total sets" in p for p in problems), problems


class TestCorrectStatementsPass:
    """A verifier that flags correct text is worse than none: it would strip good
    sentences and train the reader to ignore the warnings."""

    def test_exact_figures_pass(self):
        fb = {
            "strava_block": "Cette semaine : 1 course (6,4km) + 1 seance muscu.",
            "detailed_analysis": "25 series, 238 reps, 15370 kg soulevés au total.",
            "recommendation_next": "Il te reste 4 seances Campus.",
        }
        assert verify_weekly_claims(fb, _overview(), _session()) == []

    def test_rounded_kilometres_tolerated(self):
        fb = {"strava_block": "6,5km cette semaine."}
        assert verify_weekly_claims(fb, _overview(run_km=6.42), None) == []

    def test_past_week_figures_are_not_compared_to_this_week(self):
        """weekly_breakdown legitimately reports other weeks."""
        fb = {"detailed_analysis": "La semaine derniere : 4 courses (26.5km), 2 muscu."}
        assert verify_weekly_claims(fb, _overview(runs=1, run_km=6.4), None) == []

    def test_incomplete_counts_disable_weekly_checks(self):
        """When the code itself flagged its counts as incomplete, it cannot arbitrate."""
        fb = {"strava_block": "3 courses cette semaine."}
        assert verify_weekly_claims(fb, _overview(runs=1, incomplete=True), None) == []

    def test_partial_tonnage_is_not_compared(self):
        """A partial tonnage legitimately differs from any stated figure."""
        fb = {"detailed_analysis": "environ 9000 kg soulevés."}
        assert verify_weekly_claims(fb, _overview(), _session(incomplete=True)) == []

    def test_no_figures_no_problems(self):
        fb = {"strava_block": "Belle seance, les sensations reviennent."}
        assert verify_weekly_claims(fb, _overview(), _session()) == []


class TestRobustness:
    """The verifier must never be the reason a coach feedback fails to publish."""

    def test_missing_inputs_are_tolerated(self):
        assert verify_weekly_claims(None, None, None) == []
        assert verify_weekly_claims({}, {}, {}) == []
        assert verify_weekly_claims({"strava_block": None}, _overview(), None) == []

    def test_non_dict_feedback_tolerated(self):
        assert verify_weekly_claims("not a dict", _overview(), None) == []

    def test_unparseable_truth_is_skipped(self):
        fb = {"strava_block": "3 courses cette semaine."}
        ov = _overview()
        ov["done_this_week"]["runs"] = "many"
        assert verify_weekly_claims(fb, ov, None) == []

    def test_sentence_splitting_keeps_newline_fragments_apart(self):
        parts = split_sentences("Premiere phrase.\nDeuxieme ligne. Troisieme !")
        assert len(parts) == 3, parts


class TestStripFalseClaims:
    """Last resort after a failed regeneration."""

    def test_only_the_offending_sentence_is_removed(self):
        fb = {
            "strava_block": (
                "Belle seance upper. Fun fact : 320 reps au total. "
                "Low row qui grimpe a 90kg, belle progression."
            )
        }
        cleaned, removed = strip_false_claims(fb, _overview(), _session())
        assert len(removed) == 1, removed
        assert "320 reps" in removed[0]
        assert "Belle seance upper." in cleaned["strava_block"]
        assert "belle progression" in cleaned["strava_block"]
        assert "320" not in cleaned["strava_block"]

    def test_clean_feedback_is_untouched(self):
        fb = {"strava_block": "238 reps au total, 25 series."}
        cleaned, removed = strip_false_claims(fb, _overview(), _session())
        assert removed == []
        assert cleaned["strava_block"] == "238 reps au total, 25 series."

    def test_all_checked_fields_are_cleaned(self):
        fb = {
            "strava_block": "320 reps au total.",
            "detailed_analysis": "Il te reste 2 seances.",
            "recommendation_next": "Repose-toi 48h.",
        }
        cleaned, removed = strip_false_claims(fb, _overview(), _session())
        assert len(removed) == 2, removed
        assert cleaned["strava_block"] == ""
        assert cleaned["recommendation_next"] == "Repose-toi 48h."


class TestRemainingVersusDone:
    """"il reste 2 muscu" counts sessions TO DO, not sessions done.

    The first version compared any "N muscu" against done_this_week.strength and
    stripped this correct sentence from a live coach output:
    "Il reste 4 seances Campus (3 courses dont 1 PPG) + 2 muscu perso".
    """

    def test_remaining_own_strength_is_not_compared_to_done(self):
        fb = {"recommendation_next": "Il reste 4 seances Campus + 2 muscu perso."}
        assert verify_weekly_claims(fb, _overview(strength=1, remaining=4), None) == []

    def test_wrong_remaining_own_strength_is_still_caught(self):
        fb = {"recommendation_next": "Il te reste 5 seances muscu perso a faire."}
        problems = verify_weekly_claims(fb, _overview(), None)
        assert any("remaining own strength" in p for p in problems), problems

    def test_done_claim_still_checked_when_no_remaining_marker(self):
        fb = {"strava_block": "Cette semaine : 2 seances muscu."}
        problems = verify_weekly_claims(fb, _overview(strength=1), None)
        assert any("strength sessions this week" in p for p in problems), problems


class TestAdvisorySentencesAreNotClaims:
    """Advice carrying a number claims nothing about the week.

    "evite 2 seances muscu consecutives" was stripped from a live output by the
    first version, removing useful coaching for no gain.
    """

    def test_advice_is_not_verified(self):
        fb = {"recommendation_next": "Alterne course et muscu, évite 2 séances muscu consécutives."}
        assert verify_weekly_claims(fb, _overview(strength=1), None) == []

    def test_factual_claim_in_the_same_field_is_still_verified(self):
        fb = {"recommendation_next": "Cette semaine : 2 séances muscu. Évite 2 muscu consécutives."}
        problems = verify_weekly_claims(fb, _overview(strength=1), None)
        assert len(problems) == 1, problems
        assert "strength sessions this week" in problems[0]
