"""Caller binding of the preferences API (GET/POST /preferences).

The user is the Cognito ``custom:strava_id`` claim. A query/body ``user_id`` is
only checked against it: a different one is a 403, a missing claim is a 401, and
DEFAULT_USER_ID is never a fallback. DynamoDB is a MagicMock: these tests pin
WHICH key is read or written, and that nothing is touched when the call is denied.
"""

import json
import os
import sys
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from api import user_preferences_api as api  # noqa: E402

CALLER = 'athlete-a'
OTHER = 'athlete-b'


def _context(claim: Optional[str]) -> Dict[str, Any]:
    if claim is None:
        return {'authorizer': {'claims': {'sub': 'some-sub', 'cognito:username': 'someone'}}}
    return {'authorizer': {'claims': {'custom:strava_id': claim}}}


def _get_event(claim: Optional[str], query: Optional[Dict[str, str]]) -> Dict[str, Any]:
    return {'httpMethod': 'GET', 'path': '/preferences', 'queryStringParameters': query,
            'requestContext': _context(claim)}


def _post_event(claim: Optional[str], body: Dict[str, Any]) -> Dict[str, Any]:
    return {'httpMethod': 'POST', 'path': '/preferences', 'body': json.dumps(body),
            'requestContext': _context(claim)}


def _table() -> MagicMock:
    table = MagicMock()
    table.get_item.return_value = {'Item': {'user_id': CALLER, 'user_preferences': {'content_tone': 'casual & friendly'}}}
    return table


class TestGetPreferencesCallerBinding:
    @patch('api.user_preferences_api.dynamodb')
    def test_own_user_id_reads_caller_row(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        response = api.handler(_get_event(CALLER, {'user_id': CALLER}), None)
        assert response['statusCode'] == 200
        table.get_item.assert_called_once_with(Key={'user_id': CALLER})
        body = json.loads(response['body'])
        assert body['success'] is True
        assert body['preferences']['content_tone'] == 'casual & friendly'

    @patch('api.user_preferences_api.dynamodb')
    def test_no_query_user_id_uses_claim(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        response = api.handler(_get_event(CALLER, None), None)
        assert response['statusCode'] == 200
        table.get_item.assert_called_once_with(Key={'user_id': CALLER})

    @patch('api.user_preferences_api.dynamodb')
    def test_empty_query_user_id_uses_claim(self, mock_dynamodb: MagicMock) -> None:
        """The frontend sends ``?user_id=`` when its default id is not configured."""
        table = _table()
        mock_dynamodb.Table.return_value = table
        response = api.handler(_get_event(CALLER, {'user_id': ''}), None)
        assert response['statusCode'] == 200
        table.get_item.assert_called_once_with(Key={'user_id': CALLER})

    @patch('api.user_preferences_api.dynamodb')
    def test_other_user_id_is_403(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        response = api.handler(_get_event(CALLER, {'user_id': OTHER}), None)
        assert response['statusCode'] == 403
        table.get_item.assert_not_called()

    @patch('api.user_preferences_api.dynamodb')
    def test_missing_claim_is_401(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        response = api.handler(_get_event(None, {'user_id': CALLER}), None)
        assert response['statusCode'] == 401
        table.get_item.assert_not_called()

    @patch('api.user_preferences_api.dynamodb')
    def test_missing_request_context_is_401(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        event = {'httpMethod': 'GET', 'path': '/preferences', 'queryStringParameters': {'user_id': CALLER}}
        response = api.handler(event, None)
        assert response['statusCode'] == 401
        table.get_item.assert_not_called()

    @patch('api.user_preferences_api.dynamodb')
    def test_default_user_id_is_never_a_fallback(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        with patch.dict(os.environ, {'DEFAULT_USER_ID': CALLER}):
            response = api.handler(_get_event(None, None), None)
        assert response['statusCode'] == 401
        table.get_item.assert_not_called()

    @patch('api.user_preferences_api.dynamodb')
    def test_malformed_claim_is_401(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        response = api.handler(_get_event('bad id/../x', None), None)
        assert response['statusCode'] == 401
        table.get_item.assert_not_called()


class TestPostPreferencesCallerBinding:
    @patch('api.user_preferences_api.dynamodb')
    def test_own_user_id_writes_caller_row(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        response = api.handler(_post_event(CALLER, {'user_id': CALLER, 'content_tone': 'casual & friendly'}), None)
        assert response['statusCode'] == 200
        assert table.update_item.call_args.kwargs['Key'] == {'user_id': CALLER}
        body = json.loads(response['body'])
        assert body['success'] is True
        assert body['preferences']['content_tone'] == 'casual & friendly'

    @patch('api.user_preferences_api.dynamodb')
    def test_no_body_user_id_writes_caller_row(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        response = api.handler(_post_event(CALLER, {'content_tone': 'casual & friendly'}), None)
        assert response['statusCode'] == 200
        assert table.update_item.call_args.kwargs['Key'] == {'user_id': CALLER}

    @patch('api.user_preferences_api.dynamodb')
    def test_other_user_id_is_403(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        response = api.handler(_post_event(CALLER, {'user_id': OTHER, 'content_tone': 'casual & friendly'}), None)
        assert response['statusCode'] == 403
        table.update_item.assert_not_called()

    @patch('api.user_preferences_api.dynamodb')
    def test_missing_claim_is_401(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        response = api.handler(_post_event(None, {'user_id': CALLER}), None)
        assert response['statusCode'] == 401
        table.update_item.assert_not_called()

    @patch('api.user_preferences_api.dynamodb')
    def test_default_user_id_is_never_a_fallback(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        with patch.dict(os.environ, {'DEFAULT_USER_ID': CALLER}):
            response = api.handler(_post_event(None, {}), None)
        assert response['statusCode'] == 401
        table.update_item.assert_not_called()

    @patch('api.user_preferences_api.dynamodb')
    def test_non_object_body_is_400(self, mock_dynamodb: MagicMock) -> None:
        table = _table()
        mock_dynamodb.Table.return_value = table
        event = {'httpMethod': 'POST', 'path': '/preferences', 'body': json.dumps([CALLER]),
                 'requestContext': _context(CALLER)}
        response = api.handler(event, None)
        assert response['statusCode'] == 400
        table.update_item.assert_not_called()
