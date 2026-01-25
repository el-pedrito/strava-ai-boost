"""
Feedback Loop Stack

Infrastructure for automatic feedback analysis and learning from user modifications.
"""

import os
import yaml
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    Aws,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
)
from constructs import Construct


class FeedbackLoopStack(Stack):
    """
    Stack for feedback loop infrastructure
    
    Components:
    - DynamoDB table for memory versions (versioning/rollback)
    - Lambda function for feedback analysis
    - EventBridge schedule rule (nightly at 3 AM)
    - IAM permissions (least privilege)
    """
    
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        activities_table: dynamodb.Table,
        strava_oauth_secret,
        strava_app_secret,  # Add app secret for token refresh
        dependencies_layer,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Load MEMORY_ID from .env.agentcore
        memory_id = self._load_memory_id_from_env()
        
        # ============================================
        # Lambda: Feedback Analyzer
        # ============================================
        
        feedback_analyzer = lambda_.Function(
            self, "FeedbackAnalyzer",
            function_name="StravaAIBoost-FeedbackAnalyzer",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="feedback_analyzer.lambda_handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[dependencies_layer],
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                'ACTIVITIES_TABLE': activities_table.table_name,
                'STRAVA_OAUTH_SECRET': strava_oauth_secret.secret_name,
                'BEDROCK_MODEL_ID': os.environ.get('BEDROCK_MODEL_ID', 'global.anthropic.claude-sonnet-4-5-20250929-v1:0'),
                'BEDROCK_AGENTCORE_MEMORY_ID': memory_id  # Loaded from .env.agentcore
                # AWS_REGION is automatically set by Lambda runtime
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )
        
        # ============================================
        # IAM Permissions (Least Privilege)
        # ============================================
        
        # DynamoDB permissions
        activities_table.grant_read_write_data(feedback_analyzer)
        
        # Secrets Manager permissions (OAuth tokens + app config for refresh)
        strava_oauth_secret.grant_read(feedback_analyzer)
        strava_oauth_secret.grant_write(feedback_analyzer)  # For token refresh
        strava_app_secret.grant_read(feedback_analyzer)  # For client credentials
        
        # Bedrock permissions (for pattern analysis via Bedrock)
        feedback_analyzer.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=[
                    # Foundation models in all regions
                    "arn:aws:bedrock:*::foundation-model/*",
                    # Inference profiles (for global models like Claude Sonnet 4.5)
                    f"arn:aws:bedrock:{Aws.REGION}:{Aws.ACCOUNT_ID}:inference-profile/*"
                ]
            )
        )
        
        # AgentCore Memory permissions (for writing feedback patterns)
        feedback_analyzer.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:GetEvents",
                    "bedrock-agentcore:ListEvents"
                ],
                resources=[
                    f"arn:aws:bedrock-agentcore:{Aws.REGION}:{Aws.ACCOUNT_ID}:memory/*"
                ]
            )
        )
        
        # ============================================
        # EventBridge Schedule Rule
        # ============================================
        
        # Trigger daily at 3 AM UTC
        schedule_rule = events.Rule(
            self, "FeedbackAnalyzerSchedule",
            rule_name="strava-ai-boost-feedback-analyzer-schedule",
            description="Trigger feedback analyzer daily at 3 AM UTC",
            schedule=events.Schedule.cron(
                hour='3',
                minute='0',
                month='*',
                week_day='*',
                year='*'
            ),
            enabled=True
        )
        
        # Add Lambda as target
        schedule_rule.add_target(
            targets.LambdaFunction(feedback_analyzer)
        )
        
        # ============================================
        # Outputs
        # ============================================
        
        self.feedback_analyzer = feedback_analyzer
    
    def _load_memory_id_from_env(self) -> str:
        """Load MEMORY_ID from .env.agentcore file"""
        env_file_path = os.path.join(os.path.dirname(__file__), '..', '.env.agentcore')
        
        if os.path.exists(env_file_path):
            try:
                with open(env_file_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('BEDROCK_AGENTCORE_MEMORY_ID='):
                            memory_id = line.split('=', 1)[1].strip()
                            print(f"✅ Loaded MEMORY_ID from .env.agentcore: {memory_id}")
                            return memory_id
            except Exception as e:
                print(f"⚠️  Warning: Could not read .env.agentcore: {e}")
        
        # Fallback: try to read from .bedrock_agentcore.yaml
        yaml_path = os.path.join(os.path.dirname(__file__), '..', '.bedrock_agentcore.yaml')
        if os.path.exists(yaml_path):
            try:
                import yaml
                with open(yaml_path, 'r') as f:
                    config = yaml.safe_load(f)
                    memory_id = config.get('agents', {}).get('content_gen', {}).get('memory', {}).get('memory_id', '')
                    if memory_id:
                        print(f"✅ Loaded MEMORY_ID from .bedrock_agentcore.yaml: {memory_id}")
                        return memory_id
            except Exception as e:
                print(f"⚠️  Warning: Could not read .bedrock_agentcore.yaml: {e}")
        
        print(f"⚠️  Warning: MEMORY_ID not found, using empty string")
        return ''
