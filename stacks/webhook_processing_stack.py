"""
Webhook Processing Stack for Strava AI Boost

This stack creates the infrastructure for processing Strava webhooks:
- SQS queue with dead letter queue for reliable message processing
- Lambda function for webhook validation and queuing
- EventBridge rules for webhook subscription management
"""

from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_events,
    aws_sqs as sqs,
    aws_apigateway as apigateway,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_secretsmanager as secretsmanager,
    aws_dynamodb as dynamodb,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subscriptions,
    aws_budgets as budgets,
    Duration
)
from constructs import Construct
from .core_infrastructure_stack import CoreInfrastructureStack


class WebhookProcessingStack(Stack):
    """Webhook processing stack for Strava webhooks and SQS queuing"""

    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        core_stack: CoreInfrastructureStack,
        step_functions_arn: str = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.core_stack = core_stack
        self.step_functions_arn = step_functions_arn
        
        # Create SQS queues
        self._create_sqs_queues()
        
        # Create Lambda functions
        self._create_lambda_functions()
        
        # Create Step Functions error handler (if Step Functions ARN provided)
        if self.step_functions_arn:
            self._create_stepfunctions_error_handler()
        
        # Create CloudWatch Alarms (AWS Best Practice)
        self._create_cloudwatch_alarms()
        
        # Create webhook API
        self._create_webhook_api()

        # Create Campus Coach sync
        self._create_campus_coach_sync()

    def _create_sqs_queues(self) -> None:
        """Create SQS queues for reliable message processing"""
        
        # Dead letter queue for failed messages
        self.dlq = sqs.Queue(
            self, "ActivityProcessingDLQ",
            queue_name="strava-ai-boost-activity-processing-dlq",
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.KMS_MANAGED
        )

        # Main processing queue
        self.processing_queue = sqs.Queue(
            self, "ActivityProcessingQueue",
            queue_name="strava-ai-boost-activity-processing",
            visibility_timeout=Duration.minutes(35),  # Longer than Step Functions timeout
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.KMS_MANAGED,
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=self.dlq
            )
        )

    def _create_lambda_functions(self) -> None:
        """Create Lambda functions for webhook processing"""
        
        # Webhook handler Lambda
        self.webhook_handler = lambda_.Function(
            self, "WebhookHandler",
            function_name="StravaAIBoost-WebhookHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="webhooks.webhook_handler.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(30),
            memory_size=256,
            # Create role locally instead of using core stack role
            environment={
                "PROCESSING_QUEUE_URL": self.processing_queue.queue_url,
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name,
                # Origin filtering for unsigned Strava webhook events. Both are
                # optional: when a value is absent the corresponding check is
                # skipped so ingestion can never break on missing config.
                "STRAVA_SUBSCRIPTION_ID": str(
                    self.node.try_get_context("strava_subscription_id") or ""
                ),
                "DEFAULT_USER_ID": str(self.node.try_get_context("default_user_id") or ""),
                # Kill switch: set to "false" to stop dropping foreign events.
                "WEBHOOK_STRICT_ORIGIN": str(
                    self.node.try_get_context("webhook_strict_origin")
                    if self.node.try_get_context("webhook_strict_origin") is not None
                    else "true"
                )
            }
        )

        # Grant SQS permissions to webhook handler
        self.processing_queue.grant_send_messages(self.webhook_handler)
        
        # Grant DynamoDB permissions to webhook handler
        self.core_stack.activities_table.grant_read_write_data(self.webhook_handler)
        self.core_stack.user_config_table.grant_read_data(self.webhook_handler)
        
        # Grant Secrets Manager permissions to webhook handler
        self.core_stack.strava_oauth_secret.grant_read(self.webhook_handler)
        
        # Activity processor Lambda (triggered by SQS)
        # This Lambda now handles Step Functions failures by NOT deleting the SQS message on SF error
        activity_processor_env = {
            "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
            "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name,
            "PROCESSING_QUEUE_URL": self.processing_queue.queue_url,
            "DLQ_URL": self.dlq.queue_url  # Add DLQ URL for manual error handling
        }
        
        # Add Step Functions ARN if provided
        if self.step_functions_arn:
            activity_processor_env["STEP_FUNCTIONS_ARN"] = self.step_functions_arn
        
        # Add USER_CONFIG_TABLE for Enduraw module configuration
        activity_processor_env["USER_CONFIG_TABLE"] = self.core_stack.table_names["user_config"]
        
        self.activity_processor = lambda_.Function(
            self, "ActivityProcessor",
            function_name="StravaAIBoost-ActivityProcessor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="webhooks.activity_processor.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(300),  # 5 minutes for Strava API calls
            memory_size=512,
            # Create role locally instead of using core stack role
            environment=activity_processor_env,
            # CRITICAL: Set reserved concurrent executions to prevent overwhelming Step Functions
            reserved_concurrent_executions=5
        )

        # Grant SQS permissions to activity processor (including DLQ)
        self.processing_queue.grant_consume_messages(self.activity_processor)
        self.dlq.grant_send_messages(self.activity_processor)
        
        # Grant DynamoDB permissions to activity processor
        self.core_stack.activities_table.grant_read_write_data(self.activity_processor)
        self.core_stack.user_config_table.grant_read_data(self.activity_processor)  # For Enduraw module config
        
        # Grant Secrets Manager permissions to activity processor
        self.core_stack.strava_oauth_secret.grant_read(self.activity_processor)
        
        # Grant Step Functions permissions to activity processor if ARN provided
        if self.step_functions_arn:
            self.activity_processor.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "states:StartExecution",
                        "states:DescribeExecution"  # To check execution status
                    ],
                    resources=[
                        self.step_functions_arn,
                        f"{self.step_functions_arn.rsplit(':', 1)[0]}:*"  # Allow describe on executions
                    ]
                )
            )
        
        # Grant SQS send permissions for DLQ
        self.activity_processor.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["sqs:SendMessage"],
                resources=[
                    self.processing_queue.queue_arn,
                    self.dlq.queue_arn
                ]
            )
        )
        
        # Add SQS event source to activity processor
        self.activity_processor.add_event_source(
            lambda_events.SqsEventSource(
                self.processing_queue,
                batch_size=1,  # Process one activity at a time
                max_batching_window=Duration.seconds(5),
                # CRITICAL: Report batch item failures to prevent deleting failed messages
                # This automatically sets FunctionResponseTypes=ReportBatchItemFailures
                report_batch_item_failures=True,
                # AWS Best Practice: Set max concurrency to prevent overwhelming downstream services
                max_concurrency=5  # Matches reserved_concurrent_executions
            )
        )


    def _create_stepfunctions_error_handler(self) -> None:
        """
        Create Lambda function and EventBridge rule to handle Step Functions failures
        
        This captures Step Functions execution failures and sends them to DLQ
        """
        
        # Create Lambda function for Step Functions error handling
        self.stepfunctions_error_handler = lambda_.Function(
            self, "StepFunctionsErrorHandler",
            function_name="StravaAIBoost-StepFunctionsErrorHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="support.stepfunctions_error_handler.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(60),
            memory_size=256,
            environment={
                "DLQ_URL": self.dlq.queue_url,
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"]
            }
        )
        
        # Grant permissions to send to DLQ
        self.dlq.grant_send_messages(self.stepfunctions_error_handler)
        
        # Grant permissions to update DynamoDB
        self.core_stack.activities_table.grant_read_write_data(self.stepfunctions_error_handler)
        
        # Grant permissions to describe Step Functions executions
        self.stepfunctions_error_handler.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["states:DescribeExecution"],
                resources=[f"{self.step_functions_arn.rsplit(':', 1)[0]}:*"]
            )
        )
        
        # Create EventBridge rule to trigger on Step Functions failures
        failure_rule = events.Rule(
            self, "StepFunctionsFailureRule",
            rule_name="strava-ai-boost-stepfunctions-failures",
            description="Capture Step Functions execution failures and send to DLQ",
            event_pattern=events.EventPattern(
                source=["aws.states"],
                detail_type=["Step Functions Execution Status Change"],
                detail={
                    "status": ["FAILED", "TIMED_OUT", "ABORTED"],
                    "stateMachineArn": [self.step_functions_arn]
                }
            )
        )
        
        # Add Lambda as target for the rule
        failure_rule.add_target(targets.LambdaFunction(self.stepfunctions_error_handler))

    def _create_cloudwatch_alarms(self) -> None:
        """
        Create CloudWatch Alarms for monitoring (AWS Best Practice)

        AWS recommends creating alarms for:
        - DLQ messages (any message indicates a problem)
        - Old messages in queue (processing delays)
        - Lambda errors

        All alarms notify the alerts SNS topic (email subscription).
        """

        # SNS topic for operational alerts (alarms + budget)
        self.alerts_topic = sns.Topic(
            self, "OpsAlertsTopic",
            topic_name="strava-ai-boost-ops-alerts",
            display_name="Strava AI Boost Ops Alerts"
        )
        alert_email = self.node.try_get_context("alert_email")
        if alert_email:
            self.alerts_topic.add_subscription(
                sns_subscriptions.EmailSubscription(alert_email)
            )
        alarm_action = cw_actions.SnsAction(self.alerts_topic)

        # Alarm on DLQ messages (AWS Best Practice)
        # Reference: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html
        dlq_alarm = cloudwatch.Alarm(
            self, "DLQMessagesAlarm",
            alarm_name="strava-ai-boost-dlq-messages",
            alarm_description="Alert when messages appear in the Dead Letter Queue - indicates processing failures",
            metric=self.dlq.metric_approximate_number_of_messages_visible(),
            threshold=1,  # Alert on ANY message in DLQ
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        dlq_alarm.add_alarm_action(alarm_action)

        # Alarm on old messages in processing queue (AWS Best Practice)
        old_messages_alarm = cloudwatch.Alarm(
            self, "OldMessagesAlarm",
            alarm_name="strava-ai-boost-old-messages",
            alarm_description="Alert when messages are stuck in queue for too long",
            metric=self.processing_queue.metric_approximate_age_of_oldest_message(),
            threshold=3600,  # 1 hour
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        old_messages_alarm.add_alarm_action(alarm_action)

        # Alarm on Lambda errors (AWS Best Practice)
        lambda_errors_alarm = cloudwatch.Alarm(
            self, "ActivityProcessorErrorsAlarm",
            alarm_name="strava-ai-boost-lambda-errors",
            alarm_description="Alert when activity processor Lambda has errors",
            metric=self.activity_processor.metric_errors(
                period=Duration.minutes(5)
            ),
            threshold=3,  # Alert after 3 errors in 5 minutes
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        lambda_errors_alarm.add_alarm_action(alarm_action)

        # Monthly cost budget with email notification at 80% actual and 100% forecasted
        if not alert_email:
            return  # Budget notifications require an email; set alert_email in cdk.context.json
        budget_limit = float(self.node.try_get_context("budget_limit_usd") or 35)
        budgets.CfnBudget(
            self, "MonthlyCostBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name="strava-ai-boost-monthly",
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=budget_limit, unit="USD"
                ),
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL",
                        comparison_operator="GREATER_THAN",
                        threshold=80,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[budgets.CfnBudget.SubscriberProperty(
                        subscription_type="EMAIL", address=alert_email
                    )],
                ),
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="FORECASTED",
                        comparison_operator="GREATER_THAN",
                        threshold=100,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[budgets.CfnBudget.SubscriberProperty(
                        subscription_type="EMAIL", address=alert_email
                    )],
                ),
            ],
        )

    def _create_webhook_api(self) -> None:
        """Create API Gateway for Strava webhook endpoints"""
        
        # Create REST API for webhooks
        self.webhook_api = apigateway.RestApi(
            self, "StravaWebhookAPI",
            rest_api_name="Strava AI Boost Webhook API",
            description="API for receiving Strava webhook notifications",
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
            )
        )

        # Create webhook resource
        webhook_resource = self.webhook_api.root.add_resource("webhook")
        
        # Webhook endpoints are intentionally PUBLIC (no API key / IAM auth).
        # Strava requires unauthenticated GET (subscription verification) and POST
        # (event notifications) endpoints. Security is handled at the application
        # level via HMAC-SHA1 signature verification in webhook_handler.py.
        webhook_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.webhook_handler),
            method_responses=[
                apigateway.MethodResponse(status_code="200"),
                apigateway.MethodResponse(status_code="400")
            ]
        )

        webhook_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.webhook_handler),
            method_responses=[
                apigateway.MethodResponse(status_code="200"),
                apigateway.MethodResponse(status_code="400"),
                apigateway.MethodResponse(status_code="500")
            ]
        )

        # Add request validation
        self.webhook_api.add_request_validator(
            "WebhookValidator",
            validate_request_body=True,
            validate_request_parameters=True
        )

    def _create_campus_coach_sync(self) -> None:
        """Create Campus Coach sync Lambda triggered daily"""

        campus_coach_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "CampusCoachSecret",
            "strava-ai-boost-campus-coach-credentials"
        )
        coaching_sessions_table = dynamodb.Table.from_table_name(
            self, "CoachingSessionsTable",
            "strava-ai-boost-campus-coaching-sessions"
        )

        self.campus_coach_sync = lambda_.Function(
            self, "CampusCoachSync",
            function_name="StravaAIBoost-CampusCoachSync",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="webhooks.campus_coach_sync.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(60),
            memory_size=256,
            environment={
                "CAMPUS_COACH_SECRET_ARN": campus_coach_secret.secret_arn,
                "COACHING_SESSIONS_TABLE": "strava-ai-boost-campus-coaching-sessions",
                "USER_CONFIG_TABLE": "strava-ai-boost-user-configuration",
                "DEFAULT_USER_ID": self.node.try_get_context("default_user_id") or "",
            }
        )

        campus_coach_secret.grant_read(self.campus_coach_sync)
        coaching_sessions_table.grant_read_write_data(self.campus_coach_sync)

        # Also need to read user config to check if module is enabled
        user_config_table = dynamodb.Table.from_table_name(
            self, "UserConfigTableRef", "strava-ai-boost-user-configuration"
        )
        user_config_table.grant_read_data(self.campus_coach_sync)

        events.Rule(
            self, "CampusCoachSyncSchedule",
            rule_name="strava-ai-boost-campus-coach-daily-sync",
            schedule=events.Schedule.cron(hour="5", minute="0"),
            targets=[targets.LambdaFunction(self.campus_coach_sync)]
        )

    @property
    def webhook_url(self) -> str:
        """Return the webhook API URL"""
        return f"{self.webhook_api.url}webhook"

    @property
    def queue_arn(self) -> str:
        """Return the processing queue ARN"""
        return self.processing_queue.queue_arn