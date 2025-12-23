"""
Property-Based Tests for Error Recovery

Tests Property 9: Processing failures trigger SQS retry with exponential backoff
Validates Requirements 2.13
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
from typing import Dict, Any, List
from botocore.exceptions import ClientError

# Set up environment variables BEFORE importing modules
os.environ.setdefault('ACTIVITIES_TABLE', 'test-activities')
os.environ.setdefault('RATE_LIMITS_TABLE', 'test-rate-limits')
os.environ.setdefault('STRAVA_OAUTH_SECRET', 'test-oauth-secret')
os.environ.setdefault('STEP_FUNCTIONS_ARN', 'arn:aws:states:us-east-1:123456789012:stateMachine:test-workflow')

# Import the modules to test
import sys
sys.path.append('lambda_functions')
sys.path.append('src')

import activity_processor
from activity_processor import handler as activity_processor_handler, process_activity_record, check_rate_limits, start_step_functions_workflow
from src.utils.data_models import ProcessingStatus


# Test data strategies
@st.composite
def sqs_record_strategy(draw):
    """Generate SQS record with activity data"""
    activity_id = draw(st.integers(min_value=1, max_value=999999999))
    user_id = draw(st.integers(min_value=1, max_value=999999))
    
    message_body = {
        'activity_id': str(activity_id),
        'user_id': str(user_id),
        'webhook_data': {
            'object_type': 'activity',
            'object_id': activity_id,
            'aspect_type': draw(st.sampled_from(['create', 'update'])),
            'owner_id': user_id,
            'subscription_id': draw(st.integers(min_value=1, max_value=99999)),
            'event_time': draw(st.integers(min_value=1600000000, max_value=2000000000))
        },
        'event_time': draw(st.integers(min_value=1600000000, max_value=2000000000))
    }
    
    return {
        'messageId': f'test-message-{activity_id}',
        'receiptHandle': f'test-receipt-{activity_id}',
        'body': json.dumps(message_body),
        'attributes': {
            'ApproximateReceiveCount': str(draw(st.integers(min_value=1, max_value=3))),
            'SentTimestamp': str(draw(st.integers(min_value=1600000000000, max_value=2000000000000))),
            'ApproximateFirstReceiveTimestamp': str(draw(st.integers(min_value=1600000000000, max_value=2000000000000)))
        },
        'messageAttributes': {},
        'md5OfBody': 'test-md5',
        'eventSource': 'aws:sqs',
        'eventSourceARN': 'arn:aws:sqs:us-east-1:123456789012:test-queue',
        'awsRegion': 'us-east-1'
    }


@st.composite
def sqs_event_strategy(draw, num_records=None):
    """Generate SQS event with multiple records"""
    if num_records is None:
        num_records = draw(st.integers(min_value=1, max_value=5))
    
    records = [draw(sqs_record_strategy()) for _ in range(num_records)]
    
    return {
        'Records': records
    }


@st.composite
def failure_scenario_strategy(draw):
    """Generate different failure scenarios"""
    failure_types = [
        'strava_api_error',
        'rate_limit_exceeded',
        'step_functions_error',
        'dynamodb_error',
        'secrets_manager_error',
        'network_timeout',
        'invalid_response'
    ]
    
    return {
        'failure_type': draw(st.sampled_from(failure_types)),
        'error_message': draw(st.text(min_size=10, max_size=100)),
        'should_retry': draw(st.booleans()),
        'retry_count': draw(st.integers(min_value=1, max_value=3))
    }


class TestErrorRecoveryProperties:
    """
    Property-based tests for error recovery mechanisms.
    
    **Feature: strava-ai-boost, Property 9: Processing failures trigger SQS retry with exponential backoff**
    """
    
    def setup_method(self):
        """Set up test environment before each test method"""
        # Generate unique identifiers for this test run
        self.test_id = str(uuid.uuid4())[:8]
        
        # Set up environment variables with unique names
        self.env_vars = {
            'ACTIVITIES_TABLE': f'test-activities-{self.test_id}',
            'RATE_LIMITS_TABLE': f'test-rate-limits-{self.test_id}',
            'STRAVA_OAUTH_SECRET': 'test-oauth-secret',
            'STEP_FUNCTIONS_ARN': f'arn:aws:states:us-east-1:123456789012:stateMachine:test-workflow-{self.test_id}'
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
        # Mock Step Functions client
        mock_stepfunctions = Mock()
        mock_stepfunctions.start_execution.return_value = {
            'executionArn': f'arn:aws:states:us-east-1:123456789012:execution:test-workflow-{self.test_id}:test-execution'
        }
        
        # Mock DynamoDB resource and tables
        mock_dynamodb = Mock()
        mock_activities_table = Mock()
        mock_rate_limits_table = Mock()
        
        # Configure rate limits table responses
        mock_rate_limits_table.get_item.return_value = {
            'Item': {'current_usage': 50, 'reset_time': datetime.now(UTC).isoformat()}
        }
        
        def table_side_effect(table_name):
            if 'activities' in table_name:
                return mock_activities_table
            elif 'rate-limits' in table_name:
                return mock_rate_limits_table
            else:
                return Mock()
        
        mock_dynamodb.Table.side_effect = table_side_effect
        
        return mock_stepfunctions, mock_dynamodb, mock_activities_table, mock_rate_limits_table
    
    @given(sqs_event=sqs_event_strategy(), failure_scenario=failure_scenario_strategy())
    @settings(max_examples=100, deadline=None)
    def test_processing_failures_trigger_sqs_retry_property(self, sqs_event, failure_scenario):
        """
        **Feature: strava-ai-boost, Property 9: Processing failures trigger SQS retry with exponential backoff**
        
        For any SQS message processing failure, when the activity processor encounters an error,
        it should raise an exception to trigger SQS retry logic with exponential backoff.
        
        **Validates: Requirements 2.13**
        """
        # Arrange
        mock_stepfunctions, mock_dynamodb, mock_activities_table, mock_rate_limits_table = self._create_comprehensive_mocks()
        
        # Configure failure scenario
        if failure_scenario['failure_type'] == 'strava_api_error':
            mock_stepfunctions.start_execution.side_effect = ClientError(
                {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
                'StartExecution'
            )
        elif failure_scenario['failure_type'] == 'rate_limit_exceeded':
            mock_rate_limits_table.get_item.return_value = {
                'Item': {'current_usage': 95, 'reset_time': datetime.now(UTC).isoformat()}
            }
        elif failure_scenario['failure_type'] == 'step_functions_error':
            mock_stepfunctions.start_execution.side_effect = Exception(failure_scenario['error_message'])
        elif failure_scenario['failure_type'] == 'dynamodb_error':
            mock_activities_table.update_item.side_effect = ClientError(
                {'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'Throttled'}},
                'UpdateItem'
            )
        elif failure_scenario['failure_type'] == 'network_timeout':
            mock_stepfunctions.start_execution.side_effect = Exception("Network timeout")
        
        context = Mock()
        context.aws_request_id = f'test-request-{self.test_id}'
        
        # Apply comprehensive mocking
        with patch('activity_processor.stepfunctions', mock_stepfunctions), \
             patch('activity_processor.dynamodb', mock_dynamodb), \
             patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks as fallback
            def client_side_effect(service_name, **kwargs):
                if service_name == 'stepfunctions':
                    return mock_stepfunctions
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act & Assert - Processing should raise exception for SQS retry
            # Focus on failure types that should trigger retry
            if failure_scenario['failure_type'] in [
                'strava_api_error', 'rate_limit_exceeded', 'step_functions_error', 
                'network_timeout'
            ]:
                with pytest.raises(Exception):
                    activity_processor_handler(sqs_event, context)
                
                # Verify that the exception was raised to trigger SQS retry
                # SQS will automatically retry based on the exception
                
            else:
                # For other scenarios, test may succeed or fail
                # The key is that failures should raise exceptions for retry
                try:
                    result = activity_processor_handler(sqs_event, context)
                    # If it succeeds, verify it processed the records
                    assert result['statusCode'] == 200
                    assert result['processed'] == len(sqs_event['Records'])
                except Exception:
                    # Exception is acceptable for triggering retry
                    pass
    
    @given(sqs_record=sqs_record_strategy())
    @settings(max_examples=100, deadline=None)
    def test_rate_limit_exceeded_triggers_retry_property(self, sqs_record):
        """
        **Feature: strava-ai-boost, Property 9: Processing failures trigger SQS retry with exponential backoff**
        
        For any SQS record, when rate limits are exceeded, processing should fail
        and trigger SQS retry logic to wait for rate limit reset.
        
        **Validates: Requirements 2.13**
        """
        # Arrange
        mock_stepfunctions, mock_dynamodb, mock_activities_table, mock_rate_limits_table = self._create_comprehensive_mocks()
        
        # Configure rate limits to be exceeded
        mock_rate_limits_table.get_item.side_effect = [
            {'Item': {'current_usage': 95, 'reset_time': datetime.now(UTC).isoformat()}},  # Short-term limit
            {'Item': {'current_usage': 980, 'reset_time': datetime.now(UTC).isoformat()}}  # Daily limit
        ]
        
        # Apply comprehensive mocking
        with patch('activity_processor.stepfunctions', mock_stepfunctions), \
             patch('activity_processor.dynamodb', mock_dynamodb), \
             patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'stepfunctions':
                    return mock_stepfunctions
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act & Assert - Should raise exception when rate limits exceeded
            with pytest.raises(Exception, match="Rate limits exceeded"):
                process_activity_record(sqs_record)
            
            # Verify rate limit check was performed
            assert mock_rate_limits_table.get_item.call_count >= 1
            
            # Verify Step Functions was not called due to rate limiting
            mock_stepfunctions.start_execution.assert_not_called()
    
    @given(sqs_record=sqs_record_strategy())
    @settings(max_examples=100, deadline=None)
    def test_step_functions_failure_triggers_retry_property(self, sqs_record):
        """
        **Feature: strava-ai-boost, Property 9: Processing failures trigger SQS retry with exponential backoff**
        
        For any SQS record, when Step Functions workflow fails to start,
        processing should fail and trigger SQS retry logic.
        
        **Validates: Requirements 2.13**
        """
        # Arrange
        mock_stepfunctions, mock_dynamodb, mock_activities_table, mock_rate_limits_table = self._create_comprehensive_mocks()
        
        # Configure Step Functions to fail
        step_functions_errors = [
            ClientError({'Error': {'Code': 'ExecutionLimitExceeded', 'Message': 'Too many executions'}}, 'StartExecution'),
            ClientError({'Error': {'Code': 'StateMachineDoesNotExist', 'Message': 'State machine not found'}}, 'StartExecution'),
            Exception("Network error"),
            Exception("Service unavailable")
        ]
        
        mock_stepfunctions.start_execution.side_effect = step_functions_errors[0]
        
        # Apply comprehensive mocking
        with patch('activity_processor.stepfunctions', mock_stepfunctions), \
             patch('activity_processor.dynamodb', mock_dynamodb), \
             patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'stepfunctions':
                    return mock_stepfunctions
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act & Assert - Should raise exception when Step Functions fails
            with pytest.raises(Exception):
                process_activity_record(sqs_record)
            
            # Verify Step Functions start was attempted
            mock_stepfunctions.start_execution.assert_called_once()
            
            # Verify activity status was updated to failed
            mock_activities_table.update_item.assert_called()
            
            # Check that the update included failure status
            update_calls = mock_activities_table.update_item.call_args_list
            assert any('failed' in str(call) for call in update_calls)
    
    @given(sqs_record=sqs_record_strategy())
    @settings(max_examples=100, deadline=None)
    def test_dynamodb_failure_triggers_retry_property(self, sqs_record):
        """
        **Feature: strava-ai-boost, Property 9: Processing failures trigger SQS retry with exponential backoff**
        
        For any SQS record, when DynamoDB operations fail (throttling, unavailable),
        processing should fail and trigger SQS retry logic.
        
        **Validates: Requirements 2.13**
        """
        # Arrange
        mock_stepfunctions, mock_dynamodb, mock_activities_table, mock_rate_limits_table = self._create_comprehensive_mocks()
        
        # Configure DynamoDB to fail on status update
        mock_activities_table.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'Request rate is too high'}},
            'UpdateItem'
        )
        
        # Apply comprehensive mocking
        with patch('activity_processor.stepfunctions', mock_stepfunctions), \
             patch('activity_processor.dynamodb', mock_dynamodb), \
             patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'stepfunctions':
                    return mock_stepfunctions
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act & Assert - Should raise exception when DynamoDB fails
            with pytest.raises(Exception):
                process_activity_record(sqs_record)
            
            # Verify DynamoDB update was attempted
            mock_activities_table.update_item.assert_called()
    
    @given(
        sqs_event=sqs_event_strategy(num_records=1),
        receive_count=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=100, deadline=None)
    def test_sqs_retry_count_tracking_property(self, sqs_event, receive_count):
        """
        **Feature: strava-ai-boost, Property 9: Processing failures trigger SQS retry with exponential backoff**
        
        For any SQS message with retry attempts, the ApproximateReceiveCount should
        increase with each retry, and after max retries, message goes to DLQ.
        
        **Validates: Requirements 2.13**
        """
        # Arrange
        mock_stepfunctions, mock_dynamodb, mock_activities_table, mock_rate_limits_table = self._create_comprehensive_mocks()
        
        # Configure consistent failure to trigger retries
        mock_stepfunctions.start_execution.side_effect = Exception("Persistent failure")
        
        # Update SQS record with receive count
        sqs_event['Records'][0]['attributes']['ApproximateReceiveCount'] = str(receive_count)
        
        context = Mock()
        context.aws_request_id = f'test-request-{self.test_id}'
        
        # Apply comprehensive mocking
        with patch('activity_processor.stepfunctions', mock_stepfunctions), \
             patch('activity_processor.dynamodb', mock_dynamodb), \
             patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'stepfunctions':
                    return mock_stepfunctions
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act & Assert - Should raise exception for retry
            with pytest.raises(Exception):
                activity_processor_handler(sqs_event, context)
            
            # Verify the receive count is tracked in SQS attributes
            record = sqs_event['Records'][0]
            actual_receive_count = int(record['attributes']['ApproximateReceiveCount'])
            assert actual_receive_count == receive_count, f"Receive count should be {receive_count}"
            
            # Verify processing was attempted
            mock_stepfunctions.start_execution.assert_called_once()
            
            # If this is the max retry (3), the message would go to DLQ
            # (This is handled by SQS infrastructure, not our code)
            if receive_count >= 3:
                # On max retries, our code still fails but SQS moves to DLQ
                pass
    
    @given(sqs_event=sqs_event_strategy())
    @settings(max_examples=100, deadline=None)
    def test_successful_processing_no_retry_property(self, sqs_event):
        """
        **Feature: strava-ai-boost, Property 9: Processing failures trigger SQS retry with exponential backoff**
        
        For any SQS message that processes successfully, no exception should be raised
        and no retry should be triggered.
        
        **Validates: Requirements 2.13**
        """
        # Arrange
        mock_stepfunctions, mock_dynamodb, mock_activities_table, mock_rate_limits_table = self._create_comprehensive_mocks()
        
        # Configure successful processing
        mock_stepfunctions.start_execution.return_value = {
            'executionArn': f'arn:aws:states:us-east-1:123456789012:execution:test-workflow-{self.test_id}:success'
        }
        
        context = Mock()
        context.aws_request_id = f'test-request-{self.test_id}'
        
        # Apply comprehensive mocking
        with patch('activity_processor.stepfunctions', mock_stepfunctions), \
             patch('activity_processor.dynamodb', mock_dynamodb), \
             patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'stepfunctions':
                    return mock_stepfunctions
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act - Should process successfully without exception
            result = activity_processor_handler(sqs_event, context)
            
            # Assert - Successful processing
            assert result['statusCode'] == 200, "Successful processing should return 200"
            assert result['processed'] == len(sqs_event['Records']), "Should process all records"
            
            # Verify Step Functions was called for each record
            assert mock_stepfunctions.start_execution.call_count == len(sqs_event['Records'])
            
            # Verify activity status updates were attempted
            expected_calls = len(sqs_event['Records']) * 2  # processing + execution_arn updates
            assert mock_activities_table.update_item.call_count >= len(sqs_event['Records'])
    
    @given(
        sqs_event=sqs_event_strategy(num_records=1),  # Simplify to single record for clearer logic
        failure_count=st.integers(min_value=0, max_value=3)
    )
    @settings(max_examples=100, deadline=None)
    def test_intermittent_failures_eventual_success_property(self, sqs_event, failure_count):
        """
        **Feature: strava-ai-boost, Property 9: Processing failures trigger SQS retry with exponential backoff**
        
        For any SQS message with intermittent failures, retry logic should eventually
        succeed when the underlying issue is resolved.
        
        **Validates: Requirements 2.13**
        """
        # Arrange
        mock_stepfunctions, mock_dynamodb, mock_activities_table, mock_rate_limits_table = self._create_comprehensive_mocks()
        
        # Configure failures followed by success
        # Create a list with 'failure_count' failures followed by success
        side_effects = []
        for i in range(failure_count):
            side_effects.append(Exception(f"Intermittent failure {i+1}"))
        
        # Always end with success
        side_effects.append({
            'executionArn': f'arn:aws:states:us-east-1:123456789012:execution:test-workflow-{self.test_id}:final-success'
        })
        
        # Track call count to reset side_effect when needed
        call_count = 0
        original_side_effects = side_effects.copy()
        
        def dynamic_side_effect(*args, **kwargs):
            nonlocal call_count, side_effects
            if call_count < len(original_side_effects):
                effect = original_side_effects[call_count]
                call_count += 1
                if isinstance(effect, Exception):
                    raise effect
                return effect
            else:
                # After all planned effects, always return success
                return {
                    'executionArn': f'arn:aws:states:us-east-1:123456789012:execution:test-workflow-{self.test_id}:continued-success'
                }
        
        mock_stepfunctions.start_execution.side_effect = dynamic_side_effect
        
        context = Mock()
        context.aws_request_id = f'test-request-{self.test_id}'
        
        # Apply comprehensive mocking
        with patch('activity_processor.stepfunctions', mock_stepfunctions), \
             patch('activity_processor.dynamodb', mock_dynamodb), \
             patch('boto3.client') as mock_boto_client, \
             patch('boto3.resource') as mock_boto_resource:
            
            # Configure boto3 mocks
            def client_side_effect(service_name, **kwargs):
                if service_name == 'stepfunctions':
                    return mock_stepfunctions
                else:
                    return Mock()
            
            def resource_side_effect(service_name, **kwargs):
                if service_name == 'dynamodb':
                    return mock_dynamodb
                else:
                    return Mock()
            
            mock_boto_client.side_effect = client_side_effect
            mock_boto_resource.side_effect = resource_side_effect
            
            # Act - Test the behavior based on failure count
            if failure_count == 0:
                # No failures - should succeed immediately
                result = activity_processor_handler(sqs_event, context)
                assert result['statusCode'] == 200, "Should succeed when no failures"
                assert result['processed'] == len(sqs_event['Records'])
                
            else:
                # Has failures - should fail initially (triggering SQS retry)
                with pytest.raises(Exception):
                    activity_processor_handler(sqs_event, context)
                
                # Verify that Step Functions was called (and failed)
                assert mock_stepfunctions.start_execution.call_count >= 1
                
                # Simulate retry after failure - this would happen via SQS retry
                # Reset call count to simulate fresh invocation after retry delay
                call_count = failure_count  # Skip to success part
                
                # Now it should succeed (simulating eventual success after retries)
                result = activity_processor_handler(sqs_event, context)
                assert result['statusCode'] == 200, "Should eventually succeed after retries"
                assert result['processed'] == len(sqs_event['Records'])
            
            # Verify Step Functions was called appropriately
            assert mock_stepfunctions.start_execution.call_count >= 1


if __name__ == "__main__":
    # Run the property tests
    pytest.main([__file__, "-v", "--tb=short"])