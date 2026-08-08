"""Regression test for the coach '5 courses en 5 jours' bug.

The verifier only checked weekly run/km counts when the sentence matched the
current-week allowlist. The agent dodged it by scoping the count to a rolling
'en N jours (03-07/08)' window, which the prompt forbids, so a stated 5 courses
/ 27km slipped past unchecked while the ISO-week truth was 3 courses / 20.5km.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from processing.coach_output_check import verify_weekly_claims, _mentions_current_week

WEEK_OVERVIEW = {
    "done_this_week": {"runs": 3, "run_km": 20.5, "strength": 1, "total": 4},
}


class TestSlidingWindowRunCount:
    def test_en_n_jours_is_treated_as_current_week(self):
        assert _mentions_current_week("5 courses en 5 jours (03-07/08) = 27km") is True

    def test_sliding_window_run_count_is_flagged(self):
        feedback = {
            "strava_block": "Ton cardio digere bien la charge. 5 courses en 5 jours (03-07/08) = 27km, Form a -14,6.",
        }
        problems = verify_weekly_claims(feedback, WEEK_OVERVIEW)
        assert problems, "the fabricated 5 courses / 27km should be flagged"
        joined = " ".join(problems)
        assert "run count this week" in joined
        assert "kilometres this week" in joined

    def test_correct_iso_week_count_is_not_flagged(self):
        feedback = {"strava_block": "Cette semaine: 3 courses (20.5km). Beau boulot."}
        assert verify_weekly_claims(feedback, WEEK_OVERVIEW) == []

    def test_past_week_still_not_flagged(self):
        # "en N jours" must not override an explicit past-week marker.
        feedback = {"strava_block": "La semaine derniere: 4 courses (26.5km), rien d'alarmant."}
        assert verify_weekly_claims(feedback, WEEK_OVERVIEW) == []

    def test_ces_n_derniers_jours_also_caught(self):
        feedback = {"strava_block": "Ces 5 derniers jours: 5 courses au compteur."}
        problems = verify_weekly_claims(feedback, WEEK_OVERVIEW)
        assert any("run count this week" in p for p in problems)
