"""The coach verifier must catch a muscu/total count that treats the Campus PPG as
an own muscu ("3 muscu = 8 séances" on a 2 muscu + 1 PPG = 7 week), while NOT
false-flagging the correct "2 muscu = 7 séances".
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from processing.coach_output_check import _check_sentence

WO = {
    "done_this_week": {"runs": 4, "run_km": 40.0, "strength": 3, "muscu": 2, "ppg": 1, "total": 7},
    "campus_remaining": {"count": 0},
    "own_strength_program": {"remaining": 0, "planned_per_week": 2},
}


class TestVerifierMuscuTotal:
    def test_flags_ppg_counted_as_muscu(self):
        s = "Cette semaine Campus complète : 4 courses + 1 PPG + 3 muscu = 8 séances totales."
        probs = _check_sentence(s, WO, None)
        assert any("strength sessions this week" in p for p in probs), probs   # 3 vs 2
        assert any("total sessions this week" in p for p in probs), probs      # 8 vs 7

    def test_correct_counts_pass(self):
        s = "Cette semaine : 4 courses + 1 PPG + 2 muscu = 7 séances totales."
        probs = _check_sentence(s, WO, None)
        assert probs == [], probs

    def test_correct_muscu_not_flagged_against_strength(self):
        # regression: 2 muscu must NOT be compared against strength=3 (old bug would flag it)
        probs = _check_sentence("Cette semaine tu as fait 2 muscu.", WO, None)
        assert probs == [], probs


class TestClaimLevelScoping:
    """Production incident 2026-08-09: '5e course en 7 jours (40km cette semaine vs
    27km semaine derniere)' published against a computed 4 runs / 30.5km. Two holes:
    the ordinal escaped _RUN_COUNT, and the past-week mention disabled the whole
    sentence instead of just its own comparison segment."""

    WO2 = {
        "done_this_week": {"runs": 4, "run_km": 30.5, "strength": 3, "muscu": 2,
                            "ppg": 1, "total": 7},
        "campus_remaining": {"count": 0},
        "own_strength_program": {"remaining": 0},
    }

    def test_exact_production_sentence_is_flagged(self):
        s = "5e course en 7 jours (40km cette semaine vs 27km semaine dernière)."
        probs = _check_sentence(s, self.WO2, None)
        assert any("run count" in p and "5" in p for p in probs), probs
        assert any("kilometres" in p and "40" in p for p in probs), probs

    def test_past_week_segment_not_flagged(self):
        # the 27km belongs to last week: it must NOT be compared to this week's 30.5
        s = "30,5km cette semaine vs 27km semaine dernière."
        probs = _check_sentence(s, self.WO2, None)
        assert probs == [], probs

    def test_ordinal_run_count_correct_passes(self):
        probs = _check_sentence("4e course cette semaine, belle régularité.", self.WO2, None)
        assert probs == [], probs

    def test_recap_line_verbatim_passes(self):
        s = "Cette semaine : 4 courses (30,5 km), 2 muscu, 1 PPG, soit 7 séances au total."
        probs = _check_sentence(s, self.WO2, None)
        assert probs == [], probs
