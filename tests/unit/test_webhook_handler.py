"""Unit tests for webhook_handler Lambda"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from webhooks.webhook_handler import (
    handler,
    handle_webhook_verification,
    handle_webhook_notification,
    validate_webhook_data,
    is_enhancement_paused,
)


class TestValidateWebhookData:
    """Test webhook data validation (pure function)"""

    def test_valid_activity_create(self):
        data = {
            'object_type': 'activity',
            'object_id': 12345678,
            'aspect_type': 'create',
            'owner_id': 67890,
            'event_time': 1704268800
        }
        assert validate_webhook_data(data) is True

    def test_valid_activity_update(self):
        data = {
            'object_type': 'activity',
            'object_id': 12345678,
            'aspect_type': 'update',
            'owner_id': 67890,
        }
        assert validate_webhook_data(data) is True

    def test_valid_activity_delete(self):
        data = {
            'object_type': 'activity',
            'object_id': 12345678,
            'aspect_type': 'delete',
            'owner_id': 67890,
        }
        assert validate_webhook_data(data) is True

    def test_valid_athlete_event(self):
        data = {
            'object_type': 'athlete',
            'object_id': 12345678,
            'aspect_type': 'update',
            'owner_id': 67890,
        }
        assert validate_webhook_data(data) is True

    def test_missing_object_type(self):
        data = {'object_id': 123, 'aspect_type': 'create', 'owner_id': 456}
        assert validate_webhook_data(data) is False

    def test_missing_object_id(self):
        data = {'object_type': 'activity', 'aspect_type': 'create', 'owner_id': 456}
        assert validate_webhook_data(data) is False

    def test_missing_aspect_type(self):
        data = {'object_type': 'activity', 'object_id': 123, 'owner_id': 456}
        assert validate_webhook_data(data) is False

    def test_missing_owner_id(self):
        data = {'object_type': 'activity', 'object_id': 123, 'aspect_type': 'create'}
        assert validate_webhook_data(data) is False

    def test_invalid_object_type(self):
        data = {
            'object_type': 'unknown',
            'object_id': 123,
            'aspect_type': 'create',
            'owner_id': 456,
        }
        assert validate_webhook_data(data) is False

    def test_invalid_aspect_type(self):
        data = {
            'object_type': 'activity',
            'object_id': 123,
            'aspect_type': 'invalid',
            'owner_id': 456,
        }
        assert validate_webhook_data(data) is False

    def test_string_ids_valid(self):
        data = {
            'object_type': 'activity',
            'object_id': '12345678',
            'aspect_type': 'create',
            'owner_id': '67890',
        }
        assert validate_webhook_data(data) is True

    def test_non_numeric_object_id(self):
        data = {
            'object_type': 'activity',
            'object_id': 'abc',
            'aspect_type': 'create',
            'owner_id': 456,
        }
        assert validate_webhook_data(data) is False

    def test_invalid_event_time(self):
        data = {
            'object_type': 'activity',
            'object_id': 123,
            'aspect_type': 'create',
            'owner_id': 456,
            'event_time': 'not-a-number',
        }
        assert validate_webhook_data(data) is False

    def test_empty_data(self):
        assert validate_webhook_data({}) is False


class TestHandlerRouting:
    """Test handler routes GET/POST/other correctly"""

    @patch('webhooks.webhook_handler.handle_webhook_verification')
    def test_get_routes_to_verification(self, mock_verify):
        mock_verify.return_value = {'statusCode': 200, 'body': '{}'}
        event = {'httpMethod': 'GET'}
        handler(event, None)
        mock_verify.assert_called_once_with(event)

    @patch('webhooks.webhook_handler.handle_webhook_notification')
    def test_post_routes_to_notification(self, mock_notify):
        mock_notify.return_value = {'statusCode': 200, 'body': '{}'}
        event = {'httpMethod': 'POST'}
        handler(event, None)
        mock_notify.assert_called_once_with(event)

    def test_unsupported_method_returns_405(self):
        event = {'httpMethod': 'PUT'}
        response = handler(event, None)
        assert response['statusCode'] == 405

    def test_delete_returns_405(self):
        event = {'httpMethod': 'DELETE'}
        response = handler(event, None)
        assert response['statusCode'] == 405


class TestWebhookVerification:
    """Test webhook verification flow"""

    @patch('webhooks.webhook_handler.validate_verify_token', return_value=True)
    def test_valid_verification(self, mock_validate):
        event = {
            'queryStringParameters': {
                'hub.mode': 'subscribe',
                'hub.challenge': 'test_challenge_abc',
                'hub.verify_token': 'my-token',
            }
        }
        response = handle_webhook_verification(event)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['hub.challenge'] == 'test_challenge_abc'

    @patch('webhooks.webhook_handler.validate_verify_token', return_value=False)
    def test_invalid_token_returns_403(self, mock_validate):
        event = {
            'queryStringParameters': {
                'hub.mode': 'subscribe',
                'hub.challenge': 'challenge',
                'hub.verify_token': 'wrong-token',
            }
        }
        response = handle_webhook_verification(event)
        assert response['statusCode'] == 403

    @patch('webhooks.webhook_handler.validate_verify_token', return_value=True)
    def test_missing_challenge_returns_400(self, mock_validate):
        event = {
            'queryStringParameters': {
                'hub.mode': 'subscribe',
                'hub.verify_token': 'token',
            }
        }
        response = handle_webhook_verification(event)
        assert response['statusCode'] == 400

    @patch('webhooks.webhook_handler.validate_verify_token', return_value=True)
    def test_wrong_mode_returns_400(self, mock_validate):
        event = {
            'queryStringParameters': {
                'hub.mode': 'unsubscribe',
                'hub.challenge': 'challenge',
                'hub.verify_token': 'token',
            }
        }
        response = handle_webhook_verification(event)
        assert response['statusCode'] == 400

    @patch('webhooks.webhook_handler.validate_verify_token', return_value=True)
    def test_null_query_params(self, mock_validate):
        event = {'queryStringParameters': None}
        response = handle_webhook_verification(event)
        # Should handle gracefully (no crash)
        assert response['statusCode'] in (400, 403)


class TestWebhookNotification:
    """Test webhook notification processing"""

    @patch('webhooks.webhook_handler.get_sqs_client')
    @patch('webhooks.webhook_handler.verify_webhook_signature', return_value=True)
    @patch('webhooks.webhook_handler.is_enhancement_paused', return_value=False)
    def test_activity_create_queued(self, mock_paused, mock_sig, mock_sqs):
        mock_client = MagicMock()
        mock_sqs.return_value = mock_client

        webhook_body = {
            'object_type': 'activity',
            'object_id': 12345678,
            'aspect_type': 'create',
            'owner_id': 67890,
            'event_time': 1704268800,
        }
        event = {
            'body': json.dumps(webhook_body),
            'headers': {},
        }

        response = handle_webhook_notification(event)
        assert response['statusCode'] == 200
        mock_client.send_message.assert_called_once()

        # Verify message content
        call_kwargs = mock_client.send_message.call_args[1]
        msg_body = json.loads(call_kwargs['MessageBody'])
        assert msg_body['activity_id'] == '12345678'
        assert msg_body['user_id'] == '67890'

    @patch('webhooks.webhook_handler.verify_webhook_signature', return_value=False)
    def test_invalid_signature_returns_401(self, mock_sig):
        event = {
            'body': json.dumps({'object_type': 'activity', 'object_id': 1, 'aspect_type': 'create', 'owner_id': 2}),
            'headers': {},
        }
        response = handle_webhook_notification(event)
        assert response['statusCode'] == 401

    @patch('webhooks.webhook_handler.get_sqs_client')
    @patch('webhooks.webhook_handler.verify_webhook_signature', return_value=True)
    @patch('webhooks.webhook_handler.is_enhancement_paused', return_value=True)
    def test_paused_user_acknowledged(self, mock_paused, mock_sig, mock_sqs):
        webhook_body = {
            'object_type': 'activity',
            'object_id': 123,
            'aspect_type': 'create',
            'owner_id': 456,
        }
        event = {'body': json.dumps(webhook_body), 'headers': {}}
        response = handle_webhook_notification(event)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'acknowledged_paused'
        mock_sqs.return_value.send_message.assert_not_called()

    @patch('webhooks.webhook_handler.verify_webhook_signature', return_value=True)
    @patch('webhooks.webhook_handler.is_enhancement_paused', return_value=False)
    def test_invalid_json_body_returns_400(self, mock_paused, mock_sig):
        event = {'body': 'not-json', 'headers': {}}
        response = handle_webhook_notification(event)
        assert response['statusCode'] == 400

    @patch('webhooks.webhook_handler.get_sqs_client')
    @patch('webhooks.webhook_handler.verify_webhook_signature', return_value=True)
    @patch('webhooks.webhook_handler.is_enhancement_paused', return_value=False)
    def test_athlete_event_not_queued(self, mock_paused, mock_sig, mock_sqs):
        webhook_body = {
            'object_type': 'athlete',
            'object_id': 123,
            'aspect_type': 'update',
            'owner_id': 456,
        }
        event = {'body': json.dumps(webhook_body), 'headers': {}}
        response = handle_webhook_notification(event)
        assert response['statusCode'] == 200
        mock_sqs.return_value.send_message.assert_not_called()


class TestIsEnhancementPaused:
    """Test enhancement pause check with mocked DynamoDB"""

    @patch('webhooks.webhook_handler.get_dynamodb_resource')
    def test_enabled_user(self, mock_dynamo):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {'user_id': '123', 'enhancement_enabled': True}
        }
        mock_dynamo.return_value.Table.return_value = mock_table

        assert is_enhancement_paused('123') is False

    @patch('webhooks.webhook_handler.get_dynamodb_resource')
    def test_paused_user(self, mock_dynamo):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {'user_id': '123', 'enhancement_enabled': False}
        }
        mock_dynamo.return_value.Table.return_value = mock_table

        assert is_enhancement_paused('123') is True

    @patch('webhooks.webhook_handler.get_dynamodb_resource')
    def test_no_config_defaults_enabled(self, mock_dynamo):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item
        mock_dynamo.return_value.Table.return_value = mock_table

        assert is_enhancement_paused('123') is False

    def test_no_user_id_defaults_enabled(self):
        assert is_enhancement_paused(None) is False

    @patch('webhooks.webhook_handler.get_dynamodb_resource')
    def test_dynamo_error_defaults_enabled(self, mock_dynamo):
        mock_dynamo.return_value.Table.return_value.get_item.side_effect = Exception("timeout")
        assert is_enhancement_paused('123') is False
