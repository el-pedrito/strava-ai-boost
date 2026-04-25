> ⚠️ **Early Access**: Behavior documentation is in early access. Please review critically.

# Decision Logic

> See also: [Business Logic](business-logic.md) | [Workflows](workflows.md) | [Error Handling](error-handling.md)

## Should Activity Be Enhanced?

**Source**: `webhook_handler.py` → `activity_processor.py`

```
Webhook received
    │
    ├── Is httpMethod == POST?
    │       ├── No → Return 405 (Method Not Allowed)
    │       └── Yes ↓
    │
    ├── Is webhook signature valid? (HMAC-SHA1)
    │       ├── No → Return 401 (Invalid signature)
    │       └── Yes ↓
    │
    ├── Is webhook data valid? (object_type, object_id, aspect_type, owner_id)
    │       ├── No → Return 400 (Invalid webhook data)
    │       └── Yes ↓
    │
    ├── Is enhancement paused for this user? (user_config_table → enhancement_enabled)
    │       ├── Yes → Return 200 (acknowledged_paused, no processing)
    │       └── No ↓
    │
    ├── Is object_type == 'activity' AND aspect_type in ['create', 'update']?
    │       ├── No → Return 200 (acknowledged, ignored)
    │       └── Yes → Send to SQS queue
    │
    ╔═══ SQS Consumer (Activity Processor) ═══╗
    │
    ├── Does activity exist in DynamoDB?
    │       ├── No → Process (new activity)
    │       └── Yes ↓
    │
    ├── Is processing_status == 'completed'?
    │       ├── Yes → SKIP (already done)
    │       └── No ↓
    │
    ├── Is processing_status == 'processing'?
    │       ├── Yes → SKIP (concurrent processing)
    │       └── No ↓
    │
    ├── Is processing_status == 'waiting_enduraw'?
    │       ├── Yes AND enduraw_waited == False → SKIP
    │       ├── Yes AND enduraw_waited == True → PROCESS (delay completed)
    │       └── No ↓
    │
    ├── Is aspect_type == 'update'?
    │       ├── Yes → Is status completed/processing? → SKIP
    │       │       → Is status failed AND updated < 1 hour ago? → SKIP
    │       └── No → PROCESS
    ╚══════════════════════════════════════════╝
```

## Enduraw Delay Decision

**Source**: `activity_processor.py`

```
User configuration loaded for user_id
    │
    ├── Is Enduraw module enabled? (modules_config.enduraw.enabled)
    │       ├── No → Proceed to Step Functions immediately
    │       └── Yes ↓
    │
    ├── Has Enduraw wait already been done? (message_body.enduraw_waited)
    │       ├── Yes → Proceed to Step Functions (delay completed)
    │       └── No ↓
    │
    └── Set status to 'waiting_enduraw'
        Set enduraw_waited = True in message body
        Re-queue to SQS with DelaySeconds=120 (2 minutes)
        Return success (original message deleted)
```

## Content Generation: AgentCore Agent Selection

**Source**: `content_generator.py`, `content_agent.py`

```
Content generation requested
    │
    ├── Is CONTENT_GENERATION_AGENT_ARN configured?
    │       ├── No → Raise ValueError (agent not configured)
    │       └── Yes ↓
    │
    ├── Initialize AgentCore client (bedrock-agentcore or bedrock-agent-runtime)
    │
    ├── Is BEDROCK_AGENTCORE_MEMORY_ID configured?
    │       ├── Yes → Retrieve user preferences via RetrieveMemoryRecords (semantic search)
    │       │         Append preferences to system prompt
    │       └── No → Use base system prompt only
    │
    ├── Validate user input with Guardrail (if GUARDRAIL_ENABLED)
    │       ├── Title blocked → Return safe fallback content
    │       ├── Description blocked → Return safe fallback content
    │       └── Both passed → Continue with validated content
    │
    ├── Build complete prompt with:
    │       - User's original title + description (validated)
    │       - Activity data (type, distance, duration, HR, pace, cadence, power)
    │       - Athlete stats + profile
    │       - Laps data (formatted)
    │       - Workout classification
    │       - Campus Coach sessions
    │       - Enduraw data
    │       - Intervals.icu data (fitness/fatigue context + trends)
    │       - Style instructions (from user preferences)
    │       - Profile context (age, interests, sport approach)
    │
    └── Invoke AgentCore agent → Parse JSON response → Enforce preferences → Return
```

