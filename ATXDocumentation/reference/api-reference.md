# API Reference / Module Organization

> See also: [Interfaces](interfaces.md) | [Data Models](data-models.md) | [Program Structure](program-structure.md)

## Module Registry System

### How It Works
The `src/modules/` package implements a plugin architecture for integrating external data sources:

1. **BaseModule** (`base_module.py`): Abstract base class defining the module lifecycle interface — `initialize()`, `analyze_activity()`, `configure()`, `validate_configuration()`, `shutdown()`
2. **ModuleRegistry** (`base_module.py`): Singleton registry that manages module class registration, instance creation, and lifecycle. Provides `register_module()`, `get_available_modules()`, `create_module_instance()`, `get_module_info()`
3. **Auto-registration** (`registry.py`): On import, `register_all_modules()` registers all concrete module classes with the global `module_registry` instance
4. **Runtime usage** (`modules_processing.py`): `get_active_modules()` queries the registry for modules enabled in the user's config; `apply_module_processing()` creates instances and calls `analyze_activity_with_timeout()`

### Registered Modules
| Module ID | Class | Status |
|---|---|---|
| `enduraw` | `EndurawModule` | Registered |
| `runna` | — | Placeholder (TODO) |
| `training_peaks` | — | Placeholder (TODO) |

### Module Data Flow
```
User Config (DynamoDB) → get_active_modules() → module_registry.create_module_instance()
    → module.analyze_activity_with_timeout(activity_data, streams_data)
    → ModuleInsight {insights, confidence, metadata, processing_time_ms}
    → Passed to content generation agent as context
```

## Lambda Function Packages

### api/ (4 handlers)
Handles all REST API endpoints for the local web interface. All functions use `webhook_lambda_role` from Core stack (shared role with DynamoDB, Secrets Manager, SQS, and Step Functions read permissions).

- **configuration_api.py**: Routes by `resource` path — `/config/strava`, `/config/oauth`, `/config/modules`, `/config/enhancement`. Manages Strava app setup, OAuth token exchange, module enable/disable (with EventBridge rule toggle for Campus Coach), and enhancement pause/resume.
- **dashboard_api.py**: Routes by `resource` — `/dashboard/stats`, `/dashboard/activities`, `/dashboard/system`. Queries DynamoDB for activity counts, recent activities with processing details, and system health including SQS queue depth and Step Functions execution status.
- **user_preferences_api.py**: GET reads and POST writes to `user_config_table.user_preferences`. Supports all preference fields including nested pace_zones.
- **agentcore_health_check.py**: Calls `bedrock-agentcore:GetAgentRuntime` for configured agent ARNs. Returns health status (healthy/not_configured/error).

### processing/ (5 files — 3 Step Functions handlers + 2 utilities)
The content generation pipeline executed by Step Functions.

- **activity_fetcher.py** (handler): Step Functions task 1. Fetches Strava activity, laps, athlete stats, athlete profile. Conditionally fetches Intervals.icu data. Stores everything in DynamoDB as JSON strings.
- **content_generator.py** (handler): Step Functions task 2. Retrieves data from DynamoDB. Discovers active modules. Invokes AgentCore content agent. Parses response, enforces preferences, stores enhanced content.
- **strava_updater.py** (handler): Step Functions task 3. PUTs enhanced title and description to Strava API. Marks activity as completed.
- **modules_processing.py** (utility): Module discovery and processing. Uses module registry to find active modules and apply per-module analysis (Campus Coach session matching, Enduraw data extraction).
- **workout_analysis.py** (utility): Classifies workout type from device laps (intervals, fartlek, progression, steady, specific pace zones). Extracts Enduraw Report from activity description via regex.

### webhooks/ (3 handlers)
Event-driven handlers for Strava webhooks and scheduled tasks.

- **webhook_handler.py**: API Gateway integration for Strava webhooks. Handles GET (subscription verification) and POST (event notifications). Validates HMAC-SHA1 signatures, checks enhancement status, queues to SQS.
- **activity_processor.py**: SQS event source consumer. Implements skip logic (infinite loop prevention), Enduraw delay, Step Functions workflow launch, batch item failure reporting.
- **campus_coach_invoker.py**: Invokes Campus Coach AgentCore agent asynchronously for daily session extraction.

### shared/ (4 utility modules)
Common utilities available to all Lambda functions via import.

- **logger.py**: AWS Lambda Powertools Logger + Metrics wrappers. Exports `get_logger()`, `metrics`, `MetricUnit`.
- **responses.py**: CORS headers (read/write variants), `create_success_response()`, `create_error_response()`, Decimal serialization helper.
- **env_validation.py**: `validate_env_vars(required, context)` — raises EnvironmentError if required vars missing.
- **strava_oauth.py**: `refresh_access_token(refresh_token, client_id, client_secret)` — reusable OAuth token refresh.

### support/ (2 handlers)
Background and error-handling functions.

- **feedback_analyzer.py**: EventBridge-scheduled nightly job. Compares current Strava descriptions against generated ones. Writes feedback diffs to AgentCore Memory.
- **stepfunctions_error_handler.py**: EventBridge-triggered on Step Functions failures. Updates DynamoDB status to failed, sends error details to DLQ.

## CDK Stack Modules (stacks/)
Each stack file is a self-contained CDK Stack subclass with private methods for resource creation:

| Stack | Key Methods |
|---|---|
| `core_infrastructure_stack.py` | `_create_dynamodb_tables`, `_create_lambda_layer`, `_create_iam_roles`, `_create_secrets`, `_add_secrets_permissions` |
| `security_stack.py` | `_create_guardrail`, `_create_memory_execution_role`, `_enable_agentcore_observability` |
| `content_generation_stack.py` | `_get_base_environment_variables`, `_create_lambda_functions`, `_create_step_functions_workflow` |
| `webhook_processing_stack.py` | `_create_sqs_queues`, `_create_lambda_functions`, `_create_stepfunctions_error_handler`, `_create_cloudwatch_alarms`, `_create_webhook_api` |
| `api_gateway_stack.py` | `_create_lambda_functions`, `_create_api_gateway` |
| `monitoring_stack.py` | `_create_sns_topic`, `_create_alarms`, `_create_dashboard` |
| `feedback_loop_stack.py` | `_load_memory_id_from_env` (constructor creates all resources inline) |
| `env_loader.py` | `load_env_agentcore`, `load_agentcore_agent_arns`, `load_agentcore_memory_id` |
