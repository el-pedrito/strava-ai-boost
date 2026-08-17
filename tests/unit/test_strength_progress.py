"""Tests for the per-exercise progression comparison.

The specification is the 2026-08-14 Upperbody session. The coach published that the
bench press had REGRESSED and that the athlete had "flanche", inventing a previous
session of "4x8 @90kg". The stored history says otherwise:

    11/08  80x10, 90x8, 90x8, 90x8   -> 3 work sets at 90, 24 reps at 90
    14/08  80x10, 90x8, 90x8, 90x9   -> 3 work sets at 90, 25 reps at 90

Same top load, same number of work sets, one more repetition. That is a progression,
and the published feedback inverted it. The comparison is therefore computed here and
handed to the model as a fact, instead of being inferred from the raw history.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared.strength_progress import build_exercise_comparisons, compare_exercise  # noqa: E402

BENCH_11_08 = [
    {"reps": 10, "weight_kg": 80},
    {"reps": 8, "weight_kg": 90},
    {"reps": 8, "weight_kg": 90},
    {"reps": 8, "weight_kg": 90},
]
BENCH_14_08 = [
    {"reps": 10, "weight_kg": 80},
    {"reps": 8, "weight_kg": 90},
    {"reps": 8, "weight_kg": 90},
    {"reps": 9, "weight_kg": 90},
]


class TestTheProductionInversion:
    def test_one_extra_rep_at_the_same_top_load_is_a_progression(self):
        result = compare_exercise("Développé couché", BENCH_14_08, BENCH_11_08)
        assert result["classification"] == "progression"
        assert result["delta_reps_at_top_load"] == 1

    def test_the_top_load_and_set_count_are_reported_unchanged(self):
        result = compare_exercise("Développé couché", BENCH_14_08, BENCH_11_08)
        assert result["current"]["top_load_kg"] == 90
        assert result["current"]["sets_at_top_load"] == 3
        assert result["current"]["reps_at_top_load"] == 25
        assert result["previous"]["sets_at_top_load"] == 3
        assert result["previous"]["reps_at_top_load"] == 24

    def test_the_reverse_direction_is_a_regression(self):
        result = compare_exercise("Développé couché", BENCH_11_08, BENCH_14_08)
        assert result["classification"] == "regression"
        assert result["delta_reps_at_top_load"] == -1


class TestClassification:
    def test_identical_sessions_are_a_maintien(self):
        result = compare_exercise("Développé couché", BENCH_11_08, BENCH_11_08)
        assert result["classification"] == "maintien"
        assert result["delta_reps_at_top_load"] == 0

    def test_a_heavier_top_load_is_a_progression_whatever_the_reps(self):
        heavier = [{"reps": 5, "weight_kg": 95}]
        result = compare_exercise("Développé couché", heavier, BENCH_11_08)
        assert result["classification"] == "progression"

    def test_a_lighter_top_load_is_a_regression(self):
        lighter = [{"reps": 12, "weight_kg": 85}]
        result = compare_exercise("Développé couché", lighter, BENCH_11_08)
        assert result["classification"] == "regression"

    def test_no_previous_session_is_incomparable_never_a_regression(self):
        result = compare_exercise("Développé couché", BENCH_14_08, None)
        assert result["classification"] == "incomparable"
        assert result["previous"] is None

    def test_bodyweight_sets_without_load_are_incomparable(self):
        pullups = [{"reps": 10, "weight_kg": None}, {"reps": 10, "weight_kg": None}]
        result = compare_exercise("Tractions", pullups, pullups)
        assert result["classification"] == "incomparable"


class TestBuildFromHistory:
    def test_matches_the_same_exercise_in_the_most_recent_earlier_entry(self):
        history = [
            {
                "date": "2026-08-08",
                "parsed_sets": [
                    {"exercise": "Développé couché", "sets_detail": [{"reps": 6, "weight_kg": 90}]}
                ],
            },
            {
                "date": "2026-08-11",
                "parsed_sets": [
                    {"exercise": "Développé couché", "sets_detail": BENCH_11_08}
                ],
            },
        ]
        current = [{"exercise": "Développé couché", "sets_detail": BENCH_14_08}]
        comparisons = build_exercise_comparisons(current, history)
        assert len(comparisons) == 1
        assert comparisons[0]["previous"]["date"] == "2026-08-11"
        assert comparisons[0]["classification"] == "progression"

    def test_rebuilds_sets_detail_from_the_flat_shape_when_absent(self):
        """Rows written before sets_detail existed must still compare."""
        history = [
            {
                "date": "2026-08-11",
                "parsed_sets": [
                    {"exercise": "Développé couché", "sets": 3, "reps": 8, "weight_kg": 90}
                ],
            }
        ]
        current = [{"exercise": "Développé couché", "sets_detail": BENCH_14_08}]
        comparisons = build_exercise_comparisons(current, history)
        assert comparisons[0]["previous"]["reps_at_top_load"] == 24

    def test_an_exercise_absent_from_history_is_reported_incomparable(self):
        current = [{"exercise": "Swing avec charge", "sets_detail": [{"reps": 8, "weight_kg": 24}]}]
        comparisons = build_exercise_comparisons(current, [])
        assert comparisons[0]["classification"] == "incomparable"

    def test_never_raises_on_malformed_input(self):
        assert build_exercise_comparisons(None, None) == []
        assert build_exercise_comparisons("nope", [{"parsed_sets": "nope"}]) == []
