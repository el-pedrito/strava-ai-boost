#!/usr/bin/env python3
"""
Strava AI Boost - CDK Application Entry Point

This is the main CDK application that defines and deploys all AWS infrastructure
for the Strava AI Boost system.
"""

import aws_cdk as cdk
from stacks.core_infrastructure_stack import CoreInfrastructureStack
from stacks.security_stack import SecurityStack
from stacks.api_gateway_stack import ApiGatewayStack
from stacks.webhook_processing_stack import WebhookProcessingStack
from stacks.content_generation_stack import ContentGenerationStack
from stacks.monitoring_stack import MonitoringStack
from stacks.feedback_loop_stack import FeedbackLoopStack

app = cdk.App()

# Environment configuration
env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "eu-west-1"
)

# Core infrastructure stack - DynamoDB tables, IAM roles
core_stack = CoreInfrastructureStack(
    app, 
    "StravaAIBoost-Core",
    env=env,
    description="Core infrastructure for Strava AI Boost - DynamoDB tables and IAM roles"
)

# Security stack - Bedrock Guardrails
security_stack = SecurityStack(
    app,
    "StravaAIBoost-Security",
    env=env,
    description="Security infrastructure with Bedrock Guardrails for content safety"
)

# Content generation stack - Step Functions, Bedrock, AgentCore
content_stack = ContentGenerationStack(
    app,
    "StravaAIBoost-Content",
    core_stack=core_stack,
    security_stack=security_stack,
    env=env,
    description="Content generation infrastructure with Step Functions and Bedrock"
)
# Explicit dependencies
content_stack.add_dependency(core_stack)
content_stack.add_dependency(security_stack)

# Webhook processing stack - Strava webhooks, SQS
webhook_stack = WebhookProcessingStack(
    app,
    "StravaAIBoost-Webhook",
    core_stack=core_stack,
    step_functions_arn=content_stack.state_machine_arn,
    env=env,
    description="Webhook processing infrastructure for Strava AI Boost"
)
# Explicit dependencies
webhook_stack.add_dependency(core_stack)
webhook_stack.add_dependency(content_stack)

# API Gateway stack - Local interface endpoints
api_stack = ApiGatewayStack(
    app,
    "StravaAIBoost-API",
    core_stack=core_stack,
    env=env,
    description="API Gateway for local web interface"
)
# Explicit dependency on core stack
api_stack.add_dependency(core_stack)

# Monitoring stack - CloudWatch alarms and dashboards
monitoring_stack = MonitoringStack(
    app,
    "StravaAIBoost-Monitoring",
    core_stack=core_stack,
    webhook_stack=webhook_stack,
    content_stack=content_stack,
    env=env,
    description="Monitoring and observability infrastructure"
)
# Explicit dependencies on all other stacks
monitoring_stack.add_dependency(core_stack)
monitoring_stack.add_dependency(content_stack)
monitoring_stack.add_dependency(webhook_stack)
monitoring_stack.add_dependency(api_stack)

# Feedback loop stack - Automatic learning from user modifications
feedback_stack = FeedbackLoopStack(
    app,
    "StravaAIBoost-Feedback",
    activities_table=core_stack.activities_table,
    strava_oauth_secret=core_stack.strava_oauth_secret,
    strava_app_secret=core_stack.strava_app_secret,
    dependencies_layer=core_stack.dependencies_layer,
    env=env,
    description="Feedback loop infrastructure for learning from user modifications"
)
# Explicit dependency on core stack
feedback_stack.add_dependency(core_stack)

# Synthesize the CDK app
app.synth()