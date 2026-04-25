# Architectural Patterns

> See also: [System Overview](system-overview.md) | [Components](components.md) | [Diagrams](../diagrams/architecture/system-context.md)

## 1. Serverless Event-Driven Architecture

The entire system runs without persistent infrastructure. All compute is AWS Lambda, orchestrated by Step Functions, triggered by SQS events and EventBridge schedules. This provides automatic scaling, pay-per-invocation pricing, and zero idle cost.

**Implementation**: 12 Lambda functions, 1 Step Functions state machine, 2 SQS queues, 3 EventBridge rules, 2 API Gateway REST APIs.

## 2. Webhook → SQS → Step Functions Pipeline

The core processing pipeline uses a three-stage asynchronous pattern:
1. **Webhook Handler** validates Strava webhooks (HMAC-SHA1 signature) and sends messages to SQS
2. **Activity Processor** consumes SQS messages with batch item failure reporting and starts Step Functions executions
3. **Step Functions** orchestrates the Fetch → Generate → Update workflow with error handling at each step

This pattern provides reliable delivery (SQS durability), retry logic (SQS visibility timeout + DLQ), and observable orchestration (Step Functions execution history).

**Source**: `webhook_processing_stack.py` (SQS, Lambda event source), `content_generation_stack.py` (Step Functions definition)

## 3. Module Pattern (Plugin Architecture)

An extensible module system allows adding new integrations without modifying the core pipeline:
- **BaseModule** (`src/modules/base_module.py`): Abstract base class with lifecycle management (`initialize`, `shutdown`, `analyze_activity_with_timeout`), Pydantic-validated configuration (`ModuleConfig`), and structured results (`ModuleInsight`)
- **ModuleRegistry**: Global registry that modules register with on import; provides `get_available_modules()`, `create_module_instance()`, `get_module_info()`
- **Concrete Modules**: `EndurawModule` (wind/elevation/weather analysis), with TODO placeholders for Runna, TrainingPeaks
- **Auto-registration**: `registry.py` calls `register_all_modules()` on import

**Source**: `src/modules/base_module.py`, `src/modules/registry.py`, `src/modules/enduraw_module.py`

## 4. Dual-Mode AI (AgentCore Primary, Bedrock Fallback)

Content generation uses AgentCore (Strands Agents on managed runtime) as the primary AI system:
- **AgentCore agents** run on managed infrastructure with tools (Browser Tool for Campus Coach), memory (STM + LTM), and hooks
- **Content Agent** uses a comprehensive embedded system prompt (~20K+ chars) with rules for content generation, Campus Coach matching, Enduraw integration, and user preference enforcement
- **Guardrail input validation**: User-provided title/description validated via `apply_guardrail()` API before inclusion in the prompt, rather than wrapping the entire prompt with guardrails

**Source**: `src/agents/content_agent.py`, `src/agents/campus_coach_agent.py`, `src/agents/embedded_prompts.py`

## 5. DynamoDB as Data Bus Pattern

To avoid the Step Functions 256KB payload limit, all fetched data is stored in DynamoDB:
- **Activity Fetcher** stores complete activity data, athlete stats, athlete profile, laps, and Intervals.icu data as JSON strings in the `activities` table
- **Content Generator** retrieves this data from DynamoDB instead of receiving it through the Step Functions payload
- **Step Functions** passes only minimal references (`activity_id`, `user_id`) between states

**Source**: `activity_fetcher.py` (`store_activity_data`), `content_generator.py` (`retrieve_activity_data_from_dynamodb`)

## 6. CDK Multi-Stack Composition

The infrastructure is decomposed into 7 CDK stacks with explicit dependency declarations:
- Stacks share resources via properties (e.g., `core_stack.activities_table`)
- Dependencies declared via `add_dependency()` to ensure deployment order
- `env_loader.py` provides a shared utility for loading `.env.agentcore` configuration across stacks

**Anti-pattern addressed**: Lambda Layer cross-stack export uses a pinned `asset_hash` to prevent spurious replacements from filesystem metadata changes (macOS xattrs), which would break CloudFormation exports.

**Source**: `app.py`, `stacks/env_loader.py`, `stacks/core_infrastructure_stack.py` (LAYER_ASSET_HASH comment)

