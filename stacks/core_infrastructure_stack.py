"""
Core Infrastructure Stack for Strava AI Boost

This stack creates the foundational AWS resources:
- DynamoDB tables for data storage
- IAM roles and policies with least privilege
- Secrets Manager for secure credential storage
- Core security configurations
"""

from aws_cdk import (
    Aws,
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

# Fixed name of the activity state machine created in content_generation_stack.py
# (kept here because Core is deployed first and cannot import Content's ARN).
ACTIVITY_STATE_MACHINE_NAME = "StravaAIBoost-ActivityProcessing"
# Fixed name of the InputWait Lambda (content_generation_stack.py): the Webhook
# stack alarms on its Errors metric by name, without a cross-stack reference.
INPUT_WAIT_FUNCTION_NAME = "StravaAIBoost-InputWait"

# Add src directory to path for config imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# Central Bedrock model registry — single source of truth for model IDs.
from config.llm_config import all_iam_resources


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
        """Create all required DynamoDB tables with encryption.

        RETAIN + PITR on every table (reliability plan lot 7): they hold the only
        copy of the athlete's history, so a stack deletion or an accidental
        replacement must orphan them, never delete them. Changing a removal
        policy only rewrites DeletionPolicy/UpdateReplacePolicy in the template,
        it does not replace the table.
        """
        
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
            removal_policy=RemovalPolicy.RETAIN,  # user data: survives a stack deletion
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
        )
        # Keep the whole history: TTL used to delete activities ~1 year after
        # processing. Disabled explicitly (not just omitted) so CloudFormation
        # turns it off on the live table. Old items still carry an `expires_at`
        # attribute; with TTL off it is inert, and it is not stripped item by
        # item because each write would fire the table stream (voice debrief).
        self.activities_table.node.default_child.add_property_override(
            "TimeToLiveSpecification",
            {"AttributeName": "expires_at", "Enabled": False},
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

        # Add GSI for querying user activities by date (coach historical context)
        self.activities_table.add_global_secondary_index(
            index_name="UserActivitiesIndex",
            partition_key=dynamodb.Attribute(
                name="user_id",
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
            removal_policy=RemovalPolicy.RETAIN
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
            removal_policy=RemovalPolicy.RETAIN
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

        self.coaching_sessions_table.add_global_secondary_index(
            index_name="IsoWeekIndex",
            partition_key=dynamodb.Attribute(
                name="iso_week",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="session_date",
                type=dynamodb.AttributeType.STRING
            )
        )

        # Wellness table - daily health signals, Campus home aggregates, and the
        # morning brief. PK=user_id (CAMPUS_OWNER_STRAVA_ID), SK=sk with prefixes
        # day#/brief#/campus#. RETAIN + PITR like the other user-data tables; no
        # TTL (health history is kept forever) and no stream (nothing reacts to a
        # wellness write — unlike the activities table which drives voice debrief).
        self.wellness_table = dynamodb.Table(
            self, "WellnessTable",
            table_name="strava-ai-boost-wellness",
            partition_key=dynamodb.Attribute(
                name="user_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="sk",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

    def _create_lambda_layer(self) -> None:
        """Create Lambda Layer for shared dependencies"""

        # Pin asset hash to avoid spurious layer replacements from filesystem metadata
        # changes (macOS xattrs). A layer replacement breaks cross-stack CF exports.
        # Update this hash only when lambda_layer/requirements.txt content changes
        # and you rebuild the layer zip. Run: build_layer.sh then cdk deploy.
        LAYER_ASSET_HASH = "480096d1e714d30a9d29ebbdc34f0f708841cc0ccd881c6eb6493cc5de9fd098"

        # Create Lambda Layer with all dependencies
        self.dependencies_layer = _lambda.LayerVersion(
            self, "StravaAIBoostDependenciesLayer",
            layer_version_name="strava-ai-boost-dependencies",
            code=_lambda.Code.from_asset("lambda_layer", asset_hash=LAYER_ASSET_HASH),
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
                    self.user_config_table.table_arn,
                    self.coaching_sessions_table.table_arn,
                    f"{self.activities_table.table_arn}/index/*",
                    f"{self.coaching_sessions_table.table_arn}/index/*"
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
                resources=[
                    f"arn:aws:sqs:{Aws.REGION}:{Aws.ACCOUNT_ID}:strava-ai-boost-activity-processing",
                    f"arn:aws:sqs:{Aws.REGION}:{Aws.ACCOUNT_ID}:strava-ai-boost-activity-processing-dlq"
                ]
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
                # The single state machine (Content stack, fixed name). Not a token
                # reference: Content depends on Core, so Core cannot import its ARN.
                resources=[
                    f"arn:aws:states:{Aws.REGION}:{Aws.ACCOUNT_ID}:stateMachine:{ACTIVITY_STATE_MACHINE_NAME}",
                    f"arn:aws:states:{Aws.REGION}:{Aws.ACCOUNT_ID}:execution:{ACTIVITY_STATE_MACHINE_NAME}:*"
                ]
            )
        )

        # Add Bedrock permissions for coach ask conversational endpoint
        self.webhook_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                # Registry models only (src/config/llm_config.py), no foundation-model/*.
                resources=all_iam_resources(region=Aws.REGION, account=Aws.ACCOUNT_ID)
            )
        )

        # Add AgentCore permissions for coach ask (invoke agent runtime)
        self.webhook_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=[f"arn:aws:bedrock-agentcore:{Aws.REGION}:{Aws.ACCOUNT_ID}:runtime/*"]
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
                # Registry models only (src/config/llm_config.py), no foundation-model/*.
                resources=all_iam_resources(region=self.region, account=Aws.ACCOUNT_ID)
            )
        )

        # Add permissions for AgentCore access
        self.content_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:GetAgentRuntime",
                    "bedrock-agentcore:ListAgentRuntimes"
                ],
                resources=[
                    f"arn:aws:bedrock-agentcore:{Aws.REGION}:{Aws.ACCOUNT_ID}:runtime/*"
                ]
            )
        )

        # (No Step Functions role here: the state machine's role lives in the
        # Content stack, next to the functions it invokes. The unused Core copy,
        # with its StravaAIBoost-* invoke grant, was removed 2026-10-12.)

    def _create_secrets(self) -> None:
        """Create Secrets Manager secrets for secure credential storage"""
        
        # Strava OAuth tokens
        self.strava_oauth_secret = secretsmanager.Secret(
            self, "StravaOAuthSecret",
            secret_name="strava-ai-boost-oauth-tokens",
            description="Strava OAuth access and refresh tokens for AI Boost",
            removal_policy=RemovalPolicy.RETAIN
        )

        # Strava App credentials (client_id and client_secret)
        self.strava_app_secret = secretsmanager.Secret(
            self, "StravaAppSecret",
            secret_name="strava-ai-boost-app-config",
            description="Strava application client ID and secret",
            removal_policy=RemovalPolicy.RETAIN
        )

        # Campus Coach credentials
        self.campus_coach_secret = secretsmanager.Secret(
            self, "CampusCoachSecret",
            secret_name="strava-ai-boost-campus-coach-credentials",
            description="Campus Coach login credentials for AgentCore Browser Tool",
            removal_policy=RemovalPolicy.RETAIN
        )

        # Intervals.icu API credentials
        self.intervals_icu_secret = secretsmanager.Secret(
            self, "IntervalsICUSecret",
            secret_name="strava-ai-boost-intervals-icu-credentials",
            description="Intervals.icu API key for fitness metrics",
            removal_policy=RemovalPolicy.RETAIN
        )

    @property
    def table_names(self) -> Dict[str, str]:
        """Return dictionary of table names for use in other stacks"""
        return {
            "activities": self.activities_table.table_name,
            "user_config": self.user_config_table.table_name,
            "coaching_sessions": self.coaching_sessions_table.table_name,
            "wellness": self.wellness_table.table_name
        }

    @property
    def table_arns(self) -> Dict[str, str]:
        """Return dictionary of table ARNs for use in other stacks"""
        return {
            "activities": self.activities_table.table_arn,
            "user_config": self.user_config_table.table_arn,
            "coaching_sessions": self.coaching_sessions_table.table_arn,
            "wellness": self.wellness_table.table_arn
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
                    self.intervals_icu_secret.secret_arn,
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
                    self.intervals_icu_secret.secret_arn,
                    self.strava_oauth_secret.secret_arn,
                    self.strava_app_secret.secret_arn
                ]
            )
        )
