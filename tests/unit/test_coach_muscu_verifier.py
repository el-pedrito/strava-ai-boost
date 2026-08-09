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
