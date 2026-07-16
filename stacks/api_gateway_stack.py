"""
API Gateway Stack for Strava AI Boost

This stack creates the REST API endpoints for the local web interface:
- Configuration endpoints for OAuth and module management
- Dashboard endpoints for statistics and monitoring
- Status endpoints for real-time processing updates
"""

import os

from aws_cdk import (
    Aws,
    Stack,
    aws_apigateway as apigateway,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_cognito as cognito,
    Duration,
    CfnOutput
)
from constructs import Construct
from .core_infrastructure_stack import CoreInfrastructureStack


class ApiGatewayStack(Stack):
    """API Gateway stack for local web interface"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        core_stack: CoreInfrastructureStack,
        webhook_stack=None,
        step_functions_arn: str = None,
        user_pool=None,
        user_pool_client=None,
        cloudfront_domain: str = None,
        audio_debrief_lambda: lambda_.IFunction = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.core_stack = core_stack
        self.webhook_stack = webhook_stack
        self.step_functions_arn = step_functions_arn
        self.user_pool = user_pool
        self.user_pool_client = user_pool_client
        self.cloudfront_domain = cloudfront_domain
        self.audio_debrief_lambda = audio_debrief_lambda

        # Create Lambda functions for API endpoints
        self._create_lambda_functions()

        # Create API Gateway
        self._create_api_gateway()

    def _create_lambda_functions(self) -> None:
        """Create Lambda functions for API endpoints"""
        
        # IAM Note: API Lambdas share webhook_lambda_role for simplicity (single-user app).
        # For multi-user production, split into per-Lambda roles with least-privilege.

        # Configuration API Lambda
        self.config_lambda = lambda_.Function(
            self, "ConfigurationAPI",
            function_name="StravaAIBoost-ConfigurationAPI",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="api.configuration_api.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(30),
            memory_size=256,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name,
                "CAMPUS_COACH_SECRET": self.core_stack.campus_coach_secret.secret_name,
                "INTERVALS_ICU_SECRET": self.core_stack.intervals_icu_secret.secret_name,
                "DEFAULT_USER_ID": os.environ.get("DEFAULT_USER_ID", ""),
                "COGNITO_USER_POOL_ID": self.user_pool.user_pool_id if self.user_pool else ""
            }
        )

        # Grant Secrets Manager permissions to config lambda
        self.core_stack.strava_oauth_secret.grant_read(self.config_lambda)
        self.core_stack.campus_coach_secret.grant_read(self.config_lambda)
        self.core_stack.intervals_icu_secret.grant_read(self.config_lambda)
        self.core_stack.intervals_icu_secret.grant_write(self.config_lambda)
        
        # Allow config Lambda to set custom:strava_id on Cognito users
        if self.user_pool:
            self.config_lambda.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["cognito-idp:AdminUpdateUserAttributes"],
                    resources=[self.user_pool.user_pool_arn]
                )
            )

        # Dashboard API Lambda
        self.dashboard_lambda = lambda_.Function(
            self, "DashboardAPI",
            function_name="StravaAIBoost-DashboardAPI",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="api.dashboard_api.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(30),
            memory_size=256,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "COACHING_SESSIONS_TABLE": self.core_stack.table_names["coaching_sessions"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name,
                "DEFAULT_USER_ID": self.node.try_get_context("default_user_id") or "",
                "RECAP_TABLE": "strava-ai-boost-weekly-recaps",
                "AUDIO_DEBRIEF_BUCKET": f"strava-ai-boost-audio-debriefs-{Aws.ACCOUNT_ID}",
            }
        )
        
        # Grant Secrets Manager permissions to dashboard lambda
        self.core_stack.strava_oauth_secret.grant_read(self.dashboard_lambda)

        # Grant DashboardAPI permission to invoke WeeklyAudioRecap Lambda (on-demand recap generation)
        self.dashboard_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[f"arn:aws:lambda:{Aws.REGION}:{Aws.ACCOUNT_ID}:function:StravaAIBoost-WeeklyAudioRecap"],
            )
        )
        # Grant DashboardAPI read access to recaps table and S3 for presigned URLs
        self.dashboard_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:Query", "dynamodb:GetItem"],
                resources=[f"arn:aws:dynamodb:{Aws.REGION}:{Aws.ACCOUNT_ID}:table/strava-ai-boost-weekly-recaps"],
            )
        )
        self.dashboard_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[f"arn:aws:s3:::strava-ai-boost-audio-debriefs-{Aws.ACCOUNT_ID}/recaps/*"],
            )
        )

        # User Preferences API Lambda
        self.preferences_lambda = lambda_.Function(
            self, "UserPreferencesAPI",
            function_name="StravaAIBoost-UserPreferencesAPI",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="api.user_preferences_api.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(10),
            memory_size=128,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "DEFAULT_USER_ID": os.environ.get("DEFAULT_USER_ID", "")
            }
        )
        
        # AgentCore Health Check Lambda
        agentcore_env = {
        }
        
        # Load AgentCore agent ARNs from .env.agentcore if available
        from .env_loader import load_agentcore_agent_arns
        agentcore_env.update(load_agentcore_agent_arns())
        
        self.agentcore_health_lambda = lambda_.Function(
            self, "AgentCoreHealthCheck",
            function_name="StravaAIBoost-AgentCoreHealthCheck",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="api.agentcore_health_check.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(10),
            memory_size=128,
            role=self.core_stack.webhook_lambda_role,
            environment=agentcore_env
        )
        
        # Grant AgentCore permissions - scoped to agent runtime ARNs
        agentcore_resources = []
        for arn_key in ['CONTENT_GENERATION_AGENT_ARN']:
            if arn_key in agentcore_env:
                agentcore_resources.append(agentcore_env[arn_key])
        if not agentcore_resources:
            agentcore_resources = [
                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:runtime/*"
            ]
        self.agentcore_health_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:GetAgentRuntime"
                ],
                resources=agentcore_resources
            )
        )

    def _create_api_gateway(self) -> None:
        """Create API Gateway with Cognito authentication"""
        
        # Build allowed origins
        allowed_origins = [
            "http://localhost:3000", "http://127.0.0.1:3000",
            "http://localhost:5173", "http://127.0.0.1:5173",
        ]
        if self.cloudfront_domain:
            allowed_origins.append(f"https://{self.cloudfront_domain}")

        # Create REST API
        self.api = apigateway.RestApi(
            self, "StravaAIBoostAPI",
            rest_api_name="Strava AI Boost Local Interface API",
            description="REST API for Strava AI Boost (Cognito auth)",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=allowed_origins,
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization", "X-Requested-With"]
            ),
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
            ),
            deploy_options=apigateway.StageOptions(
                throttling_rate_limit=100,
                throttling_burst_limit=200,
            )
        )

        # Cognito Authorizer (primary auth for frontend)
        self.cognito_authorizer = None
        if self.user_pool:
            self.cognito_authorizer = apigateway.CognitoUserPoolsAuthorizer(
                self, "CognitoAuthorizer",
                cognito_user_pools=[self.user_pool],
                authorizer_name="StravaAIBoost-CognitoAuth",
            )
        
        # Create API resources and methods (Cognito-authorized)

        # /config resource for configuration management
        config_resource = self.api.root.add_resource("config")
        
        # Strava app config endpoint (check if configured)
        strava_resource = config_resource.add_resource("strava")
        strava_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.config_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
            method_responses=[
                apigateway.MethodResponse(status_code="200"),
                apigateway.MethodResponse(status_code="500")
            ]
        )
        
        # OAuth endpoints
        oauth_resource = config_resource.add_resource("oauth")
        oauth_resource.add_method(
            "GET", 
            apigateway.LambdaIntegration(self.config_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
            method_responses=[
                apigateway.MethodResponse(status_code="200"),
                apigateway.MethodResponse(status_code="400"),
                apigateway.MethodResponse(status_code="401"),
                apigateway.MethodResponse(status_code="403"),
                apigateway.MethodResponse(status_code="500")
            ]
        )
        oauth_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.config_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        oauth_resource.add_method(
            "DELETE",
            apigateway.LambdaIntegration(self.config_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # Module management endpoints
        modules_resource = config_resource.add_resource("modules")
        modules_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.config_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        modules_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.config_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        
        module_resource = modules_resource.add_resource("{module_id}")
        module_resource.add_method(
            "PUT",
            apigateway.LambdaIntegration(self.config_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        module_resource.add_method(
            "DELETE",
            apigateway.LambdaIntegration(self.config_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # Enhancement control endpoints
        enhancement_resource = config_resource.add_resource("enhancement")
        enhancement_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.config_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        enhancement_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.config_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # /dashboard resource for statistics and monitoring
        dashboard_resource = self.api.root.add_resource("dashboard")
        
        # Statistics endpoint
        stats_resource = dashboard_resource.add_resource("stats")
        stats_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # Activity history endpoint
        activities_resource = dashboard_resource.add_resource("activities")
        activities_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        
        # System stats endpoint (total activities, success rate, queue depth)
        system_resource = dashboard_resource.add_resource("system")
        system_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # /coach resource for coaching summary
        coach_resource = self.api.root.add_resource("coach")
        coach_summary_resource = coach_resource.add_resource("summary")
        coach_summary_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # /coach/recaps endpoint (GET list + POST generate)
        coach_recaps_resource = coach_resource.add_resource("recaps")
        coach_recaps_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        coach_recaps_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # /preferences resource for user preferences
        preferences_resource = self.api.root.add_resource("preferences")
        preferences_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.preferences_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        preferences_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.preferences_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        
        # /health resource for AgentCore health check
        health_resource = self.api.root.add_resource("health")
        agentcore_health_resource = health_resource.add_resource("agentcore")
        agentcore_health_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.agentcore_health_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        
        # /activities/{activityId}/audio-url — presigned URL for voice debrief MP3
        if self.audio_debrief_lambda is not None:
            activities_root = self.api.root.add_resource("activities")
            activity_item = activities_root.add_resource("{activityId}")
            audio_url_resource = activity_item.add_resource("audio-url")
            audio_url_resource.add_method(
                "GET",
                apigateway.LambdaIntegration(self.audio_debrief_lambda),
                authorizer=self.cognito_authorizer,
                authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
                method_responses=[
                    apigateway.MethodResponse(status_code="200"),
                    apigateway.MethodResponse(status_code="400"),
                    apigateway.MethodResponse(status_code="403"),
                    apigateway.MethodResponse(status_code="404"),
                    apigateway.MethodResponse(status_code="500"),
                ],
            )

        # /test resource for connection testing
        test_resource = self.api.root.add_resource("test")
        strava_connection_resource = test_resource.add_resource("strava-connection")
        strava_connection_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.config_lambda),
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        
        # Add request validation
        self.api.add_request_validator(
            "RequestValidator",
            validate_request_body=True,
            validate_request_parameters=True
        )

    @property
    def api_url(self) -> str:
        """Return the API Gateway URL"""
        return self.api.url