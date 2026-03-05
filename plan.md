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

### 1.5 Remove dead rate_limit_info code
- [x] `lambda_functions/configuration_api.py` — Remove all `rate_limit_info` references and fix broken function signatures
- [x] `lambda_functions/dashboard_api.py` — Remove `rate_limit_info` from handler, response functions
- [x] `lambda_functions/agentcore_health_check.py` — Remove `rate_limit_info` variable, parameter, and argument

---

## 2. Architecture (High Priority)

### 2.1 Add GSI for user_id on activities_table
- [x] ~~Skipped~~ — No Lambda currently queries activities by user_id (only by activity_id). GSI not needed.

### 2.2 Refactor Step Functions to Parallel state
- [ ] `stacks/content_generation_stack.py:355-541` — Run content_generator and campus_coach_invoker in Parallel
- [ ] strava_updater runs after Parallel completes (even if one branch fails)
- [ ] Each branch has its own Catch block

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
- [ ] Create `lambda_functions/shared/responses.py` — `create_success_response()`, `create_error_response()` with CORS headers
- [ ] Create `lambda_functions/shared/strava_oauth.py` — Token refresh logic (extract from feedback_analyzer.py and activity_fetcher.py)
- [ ] Create `lambda_functions/shared/dynamodb_utils.py` — Common query/scan patterns with retry
- [ ] Update all Lambda functions to import from shared module
- [ ] Add shared/ to Lambda layer or bundle

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
- [ ] Add `aws-lambda-powertools` to Lambda layer dependencies
- [ ] Refactor Lambda handlers to use Powertools Logger with structured fields
- [ ] Add correlation ID extraction from event headers, propagate through all log entries

### 4.3 Add business metrics
- [ ] Publish custom CloudWatch metrics from Lambda handlers: ActivitiesProcessed, ContentGenerated, FeedbackAnalyzed
- [ ] Add business metrics widget to `stacks/monitoring_stack.py` dashboard

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
- [ ] `lambda_functions/feedback_analyzer.py:266` — Add requests retry adapter with exponential backoff for Strava API
- [ ] `lambda_functions/user_preferences_api.py` — Add boto3 retry config for DynamoDB

### 6.2 Catch specific exceptions instead of bare `except Exception`
- [ ] Audit all Lambda functions — replace broad catches with specific ones (ClientError, json.JSONDecodeError, ValueError, etc.)
- [ ] Files: dashboard_api.py, feedback_analyzer.py, activity_processor.py, user_preferences_api.py

### 6.3 Validate environment variables at Lambda startup
- [ ] Add startup validation in each Lambda: check required env vars exist, fail fast with clear error

---

## 7. Frontend Polish (Low Priority)

### 7.1 Add error state UI
- [ ] `frontend/src/pages/Dashboard/DashboardPage.tsx` — Replace `.catch(() => null)` with proper error state
- [ ] Show "Failed to load" message with retry button per section

### 7.2 Memoize presentational components
- [ ] Wrap ConnectionStatus, SystemOverview, RecentActivities, ModuleStatus with `React.memo()`

### 7.3 Accessibility
- [ ] Add ARIA labels on metric cards in SystemOverview.tsx
- [ ] Add text labels alongside color-only status indicators in ConnectionStatus.tsx
- [ ] Add active page indicator in AppLayout.tsx navigation

### 7.4 Frontend status mapping deduplication
- [ ] Create `frontend/src/utils/statusMapper.ts` — centralize agentcoreType(), statusType(), formatModuleName()
- [ ] Create `frontend/src/utils/formatDate.ts` — centralize date formatting

---

## Execution Order

| Phase | Sections | Status |
|-------|----------|--------|
| Phase 1 | 1.1-1.5 (Security) | Done |
| Phase 2 | 2.1, 2.3, 2.4, 3.2 (Arch + Dedup) | Done |
| Phase 3 | 4.1, 5.1, 5.2, 5.3, 5.4 (Observability + Cost) | Done |
| Phase 4 | 2.2, 3.1, 4.2, 4.3, 6.1, 6.2, 6.3 (Step Functions + Robustness) | Todo |
| Phase 5 | 7.1, 7.2, 7.3, 7.4 (Frontend) | Todo |
