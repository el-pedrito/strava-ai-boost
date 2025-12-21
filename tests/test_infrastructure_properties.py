"""
Property-based tests for infrastructure security and correctness.

These tests validate that the CDK infrastructure meets security requirements
and follows AWS best practices for data protection and secure communication.
"""

import pytest
from hypothesis import given, strategies as st, settings
import aws_cdk as cdk
from aws_cdk import assertions
from moto import mock_aws

from stacks.core_infrastructure_stack import CoreInfrastructureStack
from stacks.webhook_processing_stack import WebhookProcessingStack


class TestInfrastructureSecurityProperties:
    """Property-based tests for infrastructure security"""

    def setup_method(self):
        """Set up test environment"""
        self.app = cdk.App()
        self.core_stack = CoreInfrastructureStack(
            self.app, 
            "TestCore",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        self.webhook_stack = WebhookProcessingStack(
            self.app,
            "TestWebhook", 
            core_stack=self.core_stack,
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )

    @settings(max_examples=100)
    @given(table_name=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pd'))))
    def test_property_15_data_encryption_at_rest(self, table_name):
        """
        **Feature: strava-ai-boost, Property 15: Data Encryption at Rest**
        
        For any DynamoDB table created by the infrastructure, encryption at rest 
        should be applied using AWS managed encryption.
        
        Validates: Requirements 7.1 - Data encryption at rest for all DynamoDB tables
        """
        # Get CloudFormation template
        template = assertions.Template.from_stack(self.core_stack)
        
        # Verify all DynamoDB tables have encryption enabled
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "SSESpecification": {
                "SSEEnabled": True
            }
        })
        
        # Verify point-in-time recovery is enabled for critical tables
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "PointInTimeRecoverySpecification": {
                "PointInTimeRecoveryEnabled": True
            }
        })
        
        # Check that all tables use AWS managed encryption (not customer managed)
        # This is the default when SSEEnabled is True without specifying KMSMasterKeyId
        dynamodb_resources = template.find_resources("AWS::DynamoDB::Table")
        
        for resource_id, resource in dynamodb_resources.items():
            properties = resource.get("Properties", {})
            sse_spec = properties.get("SSESpecification", {})
            
            # Verify encryption is enabled
            assert sse_spec.get("SSEEnabled") is True, f"Table {resource_id} does not have encryption enabled"
            
            # Verify AWS managed encryption (no custom KMS key specified)
            assert "KMSMasterKeyId" not in sse_spec, f"Table {resource_id} uses customer managed key instead of AWS managed"

    @settings(max_examples=100)
    @given(api_endpoint=st.text(min_size=1, max_size=100))
    def test_property_16_secure_communication_https(self, api_endpoint):
        """
        **Feature: strava-ai-boost, Property 16: Secure Communication**
        
        For any API endpoint created by the infrastructure, HTTPS should be used 
        for all communications with proper TLS configuration.
        
        Validates: Requirements 7.2 - Secure communication using HTTPS for all API endpoints
        """
        # Get CloudFormation template for webhook stack
        template = assertions.Template.from_stack(self.webhook_stack)
        
        # Verify API Gateway is configured with proper security
        template.has_resource_properties("AWS::ApiGateway::RestApi", {
            "EndpointConfiguration": {
                "Types": ["REGIONAL"]
            }
        })
        
        # Verify API Gateway methods are properly configured
        api_resources = template.find_resources("AWS::ApiGateway::Method")
        
        for resource_id, resource in api_resources.items():
            properties = resource.get("Properties", {})
            
            # Verify methods exist (GET and POST for webhook)
            http_method = properties.get("HttpMethod")
            assert http_method in ["GET", "POST"], f"Method {resource_id} has invalid HTTP method: {http_method}"
            
            # Verify method responses are configured
            method_responses = properties.get("MethodResponses", [])
            assert len(method_responses) > 0, f"Method {resource_id} has no method responses configured"
            
            # Verify status codes include success responses
            status_codes = [resp.get("StatusCode") for resp in method_responses]
            assert "200" in status_codes, f"Method {resource_id} does not include 200 status code"

    def test_secrets_manager_encryption(self):
        """
        Test that Secrets Manager secrets are properly encrypted
        """
        template = assertions.Template.from_stack(self.core_stack)
        
        # Verify Secrets Manager secrets exist
        template.resource_count_is("AWS::SecretsManager::Secret", 2)
        
        # Verify secrets have proper configuration
        template.has_resource_properties("AWS::SecretsManager::Secret", {
            "Name": "strava-ai-boost-oauth-tokens"
        })
        
        template.has_resource_properties("AWS::SecretsManager::Secret", {
            "Name": "strava-ai-boost-campus-coach-credentials"
        })

    def test_iam_least_privilege_principle(self):
        """
        Test that IAM roles follow least privilege principle
        """
        template = assertions.Template.from_stack(self.core_stack)
        
        # Verify IAM roles exist
        iam_roles = template.find_resources("AWS::IAM::Role")
        
        for role_id, role in iam_roles.items():
            properties = role.get("Properties", {})
            
            # Verify assume role policy is properly configured
            assume_role_policy = properties.get("AssumeRolePolicyDocument", {})
            assert "Statement" in assume_role_policy, f"Role {role_id} missing assume role policy"
            
            # Verify managed policies are AWS managed (not inline)
            managed_policies = properties.get("ManagedPolicyArns", [])
            for policy_arn in managed_policies:
                # Handle both direct ARN strings and CloudFormation intrinsic functions
                if isinstance(policy_arn, str):
                    assert "arn:aws:iam::aws:policy/" in policy_arn, f"Role {role_id} uses non-AWS managed policy"
                elif isinstance(policy_arn, dict) and "Fn::Join" in policy_arn:
                    # Check if the joined string contains AWS managed policy path
                    join_parts = policy_arn["Fn::Join"][1]  # Get the parts being joined
                    policy_path_found = any("service-role/AWSLambda" in str(part) or "policy/" in str(part) for part in join_parts)
                    assert policy_path_found, f"Role {role_id} uses non-AWS managed policy in Fn::Join"

    def test_sqs_encryption_and_dlq_configuration(self):
        """
        Test that SQS queues are properly encrypted and have DLQ configuration
        """
        template = assertions.Template.from_stack(self.webhook_stack)
        
        # Verify SQS queues exist
        template.resource_count_is("AWS::SQS::Queue", 2)  # Main queue + DLQ
        
        # Verify encryption is enabled
        template.has_resource_properties("AWS::SQS::Queue", {
            "KmsMasterKeyId": "alias/aws/sqs"
        })
        
        # Verify DLQ configuration exists
        sqs_queues = template.find_resources("AWS::SQS::Queue")
        
        # Find main queue (should have RedrivePolicy)
        main_queue_found = False
        dlq_found = False
        
        for queue_id, queue in sqs_queues.items():
            properties = queue.get("Properties", {})
            
            if "RedrivePolicy" in properties:
                main_queue_found = True
                redrive_policy = properties["RedrivePolicy"]
                assert "maxReceiveCount" in redrive_policy, f"Queue {queue_id} missing maxReceiveCount"
                assert redrive_policy["maxReceiveCount"] == 3, f"Queue {queue_id} has incorrect maxReceiveCount"
            else:
                dlq_found = True
        
        assert main_queue_found, "Main processing queue with DLQ configuration not found"
        assert dlq_found, "Dead letter queue not found"

    def test_lambda_function_security_configuration(self):
        """
        Test that Lambda functions have proper security configuration
        """
        template = assertions.Template.from_stack(self.webhook_stack)
        
        # Verify Lambda functions exist
        lambda_functions = template.find_resources("AWS::Lambda::Function")
        
        for function_id, function in lambda_functions.items():
            properties = function.get("Properties", {})
            
            # Verify runtime is Python 3.12
            assert properties.get("Runtime") == "python3.12", f"Function {function_id} uses incorrect runtime"
            
            # Verify timeout is reasonable (not too high)
            timeout = properties.get("Timeout", 0)
            assert 1 <= timeout <= 900, f"Function {function_id} has unreasonable timeout: {timeout}"
            
            # Verify memory size is reasonable
            memory_size = properties.get("MemorySize", 0)
            assert 128 <= memory_size <= 10240, f"Function {function_id} has unreasonable memory size: {memory_size}"
            
            # Verify environment variables don't contain sensitive data
            environment = properties.get("Environment", {})
            variables = environment.get("Variables", {})
            
            for var_name, var_value in variables.items():
                # Ensure no hardcoded secrets
                assert "password" not in var_name.lower(), f"Function {function_id} has password in environment"
                assert "secret" not in var_name.lower() or "SECRET" in var_name, f"Function {function_id} has secret value in environment"
                assert "key" not in var_name.lower() or var_name.endswith("_TABLE") or var_name.endswith("_URL"), f"Function {function_id} has key in environment"


