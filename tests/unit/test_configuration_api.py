"""Unit tests for configuration_api Lambda — Strava deauthorization flow."""

import json
import sys
import os

import pytest
import requests
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from api.configuration_api import configure_module, get_modules, revoke_oauth_tokens


VALID_TOKENS = {
    'access_token': 'acc-123',
    'refresh_token': 'ref-123',
    'expires_at': 9999999999,
}


class TestRevokeOAuthTokens:
    """Deauthorize: call Strava, clear the stored secret, degrade gracefully."""

    @patch('api.configuration_api.requests.post')
    @patch('api.configuration_api.secretsmanager')
    def test_revoke_calls_strava_and_clears_secret(self, mock_sm, mock_post):
        mock_sm.get_secret_value.return_value = {'SecretString': json.dumps(VALID_TOKENS)}
        mock_post.return_value = MagicMock(status_code=200)

        result = revoke_oauth_tokens()

        # Strava deauthorize called with the bearer token
        args, kwargs = mock_post.call_args
        assert args[0] == 'https://www.strava.com/oauth/deauthorize'
        assert kwargs['headers']['Authorization'] == 'Bearer acc-123'
        # Secret cleared
        mock_sm.put_secret_value.assert_called_once()
        assert mock_sm.put_secret_value.call_args.kwargs['SecretString'] == '{}'
        assert result['statusCode'] == 200
        assert json.loads(result['body'])['status'] == 'revoked'

    @patch('api.configuration_api.requests.post')
    @patch('api.configuration_api.secretsmanager')
    def test_clears_secret_even_if_strava_call_fails(self, mock_sm, mock_post):
        # Defensive: Strava network error must NOT block clearing local tokens
        mock_sm.get_secret_value.return_value = {'SecretString': json.dumps(VALID_TOKENS)}
        mock_post.side_effect = requests.RequestException("network down")

        result = revoke_oauth_tokens()

        mock_sm.put_secret_value.assert_called_once_with(
            SecretId='test-oauth-secret', SecretString='{}'
        )
        assert result['statusCode'] == 200
        assert json.loads(result['body'])['status'] == 'revoked'

    @patch('api.configuration_api.secretsmanager')
    def test_already_disconnected_when_no_access_token(self, mock_sm):
        mock_sm.get_secret_value.return_value = {'SecretString': '{}'}

        result = revoke_oauth_tokens()

        mock_sm.put_secret_value.assert_not_called()
        assert result['statusCode'] == 200
        assert json.loads(result['body'])['status'] == 'already_disconnected'

    @patch('api.configuration_api.secretsmanager')
    def test_resource_not_found_is_already_disconnected(self, mock_sm):
        mock_sm.get_secret_value.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}}, 'GetSecretValue'
        )

        result = revoke_oauth_tokens()

        assert result['statusCode'] == 200
        assert json.loads(result['body'])['status'] == 'already_disconnected'

    @patch('api.configuration_api.secretsmanager')
    def test_other_client_error_returns_500(self, mock_sm):
        mock_sm.get_secret_value.side_effect = ClientError(
            {'Error': {'Code': 'AccessDeniedException'}}, 'GetSecretValue'
        )

        result = revoke_oauth_tokens()

        assert result['statusCode'] == 500


class TestAthleteInputModuleConfiguration:
    """The athlete-input switch is a normal disabled-by-default module flag."""

    @patch('api.configuration_api.get_authenticated_user_id', return_value='42')
    @patch('api.configuration_api.dynamodb')
    def test_get_modules_lists_athlete_input_disabled_by_default(self, mock_dynamodb, _mock_user):
        table = MagicMock()
        table.get_item.return_value = {'Item': {'user_id': '42'}}
        mock_dynamodb.Table.return_value = table

        result = get_modules()

        assert result['statusCode'] == 200
        module = json.loads(result['body'])['modules']['athlete_input']
        assert module['enabled'] is False
        assert module['configured'] is True
        assert module['requires_credentials'] is False

    @patch('api.configuration_api.get_authenticated_user_id', return_value='42')
    @patch('api.configuration_api.dynamodb')
    def test_configure_module_persists_athlete_input_enabled(self, mock_dynamodb, _mock_user):
        table = MagicMock()
        table.get_item.return_value = {'Item': {
            'user_id': '42',
            'modules_config': {'enduraw': {'enabled': True}},
        }}
        mock_dynamodb.Table.return_value = table

        result = configure_module({
            'body': json.dumps({'module_id': 'athlete_input', 'enabled': True}),
        })

        assert result['statusCode'] == 200
        stored = table.put_item.call_args.kwargs['Item']
        assert stored['modules_config']['athlete_input']['enabled'] is True
        assert stored['modules_config']['athlete_input']['configured'] is True
        assert stored['modules_config']['enduraw'] == {'enabled': True}

    @patch('api.configuration_api.get_authenticated_user_id')
    @patch('api.configuration_api.dynamodb')
    def test_configure_module_rejects_non_boolean_athlete_input_flag(
        self, mock_dynamodb, mock_user
    ):
        result = configure_module({
            'body': json.dumps({'module_id': 'athlete_input', 'enabled': 'true'}),
        })

        assert result['statusCode'] == 400
        mock_user.assert_not_called()
        mock_dynamodb.Table.assert_not_called()

    @patch('api.configuration_api.get_authenticated_user_id')
    @patch('api.configuration_api.dynamodb')
    def test_configure_module_requires_athlete_input_flag(self, mock_dynamodb, mock_user):
        result = configure_module({
            'body': json.dumps({'module_id': 'athlete_input'}),
        })

        assert result['statusCode'] == 400
        mock_user.assert_not_called()
        mock_dynamodb.Table.assert_not_called()
