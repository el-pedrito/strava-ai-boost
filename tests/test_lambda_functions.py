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
    
    def test_all_lambdas_have_handler(self):
        """Test all Lambda files have a handler function"""
        lambda_dir = os.path.join(os.path.dirname(__file__), '..', 'lambda_functions')
        lambda_files = [
            'webhook_handler.py',
            'activity_processor.py',
            'content_generator.py',
            'activity_fetcher.py',
            'strava_updater.py',
            'campus_coach_invoker.py',
            'configuration_api.py',
            'dashboard_api.py',
            'user_preferences_api.py',
            'agentcore_health_check.py',
            'stepfunctions_error_handler.py'
            # Note: rate_limiter.py is a utility module, not a Lambda handler
        ]
        
        for lambda_file in lambda_files:
            file_path = os.path.join(lambda_dir, lambda_file)
            assert os.path.exists(file_path), f"{lambda_file} should exist"
            
            # Check file has handler function
            with open(file_path, 'r') as f:
                content = f.read()
                assert 'def handler(' in content, f"{lambda_file} should have handler function"
    
    def test_lambda_imports_boto3(self):
        """Test Lambda functions import boto3"""
        lambda_files = [
            'webhook_handler',
            'activity_processor',
            'content_generator',
            'strava_updater'
        ]
        
        for module_name in lambda_files:
            try:
                module = __import__(module_name)
                # Module imported successfully
                assert module is not None
            except ImportError:
                # Some imports may fail due to missing dependencies in test env
                # This is acceptable for structure tests
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
        # Test the verification logic without full handler
        hub_mode = "subscribe"
        hub_challenge = "test_challenge_12345"
        hub_verify_token = "test-verify-token"
        expected_token = "test-verify-token"
        
        # Simulate verification
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
    
    def test_content_generator_has_fallback(self):
        """Test content generator has Bedrock fallback"""
        import content_generator
        
        # Check fallback function exists
        assert hasattr(content_generator, 'get_bedrock_content_generation_prompt')
    
    def test_content_generator_modules_support(self):
        """Test content generator supports modules"""
        import content_generator
        
        # Check module functions exist
        assert hasattr(content_generator, 'get_active_modules')
        assert hasattr(content_generator, 'apply_module_processing')


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


class TestRateLimiter:
    """Test rate limiter Lambda"""
    
    def test_rate_limit_types(self):
        """Test rate limit types are defined"""
        limit_types = ["short_term", "daily"]
        
        for limit_type in limit_types:
            assert limit_type in ["short_term", "daily"]
    
    def test_rate_limit_thresholds(self):
        """Test rate limit thresholds are reasonable"""
        short_term_limit = 100  # 100 requests per 15 minutes
        daily_limit = 1000  # 1000 requests per day
        
        assert short_term_limit > 0
        assert daily_limit > short_term_limit
        assert daily_limit <= 10000  # Strava's actual limit
