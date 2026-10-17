"""
Tests for CDK infrastructure

Tests the CDK stacks and infrastructure configuration:
- Core infrastructure (DynamoDB, IAM, Secrets Manager)
- Content generation stack (Lambda, Step Functions)
- Webhook processing stack (SQS, Lambda, API Gateway)
- API Gateway stack (REST API, endpoints)
- Security and compliance
"""

import pytest
import json
import aws_cdk as cdk
from aws_cdk import assertions
import sys
import os

# Add stacks to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from stacks.core_infrastructure_stack import CoreInfrastructureStack
from stacks.content_generation_stack import ContentGenerationStack
from stacks.webhook_processing_stack import WebhookProcessingStack
from stacks.api_gateway_stack import ApiGatewayStack


class TestCoreInfrastructureStack:
    """Test core infrastructure stack"""
    
    @pytest.fixture
    def core_stack(self):
        """Create core infrastructure stack for testing"""
        app = cdk.App()
        stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        return stack
    
    def test_dynamodb_tables_created(self, core_stack):
        """Test that all required DynamoDB tables are created"""
        template = assertions.Template.from_stack(core_stack)

        # 4 tables (activities, user-config, coaching-sessions, wellness)
        template.resource_count_is("AWS::DynamoDB::Table", 4)

        # Verify encryption is enabled
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "SSESpecification": {
                "SSEEnabled": True
            }
        })

    def test_wellness_table_retained_pitr_no_ttl_no_stream(self, core_stack):
        """A1: wellness table is RETAIN + PITR, PK user_id/SK sk, no TTL, no stream."""
        template = assertions.Template.from_stack(core_stack)

        # RETAIN removal policy -> DeletionPolicy/UpdateReplacePolicy = Retain.
        template.has_resource("AWS::DynamoDB::Table", {
            "DeletionPolicy": "Retain",
            "UpdateReplacePolicy": "Retain",
            "Properties": assertions.Match.object_like({
                "TableName": "strava-ai-boost-wellness",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "sk", "KeyType": "RANGE"},
                ],
                "PointInTimeRecoverySpecification": {
                    "PointInTimeRecoveryEnabled": True
                },
                # No stream and no TTL on this table.
                "StreamSpecification": assertions.Match.absent(),
                "TimeToLiveSpecification": assertions.Match.absent(),
            }),
        })

    def test_wellness_table_name_exported(self, core_stack):
        # table_name is a CDK token until synth; assert the key is wired through
        # both maps and that the physical name lands in the synthesized template.
        assert "wellness" in core_stack.table_names
        assert "wellness" in core_stack.table_arns
        template = assertions.Template.from_stack(core_stack)
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": "strava-ai-boost-wellness",
        })
    
    def test_dynamodb_table_names(self, core_stack):
        """Test DynamoDB table naming convention"""
        assert "activities" in core_stack.table_names
        assert "user_config" in core_stack.table_names
        assert "coaching_sessions" in core_stack.table_names
    
    def test_secrets_manager_secrets(self, core_stack):
        """Test Secrets Manager secrets are created"""
        template = assertions.Template.from_stack(core_stack)
        
        # 4 secrets: Strava OAuth tokens, Strava app config, Campus Coach and
        # Intervals.icu credentials
        template.resource_count_is("AWS::SecretsManager::Secret", 4)
        for name in (
            "strava-ai-boost-oauth-tokens",
            "strava-ai-boost-app-config",
            "strava-ai-boost-campus-coach-credentials",
            "strava-ai-boost-intervals-icu-credentials",
        ):
            template.has_resource_properties(
                "AWS::SecretsManager::Secret", {"Name": name}
            )
    
    def test_lambda_layer_created(self, core_stack):
        """Test Lambda Layer is created"""
        template = assertions.Template.from_stack(core_stack)
        
        template.resource_count_is("AWS::Lambda::LayerVersion", 1)
    
    def test_iam_roles_created(self, core_stack):
        """Test IAM roles are created with proper permissions"""
        template = assertions.Template.from_stack(core_stack)
        
        # Should have at least 2 IAM roles (webhook and content)
        roles = template.find_resources("AWS::IAM::Role")
        assert len(roles) >= 2, "Should have at least 2 IAM roles"


