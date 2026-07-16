"""Unit tests for dashboard_api Lambda"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from api.dashboard_api import (
    handler,
    validate_request,
    get_activity_type_breakdown,
    get_cached_or_compute,
    _cache,
    _cache_ttl,
    _build_strength_progression,
)


class TestValidateRequest:
    """Test request validation"""

    def test_valid_get_request(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {}}
        assert validate_request(event) is None

    def test_valid_options_request(self):
        event = {'httpMethod': 'OPTIONS'}
        assert validate_request(event) is None

    def test_post_not_allowed(self):
        event = {'httpMethod': 'PUT'}
        result = validate_request(event)
        assert 'not allowed' in result

    def test_valid_days_param(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'days': '30'}}
        assert validate_request(event) is None

    def test_days_too_large(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'days': '500'}}
        result = validate_request(event)
        assert 'between 1 and 365' in result

    def test_days_zero(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'days': '0'}}
        result = validate_request(event)
        assert 'between 1 and 365' in result

    def test_days_not_integer(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'days': 'abc'}}
        result = validate_request(event)
        assert 'valid integer' in result

    def test_valid_limit(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'limit': '50'}}
        assert validate_request(event) is None

    def test_limit_too_large(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'limit': '200'}}
        result = validate_request(event)
        assert 'between 1 and 100' in result

    def test_limit_not_integer(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'limit': 'abc'}}
        result = validate_request(event)
        assert 'valid integer' in result

    def test_valid_offset(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'offset': '10'}}
        assert validate_request(event) is None

    def test_negative_offset(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'offset': '-1'}}
        result = validate_request(event)
        assert 'non-negative' in result

    def test_null_query_params(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': None}
        assert validate_request(event) is None


class TestHandlerRouting:
    """Test handler routes to correct endpoint"""

    def test_options_returns_200(self):
        event = {'httpMethod': 'OPTIONS', 'path': '/dashboard/stats'}
        response = handler(event, None)
        assert response['statusCode'] == 200

    @patch('api.dashboard_api.get_dashboard_stats')
    def test_stats_route(self, mock_stats):
        mock_stats.return_value = {'total': 10}
        event = {
            'httpMethod': 'GET',
            'path': '/dashboard/stats',
            'queryStringParameters': {},
        }
        response = handler(event, None)
        assert response['statusCode'] == 200
        mock_stats.assert_called_once()

    @patch('api.dashboard_api.get_activity_history')
    def test_activities_route(self, mock_history):
        mock_history.return_value = {'activities': []}
        event = {
            'httpMethod': 'GET',
            'path': '/dashboard/activities',
            'queryStringParameters': {},
        }
        response = handler(event, None)
        assert response['statusCode'] == 200

    @patch('api.dashboard_api.get_system_stats')
    def test_system_route(self, mock_system):
        mock_system.return_value = {'queue_depth': 0}
        event = {
            'httpMethod': 'GET',
            'path': '/dashboard/system',
            'queryStringParameters': {},
        }
        response = handler(event, None)
        assert response['statusCode'] == 200

    def test_unknown_route_returns_404(self):
        event = {
            'httpMethod': 'GET',
            'path': '/dashboard/unknown',
            'queryStringParameters': {},
        }
        response = handler(event, None)
        assert response['statusCode'] == 404

    def test_invalid_method_returns_400(self):
        event = {
            'httpMethod': 'DELETE',
            'path': '/dashboard/stats',
            'queryStringParameters': {},
        }
        response = handler(event, None)
        assert response['statusCode'] == 400


class TestGetActivityTypeBreakdown:
    """Test activity type aggregation"""

    def test_single_type(self):
        activities = [
            {'activity_type': 'Run'},
            {'activity_type': 'Run'},
            {'activity_type': 'Run'},
        ]
        result = get_activity_type_breakdown(activities)
        assert result == {'Run': 3}

    def test_multiple_types(self):
        activities = [
            {'activity_type': 'Run'},
            {'activity_type': 'Ride'},
            {'activity_type': 'Run'},
            {'activity_type': 'Swim'},
        ]
        result = get_activity_type_breakdown(activities)
        assert result == {'Run': 2, 'Ride': 1, 'Swim': 1}

    def test_missing_type_defaults_unknown(self):
        activities = [{'other_field': 'value'}]
        result = get_activity_type_breakdown(activities)
        assert result == {'Unknown': 1}

    def test_empty_list(self):
        assert get_activity_type_breakdown([]) == {}


class TestCache:
    """Test caching mechanism"""

    def setup_method(self):
        _cache.clear()
        _cache_ttl.clear()

    def test_cache_miss_computes(self):
        counter = {'calls': 0}

        def compute():
            counter['calls'] += 1
            return 42

        result = get_cached_or_compute('test_key', compute)
        assert result == 42
        assert counter['calls'] == 1

    def test_cache_hit_reuses(self):
        counter = {'calls': 0}

        def compute():
            counter['calls'] += 1
            return 42

        get_cached_or_compute('test_key', compute)
        result = get_cached_or_compute('test_key', compute)
        assert result == 42
        assert counter['calls'] == 1  # Only called once


class TestBuildStrengthProgression:
    """Test per-exercise strength progression aggregation."""

    def test_empty(self):
        assert _build_strength_progression([]) == []

    def test_entries_without_parsed_sets_ignored(self):
        entries = [{'date': '2026-07-01', 'description': 'DC 4x8'}]
        assert _build_strength_progression(entries) == []

    def test_aggregates_per_exercise_sorted_by_sessions(self):
        entries = [
            {'date': '2026-07-01', 'parsed_sets': [
                {'exercise': 'Développé couché', 'sets': 4, 'reps': 8, 'weight_kg': 80},
                {'exercise': 'Tractions', 'sets': 4, 'reps': 10, 'weight_kg': None},
            ]},
            {'date': '2026-07-08', 'parsed_sets': [
                {'exercise': 'Développé couché', 'sets': 4, 'reps': 8, 'weight_kg': 82.5},
            ]},
        ]
        result = _build_strength_progression(entries)
        # DC has 2 sessions, Tractions 1 → DC first
        assert result[0]['exercise'] == 'Développé couché'
        assert result[0]['sessions'] == 2
        assert result[0]['points'][0] == {'date': '2026-07-01', 'top_weight_kg': 80.0, 'volume_kg': 2560.0}
        assert result[0]['points'][1]['top_weight_kg'] == 82.5
        # Bodyweight exercise → weight/volume None
        tractions = next(e for e in result if e['exercise'] == 'Tractions')
        assert tractions['points'][0]['top_weight_kg'] is None
        assert tractions['points'][0]['volume_kg'] is None

    def test_same_day_merges_max_weight_and_summed_volume(self):
        entries = [
            {'date': '2026-07-01', 'parsed_sets': [
                {'exercise': 'Squat', 'sets': 3, 'reps': 5, 'weight_kg': 100},
            ]},
            {'date': '2026-07-01', 'parsed_sets': [
                {'exercise': 'Squat', 'sets': 2, 'reps': 3, 'weight_kg': 110},
            ]},
        ]
        result = _build_strength_progression(entries)
        assert len(result) == 1
        pts = result[0]['points']
        assert len(pts) == 1  # merged into one day
        assert pts[0]['top_weight_kg'] == 110.0
        assert pts[0]['volume_kg'] == 3 * 5 * 100 + 2 * 3 * 110
