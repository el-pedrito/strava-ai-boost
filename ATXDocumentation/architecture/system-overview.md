# System Overview

> See also: [Components](components.md) | [Dependencies](dependencies.md) | [Patterns](patterns.md) | [Diagrams](../diagrams/architecture/system-context.md)

## High-Level Architecture

Strava AI Boost is a **serverless, event-driven system** deployed on AWS using the Cloud Development Kit (CDK). It processes Strava activity webhooks through a multi-stage pipeline that enriches activities with AI-generated content using Amazon Bedrock (Claude Sonnet 4.5) via AgentCore.

## CDK Stacks (7 Total)

### 1. CoreInfrastructureStack (`StravaAIBoost-Core`)
**Purpose**: Foundation layer providing shared data stores, IAM roles, secrets, and the Lambda dependency layer.
- **DynamoDB Tables**: `strava-ai-boost-activities` (partition: `activity_id`, GSI: `ProcessingStatusIndex`, TTL: `expires_at`, DynamoDB Streams), `strava-ai-boost-user-configuration` (partition: `user_id`), `strava-ai-boost-campus-coaching-sessions` (partition: `session_date`, sort: `session_id`, GSI: `WeekNumberIndex`)
- **IAM Roles**: `WebhookLambdaRole` (DynamoDB, SQS, Secrets Manager, Step Functions read), `ContentLambdaRole` (Bedrock, AgentCore), `StepFunctionsRole` (Lambda invocation)
- **Secrets Manager**: 4 secrets — Strava OAuth tokens, Strava App config, Campus Coach credentials, Intervals.icu API key
- **Lambda Layer**: Shared dependencies (requests, aws-lambda-powertools) with pinned asset hash to prevent cross-stack export breakage
- **Dependencies**: None (base stack)

### 2. SecurityStack (`StravaAIBoost-Security`)
**Purpose**: AI safety and observability infrastructure.
- **Bedrock Guardrail**: `strava-ai-boost-content-guardrail` — prompt attack protection (HIGH input strength), content policy with only PROMPT_ATTACK filter to avoid rate limiting on large prompts
- **AgentCore Memory Execution Role**: IAM role for `bedrock-agentcore.amazonaws.com` to invoke Bedrock models for UserPreferenceStrategy
- **AgentCore Observability**: CloudWatch Logs resource policy for X-Ray, 100% sampling for full trace capture
- **Custom Resources**: Lambda-backed custom resources for CloudWatch Logs policy and X-Ray configuration
- **Dependencies**: None

### 3. ContentGenerationStack (`StravaAIBoost-Content`)
**Purpose**: AI content generation pipeline with Step Functions orchestration.
- **Lambda Functions**: `ContentGenerator` (2 min timeout, 1024MB, AgentCore invocation), `ActivityFetcher` (3 min, 512MB, Strava + Intervals.icu APIs), `StravaUpdater` (2 min, 256MB), `CampusCoachInvoker` (2 min, 512MB, AgentCore Browser Tool)
- **Step Functions**: `StravaAIBoost-ActivityProcessing` state machine — TransformInput → FetchActivityData → CheckFetchSuccess → GenerateContent → UpdateStrava (30 min timeout)
- **EventBridge Rule**: `StravaAIBoost-CampusCoach-DailyExtraction` — Daily at 5 UTC (6 AM Paris), disabled by default, enabled via API when user toggles Campus Coach module
- **Dependencies**: CoreInfrastructureStack, SecurityStack

### 4. WebhookProcessingStack (`StravaAIBoost-Webhook`)
**Purpose**: Strava webhook reception and reliable message processing.
- **SQS Queues**: Processing queue (35 min visibility, 14 day retention, KMS encrypted, DLQ with maxReceiveCount: 3), DLQ (14 day retention)
- **Lambda Functions**: `WebhookHandler` (30s, webhook validation + SQS queueing), `ActivityProcessor` (5 min, 512MB, SQS consumer + Step Functions launcher, reserved concurrency: 5, batch item failure reporting)
- **Step Functions Error Handler**: Lambda triggered by EventBridge rule on Step Functions `FAILED/TIMED_OUT/ABORTED` events
- **CloudWatch Alarms**: DLQ messages ≥ 1, old messages > 1 hour, Lambda errors > 3 in 5 min
- **Webhook API Gateway**: Public REST API (no auth — Strava requires unauthenticated endpoints, security via HMAC-SHA1 signature verification)
- **Dependencies**: CoreInfrastructureStack, ContentGenerationStack

