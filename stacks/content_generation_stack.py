"""
Content Generation Stack for Strava AI Boost

This stack creates the infrastructure for AI-powered content generation:
- Step Functions workflow for activity processing orchestration
- Lambda functions for content generation using Bedrock and AgentCore
- Integration with AgentCore Memory for personalization
"""

from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
    aws_iam as iam,
    Duration,
    aws_logs as logs,
    Aws
)
from constructs import Construct
from .core_infrastructure_stack import CoreInfrastructureStack
from typing import Dict
import os
import sys

# Add src directory to path for config imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from config.llm_config import llm_config, get_model_arn, get_bedrock_model_id
except ImportError:
    # Fallback for development
    def get_model_arn(region: str = None) -> str:
        import os
        region = region or "eu-west-1"
        model_id = os.environ.get('BEDROCK_MODEL_ID', 'global.anthropic.claude-sonnet-4-5-20250929-v1:0')
        return f"arn:aws:bedrock:{region}::foundation-model/{model_id}"
    def get_bedrock_model_id() -> str:
        import os
        return os.environ.get('BEDROCK_MODEL_ID', 'global.anthropic.claude-sonnet-4-5-20250929-v1:0')


class ContentGenerationStack(Stack):
    """Content generation stack with Step Functions and Bedrock integration"""

    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        core_stack: CoreInfrastructureStack,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.core_stack = core_stack
        
        # Create Lambda functions
        self._create_lambda_functions()
        
        # Create Step Functions workflow
        self._create_step_functions_workflow()

    def _get_base_environment_variables(self) -> Dict[str, str]:
        """
        Get base environment variables for Lambda functions including AgentCore ARNs
        
        Reads from .env.agentcore file if available
        
        Returns:
            Dictionary of base environment variables
        """
        # Try to read from .env.agentcore file
        env_file_path = os.path.join(os.path.dirname(__file__), '..', '.env.agentcore')
        env_vars = {
            # Default values
            "CONTENT_GENERATION_AGENT_ARN": "",
            "CAMPUS_COACH_AGENT_ARN": "",
            "BEDROCK_AGENTCORE_MEMORY_ID": "",
            "AGENTCORE_AGENTS_AVAILABLE": "false",
            "AGENTCORE_REGION": Aws.REGION,
            "CONTENT_GENERATION_AGENT_NAME": "",
            "CAMPUS_COACH_AGENT_NAME": ""
        }
        
        # Read from .env.agentcore if it exists
        if os.path.exists(env_file_path):
            try:
                with open(env_file_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        # Skip comments and empty lines
                        if not line or line.startswith('#'):
                            continue
                        # Parse KEY=VALUE
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            # Only update if key is in our env_vars
                            if key in env_vars:
                                env_vars[key] = value
                            # Also check for AGENTCORE_AGENTS_AVAILABLE
                            elif key == 'AGENTCORE_AGENTS_AVAILABLE':
                                env_vars['AGENTCORE_AGENTS_AVAILABLE'] = value
                
                print(f"✅ Loaded AgentCore configuration from .env.agentcore")
                print(f"   CONTENT_GENERATION_AGENT_ARN: {env_vars['CONTENT_GENERATION_AGENT_ARN'][:50]}...")
                print(f"   CAMPUS_COACH_AGENT_ARN: {env_vars['CAMPUS_COACH_AGENT_ARN'][:50]}...")
            except Exception as e:
                print(f"⚠️  Warning: Could not read .env.agentcore: {e}")
        else:
            print(f"⚠️  Warning: .env.agentcore not found at {env_file_path}")
        
        return env_vars

    def _create_lambda_functions(self) -> None:
        """Create Lambda functions for content generation pipeline"""
        
        # Create IAM role for content generation Lambda functions
        content_lambda_role = iam.Role(
            self, "ContentLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Add permissions for DynamoDB access
        content_lambda_role.add_to_policy(
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
                    self.core_stack.activities_table.table_arn,
                    self.core_stack.user_config_table.table_arn,
                    self.core_stack.coaching_sessions_table.table_arn,
                    f"{self.core_stack.activities_table.table_arn}/index/*",
                    f"{self.core_stack.coaching_sessions_table.table_arn}/index/*"
                ]
            )
        )

        # Add permissions for Bedrock access (foundation models and inference profiles across all regions)
        content_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=[
                    # Foundation models in all regions
                    "arn:aws:bedrock:*::foundation-model/*",
                    # Inference profiles in current account and region
                    f"arn:aws:bedrock:{Aws.REGION}:{Aws.ACCOUNT_ID}:inference-profile/*"
                ]
            )
        )

        # Add permissions for AgentCore access
        content_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeAgent",
                    "bedrock:GetAgent",
                    "bedrock:ListAgents"
                ],
                resources=["*"]  # AgentCore resources are dynamic
            )
        )

        # Add permissions for Secrets Manager access
        content_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue"
                ],
                resources=[
                    self.core_stack.strava_oauth_secret.secret_arn,
                    self.core_stack.campus_coach_secret.secret_arn
                ]
            )
        )

        # Create IAM role for activity fetcher and updater Lambda functions
        strava_lambda_role = iam.Role(
            self, "StravaLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Add permissions for DynamoDB access
        strava_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:PutItem",
                    "dynamodb:GetItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query"
                ],
                resources=[
                    self.core_stack.activities_table.table_arn,
                    self.core_stack.user_config_table.table_arn,
                    self.core_stack.rate_limits_table.table_arn,
                    f"{self.core_stack.activities_table.table_arn}/index/*"
                ]
            )
        )

        # Add permissions for Secrets Manager access (read AND write for token refresh)
        strava_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:UpdateSecret"  # Required for OAuth token refresh
                ],
                resources=[
                    self.core_stack.strava_oauth_secret.secret_arn,
                    self.core_stack.strava_app_secret.secret_arn
                ]
            )
        )
        
        # Content generation Lambda with Bedrock and AgentCore
        self.content_generator = lambda_.Function(
            self, "ContentGenerator",
            function_name="StravaAIBoost-ContentGenerator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="content_generator.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.minutes(5),
            memory_size=1024,
            role=content_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "COACHING_SESSIONS_TABLE": self.core_stack.table_names["coaching_sessions"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name,
                "CAMPUS_COACH_SECRET": self.core_stack.campus_coach_secret.secret_name,
                "BEDROCK_MODEL_ID": get_bedrock_model_id(),
                # Base environment variables (AgentCore will be populated in Phase 2)
                **self._get_base_environment_variables()
            }
        )

        # Campus Coach invoker Lambda for AgentCore Browser Tool
        self.campus_coach_invoker = lambda_.Function(
            self, "CampusCoachInvoker",
            function_name="StravaAIBoost-CampusCoachInvoker",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="campus_coach_invoker.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.minutes(10),  # Campus Coach extraction can take time
            memory_size=512,
            role=content_lambda_role,
            environment={
                "COACHING_SESSIONS_TABLE": self.core_stack.table_names["coaching_sessions"],
                "CAMPUS_COACH_SECRET": self.core_stack.campus_coach_secret.secret_name,
                "BEDROCK_MODEL_ID": get_bedrock_model_id(),
                # Base environment variables (AgentCore will be populated in Phase 2)
                **self._get_base_environment_variables()
            }
        )

        # Activity data fetcher Lambda
        self.activity_fetcher = lambda_.Function(
            self, "ActivityFetcher",
            function_name="StravaAIBoost-ActivityFetcher",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="activity_fetcher.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.minutes(3),
            memory_size=512,
            role=strava_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "RATE_LIMITS_TABLE": self.core_stack.table_names["rate_limits"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name,
                "STRAVA_APP_SECRET": self.core_stack.strava_app_secret.secret_name,
                "BEDROCK_MODEL_ID": get_bedrock_model_id()
            }
        )

        # Strava updater Lambda
        self.strava_updater = lambda_.Function(
            self, "StravaUpdater",
            function_name="StravaAIBoost-StravaUpdater",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="strava_updater.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.minutes(2),
            memory_size=256,
            role=strava_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "RATE_LIMITS_TABLE": self.core_stack.table_names["rate_limits"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name,
                "BEDROCK_MODEL_ID": get_bedrock_model_id()
            }
        )

    def _create_step_functions_workflow(self) -> None:
        """Create Step Functions workflow for activity processing"""
        
        # Create IAM role for Step Functions
        step_functions_role = iam.Role(
            self, "StepFunctionsRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com")
        )

        # Add permissions for Lambda invocation
        step_functions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "lambda:InvokeFunction"
                ],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account}:function:StravaAIBoost-*"
                ]
            )
        )

        # Add permissions for CloudWatch Logs
        step_functions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogDelivery",
                    "logs:GetLogDelivery",
                    "logs:UpdateLogDelivery",
                    "logs:DeleteLogDelivery",
                    "logs:ListLogDeliveries",
                    "logs:PutResourcePolicy",
                    "logs:DescribeResourcePolicies",
                    "logs:DescribeLogGroups"
                ],
                resources=["*"]
            )
        )
        
        # Create CloudWatch log group for Step Functions
        log_group = logs.LogGroup(
            self, "ActivityProcessingLogGroup",
            log_group_name="/aws/stepfunctions/strava-ai-boost-activity-processing",
            retention=logs.RetentionDays.ONE_WEEK
        )

        # Define Step Functions tasks
        
        # Transform input task
        transform_input = sfn.Pass(
            self, "TransformInput",
            comment="Transform and validate webhook input data",
            parameters={
                "activity_id.$": "$.activity_id",
                "user_id.$": "$.user_id",
                "webhook_data.$": "$.webhook_data",
                "processing_timestamp.$": "$$.State.EnteredTime"
            }
        )

        # Fetch activity data task
        fetch_activity = sfn_tasks.LambdaInvoke(
            self, "FetchActivityData",
            lambda_function=self.activity_fetcher,
            comment="Fetch complete activity data from Strava API",
            payload_response_only=True,
            retry_on_service_exceptions=True
        )

        # Check if activity fetch was successful
        check_fetch_success = sfn.Choice(
            self, "CheckFetchSuccess",
            comment="Check if activity data was fetched successfully"
        )

        # Handle fetch failure
        fetch_failed = sfn.Fail(
            self, "FetchFailed",
            comment="Failed to fetch activity data from Strava API",
            cause_path="$.error"
        )

        # Store backup task
        store_backup = sfn.Pass(
            self, "StoreBackup",
            comment="Store original activity description in DynamoDB",
            result_path="$.backup_info",
            parameters={
                "activity_id.$": "$.activity_id",
                "original_description.$": "$.activity_data.description",
                "backup_timestamp.$": "$$.State.EnteredTime"
            }
        )

        # Check if Campus Coach module is enabled
        check_campus_coach = sfn.Choice(
            self, "CheckCampusCoachEnabled",
            comment="Check if Campus Coach module is enabled for this user"
        )

        # Campus Coach session extraction task (conditional)
        extract_campus_sessions = sfn_tasks.LambdaInvoke(
            self, "ExtractCampusSessions",
            lambda_function=self.campus_coach_invoker,
            comment="Extract Campus Coach sessions using AgentCore Browser Tool",
            payload_response_only=True,
            retry_on_service_exceptions=True,
            input_path="$",
            result_path="$.campus_coach_result"
        )

        # Skip Campus Coach extraction
        skip_campus_coach = sfn.Pass(
            self, "SkipCampusCoach",
            comment="Skip Campus Coach extraction - module not enabled",
            result_path="$.campus_coach_result",
            result=sfn.Result.from_object({
                "statusCode": 200,
                "skipped": True,
                "reason": "Campus Coach module not enabled"
            })
        )

        # Generate content task
        generate_content = sfn_tasks.LambdaInvoke(
            self, "GenerateContent",
            lambda_function=self.content_generator,
            comment="Generate enhanced content using Bedrock AI and AgentCore Memory",
            payload_response_only=True,
            retry_on_service_exceptions=True
        )

        # Update Strava task
        update_strava = sfn_tasks.LambdaInvoke(
            self, "UpdateStrava",
            lambda_function=self.strava_updater,
            comment="Update Strava activity with enhanced content",
            payload_response_only=True,
            retry_on_service_exceptions=True
        )

        # Success state
        success = sfn.Succeed(
            self, "ProcessingComplete",
            comment="Activity processing completed successfully"
        )

        # Failure state
        failure = sfn.Fail(
            self, "ProcessingFailed",
            comment="Activity processing failed",
            cause="Step Functions workflow execution failed"
        )

        # Error handling for each step
        fetch_activity.add_catch(
            failure,
            errors=["States.ALL"]
        )

        extract_campus_sessions.add_catch(
            failure,
            errors=["States.ALL"]
        )

        generate_content.add_catch(
            failure,
            errors=["States.ALL"]
        )

        update_strava.add_catch(
            failure,
            errors=["States.ALL"]
        )

        # Define workflow with error handling and Campus Coach conditional logic
        
        # Configure fetch success check
        check_fetch_success.when(
            sfn.Condition.number_equals("$.statusCode", 200),
            store_backup.next(check_campus_coach)
        ).otherwise(
            fetch_failed
        )
        
        # Configure Campus Coach choice conditions
        check_campus_coach.when(
            sfn.Condition.and_(
                sfn.Condition.is_present("$.user_config.modules_config.campus_coach.enabled"),
                sfn.Condition.boolean_equals("$.user_config.modules_config.campus_coach.enabled", True)
            ),
            extract_campus_sessions.next(generate_content)
        ).otherwise(
            skip_campus_coach.next(generate_content)
        )
        
        definition = (
            transform_input
            .next(fetch_activity)
            .next(check_fetch_success)
        )
        
        # Both Campus Coach paths lead to content generation, then update, then success
        generate_content.next(update_strava).next(success)

        # Create Step Functions state machine
        self.state_machine = sfn.StateMachine(
            self, "ActivityProcessingWorkflow",
            state_machine_name="StravaAIBoost-ActivityProcessing",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.minutes(30),
            role=step_functions_role,
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL
            )
        )

        # Grant Step Functions permission to invoke Lambda functions
        for lambda_function in [
            self.activity_fetcher,
            self.campus_coach_invoker,
            self.content_generator,
            self.strava_updater
        ]:
            lambda_function.grant_invoke(step_functions_role)

    @property
    def state_machine_arn(self) -> str:
        """Return the Step Functions state machine ARN"""
        return self.state_machine.state_machine_arn