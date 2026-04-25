> ⚠️ **Early Access**: Behavior documentation is in early access. Please review critically.

# Workflows

> See also: [Business Logic](business-logic.md) | [Decision Logic](decision-logic.md) | [Sequence Diagrams](../diagrams/behavioral/sequence-diagrams.md)

## 1. Activity Enhancement Workflow (Core Pipeline)

**Trigger**: Strava sends a webhook when an athlete uploads or edits an activity.

1. **Strava** → POST `/webhook` → **Webhook Handler Lambda**
2. Webhook Handler validates signature (HMAC-SHA1), checks enhancement not paused, validates data structure
3. Webhook Handler sends message to **SQS Processing Queue** (`activity_id`, `user_id`, `webhook_data`)
4. **Activity Processor Lambda** consumes SQS message (batch size 1, max concurrency 5)
5. Activity Processor checks `should_skip_processing()` — skips completed/processing/recent failures
6. Activity Processor checks Enduraw module: if enabled and not waited, re-queues with 2-min delay
7. Activity Processor sets DynamoDB status to `processing` and starts **Step Functions** execution
8. **Step Functions** executes:
   - **TransformInput** (Pass): Extracts `activity_id`, `user_id`, adds `processing_timestamp`
   - **FetchActivityData** (Lambda): Calls Strava API (activity, laps, athlete stats, profile), Intervals.icu API, stores all data in DynamoDB
   - **CheckFetchSuccess** (Choice): Routes on `statusCode == 200` → GenerateContent, else → FetchFailed
   - **GenerateContent** (Lambda): Retrieves data from DynamoDB, applies modules, invokes AgentCore content agent, stores enhanced content
   - **UpdateStrava** (Lambda): PUTs enhanced title + description to Strava API, marks activity as `completed`
9. On failure at any step → **ProcessingFailed** state → EventBridge rule triggers **StepFunctionsErrorHandler** → routes to DLQ

## 2. OAuth Authentication Flow

**Trigger**: User initiates Strava connection from the frontend Configuration page.

1. **Frontend** → GET `/config/strava` to check if Strava app is configured
2. **Frontend** renders OAuth connection button with authorization URL
3. **User** clicks "Connect to Strava" → redirected to `strava.com/oauth/authorize` with `client_id`, `redirect_uri`, scopes
4. **User** approves → Strava redirects to frontend callback URL with `code`
5. **Frontend** → POST `/config/oauth` with authorization `code`
6. **Configuration API Lambda** exchanges code for tokens via Strava `POST /oauth/token`
7. Lambda stores tokens in Secrets Manager (`strava-ai-boost-oauth-tokens`): `access_token`, `refresh_token`, `expires_at`, `athlete_id`
8. Lambda updates `user_config_table` with `strava_connected=true` and `user_id` (athlete ID)
9. **Frontend** shows success message and redirects to Dashboard

**Token Refresh**: When `access_token` expires, `activity_fetcher.py` automatically refreshes using `refresh_token` + client credentials from `strava-ai-boost-app-config` secret, then updates Secrets Manager.

## 3. User Configuration Flow

**Trigger**: User modifies settings through the frontend.

### Module Configuration
1. **Frontend** → GET `/config/modules` — retrieves current module states from `user_config_table`
2. **User** toggles a module (e.g., Campus Coach)
3. **Frontend** → PUT `/config/modules/campus_coach` with `{enabled: true, credentials: {...}}`
4. **Configuration API Lambda** updates `modules_config.campus_coach` in DynamoDB
5. If Campus Coach enabled: Lambda enables EventBridge rule `StravaAIBoost-CampusCoach-DailyExtraction`
6. If Campus Coach disabled: Lambda disables the EventBridge rule

### Preferences Update
1. **Frontend** → GET `/preferences` — retrieves current preferences
2. **User** edits preferences (tone, length, language, emoji, pace zones)
3. **Frontend** → POST `/preferences` with updated preferences object
4. **User Preferences API Lambda** validates and stores in `user_config_table.user_preferences`

## 4. Feedback Analysis Workflow

**Trigger**: EventBridge schedule (daily at 3 AM UTC).

1. **EventBridge** triggers **FeedbackAnalyzer Lambda**
2. Lambda scans `activities_table` for recently completed activities (ProcessingStatusIndex GSI)
3. For each activity with `processing_status == 'completed'`:
   a. Fetches current Strava description via OAuth (with auto-refresh)
   b. Compares against `enhanced_description` stored in DynamoDB
   c. If descriptions differ: `description_modified = True`, computes similarity score
   d. Updates DynamoDB with `feedback_analyzed`, `description_modified`, `similarity_score`
4. For modified activities: writes feedback diff to **AgentCore Memory** as conversational event
5. AgentCore's UserPreferenceStrategy processes events and extracts user preferences
6. Emits business metrics: `FeedbackAnalyzed`, `FeedbackModified`

## 5. Dashboard Data Retrieval

**Trigger**: User opens the Dashboard page in the frontend.

1. **Frontend** → GET `/dashboard/stats` — total activities, success rate, completed/failed counts
2. **Frontend** → GET `/dashboard/activities` — recent activity list with processing details
3. **Frontend** → GET `/dashboard/system` — system health (Strava connected, AgentCore status, enhancement status, queue depth)
4. **Dashboard API Lambda** queries `activities_table` (GSI for status), `user_config_table`, checks SQS queue attributes, Step Functions execution history
5. **Frontend** auto-refreshes via `useAutoRefresh` hook at configurable interval

## 6. Campus Coach Daily Extraction

**Trigger**: EventBridge schedule (daily at 5 AM UTC, when enabled).

1. **EventBridge** sends `{action: "extract_sessions", source: "eventbridge_scheduler"}` to **CampusCoachInvoker Lambda**
2. Lambda retrieves Campus Coach agent ARN from environment
3. Lambda invokes AgentCore agent runtime asynchronously (fire and forget)
4. **Campus Coach Agent** (on AgentCore runtime):
   a. Retrieves credentials from Secrets Manager
   b. Initializes Strands Agent with Browser Tool and Memory hooks
   c. Navigates to `app.campus.coach/auth`, authenticates
   d. Scrolls dashboard, extracts 5 weekly sessions
   e. Parses JSON, saves sessions to `coaching_sessions` DynamoDB table (upsert by week+session number)
   f. Saves extraction summary to AgentCore Memory
5. Sessions are available for matching during next activity content generation
