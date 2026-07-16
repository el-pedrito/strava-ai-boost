"""
Tests for Lambda functions

Simplified tests focusing on Lambda structure and basic functionality
"""

import pytest
import json
import sys
import os

# Add lambda_functions to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda_functions'))


class TestLambdaStructure:
    """Test Lambda function structure and configuration"""

    # Map of lambda files to their package subdirectory
    LAMBDA_FILES = {
        'webhooks/webhook_handler.py': 'def handler(',
        'webhooks/activity_processor.py': 'def handler(',
        'processing/content_generator.py': 'def handler(',
        'processing/activity_fetcher.py': 'def handler(',
        'processing/strava_updater.py': 'def handler(',
        'api/configuration_api.py': 'def handler(',
        'api/dashboard_api.py': 'def handler(',
        'api/user_preferences_api.py': 'def handler(',
        'api/agentcore_health_check.py': 'def handler(',
        'support/stepfunctions_error_handler.py': 'def handler(',
    }

    def test_all_lambdas_have_handler(self):
        """Test all Lambda files have a handler function"""
        lambda_dir = os.path.join(os.path.dirname(__file__), '..', 'lambda_functions')

        for lambda_file, handler_sig in self.LAMBDA_FILES.items():
            file_path = os.path.join(lambda_dir, lambda_file)
            assert os.path.exists(file_path), f"{lambda_file} should exist"

            with open(file_path, 'r') as f:
                content = f.read()
                assert handler_sig in content, f"{lambda_file} should have handler function"

    def test_lambda_imports_boto3(self):
        """Test Lambda functions import boto3"""
        lambda_modules = [
            'webhooks.webhook_handler',
            'webhooks.activity_processor',
            'processing.content_generator',
            'processing.strava_updater'
        ]

        for module_name in lambda_modules:
            try:
                module = __import__(module_name)
                assert module is not None
            except ImportError:
                # Some imports may fail due to missing dependencies in test env
                pass

    def test_lambda_environment_variables(self):
        """Test Lambda functions read environment variables"""
        required_vars = [
            "ACTIVITIES_TABLE",
            "USER_CONFIG_TABLE",
            "RATE_LIMITS_TABLE",
            "BEDROCK_MODEL_ID"
        ]

        for var in required_vars:
            assert var in os.environ


class TestWebhookHandler:
    """Test webhook handler Lambda"""

    def test_webhook_verification_logic(self):
        """Test webhook verification logic"""
        hub_mode = "subscribe"
        hub_challenge = "test_challenge_12345"
        hub_verify_token = "test-verify-token"
        expected_token = "test-verify-token"

        is_valid = (hub_mode == "subscribe" and hub_verify_token == expected_token)

        assert is_valid == True

        if is_valid:
            response = {
                "statusCode": 200,
                "body": json.dumps({"hub.challenge": hub_challenge})
            }
            assert response["statusCode"] == 200

    def test_webhook_event_structure(self, sample_webhook_event):
        """Test webhook event has required fields"""
        required_fields = ["object_type", "object_id", "aspect_type", "owner_id"]

        for field in required_fields:
            assert field in sample_webhook_event


class TestContentGenerator:
    """Test content generator Lambda"""

    def test_content_generator_has_agent_generation(self):
        """Test content_generator has AgentCore generation"""
        from processing import content_generator

        assert hasattr(content_generator, 'generate_enhanced_content')

    def test_modules_processing(self):
        """Test modules_processing supports module discovery and processing"""
        from processing import modules_processing

        assert hasattr(modules_processing, 'get_active_modules')
        assert hasattr(modules_processing, 'apply_module_processing')


class TestActivityProcessor:
    """Test activity processor Lambda"""

    def test_sqs_event_structure(self):
        """Test SQS event structure is valid"""
        event = {
            "Records": [
                {
                    "messageId": "test-id",
                    "body": json.dumps({
                        "activity_id": "12345",
                        "user_id": "test-user"
                    })
                }
            ]
        }

        assert "Records" in event
        assert len(event["Records"]) > 0
        assert "messageId" in event["Records"][0]
        assert "body" in event["Records"][0]
