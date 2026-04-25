# Data Models

> See also: [Interfaces](interfaces.md) | [Components](../architecture/components.md) | [Database Patterns](../specialized/database-patterns.md)

## DynamoDB Table Schemas

### strava-ai-boost-activities
| Attribute | Type | Key | Description |
|---|---|---|---|
| `activity_id` | String | PK | Strava activity ID |
| `processing_status` | String | GSI PK | pending/fetched/processing/waiting_enduraw/completed/failed |
| `created_at` | String (ISO) | GSI SK | Creation timestamp |
| `updated_at` | String (ISO) | — | Last update timestamp |
| `original_name` | String | — | Original Strava activity title |
| `original_description` | String | — | Original Strava description |
| `activity_type` | String | — | Strava activity type (Run, Ride, etc.) |
| `distance` | Number | — | Distance in meters |
| `moving_time` | Number | — | Moving time in seconds |
| `total_elevation_gain` | Number | — | Elevation in meters |
| `start_date` | String (ISO) | — | Activity start date |
| `activity_data_json` | String | — | Complete Strava activity JSON |
| `athlete_stats_json` | String | — | Athlete statistics JSON |
| `athlete_profile_json` | String | — | Athlete profile JSON |
| `intervals_icu_json` | String | — | Intervals.icu data JSON |
| `laps_json` | String | — | Device laps data JSON |
| `enhanced_title` | String | — | AI-generated title |
| `enhanced_description` | String | — | AI-generated description |
| `generation_metadata` | Map | — | Style elements, confidence, modules, analysis type |
| `execution_arn` | String | — | Step Functions execution ARN |
| `error_message` | String | — | Error details (on failure) |
| `expires_at` | Number | TTL | Unix timestamp (365 days from creation) |
| `location_city` | String | — | Activity location city |
| `location_country` | String | — | Activity location country |
| `start_latitude` | Number | — | Start GPS latitude |
| `start_longitude` | Number | — | Start GPS longitude |
| `description_modified` | Boolean | — | User modified AI content |
| `similarity_score` | Number | — | Current vs generated similarity |
| `feedback_analyzed` | Boolean | — | Feedback analysis complete |

### strava-ai-boost-user-configuration
| Attribute | Type | Key | Description |
|---|---|---|---|
| `user_id` | String | PK | Strava athlete ID |
| `enhancement_enabled` | Boolean | — | Enhancement active/paused |
| `strava_connected` | Boolean | — | OAuth tokens available |
| `modules_config` | Map | — | Module configurations (see below) |
| `user_preferences` | Map | — | User preferences (see below) |
| `created_at` | String (ISO) | — | Record creation timestamp |

**modules_config structure:**
```json
{
  "campus_coach": {"enabled": false, "configured": false},
  "enduraw": {"enabled": false},
  "intervals_icu": {"enabled": false}
}
```

**user_preferences structure:**
```json
{
  "age_range": "26-35",
  "sport_approach": "health & wellness",
  "content_length": "medium",
  "content_tone": "motivational & energetic",
  "emoji_usage": "moderate",
  "technical_detail": "intermediate",
  "content_language": "french",
  "interests": ["music", "technology"],
  "pace_zones": {
    "recovery": {"min": "6:30", "max": "7:30"},
    "ef": {"min": "6:01", "max": "6:31"},
    ...
  }
}
```

### strava-ai-boost-campus-coaching-sessions
| Attribute | Type | Key | Description |
|---|---|---|---|
| `session_date` | String | PK | Format: `week-{week_number}` |
| `session_id` | String | SK | Format: `{week_number}-{session_number}` |
| `week_number` | String | GSI PK | Week identifier (e.g., "15-12") |
| `session_number` | String | — | Position in week (e.g., "1/5") |
| `title` | String | — | Session title |
| `workout` | String | — | "ROUTE" or "RENFORCEMENT" |
| `status` | String | — | "À faire" or "Complétée" |
| `targetedMetrics` | Map | — | target_distance_km, target_duration_min, difficulty |
| `intervals` | List | — | Training intervals with pace targets |
| `coach_advice` | Map | — | main_advice text |
| `description` | String | — | Session description |
| `objectives` | List | — | Training goals |
| `updated_at` | String (ISO) | — | Last update timestamp |

## Pydantic Models (src/modules/base_module.py)

### ModuleConfig
```python
class ModuleConfig(BaseModel):
    module_id: str          # Validated: alphanumeric + underscores/hyphens
    enabled: bool = False
    credentials: Optional[Dict[str, str]] = None
    settings: Dict[str, Any] = {}
    priority: int = 100     # 0-1000, lower = higher priority
    timeout_seconds: int = 30
    retry_attempts: int = 3
```

### ModuleInsight
```python
class ModuleInsight(BaseModel):
    module_id: str
    insights: Dict[str, Any]
    confidence: float       # 0.0-1.0
    metadata: Dict[str, Any] = {}
    processing_time_ms: Optional[int] = None
    error_message: Optional[str] = None
```

## TypeScript Types (frontend/src/types/index.ts)

### Core Types
- `DashboardStats`: `{total_activities, success_rate, completed_activities, failed_activities}`
- `Activity`: `{name, date, processing_time, status, modules_used[], activity_type?, confidence?, description_modified?, similarity_score?, feedback_analyzed?, generated_at?}`
- `QualityStats`: `{avg_confidence, edit_rate, avg_similarity, total_analyzed, total_feedback}`

### Configuration Types
- `OAuthStatus`: `{connected, configured, obtained_at?, last_refreshed?, scopes?, message?}`
- `StravaAppStatus`: `{configured, client_id?, redirect_uri?, message?}`
- `ModuleConfig`: `{enabled, configured, description?, status?, last_extraction?, wait_time?}`
- `ModulesMap`: `{campus_coach, enduraw, intervals_icu}` (each is ModuleConfig)
- `EnhancementStatus`: `{enhancement_enabled, enhancement_paused_at, status}`
- `SystemStatus`: `{strava_connected, agentcore_status, enhancement_enabled, enhancement_status}`

### User Types
- `UserPreferences`: `{age_range, sport_approach, content_length, content_tone, emoji_usage, technical_detail, content_language, interests[], pace_zones?}`
- `PaceZones`: Record of zone names to `PaceZone {min, max}` (mm:ss format)
- `FlashMessage`: `{id, type, content, dismissible}`

## LLM Configuration (src/config/llm_config.py)

```python
class LLMConfig:
    bedrock_model_id: str   # Default: "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
    anthropic_version: str  # Default: "bedrock-2023-05-31"
    max_tokens: int         # Default: 2000
    temperature: float      # Default: 0.7
    aws_region: str         # Default: "eu-west-1"
```