## Module Enablement Decisions

**Source**: `modules_processing.py`, `configuration_api.py`

```
For each registered module in module_registry:
    │
    ├── Is module_id in user's modules_config?
    │       ├── No → Module not active
    │       └── Yes ↓
    │
    ├── Is config.enabled == True?
    │       ├── No → Module not active
    │       └── Yes → Module IS active
    │
    ├── Campus Coach specific:
    │       └── When enabled → Enable EventBridge rule for daily extraction
    │           When disabled → Disable EventBridge rule
    │
    ├── Enduraw specific:
    │       └── When enabled → Activity Processor adds 2-min SQS delay
    │           When disabled → No delay
    │
    └── Intervals.icu specific:
            └── When enabled → Activity Fetcher calls Intervals.icu API
                When disabled → API calls skipped
```

## Content Generation Parameter Selection

**Source**: `content_agent.py` (`build_preference_instructions`, `resolve_adaptive_content_length`)

```
User preferences loaded from user_config_table.user_preferences
    │
    ├── TONE: Maps to generation style
    │       - "technical & analytical" → Data-driven, precise metrics
    │       - "motivational & energetic" → Exclamation marks, action verbs
    │       - "casual & friendly" → Conversational, contractions
    │       - "humorous & fun" → Light humor, playful metaphors
    │       - "authentic & personal" → Genuine insights, introspective
    │
    ├── EMOJI: Maps to emoji count limit
    │       - "none" → 0 emojis
    │       - "minimal" → max 2
    │       - "moderate" → max 5
    │       - "enthusiastic" → max 10
    │
    ├── CONTENT LENGTH: Maps to character limit
    │       - "short" → max 300 chars
    │       - "medium" → max 800 chars
    │       - "detailed" → max 1500 chars
    │       - "adaptive" → Resolved based on:
    │           - Intervals detected (≥5 laps, >30s/km variation) + advanced profile → detailed
    │           - Long activity (>60min) or advanced technical_detail → detailed
    │           - Short activity (<30min) without intervals → medium
    │           - Default → medium
    │
    ├── LANGUAGE: Generate ALL content in specified language
    │       - "french" (default) → No override needed
    │       - Any other → Language override prepended to prompt
    │
    └── TECHNICAL DETAIL: Controls analysis depth
            - "basic" → Key metrics only
            - "intermediate" → Key metrics with brief insights
            - "advanced" → Full lap-by-lap analysis with HR zones
```

## Workout Classification Decision

**Source**: `workout_analysis.py` (`classify_workout_from_laps`)

```
Laps data from device
    │
    ├── Less than 2 laps? → type: 'unknown'
    │
    ├── Extract paces (min/km) from all laps
    │   Calculate: avg_pace, pace_std, pace_range
    │
    ├── pace_std > 0.6 AND pace_range > 2.0?
    │       └── type: 'intervals' (Fractionné / Intervalles)
    │
    ├── pace_std > 0.40?
    │       ├── First third faster than last third by >0.5 min/km?
    │       │       └── type: 'progression' (Negative Split)
    │       └── Otherwise → type: 'fartlek'
    │
    └── Steady pace (pace_std ≤ 0.40):
            ├── User has pace_zones configured?
            │       └── Match avg_pace against zones → specific type (recovery, ef, tempo, threshold, marathon pace, etc.)
            └── No pace zones → type: 'steady' (Sortie Régulière)
```

## Error Retry vs DLQ Routing

**Source**: `activity_processor.py`, `webhook_processing_stack.py`

```
SQS message processing
    │
    ├── Lambda processes message successfully → Message deleted from SQS
    │
    ├── Lambda raises exception:
    │       ├── Reported as batch item failure → Message remains in SQS
    │       ├── SQS retries after visibility timeout (35 min)
    │       └── After 3 failed attempts → Message moves to DLQ
    │
    ├── Step Functions execution fails:
    │       ├── EventBridge rule detects FAILED/TIMED_OUT/ABORTED
    │       ├── StepFunctionsErrorHandler Lambda triggered
    │       ├── Updates activity status to 'failed' in DynamoDB
    │       └── Sends error details to DLQ
    │
    └── DLQ message persists for 14 days for manual investigation
        CloudWatch alarm fires when DLQ has ≥ 1 message
```
