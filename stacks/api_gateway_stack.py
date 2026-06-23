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

    def _load_coach_arn(self) -> str:
        from .env_loader import load_env_agentcore
        env = load_env_agentcore(keys={"COACH_AGENT_ARN"})
        return env.get("COACH_AGENT_ARN", "")

    def _load_memory_id(self) -> str:
        from .env_loader import load_agentcore_memory_id
        return load_agentcore_memory_id()

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
        
        # Coach Ask API Lambda
        self.coach_ask_lambda = lambda_.Function(
            self, "CoachAskAPI",
            function_name="StravaAIBoost-CoachAskAPI",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="api.coach_ask_api.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            layers=[self.core_stack.dependencies_layer],
            timeout=Duration.seconds(30),
            memory_size=256,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "DEFAULT_USER_ID": self.node.try_get_context("default_user_id") or "",
                "BEDROCK_MODEL_ID": os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
                "COACH_AGENT_ARN": self._load_coach_arn(),
                "BEDROCK_AGENTCORE_MEMORY_ID": self._load_memory_id()
            }
        )

        # Coach Streaming Lambda (Starlette + Lambda Web Adapter) — emits AG-UI SSE.
        # Additive: the buffered /coach/ask handler above remains the fallback.
        # Starlette/uvicorn are pure-Python and vendored into lambda_functions/ by
        # scripts/build_coach_stream_deps.sh (project convention; see README Known
        # Issue #2). No Docker bundling — uses the shared asset like every Lambda.
        coach_stream_code = lambda_.Code.from_asset("lambda_functions")

        # Lambda Web Adapter layer — account/name/version come from cdk.json context
        # (official AWS Labs publisher, pinned version; nothing hardcoded in the stack).
        lwa = self.node.try_get_context("lambda_web_adapter") or {}
        lwa_arn = (
            f"arn:aws:lambda:{Aws.REGION}:{lwa['account']}:"
            f"layer:{lwa['layer_name']}:{lwa['version']}"
        )
        lwa_layer = lambda_.LayerVersion.from_layer_version_arn(
            self, "LambdaWebAdapterLayer", lwa_arn,
        )

        self.coach_stream_lambda = lambda_.Function(
            self, "CoachStreamAPI",
            function_name="StravaAIBoost-CoachStreamAPI",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="coach_stream/run.sh",
            code=coach_stream_code,
            # LWA layer + shared deps layer (powertools, requests used by shared/*).
            layers=[lwa_layer, self.core_stack.dependencies_layer],
            timeout=Duration.seconds(60),
            memory_size=512,
            role=self.core_stack.webhook_lambda_role,
            environment={
                "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bootstrap",
                "AWS_LWA_INVOKE_MODE": "response_stream",
                "PORT": "8000",
                "ACTIVITIES_TABLE": self.core_stack.table_names["activities"],
                "USER_CONFIG_TABLE": self.core_stack.table_names["user_config"],
                "COACHING_SESSIONS_TABLE": self.core_stack.table_names["coaching_sessions"],
                "DEFAULT_USER_ID": self.node.try_get_context("default_user_id") or "",
                "BEDROCK_MODEL_ID": os.environ.get(
                    "BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
                ),
                "BEDROCK_AGENTCORE_MEMORY_ID": self._load_memory_id(),
            },
        )

        # Function URL with RESPONSE_STREAM + AWS_IAM (NEVER NONE — security policy §1).
        # Authz is delegated to IAM; the frontend signs requests with SigV4 using
        # temporary credentials from the Cognito Identity Pool.
        cors_origin = f"https://{self.cloudfront_domain}" if self.cloudfront_domain else "*"
        self.coach_stream_url = self.coach_stream_lambda.add_function_url(
            auth_type=lambda_.FunctionUrlAuthType.AWS_IAM,
            invoke_mode=lambda_.InvokeMode.RESPONSE_STREAM,
            cors=lambda_.FunctionUrlCorsOptions(
                allowed_origins=[cors_origin],
                allowed_methods=[lambda_.HttpMethod.POST],
                allowed_headers=["authorization", "content-type", "x-amz-date",
                                 "x-amz-security-token", "x-amz-content-sha256"],
                max_age=Duration.hours(1),
            ),
        )

        CfnOutput(
            self, "CoachStreamUrl",
            value=self.coach_stream_url.url,
            description="Coach streaming Function URL (SigV4 / AWS_IAM)",
        )

        # Cognito Identity Pool — lets authenticated User Pool users obtain temporary
        # IAM credentials to sign the coach Function URL with SigV4 (security policy:
        # frontend signs requests with SigV4; no public/NONE endpoints).
        if self.user_pool and self.user_pool_client:
            identity_pool = cognito.CfnIdentityPool(
                self, "CoachIdentityPool",
                allow_unauthenticated_identities=False,
                cognito_identity_providers=[
                    cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                        client_id=self.user_pool_client.user_pool_client_id,
                        provider_name=self.user_pool.user_pool_provider_name,
                        server_side_token_check=True,
                    )
                ],
            )

            # Authenticated role: scoped to invoking ONLY the coach Function URL.
            authenticated_role = iam.Role(
                self, "CoachAuthenticatedRole",
                assumed_by=iam.FederatedPrincipal(
                    "cognito-identity.amazonaws.com",
                    conditions={
                        "StringEquals": {
                            "cognito-identity.amazonaws.com:aud": identity_pool.ref
                        },
                        "ForAnyValue:StringLike": {
                            "cognito-identity.amazonaws.com:amr": "authenticated"
                        },
                    },
                    assume_role_action="sts:AssumeRoleWithWebIdentity",
                ),
            )
            # Function URL invocation requires BOTH lambda:InvokeFunctionUrl AND
            # lambda:InvokeFunction (per AWS docs). The condition only applies to
            # InvokeFunctionUrl, so InvokeFunction is granted as a separate statement.
            authenticated_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunctionUrl"],
                    resources=[self.coach_stream_lambda.function_arn],
                    conditions={
                        "StringEquals": {"lambda:FunctionUrlAuthType": "AWS_IAM"}
                    },
                )
            )
            authenticated_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=[self.coach_stream_lambda.function_arn],
                )
            )

            # Function URLs with AWS_IAM auth require a resource-based policy in
            # ADDITION to the caller's identity policy. Without this, the scoped
            # authenticated role gets 403 (only principals with '*' like Admin bypass it).
            self.coach_stream_lambda.add_permission(
                "AllowCognitoAuthenticatedInvokeUrl",
                principal=authenticated_role.grant_principal,
                action="lambda:InvokeFunctionUrl",
                function_url_auth_type=lambda_.FunctionUrlAuthType.AWS_IAM,
            )

            cognito.CfnIdentityPoolRoleAttachment(
                self, "CoachIdentityPoolRoleAttachment",
                identity_pool_id=identity_pool.ref,
                roles={"authenticated": authenticated_role.role_arn},
            )

            CfnOutput(
                self, "CoachIdentityPoolId",
                value=identity_pool.ref,
                description="Cognito Identity Pool ID for SigV4-signed coach streaming",
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
        for arn_key in ['CONTENT_GENERATION_AGENT_ARN', 'CAMPUS_COACH_AGENT_ARN']:
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
            description="REST API for Strava AI Boost (Cognito + API Key auth)",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=allowed_origins,
                allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-API-Key"]
            ),
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
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
            api_key_required=False,
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
            api_key_required=False,
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
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        oauth_resource.add_method(
            "DELETE",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # Module management endpoints
        modules_resource = config_resource.add_resource("modules")
        modules_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        modules_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        
        module_resource = modules_resource.add_resource("{module_id}")
        module_resource.add_method(
            "PUT",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        module_resource.add_method(
            "DELETE",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # Enhancement control endpoints
        enhancement_resource = config_resource.add_resource("enhancement")
        enhancement_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        enhancement_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.config_lambda),
            api_key_required=False,
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
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # Activity history endpoint
        activities_resource = dashboard_resource.add_resource("activities")
        activities_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        
        # System stats endpoint (total activities, success rate, queue depth)
        system_resource = dashboard_resource.add_resource("system")
        system_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # /coach resource for coaching summary
        coach_resource = self.api.root.add_resource("coach")
        coach_summary_resource = coach_resource.add_resource("summary")
        coach_summary_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # /coach/ask endpoint
        coach_ask_resource = coach_resource.add_resource("ask")
        coach_ask_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.coach_ask_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # /coach/recaps endpoint (GET list + POST generate)
        coach_recaps_resource = coach_resource.add_resource("recaps")
        coach_recaps_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        coach_recaps_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.dashboard_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )

        # /preferences resource for user preferences
        preferences_resource = self.api.root.add_resource("preferences")
        preferences_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.preferences_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        preferences_resource.add_method(
            "POST",
            apigateway.LambdaIntegration(self.preferences_lambda),
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
        )
        
        # /health resource for AgentCore health check
        health_resource = self.api.root.add_resource("health")
        agentcore_health_resource = health_resource.add_resource("agentcore")
        agentcore_health_resource.add_method(
            "GET",
            apigateway.LambdaIntegration(self.agentcore_health_lambda),
            api_key_required=False,
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
                api_key_required=False,
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
            api_key_required=False,
            authorizer=self.cognito_authorizer,
            authorization_type=apigateway.AuthorizationType.COGNITO if self.cognito_authorizer else apigateway.AuthorizationType.NONE,
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