### 5. ApiGatewayStack (`StravaAIBoost-API`)
**Purpose**: Local web interface REST API with API key authentication.
- **REST API**: Regional endpoint with CORS for localhost:3000/5173
- **API Key + Usage Plan**: Rate limit 100 req/s, burst 200, quota 10,000/day
- **Lambda Functions**: `ConfigurationAPI` (OAuth, modules, enhancement control), `DashboardAPI` (stats, activities, system), `UserPreferencesAPI` (preferences), `AgentCoreHealthCheck` (agent runtime status)
- **Endpoints**: `/config/strava`, `/config/oauth`, `/config/modules`, `/config/enhancement`, `/dashboard/stats`, `/dashboard/activities`, `/dashboard/system`, `/preferences`, `/health/agentcore`, `/test/strava-connection`
- **Dependencies**: CoreInfrastructureStack

### 6. MonitoringStack (`StravaAIBoost-Monitoring`)
**Purpose**: Comprehensive monitoring and alerting.
- **SNS Topic**: `strava-ai-boost-alarms` for alert notifications
- **CloudWatch Alarms**: Error rate + duration alarms for 5 Lambda functions, Step Functions failure alarm, SQS DLQ alarm, DynamoDB throttling alarms for 3 tables
- **CloudWatch Dashboard**: `Strava-AI-Boost-System-Metrics` with 5 widgets (Lambda, Step Functions, SQS, DynamoDB, Business Metrics)
- **Dependencies**: CoreInfrastructureStack, WebhookProcessingStack, ContentGenerationStack, ApiGatewayStack

### 7. FeedbackLoopStack (`StravaAIBoost-Feedback`)
**Purpose**: Automatic learning from user modifications to AI-generated content.
- **Lambda Function**: `FeedbackAnalyzer` (5 min, 512MB) — compares current Strava descriptions against generated ones, writes feedback diffs to AgentCore Memory for UserPreferenceStrategy learning
- **EventBridge Schedule**: Daily at 3 AM UTC
- **IAM**: DynamoDB read/write, Secrets Manager read/write (token refresh), AgentCore Memory create/get/list events
- **Dependencies**: CoreInfrastructureStack

## Deployment Model

- **CDK CLI**: `cdk deploy --all` deploys all 7 stacks in dependency order
- **Region**: `eu-west-1` (configurable via `cdk.json` context)
- **Environment Tags**: Project, Environment, Owner, CostCenter, ManagedBy
- **AgentCore Agents**: Deployed separately via `bedrock-agentcore` CLI (`scripts/deploy_agentcore_agents.sh`)
- **Lambda Layer**: Manual build via `pip install -t` to `lambda_layer/` directory, asset hash pinned in `core_infrastructure_stack.py`

## Key Architectural Decisions

1. **Serverless-first**: No persistent compute infrastructure; all functions run on Lambda with pay-per-invocation pricing
2. **Dual-mode AI**: AgentCore (Strands Agents on managed runtime) as primary, with Bedrock direct invoke as potential fallback
3. **DynamoDB as data bus**: All fetched activity data stored in DynamoDB to avoid Step Functions 256KB payload limit; downstream Lambdas read from DynamoDB
4. **Webhook update loop prevention**: Status-based skip logic in `activity_processor.py` prevents infinite loops when Strava sends update webhooks for AI-modified activities
5. **Module extensibility**: Base module abstract class + registry pattern enables adding new integrations without modifying the core pipeline
6. **Memory-driven personalization**: AgentCore Memory (STM + LTM) with UserPreferenceStrategy learns from user modifications via nightly feedback analysis
7. **Zero AWS SDK in frontend**: React app uses only fetch() with API key — no AWS credentials exposed to browser
8. **Guardrail on inputs only**: Bedrock Guardrail applied to user-provided title/description via `apply_guardrail()` API, not on the full 230K+ character prompt to avoid rate limiting
