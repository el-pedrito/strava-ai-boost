"""Garbage strength_history must not break /coach/summary.

Asserts: HTTP 200, body parses with a STRICT JSON parser (parse_constant raises
on NaN/Infinity), the non-strength ("running") trends are byte-for-byte identical
to a baseline whose strength_history is empty (with real run activities seeded so
the comparison is not all zeros), the strength builders degrade to [] / None
rather than raising, a non-finite value injected by a builder is sanitised to
null in the HTTP body, and the valid Squat row in the garbage fixture still
yields a Squat progression point without a "Failed to build" warning.
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from api.dashboard_api import get_coach_summary, handler  # noqa: E402


def _raise_constant(value):
    """parse_constant hook: json.loads calls it for NaN/Infinity/-Infinity.

    Raising here makes json.loads reject any non-standard token, so a passing
    parse proves the body is strict JSON (no bare NaN/Infinity).
    """
    raise AssertionError(f"non-strict JSON constant in body: {value!r}")


def _strict_loads(body):
    return json.loads(body, parse_constant=_raise_constant)


def _recent_runs(n=3):
    """A few recent Run activities so the running trends are non-zero."""
    now = datetime.now(tz=timezone.utc)
    runs = []
    for i in range(n):
        d = (now - timedelta(days=2 + i * 7)).isoformat()
        runs.append({
            'activity_id': f'run-{i}',
            'user_id': '42',
            'activity_type': 'Run',
            'distance': 10000 + i * 500,
            'moving_time': 3000 + i * 60,
            'start_date': d,
            'created_at': d,
        })
    return runs


def _mock_tables(strength_entries, run_activities=None):
    activities_table = MagicMock()
    activities_table.query.return_value = {'Items': run_activities or []}
    activities_table.scan.return_value = {'Items': run_activities or []}
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


# A payload mixing every shape the normalizer and builders must survive. The
# last row carries a VALID Squat set (3x5 @100) that must still produce output.
GARBAGE_ENTRIES = [
    "abc",
    {},
    None,
    42,
    {'date': None, 'parsed_sets': []},
    {'date': 'not-a-date', 'parsed_sets': []},
    {'date': '2026-13-99', 'parsed_sets': []},
    {'date': '20261013', 'parsed_sets': []},        # no dashes -> dropped (item 6)
    {'date': '2026-W42-1', 'parsed_sets': []},      # ISO week -> dropped (item 6)
    {'date': '2026-10-13', 'parsed_sets': 'not-a-list'},
    {'date': '2026-10-13', 'parsed_sets': [None, 'x', {}, {'exercise': ''}]},
    {'date': '2026-10-13', 'parsed_sets': [
        {'exercise': 'Squat', 'sets_detail': 'bad', 'sets': 'abc', 'reps': 'xyz', 'weight_kg': 'nope'},
    ]},
    {'date': '2026-10-06', 'activity_id': 'sq1', 'parsed_sets': [
        {'exercise': 'Squat', 'sets_detail': [{'reps': 5, 'weight_kg': 100}] * 3}]},
    {'date': '2026-10-13', 'activity_id': 'sq2', 'total_sets': 'abc', 'total_reps': None,
     'volume_kg': 'bad', 'parsed_sets': [
        {'exercise': 'Squat', 'sets_detail': [{'reps': 5, 'weight_kg': 100}] * 3,
         'weight_kg': 100, 'sets': 3, 'reps': 5}]},
]


class TestGarbageIsolation:
    @patch('api.dashboard_api.dynamodb')
    def test_handler_returns_200_and_strict_json(self, mock_dynamo):
        mock_dynamo.Table.side_effect = _mock_tables(GARBAGE_ENTRIES)
        event = {'httpMethod': 'GET', 'path': '/coach/summary',
                 'requestContext': {'authorizer': {'claims': {'custom:strava_id': '42'}}}}
        resp = handler(event, None)
        assert resp['statusCode'] == 200
        # Strict parse: parse_constant raises on any NaN/Infinity token.
        body = _strict_loads(resp['body'])
        assert body['schema_version'] == 1

    @patch('api.dashboard_api.dynamodb')
    def test_nan_from_builder_is_sanitised_to_null(self, mock_dynamo):
        """A builder emitting a NaN must not reach the body as a bare token: the
        responses sanitizer maps it to null and the strict parser still passes."""
        mock_dynamo.Table.side_effect = _mock_tables(GARBAGE_ENTRIES)
        event = {'httpMethod': 'GET', 'path': '/coach/summary',
                 'requestContext': {'authorizer': {'claims': {'custom:strava_id': '42'}}}}
        with patch(
            'api.dashboard_api._build_strength_sessions',
            return_value=[{'date': '2026-10-13', 'tonnage_kg': float('nan')}],
        ):
            resp = handler(event, None)
        assert resp['statusCode'] == 200
        body = _strict_loads(resp['body'])  # raises if a NaN token survived
        sessions = body['trends']['strength_sessions']
        assert sessions and sessions[0]['tonnage_kg'] is None

    @patch('api.dashboard_api.dynamodb')
    def test_running_trends_identical_to_empty_baseline(self, mock_dynamo):
        runs = _recent_runs()
        # Baseline: empty strength history, same run activities.
        mock_dynamo.Table.side_effect = _mock_tables([], run_activities=runs)
        baseline = get_coach_summary('42')

        # Garbage strength history, everything else identical.
        mock_dynamo.Table.side_effect = _mock_tables(GARBAGE_ENTRIES, run_activities=runs)
        garbage = get_coach_summary('42')

        strength_keys = {
            'strength_history', 'strength_progression',
            'strength_sessions', 'strength_insights',
        }
        base_running = {k: v for k, v in baseline['trends'].items() if k not in strength_keys}
        garb_running = {k: v for k, v in garbage['trends'].items() if k not in strength_keys}
        # The runs produce non-zero volume, so the equality is not vacuous.
        assert any(v > 0 for v in base_running['weekly_volume_km'])
        assert base_running == garb_running
        # And the whole non-trends top level is unchanged too.
        base_top = {k: v for k, v in baseline.items() if k != 'trends'}
        garb_top = {k: v for k, v in garbage.items() if k != 'trends'}
        assert base_top == garb_top

    @patch('api.dashboard_api.dynamodb')
    def test_strength_builders_degrade_gracefully(self, mock_dynamo, caplog):
        import logging
        mock_dynamo.Table.side_effect = _mock_tables(GARBAGE_ENTRIES)
        with caplog.at_level(logging.WARNING):
            result = get_coach_summary('42')
        trends = result['trends']
        assert isinstance(trends['strength_history'], list)
        assert isinstance(trends['strength_progression'], list)
        assert isinstance(trends['strength_sessions'], list)
        assert isinstance(trends['strength_insights'], dict)
        # The valid Squat rows (two sessions) still produce a progression entry.
        squat = next(
            (p for p in trends['strength_progression'] if p['exercise'] == 'Squat'), None
        )
        assert squat is not None
        assert any(pt.get('top_weight_kg') == 100 for pt in squat['points'])
        # Squat has >= 2 distinct sessions -> a records row exists.
        assert any(r['exercise'] == 'Squat' for r in trends['strength_insights']['records'])
        # No builder hit its except: no "Failed to build" warning on garbage.
        assert not any('Failed to build' in rec.message for rec in caplog.records)

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

    @patch('api.dashboard_api.dynamodb')
    def test_handler_returns_500_with_cors_when_dumps_raises(self, mock_dynamo):
        """Item 18: if json.dumps raises ValueError serializing the success body
        (e.g. a non-finite that slipped past the sanitizer, allow_nan=False), the
        handler fails closed to a 500 that still carries CORS headers.

        Only the success serialization (allow_nan=False) is forced to raise; the
        error path's own json.dumps still works so the 500 body is produced.
        """
        import shared.responses as responses_mod
        real_dumps = json.dumps

        def _dumps(obj, *args, **kwargs):
            if kwargs.get('allow_nan') is False:
                raise ValueError('simulated non-finite serialization failure')
            return real_dumps(obj, *args, **kwargs)

        mock_dynamo.Table.side_effect = _mock_tables([])
        event = {'httpMethod': 'GET', 'path': '/coach/summary',
                 'requestContext': {'authorizer': {'claims': {'custom:strava_id': '42'}}}}
        with patch.object(responses_mod.json, 'dumps', side_effect=_dumps):
            resp = handler(event, None)
        assert resp['statusCode'] == 500
        assert resp['headers'].get('Access-Control-Allow-Origin') == '*'
        assert 'Content-Type' in resp['headers']