## 7. OAuth Token Management with Automatic Refresh

Strava OAuth tokens are stored in Secrets Manager and automatically refreshed when expired:
- **Token check**: `is_token_expired()` checks `expires_at` with a 5-minute safety buffer
- **Refresh flow**: Uses refresh token + client credentials from separate secrets (`strava-ai-boost-oauth-tokens` + `strava-ai-boost-app-config`)
- **Token storage**: Refreshed tokens written back to Secrets Manager immediately
- **Shared utility**: `shared/strava_oauth.py` provides a reusable `refresh_access_token()` function

**Source**: `activity_fetcher.py` (`get_access_token`, `is_token_expired`, `refresh_access_token`), `shared/strava_oauth.py`

## 8. Infinite Loop Prevention

When the system updates a Strava activity, Strava sends a webhook for the update, which could create an infinite loop. Prevention is multi-layered:
1. **Status check**: `should_skip_processing()` checks `processing_status` in DynamoDB — skips if `completed` or `processing`
2. **Update webhook filtering**: For `aspect_type == 'update'`, additional restrictions apply — skip if ever processed successfully
3. **Cooldown**: Failed activities within 1 hour are skipped on update webhooks
4. **Enduraw wait state**: Activities in `waiting_enduraw` status are skipped unless the `enduraw_waited` flag is set

**Source**: `activity_processor.py` (`should_skip_processing`)

## 9. Dead Letter Queue (DLQ) Error Handling

Failed messages flow through a multi-level error handling chain:
1. **SQS retry**: Messages retried up to 3 times (maxReceiveCount) before moving to DLQ
2. **Batch item failure reporting**: `activity_processor.py` uses `ReportBatchItemFailures` to selectively retry failed messages without affecting successful ones
3. **Step Functions error handler**: EventBridge rule captures SF failures and routes to DLQ via a dedicated Lambda
4. **CloudWatch alarms**: DLQ message count triggers alarms (threshold: 1 message)

**Source**: `webhook_processing_stack.py`, `activity_processor.py`, `support/stepfunctions_error_handler.py`

## 10. Memory-Driven Personalization (AgentCore Memory)

The system learns user preferences over time through a feedback loop:
1. **Content Generation**: Agent generates content using embedded system prompt + user preferences
2. **Strava Update**: Content pushed to Strava
3. **User Modification**: User edits the AI-generated content on Strava
4. **Feedback Analysis**: Nightly `FeedbackAnalyzer` compares current vs. generated content, writes diffs to AgentCore Memory as conversational events
5. **Memory Processing**: AgentCore's built-in UserPreferenceStrategy extracts preferences from feedback diffs
6. **Preference Retrieval**: Next content generation retrieves preferences via `RetrieveMemoryRecords` (semantic search) and includes them in the system prompt

**Source**: `support/feedback_analyzer.py`, `src/agents/content_agent.py` (`retrieve_user_preferences`, `AgentCoreMemoryHook`)

## 11. Shared Utilities Pattern (Lambda Layer)

Common functionality is extracted into `lambda_functions/shared/`:
- **Structured logging**: AWS Lambda Powertools Logger with service name, uncaught exception logging, correlation ID injection
- **Business metrics**: Pre-configured Metrics instance with `StravaAIBoost` namespace
- **CORS responses**: Standardized success/error response builders with CORS headers for read/write operations
- **Environment validation**: Simple validator for required environment variables
- **OAuth refresh**: Reusable token refresh function

The Lambda Layer (`lambda_layer/`) packages `requests` and `aws-lambda-powertools` for all functions.

**Source**: `lambda_functions/shared/*.py`, `lambda_layer/requirements.txt`

## 12. Enduraw Integration Delay Pattern

When the Enduraw module is enabled, activities are processed with a 2-minute delay:
1. **Activity Processor** checks user config for Enduraw enablement
2. If enabled and not yet waited, re-queues the SQS message with `DelaySeconds=120`
3. Sets `enduraw_waited=True` flag in the message body
4. On the delayed re-delivery, processing continues normally
5. The delay allows Enduraw's third-party app to process the activity and add enhanced data to the Strava description

**Source**: `activity_processor.py` (Enduraw wait logic), `content_generator.py` (`extract_enduraw_report`)
