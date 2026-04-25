# Interfaces

> See also: [Program Structure](program-structure.md) | [Data Models](data-models.md) | [API Reference](api-reference.md)

## API Gateway Endpoints

### Local Interface API (API Key Required)

| Method | Path | Lambda | Description |
|---|---|---|---|
| GET | `/config/strava` | ConfigurationAPI | Check Strava app configuration status |
| GET | `/config/oauth` | ConfigurationAPI | Check OAuth connection status |
| POST | `/config/oauth` | ConfigurationAPI | Exchange authorization code for tokens |
| DELETE | `/config/oauth` | ConfigurationAPI | Disconnect Strava (delete tokens) |
| GET | `/config/modules` | ConfigurationAPI | List module configurations |
| POST | `/config/modules` | ConfigurationAPI | Update module configuration |
| PUT | `/config/modules/{module_id}` | ConfigurationAPI | Enable/configure specific module |
| DELETE | `/config/modules/{module_id}` | ConfigurationAPI | Disable specific module |
| GET | `/config/enhancement` | ConfigurationAPI | Get enhancement status (active/paused) |
| POST | `/config/enhancement` | ConfigurationAPI | Toggle enhancement (pause/resume) |
| GET | `/dashboard/stats` | DashboardAPI | Activity statistics (totals, success rate) |
| GET | `/dashboard/activities` | DashboardAPI | Recent activity list with processing details |
| GET | `/dashboard/system` | DashboardAPI | System health (Strava, AgentCore, queues) |
| GET | `/preferences` | UserPreferencesAPI | Get user preferences |
| POST | `/preferences` | UserPreferencesAPI | Update user preferences |
| GET | `/health/agentcore` | AgentCoreHealthCheck | AgentCore agent runtime health |
| GET | `/test/strava-connection` | ConfigurationAPI | Test Strava API connection |

### Webhook API (Public — No Auth)

| Method | Path | Lambda | Description |
|---|---|---|---|
| GET | `/webhook` | WebhookHandler | Strava subscription verification |
| POST | `/webhook` | WebhookHandler | Strava event notifications |

## Lambda Handler Signatures

All handlers follow `handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]`.

| Handler | Event Source | Key Input Fields | Key Output Fields |
|---|---|---|---|
| `webhooks.webhook_handler.handler` | API Gateway | `httpMethod`, `queryStringParameters`, `body`, `headers` | `statusCode`, `body` (JSON) |
| `webhooks.activity_processor.handler` | SQS | `Records[].body` (JSON: activity_id, user_id, webhook_data) | `batchItemFailures` |
| `webhooks.campus_coach_invoker.handler` | EventBridge / Lambda | `action`, `user_id` | `statusCode`, `session_id`, `agent_arn` |
| `processing.activity_fetcher.handler` | Step Functions | `activity_id`, `user_id` | `statusCode`, `activity_id`, `data_stored_in_dynamodb` |
| `processing.content_generator.handler` | Step Functions | `activity_id`, `user_id` | `statusCode`, `enhanced_content`, `modules_applied` |
| `processing.strava_updater.handler` | Step Functions | `activity_id`, `user_id`, `enhanced_content` | `statusCode`, `update_result` |
| `api.configuration_api.handler` | API Gateway | `httpMethod`, `resource`, `pathParameters`, `body` | `statusCode`, `headers`, `body` |
| `api.dashboard_api.handler` | API Gateway | `httpMethod`, `resource` | `statusCode`, `headers`, `body` |
| `api.user_preferences_api.handler` | API Gateway | `httpMethod`, `body` | `statusCode`, `headers`, `body` |
| `api.agentcore_health_check.handler` | API Gateway | — | `statusCode`, `headers`, `body` |
| `support.feedback_analyzer.lambda_handler` | EventBridge | — (scheduled) | — |
| `support.stepfunctions_error_handler.handler` | EventBridge | `detail.executionArn`, `detail.status` | — |

## AgentCore Agent Interfaces

### Content Generation Agent (`content_agent.py`)
- **Entrypoint**: `@app.entrypoint def invoke(payload, context=None)`
- **Input payload**: `{action, activity_data, user_id, user_profile, active_modules, campus_coach_session, enduraw_data, intervals_icu_data, laps_data, athlete_stats, athlete_profile, workout_classification, classification_instruction, use_memory, personalization}`
- **Output**: `{response: str (JSON), user_id, activity_id, model_id, agentcore_runtime, prompt_source}`

### Campus Coach Agent (`campus_coach_agent.py`)
- **Entrypoint**: `@app.entrypoint async def invoke(payload, context=None)`
- **Input payload**: `{action, user_id, region}`
- **Output**: `{success: bool, message: str}`
- **Async task**: `scrape_campus_sessions(region, username, password)` → `{success, sessions, saved_count, message}`

## Module Interface (BaseModule ABC)

```python
class BaseModule(ABC):
    async def initialize(self) -> bool
    async def shutdown(self) -> None
    async def analyze_activity_with_timeout(activity_data, streams_data) -> ModuleInsight
    @abstractmethod async def analyze_activity(activity_data, streams_data) -> ModuleInsight
    @abstractmethod async def configure(credentials: Dict) -> bool
    @abstractmethod async def validate_configuration() -> bool
    def is_enabled() -> bool
    def enable() / disable()
    def get_status() -> Dict
    def get_module_info() -> Dict
    def get_required_credentials() -> List[str]
```

## Frontend API Client

```typescript
// frontend/src/api/client.ts
export const api = {
  get: <T>(path: string) => Promise<T>,
  post: <T>(path: string, body?: unknown) => Promise<T>,
  delete: <T>(path: string) => Promise<T>,
};
// All requests include x-api-key header from config
```

## Strava OAuth Interface

```python
# shared/strava_oauth.py
def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    http_session: requests.Session | None = None,
) -> Optional[Dict[str, Any]]
# Returns: {access_token, refresh_token, expires_at, token_type, ...}
```
