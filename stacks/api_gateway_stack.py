"""
API Gateway Stack for Strava AI Boost

This stack creates the REST API endpoints for the local web interface:
- Configuration endpoints for OAuth and module management
- Dashboard endpoints for statistics and monitoring
- Status endpoints for real-time processing updates
"""

from aws_cdk import (
    Stack,
    aws_apigateway as apigateway,
    aws_lambda as lambda_,
    aws_iam as iam,
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
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.core_stack = core_stack
        self.webhook_stack = webhook_stack
        self.step_functions_arn = step_functions_arn
        
        # Create Lambda functions for API endpoints
        self._create_lambda_functions()
        
        # Create API Gateway
        self._create_api_gateway()

    def _create_lambda_functions(self) -> None:
        """Create Lambda functions for API endpoints"""
        
        # Configuration API Lambda
        self.config_lambda = lambda_.Function(
            self, "ConfigurationAPI",
            function_name="StravaAIBoost-ConfigurationAPI",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="configuration_api.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(30),
            memory_size=256,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name,
                "CAMPUS_COACH_SECRET": self.core_stack.campus_coach_secret.secret_name
            }
        )
        
        # Grant Secrets Manager permissions to config lambda
        self.core_stack.strava_oauth_secret.grant_read(self.config_lambda)
        self.core_stack.campus_coach_secret.grant_read(self.config_lambda)
        
        # Grant EventBridge permissions to config lambda (for enabling/disabling Campus Coach scheduler)
        self.config_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "events:EnableRule",
                    "events:DisableRule",
                    "events:DescribeRule"
                ],
                resources=[
                    f"arn:aws:events:{self.region}:{self.account}:rule/StravaAIBoost-CampusCoach-DailyExtraction"
                ]
            )
        )

        # Dashboard API Lambda
        self.dashboard_lambda = lambda_.Function(
            self, "DashboardAPI",
            function_name="StravaAIBoost-DashboardAPI",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="dashboard_api.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(30),
            memory_size=256,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "COACHING_SESSIONS_TABLE": self.core_stack.table_names["coaching_sessions"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name
            }
        )
        
        # Grant Secrets Manager permissions to dashboard lambda
        self.core_stack.strava_oauth_secret.grant_read(self.dashboard_lambda)

        # User Preferences API Lambda
        self.preferences_lambda = lambda_.Function(
            self, "UserPreferencesAPI",
            function_name="StravaAIBoost-UserPreferencesAPI",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="user_preferences_api.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(10),
            memory_size=128,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "DEFAULT_USER_ID": "YOUR_USER_ID"
            }
        )
        
        # AgentCore Health Check Lambda
        agentcore_env = {
        }
        
        # Load AgentCore agent ARNs from .env.agentcore if available
        import os as env_os
        env_file = env_os.path.join(env_os.path.dirname(__file__), '..', '.env.agentcore')
        if env_os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        if key in ['CONTENT_GENERATION_AGENT_ARN', 'CAMPUS_COACH_AGENT_ARN']:
                            agentcore_env[key] = value
        
        self.agentcore_health_lambda = lambda_.Function(
            self, "AgentCoreHealthCheck",
            function_name="StravaAIBoost-AgentCoreHealthCheck",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="agentcore_health_check.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(10),
            memory_size=128,
            role=self.core_stack.webhook_lambda_role,
            environment=agentcore_env
        )
        
        # Grant AgentCore permissions
        self.agentcore_health_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:GetAgentRuntime"
                ],
                resources=["*"]  # Will be restricted to specific agent ARNs in production
            )
        )

    def _create_api_gateway(self) -> None:
        """Create API Gateway with API Key authentication for local development"""
        
        # Create REST API
        self.api = apigateway.RestApi(
            self, "StravaAIBoostAPI",
            rest_api_name="Strava AI Boost Local Interface API",
            description="REST API for Strava AI Boost local web interface (API Key required)",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-API-Key"]
            ),
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
            )
        )
        
        # Create API Key for authentication
        self.api_key = self.api.add_api_key(
            "StravaAIBoostAPIKey",
            api_key_name="strava-ai-boost-local-interface-key",
            description="API Key for Strava AI Boost local web interface"
        )
        
        # Create Usage Plan
        self.usage_plan = self.api.add_usage_plan(
            "StravaAIBoostUsagePlan",
            name="Strava AI Boost Local Interface Usage Plan",
            description="Usage plan for local web interface with rate limiting",
            throttle=apigateway.ThrottleSettings(
                rate_limit=100,  # 100 requests per second
                burst_limit=200  # 200 concurrent requests
            ),
            quota=apigateway.QuotaSettings(
                limit=10000,  # 10,000 requests per day
                period=apigateway.Period.DAY
            )
        )
        
        # Associate API Key with Usage Plan
        self.usage_plan.add_api_key(self.api_key)

        # Create API resources and methods with API Key requirement
        
        # /config resource for configuration management
        config_resource = self.api.root.add_resource("config")
        
        # Strava app config endpoint (check if configured)
        strava_resource = config_resource.add_resource("strava")
        strava_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=True,
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
            api_key_required=True,
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
            api_key_required=True
        )
        oauth_resource.add_method(
            "DELETE",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=True
        )

        # Module management endpoints
        modules_resource = config_resource.add_resource("modules")
        modules_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=True
        )
        modules_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=True
        )
        
        module_resource = modules_resource.add_resource("{module_id}")
        module_resource.add_method(
            "PUT",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=True
        )
        module_resource.add_method(
            "DELETE",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=True
        )

        # Enhancement control endpoints
        enhancement_resource = config_resource.add_resource("enhancement")
        enhancement_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=True
        )
        enhancement_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=True
        )

        # /dashboard resource for statistics and monitoring
        dashboard_resource = self.api.root.add_resource("dashboard")
        
        # Statistics endpoint
        stats_resource = dashboard_resource.add_resource("stats")
        stats_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            api_key_required=True
        )

        # Activity history endpoint
        activities_resource = dashboard_resource.add_resource("activities")
        activities_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            api_key_required=True
        )
        
        # System stats endpoint (total activities, success rate, queue depth)
        system_resource = dashboard_resource.add_resource("system")
        system_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            api_key_required=True
        )

        # /preferences resource for user preferences
        preferences_resource = self.api.root.add_resource("preferences")
        preferences_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.preferences_lambda),
            api_key_required=True
        )
        preferences_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.preferences_lambda),
            api_key_required=True
        )
        
        # /health resource for AgentCore health check
        health_resource = self.api.root.add_resource("health")
        agentcore_health_resource = health_resource.add_resource("agentcore")
        agentcore_health_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.agentcore_health_lambda),
            api_key_required=True
        )
        
        # /test resource for connection testing
        test_resource = self.api.root.add_resource("test")
        strava_connection_resource = test_resource.add_resource("strava-connection")
        strava_connection_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=True
        )
        
        # Associate Usage Plan with API Stage
        self.usage_plan.add_api_stage(
            stage=self.api.deployment_stage
        )

        # Add request validation
        self.api.add_request_validator(
            "RequestValidator",
            validate_request_body=True,
            validate_request_parameters=True
        )
        
        # Output API Key value (will be shown in CloudFormation outputs)
        CfnOutput(
            self, "APIKeyValue",
            value=self.api_key.key_id,
            description="API Key ID for Strava AI Boost local interface (retrieve value with: aws apigateway get-api-key --api-key <key-id> --include-value)"
        )

    @property
    def api_url(self) -> str:
        """Return the API Gateway URL"""
        return self.api.url