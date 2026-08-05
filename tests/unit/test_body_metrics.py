"""Unit tests for structured body metrics (body_weight_kg, height_cm).

Covers WP4 of docs/design/coach-figures-integrity.md:
- API validation of the two flat fields (bounds accepted / rejected, GET exposes them)
- opportunistic seeding of body_weight_kg from the Strava athlete profile
- a manual entry is authoritative and never overwritten by Strava
- absence of the fields is tolerated end to end
"""

import json
import os
import sys
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from api.user_preferences_api import get_user_preferences, update_user_preferences
from processing.activity_fetcher import persist_body_weight_from_strava


def _post_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build an API Gateway POST event for the preferences API."""
    return {'httpMethod': 'POST', 'path': '/preferences', 'body': json.dumps(payload)}


def _get_event(user_id: str = 'athlete1') -> Dict[str, Any]:
    """Build an API Gateway GET event for the preferences API."""
    return {'httpMethod': 'GET', 'path': '/preferences', 'queryStringParameters': {'user_id': user_id}}


class TestBodyMetricsApiValidation:
    """The preferences API validates the two flat body-metrics fields."""

    @patch('api.user_preferences_api.dynamodb')
    def test_body_weight_within_bounds_accepted(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1', 'body_weight_kg': 92}))
        assert response['statusCode'] == 200
        prefs = json.loads(response['body'])['preferences']
        assert prefs['body_weight_kg'] == 92

    @patch('api.user_preferences_api.dynamodb')
    def test_body_weight_lower_bound_accepted(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1', 'body_weight_kg': 30}))
        assert response['statusCode'] == 200

    @patch('api.user_preferences_api.dynamodb')
    def test_body_weight_upper_bound_accepted(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1', 'body_weight_kg': 250}))
        assert response['statusCode'] == 200

    @patch('api.user_preferences_api.dynamodb')
    def test_body_weight_below_bound_rejected(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1', 'body_weight_kg': 29}))
        assert response['statusCode'] == 400

    @patch('api.user_preferences_api.dynamodb')
    def test_body_weight_above_bound_rejected(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1', 'body_weight_kg': 251}))
        assert response['statusCode'] == 400

    @patch('api.user_preferences_api.dynamodb')
    def test_body_weight_non_numeric_rejected(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1', 'body_weight_kg': 'heavy'}))
        assert response['statusCode'] == 400

    @patch('api.user_preferences_api.dynamodb')
    def test_body_weight_decimal_accepted(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1', 'body_weight_kg': 72.5}))
        assert response['statusCode'] == 200
        prefs = json.loads(response['body'])['preferences']
        assert prefs['body_weight_kg'] == 72.5

    @patch('api.user_preferences_api.dynamodb')
    def test_height_within_bounds_accepted(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1', 'height_cm': 192}))
        assert response['statusCode'] == 200
        prefs = json.loads(response['body'])['preferences']
        assert prefs['height_cm'] == 192

    @patch('api.user_preferences_api.dynamodb')
    def test_height_lower_bound_accepted(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1', 'height_cm': 100}))
        assert response['statusCode'] == 200

    @patch('api.user_preferences_api.dynamodb')
    def test_height_upper_bound_accepted(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1', 'height_cm': 250}))
        assert response['statusCode'] == 200

    @patch('api.user_preferences_api.dynamodb')
    def test_height_below_bound_rejected(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1', 'height_cm': 99}))
        assert response['statusCode'] == 400

    @patch('api.user_preferences_api.dynamodb')
    def test_height_above_bound_rejected(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1', 'height_cm': 251}))
        assert response['statusCode'] == 400

    @patch('api.user_preferences_api.dynamodb')
    def test_absence_of_fields_tolerated_on_save(self, mock_dynamodb: MagicMock) -> None:
        mock_dynamodb.Table.return_value = MagicMock()
        response = update_user_preferences(_post_event({'user_id': 'athlete1'}))
        assert response['statusCode'] == 200
        prefs = json.loads(response['body'])['preferences']
        assert 'body_weight_kg' not in prefs
        assert 'height_cm' not in prefs


class TestBodyMetricsApiGet:
    """GET returns the two fields, including None when absent."""

    @patch('api.user_preferences_api.dynamodb')
    def test_get_returns_stored_values(self, mock_dynamodb: MagicMock) -> None:
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'user_id': 'athlete1',
                'user_preferences': {'body_weight_kg': Decimal('92'), 'height_cm': Decimal('192')},
            }
        }
        mock_dynamodb.Table.return_value = mock_table
        response = get_user_preferences(_get_event())
        assert response['statusCode'] == 200
        prefs = json.loads(response['body'])['preferences']
        assert prefs['body_weight_kg'] == 92
        assert prefs['height_cm'] == 192

    @patch('api.user_preferences_api.dynamodb')
    def test_get_returns_none_when_absent(self, mock_dynamodb: MagicMock) -> None:
        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {'user_id': 'athlete1', 'user_preferences': {}}}
        mock_dynamodb.Table.return_value = mock_table
        response = get_user_preferences(_get_event())
        assert response['statusCode'] == 200
        prefs = json.loads(response['body'])['preferences']
        assert prefs['body_weight_kg'] is None
        assert prefs['height_cm'] is None


class TestStravaWeightSeeding:
    """activity_fetcher seeds body_weight_kg from Strava without overwriting a manual entry."""

    @patch('processing.activity_fetcher.dynamodb')
    def test_seeds_when_preferences_map_absent(self, mock_dynamodb: MagicMock) -> None:
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        user_config: Dict[str, Any] = {'user_id': 'athlete1'}

        persist_body_weight_from_strava('athlete1', {'weight': 92}, user_config)

        mock_table.update_item.assert_called_once()
        kwargs = mock_table.update_item.call_args.kwargs
        assert kwargs['UpdateExpression'] == 'SET user_preferences = :prefs'
        assert kwargs['ExpressionAttributeValues'][':prefs']['body_weight_kg'] == Decimal('92')
        assert user_config['user_preferences']['body_weight_kg'] == Decimal('92')

    @patch('processing.activity_fetcher.dynamodb')
    def test_seeds_when_preferences_exist_without_weight(self, mock_dynamodb: MagicMock) -> None:
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        user_config: Dict[str, Any] = {'user_id': 'athlete1', 'user_preferences': {'max_hr': 190}}

        persist_body_weight_from_strava('athlete1', {'weight': 92}, user_config)

        mock_table.update_item.assert_called_once()
        kwargs = mock_table.update_item.call_args.kwargs
        assert kwargs['UpdateExpression'] == 'SET user_preferences.body_weight_kg = :w'
        assert kwargs['ExpressionAttributeValues'][':w'] == Decimal('92')

    @patch('processing.activity_fetcher.dynamodb')
    def test_does_not_overwrite_manual_entry(self, mock_dynamodb: MagicMock) -> None:
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        user_config: Dict[str, Any] = {
            'user_id': 'athlete1',
            'user_preferences': {'body_weight_kg': Decimal('80')},
        }

        persist_body_weight_from_strava('athlete1', {'weight': 92}, user_config)

        mock_table.update_item.assert_not_called()
        assert user_config['user_preferences']['body_weight_kg'] == Decimal('80')

    @patch('processing.activity_fetcher.dynamodb')
    def test_no_seed_when_strava_weight_missing(self, mock_dynamodb: MagicMock) -> None:
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        user_config: Dict[str, Any] = {'user_id': 'athlete1'}

        persist_body_weight_from_strava('athlete1', {'ftp': 250}, user_config)

        mock_table.update_item.assert_not_called()

    @patch('processing.activity_fetcher.dynamodb')
    def test_no_seed_when_profile_none(self, mock_dynamodb: MagicMock) -> None:
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        user_config: Dict[str, Any] = {'user_id': 'athlete1'}

        persist_body_weight_from_strava('athlete1', None, user_config)

        mock_table.update_item.assert_not_called()

    @patch('processing.activity_fetcher.dynamodb')
    def test_no_seed_when_strava_weight_out_of_bounds(self, mock_dynamodb: MagicMock) -> None:
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        user_config: Dict[str, Any] = {'user_id': 'athlete1'}

        persist_body_weight_from_strava('athlete1', {'weight': 500}, user_config)

        mock_table.update_item.assert_not_called()

    @patch('processing.activity_fetcher.dynamodb')
    def test_no_seed_when_strava_weight_not_numeric(self, mock_dynamodb: MagicMock) -> None:
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        user_config: Dict[str, Any] = {'user_id': 'athlete1'}

        persist_body_weight_from_strava('athlete1', {'weight': 'unknown'}, user_config)

        mock_table.update_item.assert_not_called()

    @patch('processing.activity_fetcher.dynamodb')
    def test_concurrent_manual_write_is_not_clobbered(self, mock_dynamodb: MagicMock) -> None:
        mock_table = MagicMock()
        mock_table.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'exists'}},
            'UpdateItem',
        )
        mock_dynamodb.Table.return_value = mock_table
        user_config: Dict[str, Any] = {'user_id': 'athlete1', 'user_preferences': {'max_hr': 190}}

        persist_body_weight_from_strava('athlete1', {'weight': 92}, user_config)

        mock_table.update_item.assert_called_once()
