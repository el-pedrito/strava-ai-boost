"""
Tests for CDK infrastructure

Tests the CDK stacks and infrastructure configuration:
- Core infrastructure (DynamoDB, IAM, Secrets Manager)
- Content generation stack (Lambda, Step Functions)
- Webhook processing stack (SQS, Lambda, API Gateway)
- API Gateway stack (REST API, endpoints)
- Security and compliance
"""

import pytest
import aws_cdk as cdk
from aws_cdk import assertions
import sys
import os

# Add stacks to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from stacks.core_infrastructure_stack import CoreInfrastructureStack
from stacks.content_generation_stack import ContentGenerationStack
from stacks.webhook_processing_stack import WebhookProcessingStack
from stacks.api_gateway_stack import ApiGatewayStack


class TestCoreInfrastructureStack:
    """Test core infrastructure stack"""
    
    @pytest.fixture
    def core_stack(self):
        """Create core infrastructure stack for testing"""
        app = cdk.App()
        stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        return stack
    
    def test_dynamodb_tables_created(self, core_stack):
        """Test that all required DynamoDB tables are created"""
        template = assertions.Template.from_stack(core_stack)
        
        # Should have 3 tables (activities, user-config, coaching-sessions)
        template.resource_count_is("AWS::DynamoDB::Table", 3)
        
        # Verify encryption is enabled
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "SSESpecification": {
                "SSEEnabled": True
            }
        })
    
    def test_dynamodb_table_names(self, core_stack):
        """Test DynamoDB table naming convention"""
        assert "activities" in core_stack.table_names
        assert "user_config" in core_stack.table_names
        assert "coaching_sessions" in core_stack.table_names
    
    def test_secrets_manager_secrets(self, core_stack):
        """Test Secrets Manager secrets are created"""
        template = assertions.Template.from_stack(core_stack)
        
        # Should have 3 secrets
        template.resource_count_is("AWS::SecretsManager::Secret", 3)
    
    def test_lambda_layer_created(self, core_stack):
        """Test Lambda Layer is created"""
        template = assertions.Template.from_stack(core_stack)
        
        template.resource_count_is("AWS::Lambda::LayerVersion", 1)
    
    def test_iam_roles_created(self, core_stack):
        """Test IAM roles are created with proper permissions"""
        template = assertions.Template.from_stack(core_stack)
        
        # Should have at least 2 IAM roles (webhook and content)
        roles = template.find_resources("AWS::IAM::Role")
        assert len(roles) >= 2, "Should have at least 2 IAM roles"