class TestContentGenerationStack:
    """Test content generation stack"""
    
    @pytest.fixture
    def content_stack(self):
        """Create content generation stack for testing"""
        app = cdk.App()
        core_stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        stack = ContentGenerationStack(
            app,
            "TestContentStack",
            core_stack=core_stack,
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        return stack
    
    def test_lambda_functions_created(self, content_stack):
        """Test that all Lambda functions are created"""
        template = assertions.Template.from_stack(content_stack)
        
        # 5 Lambda functions: fetcher, content, coach, assembly, Strava updater
        template.resource_count_is("AWS::Lambda::Function", 5)
        for name in (
            "StravaAIBoost-ActivityFetcher",
            "StravaAIBoost-ContentGenerator",
            "StravaAIBoost-CoachGenerator",
            "StravaAIBoost-Assembly",
            "StravaAIBoost-StravaUpdater",
        ):
            template.has_resource_properties(
                "AWS::Lambda::Function", {"FunctionName": name}
            )
    
    def test_step_functions_workflow(self, content_stack):
        """Test Step Functions state machine is created"""
        template = assertions.Template.from_stack(content_stack)
        
        template.resource_count_is("AWS::StepFunctions::StateMachine", 1)
    
    def test_no_eventbridge_schedule(self, content_stack):
        """The Campus Coach schedule moved to the webhook stack (REST sync)"""
        template = assertions.Template.from_stack(content_stack)

        template.resource_count_is("AWS::Events::Rule", 0)
    
    def test_lambda_environment_variables(self, content_stack):
        """Test Lambda functions have required environment variables"""
        template = assertions.Template.from_stack(content_stack)
        
        # Content generator should have required env vars
        template.has_resource_properties("AWS::Lambda::Function", {
            "Environment": {
                "Variables": {
                    "ACTIVITIES_TABLE": assertions.Match.any_value(),
                    "USER_CONFIG_TABLE": assertions.Match.any_value(),
                    "BEDROCK_MODEL_ID": assertions.Match.any_value()
                }
            }
        })


class TestWebhookProcessingStack:
    """Test webhook processing stack"""
    
    @pytest.fixture
    def webhook_stack(self):
        """Create webhook processing stack for testing"""
        app = cdk.App()
        core_stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        stack = WebhookProcessingStack(
            app,
            "TestWebhookStack",
            core_stack=core_stack,
            step_functions_arn="arn:aws:states:eu-west-1:123456789012:stateMachine:test",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        return stack
    
    def test_sqs_queues_created(self, webhook_stack):
        """Test SQS queues are created"""
        template = assertions.Template.from_stack(webhook_stack)
        
        # Should have 2 queues (main + DLQ)
        template.resource_count_is("AWS::SQS::Queue", 2)
    
    def test_sqs_encryption(self, webhook_stack):
        """Test SQS queues are encrypted"""
        template = assertions.Template.from_stack(webhook_stack)
        
        template.has_resource_properties("AWS::SQS::Queue", {
            "KmsMasterKeyId": assertions.Match.any_value()
        })
    
    def test_sqs_dlq_configuration(self, webhook_stack):
        """Test DLQ is properly configured"""
        template = assertions.Template.from_stack(webhook_stack)
        
        template.has_resource_properties("AWS::SQS::Queue", {
            "RedrivePolicy": assertions.Match.object_like({
                "maxReceiveCount": 3
            })
        })
    
    def test_cloudwatch_alarms(self, webhook_stack):
        """Test CloudWatch alarms are created"""
        template = assertions.Template.from_stack(webhook_stack)
        
        # Should have alarms for DLQ, old messages, Lambda errors
        template.resource_count_is("AWS::CloudWatch::Alarm", 14)
    
    def test_api_gateway_created(self, webhook_stack):
        """Test API Gateway is created for webhooks"""
        template = assertions.Template.from_stack(webhook_stack)
        
        template.resource_count_is("AWS::ApiGateway::RestApi", 1)

    def test_eventbridge_schedule(self, webhook_stack):
        """Test EventBridge schedule for the Campus Coach REST sync"""
        template = assertions.Template.from_stack(webhook_stack)

        template.has_resource_properties("AWS::Events::Rule", {
            "Name": "strava-ai-boost-campus-coach-daily-sync",
            "ScheduleExpression": assertions.Match.string_like_regexp("cron.*"),
            "Targets": assertions.Match.array_with([
                assertions.Match.object_like({"Arn": assertions.Match.any_value()})
            ]),
        })

    def test_wellness_sync_scheduler_paris_timezone(self, webhook_stack):
        """A2: EventBridge Scheduler schedules for WellnessSync run in Europe/Paris
        with retry 2 / max age 1h, flexible window OFF."""
        template = assertions.Template.from_stack(webhook_stack)
        template.resource_count_is("AWS::Scheduler::Schedule", 2)
        schedules = template.find_resources("AWS::Scheduler::Schedule")
        for props in (r["Properties"] for r in schedules.values()):
            assert props["ScheduleExpressionTimezone"] == "Europe/Paris"
            assert props["FlexibleTimeWindow"]["Mode"] == "OFF"
            retry = props["Target"]["RetryPolicy"]
            assert retry["MaximumRetryAttempts"] == 2
            assert retry["MaximumEventAgeInSeconds"] == 3600
        exprs = {props["ScheduleExpression"] for props in
                 (r["Properties"] for r in schedules.values())}
        # 06:30 + 09:30 and 11:00 + 15:00 Paris.
        assert "cron(30 6,9 ? * * *)" in exprs
        assert "cron(0 11,15 ? * * *)" in exprs

    def test_wellness_sync_scheduler_role_invoke_only(self, webhook_stack):
        """The scheduler role is assumable only by scheduler.amazonaws.com and may
        only lambda:InvokeFunction (no wildcards)."""
        template = assertions.Template.from_stack(webhook_stack)
        roles = template.find_resources("AWS::IAM::Role")
        sched_roles = [
            props for props in (r["Properties"] for r in roles.values())
            if any(
                st["Principal"].get("Service") == "scheduler.amazonaws.com"
                for st in props["AssumeRolePolicyDocument"]["Statement"]
            )
        ]
        assert len(sched_roles) == 1
        policies = template.find_resources("AWS::IAM::Policy")
        invoke_only = []
        for props in (r["Properties"] for r in policies.values()):
            actions = []
            for st in props["PolicyDocument"]["Statement"]:
                a = st["Action"]
                actions += a if isinstance(a, list) else [a]
            if actions == ["lambda:InvokeFunction"]:
                invoke_only.append(props)
        assert invoke_only, "expected an invoke-only policy for the scheduler role"

    def test_campus_sync_wellness_grant_is_narrow(self, webhook_stack):
        """A3: CampusCoachSync may only UpdateItem the owner's partition in
        the wellness table (LeadingKeys), nothing broader. No PutItem."""
        import json as _json
        template = assertions.Template.from_stack(webhook_stack)
        template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "StravaAIBoost-CampusCoachSync",
            "Environment": {"Variables": assertions.Match.object_like({
                "WELLNESS_TABLE": "strava-ai-boost-wellness",
            })},
        })
        policies = template.find_resources("AWS::IAM::Policy")
        statements = []
        for props in (r["Properties"] for r in policies.values()):
            statements += props["PolicyDocument"]["Statement"]
        # The wellness write is the LeadingKeys-scoped UpdateItem-only statement
        # (the Resource is a cross-stack Fn::ImportValue of the wellness table ARN,
        # so it is matched by its condition + narrow action, not a literal name).
        wellness_writes = [
            st for st in statements
            if "dynamodb:LeadingKeys" in _json.dumps(st.get("Condition", {}))
            and set(st["Action"] if isinstance(st["Action"], list) else [st["Action"]])
                <= {"dynamodb:UpdateItem", "dynamodb:Query"}
            and "WellnessTable" in _json.dumps(st.get("Resource", ""))
        ]
        assert wellness_writes, "expected a LeadingKeys-scoped wellness write for CampusCoachSync"
        campus_writes = [
            st for st in wellness_writes
            if set(st["Action"] if isinstance(st["Action"], list) else [st["Action"]])
                == {"dynamodb:UpdateItem"}
        ]
        assert campus_writes, "CampusCoachSync wellness write must be UpdateItem only"
        for st in campus_writes:
            actions = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
            assert "dynamodb:PutItem" not in actions

    def test_wellness_sync_lambda_role_least_privilege(self, webhook_stack):
        """The WellnessSync Lambda role: no '*' resource/action, reads the
        intervals secret, writes/queries only the wellness table, GetItem on
        user-config scoped by LeadingKeys, Query on the coaching table."""
        template = assertions.Template.from_stack(webhook_stack)
        template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "StravaAIBoost-WellnessSync",
            "Handler": "webhooks.wellness_sync.handler",
        })
        policies = template.find_resources("AWS::IAM::Policy")
        all_statements = []
        for props in (r["Properties"] for r in policies.values()):
            all_statements += props["PolicyDocument"]["Statement"]

        import json as _json
        blob = _json.dumps(all_statements)
        # LeadingKeys condition present for the user-config GetItem.
        assert "dynamodb:LeadingKeys" in blob
        # The owner-scoped GetItem statement carries the LeadingKeys condition.
        getitem_scoped = [
            st for st in all_statements
            if "dynamodb:GetItem" in (st["Action"] if isinstance(st["Action"], list) else [st["Action"]])
            and "Condition" in st
            and "dynamodb:LeadingKeys" in _json.dumps(st["Condition"])
        ]
        assert getitem_scoped, "user-config GetItem must be scoped by LeadingKeys"
        # No wildcard dynamodb or secretsmanager action anywhere in these policies.
        assert "dynamodb:*" not in blob
        assert "secretsmanager:*" not in blob
        # The wellness write statement is UpdateItem/Query only (no PutItem/GetItem)
        # and scoped to the owner's partition by LeadingKeys.
        wellness_writes = [
            st for st in all_statements
            if "WellnessTable" in _json.dumps(st.get("Resource", ""))
            and set(st["Action"] if isinstance(st["Action"], list) else [st["Action"]])
                <= {"dynamodb:UpdateItem", "dynamodb:Query"}
            and "dynamodb:LeadingKeys" in _json.dumps(st.get("Condition", {}))
        ]
        assert wellness_writes, "expected a LeadingKeys-scoped UpdateItem/Query wellness statement"
        for st in wellness_writes:
            actions = set(st["Action"] if isinstance(st["Action"], list) else [st["Action"]])
            assert "dynamodb:PutItem" not in actions
            assert "dynamodb:GetItem" not in actions



