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
    RemovalPolicy,
    Duration
)
from constructs import Construct
from typing import Dict, Any


class CoreInfrastructureStack(Stack):
    """Core infrastructure stack with DynamoDB tables and IAM roles"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create DynamoDB tables
        self._create_dynamodb_tables()
        
        # Create IAM roles
        self._create_iam_roles()
        
        # Create Secrets Manager secrets
        self._create_secrets()

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
                    "dynamodb:Query"
                ],
                resources=[
                    self.activities_table.table_arn,
                    self.rate_limits_table.table_arn,
                    f"{self.activities_table.table_arn}/index/*"
                ]
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
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
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
            description="Strava OAuth access and refresh tokens",
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