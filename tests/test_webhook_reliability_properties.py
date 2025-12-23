"""
Property-Based Tests for Webhook Reliability

Tests Property 2: Valid webhooks queued in SQS for reliable processing
Validates Requirements 2.2
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import Mock, patch, MagicMock, call
import json
from datetime import datetime, UTC
import boto3
from moto import mock_aws
import os
import uuid
from typing import Dict, Any

# Set up environment variables BEFORE importing webhook handler
os.environ.setdefault('PROCESSING_QUEUE_URL', 'https://sqs.us-east-1.amazonaws.com/123456789012/test-queue')
os.environ.setdefault('ACTIVITIES_TABLE', 'test-activities')
os.environ.setdefault('RATE_LIMITS_TABLE', 'test-rate-limits')
os.environ.setdefault('USER_CONFIG_TABLE', 'test-user-config')
os.environ.setdefault('STRAVA_OAUTH_SECRET', 'test-oauth-secret')

# Import the modules to test
import sys
sys.path.append('lambda_functions')
sys.path.append('src')

# Import webhook handler module for patching
import webhook_handler
from webhook_handler import handler as webhook_handler_func, validate_webhook_data, is_enhancement_paused
from src.utils.data_models import ProcessingStatus


# Test data strategies
@st.composite
def valid_webhook_strategy(draw):
    """Generate valid Strava webhook data"""
    object_types = ['activity', 'athlete']
    aspect_types = ['create', 'update', 'delete']
    
    return {
        'object_type': draw(st.sampled_from(object_types)),
        'object_id': draw(st.integers(min_value=1, max_value=999999999)),
        'aspect_type': draw(st.sampled_from(aspect_types)),
        'owner_id': draw(st.integers(min_value=1, max_value=999999)),
        'subscription_id': draw(st.integers(min_value=1, max_value=99999)),
        'event_time': draw(st.integers(min_value=1600000000, max_value=2000000000))  # Valid Unix timestamps
    }


@st.composite
def activity_webhook_strategy(draw):
    """Generate valid activity webhook data specifically"""
    aspect_types = ['create', 'update']
    
    return {
        'object_type': 'activity',
        'object_id': draw(st.integers(min_value=1, max_value=999999999)),
        'aspect_type': draw(st.sampled_from(aspect_types)),
        'owner_id': draw(st.integers(min_value=1, max_value=999999)),
        'subscription_id': draw(st.integers(min_value=1, max_value=99999)),
        'event_time': draw(st.integers(min_value=1600000000, max_value=2000000000))
    }


@st.composite
def invalid_webhook_strategy(draw):
    """Generate invalid webhook data missing required fields"""
    # Start with a valid webhook and remove required fields
    valid_fields = ['object_type', 'object_id', 'aspect_type', 'owner_id']
    
    webhook = {
        'object_type': 'activity',
        'object_id': draw(st.integers(min_value=1, max_value=999999999)),
        'aspect_type': 'create',
        'owner_id': draw(st.integers(min_value=1, max_value=999999)),
        'subscription_id': draw(st.integers(min_value=1, max_value=99999)),
        'event_time': draw(st.integers(min_value=1600000000, max_value=2000000000))
    }
    
    # Remove at least one required field
    field_to_remove = draw(st.sampled_from(valid_fields))
    del webhook[field_to_remove]
    
    return webhook


@st.composite
def api_gateway_event_strategy(draw, webhook_data=None):
    """Generate API Gateway event structure"""
    if webhook_data is None:
        webhook_data = draw(activity_webhook_strategy())
    
    return {
        'httpMethod': 'POST',
        'body': json.dumps(webhook_data),
        'headers': {
            'Content-Type': 'application/json',
            'User-Agent': 'Strava/1.0'
        },
        'queryStringParameters': None,
        'pathParameters': None,
        'requestContext': {
            'requestId': draw(st.text(min_size=10, max_size=50)),
            'stage': 'prod'
        }
    }


class TestWebhookReliabilityProperties:
    """
    Property-based tests for webhook reliability.
    
    **Feature: strava-ai-boost, Property 2: Valid webhooks queued in SQS for reliable processing**
    """
    
    def setup_method(self):
        """Set up test environment before each test method"""
        # Generate unique identifiers for this test run
        self.test_id = str(uuid.uuid4())[:8]
        
        # Set up environment variables with unique names
        self.env_vars = {
            'PROCESSING_QUEUE_URL': f'https://sqs.us-east-1.amazonaws.com/123456789012/test-queue-{self.test_id}',
            'ACTIVITIES_TABLE': f'test-activities-{self.test_id}',
            'RATE_LIMITS_TABLE': f'test-rate-limits-{self.test_id}',
            'USER_CONFIG_TABLE': f'test-user-config-{self.test_id}',
            'STRAVA_OAUTH_SECRET': 'test-oauth-secret'
        }
        
        # Apply environment variables
        for key, value in self.env_vars.items():
            os.environ[key] = value
    
    def teardown_method(self):
        """Clean up after each test method"""
        # Clean up environment variables
        for key in self.env_vars.keys():
            if key in os.environ:
                del os.environ[key]
    
    def _create_comprehensive_mocks(self):
        """Create comprehensive mocks for all AWS services"""
        # Mock SQS client
        mock_sqs = Mock()
        mock_sqs.send_message.return_value = {'MessageId': f'test-message-{self.test_id}'}
        
        # Mock DynamoDB resource and table
        mock_dynamodb = Mock()
        mock_table = Mock()
        mock_table.get_item.return_value = {'Item': {'enhancement_enabled': True}}
        mock_dynamodb.Table.return_value = mock_table
        
        # Mock Secrets Manager client
        mock_secrets = Mock()
        
        return mock_sqs, mock_dynamodb, mock_secrets
    
    @given(webhook_data=activity_webhook_strategy())
    @settings(max_examples=100, deadline=None)
    def test_valid_activity_webhooks_queued_in_sqs_property(self, webhook_data):
        """
        **Feature: strava-ai-boost, Property 2: Valid webhooks queued in SQS for reliable processing**
        
        For any valid activity webhook (create/update), when received by the webhook handler,
        it should be queued in SQS for reliable processing.
        
        **Validates: Requirements 2.2**
        """
        # Arrange
        mock_sqs, mock_dynamodb, mock_secrets = self._create_comprehensive_mocks()
        
        # Create API Gateway event
        event = {
            'httpMethod': 'POST',
            'body': json.dumps(webhook_data),
            'headers': {'Content-Type': 'application/json'},
            'queryStringParameters': None
        }
        
        context = Mock()
        context.aws_request_id = f'test-request-{self.test_id}'
        
        # Apply comprehensive mocking
        with patch('webhook_handler.get_sqs_client', return_value=mock_sqs), \
             patch('webhook_handler.get_dynamodb_resource', return_value=mock_dynamodb), \
             patch('webhook_handler.get_secretsmanager_client', return_value=mock_secrets), \
             patch('webhook_handler.PROCESSING_QUEUE_URL', self.env_vars['PROCESSING_QUEUE_URL']), \
             patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks as fallback
            def client_side_effect(service_name, **kwargs):
                if service_name == 'sqs':
                    return mock_sqs
                elif service_name == 'secretsmanager':
                    return mock_secrets
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act - Process webhook
            response = webhook_handler_func(event, context)
            
            # Assert - Response should be successful
            assert response['statusCode'] == 200, "Webhook should be processed successfully"
            
            response_body = json.loads(response['body'])
            assert response_body['status'] == 'received', "Webhook should be acknowledged as received"
            
            # Assert - SQS message should be sent
            mock_sqs.send_message.assert_called_once()
            
            # Verify SQS message content
            call_args = mock_sqs.send_message.call_args
            assert call_args[1]['QueueUrl'] == self.env_vars['PROCESSING_QUEUE_URL'], "Should use correct queue URL"
            
            # Parse message body
            message_body = json.loads(call_args[1]['MessageBody'])
            assert message_body['activity_id'] == str(webhook_data['object_id']), "Message should contain activity ID"
            assert message_body['user_id'] == str(webhook_data['owner_id']), "Message should contain user ID"
            assert message_body['webhook_data'] == webhook_data, "Message should contain original webhook data"
            assert message_body['event_time'] == webhook_data['event_time'], "Message should contain event time"
            
            # Verify message attributes
            message_attributes = call_args[1]['MessageAttributes']
            assert 'ActivityId' in message_attributes, "Should include ActivityId attribute"
            assert 'UserId' in message_attributes, "Should include UserId attribute"
            assert message_attributes['ActivityId']['StringValue'] == str(webhook_data['object_id']), "ActivityId should match"
            assert message_attributes['UserId']['StringValue'] == str(webhook_data['owner_id']), "UserId should match"
    
    @given(webhook_data=valid_webhook_strategy())
    @settings(max_examples=100, deadline=None)
    def test_non_activity_webhooks_not_queued_property(self, webhook_data):
        """
        **Feature: strava-ai-boost, Property 2: Valid webhooks queued in SQS for reliable processing**
        
        For any valid webhook that is not an activity create/update event,
        it should be acknowledged but not queued for processing.
        
        **Validates: Requirements 2.2**
        """
        # Skip activity webhooks for this test
        assume(webhook_data['object_type'] != 'activity' or 
               webhook_data['aspect_type'] not in ['create', 'update'])
        
        # Arrange
        mock_sqs, mock_dynamodb, mock_secrets = self._create_comprehensive_mocks()
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps(webhook_data),
            'headers': {'Content-Type': 'application/json'},
            'queryStringParameters': None
        }
        
        context = Mock()
        context.aws_request_id = f'test-request-{self.test_id}'
        
        # Apply comprehensive mocking
        with patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'sqs':
                    return mock_sqs
                elif service_name == 'secretsmanager':
                    return mock_secrets
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act - Process webhook
            response = webhook_handler_func(event, context)
            
            # Assert - Response should be successful
            assert response['statusCode'] == 200, "Non-activity webhook should be acknowledged"
            
            response_body = json.loads(response['body'])
            assert response_body['status'] == 'received', "Webhook should be acknowledged as received"
            
            # Assert - SQS message should NOT be sent
            mock_sqs.send_message.assert_not_called()
    
    @given(webhook_data=invalid_webhook_strategy())
    @settings(max_examples=100, deadline=None)
    def test_invalid_webhooks_rejected_not_queued_property(self, webhook_data):
        """
        **Feature: strava-ai-boost, Property 2: Valid webhooks queued in SQS for reliable processing**
        
        For any invalid webhook data (missing required fields),
        it should be rejected and not queued for processing.
        
        **Validates: Requirements 2.2**
        """
        # Arrange
        mock_sqs, mock_dynamodb, mock_secrets = self._create_comprehensive_mocks()
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps(webhook_data),
            'headers': {'Content-Type': 'application/json'},
            'queryStringParameters': None
        }
        
        context = Mock()
        context.aws_request_id = f'test-request-{self.test_id}'
        
        # Apply comprehensive mocking
        with patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'sqs':
                    return mock_sqs
                elif service_name == 'secretsmanager':
                    return mock_secrets
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act - Process webhook
            response = webhook_handler_func(event, context)
            
            # Assert - Response should be error
            assert response['statusCode'] == 400, "Invalid webhook should be rejected"
            
            response_body = json.loads(response['body'])
            assert 'error' in response_body, "Response should contain error message"
            
            # Assert - SQS message should NOT be sent
            mock_sqs.send_message.assert_not_called()
    
    @given(webhook_data=activity_webhook_strategy())
    @settings(max_examples=100, deadline=None)
    def test_paused_enhancement_webhooks_acknowledged_not_queued_property(self, webhook_data):
        """
        **Feature: strava-ai-boost, Property 2: Valid webhooks queued in SQS for reliable processing**
        
        For any valid activity webhook when enhancement is paused,
        it should be acknowledged but not queued for processing.
        
        **Validates: Requirements 2.2**
        """
        # Arrange
        mock_sqs, mock_dynamodb, mock_secrets = self._create_comprehensive_mocks()
        
        # Configure DynamoDB to return enhancement disabled
        mock_table = Mock()
        mock_table.get_item.return_value = {'Item': {'enhancement_enabled': False}}
        mock_dynamodb.Table.return_value = mock_table
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps(webhook_data),
            'headers': {'Content-Type': 'application/json'},
            'queryStringParameters': None
        }
        
        context = Mock()
        context.aws_request_id = f'test-request-{self.test_id}'
        
        # Apply comprehensive mocking
        with patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'sqs':
                    return mock_sqs
                elif service_name == 'secretsmanager':
                    return mock_secrets
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act - Process webhook
            response = webhook_handler_func(event, context)
            
            # Assert - Response should be successful but indicate paused
            assert response['statusCode'] == 200, "Webhook should be acknowledged even when paused"
            
            response_body = json.loads(response['body'])
            assert response_body['status'] == 'acknowledged_paused', "Should indicate enhancement is paused"
            
            # Assert - SQS message should NOT be sent
            mock_sqs.send_message.assert_not_called()
    
    @given(webhook_data=activity_webhook_strategy())
    @settings(max_examples=100, deadline=None)
    def test_sqs_failure_returns_error_property(self, webhook_data):
        """
        **Feature: strava-ai-boost, Property 2: Valid webhooks queued in SQS for reliable processing**
        
        For any valid activity webhook, when SQS queuing fails,
        the webhook handler should return an error response.
        
        **Validates: Requirements 2.2**
        """
        # Arrange
        mock_sqs, mock_dynamodb, mock_secrets = self._create_comprehensive_mocks()
        
        # Configure SQS to raise exception
        mock_sqs.send_message.side_effect = Exception("SQS service unavailable")
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps(webhook_data),
            'headers': {'Content-Type': 'application/json'},
            'queryStringParameters': None
        }
        
        context = Mock()
        context.aws_request_id = f'test-request-{self.test_id}'
        
        # Apply comprehensive mocking
        with patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'sqs':
                    return mock_sqs
                elif service_name == 'secretsmanager':
                    return mock_secrets
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act - Process webhook
            response = webhook_handler_func(event, context)
            
            # Assert - Response should be error
            assert response['statusCode'] == 500, "Should return error when SQS fails"
            
            response_body = json.loads(response['body'])
            assert 'error' in response_body, "Response should contain error message"
            
            # Assert - SQS send was attempted
            mock_sqs.send_message.assert_called_once()
    
    @given(
        webhook_data=activity_webhook_strategy(),
        malformed_json=st.text(min_size=1, max_size=100)
    )
    @settings(max_examples=100, deadline=None)
    def test_malformed_json_webhooks_rejected_property(self, webhook_data, malformed_json):
        """
        **Feature: strava-ai-boost, Property 2: Valid webhooks queued in SQS for reliable processing**
        
        For any webhook with malformed JSON body,
        it should be rejected with a 400 error and not queued.
        
        **Validates: Requirements 2.2**
        """
        # Ensure malformed JSON is actually invalid
        assume(malformed_json.strip() != '')
        try:
            json.loads(malformed_json)
            assume(False)  # Skip if it's actually valid JSON
        except json.JSONDecodeError:
            pass  # This is what we want - invalid JSON
        
        # Arrange
        mock_sqs, mock_dynamodb, mock_secrets = self._create_comprehensive_mocks()
        
        event = {
            'httpMethod': 'POST',
            'body': malformed_json,  # Invalid JSON
            'headers': {'Content-Type': 'application/json'},
            'queryStringParameters': None
        }
        
        context = Mock()
        context.aws_request_id = f'test-request-{self.test_id}'
        
        # Apply comprehensive mocking
        with patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'sqs':
                    return mock_sqs
                elif service_name == 'secretsmanager':
                    return mock_secrets
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act - Process webhook
            response = webhook_handler_func(event, context)
            
            # Assert - Response should be error
            assert response['statusCode'] == 400, "Malformed JSON should be rejected"
            
            response_body = json.loads(response['body'])
            assert 'error' in response_body, "Response should contain error message"
            assert 'JSON' in response_body['error'], "Error should mention JSON parsing"
            
            # Assert - SQS message should NOT be sent
            mock_sqs.send_message.assert_not_called()
    
    @given(webhook_data=activity_webhook_strategy())
    @settings(max_examples=100, deadline=None)
    def test_webhook_verification_get_request_property(self, webhook_data):
        """
        **Feature: strava-ai-boost, Property 2: Valid webhooks queued in SQS for reliable processing**
        
        For any GET request (webhook verification), it should be handled
        separately and not attempt to queue any messages.
        
        **Validates: Requirements 2.2**
        """
        # Arrange
        mock_sqs, mock_dynamodb, mock_secrets = self._create_comprehensive_mocks()
        
        # Create GET request for webhook verification
        event = {
            'httpMethod': 'GET',
            'queryStringParameters': {
                'hub.mode': 'subscribe',
                'hub.challenge': 'test-challenge-123',
                'hub.verify_token': 'test-token'
            },
            'body': None
        }
        
        context = Mock()
        context.aws_request_id = f'test-request-{self.test_id}'
        
        # Apply comprehensive mocking
        with patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'sqs':
                    return mock_sqs
                elif service_name == 'secretsmanager':
                    return mock_secrets
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act - Process webhook verification
            response = webhook_handler_func(event, context)
            
            # Assert - Response should be successful verification
            assert response['statusCode'] == 200, "Webhook verification should succeed"
            
            response_body = json.loads(response['body'])
            assert 'hub.challenge' in response_body, "Should return challenge"
            assert response_body['hub.challenge'] == 'test-challenge-123', "Should return correct challenge"
            
            # Assert - SQS message should NOT be sent for verification
            mock_sqs.send_message.assert_not_called()
    
    @given(
        webhook_batch=st.lists(
            activity_webhook_strategy(),
            min_size=1,
            max_size=10
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_multiple_webhooks_all_queued_property(self, webhook_batch):
        """
        **Feature: strava-ai-boost, Property 2: Valid webhooks queued in SQS for reliable processing**
        
        For any batch of valid activity webhooks processed sequentially,
        each webhook should be independently queued in SQS.
        
        **Validates: Requirements 2.2**
        """
        # Arrange
        mock_sqs, mock_dynamodb, mock_secrets = self._create_comprehensive_mocks()
        
        context = Mock()
        context.aws_request_id = f'test-request-{self.test_id}'
        
        # Apply comprehensive mocking
        with patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'sqs':
                    return mock_sqs
                elif service_name == 'secretsmanager':
                    return mock_secrets
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            successful_webhooks = 0
            
            # Act - Process each webhook in the batch
            for webhook_data in webhook_batch:
                event = {
                    'httpMethod': 'POST',
                    'body': json.dumps(webhook_data),
                    'headers': {'Content-Type': 'application/json'},
                    'queryStringParameters': None
                }
                
                response = webhook_handler_func(event, context)
                
                # Assert - Each webhook should be processed successfully
                assert response['statusCode'] == 200, f"Webhook {webhook_data['object_id']} should be processed successfully"
                
                response_body = json.loads(response['body'])
                assert response_body['status'] == 'received', f"Webhook {webhook_data['object_id']} should be acknowledged"
                
                successful_webhooks += 1
            
            # Assert - All webhooks should have been queued
            assert mock_sqs.send_message.call_count == len(webhook_batch), "All webhooks should be queued"
            assert successful_webhooks == len(webhook_batch), "All webhooks should be processed successfully"
            
            # Verify each message was queued with correct data
            for i, call_args in enumerate(mock_sqs.send_message.call_args_list):
                message_body = json.loads(call_args[1]['MessageBody'])
                original_webhook = webhook_batch[i]
                
                assert message_body['activity_id'] == str(original_webhook['object_id']), f"Message {i} should contain correct activity ID"
                assert message_body['user_id'] == str(original_webhook['owner_id']), f"Message {i} should contain correct user ID"
                assert message_body['webhook_data'] == original_webhook, f"Message {i} should contain original webhook data"


if __name__ == "__main__":
    # Run the property tests
    pytest.main([__file__, "-v", "--tb=short"])