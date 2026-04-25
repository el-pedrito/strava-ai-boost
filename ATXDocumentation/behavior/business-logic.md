> ⚠️ **Early Access**: Behavior documentation is in early access. Please review critically.

# Business Logic

> See also: [Workflows](workflows.md) | [Decision Logic](decision-logic.md) | [Error Handling](error-handling.md) | [Architecture Patterns](../architecture/patterns.md)

## Webhook Validation and Subscription Verification
**Source**: `lambda_functions/webhooks/webhook_handler.py`

- **GET requests** (verification): Strava sends `hub.mode`, `hub.challenge`, `hub.verify_token`; handler validates `verify_token` against value stored in Secrets Manager (`strava-ai-boost-oauth-tokens → webhook_verify_token`), returns `hub.challenge` if valid
- **POST requests** (notifications): Validates webhook signature via HMAC-SHA1 (`X-Hub-Signature` header) using `webhook_secret` from Secrets Manager; parses body and validates required fields (`object_type`, `object_id`, `aspect_type`, `owner_id`)
- **Enhancement pause check**: Before queueing, reads `user_config_table` for `enhancement_enabled` flag; if paused, acknowledges webhook but skips processing
- **Event filtering**: Only processes `object_type=activity` with `aspect_type` in `[create, update]`; ignores athlete events and delete events
- **SQS queueing**: Sends message with `activity_id`, `user_id`, `webhook_data`, `event_time` to processing queue with message attributes

## Activity Enhancement Pipeline
**Source**: `lambda_functions/processing/activity_fetcher.py`, `content_generator.py`, `strava_updater.py`

### Activity Fetcher
- Retrieves Strava OAuth access token with automatic refresh (5-minute expiry buffer)
- Fetches complete activity data (67+ Strava fields) including `start_latlng`, `location_city`, `description`
- Fetches device-recorded laps via `/activities/{id}/laps` endpoint
- Fetches athlete stats (YTD totals, all-time records) and athlete profile (FTP, weight)
- Fetches user configuration for module decisions
- Conditionally fetches Intervals.icu data if module is enabled
- **Stores ALL data in DynamoDB** as JSON strings to avoid Step Functions 256KB payload limit
- Sets TTL of 365 days on activity records

### Content Generator
- Retrieves complete activity data from DynamoDB (not from Step Functions payload)
- Determines active modules from user configuration via module registry
- Extracts Enduraw Report from activity description using regex pattern matching (`𝗘𝗻𝗱𝘂𝗿𝗮𝘄 𝗥𝗲𝗽𝗼𝗿𝘁`)
- Classifies workout type from laps (intervals, fartlek, progression, steady, recovery, tempo, etc.) using pace variability analysis
- Applies module-specific processing (Campus Coach session matching, Enduraw metrics)
- Invokes AgentCore content generation agent with complete context
- Parses JSON response, validates title/description, enforces user preferences (emoji limits, content length, language)
- Stores generated content (`enhanced_title`, `enhanced_description`, `generation_metadata`) in DynamoDB

### Strava Updater
- Retrieves access token from Secrets Manager
- Updates Strava activity via `PUT /activities/{id}` with `name` and `description`
- Updates DynamoDB processing status to `completed` with enhanced content
- Handles rate limiting (429), auth failures (401), and HTTP errors

## Campus Coach Integration
**Source**: `lambda_functions/webhooks/campus_coach_invoker.py`, `lambda_functions/processing/modules_processing.py`

- **Daily extraction**: EventBridge triggers `CampusCoachInvoker` Lambda at 6 AM Paris time (disabled by default, enabled via API)
- **AgentCore invocation**: Fires asynchronously — invokes `campus_coach` AgentCore agent with action `extract_sessions`
- **Agent workflow**: Agent retrieves credentials from Secrets Manager, uses Browser Tool to navigate `app.campus.coach/auth`, login, scroll dashboard, extract 5 weekly sessions, parse JSON, save to DynamoDB (`coaching_sessions` table)
- **Session matching at generation time**: `_apply_campus_coach_processing()` retrieves recent sessions (last 14 days, status "À faire", max 6) from DynamoDB for the content agent to intelligently match against activity data
- **Matching signals**: Activity title keywords, distance tolerance ±30%, duration tolerance ±40%, lap structure, pace zones

