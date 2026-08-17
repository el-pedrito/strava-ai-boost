"""Tests for the guard on announced totals of seconds under load.

Reason this exists: on 2026-08-17, after both earlier fixes were verified live, the content
agent published "mes mollets ont bossé 328 secondes au total (extensions + statique)". The
computed time under load is 160 s (40 s x 4 rounds for the static hold); the calf
EXTENSIONS are counted in reps, not seconds, so the missing 168 s come from an implicit
seconds-per-rep estimate the model made on its own.

The figure is not exactly false, it is UNSOURCED, which is the recurring failure of this
whole pipeline: the model fills any space the provided facts leave empty. The guard closes
that space for time totals.

Tolerance is deliberate, not sloppiness: the athlete may hold a little longer than planned,
so a total within 10% of a computed value is accepted. What is rejected is a total that
matches none of the computed times.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from processing.coach_output_check import (  # noqa: E402
    CONTENT_CHECKED_FIELDS,
    verify_weekly_claims,
)

# W33 Renforcement: 160 s of loaded isometrics, 240 s of bodyweight isometrics.
RENFO_FACTS = {
    "campus": {
        "fully_completed": True,
        "computed_volume": {
            "total_sets": 24,
            "total_reps": 112,
            "volume_kg": 2624.0,
            "time_under_load_s": 160.0,
            "bodyweight_time_s": 240.0,
        },
    }
}


class TestTheUnsourcedTotalIsCaught:
    def test_the_published_328_seconds_is_flagged(self):
        sentence = "Fun fact : mes mollets ont bosse 328 secondes au total (extensions + statique)."
        problems = verify_weekly_claims(
            {"description": sentence}, None, None, RENFO_FACTS, CONTENT_CHECKED_FIELDS
        )
        assert any("time total" in p for p in problems), problems

    def test_the_problem_names_the_computed_values(self):
        sentence = "328 secondes au total sous charge."
        problems = verify_weekly_claims(
            {"description": sentence}, None, None, RENFO_FACTS, CONTENT_CHECKED_FIELDS
        )
        assert problems and "160" in problems[0], problems


class TestTheComputedTotalsPass:
    def test_the_loaded_isometric_total_passes(self):
        sentence = "160 secondes au total sous charge sur les mollets."
        assert (
            verify_weekly_claims(
                {"description": sentence}, None, None, RENFO_FACTS, CONTENT_CHECKED_FIELDS
            )
            == []
        )

    def test_the_bodyweight_total_passes(self):
        sentence = "Les gainages cumulent 240 secondes au total."
        assert (
            verify_weekly_claims(
                {"description": sentence}, None, None, RENFO_FACTS, CONTENT_CHECKED_FIELDS
            )
            == []
        )

    def test_the_sum_of_both_passes(self):
        """400 s of isometric work is a legitimate reading of the same session."""
        sentence = "400 secondes de gainage et de maintien au total."
        assert (
            verify_weekly_claims(
                {"description": sentence}, None, None, RENFO_FACTS, CONTENT_CHECKED_FIELDS
            )
            == []
        )

    def test_a_small_overshoot_is_tolerated(self):
        sentence = "168 secondes au total sur les mollets."
        assert (
            verify_weekly_claims(
                {"description": sentence}, None, None, RENFO_FACTS, CONTENT_CHECKED_FIELDS
            )
            == []
        ), "the athlete may hold slightly longer than planned"


class TestWhatMustNotBeFlagged:
    def test_a_single_exercise_duration_is_not_a_total(self):
        sentence = "Gainage Frontal 30 secondes, Mollet statique 40 secondes."
        assert (
            verify_weekly_claims(
                {"description": sentence}, None, None, RENFO_FACTS, CONTENT_CHECKED_FIELDS
            )
            == []
        )

    def test_the_session_duration_in_minutes_is_untouched(self):
        """44 min is the session length, checked elsewhere against moving_time."""
        sentence = "44 minutes au total contre 30 prevues."
        assert (
            verify_weekly_claims(
                {"description": sentence}, None, None, RENFO_FACTS, CONTENT_CHECKED_FIELDS
            )
            == []
        )

    def test_a_recovery_duration_is_not_a_total(self):
        sentence = "1'30 de recup entre les series, 90 secondes exactement."
        assert (
            verify_weekly_claims(
                {"description": sentence}, None, None, RENFO_FACTS, CONTENT_CHECKED_FIELDS
            )
            == []
        )

    def test_without_the_computed_volume_no_verdict_is_given(self):
        sentence = "328 secondes au total sur les mollets."
        assert (
            verify_weekly_claims(
                {"description": sentence},
                None,
                None,
                {"campus": {"fully_completed": True}},
                CONTENT_CHECKED_FIELDS,
            )
            == []
        ), "a missing fact must produce no verdict, never a guess"
