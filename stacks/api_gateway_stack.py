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
    Duration
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
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.core_stack = core_stack
        
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
            timeout=Duration.seconds(30),
            memory_size=256,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "RATE_LIMITS_TABLE": self.core_stack.table_names["rate_limits"],
                "STRAVA_OAUTH_SECRET": self.core_stack.strava_oauth_secret.secret_name,
                "CAMPUS_COACH_SECRET": self.core_stack.campus_coach_secret.secret_name
            }
        )

        # Dashboard API Lambda
        self.dashboard_lambda = lambda_.Function(
            self, "DashboardAPI",
            function_name="StravaAIBoost-DashboardAPI",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="dashboard_api.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            timeout=Duration.seconds(30),
            memory_size=256,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "COACHING_SESSIONS_TABLE": self.core_stack.table_names["coaching_sessions"]
            }
        )

        # Status API Lambda
        self.status_lambda = lambda_.Function(
            self, "StatusAPI",
            function_name="StravaAIBoost-StatusAPI",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="status_api.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            timeout=Duration.seconds(15),
            memory_size=128,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"]
            }
        )

    def _create_api_gateway(self) -> None:
        """Create API Gateway with CORS for local development"""
        
        # Create REST API
        self.api = apigateway.RestApi(
            self, "StravaAIBoostAPI",
            rest_api_name="Strava AI Boost Local Interface API",
            description="REST API for Strava AI Boost local web interface",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization", "X-Requested-With"]
            ),
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
            )
        )

        # Create API resources and methods
        
        # /config resource for configuration management
        config_resource = self.api.root.add_resource("config")
        
        # OAuth endpoints
        oauth_resource = config_resource.add_resource("oauth")
        oauth_resource.add_method(
            "GET", 
            apigateway.LambdaIntegration(self.config_lambda),
            method_responses=[
                apigateway.MethodResponse(status_code="200"),
                apigateway.MethodResponse(status_code="400"),
                apigateway.MethodResponse(status_code="500")
            ]
        )
        oauth_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.config_lambda)
        )

        # Module management endpoints
        modules_resource = config_resource.add_resource("modules")
        modules_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.config_lambda)
        )
        modules_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.config_lambda)
        )
        
        module_resource = modules_resource.add_resource("{module_id}")
        module_resource.add_method(
            "PUT",
            apigateway.LambdaIntegration(self.config_lambda)
        )
        module_resource.add_method(
            "DELETE",
            apigateway.LambdaIntegration(self.config_lambda)
        )

        # Enhancement control endpoints
        enhancement_resource = config_resource.add_resource("enhancement")
        enhancement_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.config_lambda)
        )
        enhancement_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.config_lambda)
        )

        # /dashboard resource for statistics and monitoring
        dashboard_resource = self.api.root.add_resource("dashboard")
        
        # Statistics endpoint
        stats_resource = dashboard_resource.add_resource("stats")
        stats_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda)
        )

        # Activity history endpoint
        activities_resource = dashboard_resource.add_resource("activities")
        activities_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda)
        )

        # /status resource for real-time processing status
        status_resource = self.api.root.add_resource("status")
        status_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.status_lambda)
        )
        
        # Processing status for specific activity
        activity_status_resource = status_resource.add_resource("{activity_id}")
        activity_status_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.status_lambda)
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