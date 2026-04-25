# Components

> See also: [System Overview](system-overview.md) | [Dependencies](dependencies.md) | [Data Models](../reference/data-models.md)

## DynamoDB Tables

### strava-ai-boost-activities
- **Partition Key**: `activity_id` (String)
- **GSI**: `ProcessingStatusIndex` (partition: `processing_status`, sort: `created_at`)
- **TTL**: `expires_at` (365 days)
- **Stream**: NEW_AND_OLD_IMAGES
- **Billing**: PAY_PER_REQUEST
- **Encryption**: AWS_MANAGED
- **PITR**: Enabled
- **Key Fields**: `original_name`, `original_description`, `activity_type`, `distance`, `moving_time`, `processing_status`, `enhanced_title`, `enhanced_description`, `activity_data_json`, `athlete_stats_json`, `laps_json`, `intervals_icu_json`, `generation_metadata`, `execution_arn`

### strava-ai-boost-user-configuration
- **Partition Key**: `user_id` (String)
- **Key Fields**: `enhancement_enabled`, `strava_connected`, `modules_config` (nested: campus_coach, enduraw, intervals_icu), `user_preferences` (age_range, interests, sport_approach, content_length, content_tone, emoji_usage, technical_detail, content_language, pace_zones)

### strava-ai-boost-campus-coaching-sessions
- **Partition Key**: `session_date` (String)
- **Sort Key**: `session_id` (String)
- **GSI**: `WeekNumberIndex` (partition: `week_number`, sort: `session_date`)
- **Key Fields**: `title`, `workout`, `status` ("À faire"/"Complétée"), `targetedMetrics`, `intervals`, `coach_advice`, `objectives`, `week_number`, `session_number`

## Lambda Functions (12)

| Function | Package | Timeout | Memory | Trigger |
|---|---|---|---|---|
| WebhookHandler | webhooks | 30s | 256MB | API Gateway (public) |
| ActivityProcessor | webhooks | 5min | 512MB | SQS (batch=1, concurrency=5) |
| CampusCoachInvoker | webhooks | 2min | 512MB | EventBridge (daily 5 UTC) |
| ActivityFetcher | processing | 3min | 512MB | Step Functions |
| ContentGenerator | processing | 2min | 1024MB | Step Functions |
| StravaUpdater | processing | 2min | 256MB | Step Functions |
| ConfigurationAPI | api | 30s | 256MB | API Gateway |
| DashboardAPI | api | 30s | 256MB | API Gateway |
| UserPreferencesAPI | api | 10s | 128MB | API Gateway |
| AgentCoreHealthCheck | api | 10s | 128MB | API Gateway |
| FeedbackAnalyzer | support | 5min | 512MB | EventBridge (daily 3 UTC) |
| StepFunctionsErrorHandler | support | 60s | 256MB | EventBridge (SF failures) |

All Lambda functions use Python 3.12 runtime and share the `strava-ai-boost-dependencies` Lambda Layer.

## Step Functions State Machine

**Name**: `StravaAIBoost-ActivityProcessing`
**Timeout**: 30 minutes
**Logging**: ERROR level to `/aws/stepfunctions/strava-ai-boost-activity-processing`

**States**: TransformInput (Pass) → FetchActivityData (Lambda) → CheckFetchSuccess (Choice on statusCode=200) → GenerateContent (Lambda) → UpdateStrava (Lambda) → ProcessingComplete (Succeed). Each Lambda task has catch-all error handling routing to ProcessingFailed (Fail).

## SQS Queues

- **Processing Queue**: `strava-ai-boost-activity-processing` — 35 min visibility timeout, 14 day retention, KMS encrypted, DLQ after 3 failures
- **Dead Letter Queue**: `strava-ai-boost-activity-processing-dlq` — 14 day retention, KMS encrypted

## API Gateway (2 APIs)

### Strava AI Boost Local Interface API
- **Type**: REST, Regional
- **Auth**: API Key required on all endpoints
- **CORS**: `localhost:3000`, `localhost:5173`
- **Usage Plan**: 100 req/s, burst 200, 10K/day quota

### Strava AI Boost Webhook API
- **Type**: REST, Regional
- **Auth**: None (Strava requirement — security via HMAC-SHA1 signature)
- **Endpoints**: GET `/webhook` (verification), POST `/webhook` (notifications)

## Secrets Manager (4 Secrets)

| Secret | Purpose |
|---|---|
| `strava-ai-boost-oauth-tokens` | Strava OAuth access/refresh tokens, webhook verify token |
| `strava-ai-boost-app-config` | Strava app client_id + client_secret |
| `strava-ai-boost-campus-coach-credentials` | Campus Coach login username + password |
| `strava-ai-boost-intervals-icu-credentials` | Intervals.icu API key |

## AgentCore Agents (2)

### content_gen
- **Runtime**: PYTHON_3_12, linux/arm64
- **Entrypoint**: `src/agents/content_agent.py`
- **Model**: Claude Sonnet 4.5 (`global.anthropic.claude-sonnet-4-5-20250929-v1:0`)
- **Memory**: STM_AND_LTM (`content_gen_mem`)
- **Network**: PUBLIC
- **Features**: Semantic preference retrieval, UserPreferenceStrategy, guardrail input validation

### campus_coach
- **Runtime**: PYTHON_3_12, linux/arm64
- **Entrypoint**: `src/agents/campus_coach_agent.py`
- **Model**: Claude Sonnet 4.5
- **Tools**: AgentCore Browser Tool (headless Chrome)
- **Memory**: STM_AND_LTM (`campus_coach_mem`)
- **Network**: PUBLIC (requires web access for scraping)
- **Features**: Async task execution, DynamoDB session storage, credential retrieval from Secrets Manager

## Bedrock Guardrail

**Name**: `strava-ai-boost-content-guardrail`
- **PROMPT_ATTACK filter**: Input strength HIGH, output NONE
- **All other policies DISABLED**: Topic, PII, Word, and content filters (sexual, violence, hate) disabled to avoid rate limiting on 230K+ character prompts
- **Usage**: Applied selectively via `apply_guardrail()` API on user-provided title/description only

## CloudWatch Monitoring

- **Dashboard**: `Strava-AI-Boost-System-Metrics` (Lambda, Step Functions, SQS, DynamoDB, Business Metrics widgets)
- **Alarms**: 15+ alarms covering Lambda errors, duration, Step Functions failures, SQS DLQ, DynamoDB throttling
- **SNS Topic**: `strava-ai-boost-alarms`
- **Custom Metrics Namespace**: `StravaAIBoost` (ActivitiesProcessed, ActivitiesProcessFailed, FeedbackAnalyzed, FeedbackModified)

## EventBridge Rules

| Rule | Schedule | Target | Default State |
|---|---|---|---|
| `strava-ai-boost-feedback-analyzer-schedule` | Daily 3 AM UTC | FeedbackAnalyzer Lambda | Enabled |
| `StravaAIBoost-CampusCoach-DailyExtraction` | Daily 5 AM UTC | CampusCoachInvoker Lambda | Disabled |
| `strava-ai-boost-stepfunctions-failures` | Event pattern (SF failures) | StepFunctionsErrorHandler Lambda | Enabled |
