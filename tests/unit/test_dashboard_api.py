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
        event = {'httpMethod': 'POST'}
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