class TestApiGatewayStack:
    """Test API Gateway stack"""
    
    @pytest.fixture
    def api_stack(self):
        """Create API Gateway stack for testing"""
        # Load cdk.json context (lambda_web_adapter layer config needed by the stack)
        import json
        from pathlib import Path
        cdk_context = json.loads(
            (Path(__file__).parent.parent / "cdk.json").read_text()
        ).get("context", {})
        app = cdk.App(context=cdk_context)
        core_stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        stack = ApiGatewayStack(
            app,
            "TestAPIStack",
            core_stack=core_stack,
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        return stack
    
    def test_api_gateway_created(self, api_stack):
        """Test REST API is created"""
        template = assertions.Template.from_stack(api_stack)
        
        template.resource_count_is("AWS::ApiGateway::RestApi", 1)
    
    def test_no_api_key(self, api_stack):
        """Test no API Key remains (auth is Cognito-only)"""
        template = assertions.Template.from_stack(api_stack)

        template.resource_count_is("AWS::ApiGateway::ApiKey", 0)
        template.resource_count_is("AWS::ApiGateway::UsagePlan", 0)

    def test_stage_throttling(self, api_stack):
        """Test stage-level rate limiting"""
        template = assertions.Template.from_stack(api_stack)

        template.has_resource_properties("AWS::ApiGateway::Stage", {
            "MethodSettings": assertions.Match.array_with([
                assertions.Match.object_like({
                    "ThrottlingRateLimit": 100,
                    "ThrottlingBurstLimit": 200
                })
            ])
        })
    
    def test_cors_configuration(self, api_stack):
        """Test CORS is properly configured"""
        template = assertions.Template.from_stack(api_stack)
        
        # CORS should allow localhost origins
        template.has_resource_properties("AWS::ApiGateway::RestApi", {
            "Name": assertions.Match.string_like_regexp(".*Local Interface.*")
        })
    
    def test_lambda_functions_for_api(self, api_stack):
        """Test Lambda functions for API endpoints"""
        template = assertions.Template.from_stack(api_stack)
        
        # Config, dashboard, preferences, health. The coach ask/stream Lambdas
        # were replaced by the coach_chat AgentCore Runtime (outside CDK), and
        # the audio debrief Lambda belongs to the voice debrief stack.
        template.resource_count_is("AWS::Lambda::Function", 4)
        for name in (
            "StravaAIBoost-ConfigurationAPI",
            "StravaAIBoost-DashboardAPI",
            "StravaAIBoost-UserPreferencesAPI",
            "StravaAIBoost-AgentCoreHealthCheck",
        ):
            template.has_resource_properties(
                "AWS::Lambda::Function", {"FunctionName": name}
            )


class TestPlanWorkoutsRoute:
    """GET /plan/workouts: Cognito route, owner env var, client cannot write the claim."""

    OWNER = "424242"

    @pytest.fixture(scope="class")
    def stacks(self):
        from pathlib import Path
        from stacks.frontend_hosting_stack import FrontendHostingStack
        cdk_context = json.loads(
            (Path(__file__).parent.parent / "cdk.json").read_text()
        ).get("context", {})
        app = cdk.App(context={**cdk_context, "default_user_id": self.OWNER})
        env = cdk.Environment(account="123456789012", region="us-east-1")
        core = CoreInfrastructureStack(app, "TestCoreStack", env=env)
        frontend = FrontendHostingStack(app, "TestFrontendStack", env=env)
        api = ApiGatewayStack(
            app, "TestAPIStack", core_stack=core,
            user_pool=frontend.user_pool, user_pool_client=frontend.user_pool_client,
            env=env,
        )
        return {
            "api": assertions.Template.from_stack(api),
            "frontend": assertions.Template.from_stack(frontend),
            "core": assertions.Template.from_stack(core),
        }

    def test_route_uses_cognito_authorizer(self, stacks):
        template = stacks["api"]
        resources = template.find_resources("AWS::ApiGateway::Resource")
        by_id = {lid: r["Properties"] for lid, r in resources.items()}
        workouts_ids = [
            lid for lid, props in by_id.items()
            if props["PathPart"] == "workouts"
            and by_id.get(props["ParentId"].get("Ref"), {}).get("PathPart") == "plan"
        ]
        assert len(workouts_ids) == 1
        methods = [
            m["Properties"] for m in template.find_resources("AWS::ApiGateway::Method").values()
            if m["Properties"].get("ResourceId", {}).get("Ref") == workouts_ids[0]
        ]
        get = [m for m in methods if m["HttpMethod"] == "GET"]
        assert len(get) == 1
        assert get[0]["AuthorizationType"] == "COGNITO_USER_POOLS"
        assert get[0]["AuthorizerId"] == {"Ref": next(iter(template.find_resources("AWS::ApiGateway::Authorizer")))}
        assert "DashboardAPI" in json.dumps(get[0]["Integration"]["Uri"])

    def test_home_summary_route_uses_cognito_authorizer(self, stacks):
        """A4: GET /home/summary is COGNITO_USER_POOLS, integrated with DashboardAPI."""
        template = stacks["api"]
        resources = template.find_resources("AWS::ApiGateway::Resource")
        by_id = {lid: r["Properties"] for lid, r in resources.items()}
        summary_ids = [
            lid for lid, props in by_id.items()
            if props["PathPart"] == "summary"
            and by_id.get(props["ParentId"].get("Ref"), {}).get("PathPart") == "home"
        ]
        assert len(summary_ids) == 1
        methods = [
            m["Properties"] for m in template.find_resources("AWS::ApiGateway::Method").values()
            if m["Properties"].get("ResourceId", {}).get("Ref") == summary_ids[0]
        ]
        get = [m for m in methods if m["HttpMethod"] == "GET"]
        assert len(get) == 1
        assert get[0]["AuthorizationType"] == "COGNITO_USER_POOLS"
        assert "DashboardAPI" in json.dumps(get[0]["Integration"]["Uri"])

    def test_dashboard_can_read_wellness_table(self, stacks):
        """A4: the DashboardAPI role has a read-only (GetItem/Query) grant on the
        wellness table. DashboardAPI uses the SHARED webhook_lambda_role defined
        in the Core stack, so the inline grant lands in the Core template."""
        import json as _json
        template = stacks["core"]
        policies = template.find_resources("AWS::IAM::Policy")
        statements = []
        for props in (r["Properties"] for r in policies.values()):
            statements += props["PolicyDocument"]["Statement"]
        wellness_reads = [
            st for st in statements
            if "WellnessTable" in _json.dumps(st.get("Resource", ""))
            and set(st["Action"] if isinstance(st["Action"], list) else [st["Action"]])
                <= {"dynamodb:GetItem", "dynamodb:Query"}
        ]
        assert wellness_reads, "expected a read-only wellness grant on the shared dashboard role"
        for st in wellness_reads:
            assert "dynamodb:LeadingKeys" in _json.dumps(st.get("Condition", {})), \
                "dashboard wellness read must be scoped by LeadingKeys"

    def test_owner_env_var_on_dashboard_lambda(self, stacks):
        stacks["api"].has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "StravaAIBoost-DashboardAPI",
            "Environment": {"Variables": assertions.Match.object_like({
                "CAMPUS_OWNER_STRAVA_ID": self.OWNER,
            })},
        })

    def test_lambda_function_count_unchanged(self, stacks):
        stacks["api"].resource_count_is("AWS::Lambda::Function", 4)

    def test_client_cannot_write_strava_claim(self, stacks):
        clients = stacks["frontend"].find_resources("AWS::Cognito::UserPoolClient")
        assert len(clients) == 1
        props = next(iter(clients.values()))["Properties"]
        write = props.get("WriteAttributes")
        assert write, "WriteAttributes must be explicit (unset means every attribute is writable)"
        assert "custom:strava_id" not in write
        assert not any(attr.startswith("custom:") for attr in write)
        read = props.get("ReadAttributes")
        assert read is None or "custom:strava_id" in read


