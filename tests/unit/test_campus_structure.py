"""Tests for the Campus PPG structure summary and volume computation.

The fixture is the real W33 "Renforcement" session as stored in
``strava-ai-boost-campus-coaching-sessions``, and the loads are the ones the athlete
logged that day ("Mollet ketle 12kg / Fentes ketle 20kg / Swing ketle 24kg", plus his
confirmation that the split squat carries 2x20kg and the static calf raise the same
12kg kettlebell).

What the deployed pipeline did with it, and why each rule below exists:
  * it flattened a 2-block, 4-round session into a list of three loads, losing the
    structure and three of the six work exercises;
  * it read "Partie 1 du jour" (the first of two SESSIONS that day) as "block 1 of 2",
    announced only block 1, and projected block 2 as a future session;
  * it compared the 44 minutes actually done to the 30 planned minutes as if those 30
    covered a single block;
  * and the strength history stored zero sets for the session, although plan x loads
    makes the volume fully computable.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared.campus_structure import (  # noqa: E402
    compute_ppg_volume,
    is_fully_completed,
    summarize_structure,
)

W33_RENFORCEMENT = {
    "title": "Renforcement",
    "sport": "ppg",
    "expected_duration_min": 30,
    "intervals": [
        {
            "type": "block",
            "repeat": 4,
            "exercises": [
                {"type": "work", "name": "Split Squat avec charge additionnelle", "reps": 8},
                {"type": "work", "name": "Gainage Frontal", "duration": "30 sec"},
                {"type": "work", "name": "Extension de Mollet", "reps": 12},
                {"type": "recovery", "name": "Récupération", "duration": "1:30 min"},
            ],
        },
        {
            "type": "block",
            "repeat": 4,
            "exercises": [
                {"type": "work", "name": "Swing avec charge", "reps": 8},
                {"type": "work", "name": "Gainage Latéral", "duration": "30 sec"},
                {"type": "work", "name": "Mollet statique", "duration": "40 sec"},
                {"type": "recovery", "name": "Récupération", "duration": "1:30 min"},
            ],
        },
    ],
}

# The athlete logs one load per MOVEMENT FAMILY, and it applies to every exercise of
# that family in the plan: "Mollet 12kg" covers both "Extension de Mollet" (block 1)
# and "Mollet statique" (block 2).
ATHLETE_LOADS = {"mollet": 12.0, "fente": 40.0, "swing": 24.0}


class TestStructureSummary:
    def test_reports_both_blocks_and_their_rounds(self):
        summary = summarize_structure(W33_RENFORCEMENT)
        assert summary["blocks"] == 2
        assert summary["rounds"] == [4, 4]

    def test_lists_every_work_exercise_never_only_the_loaded_ones(self):
        """The three unloaded exercises are exactly the ones production dropped."""
        names = summarize_structure(W33_RENFORCEMENT)["work_exercises"]
        assert names == [
            "Split Squat avec charge additionnelle",
            "Gainage Frontal",
            "Extension de Mollet",
            "Swing avec charge",
            "Gainage Latéral",
            "Mollet statique",
        ]

    def test_keeps_the_planned_duration_for_the_whole_session(self):
        assert summarize_structure(W33_RENFORCEMENT)["expected_duration_min"] == 30

    def test_tolerates_a_flat_interval_list(self):
        """Rows written before the block shape must not crash the summary."""
        flat = {"expected_duration_min": 20, "intervals": [{"type": "work", "duration": "30 sec"}]}
        summary = summarize_structure(flat)
        assert summary["blocks"] == 1
        assert summary["rounds"] == [1]

    def test_empty_session_yields_no_structure(self):
        assert summarize_structure({})["blocks"] == 0
        assert summarize_structure(None)["blocks"] == 0


class TestFullCompletionFromDuration:
    """44 minutes done against 30 planned: the session cannot be 'block 1 of 2'."""

    def test_longer_than_planned_is_fully_completed(self):
        assert is_fully_completed(W33_RENFORCEMENT, 44) is True

    def test_clearly_shorter_is_not_asserted_complete(self):
        assert is_fully_completed(W33_RENFORCEMENT, 12) is False

    def test_unknown_duration_abstains(self):
        assert is_fully_completed(W33_RENFORCEMENT, None) is None


class TestPpgVolume:
    def test_loads_propagate_across_the_family_in_both_blocks(self):
        volume = compute_ppg_volume(W33_RENFORCEMENT, ATHLETE_LOADS)
        by_name = {e["exercise"]: e for e in volume["per_exercise"]}
        assert by_name["Extension de Mollet"]["weight_kg"] == 12.0
        assert by_name["Mollet statique"]["weight_kg"] == 12.0

    def test_reps_based_exercises_produce_tonnage(self):
        by_name = {
            e["exercise"]: e
            for e in compute_ppg_volume(W33_RENFORCEMENT, ATHLETE_LOADS)["per_exercise"]
        }
        assert by_name["Split Squat avec charge additionnelle"]["volume_kg"] == 1280.0
        assert by_name["Extension de Mollet"]["volume_kg"] == 576.0
        assert by_name["Swing avec charge"]["volume_kg"] == 768.0

    def test_loaded_isometric_counts_as_time_under_load_not_tonnage(self):
        volume = compute_ppg_volume(W33_RENFORCEMENT, ATHLETE_LOADS)
        by_name = {e["exercise"]: e for e in volume["per_exercise"]}
        static = by_name["Mollet statique"]
        assert static["volume_kg"] == 0.0
        assert static["time_under_load_s"] == 160.0
        assert volume["time_under_load_s"] == 160.0

    def test_totals_and_incompleteness(self):
        volume = compute_ppg_volume(W33_RENFORCEMENT, ATHLETE_LOADS)
        assert volume["total_sets"] == 24
        assert volume["total_reps"] == 112
        assert volume["volume_kg"] == 2624.0
        # A loaded isometric carries real work that reps x load cannot express, so the
        # tonnage must stay explicitly partial rather than look complete.
        assert volume["volume_kg_incomplete"] is True
        assert "Mollet statique" in volume["excluded_exercises"]

    def test_bodyweight_holds_are_time_only(self):
        volume = compute_ppg_volume(W33_RENFORCEMENT, ATHLETE_LOADS)
        assert volume["bodyweight_time_s"] == 240.0

    def test_without_loads_nothing_is_invented(self):
        volume = compute_ppg_volume(W33_RENFORCEMENT, {})
        assert volume["volume_kg"] == 0.0
        assert volume["volume_kg_incomplete"] is True
        assert volume["total_sets"] == 24

    def test_never_raises_on_malformed_input(self):
        assert compute_ppg_volume(None, None)["total_sets"] == 0
        assert compute_ppg_volume({"intervals": "nope"}, {})["total_sets"] == 0
