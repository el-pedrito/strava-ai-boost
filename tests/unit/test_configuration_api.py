"""Unit tests for configuration_api Lambda — Strava deauthorization flow."""

import json
import sys
import os

import pytest
import requests
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

import boto3
from moto import mock_aws

import api.configuration_api as configuration_api
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

    def test_configure_module_persists_athlete_input_enabled(self, user_config_table):
        user_config_table.put_item(Item={
            'user_id': '42',
            'modules_config': {'enduraw': {'enabled': True}},
        })

        result = _configure({'module_id': 'athlete_input', 'enabled': True})

        assert result['statusCode'] == 200
        stored = user_config_table.get_item(Key={'user_id': '42'})['Item']
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


@pytest.fixture
def user_config_table(monkeypatch):
    """Real conditional/nested-path semantics: moto, not a MagicMock."""
    with mock_aws():
        ddb = boto3.resource('dynamodb', region_name='us-east-1')
        table = ddb.create_table(
            TableName=configuration_api.USER_CONFIG_TABLE,
            KeySchema=[{'AttributeName': 'user_id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'user_id', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST',
        )
        monkeypatch.setattr(configuration_api, 'dynamodb', ddb)
        monkeypatch.setattr(configuration_api, 'get_authenticated_user_id', lambda: '42')
        yield table


def _configure(body):
    return configure_module({'body': json.dumps(body)})


class TestConfigureModuleAtomicWrite:
    """configure_module writes only modules_config.<module_id> (no whole-item put)."""

    def test_unrelated_fields_written_concurrently_survive(self, user_config_table, monkeypatch):
        """A preference saved between the old read and write is no longer clobbered."""
        user_config_table.put_item(Item={
            'user_id': '42',
            'user_preferences': {'tone': 'old'},
            'modules_config': {'enduraw': {'enabled': True}},
        })
        real_update = user_config_table.update_item
        table = MagicMock(wraps=user_config_table)

        def concurrent_writer_first(**kwargs):
            # Another request (Preferences save, another module toggle) lands first.
            real_update(
                Key={'user_id': '42'},
                UpdateExpression='SET user_preferences.tone = :t, modules_config.enduraw.wait_time = :w',
                ExpressionAttributeValues={':t': 'new', ':w': '3 minutes'},
            )
            table.update_item.side_effect = None
            table.update_item.wraps = real_update
            return real_update(**kwargs)

        table.update_item.side_effect = concurrent_writer_first
        fake_resource = MagicMock()
        fake_resource.Table.return_value = table
        monkeypatch.setattr(configuration_api, 'dynamodb', fake_resource)

        result = _configure({'module_id': 'athlete_input', 'enabled': True})

        assert result['statusCode'] == 200
        stored = user_config_table.get_item(Key={'user_id': '42'})['Item']
        assert stored['user_preferences'] == {'tone': 'new'}
        assert stored['modules_config']['enduraw'] == {'enabled': True, 'wait_time': '3 minutes'}
        assert stored['modules_config']['athlete_input']['enabled'] is True
        table.put_item.assert_not_called()

    def test_existing_module_keys_are_kept(self, user_config_table):
        user_config_table.put_item(Item={
            'user_id': '42',
            'modules_config': {'campus_coach': {'enabled': True, 'last_sync': '2026-10-01'}},
        })
        result = _configure({'module_id': 'campus_coach', 'enabled': False})

        assert result['statusCode'] == 200
        module = user_config_table.get_item(Key={'user_id': '42'})['Item']['modules_config']['campus_coach']
        assert module['enabled'] is False
        assert module['configured'] is True
        assert module['last_sync'] == '2026-10-01'
        assert module['updated_at']

    def test_missing_modules_config_map_is_created(self, user_config_table):
        user_config_table.put_item(Item={'user_id': '42', 'user_preferences': {'tone': 'x'}})
        result = _configure({'module_id': 'athlete_input', 'enabled': True})

        assert result['statusCode'] == 200
        stored = user_config_table.get_item(Key={'user_id': '42'})['Item']
        assert stored['modules_config']['athlete_input']['enabled'] is True
        assert stored['user_preferences'] == {'tone': 'x'}

    def test_missing_user_item_is_created(self, user_config_table):
        result = _configure({'module_id': 'athlete_input', 'enabled': False})

        assert result['statusCode'] == 200
        stored = user_config_table.get_item(Key={'user_id': '42'})['Item']
        assert stored['modules_config']['athlete_input']['enabled'] is False
        assert stored['modules_config']['athlete_input']['configured'] is True

    def test_enduraw_wait_time_and_response_unchanged(self, user_config_table):
        result = _configure({'module_id': 'enduraw', 'enabled': True, 'config': {'wait_time': '5 minutes'}})

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        body.pop('timestamp')
        assert body == {
            'status': 'configured',
            'module_id': 'enduraw',
            'enabled': True,
            'message': 'Enduraw enabled successfully',
        }
        module = user_config_table.get_item(Key={'user_id': '42'})['Item']['modules_config']['enduraw']
        assert module['wait_time'] == '5 minutes'

    def test_dynamodb_error_returns_500(self, user_config_table, monkeypatch):
        broken = MagicMock()
        broken.Table.return_value.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'x'}}, 'UpdateItem'
        )
        monkeypatch.setattr(configuration_api, 'dynamodb', broken)
        result = _configure({'module_id': 'athlete_input', 'enabled': True})
        assert result['statusCode'] == 500
