> ⚠️ **Early Access**: Behavior documentation is in early access. Please review critically.

# Error Handling

> See also: [Decision Logic](decision-logic.md) | [Business Logic](business-logic.md) | [Architecture Patterns](../architecture/patterns.md)

## Step Functions Error Handler
**Source**: `lambda_functions/support/stepfunctions_error_handler.py`, `stacks/webhook_processing_stack.py`

- **EventBridge Rule** (`strava-ai-boost-stepfunctions-failures`) captures Step Functions execution status changes where `status` is `FAILED`, `TIMED_OUT`, or `ABORTED` for the `StravaAIBoost-ActivityProcessing` state machine
- **StepFunctionsErrorHandler Lambda**: Receives EventBridge event, extracts execution ARN, describes execution to get error details, updates activity status to `failed` in DynamoDB, and sends error details to DLQ for manual investigation
- **Permissions**: `states:DescribeExecution` on execution ARNs, DynamoDB read/write on activities table, SQS send to DLQ

## DLQ Handling
**Source**: `stacks/webhook_processing_stack.py`

- **Max receive count**: 3 — messages are retried 3 times before moving to DLQ
- **Visibility timeout**: 35 minutes (longer than Step Functions max timeout to avoid duplicate processing)
- **DLQ retention**: 14 days
- **CloudWatch Alarm**: `strava-ai-boost-dlq-messages` fires when `ApproximateNumberOfVisibleMessages >= 1`
- **Manual reprocessing**: `scripts/reprocess_dlq.sh` script for manually replaying DLQ messages
- **Activity Processor also directly sends to DLQ**: In addition to SQS automatic DLQ routing, the Activity Processor has explicit DLQ send permissions for manual error routing

## Batch Item Failure Reporting
**Source**: `lambda_functions/webhooks/activity_processor.py`

- Lambda returns `{'batchItemFailures': [...]}` with `itemIdentifier` for failed records
- SQS event source configured with `report_batch_item_failures=True` (sets `FunctionResponseTypes=ReportBatchItemFailures`)
- Successful messages are deleted from queue; failed messages remain for retry
- On critical Lambda errors (ClientError, JSONDecodeError, KeyError, ValueError), ALL messages are reported as failures
- Business metrics emitted: `ActivitiesProcessed` (successful) and `ActivitiesProcessFailed` (failed)

## Lambda Powertools Structured Logging
**Source**: `lambda_functions/shared/logger.py`

- **Logger**: `aws_lambda_powertools.Logger` with service name, `log_uncaught_exceptions=True`
- **Metrics**: Pre-configured `Metrics` instance with `StravaAIBoost` namespace
- **Correlation ID**: `inject_correlation_id()` extracts API Gateway `requestId` and sets on logger
- All Lambda functions use `get_logger(service_name)` for consistent structured JSON logging
- Log levels: INFO for normal operations, WARNING for degraded paths, ERROR for failures
- Each logger includes service name for CloudWatch Logs Insights filtering

## OAuth Token Refresh Error Handling
**Source**: `lambda_functions/processing/activity_fetcher.py`, `lambda_functions/shared/strava_oauth.py`

- **Expiry detection**: `is_token_expired()` handles both timestamp and ISO format `expires_at` with 5-minute safety buffer
- **Refresh flow**: Gets `refresh_token` from OAuth secret + `client_id`/`client_secret` from app config secret
- **HTTP retry**: Uses `requests.Session` with `Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])`
- **Failure modes**:
  - Missing credentials (client_id or client_secret) → returns None, raises ValueError upstream
  - Strava API returns non-200 → logs error, returns None
  - Invalid response (no access_token) → logs error, returns None
  - Network error (RequestException) → logs error, returns None
- **Token storage**: On successful refresh, immediately writes updated tokens to Secrets Manager
- **Shared utility**: `shared/strava_oauth.py` provides a simpler `refresh_access_token()` for other consumers (feedback_analyzer)

## AgentCore Cold Start and Error Handling
**Source**: `lambda_functions/webhooks/campus_coach_invoker.py`, `src/agents/campus_coach_agent.py`

- **Campus Coach Invoker**: Catches all exceptions, returns structured error response (never crashes Lambda)
- **Missing agent ARN**: Checks `CAMPUS_COACH_AGENT_ARN` env var, returns 500 error if not configured
- **Async invocation**: Campus Coach agent invoked asynchronously (fire-and-forget pattern) — Lambda returns immediately, agent runs in background on AgentCore runtime
- **Agent-level error handling**: Browser Tool exceptions caught and logged; JSON parsing failures return partial results with `saved_count: 0`
- **Memory hook errors**: `AgentCoreMemoryHook` catches and logs all exceptions in `on_agent_initialized` and `on_message_added` without failing the agent
- **Content Agent**: Guardrail validation failures return safe fallback content instead of erroring; empty AgentCore responses raise ValueError caught by handler

## Webhook Security and Validation
**Source**: `lambda_functions/webhooks/webhook_handler.py`

- **Signature verification**: HMAC-SHA1 comparison using `hmac.compare_digest()` for timing-safe comparison
- **Graceful degradation**: If no webhook secret configured in Secrets Manager, allows requests through (development mode)
- **ResourceNotFoundException**: If Secrets Manager secret doesn't exist, allows verification/webhooks through with warning
- **Field validation**: Validates `object_id` and `owner_id` are numeric, `object_type` in `[activity, athlete]`, `aspect_type` in `[create, update, delete]`, `event_time` is numeric
- **JSON decode errors**: Caught and returned as 400 Bad Request

## Step Functions Workflow Error Handling
**Source**: `stacks/content_generation_stack.py`

- Each Lambda task (`FetchActivityData`, `GenerateContent`, `UpdateStrava`) has `.add_catch(failure, errors=["States.ALL"])` — catches all errors and routes to ProcessingFailed state
- `FetchActivityData` success check: Choice state validates `statusCode == 200`, routes non-200 to `FetchFailed` (separate Fail state with `cause_path`)
- Lambda tasks have `retry_on_service_exceptions=True` for automatic retry on transient Lambda errors
- State machine timeout: 30 minutes
- Error logging: `LogLevel.ERROR` to dedicated CloudWatch log group

## DynamoDB Status Update Error Handling
**Source**: `lambda_functions/webhooks/activity_processor.py`

- `update_activity_status()` accepts a `critical` parameter:
  - `critical=True` (e.g., setting initial `processing` status): Re-raises `ClientError` to trigger SQS retry
  - `critical=False` (e.g., setting final `failed` status): Logs error but does not raise — avoids cascading failures
- This prevents a DynamoDB update failure from blocking the entire processing pipeline for non-critical status changes

## Frontend Error Handling
**Source**: `frontend/src/components/ErrorBoundary.tsx`, `frontend/src/api/client.ts`

- **ErrorBoundary**: React error boundary wrapping the entire application; renders fallback UI on unrecoverable errors
- **ApiError class**: Custom error with HTTP status code for structured error handling
- **API client**: All requests wrapped with consistent error handling — non-200 responses throw `ApiError` with extracted error message
- **Flash messages**: `useFlashMessages` hook provides dismissible success/error/warning notifications
