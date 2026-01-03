"""
Core Infrastructure Stack for Strava AI Boost

This stack creates the foundational AWS resources:
- DynamoDB tables for data storage
- IAM roles and policies with least privilege
- Secrets Manager for secure credential storage
- Core security configurations
"""

from aws_cdk import (
    Stack,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_kms as kms,
    aws_lambda as _lambda,
    RemovalPolicy,
    Duration
)
from constructs import Construct
from typing import Dict, Any
import os
import sys

# Add src directory to path for config imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from config.llm_config import llm_config, get_model_arn
except ImportError:
    # Fallback for development
    def get_model_arn(region: str = None) -> str:
        import os
        region = region or "eu-west-1"
        model_id = os.environ.get('BEDROCK_MODEL_ID', 'global.anthropic.claude-sonnet-4-5-20250929-v1:0')
        return f"arn:aws:bedrock:{region}::foundation-model/{model_id}"


class CoreInfrastructureStack(Stack):
    """Core infrastructure stack with DynamoDB tables and IAM roles"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create DynamoDB tables
        self._create_dynamodb_tables()
        
        # Create Lambda Layer for dependencies
        self._create_lambda_layer()
        
        # Create IAM roles
        self._create_iam_roles()
        
        # Create Secrets Manager secrets
        self._create_secrets()
        
        # Add Secrets Manager permissions after secrets are created
        self._add_secrets_permissions()

    def _create_dynamodb_tables(self) -> None:
        """Create all required DynamoDB tables with encryption"""
        
        # Strava Activities table - stores activity data and processing status
        self.activities_table = dynamodb.Table(
            self, "StravaActivitiesTable",
            table_name="strava-ai-boost-activities",
            partition_key=dynamodb.Attribute(
                name="activity_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            removal_policy=RemovalPolicy.DESTROY,  # For development
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES
        )

        # Add GSI for querying by processing status
        self.activities_table.add_global_secondary_index(
            index_name="ProcessingStatusIndex",
            partition_key=dynamodb.Attribute(
                name="processing_status",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING
            )
        )

        # User Configuration table - stores user settings and module configurations
        self.user_config_table = dynamodb.Table(
            self, "UserConfigurationTable",
            table_name="strava-ai-boost-user-configuration",
            partition_key=dynamodb.Attribute(
                name="user_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            removal_policy=RemovalPolicy.DESTROY
        )

        # Strava Rate Limits table - tracks API usage
        self.rate_limits_table = dynamodb.Table(
            self, "StravaRateLimitsTable",
            table_name="strava-ai-boost-rate-limits",
            partition_key=dynamodb.Attribute(
                name="limit_type",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            # TTL for automatic cleanup of old rate limit data
            time_to_live_attribute="ttl"
        )

        # Campus Coaching Sessions table - stores extracted training sessions
        self.coaching_sessions_table = dynamodb.Table(
            self, "CampusCoachingSessionsTable",
            table_name="strava-ai-boost-campus-coaching-sessions",
            partition_key=dynamodb.Attribute(
                name="session_date",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="session_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            removal_policy=RemovalPolicy.DESTROY
        )

        # Add GSI for querying by week number
        self.coaching_sessions_table.add_global_secondary_index(
            index_name="WeekNumberIndex",
            partition_key=dynamodb.Attribute(
                name="week_number",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="session_date",
                type=dynamodb.AttributeType.STRING
            )
        )

    def _create_lambda_layer(self) -> None:
        """Create Lambda Layer for shared dependencies"""
        
        # Create Lambda Layer with all dependencies
        self.dependencies_layer = _lambda.LayerVersion(
            self, "StravaAIBoostDependenciesLayer",
            layer_version_name="strava-ai-boost-dependencies",
            code=_lambda.Code.from_asset("lambda_layer"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="Shared dependencies for Strava AI Boost Lambda functions",
            removal_policy=RemovalPolicy.DESTROY
        )

    def _create_iam_roles(self) -> None:
        """Create IAM roles with least privilege principle"""
        
        # Lambda execution role for webhook processing
        self.webhook_lambda_role = iam.Role(
            self, "WebhookLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Add permissions for DynamoDB access
        self.webhook_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:PutItem",
                    "dynamodb:GetItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ],
                resources=[
                    self.activities_table.table_arn,
                    self.rate_limits_table.table_arn,
                    self.user_config_table.table_arn,
                    self.coaching_sessions_table.table_arn,
                    f"{self.activities_table.table_arn}/index/*"
                ]
            )
        )
        
        # Add permissions for SQS access (for queue depth monitoring)
        self.webhook_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl"
                ],
                resources=["*"]  # Will be restricted by queue URLs in environment variables
            )
        )
        
        # Add permissions for Step Functions access (for workflow status monitoring)
        self.webhook_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "states:ListExecutions",
                    "states:DescribeExecution",
                    "states:GetExecutionHistory"
                ],
                resources=["*"]  # Will be restricted by state machine ARN in environment variables
            )
        )

        # Lambda execution role for content generation
        self.content_lambda_role = iam.Role(
            self, "ContentLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Add permissions for Bedrock access
        self.content_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=[
                    get_model_arn(self.region)
                ]
            )
        )

        # Add permissions for AgentCore access
        self.content_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:InvokeAgent",
                    "bedrock-agentcore:GetAgent",
                    "bedrock-agentcore:ListAgents"
                ],
                resources=["*"]  # AgentCore resources are dynamic
            )
        )

        # Step Functions execution role
        self.step_functions_role = iam.Role(
            self, "StepFunctionsRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaRole"
                )
            ]
        )

        # Add permissions for Lambda invocation
        self.step_functions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "lambda:InvokeFunction"
                ],
                resources=[f"arn:aws:lambda:{self.region}:{self.account}:function:StravaAIBoost-*"]
            )
        )

    def _create_secrets(self) -> None:
        """Create Secrets Manager secrets for secure credential storage"""
        
        # Strava OAuth tokens
        self.strava_oauth_secret = secretsmanager.Secret(
            self, "StravaOAuthSecret",
            secret_name="strava-ai-boost-oauth-tokens",
            description="Strava OAuth access and refresh tokens for AI Boost",
            removal_policy=RemovalPolicy.DESTROY
        )

        # Strava App credentials (client_id and client_secret)
        self.strava_app_secret = secretsmanager.Secret(
            self, "StravaAppSecret",
            secret_name="strava-ai-boost-app-config",
            description="Strava application client ID and secret",
            removal_policy=RemovalPolicy.DESTROY
        )

        # Campus Coach credentials
        self.campus_coach_secret = secretsmanager.Secret(
            self, "CampusCoachSecret",
            secret_name="strava-ai-boost-campus-coach-credentials",
            description="Campus Coach login credentials for AgentCore Browser Tool",
            removal_policy=RemovalPolicy.DESTROY
        )

    @property
    def table_names(self) -> Dict[str, str]:
        """Return dictionary of table names for use in other stacks"""
        return {
            "activities": self.activities_table.table_name,
            "user_config": self.user_config_table.table_name,
            "rate_limits": self.rate_limits_table.table_name,
            "coaching_sessions": self.coaching_sessions_table.table_name
        }

    @property
    def table_arns(self) -> Dict[str, str]:
        """Return dictionary of table ARNs for use in other stacks"""
        return {
            "activities": self.activities_table.table_arn,
            "user_config": self.user_config_table.table_arn,
            "rate_limits": self.rate_limits_table.table_arn,
            "coaching_sessions": self.coaching_sessions_table.table_arn
        }

    
    def _add_secrets_permissions(self) -> None:
        """Add Secrets Manager permissions after secrets are created"""
        # Add permissions for Secrets Manager read access (for all Lambdas)
        self.webhook_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret"
                ],
                resources=[
                    self.campus_coach_secret.secret_arn,
                    self.strava_oauth_secret.secret_arn,
                    self.strava_app_secret.secret_arn
                ]
            )
        )
        
        # Add permissions for Secrets Manager write access (for configuration)
        # Updated 2026-01-03: Added strava_app_secret for configuration API
        self.webhook_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:CreateSecret",
                    "secretsmanager:UpdateSecret",
                    "secretsmanager:PutSecretValue"
                ],
                resources=[
                    self.campus_coach_secret.secret_arn,
                    self.strava_oauth_secret.secret_arn,
                    self.strava_app_secret.secret_arn
                ]
            )
        )
