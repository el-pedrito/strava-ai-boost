# Strava AI Boost - Improvement Plan

## 1. Security Fixes (Critical)

### 1.1 Scope IAM permissions to specific ARNs
- [x] `stacks/core_infrastructure_stack.py:198-220` — Replace `resources=["*"]` for SQS and Step Functions with specific ARNs
- [x] `stacks/api_gateway_stack.py:162-171` — Replace `resources=["*"]` for bedrock-agentcore with agent ARNs from env
- [x] ~~`stacks/core_infrastructure_stack.py:359-374` — Scope Secrets Manager write permissions~~ (already scoped to specific secret ARNs)

### 1.2 Filter EventBridge rule to our state machine only
- [x] ~~`stacks/webhook_processing_stack.py:239-251`~~ (already has `stateMachineArn` filter)

### 1.3 Stop exposing internal errors to API consumers
- [x] `lambda_functions/dashboard_api.py` — Return generic errors, log full error internally
- [x] `lambda_functions/user_preferences_api.py` — Same treatment
- [x] `lambda_functions/configuration_api.py` — Audit and fix all error responses

### 1.4 Add input validation on Lambda APIs
- [x] `lambda_functions/user_preferences_api.py` — Validate user_id format, whitelist preference values, body size check
- [x] ~~`lambda_functions/dashboard_api.py:135` — `days` param~~ (already validated in try/except at line 146)

### 1.5 Remove dead rate_limit code (feature entirely removed)
- [x] `lambda_functions/configuration_api.py` — Remove all `rate_limit_info` references and fix broken function signatures
- [x] `lambda_functions/dashboard_api.py` — Remove `rate_limit_info` from handler, response functions
- [x] `lambda_functions/agentcore_health_check.py` — Remove `rate_limit_info` variable, parameter, and argument
- [x] `tests/test_lambda_functions.py` — Remove stale `test_rate_limit_types`, `test_rate_limit_thresholds`
- [x] `tests/test_cdk_infrastructure.py` — Remove `rate_limits` table references (table no longer exists)
- [x] `tests/test_api_gateway.py` — Remove `test_rate_limit_headers` (rate limit headers no longer returned)

---

## 2. Architecture (High Priority)

### 2.1 Add GSI for user_id on activities_table
- [x] ~~Skipped~~ — No Lambda currently queries activities by user_id (only by activity_id). GSI not needed.

### 2.2 Refactor Step Functions to Parallel state
- [x] ~~Not applicable~~ — campus_coach_invoker runs via EventBridge daily schedule, not in the Step Function
- [x] Removed stale `campus_coach_invoker` from Step Functions `grant_invoke` list

### 2.3 Add Error Boundary in frontend
- [x] Create `frontend/src/components/ErrorBoundary.tsx` — Cloudscape Alert with retry button
- [x] Wrap routes in App.tsx with ErrorBoundary

### 2.4 Add React.lazy() code splitting
- [x] `frontend/src/App.tsx` — Lazy load DashboardPage, ConfigurationPage, PreferencesPage
- [x] Add Suspense wrapper with Spinner fallback
- [x] OAuthCallback kept eagerly loaded (lightweight, needs fast redirect)

---

## 3. Code Deduplication (High Priority)

### 3.1 Create shared Lambda utilities module
- [x] Create `lambda_functions/shared/responses.py` — `create_success_response()`, `create_error_response()` with CORS headers and `decimal_default`
- [x] Create `lambda_functions/shared/strava_oauth.py` — Shared `refresh_access_token()` (activity_fetcher has extended fallback logic, not migrated yet)
- [x] Create `lambda_functions/shared/env_validation.py` — `validate_env_vars()` for startup checks
- [x] ~~Create `lambda_functions/shared/dynamodb_utils.py`~~ — Not needed, DynamoDB patterns already use native `Table.query/scan` with CDK-granted permissions
- [x] Create `lambda_functions/shared/logger.py` — Powertools Logger + Metrics wrapper
- [x] Migrate `configuration_api.py` to shared responses (removed duplicate functions, removed local helpers)
- [x] Migrate `dashboard_api.py` — removed local CORS_HEADERS and `decimal_to_float` (uses shared)
- [x] Migrate `user_preferences_api.py` — removed local CORS_HEADERS (uses shared)
- [x] All 4 API Lambdas + activity_processor + feedback_analyzer use Powertools Logger via shared

### 3.2 Extract .env.agentcore loading into shared utility
- [x] Create `stacks/env_loader.py` with `load_env_agentcore()`, `load_agentcore_agent_arns()`, `load_agentcore_memory_id()`
- [x] Refactor `api_gateway_stack.py` — use `load_agentcore_agent_arns()`
- [x] Refactor `content_generation_stack.py` — use `load_env_agentcore()`
- [x] Refactor `feedback_loop_stack.py` — use `load_agentcore_memory_id()`

---

## 4. Observability (Medium Priority)

### 4.1 Add resource tags
- [x] `app.py` — Add Project and ManagedBy tags at app level

### 4.2 Implement structured logging
- [x] Add `aws-lambda-powertools>=2.40.0` to Lambda layer dependencies
- [x] Create `lambda_functions/shared/logger.py` — `get_logger()`, `get_metrics()` wrappers
- [x] Migrate API Lambdas to Powertools Logger: dashboard_api, configuration_api, user_preferences_api, agentcore_health_check
- [x] Migrate internal Lambdas: activity_processor, feedback_analyzer
- [x] Add correlation ID extraction from API Gateway `requestContext.requestId` via `inject_correlation_id()` in all 4 API handlers