class TestSecurityCompliance:
    """Test security and compliance configurations"""
    
    @pytest.fixture
    def all_stacks(self):
        """Create all stacks for security testing"""
        app = cdk.App()
        core_stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        content_stack = ContentGenerationStack(
            app,
            "TestContentStack",
            core_stack=core_stack,
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        return {"core": core_stack, "content": content_stack}
    
    def test_encryption_at_rest(self, all_stacks):
        """Test all data is encrypted at rest"""
        core_template = assertions.Template.from_stack(all_stacks["core"])
        
        # All DynamoDB tables should have encryption
        core_template.has_resource_properties("AWS::DynamoDB::Table", {
            "SSESpecification": {
                "SSEEnabled": True
            }
        })
    
    def test_iam_least_privilege(self, all_stacks):
        """Test IAM roles follow least privilege principle"""
        core_template = assertions.Template.from_stack(all_stacks["core"])
        
        # IAM roles should exist
        roles = core_template.find_resources("AWS::IAM::Role")
        assert len(roles) >= 2, "Should have IAM roles configured"
    
    def test_secrets_encryption(self, all_stacks):
        """Test Secrets Manager secrets are encrypted"""
        core_template = assertions.Template.from_stack(all_stacks["core"])
        
        # Secrets should be created (encryption is default)
        core_template.resource_count_is("AWS::SecretsManager::Secret", 4)
    
    def test_lambda_timeout_configuration(self, all_stacks):
        """Test Lambda functions have appropriate timeouts"""
        content_template = assertions.Template.from_stack(all_stacks["content"])
        
        # Lambda functions should have reasonable timeouts
        content_template.has_resource_properties("AWS::Lambda::Function", {
            "Timeout": assertions.Match.any_value()
        })


class TestInfrastructureIntegration:
    """Test infrastructure integration and dependencies"""
    
    def test_stack_dependencies(self):
        """Test stacks have proper dependencies"""
        app = cdk.App()
        core_stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        content_stack = ContentGenerationStack(
            app,
            "TestContentStack",
            core_stack=core_stack,
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        
        # Content stack should depend on core stack
        assert content_stack.core_stack == core_stack
    
    def test_resource_naming_consistency(self):
        """Test resource naming follows consistent pattern"""
        app = cdk.App()
        core_stack = CoreInfrastructureStack(
            app,
            "TestCoreStack",
            env=cdk.Environment(account="123456789012", region="eu-west-1")
        )
        
        # Check that table_names dictionary has the expected keys
        expected_keys = ["activities", "user_config", "coaching_sessions", "wellness"]
        for key in expected_keys:
            assert key in core_stack.table_names, f"Expected table key '{key}' in table_names"

        # Verify we have 4 tables
        assert len(core_stack.table_names) == 4, f"Expected 4 tables, found {len(core_stack.table_names)}"


def _campus_paces_templates(context):
    """Webhook + API templates synthesized with the given extra CDK context."""
    from pathlib import Path
    cdk_context = json.loads(
        (Path(__file__).parent.parent / "cdk.json").read_text()
    ).get("context", {})
    app = cdk.App(context={**cdk_context, **context})
    env = cdk.Environment(account="123456789012", region="eu-west-1")
    core = CoreInfrastructureStack(app, "TestCoreStack", env=env)
    webhook = WebhookProcessingStack(
        app, "TestWebhookStack", core_stack=core,
        step_functions_arn="arn:aws:states:eu-west-1:123456789012:stateMachine:test", env=env,
    )
    api = ApiGatewayStack(app, "TestAPIStack", core_stack=core, env=env)
    return assertions.Template.from_stack(webhook), assertions.Template.from_stack(api)


def _env_of(template, function_name):
    for resource in template.find_resources("AWS::Lambda::Function").values():
        props = resource["Properties"]
        if props.get("FunctionName") == function_name:
            return props.get("Environment", {}).get("Variables", {})
    raise AssertionError(f"{function_name} not found")


class TestCampusPaceSwitches:
    """docs/design/campus-paces.md: two switches, default off, each on its one Lambda."""

    def test_flags_parse_strictly(self):
        cases = (({}, "false"), ({"campus_zones_enabled": "false", "range_alerts_enabled": "false"}, "false"),
                 ({"campus_zones_enabled": "yes", "range_alerts_enabled": "1"}, "false"),
                 ({"campus_zones_enabled": "true", "range_alerts_enabled": "true"}, "true"),
                 ({"campus_zones_enabled": True, "range_alerts_enabled": True}, "true"))
        for context, expected in cases:
            webhook, api = _campus_paces_templates(context)
            assert _env_of(webhook, "StravaAIBoost-CampusCoachSync")["CAMPUS_ZONES_ENABLED"] == expected, context
            assert _env_of(api, "StravaAIBoost-DashboardAPI")["RANGE_ALERTS_ENABLED"] == expected, context

    def test_each_switch_lives_on_one_lambda_only(self):
        webhook, api = _campus_paces_templates({"campus_zones_enabled": "true", "range_alerts_enabled": "true"})
        for template in (webhook, api):
            for resource in template.find_resources("AWS::Lambda::Function").values():
                props = resource["Properties"]
                variables = props.get("Environment", {}).get("Variables", {})
                if props.get("FunctionName") != "StravaAIBoost-CampusCoachSync":
                    assert "CAMPUS_ZONES_ENABLED" not in variables, props.get("FunctionName")
                if props.get("FunctionName") != "StravaAIBoost-DashboardAPI":
                    assert "RANGE_ALERTS_ENABLED" not in variables, props.get("FunctionName")
        # Source check across every stack, not only the two synthesized here.
        from pathlib import Path
        stacks_dir = Path(__file__).parent.parent / "stacks"
        for name in ("CAMPUS_ZONES_ENABLED", "RANGE_ALERTS_ENABLED"):
            hits = sum(p.read_text().count(f'"{name}"') for p in stacks_dir.glob("*.py"))
            assert hits == 1, name

    def test_sync_can_update_user_config(self):
        webhook, _ = _campus_paces_templates({})
        functions = webhook.find_resources("AWS::Lambda::Function")
        sync_role = next(
            r["Properties"]["Role"]["Fn::GetAtt"][0] for r in functions.values()
            if r["Properties"].get("FunctionName") == "StravaAIBoost-CampusCoachSync"
        )
        statements = []
        for policy in webhook.find_resources("AWS::IAM::Policy").values():
            if {"Ref": sync_role} in policy["Properties"]["Roles"]:
                statements.extend(policy["Properties"]["PolicyDocument"]["Statement"])
        on_config = [s for s in statements if "strava-ai-boost-user-configuration" in json.dumps(s["Resource"])]
        actions = set()
        for statement in on_config:
            actions.update([statement["Action"]] if isinstance(statement["Action"], str) else statement["Action"])
        assert "dynamodb:UpdateItem" in actions
        assert not actions & {"dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:BatchWriteItem"}
