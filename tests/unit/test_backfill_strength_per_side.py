"""Unit tests for scripts/backfill_strength_per_side.py: the flag is written only
where it is certain, and never touches loads or rows already flagged."""

import importlib
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "lambda_functions"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

backfill = importlib.import_module("backfill_strength_per_side")


def _row(ex, kg, n=3, **extra):
    return {"exercise": ex, "sets_detail": [{"reps": 10, "weight_kg": kg}] * n, **extra}


def _never(_description):
    raise AssertionError("no re-read expected")


def test_campus_and_no_wording_rows_become_false_without_a_reread():
    entries = [
        {"sets_source": "campus_plan", "description": "Fentes 35kg/cote",
         "parsed_sets": [_row("Fentes", 35)]},
        {"sets_source": "athlete_text", "description": "dc 3x10 80",
         "parsed_sets": [_row("Développé couché", 80)]},
    ]
    out, stats = backfill.decide_flags(entries, _never)
    assert out[0]["parsed_sets"][0]["per_side"] is False
    assert out[1]["parsed_sets"][0]["per_side"] is False
    assert stats["set_false_no_wording"] == 2
    assert "per_side" not in entries[0]["parsed_sets"][0]  # input left untouched


def test_reread_flag_is_copied_only_on_a_unique_exact_match():
    entries = [{
        "sets_source": "athlete_text",
        "description": "dc 80x10 + press inc 3x10 40/c\ncurl 3x10 30",
        "parsed_sets": [
            _row("Développé couché", 80, n=1),
            _row("Développé incliné haltères", 80),
            _row("Curl biceps", 30),       # re-read gives another load: no match
        ],
    }]

    def reread(_description):
        return [
            _row("Développé couché", 80, n=1, per_side=False),
            _row("Développé incliné haltères", 80, per_side=True),
            _row("Curl biceps", 32, per_side=False),
        ]

    out, stats = backfill.decide_flags(entries, reread)
    rows = out[0]["parsed_sets"]
    assert rows[0]["per_side"] is False
    assert rows[1]["per_side"] is True
    assert "per_side" not in rows[2]
    assert +stats == {"set_false_reread": 1, "set_true_reread": 1, "left_unflagged": 1}
    # Loads are never rewritten.
    assert [s["weight_kg"] for s in rows[1]["sets_detail"]] == [80, 80, 80]


def test_two_identical_reread_rows_are_not_a_unique_match():
    entries = [{"sets_source": "athlete_text", "description": "dc 3x10 40/c",
                "parsed_sets": [_row("Développé couché", 80)]}]

    def reread(_description):
        return [_row("Développé couché", 80, per_side=True),
                _row("Développé couché", 80, per_side=False)]

    out, stats = backfill.decide_flags(entries, reread)
    assert "per_side" not in out[0]["parsed_sets"][0]
    assert stats["left_unflagged"] == 1


def test_already_flagged_rows_are_never_reread_or_changed():
    entries = [{"sets_source": "athlete_text", "description": "dc 3x10 40/c",
                "parsed_sets": [_row("Développé couché", 80, per_side=True)]}]
    out, stats = backfill.decide_flags(entries, _never)
    assert out[0]["parsed_sets"][0]["per_side"] is True
    assert stats["already_flagged"] == 1
