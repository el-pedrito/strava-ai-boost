"""Tests for the per-exercise load resolution handed to the content agent.

Reason this exists: on 2026-08-17 the redeployed content agent published "Mollet statique
au poids du corps (40s)" while the athlete had logged "Mollet 12kg". The family rule was
already implemented in campus_structure (_FAMILY_STEMS), but nothing exposed it to the
content agent, which only received the structure and the completion flag. A rule that is
implemented and not wired protects nothing.

Athlete conventions, authoritative (confirmed by him on 2026-08-17):
  - one logged load covers the whole movement FAMILY ("Mollet 12kg" covers both calf
    exercises, including the static hold),
  - "fente" is a split squat, and its load is dual kettlebell so it doubles,
  - an exercise with no stated load anywhere is bodyweight.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared.campus_structure import resolve_exercise_loads  # noqa: E402

W33_RENFORCEMENT = {
    "title": "Renforcement",
    "intervals": [
        {
            "type": "block",
            "repeat": 4,
            "exercises": [
                {"type": "work", "name": "Split Squat", "reps": 8},
                {"type": "work", "name": "Gainage Frontal", "duration": 30},
                {"type": "work", "name": "Extension de Mollet", "reps": 12},
            ],
        },
        {
            "type": "block",
            "repeat": 4,
            "exercises": [
                {"type": "work", "name": "Swing", "reps": 8},
                {"type": "work", "name": "Gainage Latéral", "duration": 30},
                {"type": "work", "name": "Mollet statique", "duration": 40},
            ],
        },
    ],
}
# VERBATIM from the 14/08 activity's original_description, read back from DynamoDB.
# Note he writes "Fentes" while the plan says "Split Squat": that mapping is the whole
# point of _FAMILY_STEMS. An earlier version of this fixture invented "Split squat 2
# kettlebells de 20kg", which tested a notation he does not use.
ATHLETE_TEXT = (
    "Partie 1 du jour\n\nRenfo course campus\nMollet ketle 12kg\n"
    "Fentes ketle 20kg\nSwing ketle 24kg"
)


def _by_name(rows):
    return {row["exercise"]: row for row in rows}


class TestTheFamilyRuleReachesEveryExercise:
    def test_the_static_calf_hold_inherits_the_calf_load(self):
        """The exact error published on 2026-08-17."""
        rows = _by_name(resolve_exercise_loads(W33_RENFORCEMENT, ATHLETE_TEXT))
        static = rows["Mollet statique"]
        assert static["load_kg"] == 12.0
        assert static["bodyweight"] is False, "12kg was logged for the calf family"

    def test_the_other_calf_exercise_gets_the_same_load(self):
        rows = _by_name(resolve_exercise_loads(W33_RENFORCEMENT, ATHLETE_TEXT))
        assert rows["Extension de Mollet"]["load_kg"] == 12.0

    def test_the_split_squat_load_is_doubled_for_dual_kettlebells(self):
        rows = _by_name(resolve_exercise_loads(W33_RENFORCEMENT, ATHLETE_TEXT))
        assert rows["Split Squat"]["load_kg"] == 40.0

    def test_the_swing_keeps_its_single_load(self):
        rows = _by_name(resolve_exercise_loads(W33_RENFORCEMENT, ATHLETE_TEXT))
        assert rows["Swing"]["load_kg"] == 24.0


class TestBodyweightIsStatedNotGuessed:
    def test_an_exercise_with_no_logged_load_is_bodyweight(self):
        rows = _by_name(resolve_exercise_loads(W33_RENFORCEMENT, ATHLETE_TEXT))
        for name in ("Gainage Frontal", "Gainage Latéral"):
            assert rows[name]["bodyweight"] is True
            assert rows[name]["load_kg"] is None

    def test_no_description_makes_every_exercise_bodyweight(self):
        rows = resolve_exercise_loads(W33_RENFORCEMENT, None)
        assert rows, "the exercises must still be listed"
        assert all(r["bodyweight"] is True for r in rows)


class TestShape:
    def test_every_exercise_of_every_block_is_present_once(self):
        rows = resolve_exercise_loads(W33_RENFORCEMENT, ATHLETE_TEXT)
        names = [r["exercise"] for r in rows]
        assert len(names) == 6, names
        assert len(set(names)) == 6, "no duplicate rows despite the repeat factor"

    def test_no_session_returns_empty_rather_than_raising(self):
        assert resolve_exercise_loads(None, ATHLETE_TEXT) == []