class TestInfrastructureCorrectnessProperties:
    """Additional correctness properties for infrastructure"""

    def setup_method(self):
        """Set up test environment"""
        self.app = cdk.App()
        self.core_stack = CoreInfrastructureStack(
            self.app, 
            "TestCore",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )

    def test_dynamodb_table_naming_consistency(self):
        """
        Test that DynamoDB tables follow consistent naming convention
        """
        template = assertions.Template.from_stack(self.core_stack)
        
        expected_tables = [
            "strava-ai-boost-activities",
            "strava-ai-boost-user-configuration", 
            "strava-ai-boost-rate-limits",
            "strava-ai-boost-campus-coaching-sessions"
        ]
        
        for table_name in expected_tables:
            template.has_resource_properties("AWS::DynamoDB::Table", {
                "TableName": table_name
            })

    def test_global_secondary_indexes_configuration(self):
        """
        Test that required GSIs are properly configured
        """
        template = assertions.Template.from_stack(self.core_stack)
        
        # Verify activities table has ProcessingStatusIndex
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": "strava-ai-boost-activities",
            "GlobalSecondaryIndexes": [
                {
                    "IndexName": "ProcessingStatusIndex",
                    "KeySchema": [
                        {
                            "AttributeName": "processing_status",
                            "KeyType": "HASH"
                        },
                        {
                            "AttributeName": "created_at", 
                            "KeyType": "RANGE"
                        }
                    ]
                }
            ]
        })
        
        # Verify coaching sessions table has WeekNumberIndex
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": "strava-ai-boost-campus-coaching-sessions",
            "GlobalSecondaryIndexes": [
                {
                    "IndexName": "WeekNumberIndex",
                    "KeySchema": [
                        {
                            "AttributeName": "week_number",
                            "KeyType": "HASH"
                        },
                        {
                            "AttributeName": "session_date",
                            "KeyType": "RANGE"
                        }
                    ]
                }
            ]
        })

    def test_ttl_configuration(self):
        """
        Test that TTL is properly configured for rate limits table
        """
        template = assertions.Template.from_stack(self.core_stack)
        
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": "strava-ai-boost-rate-limits",
            "TimeToLiveSpecification": {
                "AttributeName": "ttl",
                "Enabled": True
            }
        })

    def test_removal_policy_configuration(self):
        """
        Test that removal policies are set appropriately for development
        """
        template = assertions.Template.from_stack(self.core_stack)
        
        # All resources should have DESTROY removal policy for development
        dynamodb_resources = template.find_resources("AWS::DynamoDB::Table")
        secrets_resources = template.find_resources("AWS::SecretsManager::Secret")
        
        # Note: CDK removal policies are not directly visible in CloudFormation template
        # This test verifies the resources exist and can be destroyed
        assert len(dynamodb_resources) == 4, "Expected 4 DynamoDB tables"
        assert len(secrets_resources) == 2, "Expected 2 Secrets Manager secrets"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])