"""
Monitoring Stack for Strava AI Boost

This stack creates monitoring and observability infrastructure:
- CloudWatch alarms for system health monitoring
- Dashboards for performance metrics
- X-Ray tracing for distributed debugging
"""

from aws_cdk import (
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_logs as logs,
    Duration
)
from constructs import Construct
from .core_infrastructure_stack import CoreInfrastructureStack
from .webhook_processing_stack import WebhookProcessingStack
from .content_generation_stack import ContentGenerationStack


class MonitoringStack(Stack):
    """Monitoring and observability stack"""

    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        core_stack: CoreInfrastructureStack,
        webhook_stack: WebhookProcessingStack,
        content_stack: ContentGenerationStack,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.core_stack = core_stack
        self.webhook_stack = webhook_stack
        self.content_stack = content_stack
        
        # Create SNS topic for alerts
        self._create_sns_topic()
        
        # Create CloudWatch alarms
        self._create_alarms()
        
        # Create CloudWatch dashboard
        self._create_dashboard()

    def _create_sns_topic(self) -> None:
        """Create SNS topic for alarm notifications"""
        
        self.alarm_topic = sns.Topic(
            self, "StravaAIBoostAlarms",
            topic_name="strava-ai-boost-alarms",
            display_name="Strava AI Boost System Alarms"
        )

    def _create_alarms(self) -> None:
        """Create CloudWatch alarms for system monitoring"""
        
        # Lambda function error rate alarms
        lambda_functions = [
            ("WebhookHandler", self.webhook_stack.webhook_handler.function_name),
            ("ActivityProcessor", self.webhook_stack.activity_processor.function_name),
            ("ContentGenerator", self.content_stack.content_generator.function_name),
            ("ActivityFetcher", self.content_stack.activity_fetcher.function_name),
            ("StravaUpdater", self.content_stack.strava_updater.function_name)
        ]

        for name, function_name in lambda_functions:
            # Error rate alarm
            error_alarm = cloudwatch.Alarm(
                self, f"{name}ErrorAlarm",
                alarm_name=f"StravaAIBoost-{name}-ErrorRate",
                alarm_description=f"High error rate for {name} Lambda function",
                metric=cloudwatch.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Errors",
                    dimensions_map={"FunctionName": function_name},
                    statistic="Sum",
                    period=Duration.minutes(5)
                ),
                threshold=5,
                evaluation_periods=2,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD
            )
            error_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

            # Duration alarm for performance monitoring
            duration_alarm = cloudwatch.Alarm(
                self, f"{name}DurationAlarm",
                alarm_name=f"StravaAIBoost-{name}-Duration",
                alarm_description=f"High duration for {name} Lambda function",
                metric=cloudwatch.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Duration",
                    dimensions_map={"FunctionName": function_name},
                    statistic="Average",
                    period=Duration.minutes(5)
                ),
                threshold=30000,  # 30 seconds
                evaluation_periods=3,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
            )
            duration_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

        # Step Functions execution failure alarm
        step_functions_alarm = cloudwatch.Alarm(
            self, "StepFunctionsFailureAlarm",
            alarm_name="StravaAIBoost-StepFunctions-Failures",
            alarm_description="Step Functions workflow failures",
            metric=cloudwatch.Metric(
                namespace="AWS/States",
                metric_name="ExecutionsFailed",
                dimensions_map={"StateMachineArn": self.content_stack.state_machine_arn},
                statistic="Sum",
                period=Duration.minutes(5)
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD
        )
        step_functions_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

        # SQS DLQ message alarm
        dlq_alarm = cloudwatch.Alarm(
            self, "SQSDLQAlarm",
            alarm_name="StravaAIBoost-SQS-DLQ-Messages",
            alarm_description="Messages in SQS dead letter queue",
            metric=cloudwatch.Metric(
                namespace="AWS/SQS",
                metric_name="ApproximateNumberOfVisibleMessages",
                dimensions_map={"QueueName": self.webhook_stack.dlq.queue_name},
                statistic="Maximum",
                period=Duration.minutes(5)
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD
        )
        dlq_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

        # DynamoDB throttling alarm
        dynamodb_tables = [
            ("Activities", self.core_stack.table_names["activities"]),
            ("UserConfig", self.core_stack.table_names["user_config"]),
            ("CoachingSessions", self.core_stack.table_names["coaching_sessions"])
        ]

        for name, table_name in dynamodb_tables:
            throttle_alarm = cloudwatch.Alarm(
                self, f"DynamoDB{name}ThrottleAlarm",
                alarm_name=f"StravaAIBoost-DynamoDB-{name}-Throttles",
                alarm_description=f"DynamoDB throttling for {name} table",
                metric=cloudwatch.Metric(
                    namespace="AWS/DynamoDB",
                    metric_name="ThrottledRequests",
                    dimensions_map={"TableName": table_name},
                    statistic="Sum",
                    period=Duration.minutes(5)
                ),
                threshold=1,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD
            )
            throttle_alarm.add_alarm_action(cw_actions.SnsAction(self.alarm_topic))

    def _create_dashboard(self) -> None:
        """Create CloudWatch dashboard for system monitoring"""
        
        self.dashboard = cloudwatch.Dashboard(
            self, "StravaAIBoostDashboard",
            dashboard_name="Strava-AI-Boost-System-Metrics"
        )

        # Lambda metrics widget
        lambda_widget = cloudwatch.GraphWidget(
            title="Lambda Function Metrics",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Invocations",
                    dimensions_map={"FunctionName": self.webhook_stack.webhook_handler.function_name},
                    statistic="Sum",
                    label="Webhook Handler Invocations"
                ),
                cloudwatch.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Invocations",
                    dimensions_map={"FunctionName": self.content_stack.content_generator.function_name},
                    statistic="Sum",
                    label="Content Generator Invocations"
                )
            ],
            right=[
                cloudwatch.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Errors",
                    dimensions_map={"FunctionName": self.webhook_stack.webhook_handler.function_name},
                    statistic="Sum",
                    label="Webhook Handler Errors"
                ),
                cloudwatch.Metric(
                    namespace="AWS/Lambda",
                    metric_name="Errors",
                    dimensions_map={"FunctionName": self.content_stack.content_generator.function_name},
                    statistic="Sum",
                    label="Content Generator Errors"
                )
            ]
        )

        # Step Functions metrics widget
        step_functions_widget = cloudwatch.GraphWidget(
            title="Step Functions Workflow Metrics",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/States",
                    metric_name="ExecutionsStarted",
                    dimensions_map={"StateMachineArn": self.content_stack.state_machine_arn},
                    statistic="Sum",
                    label="Executions Started"
                ),
                cloudwatch.Metric(
                    namespace="AWS/States",
                    metric_name="ExecutionsSucceeded",
                    dimensions_map={"StateMachineArn": self.content_stack.state_machine_arn},
                    statistic="Sum",
                    label="Executions Succeeded"
                )
            ],
            right=[
                cloudwatch.Metric(
                    namespace="AWS/States",
                    metric_name="ExecutionsFailed",
                    dimensions_map={"StateMachineArn": self.content_stack.state_machine_arn},
                    statistic="Sum",
                    label="Executions Failed"
                ),
                cloudwatch.Metric(
                    namespace="AWS/States",
                    metric_name="ExecutionTime",
                    dimensions_map={"StateMachineArn": self.content_stack.state_machine_arn},
                    statistic="Average",
                    label="Average Execution Time"
                )
            ]
        )

        # SQS metrics widget
        sqs_widget = cloudwatch.GraphWidget(
            title="SQS Queue Metrics",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="NumberOfMessagesSent",
                    dimensions_map={"QueueName": self.webhook_stack.processing_queue.queue_name},
                    statistic="Sum",
                    label="Messages Sent"
                ),
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="NumberOfMessagesReceived",
                    dimensions_map={"QueueName": self.webhook_stack.processing_queue.queue_name},
                    statistic="Sum",
                    label="Messages Received"
                )
            ],
            right=[
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateNumberOfVisibleMessages",
                    dimensions_map={"QueueName": self.webhook_stack.processing_queue.queue_name},
                    statistic="Average",
                    label="Queue Depth"
                ),
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateNumberOfVisibleMessages",
                    dimensions_map={"QueueName": self.webhook_stack.dlq.queue_name},
                    statistic="Average",
                    label="DLQ Depth"
                )
            ]
        )

        # DynamoDB metrics widget
        dynamodb_widget = cloudwatch.GraphWidget(
            title="DynamoDB Table Metrics",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/DynamoDB",
                    metric_name="ConsumedReadCapacityUnits",
                    dimensions_map={"TableName": self.core_stack.table_names["activities"]},
                    statistic="Sum",
                    label="Activities Read Capacity"
                ),
                cloudwatch.Metric(
                    namespace="AWS/DynamoDB",
                    metric_name="ConsumedWriteCapacityUnits",
                    dimensions_map={"TableName": self.core_stack.table_names["activities"]},
                    statistic="Sum",
                    label="Activities Write Capacity"
                )
            ],
            right=[
                cloudwatch.Metric(
                    namespace="AWS/DynamoDB",
                    metric_name="ThrottledRequests",
                    dimensions_map={"TableName": self.core_stack.table_names["activities"]},
                    statistic="Sum",
                    label="Activities Throttles"
                ),

            ]
        )

        # Business metrics widget (custom metrics from Lambda Powertools)
        business_widget = cloudwatch.GraphWidget(
            title="Business Metrics",
            left=[
                cloudwatch.Metric(
                    namespace="StravaAIBoost",
                    metric_name="ActivitiesProcessed",
                    statistic="Sum",
                    label="Activities Processed"
                ),
                cloudwatch.Metric(
                    namespace="StravaAIBoost",
                    metric_name="FeedbackAnalyzed",
                    statistic="Sum",
                    label="Feedback Analyzed"
                ),
            ],
            right=[
                cloudwatch.Metric(
                    namespace="StravaAIBoost",
                    metric_name="ActivitiesProcessFailed",
                    statistic="Sum",
                    label="Processing Failures"
                ),
                cloudwatch.Metric(
                    namespace="StravaAIBoost",
                    metric_name="FeedbackModified",
                    statistic="Sum",
                    label="User Modifications"
                ),
            ]
        )

        # Add widgets to dashboard
        self.dashboard.add_widgets(
            lambda_widget,
            step_functions_widget,
            sqs_widget,
            dynamodb_widget,
            business_widget
        )