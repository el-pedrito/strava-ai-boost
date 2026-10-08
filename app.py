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
from stacks.feedback_loop_stack import FeedbackLoopStack
from stacks.frontend_hosting_stack import FrontendHostingStack
from stacks.voice_debrief_stack import VoiceDebriefStack
from stacks.push_stack import PushStack

app = cdk.App()

# Environment configuration
env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1"
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

# Frontend hosting stack - S3, CloudFront, Cognito
frontend_stack = FrontendHostingStack(
    app,
    "StravaAIBoost-Frontend",
    env=env,
    description="Frontend hosting with S3, CloudFront, and Cognito authentication"
)

# Voice debrief stack - Polly TTS + S3 + DynamoDB stream trigger
# (declared before api_stack so its API Lambda can be wired into API Gateway)
voice_debrief_stack = VoiceDebriefStack(
    app,
    "StravaAIBoost-VoiceDebrief",
    core_stack=core_stack,
    env=env,
    description="V1 voice debrief generator (Bedrock Haiku + Polly + private S3)"
)
voice_debrief_stack.add_dependency(core_stack)

# Push stack - opt-in Web Push notifications (subscriptions table, VAPID secret,
# PushApi + PushSend). Only synthesized with `--context push_enabled=true`, so a
# default deployment gets no new stack, secret, route or permission.
# Declared before api_stack so PushApi can be wired into API GW.
push_enabled = app.node.try_get_context("push_enabled") in (True, "true", "1")
push_stack = None
if push_enabled:
    push_stack = PushStack(
        app,
        "StravaAIBoost-Push",
        core_stack=core_stack,
        env=env,
        description="Opt-in Web Push notifications (VAPID + subscriptions + send)"
    )
    push_stack.add_dependency(core_stack)

# API Gateway stack - Local interface endpoints
api_stack = ApiGatewayStack(
    app,
    "StravaAIBoost-API",
    core_stack=core_stack,
    user_pool=frontend_stack.user_pool,
    user_pool_client=frontend_stack.user_pool_client,
    cloudfront_domain=frontend_stack.distribution.distribution_domain_name,
    audio_debrief_lambda=voice_debrief_stack.api_lambda,
    push_api_lambda=push_stack.push_api_lambda if push_stack else None,
    env=env,
    description="API Gateway for local web interface"
)
# Explicit dependency on core stack and frontend (for Cognito)
api_stack.add_dependency(core_stack)
api_stack.add_dependency(frontend_stack)
api_stack.add_dependency(voice_debrief_stack)

# Wire the push trigger into StravaUpdater: it invokes PushSend asynchronously. The
# grant is an explicit lambda:InvokeFunction on the exact PushSend ARN (see
# PushStack.grant_notify). Without push_enabled, StravaUpdater is left untouched.
if push_stack is not None:
    api_stack.add_dependency(push_stack)
    content_stack.strava_updater.add_environment("PUSH_ENABLED", "true")
    content_stack.strava_updater.add_environment(
        "PUSH_SEND_FUNCTION", push_stack.push_send_lambda.function_name
    )
    push_stack.grant_notify(content_stack.strava_updater)
    content_stack.add_dependency(push_stack)

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
feedback_stack.add_dependency(core_stack)

# Global resource tags for cost allocation
environment = app.node.try_get_context('environment') or 'dev'
cdk.Tags.of(app).add('Project', 'StravaAIBoost')
cdk.Tags.of(app).add('Environment', environment)
cdk.Tags.of(app).add('Owner', app.node.try_get_context('owner') or 'admin')
cdk.Tags.of(app).add('CostCenter', 'strava-ai-boost')
cdk.Tags.of(app).add('ManagedBy', 'CDK')

# Synthesize the CDK app
app.synth()