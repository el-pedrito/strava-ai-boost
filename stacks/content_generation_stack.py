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
    aws_logs as logs
)
from constructs import Construct
from .core_infrastructure_stack import CoreInfrastructureStack
from .webhook_processing_stack import WebhookProcessingStack


class ContentGenerationStack(Stack):
    """Content generation stack with Step Functions and Bedrock integration"""

    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        core_stack: CoreInfrastructureStack,
        webhook_stack: WebhookProcessingStack,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.core_stack = core_stack
        self.webhook_stack = webhook_stack
        
        # Create Lambda functions
        self._create_lambda_functions()
        
        # Create Step Functions workflow
        self._create_step_functions_workflow()

    def _create_lambda_functions(self) -> None:
        """Create Lambda functions for content generation pipeline"""
        
        # Content generation Lambda with Bedrock and AgentCore
        self.content_generator = lambda_.Function(
            self, "ContentGenerator",
            function_name="StravaAIBoost-ContentGenerator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="content_generator.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            timeout=Duration.minutes(5),
            memory_size=1024,
            role=self.core_stack.content_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "COACHING_SESSIONS_TABLE": self.core_stack.table_names["coaching_sessions"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name,
                "CAMPUS_COACH_SECRET": self.core_stack.campus_coach_secret.secret_name
            }
        )

        # Campus Coach invoker Lambda for AgentCore Browser Tool
        self.campus_coach_invoker = lambda_.Function(
            self, "CampusCoachInvoker",
            function_name="StravaAIBoost-CampusCoachInvoker",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="campus_coach_invoker.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            timeout=Duration.minutes(10),  # Campus Coach extraction can take time
            memory_size=512,
            role=self.core_stack.content_lambda_role,
            environment={
                "COACHING_SESSIONS_TABLE": self.core_stack.table_names["coaching_sessions"],
                "CAMPUS_COACH_SECRET": self.core_stack.campus_coach_secret.secret_name
            }
        )

        # Activity data fetcher Lambda
        self.activity_fetcher = lambda_.Function(
            self, "ActivityFetcher",
            function_name="StravaAIBoost-ActivityFetcher",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="activity_fetcher.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            timeout=Duration.minutes(3),
            memory_size=512,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "RATE_LIMITS_TABLE": self.core_stack.table_names["rate_limits"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name
            }
        )

        # Strava updater Lambda
        self.strava_updater = lambda_.Function(
            self, "StravaUpdater",
            function_name="StravaAIBoost-StravaUpdater",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="strava_updater.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            timeout=Duration.minutes(2),
            memory_size=256,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "RATE_LIMITS_TABLE": self.core_stack.table_names["rate_limits"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name
            }
        )

    def _create_step_functions_workflow(self) -> None:
        """Create Step Functions workflow for activity processing"""
        
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

        # Store backup task
        store_backup = sfn.Pass(
            self, "StoreBackup",
            comment="Store original activity description in DynamoDB",
            parameters={
                "activity_id.$": "$.activity_id",
                "original_description.$": "$.activity_data.description",
                "backup_timestamp.$": "$$.State.EnteredTime"
            }
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

        generate_content.add_catch(
            failure,
            errors=["States.ALL"]
        )

        update_strava.add_catch(
            failure,
            errors=["States.ALL"]
        )

        # Define workflow
        definition = (
            transform_input
            .next(fetch_activity)
            .next(store_backup)
            .next(generate_content)
            .next(update_strava)
            .next(success)
        )

        # Create Step Functions state machine
        self.state_machine = sfn.StateMachine(
            self, "ActivityProcessingWorkflow",
            state_machine_name="StravaAIBoost-ActivityProcessing",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.minutes(30),
            role=self.core_stack.step_functions_role,
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL
            )
        )

        # Grant Step Functions permission to invoke Lambda functions
        for lambda_function in [
            self.activity_fetcher,
            self.content_generator,
            self.strava_updater
        ]:
            lambda_function.grant_invoke(self.core_stack.step_functions_role)

    @property
    def state_machine_arn(self) -> str:
        """Return the Step Functions state machine ARN"""
        return self.state_machine.state_machine_arn