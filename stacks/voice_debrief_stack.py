"""
Voice Debrief Stack for Strava AI Boost

This stack creates infrastructure for the V1 audio debrief feature:
- Private S3 bucket for MP3 storage (BLOCK_ALL public access, lifecycle 90d, server access logging)
- Lambda VoiceDebriefGenerator triggered by DynamoDB Stream on the activities table
  (filters items where processing_status=completed AND audio_debrief_generated_at is absent)
- Lambda AudioDebriefAPI behind the existing API Gateway returning a presigned GET URL (1h)

Security policy compliance:
- Bucket: BLOCK_ALL public access, S3-managed encryption, enforce SSL, versioned, access logs
- Lambda IAM: scoped to specific Polly voices, specific Bedrock Haiku 4.5 model, table ARN, bucket ARN
- API access: Cognito JWT (configured in api_gateway_stack when wired)
"""

from typing import Optional

from aws_cdk import (
    Aws,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_events,
    aws_s3 as s3,
)
from constructs import Construct

from .core_infrastructure_stack import CoreInfrastructureStack

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# Central Bedrock model registry — single source of truth for model IDs.
from config.llm_config import get_bedrock_model_id, get_haiku_model_id, iam_resources_for


class VoiceDebriefStack(Stack):
    """Audio debrief infrastructure (Polly + private S3 + DynamoDB stream trigger)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        core_stack: CoreInfrastructureStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.core_stack = core_stack

        self._create_buckets()
        self._create_generator_lambda()
        self._create_api_lambda()

    # ------------------------------------------------------------------
    # S3 buckets
    # ------------------------------------------------------------------
    def _create_buckets(self) -> None:
        # Access logs bucket (sensitive operations -> server access logging)
        self.access_logs_bucket = s3.Bucket(
            self,
            "AudioDebriefAccessLogsBucket",
            bucket_name=f"strava-ai-boost-audio-access-logs-{Aws.ACCOUNT_ID}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=False,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireAccessLogs",
                    expiration=Duration.days(90),
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Audio debriefs bucket (private, MP3 storage)
        self.audio_bucket = s3.Bucket(
            self,
            "AudioDebriefsBucket",
            bucket_name=f"strava-ai-boost-audio-debriefs-{Aws.ACCOUNT_ID}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            server_access_logs_bucket=self.access_logs_bucket,
            server_access_logs_prefix="audio-debriefs/",
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireAudioAfter90Days",
                    expiration=Duration.days(90),
                    abort_incomplete_multipart_upload_after=Duration.days(7),
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        CfnOutput(
            self,
            "AudioDebriefBucketName",
            value=self.audio_bucket.bucket_name,
            description="S3 bucket storing voice debrief MP3 files (private)",
        )

    # ------------------------------------------------------------------
    # Generator Lambda (DynamoDB Stream trigger)
    # ------------------------------------------------------------------
    def _create_generator_lambda(self) -> None:
        role = iam.Role(
            self,
            "VoiceDebriefGeneratorRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # DynamoDB Stream read permissions (the table itself + its stream)
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:DescribeStream",
                    "dynamodb:GetRecords",
                    "dynamodb:GetShardIterator",
                    "dynamodb:ListStreams",
                ],
                resources=[
                    f"{self.core_stack.activities_table.table_arn}/stream/*"
                ],
            )
        )

        # Read full item + write audio_debrief_* fields
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:UpdateItem",
                ],
                resources=[self.core_stack.activities_table.table_arn],
            )
        )

        # Read user preferences (for language selection)
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:GetItem"],
                resources=[self.core_stack.user_config_table.table_arn],
            )
        )

        # Bedrock InvokeModel — scoped to Haiku 4.5 inference profile + foundation model
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=iam_resources_for(get_haiku_model_id(), region=Aws.REGION, account=Aws.ACCOUNT_ID),
            )
        )

        # Polly synthesize_speech — neural voices
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["polly:SynthesizeSpeech"],
                resources=["*"],  # Polly does not support resource-level permissions
            )
        )

        # S3 write to audio bucket (object-level only)
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:PutObject", "s3:PutObjectAcl"],
                resources=[self.audio_bucket.arn_for_objects("*")],
            )
        )

        self.generator_lambda = lambda_.Function(
            self,
            "VoiceDebriefGenerator",
            function_name="StravaAIBoost-VoiceDebriefGenerator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="processing.voice_debrief_generator.handler",
            code=lambda_.Code.from_asset(
                "lambda_functions",
                # Bytecode caches are regenerated by any local test run and would
                # otherwise change the asset hash, forcing pointless redeploys of
                # every function and making `cdk diff` useless as a
                # deployed-equals-source signal.
                exclude=["**/__pycache__", "**/*.pyc"],
            ),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.minutes(2),
            memory_size=512,
            role=role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "AUDIO_DEBRIEF_BUCKET": self.audio_bucket.bucket_name,
                "BEDROCK_MODEL_ID": get_haiku_model_id(),
                "POLLY_VOICE_FR": "Ambre",
                "POLLY_VOICE_EN": "Joanna",
                "POLLY_ENGINE": "generative",
            },
            description="V1 voice debrief generator (Polly TTS + Bedrock Haiku 4.5)",
        )

        # DynamoDB Stream event source — only NEW images, filtered downstream in handler
        self.generator_lambda.add_event_source(
            lambda_events.DynamoEventSource(
                self.core_stack.activities_table,
                starting_position=lambda_.StartingPosition.LATEST,
                batch_size=10,
                bisect_batch_on_error=True,
                retry_attempts=2,
                report_batch_item_failures=True,
            )
        )

        CfnOutput(
            self,
            "VoiceDebriefGeneratorArn",
            value=self.generator_lambda.function_arn,
            description="ARN of the voice debrief generator Lambda",
        )

    # ------------------------------------------------------------------
    # API Lambda (presigned URL endpoint)
    # ------------------------------------------------------------------
    def _create_api_lambda(self) -> None:
        role = iam.Role(
            self,
            "AudioDebriefApiRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # Read activity (to verify ownership before issuing presigned URL)
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:GetItem"],
                resources=[self.core_stack.activities_table.table_arn],
            )
        )

        # GetObject on audio bucket — required to sign URLs
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject"],
                resources=[self.audio_bucket.arn_for_objects("*")],
            )
        )

        self.api_lambda = lambda_.Function(
            self,
            "AudioDebriefAPI",
            function_name="StravaAIBoost-AudioDebriefAPI",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="api.audio_debrief_api.handler",
            code=lambda_.Code.from_asset(
                "lambda_functions",
                # Bytecode caches are regenerated by any local test run and would
                # otherwise change the asset hash, forcing pointless redeploys of
                # every function and making `cdk diff` useless as a
                # deployed-equals-source signal.
                exclude=["**/__pycache__", "**/*.pyc"],
            ),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(10),
            memory_size=256,
            role=role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "AUDIO_DEBRIEF_BUCKET": self.audio_bucket.bucket_name,
                "PRESIGNED_URL_TTL_SECONDS": "3600",
            },
            description="Returns a 1h presigned URL for an activity audio debrief",
        )

        CfnOutput(
            self,
            "AudioDebriefApiLambdaArn",
            value=self.api_lambda.function_arn,
            description="ARN of the audio debrief API Lambda (wire into API Gateway)",
        )

        self._create_weekly_recap()

    # ------------------------------------------------------------------
    # Weekly Audio Recap (EventBridge schedule + on-demand)
    # ------------------------------------------------------------------
    def _create_weekly_recap(self) -> None:
        from aws_cdk import aws_dynamodb as dynamodb, aws_events as events, aws_events_targets as targets

        # DynamoDB table for recap metadata
        self.recap_table = dynamodb.Table(
            self,
            "RecapTable",
            table_name="strava-ai-boost-weekly-recaps",
            partition_key=dynamodb.Attribute(name="user_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="week", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        role = iam.Role(
            self,
            "WeeklyRecapRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # DynamoDB: read activities + user config, read/write recaps
        role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:Query"],
            resources=[
                self.core_stack.activities_table.table_arn,
                f"{self.core_stack.activities_table.table_arn}/index/*",
            ],
        ))
        role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:GetItem"],
            resources=[self.core_stack.user_config_table.table_arn],
        ))
        role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:GetItem", "dynamodb:PutItem"],
            resources=[self.recap_table.table_arn],
        ))

        # AgentCore Memory read (personalize the recap with LTM observations).
        # The role previously had NO bedrock-agentcore action: the memory read
        # failed silently since day one (see docs/design/memory-improvements.md).
        role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock-agentcore:RetrieveMemoryRecords"],
            resources=[f"arn:aws:bedrock-agentcore:{Aws.REGION}:{Aws.ACCOUNT_ID}:memory/*"],
        ))

        # Bedrock Sonnet (higher quality for recap)
        role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=iam_resources_for(get_bedrock_model_id(), region=Aws.REGION, account=Aws.ACCOUNT_ID),
        ))

        # Polly
        role.add_to_policy(iam.PolicyStatement(
            actions=["polly:SynthesizeSpeech"],
            resources=["*"],
        ))

        # S3 write recaps
        role.add_to_policy(iam.PolicyStatement(
            actions=["s3:PutObject"],
            resources=[self.audio_bucket.arn_for_objects("recaps/*")],
        ))

        self.recap_lambda = lambda_.Function(
            self,
            "WeeklyAudioRecap",
            function_name="StravaAIBoost-WeeklyAudioRecap",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="support.weekly_audio_recap.handler",
            code=lambda_.Code.from_asset(
                "lambda_functions",
                # Bytecode caches are regenerated by any local test run and would
                # otherwise change the asset hash, forcing pointless redeploys of
                # every function and making `cdk diff` useless as a
                # deployed-equals-source signal.
                exclude=["**/__pycache__", "**/*.pyc"],
            ),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.minutes(3),
            memory_size=512,
            role=role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "RECAP_TABLE": "strava-ai-boost-weekly-recaps",
                "AUDIO_DEBRIEF_BUCKET": self.audio_bucket.bucket_name,
                "BEDROCK_MODEL_ID": get_bedrock_model_id(),
                "POLLY_VOICE_FR": "Ambre",
                "POLLY_VOICE_EN": "Joanna",
                "DEFAULT_USER_ID": self.node.try_get_context("default_user_id") or "",
                "BEDROCK_AGENTCORE_MEMORY_ID": self._load_memory_id(),
            },
            description="Weekly audio recap generator (Sunday 20h + on-demand)",
        )

        # EventBridge: Sunday 20:00 UTC
        events.Rule(
            self,
            "WeeklyRecapSchedule",
            schedule=events.Schedule.cron(minute="0", hour="20", week_day="SUN"),
            targets=[targets.LambdaFunction(self.recap_lambda)],
            description="Trigger weekly audio recap every Sunday at 20:00 UTC",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_memory_id(self) -> str:
        from .env_loader import load_agentcore_memory_id
        return load_agentcore_memory_id()

    # ------------------------------------------------------------------
    # Public references
    # ------------------------------------------------------------------
    @property
    def audio_bucket_name(self) -> str:
        return self.audio_bucket.bucket_name
