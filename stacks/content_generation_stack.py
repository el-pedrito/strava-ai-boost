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
from .core_infrastructure_stack import ACTIVITY_STATE_MACHINE_NAME, CoreInfrastructureStack
from typing import Dict
import os
import sys

# Add src directory to path for config imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# Central Bedrock model registry — single source of truth for model IDs.
from config.llm_config import (
    get_bedrock_model_id,
    get_haiku_model_id,
    all_iam_resources,
)


class ContentGenerationStack(Stack):
    """Content generation stack with Step Functions and Bedrock integration"""

    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        core_stack: CoreInfrastructureStack,
        security_stack=None,  # Optional security stack for guardrails
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.core_stack = core_stack
        self.security_stack = security_stack
        
        # Create Lambda functions
        self._create_lambda_functions()
        
        # Create Step Functions workflow
        self._create_step_functions_workflow()

    def _get_base_environment_variables(self) -> Dict[str, str]:
        """Get base environment variables for Lambda functions including AgentCore ARNs"""
        from .env_loader import load_env_agentcore

        env_vars = {
            "CONTENT_GENERATION_AGENT_ARN": "",
            "COACH_AGENT_ARN": "",
            # No BEDROCK_AGENTCORE_MEMORY_ID here: neither Lambda of this stack
            # touches AgentCore Memory (the runtimes carry their own id). A key
            # set to "" looked configured and hid 11 weeks of skipped writes.
            "AGENTCORE_AGENTS_AVAILABLE": "false",
            # Central model registry (src/config/llm_config.py)
            "BEDROCK_HAIKU_MODEL_ID": get_haiku_model_id(),
            "AGENTCORE_REGION": Aws.REGION,
            "CONTENT_GENERATION_AGENT_NAME": "",
        }

        loaded = load_env_agentcore()
        for key in list(env_vars.keys()) + ['AGENTCORE_AGENTS_AVAILABLE']:
            if key in loaded:
                env_vars[key] = loaded[key]

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

        # Add permissions for Bedrock access (scoped to specific models via inference profiles)
        # @secure_recommendation: least privilege — only Sonnet 5 + Haiku 4.5 (models used by content_gen and campus_coach)
        content_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=all_iam_resources(region=Aws.REGION, account=Aws.ACCOUNT_ID)
            )
        )

        # Add permissions for AgentCore access
        content_lambda_role.add_to_policy(
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

        # AgentCore Memory permissions (create events, retrieve records)
        content_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                    "bedrock-agentcore:ListMemoryRecords",
                    "bedrock-agentcore:ListActors",
                    "bedrock-agentcore:ListSessions",
                    "bedrock-agentcore:ListEvents"
                ],
                resources=[
                    f"arn:aws:bedrock-agentcore:{Aws.REGION}:{Aws.ACCOUNT_ID}:memory/*"
                ]
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
                    self.core_stack.strava_app_secret.secret_arn,
                    self.core_stack.intervals_icu_secret.secret_arn
                ]
            )
        )

        # Content generation Lambda with Bedrock and AgentCore
        self.content_generator = lambda_.Function(
            self, "ContentGenerator",
            function_name="StravaAIBoost-ContentGenerator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="processing.content_generator.handler",
            code=lambda_.Code.from_asset(
                "lambda_functions",
                # Bytecode caches are regenerated by any local test run and would
                # otherwise change the asset hash, forcing pointless redeploys of
                # every function and making `cdk diff` useless as a
                # deployed-equals-source signal.
                exclude=["**/__pycache__", "**/*.pyc"],
            ),
            layers=[self.core_stack.dependencies_layer],
            # Up to two agent calls (generation + one guarded correction), each
            # bounded by the client's 300s read timeout. 2 min was below a single
            # Sonnet 5 generation on context-rich interval sessions.
            timeout=Duration.minutes(11),
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

        # Campus Coach session retrieval is handled by the daily REST sync
        # (strava-ai-boost-campus-coach-daily-sync, webhook stack). The legacy
        # AgentCore Browser Tool agent + invoker Lambda were decommissioned.

        # Coach Generator Lambda (parallel branch)
        self.coach_generator = lambda_.Function(
            self, "CoachGenerator",
            function_name="StravaAIBoost-CoachGenerator",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="processing.coach_generator.handler",
            code=lambda_.Code.from_asset(
                "lambda_functions",
                # Bytecode caches are regenerated by any local test run and would
                # otherwise change the asset hash, forcing pointless redeploys of
                # every function and making `cdk diff` useless as a
                # deployed-equals-source signal.
                exclude=["**/__pycache__", "**/*.pyc"],
            ),
            layers=[self.core_stack.dependencies_layer],
            # Coach feedback + one corrective call, each up to the client's 170s
            # read timeout, plus cold-start backoff.
            timeout=Duration.minutes(6),
            memory_size=1024,
            role=content_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "COACHING_SESSIONS_TABLE": self.core_stack.table_names["coaching_sessions"],
                "BEDROCK_MODEL_ID": get_bedrock_model_id(),
                **self._get_base_environment_variables()
            }
        )

        # Assembly Lambda (merges parallel outputs)
        self.assembly_lambda = lambda_.Function(
            self, "AssemblyLambda",
            function_name="StravaAIBoost-Assembly",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="processing.assembly_lambda.handler",
            code=lambda_.Code.from_asset(
                "lambda_functions",
                # Bytecode caches are regenerated by any local test run and would
                # otherwise change the asset hash, forcing pointless redeploys of
                # every function and making `cdk diff` useless as a
                # deployed-equals-source signal.
                exclude=["**/__pycache__", "**/*.pyc"],
            ),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(30),
            memory_size=256,
            role=content_lambda_role,
            environment={}
        )

        # Activity data fetcher Lambda
        self.activity_fetcher = lambda_.Function(
            self, "ActivityFetcher",
            function_name="StravaAIBoost-ActivityFetcher",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="processing.activity_fetcher.handler",
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
            role=strava_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name,
                "STRAVA_APP_SECRET": self.core_stack.strava_app_secret.secret_name,
                "INTERVALS_ICU_SECRET": self.core_stack.intervals_icu_secret.secret_name,
                "BEDROCK_MODEL_ID": get_bedrock_model_id()
            }
        )

        self._create_input_wait_lambda()

        # Strava updater Lambda
        self.strava_updater = lambda_.Function(
            self, "StravaUpdater",
            function_name="StravaAIBoost-StravaUpdater",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="processing.strava_updater.handler",
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
            memory_size=256,
            role=strava_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name,
                "BEDROCK_MODEL_ID": get_bedrock_model_id()
            }
        )

    def _create_input_wait_lambda(self) -> None:
        """InputWait: opens the athlete-input window and sends the push request.

        Its own role, least privilege: UpdateItem on the activities table and
        states:SendTaskSuccess only (no Failure, no Heartbeat). The PushSend
        invoke grant and PUSH_* variables are added from app.py when the Push
        stack exists; without them the Lambda closes the window and releases the
        execution at once.
        """
        input_wait_role = iam.Role(
            self, "InputWaitRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        input_wait_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:UpdateItem"],
                resources=[self.core_stack.activities_table.table_arn],
            )
        )
        # SendTaskSuccess has no resource type (Service Authorization Reference):
        # Resource "*" is the only accepted value. Justified IAM5 suppression in
        # stacks/nag_suppressions.py.
        input_wait_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["states:SendTaskSuccess"],
                resources=["*"],
            )
        )
        self.input_wait = lambda_.Function(
            self, "InputWait",
            function_name="StravaAIBoost-InputWait",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="athlete_input.input_wait.handler",
            code=lambda_.Code.from_asset(
                "lambda_functions",
                exclude=["**/__pycache__", "**/*.pyc"],
            ),
            layers=[self.core_stack.dependencies_layer],
            # Above the 90 s PushSend timeout it waits on synchronously.
            timeout=Duration.seconds(120),
            memory_size=256,
            role=input_wait_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
            },
        )

    # Errors a later attempt can fix (reliability plan, lot 3). TransientAgentError is
    # raised by content_generator / coach_generator on a 502/503/504, throttling or
    # timeout of the AgentCore runtime (2026-10-09: activity 20518589504 lost to one
    # 502 of a cold content_gen runtime). StravaRateLimitError is raised by
    # strava_updater once its own 429 backoff is spent.
    TRANSIENT_TASK_ERRORS = [
        "Lambda.ServiceException",
        "Lambda.TooManyRequestsException",
        "Sandbox.Timedout",
        "TransientAgentError",
    ]
    # What retry_on_service_exceptions=True used to cover minus Lambda.ServiceException,
    # which now belongs to the transient retrier above (one error, one retrier).
    LAMBDA_SDK_ERRORS = [
        "Lambda.AWSLambdaException",
        "Lambda.SdkClientException",
        "Lambda.ClientExecutionTimeoutException",
    ]

    @classmethod
    def _add_transient_retries(
        cls, task: sfn_tasks.LambdaInvoke, extra_errors: list = None
    ) -> None:
        """Retry a generation/publish task on transient errors.

        2 attempts, 10s then 20s: enough for a cold AgentCore container to boot
        (a few seconds) without stretching a genuinely broken run.
        """
        task.add_retry(
            errors=cls.TRANSIENT_TASK_ERRORS + list(extra_errors or []),
            interval=Duration.seconds(10),
            max_attempts=2,
            backoff_rate=2,
        )
        task.add_retry(
            errors=cls.LAMBDA_SDK_ERRORS,
            interval=Duration.seconds(2),
            max_attempts=6,
            backoff_rate=2,
        )

    def _create_step_functions_workflow(self) -> None:
        """Create Step Functions workflow for activity processing"""
        
        # Create IAM role for Step Functions
        step_functions_role = iam.Role(
            self, "StepFunctionsRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com")
        )

        # Lambda invoke: granted per function (grant_invoke loop after the state
        # machine, plus the LambdaInvoke tasks themselves), no StravaAIBoost-* wildcard.

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

        # Athlete input (RPE + summary), docs/design/rpe-athlete-input.md §3.
        # The Choice reads the RAW execution input, before TransformInput: an
        # execution started by a processor that predates the field (the state
        # machine deploys first) has no wait_for_input, and IsPresent keeps that
        # case on the old path instead of raising States.Runtime.
        wait_for_athlete_input = sfn_tasks.LambdaInvoke(
            self, "WaitForAthleteInput",
            lambda_function=self.input_wait,
            comment="Ask the athlete for RPE + summary, wait up to 1 h for the callback",
            integration_pattern=sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
            payload=sfn.TaskInput.from_object({
                "activity_id.$": "$.activity_id",
                "user_id.$": "$.user_id",
                "task_token": sfn.JsonPath.task_token,
            }),
            task_timeout=sfn.Timeout.duration(Duration.hours(1)),
            result_path=sfn.JsonPath.DISCARD,
            # A retry would mint a new token and find the window already open.
            retry_on_service_exceptions=False,
        )
        # Fail open (D4, D8): timeout or any error goes on to TransformInput.
        # States.ALL covers States.Timeout and must be alone in its list.
        wait_for_athlete_input.add_catch(
            transform_input, errors=["States.ALL"], result_path="$.input_wait_error"
        )
        wait_for_athlete_input.next(transform_input)
        should_wait_for_input = sfn.Choice(
            self, "ShouldWaitForInput",
            comment="wait_for_input = athlete_input module on AND Strava create",
        )
        should_wait_for_input.when(
            sfn.Condition.and_(
                sfn.Condition.is_present("$.wait_for_input"),
                sfn.Condition.boolean_equals("$.wait_for_input", True),
            ),
            wait_for_athlete_input,
        ).otherwise(transform_input)

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

        # Generate content task (Branch 1)
        generate_content = sfn_tasks.LambdaInvoke(
            self, "GenerateContent",
            lambda_function=self.content_generator,
            comment="Generate enhanced content using Bedrock AI and AgentCore Memory",
            payload_response_only=True,
            retry_on_service_exceptions=False  # explicit retriers below
        )

        # Coach generator task (Branch 2)
        generate_coach = sfn_tasks.LambdaInvoke(
            self, "GenerateCoach",
            lambda_function=self.coach_generator,
            comment="Generate coaching feedback with historical context",
            payload_response_only=True,
            retry_on_service_exceptions=False  # explicit retriers below
        )

        # Retries come before the catches below: Step Functions evaluates Retry first.
        self._add_transient_retries(generate_content)
        self._add_transient_retries(generate_coach)

        # Coach branch catches errors and returns null result
        coach_error_fallback = sfn.Pass(
            self, "CoachErrorFallback",
            result=sfn.Result.from_object({"statusCode": 500, "coach_feedback": None})
        )
        generate_coach.add_catch(coach_error_fallback, errors=["States.ALL"])

        # Parallel execution of content + coach
        parallel_generation = sfn.Parallel(
            self, "ParallelGeneration",
            comment="Run content generation and coach generation in parallel"
        )
        parallel_generation.branch(generate_content)
        parallel_generation.branch(generate_coach)

        # Assembly task (merges parallel outputs)
        assemble_content = sfn_tasks.LambdaInvoke(
            self, "AssembleContent",
            lambda_function=self.assembly_lambda,
            comment="Merge content and coach outputs",
            payload_response_only=True,
            retry_on_service_exceptions=True
        )

        # Update Strava task
        update_strava = sfn_tasks.LambdaInvoke(
            self, "UpdateStrava",
            lambda_function=self.strava_updater,
            comment="Update Strava activity with enhanced content",
            payload_response_only=True,
            retry_on_service_exceptions=False  # explicit retriers below
        )

        self._add_transient_retries(update_strava, extra_errors=["StravaRateLimitError"])

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

        # Error handling
        fetch_activity.add_catch(failure, errors=["States.ALL"])
        parallel_generation.add_catch(failure, errors=["States.ALL"])
        assemble_content.add_catch(failure, errors=["States.ALL"])
        update_strava.add_catch(failure, errors=["States.ALL"])

        # Configure fetch success check - go to parallel generation
        check_fetch_success.when(
            sfn.Condition.number_equals("$.statusCode", 200),
            parallel_generation
        ).otherwise(
            fetch_failed
        )
        
        transform_input.next(fetch_activity).next(check_fetch_success)
        # The Choice is the start state.
        definition = should_wait_for_input
        
        # The Lambdas answer ordinary errors with a {"statusCode": 500} payload
        # instead of raising, so a failed generation or update used to reach
        # ProcessingComplete. Both payloads are checked: a non-200 fails the
        # execution, which the Step Functions error handler then records (status
        # failed + DLQ). The coach branch is not checked here: its failure is a
        # degraded run (no coach block), not a failed one.
        content_failed = sfn.Fail(
            self, "ContentGenerationFailed",
            comment="Content generation answered a non-200 payload",
            cause="Content generation failed",
        )
        update_failed = sfn.Fail(
            self, "StravaUpdateFailed",
            comment="Strava update answered a non-200 payload",
            cause="Strava update failed",
        )
        check_content_success = sfn.Choice(
            self, "CheckContentSuccess",
            comment="The merged payload carries the content branch statusCode",
        )
        check_update_success = sfn.Choice(
            self, "CheckUpdateSuccess",
            comment="Did UpdateStrava publish (or have nothing to change)?",
        )
        check_content_success.when(
            sfn.Condition.number_equals("$.statusCode", 200), update_strava
        ).otherwise(content_failed)
        check_update_success.when(
            sfn.Condition.number_equals("$.statusCode", 200), success
        ).otherwise(update_failed)

        # Parallel → Assembly → check → Update → check → Success
        parallel_generation.next(assemble_content).next(check_content_success)
        update_strava.next(check_update_success)

        # Create Step Functions state machine
        self.state_machine = sfn.StateMachine(
            self, "ActivityProcessingWorkflow",
            state_machine_name=ACTIVITY_STATE_MACHINE_NAME,
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            # 1 h athlete-input wait + content (up to 2 x 11 min) + coach + update.
            timeout=Duration.minutes(120),
            role=step_functions_role,
            # ALL events (cdk-nag SF1), but WITHOUT execution data: state inputs and
            # outputs carry the athlete's activity, titles and coach text, which have
            # no business in a 1-week troubleshooting log. Volume is a few executions
            # a day, so the extra events cost nothing measurable.
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=False,
            ),
            tracing_enabled=True,  # X-Ray (cdk-nag SF2); Lambdas already trace.
        )

        # Grant Step Functions permission to invoke Lambda functions
        for lambda_function in [
            self.activity_fetcher,
            self.content_generator,
            self.coach_generator,
            self.assembly_lambda,
            self.strava_updater,
            self.input_wait,
        ]:
            lambda_function.grant_invoke(step_functions_role)

    @property
    def state_machine_arn(self) -> str:
        """Return the Step Functions state machine ARN"""
        return self.state_machine.state_machine_arn