"""The progression's flat fallback only applies to legacy rows with no sets_detail."""

import os
import sys

os.environ.setdefault("ACTIVITIES_TABLE", "t-activities")
os.environ.setdefault("USER_CONFIG_TABLE", "t-config")
os.environ.setdefault("COACHING_SESSIONS_TABLE", "t-sessions")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from api.dashboard_api import _build_strength_progression  # noqa: E402


def test_invalid_detail_never_falls_back_to_the_flat_load():
    entries = [{
        'date': '2026-10-13',
        'parsed_sets': [{
            'exercise': 'Squat', 'sets': 3, 'reps': 5, 'weight_kg': 999,
            'sets_detail': [{'reps': 0, 'weight_kg': 999}],
        }],
    }]
    progression = _build_strength_progression(entries)
    points = progression[0]['points']
    assert all(p['top_weight_kg'] != 999 for p in points)


def test_legacy_row_without_detail_keeps_its_flat_load():
    entries = [{
        'date': '2026-10-13',
        'parsed_sets': [{'exercise': 'Squat', 'sets': 3, 'reps': 5, 'weight_kg': 100}],
    }]
    progression = _build_strength_progression(entries)
    assert progression[0]['points'][0]['top_weight_kg'] == 100.0
