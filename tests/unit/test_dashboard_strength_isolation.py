"""Garbage strength_history must not break /coach/summary.

Asserts: HTTP 200, body parses with a strict JSON parser (no NaN tokens), the
non-strength ("running") trends are byte-for-byte identical to a baseline whose
strength_history is empty, and the strength builders degrade to [] / None rather
than raising.
"""

import os
import sys
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from api.dashboard_api import get_coach_summary, handler  # noqa: E402


def _mock_tables(strength_entries):
    activities_table = MagicMock()
    activities_table.query.return_value = {'Items': []}
    config_table = MagicMock()
    config_table.get_item.return_value = {
        'Item': {'user_preferences': {'strength_history': {'entries': strength_entries}}}
    }
    sessions_table = MagicMock()
    sessions_table.scan.return_value = {'Items': []}
    return lambda name: {
        'test-activities': activities_table,
        'test-user-config': config_table,
        'test-coaching-sessions': sessions_table,
    }.get(name, MagicMock())


# A payload mixing every shape the normalizer and builders must survive.
GARBAGE_ENTRIES = [
    "abc",
    {},
    None,
    42,
    {'date': None, 'parsed_sets': []},
    {'date': 'not-a-date', 'parsed_sets': []},
    {'date': '2026-13-99', 'parsed_sets': []},
    {'date': '2026-10-13', 'parsed_sets': 'not-a-list'},
    {'date': '2026-10-13', 'parsed_sets': [None, 'x', {}, {'exercise': ''}]},
    {'date': '2026-10-13', 'parsed_sets': [
        {'exercise': 'Squat', 'sets_detail': 'bad', 'sets': 'abc', 'reps': 'xyz', 'weight_kg': 'nope'},
    ]},
    {'date': '2026-10-13', 'total_sets': 'abc', 'total_reps': None,
     'volume_kg': 'bad', 'parsed_sets': [{'exercise': 'Squat', 'weight_kg': 100, 'sets': 3, 'reps': 5}]},
]


class TestGarbageIsolation:
    @patch('api.dashboard_api.dynamodb')
    def test_handler_returns_200_and_strict_json(self, mock_dynamo):
        mock_dynamo.Table.side_effect = _mock_tables(GARBAGE_ENTRIES)
        event = {'httpMethod': 'GET', 'path': '/coach/summary',
                 'requestContext': {'authorizer': {'claims': {'custom:strava_id': '42'}}}}
        resp = handler(event, None)
        assert resp['statusCode'] == 200
        # Strict parse: json.loads rejects NaN/Infinity only with parse_constant,
        # so assert there is no bare NaN/Infinity token in the body.
        assert 'NaN' not in resp['body']
        assert 'Infinity' not in resp['body']
        body = json.loads(resp['body'])
        assert body['schema_version'] == 1

    @patch('api.dashboard_api.dynamodb')
    def test_running_trends_identical_to_empty_baseline(self, mock_dynamo):
        # Baseline: empty strength history.
        mock_dynamo.Table.side_effect = _mock_tables([])
        baseline = get_coach_summary('42')

        # Garbage strength history, everything else identical.
        mock_dynamo.Table.side_effect = _mock_tables(GARBAGE_ENTRIES)
        garbage = get_coach_summary('42')

        strength_keys = {
            'strength_history', 'strength_progression',
            'strength_sessions', 'strength_insights',
        }
        base_running = {k: v for k, v in baseline['trends'].items() if k not in strength_keys}
        garb_running = {k: v for k, v in garbage['trends'].items() if k not in strength_keys}
        assert base_running == garb_running
        # And the whole non-trends top level is unchanged too.
        base_top = {k: v for k, v in baseline.items() if k != 'trends'}
        garb_top = {k: v for k, v in garbage.items() if k != 'trends'}
        assert base_top == garb_top

    @patch('api.dashboard_api.dynamodb')
    def test_strength_builders_degrade_gracefully(self, mock_dynamo):
        mock_dynamo.Table.side_effect = _mock_tables(GARBAGE_ENTRIES)
        result = get_coach_summary('42')
        trends = result['trends']
        # Projected history keeps only the valid-date rows; builders never raise.
        assert isinstance(trends['strength_history'], list)
        assert isinstance(trends['strength_progression'], list)
        assert isinstance(trends['strength_sessions'], list)
        # strength_insights is a dict (built) or None (guarded) — never a crash.
        assert trends['strength_insights'] is None or isinstance(trends['strength_insights'], dict)

    @patch('api.dashboard_api.dynamodb')
    def test_valid_strength_history_populates_insights(self, mock_dynamo):
        entries = [
            {'date': '2026-10-06', 'activity_id': 'a1', 'duration_min': 60,
             'sets_source': 'athlete_text', 'description': 'DC 95x5',
             'parsed_sets': [{'exercise': 'Développé couché', 'sets': 3, 'reps': 5,
                              'weight_kg': 95, 'sets_detail': [{'reps': 5, 'weight_kg': 95}] * 3}],
             'per_exercise': [{'exercise': 'Développé couché', 'volume_kg': 1425,
                               'volume_incomplete': False}]},
            {'date': '2026-10-13', 'activity_id': 'a2', 'duration_min': 65,
             'sets_source': 'athlete_text', 'description': 'DC 100x5',
             'parsed_sets': [{'exercise': 'Développé couché', 'sets': 3, 'reps': 5,
                              'weight_kg': 100, 'sets_detail': [{'reps': 5, 'weight_kg': 100}] * 3}],
             'per_exercise': [{'exercise': 'Développé couché', 'volume_kg': 1500,
                               'volume_incomplete': False}]},
        ]
        mock_dynamo.Table.side_effect = _mock_tables(entries)
        result = get_coach_summary('42')
        insights = result['trends']['strength_insights']
        assert insights is not None
        assert len(insights['weeks']) == 8
        prog = result['trends']['strength_progression']
        dc = next(p for p in prog if p['exercise'] == 'Développé couché')
        assert dc['e1rm_eligible'] is True
        # e1rm_kg carried on points.
        assert any(pt.get('e1rm_kg') is not None for pt in dc['points'])
        # Projected history has only the 4 UI fields.
        for row in result['trends']['strength_history']:
            assert set(row) == {'date', 'activity_id', 'duration_min', 'description'}