### 4.3 Add business metrics
- [x] Publish custom CloudWatch metrics from activity_processor: ActivitiesProcessed, ActivitiesProcessFailed
- [x] Publish custom CloudWatch metrics from feedback_analyzer: FeedbackAnalyzed, FeedbackModified
- [x] Add business metrics widget to `stacks/monitoring_stack.py` dashboard

---

## 5. Cost Optimization (Medium Priority)

### 5.1 Add TTL on DynamoDB activities_table
- [x] `stacks/core_infrastructure_stack.py` — Add `time_to_live_attribute="expires_at"`
- [x] `lambda_functions/activity_fetcher.py` — Set `expires_at = now + 365 days` on put_item

### 5.2 Reduce Step Functions log verbosity
- [x] `stacks/content_generation_stack.py` — Change from `LogLevel.ALL` to `LogLevel.ERROR`

### 5.3 Reduce Lambda timeouts
- [x] `stacks/content_generation_stack.py` — content_generator: 10min -> 2min
- [x] `stacks/content_generation_stack.py` — campus_coach_invoker: 10min -> 2min

### 5.4 Lazy-init boto3 clients
- [x] `lambda_functions/dashboard_api.py` — Lazy-init CloudWatch client via `_get_cloudwatch()`
- [x] `lambda_functions/feedback_analyzer.py` — Lazy-init secretsmanager client via `_get_secretsmanager()`

---

## 6. Robustness (Medium Priority)

### 6.1 Add retry logic on external API calls
- [x] `lambda_functions/feedback_analyzer.py` — Add requests Session with Retry adapter (3 retries, backoff, 429/5xx)
- [x] `lambda_functions/activity_fetcher.py` — Add requests Session with Retry adapter for all Strava/external API calls

### 6.2 Catch specific exceptions instead of bare `except Exception`
- [x] `dashboard_api.py` — Replaced 10+ bare catches with ClientError, ValueError, TypeError
- [x] `feedback_analyzer.py` — Replaced 8+ bare catches with ClientError, RequestException, ValueError, json.JSONDecodeError
- [x] `activity_processor.py` — Replaced catches with ClientError, json.JSONDecodeError, ValueError
- [x] `user_preferences_api.py` — Replaced handler catch with ClientError, json.JSONDecodeError, ValueError
- [x] `configuration_api.py` — All catches now use specific types (ClientError, RequestException, json.JSONDecodeError)

### 6.3 Validate environment variables at Lambda startup
- [x] Created `lambda_functions/shared/env_validation.py` with `validate_env_vars()` utility
- [x] ~~Add validation calls~~ — Most Lambda files already use `os.environ['KEY']` (fails fast with KeyError); files using `.get()` have legitimate fallback defaults

---

## 7. Frontend Polish (Low Priority)

### 7.1 Add error state UI
- [x] `frontend/src/pages/Dashboard/DashboardPage.tsx` — Add error state with Alert and Retry button
- [x] Show error banner when API calls fail instead of silently swallowing

### 7.2 Memoize presentational components
- [x] Wrap SystemOverview, ConnectionStatus, ModuleStatus, RecentActivities with `React.memo()`

### 7.3 Accessibility
- [x] Add ARIA labels (`role="status"`) on metric cards in SystemOverview.tsx
- [x] Add `role="region"` with `aria-label` on connection cards in ConnectionStatus.tsx
- [x] Add active page indicator (`[ Page ]` brackets) in AppLayout.tsx navigation

### 7.4 Frontend status mapping deduplication
- [x] Create `frontend/src/utils/statusMapper.ts` — `statusType()`, `agentcoreType()`, `agentcoreLabel()`, `formatModuleName()`, `MODULE_DISPLAY_NAMES`, `ACTIVITY_TYPE_ICONS`, `getActivityIcon()`
- [x] Create `frontend/src/utils/formatDate.ts` — `formatDateTime()`, `computeProcessingTime()`
- [x] Update RecentActivities.tsx — import from shared utils (removed 35 lines of inline code)
- [x] Update ConnectionStatus.tsx — import `agentcoreType`, `agentcoreLabel` from shared utils
- [x] Update ModuleConfiguration.tsx — import `MODULE_DISPLAY_NAMES` from shared utils
- [x] Update DashboardPage.tsx — import `formatDateTime`, `computeProcessingTime` from shared utils

---

## Execution Order

| Phase | Sections | Status |
|-------|----------|--------|
| Phase 1 | 1.1-1.5 (Security) | Done |
| Phase 2 | 2.1, 2.3, 2.4, 3.2 (Arch + Dedup) | Done |
| Phase 3 | 4.1, 5.1, 5.2, 5.3, 5.4 (Observability + Cost) | Done |
| Phase 4 | 2.2, 6.1 (Step Functions + Retry) | Done |
| Phase 4b | 3.1, 6.3 (Shared utils, env validation) | Done |
| Phase 5 | 7.1, 7.2 (Frontend error states + memoization) | Done |
| Phase 5b | 7.3, 7.4 (Accessibility + status dedup) | Done |
| Phase 6 | 3.1, 4.2, 4.3, 6.2 (Shared migration, structured logging, business metrics, specific exceptions) | Done |