## Enduraw Module Integration
**Source**: `lambda_functions/webhooks/activity_processor.py`, `lambda_functions/processing/workout_analysis.py`

- When Enduraw module is enabled in user config, the Activity Processor delays processing by 2 minutes via SQS `DelaySeconds=120`
- After delay, `content_generator.py` extracts Enduraw Report from the activity description using regex (Enduraw third-party app appends enhanced metrics to Strava description)
- Extracts: adjusted pace, wind impact (speed + cost), elevation impact (avg % + cost)
- Unicode math bold digits (`𝟬-𝟵`) translated to regular digits for parsing

## Intervals.icu Integration
**Source**: `lambda_functions/processing/activity_fetcher.py`

- Fetched conditionally when `modules_config.intervals_icu.enabled == True`
- **Wellness day-of**: CTL (fitness), ATL (fatigue), Form (TSB), ramp rate, HRV, resting HR, VO2max, sleep data
- **Wellness J-1 fallback**: If day-of HRV/restingHR/VO2max is null, falls back to previous day (sleep NOT falling back — would show wrong night)
- **30-day wellness range**: Computes trends for VO2max, HRV, resting HR, CTL, sleep duration, sleep quality (direction: up/down/stable based on 7-day comparison)
- **Activity decoupling**: Fetches aerobic decoupling percentage from activity endpoint
- All data passed to content agent for narrative integration

## User Configuration Management
**Source**: `lambda_functions/api/configuration_api.py`, `user_preferences_api.py`

- **OAuth management**: GET/POST/DELETE `/config/oauth` — initiate OAuth flow, exchange code for tokens, disconnect
- **Module management**: GET/POST `/config/modules`, PUT/DELETE `/config/modules/{module_id}` — list, enable, configure, disable modules (campus_coach, enduraw, intervals_icu)
- **Enhancement control**: GET/POST `/config/enhancement` — pause/resume activity enhancement (sets `enhancement_enabled` flag)
- **User preferences**: GET/POST `/preferences` — age_range, sport_approach, content_length, content_tone, emoji_usage, technical_detail, content_language, interests, pace_zones

## Content Quality Feedback Loop
**Source**: `lambda_functions/support/feedback_analyzer.py`

- Runs nightly at 3 AM UTC via EventBridge schedule
- Scans activities table for recently processed activities
- Fetches current Strava descriptions via OAuth token (with automatic refresh)
- Compares current description against `enhanced_description` stored in DynamoDB
- If user modified the description (`description_modified=True`), computes similarity score and writes feedback diff to AgentCore Memory
- Memory events processed by UserPreferenceStrategy to extract learned preferences

## Infinite Loop Prevention
**Source**: `lambda_functions/webhooks/activity_processor.py` (`should_skip_processing`)

- **Completed activities**: Skip if `processing_status == 'completed'`
- **Currently processing**: Skip if `processing_status == 'processing'`
- **Enduraw wait state**: Skip if `processing_status == 'waiting_enduraw'` (unless `enduraw_waited=True`)
- **Update webhooks**: Extra restrictions — skip if ever processed successfully; skip if failed within last 1 hour
- **New activities**: Always process if no DynamoDB record exists

## Activity Deduplication and Cooldown
- SQS message deduplication via activity status checks in DynamoDB before starting Step Functions
- 1-hour cooldown for failed activities on update webhooks prevents rapid retry storms
- `reserved_concurrent_executions=5` on Activity Processor Lambda + `max_concurrency=5` on SQS event source prevents overwhelming Step Functions
