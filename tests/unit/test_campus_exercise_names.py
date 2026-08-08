"""Unit tests for Campus exercise parsing now capturing movement name + reps.

PPG/renfo exercises carry a real 'name' (Split Squat, Gainage Frontal, ...) and a
per-exercise 'repeat' = rep count. The parser used to keep only {type, duration,
pace}, leaving strength sessions as empty placeholders the coach could not name.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from webhooks.campus_coach_sync import _build_exercise_entry


class TestBuildExerciseEntry:
    def test_ppg_work_with_reps_keeps_name_and_reps(self):
        ex = {"name": "Split Squat avec charge additionnelle", "exerciseType": "ppg", "repeat": 8, "durations": []}
        entry = _build_exercise_entry(ex, "work")
        assert entry["type"] == "work"
        assert entry["name"] == "Split Squat avec charge additionnelle"
        assert entry["reps"] == 8

    def test_ppg_timed_exercise_keeps_name_and_duration(self):
        ex = {"name": "Gainage Frontal", "exerciseType": "ppg", "durations": [{"value": 30, "timeUnit": "seconds"}]}
        entry = _build_exercise_entry(ex, "work")
        assert entry["name"] == "Gainage Frontal"
        assert entry["duration"] == "30 sec"
        assert "reps" not in entry

    def test_recovery_keeps_name_but_no_reps(self):
        ex = {"name": "Récupération", "exerciseType": "recuperation", "repeat": 1,
              "durations": [{"value": 60, "timeUnit": "seconds"}]}
        entry = _build_exercise_entry(ex, "work")
        assert entry["type"] == "recovery"
        assert entry["name"] == "Récupération"
        assert "reps" not in entry

    def test_running_exercise_without_name_unchanged(self):
        ex = {"exerciseType": "", "pace": {"name": "Rapide", "value": 204},
              "durations": [{"value": 35, "timeUnit": "seconds"}]}
        entry = _build_exercise_entry(ex, "work")
        assert "name" not in entry
        assert entry["duration"] == "35 sec"
        assert "Rapide" in entry["pace"]
