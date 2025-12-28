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
        
        # Create webhook API
        self._create_webhook_api()

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
            handler="webhook_handler.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(30),
            memory_size=256,
            # Create role locally instead of using core stack role
            environment={
                "PROCESSING_QUEUE_URL": self.processing_queue.queue_url,
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "RATE_LIMITS_TABLE": self.core_stack.table_names["rate_limits"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name
            }
        )

        # Grant SQS permissions to webhook handler
        self.processing_queue.grant_send_messages(self.webhook_handler)
        
        # Grant DynamoDB permissions to webhook handler
        self.core_stack.activities_table.grant_read_write_data(self.webhook_handler)
        self.core_stack.rate_limits_table.grant_read_write_data(self.webhook_handler)
        self.core_stack.user_config_table.grant_read_data(self.webhook_handler)
        
        # Grant Secrets Manager permissions to webhook handler
        self.core_stack.strava_oauth_secret.grant_read(self.webhook_handler)
        
        # Activity processor Lambda (triggered by SQS)
        activity_processor_env = {
            "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
            "RATE_LIMITS_TABLE": self.core_stack.table_names["rate_limits"],
            "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name
        }
        
        # Add Step Functions ARN if provided
        if self.step_functions_arn:
            activity_processor_env["STEP_FUNCTIONS_ARN"] = self.step_functions_arn
        
        self.activity_processor = lambda_.Function(
            self, "ActivityProcessor",
            function_name="StravaAIBoost-ActivityProcessor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="activity_processor.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(300),  # 5 minutes for Strava API calls
            memory_size=512,
            # Create role locally instead of using core stack role
            environment=activity_processor_env
        )

        # Grant SQS permissions to activity processor
        self.processing_queue.grant_consume_messages(self.activity_processor)
        
        # Grant DynamoDB permissions to activity processor
        self.core_stack.activities_table.grant_read_write_data(self.activity_processor)
        self.core_stack.rate_limits_table.grant_read_write_data(self.activity_processor)
        
        # Grant Secrets Manager permissions to activity processor
        self.core_stack.strava_oauth_secret.grant_read(self.activity_processor)
        
        # Grant Step Functions permissions to activity processor if ARN provided
        if self.step_functions_arn:
            self.activity_processor.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["states:StartExecution"],
                    resources=[self.step_functions_arn]
                )
            )
        
        # Add SQS event source to activity processor
        self.activity_processor.add_event_source(
            lambda_events.SqsEventSource(
                self.processing_queue,
                batch_size=1,  # Process one activity at a time
                max_batching_window=Duration.seconds(5)
            )
        )

        # Rate limiter Lambda for Strava API management
        self.rate_limiter = lambda_.Function(
            self, "RateLimiter",
            function_name="StravaAIBoost-RateLimiter",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="rate_limiter.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(60),
            memory_size=128,
            # Create role locally instead of using core stack role
            environment={
                "RATE_LIMITS_TABLE": self.core_stack.table_names["rate_limits"]
            }
        )
        
        # Grant DynamoDB permissions to rate limiter
        self.core_stack.rate_limits_table.grant_read_write_data(self.rate_limiter)

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
        
        # Add GET method for webhook verification (Strava requirement)
        webhook_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.webhook_handler),
            method_responses=[
                apigateway.MethodResponse(status_code="200"),
                apigateway.MethodResponse(status_code="400")
            ]
        )
        
        # Add POST method for webhook notifications
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

    @property
    def webhook_url(self) -> str:
        """Return the webhook API URL"""
        return f"{self.webhook_api.url}webhook"

    @property
    def queue_arn(self) -> str:
        """Return the processing queue ARN"""
        return self.processing_queue.queue_arn