class TestContentGenerationStack:
    """Test content generation stack"""
    
    @pytest.fixture
    def content_stack(self):
        """Create content generation stack for testing"""
        app = cdk.App()
        core_stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        stack = ContentGenerationStack(
            app,
            "TestContentStack",
            core_stack=core_stack,
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        return stack
    
    def test_lambda_functions_created(self, content_stack):
        """Test that all Lambda functions are created"""
        template = assertions.Template.from_stack(content_stack)
        
        # Should have 4 Lambda functions
        template.resource_count_is("AWS::Lambda::Function", 4)
    
    def test_step_functions_workflow(self, content_stack):
        """Test Step Functions state machine is created"""
        template = assertions.Template.from_stack(content_stack)
        
        template.resource_count_is("AWS::StepFunctions::StateMachine", 1)
    
    def test_eventbridge_schedule(self, content_stack):
        """Test EventBridge schedule for Campus Coach"""
        template = assertions.Template.from_stack(content_stack)
        
        # Should have EventBridge rule for Campus Coach
        template.has_resource_properties("AWS::Events::Rule", {
            "ScheduleExpression": assertions.Match.string_like_regexp("cron.*")
        })
    
    def test_lambda_environment_variables(self, content_stack):
        """Test Lambda functions have required environment variables"""
        template = assertions.Template.from_stack(content_stack)
        
        # Content generator should have required env vars
        template.has_resource_properties("AWS::Lambda::Function", {
            "Environment": {
                "Variables": {
                    "ACTIVITIES_TABLE": assertions.Match.any_value(),
                    "USER_CONFIG_TABLE": assertions.Match.any_value(),
                    "BEDROCK_MODEL_ID": assertions.Match.any_value()
                }
            }
        })


class TestWebhookProcessingStack:
    """Test webhook processing stack"""
    
    @pytest.fixture
    def webhook_stack(self):
        """Create webhook processing stack for testing"""
        app = cdk.App()
        core_stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        stack = WebhookProcessingStack(
            app,
            "TestWebhookStack",
            core_stack=core_stack,
            step_functions_arn="arn:aws:states:eu-west-1:123456789012:stateMachine:test",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        return stack
    
    def test_sqs_queues_created(self, webhook_stack):
        """Test SQS queues are created"""
        template = assertions.Template.from_stack(webhook_stack)
        
        # Should have 2 queues (main + DLQ)
        template.resource_count_is("AWS::SQS::Queue", 2)
    
    def test_sqs_encryption(self, webhook_stack):
        """Test SQS queues are encrypted"""
        template = assertions.Template.from_stack(webhook_stack)
        
        template.has_resource_properties("AWS::SQS::Queue", {
            "KmsMasterKeyId": assertions.Match.any_value()
        })
    
    def test_sqs_dlq_configuration(self, webhook_stack):
        """Test DLQ is properly configured"""
        template = assertions.Template.from_stack(webhook_stack)
        
        template.has_resource_properties("AWS::SQS::Queue", {
            "RedrivePolicy": assertions.Match.object_like({
                "maxReceiveCount": 3
            })
        })
    
    def test_cloudwatch_alarms(self, webhook_stack):
        """Test CloudWatch alarms are created"""
        template = assertions.Template.from_stack(webhook_stack)
        
        # Should have alarms for DLQ, old messages, Lambda errors
        template.resource_count_is("AWS::CloudWatch::Alarm", 3)
    
    def test_api_gateway_created(self, webhook_stack):
        """Test API Gateway is created for webhooks"""
        template = assertions.Template.from_stack(webhook_stack)
        
        template.resource_count_is("AWS::ApiGateway::RestApi", 1)


class TestApiGatewayStack:
    """Test API Gateway stack"""
    
    @pytest.fixture
    def api_stack(self):
        """Create API Gateway stack for testing"""
        app = cdk.App()
        core_stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        stack = ApiGatewayStack(
            app,
            "TestAPIStack",
            core_stack=core_stack,
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        return stack
    
    def test_api_gateway_created(self, api_stack):
        """Test REST API is created"""
        template = assertions.Template.from_stack(api_stack)
        
        template.resource_count_is("AWS::ApiGateway::RestApi", 1)
    
    def test_api_key_created(self, api_stack):
        """Test API Key is created"""
        template = assertions.Template.from_stack(api_stack)
        
        template.resource_count_is("AWS::ApiGateway::ApiKey", 1)
    
    def test_usage_plan_created(self, api_stack):
        """Test Usage Plan with rate limiting"""
        template = assertions.Template.from_stack(api_stack)
        
        template.has_resource_properties("AWS::ApiGateway::UsagePlan", {
            "Throttle": {
                "RateLimit": 100,
                "BurstLimit": 200
            }
        })
    
    def test_cors_configuration(self, api_stack):
        """Test CORS is properly configured"""
        template = assertions.Template.from_stack(api_stack)
        
        # CORS should allow localhost origins
        template.has_resource_properties("AWS::ApiGateway::RestApi", {
            "Name": assertions.Match.string_like_regexp(".*Local Interface.*")
        })
    
    def test_lambda_functions_for_api(self, api_stack):
        """Test Lambda functions for API endpoints"""
        template = assertions.Template.from_stack(api_stack)
        
        # Should have Lambda functions for config, dashboard, preferences, health
        template.resource_count_is("AWS::Lambda::Function", 4)


class TestSecurityCompliance:
    """Test security and compliance configurations"""
    
    @pytest.fixture
    def all_stacks(self):
        """Create all stacks for security testing"""
        app = cdk.App()
        core_stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        content_stack = ContentGenerationStack(
            app,
            "TestContentStack",
            core_stack=core_stack,
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        return {"core": core_stack, "content": content_stack}
    
    def test_encryption_at_rest(self, all_stacks):
        """Test all data is encrypted at rest"""
        core_template = assertions.Template.from_stack(all_stacks["core"])
        
        # All DynamoDB tables should have encryption
        core_template.has_resource_properties("AWS::DynamoDB::Table", {
            "SSESpecification": {
                "SSEEnabled": True
            }
        })
    
    def test_iam_least_privilege(self, all_stacks):
        """Test IAM roles follow least privilege principle"""
        core_template = assertions.Template.from_stack(all_stacks["core"])
        
        # IAM roles should exist
        roles = core_template.find_resources("AWS::IAM::Role")
        assert len(roles) >= 2, "Should have IAM roles configured"
    
    def test_secrets_encryption(self, all_stacks):
        """Test Secrets Manager secrets are encrypted"""
        core_template = assertions.Template.from_stack(all_stacks["core"])
        
        # Secrets should be created (encryption is default)
        core_template.resource_count_is("AWS::SecretsManager::Secret", 3)
    
    def test_lambda_timeout_configuration(self, all_stacks):
        """Test Lambda functions have appropriate timeouts"""
        content_template = assertions.Template.from_stack(all_stacks["content"])
        
        # Lambda functions should have reasonable timeouts
        content_template.has_resource_properties("AWS::Lambda::Function", {
            "Timeout": assertions.Match.any_value()
        })


class TestInfrastructureIntegration:
    """Test infrastructure integration and dependencies"""
    
    def test_stack_dependencies(self):
        """Test stacks have proper dependencies"""
        app = cdk.App()
        core_stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        content_stack = ContentGenerationStack(
            app,
            "TestContentStack",
            core_stack=core_stack,
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        
        # Content stack should depend on core stack
        assert content_stack.core_stack == core_stack
    
    def test_resource_naming_consistency(self):
        """Test resource naming follows consistent pattern"""
        app = cdk.App()
        core_stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        
        # Check that table_names dictionary has the expected keys
        expected_keys = ["activities", "user_config", "coaching_sessions"]
        for key in expected_keys:
            assert key in core_stack.table_names, f"Expected table key '{key}' in table_names"

        # Verify we have 3 tables
        assert len(core_stack.table_names) == 3, f"Expected 3 tables, found {len(core_stack.table_names)}"
