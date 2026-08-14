# AGENTS.md - AI Assistant Context for Strava AI Boost

**Version:** 4.2.0
**Last Updated:** 2026-07-17
**Purpose:** Comprehensive context for AI coding assistants

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Directory Structure](#directory-structure)
3. [Development Patterns](#development-patterns)
4. [Testing Guidelines](#testing-guidelines)
5. [Module Development](#module-development)
6. [AgentCore Integration](#agentcore-integration)
7. [Deployment Procedures](#deployment-procedures)
8. [Common Tasks](#common-tasks)
9. [Troubleshooting](#troubleshooting)

---

## Project Overview

Strava AI Boost is a **serverless AWS application** that automatically enhances Strava activity titles and descriptions using AI. The system uses a **React + TypeScript frontend built on a custom Tailwind v4 design system** (semantic CSS tokens, dark mode, cva component primitives — migrated off Cloudscape) hosted on CloudFront (with Cognito authentication) that calls API Gateway directly.

### Key Statistics
- **~18,000 LOC** in core components
- **18 Lambda functions** (API, processing, webhooks, support, voice — role-based packages)
- **3 AgentCore Runtimes** — `content_gen`, `strava_ai_boost_coach` (coach), `coach_chat` (agentic conversational coach): 2 agent definitions in `src/agents/` + 1 chat runtime in `src/coach_chat/`, sharing a single AgentCore Memory (`content_gen_mem`, 3 strategies)
- **8 CDK stacks**
- **717 tests** (621 backend unit + 43 regression + 53 frontend) + on-demand prompt regression harness (deterministic V1 + managed AgentCore Evaluations V2)
- **Centralized LLM registry** — all Bedrock model IDs come from `src/config/llm_config.py` (mirrored in `lambda_functions/shared/llm_models.py` for Lambda bundling); anti-drift sync test
- **Python 3.12** runtime, **React 19 + TypeScript + Vite** frontend
- **Cognito authentication** (JWT, custom:strava_id attribute, no self-registration)
- **CloudFront + S3** frontend hosting (OAC)
- **2 DynamoDB GSIs** (ProcessingStatusIndex, UserActivitiesIndex) — all queries, no scans
- **i18n** FR/EN with react-i18next

### Architecture Pattern
**Event-Driven Serverless (Parallel Execution):**
```
Strava Webhook → SQS → Step Functions → Activity Fetcher →
  ├── Content Generator → AgentCore content_gen agent
  ├── Coach Generator → AgentCore coach_agent
  └── Assembly Lambda → Strava Update
```

**Data Pipeline:**
```
Activity Fetcher: Strava API → activity data + laps (GET /activities/{id}/laps) → DynamoDB
Content Generator: DynamoDB → classify workout from laps → build prompt with formatted laps → AgentCore agent → store
Coach Generator: DynamoDB → athlete profile + zones + PRs + historical context (4 weeks, GSI query) → AgentCore coach_agent → coaching feedback
Assembly Lambda: Merge content + coach outputs → update Strava + store results
Campus Coach API Sync: REST login + GET /smart-training → structured sessions (intervals, targets) → DynamoDB (is_current_week/is_future flags)
Campus Coach Context: Sessions stored in DynamoDB → scored deterministically against laps in modules_processing.py → best match passed to content_gen agent
```

**Conversational Coach (agentic):**
```
Dedicated AgentCore Runtime `coach_chat` (FastAPI + Strands, AGUI protocol):
  browser POSTs AG-UI RunAgentInput straight to the data plane
  (bedrock-agentcore.{region}.amazonaws.com/runtimes/{arn}/invocations) — CORS *,
  no proxy. Auth: customJWT (Cognito ID token as Bearer); user_id from the
  custom:strava_id claim. Agent runs 5 @tool loops server-side
  (query_activities, get_campus_plan, get_pace_zones, get_intervals_metrics,
  get_coach_observations) and
  streams RUN_STARTED / TOOL_CALL_* / TEXT_MESSAGE_* / RUN_FINISHED.
  Sole transport — no buffered fallback; the UI shows an error on failure.
  Source: src/coach_chat/ (deployed via scripts/deploy_agentcore_agents.sh).
```

The per-activity coach feedback pipeline (`coach_generator.py`) builds athlete
context via `shared/coach_context.py` (`build_user_context` + `format_weekly_breakdown`
for real per-ISO-week run/km/strength counts — prevents the coach from hallucinating
weekly session totals). The conversational agent instead fetches data on demand
through its tools (chantier A1), so it is not limited to a fixed context dump.

---

## Directory Structure

```
strava-ai-boost/
├── scripts/                    # Deployment and maintenance
│   ├── deploy.sh              # Main CDK deployment
│   ├── deploy_agentcore_agents.sh    # Injects BEDROCK_MODEL_ID from the central registry
│   ├── configure_agentcore_integration.sh
│   ├── create_agentcore_memories.sh
│   ├── configure_memory_strategy.py  # Configures the 3 memory strategies (idempotent)
│   ├── run_prompt_regression.py      # V1 deterministic prompt regression (deployed runtime, ~0.20$/run)
│   ├── run_managed_evals.py          # V2 managed AgentCore Evaluations (LLM-as-a-Judge, ~1.2$/run)
│   ├── build_eval_dataset.py         # Fixtures → AgentCore Evaluations dataset
│   ├── create_managed_evaluators.py  # Custom judge evaluators (idempotent)
│   ├── configure_strava_webhook.sh
│   ├── setup_local_env.sh
│   ├── validate_deployment.sh
│   ├── cleanup_strava_webhook.sh
│   ├── reprocess_dlq.sh
│   ├── uninstall.sh
│   └── verify_uninstall.sh
│
├── stacks/                     # CDK infrastructure (8 stacks)
│   ├── core_infrastructure_stack.py    # DynamoDB, Secrets, Layer
│   ├── security_stack.py               # Guardrails, Memory Execution Role, Observability
│   ├── webhook_processing_stack.py     # Webhook, SQS, Processor
│   ├── content_generation_stack.py     # Step Functions, Lambdas
│   ├── voice_debrief_stack.py          # Voice debrief (Polly, S3 audio, audio API)
│   ├── api_gateway_stack.py            # REST API, Cognito Authorizer, API Lambdas
# monitoring_stack.py REMOVED (overkill for personal project)
│   ├── feedback_loop_stack.py          # Feedback analyzer
│   └── frontend_hosting_stack.py       # S3, CloudFront (OAC), Cognito User Pool
│
├── lambda_functions/           # Lambda handlers (grouped by role)
│   ├── api/                            # API endpoint handlers
│   │   ├── configuration_api.py        # Config API
│   │   ├── dashboard_api.py            # Dashboard API
│   │   ├── user_preferences_api.py     # Preferences API
│   │   ├── audio_debrief_api.py        # Audio debrief API (presigned MP3 URLs)
│   │   └── agentcore_health_check.py   # Health check
│   ├── processing/                     # Content pipeline
│   │   ├── activity_fetcher.py         # Data fetcher
│   │   ├── content_generator.py        # AI content generation
│   │   ├── coach_generator.py          # AI coaching feedback generation
│   │   ├── assembly_lambda.py          # Merge content + coach → Strava update
│   │   ├── strava_updater.py           # Strava API updater
│   │   ├── voice_debrief_generator.py  # Per-activity audio debrief (Bedrock Haiku → Polly)
│   │   ├── workout_analysis.py         # Workout classification from laps, Enduraw extraction
│   │   └── modules_processing.py       # Module discovery, Campus Coach session retrieval
│   ├── webhooks/                       # Event ingestion
│   │   ├── webhook_handler.py          # Webhook receiver
│   │   ├── activity_processor.py       # SQS processor
│   │   └── campus_coach_sync.py        # Direct REST API sync (login + GET /smart-training, 9 weeks, 39 sessions)
│   ├── support/                        # Operational utilities
│   │   ├── feedback_analyzer.py        # Feedback loop
│   │   ├── weekly_synthesis.py         # Weekly training synthesis (EventBridge Sunday 20:00 UTC + on-demand, AgentCore Memory + user prefs/PRs/pace zones + Campus goal context)
│   │   ├── weekly_audio_recap.py       # Weekly audio recap (Bedrock Sonnet script → Polly Generative → MP3)
│   │   └── stepfunctions_error_handler.py  # Error handler
│   └── shared/                         # Shared utilities module
│       ├── __init__.py
│       ├── logger.py                   # Powertools Logger, Metrics, correlation IDs
│       ├── env_validation.py           # Environment variable validation
│       ├── responses.py                # Standardized API responses
│       ├── coach_context.py            # Athlete context builders + format_weekly_breakdown (chat + stream)
│       ├── campus_status.py            # Canonical Campus session status helper (sole source of truth for "is this session done")
│       ├── iso_week.py                 # Canonical ISO week label 'YYYY-Www' (never a bare week number)
│       ├── strength_exercises.py       # Canonical strength exercise vocabulary + alias resolver (extraction + Coach charts)
│       ├── llm_models.py               # Bedrock model IDs mirrored from src/config/llm_config.py
│       └── strava_oauth.py             # OAuth token management
│
├── src/
│   ├── agents/                 # AgentCore agents (2 agents)
│   │   ├── content_agent.py            # Content generation agent
│   │   ├── coach_agent.py              # Training coach agent (pipeline feedback)
│   │   └── embedded_prompts.py         # Prompt templates
│   │
│   ├── coach_chat/             # Conversational coach AgentCore Runtime (agentic)
│   │   ├── coach_chat_agent.py         # FastAPI + Strands, AGUI protocol, 5 @tool loops
│   │   ├── prompts.py                  # COACH_CHAT_SYSTEM_PROMPT (tools persona)
│   │   └── requirements.txt            # ag-ui-strands, fastapi, strands-agents (deploy-only)
│   │
│   ├── modules/  ── REMOVED (2026-07-26)
│   │   # The src/modules package (base_module / registry / enduraw_module) was
│   │   # dead code: CDK bundles only lambda_functions/, so `from modules import
│   │   # module_registry` always raised ImportError and the fallback ran. Modules
│   │   # are now config-driven in lambda_functions/processing/modules_processing.py
│   │   # (dispatched by name). Campus Coach: sessions fetched from DynamoDB and
│   │   # matched deterministically in modules_processing.py. Enduraw: metrics
│   │   # fetched in activity_fetcher.py / workout_analysis.py (no module class).
│   │   # Intervals.icu: integrated directly in activity_fetcher.py + content_agent.py.
│   │
│   └── config/                 # Configuration
│       └── llm_config.py               # LLM configuration
│
├── frontend/                   # React web application
│   ├── src/
│   │   ├── api/                        # API client + tests
│   │   ├── auth/                       # Authentication
│   │   │   ├── AuthContext.tsx         # Cognito auth context + JWT management
│   │   │   └── ProtectedRoute.tsx      # Route guard (redirects to login)
│   │   ├── components/                 # Custom design-system components + tests
│   │   ├── pages/                      # Page components (Dashboard, Config, Preferences, Quality, Coach, LoginPage)
│   │   ├── layouts/                    # Layout components (Shell, TopNav w/ Sign Out, Breadcrumbs)
│   │   ├── utils/                      # Pure utility functions + tests
│   │   ├── test/                       # Test setup (Vitest + Testing Library)
│   │   └── config.ts                   # Runtime configuration
│   ├── package.json                    # Dependencies
│   ├── eslint.config.js                # ESLint flat config (typescript-eslint + react-hooks + react-refresh)
│   └── vite.config.ts                  # Vite + Vitest configuration
│
├── tests/                      # Test suite
│   ├── unit/                           # Lambda unit tests (621 tests)
│   │   ├── conftest.py                 # Env vars for Lambda imports
│   │   ├── test_webhook_handler.py     # Validation, routing, signature
│   │   ├── test_content_generator.py   # DynamoDB, parsing, storage, strength extraction
│   │   ├── test_workout_analysis.py    # Laps classification, pace zones, Enduraw extraction
│   │   ├── test_dashboard_api.py       # Validation, routing, caching, health anomalies
│   │   ├── test_configuration_api.py   # Strava deauthorization flow
│   │   ├── test_coach_output_check.py  # Figure verifier: week-scope gate, km vs km/h, strip
│   │   ├── test_metrics_flush.py       # Anti-drift: add_metric requires @metrics.log_metrics
│   │   └── test_env_loader_memory_id.py # Synth must fail, not blank, an unreadable memory id
│   ├── regression/                     # Prompt regression harness (43 tests + live runners)
│   │   ├── fixtures/                   # 8 synthetic activities (shared by V1 + V2 evals)
│   │   ├── evaluators.py               # Deterministic criteria + BANNED_CLICHES (sync-tested vs prompt)
│   │   ├── evaluators_managed/         # Custom LLM-as-a-Judge configs (AgentCore Evaluations)
│   │   ├── test_evaluators.py          # Criteria unit tests + prompt/dataset sync
│   │   └── test_llm_registry.py        # Anti-drift: no model-id literal outside the registry
│   ├── test_cdk_infrastructure.py      # Stack tests
│   ├── test_api_gateway.py             # API tests
│   ├── test_lambda_functions.py        # Lambda tests
│   ├── test_end_to_end.py              # Integration tests
│   ├── aws_config.py                   # Test config helper
│   └── conftest.py                     # Pytest fixtures
│
├── lambda_layer/               # Shared Lambda dependencies
│   ├── build_layer.sh                  # Build script
│   └── requirements.txt                # Python packages
│
├── docs/                       # Project docs
│   ├── ROADMAP.md                     # Forward-looking roadmap
│   └── design/                        # Design specs
│
├── app.py                      # CDK application entry point
├── cdk.json                    # CDK configuration
├── requirements.txt            # CDK dependencies
└── README.md                   # User-facing documentation
```

---

## Development Patterns

### Lambda Function Structure

**Standard Pattern (with structured logging):**
```python
import boto3
import json
import os
from typing import Dict, Any
from shared.logger import get_logger, inject_correlation_id, metrics, MetricUnit

# Initialize structured logger and AWS clients outside handler
logger = get_logger(service="my-service")
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

@metrics.log_metrics  # REQUIRED whenever the handler records a metric: add_metric only
                      # buffers, and without this the EMF blob is never written and the
                      # metric never reaches CloudWatch. Pinned by tests/unit/test_metrics_flush.py.
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler with structured logging and correlation IDs."""
    inject_correlation_id(logger, event)
    metrics.add_metric(name="MyServiceCalls", unit=MetricUnit.Count, value=1)

    try:
        data = extract_data(event)
        result = process_data(data)

        logger.info("Request processed successfully", extra={"result_count": len(result)})
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }

    except ValueError as e:
        logger.warning("Invalid input", extra={"error": str(e)})
        return {'statusCode': 400, 'body': json.dumps({'error': str(e)})}
    except Exception as e:
        logger.exception("Unexpected error")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
```

**Shared Logger Module (`lambda_functions/shared/logger.py`):**
```python
from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit

METRICS_NAMESPACE = "StravaAIBoost"

def get_logger(service: str = "strava-ai-boost") -> Logger:
    return Logger(service=service, log_uncaught_exceptions=True)

def inject_correlation_id(logger: Logger, event: Dict[str, Any]) -> None:
    request_id = (event.get("requestContext") or {}).get("requestId")
    if request_id:
        logger.set_correlation_id(request_id)

def get_metrics(service: str = "strava-ai-boost") -> Metrics:
    return Metrics(namespace=METRICS_NAMESPACE, service=service)
```

### CDK Stack Structure

**Standard Pattern:**
```python
from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
)
from constructs import Construct

class MyStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Create resources
        self._create_dynamodb_tables()
        self._create_lambda_functions()
        
    def _create_dynamodb_tables(self) -> None:
        """Create DynamoDB tables."""
        self.table = dynamodb.Table(
            self, "MyTable",
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED
        )
        
    def _create_lambda_functions(self) -> None:
        """Create Lambda functions."""
        self.function = lambda_.Function(
            self, "MyFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            environment={
                "TABLE_NAME": self.table.table_name
            }
        )
        
        # Grant permissions
        self.table.grant_read_write_data(self.function)
```

### Module Development Pattern

**Standard Pattern:**
```python
from typing import Dict, Any, Optional
from src.modules.base_module import BaseModule, ModuleInsight

class MyModule(BaseModule):
    """Custom module implementation."""
    
    def __init__(self):
        super().__init__()
        self.module_id = "my_module"
        self.name = "My Module"
        
    def _initialize_module(self) -> None:
        """Initialize module resources."""
        # Setup connections, load config, etc.
        pass
        
    def configure(self, config: Dict[str, Any]) -> bool:
        """Configure module settings."""
        try:
            # Validate configuration
            self._validate_config(config)
            
            # Store configuration
            self.config = config
            
            return True
        except Exception as e:
            print(f"Configuration error: {e}")
            return False
            
    def analyze_activity(self, activity_data: Dict[str, Any]) -> Optional[ModuleInsight]:
        """Analyze activity and return insights."""
        try:
            # Perform analysis
            insights = self._perform_analysis(activity_data)
            
            # Return ModuleInsight
            return ModuleInsight(
                module_id=self.module_id,
                confidence=0.85,
                priority=5,
                insights=insights,
                metadata={}
            )
        except Exception as e:
            print(f"Analysis error: {e}")
            return None
            
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """Validate configuration."""
        # Implementation
        pass
        
    def _perform_analysis(self, activity_data: Dict[str, Any]) -> str:
        """Perform the actual analysis."""
        # Implementation
        pass
```

---

## Testing Guidelines

### Running Tests

**Lambda Unit Tests (621 tests, ~2s):**
```bash
pytest tests/unit/ -v
```

**Regression evaluators + LLM registry sync (43 tests, free, no AWS):**
```bash
pytest tests/regression/ -v
```

**Prompt regression — live, on-demand (run after changing `embedded_prompts.py` + deploying):**
```bash
# Run from the activated project venv (.venv-deploy, venv or .venv)
# V1 deterministic harness (~0.20$/run, invokes the deployed content_gen runtime)
python scripts/run_prompt_regression.py [--update-baseline]
# V2 managed AgentCore Evaluations (~1.2$/run, LLM-as-a-Judge on traces)
python scripts/run_managed_evals.py [--update-baseline]
```

**Infrastructure/Integration Tests (70 tests):**
```bash
export AWS_PROFILE=your-aws-profile
pytest tests/ -v --ignore=tests/unit/
```

**Frontend Tests (53 tests, ~4s):**
```bash
cd frontend && npm test
```

**All Backend Tests:**
```bash
pytest tests/ -v
```

**With Coverage:**
```bash
pytest tests/ --cov=lambda_functions --cov=stacks --cov=src
```

### Test Structure

**Standard Test Pattern:**
```python
import pytest
from unittest.mock import Mock, patch

class TestMyFunction:
    """Test suite for my_function."""
    
    @pytest.fixture
    def mock_dynamodb(self):
        """Mock DynamoDB resource."""
        with patch('boto3.resource') as mock:
            yield mock
            
    def test_success_case(self, mock_dynamodb):
        """Test successful execution."""
        # Arrange
        event = {'key': 'value'}
        context = Mock()
        
        # Act
        result = handler(event, context)
        
        # Assert
        assert result['statusCode'] == 200
        assert 'body' in result
        
    def test_error_case(self, mock_dynamodb):
        """Test error handling."""
        # Arrange
        event = {'invalid': 'data'}
        context = Mock()
        
        # Act
        result = handler(event, context)
        
        # Assert
        assert result['statusCode'] == 500
```

### Test Fixtures

**Unit tests:** `tests/unit/conftest.py` — Sets env vars at module level (before Lambda imports that use `os.environ['KEY']` at import time).

**Integration tests:** `tests/conftest.py` — AWS credentials and sample data fixtures.

**Frontend tests:** `frontend/src/test/setup.ts` — Vitest + @testing-library/jest-dom matchers.

### Unit Test Pattern (Lambda)

```python
"""Mock DynamoDB/SQS at the module level with unittest.mock.patch"""
from unittest.mock import patch, MagicMock

class TestMyHandler:
    @patch('api.my_module.dynamodb')
    def test_success(self, mock_dynamo):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {...}}
        mock_dynamo.Table.return_value = mock_table
        result = handler(event, None)
        assert result['statusCode'] == 200
```

---

## Module Development

### Creating a New Module

**Step 1: Create Module File**
```bash
touch src/modules/my_module.py
```

**Step 2: Implement Module Class**
```python
# src/modules/my_module.py
from src.modules.base_module import BaseModule, ModuleInsight
from typing import Dict, Any, Optional

class MyModule(BaseModule):
    def __init__(self):
        super().__init__()
        self.module_id = "my_module"
        self.name = "My Module"
        
    def get_module_info(self) -> Dict[str, Any]:
        return {
            "id": self.module_id,
            "name": self.name,
            "description": "Description of what this module does",
            "version": "1.0.0"
        }
        
    def get_required_credentials(self) -> list:
        return ["api_key", "secret"]  # Or empty list if none
        
    def _initialize_module(self) -> None:
        # Initialize resources
        pass
        
    def configure(self, config: Dict[str, Any]) -> bool:
        # Configure module
        return True
        
    def analyze_activity(self, activity_data: Dict[str, Any]) -> Optional[ModuleInsight]:
        # Analyze activity
        return ModuleInsight(
            module_id=self.module_id,
            confidence=0.8,
            priority=5,
            insights="Analysis results",
            metadata={}
        )
```

**Step 3: Register Module**
```python
# src/modules/registry.py
from src.modules.my_module import MyModule

def register_all_modules():
    registry = get_module_registry()
    registry.register_module("my_module", MyModule)
    # ... other modules
```

**Step 4: Test Module**
```python
# tests/test_my_module.py
import pytest
from src.modules.my_module import MyModule

class TestMyModule:
    def test_initialization(self):
        module = MyModule()
        assert module.module_id == "my_module"
        
    def test_analyze_activity(self):
        module = MyModule()
        result = module.analyze_activity({})
        assert result is not None
```

---

## AgentCore Integration

### Agents

**Location:** `src/agents/`

**Content Agent** (`content_agent.py`): Generate enhanced activity content with LTM memory, Claude Sonnet 4.5, Guardrails enabled, max_tokens 4096. Receives device-recorded laps (from Strava Laps API), Campus Coach sessions, Enduraw reports, and Intervals.icu data (CTL/ATL/Form/HRV/Decoupling). User profile includes personal_records, max_hr, and strength_program. Campus Coach context (current + future weeks with structured intervals) injected. Campus Coach matching is **deterministic** (scored in code via `modules_processing.py`, not by LLM). Only the best-matched session is passed to the LLM for narrative enrichment.

**Anti-AI Writing Rules** (enforced in content generation prompts):
- Em dash (—) and en dash (–) are **banned** from all generated content
- Banned cliché expressions: "la machine", "le corps se réveille", "chaque foulée", "repousser les limites", etc.
- Pierre's real writing style examples used as positive anchors in prompts
- Goal: authentic, personal voice — not generic AI-sounding text

**Campus Coach (no AgentCore agent)**: Campus Coach data comes from the direct REST API sync (`campus_coach_sync.py`). The legacy Browser Tool AgentCore agent (`campus_coach_agent.py`) and its fallback invoker Lambda were **decommissioned** (2026-07-16) — the REST sync had fully replaced them for weeks. Matching is done deterministically in `modules_processing.py`.

**Campus Coach Matching** (deterministic, `modules_processing.py`):
- Sessions scored against activity laps using: activity type, duration match, interval count, interval duration
- Candidates are scoped to the **activity's own ISO week**, read with a `Query` on the `session_date` partition key (`week-YYYY-Www`). The `is_current_week` flag is only the fallback, for an activity whose week has no synced plan. Scoping matters because the scorer discriminates weeks poorly: a real 9x1min activity still scores 0.82 against the 7x1min plan of the previous week, above the 0.5 threshold
- Score ≥ 0.5 → only that session sent to LLM, marked done in DynamoDB
- Score < 0.5 → all sessions passed for context, nothing marked done
- Already-done sessions are excluded, **except** the one already bound to the activity being processed (see `match_campus_session`)
- Both pipeline branches call the single matcher `match_campus_session()`. The coach branch uses it to receive an authoritative `campus_matched_session` signal instead of inferring the link from narrative context

**Gym activity vs planned PPG** (`_score_gym_against_ppg`): a `WeightTraining` carries no laps to score against the PPG intervals, so the activity type alone cannot tell the athlete's own program (`strength_program`: Upper A, Upper B, Rappel) from the running-specific PPG the plan prescribes. This used to return a flat `0.8`, above the threshold, so **every** gym session silently closed the Campus PPG, which hid a session still to do and inflated the week's count. It is now weighted, because no single factor is conclusive:

- base `0.30`, deliberately below `MATCH_THRESHOLD`: the default is "context only, do not close"
- `+0.55` when the athlete names it (writes "renfo campus" / "ppg" in the Strava title or description). He is the only one who knows, so this is the decisive factor
- `-0.15` when the text lists his own program's movements (tractions, low row, DC barre…)
- up to `+0.15` for closeness to `expected_duration_min`, weak corroboration

A declaration therefore wins even alongside a movement list, while movements without a declaration stay far below the threshold. Two guards: negations near the marker ("pas le renfo campus") do not count, and the declaration is read from `original_name`/`original_description` first, because the **generated** description routinely says "Séance Campus Coach" and would otherwise let our own output confirm the match on reprocessing.

**Strength session data contracts** (three invariants, break them and the tonnage lies):

1. **`sets_detail` is authoritative** — each exercise in `parsed_sets` carries
   `sets_detail: [{reps, weight_kg}]`, one entry per set actually performed, in order.
   The flat `{sets, reps, weight_kg}` triplet is a summary kept for backward
   compatibility (`sets = len(sets_detail)`, `reps`/`weight_kg` = most frequent value),
   never a total. The flat shape cannot represent `10x80 8x90 8x90` and under-reported a
   real session's tonnage by 33%. Consumers must tolerate rows written before the change:
   rebuild `sets_detail` from the flat fields when it is absent.
2. **The athlete's notation has three traps**, all encoded in
   `_STRENGTH_EXTRACTION_SYSTEM_PROMPT` and pinned by tests:
   - `/c`, `/cote`, `par cote`, `/side` mean the load is PER SIDE, so what is moved is
     double (`4x8 55/c` is four sets at 110).
   - a paired line `A - B 3x10-10 15-35` is a superset: two exercises, matched in order
     (A at 15, B at 35). Dropping the first value of a pair silently loses a load.
   - a trailing `xN` is the TOTAL number of sets for the pair it follows, not N extra
     sets (`80x10 x2` is two sets, never three).
3. **Tonnage has a single definition** — `shared/strength_volume.py`, computed ONCE at
   write time in `_track_strength_history` and stored on the history entry
   (`total_sets`, `total_reps`, `volume_kg`, `body_weight_kg_used`,
   `volume_kg_incomplete`, `excluded_exercises`, `per_exercise`). The coach payload, the
   dashboard chart and the `coach_chat` tool all READ those figures. They never
   recompute: the chat cannot import `lambda_functions/shared/` (its bundle is limited to
   `src/coach_chat/`), so a second implementation there drifted immediately. Bodyweight
   movements resolve through `BODYWEIGHT_EXERCISES` only, unilateral ones double through
   `UNILATERAL_EXERCISES`, and `body_weight_kg` is NEVER defaulted (a plausible wrong
   weight is worse than a flagged gap).

**Campus Coach data contracts** (three invariants, break them and the coach mixes weeks):

1. **Execution status** — always resolve through `shared/campus_status.effective_status()`. The raw `status` attribute is a legacy field that the sync deliberately never rewrites (it is in `LOCAL_EXECUTION_FIELDS`), so it holds stale, mixed values. Precedence: `local_status` → legacy `status` if done/skip → `matched_activity_id`/`completed_at` → `provider_status` → `todo`. The `coach_chat` runtime cannot import `lambda_functions/shared/` (its `direct_code_deploy` bundles only `src/coach_chat/`), so it carries a local mirror kept honest by an anti-drift test.
2. **Week identity** — always the ISO string `'YYYY-Www'` via `shared/iso_week.iso_week_label()`, never a bare week number. A bare integer cannot be compared with the `week_date_iso` values the sync writes.
3. **Intervals schema** — consumers must tolerate three shapes, because rows written before a sync keep the old form:
   - new per-block: `{'type': 'block', 'repeat': N, 'exercises': [{type, duration, pace}]}` (emitted when `repeat > 1`)
   - new flat: `{'type': 'work', 'duration', 'pace'}` (emitted when `repeat <= 1`)
   - legacy flat with a per-entry `repeat`
   Use `modules_processing._normalize_intervals()`, which expands all three into per-occurrence units. Never sum a per-entry `repeat`: the old producer copied the block factor onto every work exercise, which inflated counts. For a session's planned duration prefer the provider's `expected_duration_min` (`_session_target_duration_min`); deriving it from intervals under-reports, because legacy rows omit the repeat factor on recoveries nested in a repeated block.

**Campus Coach Sync** (`lambda_functions/webhooks/campus_coach_sync.py`): Direct REST API integration replacing Browser Tool. Login via `POST /account/login` + `GET /smart-training?from=...&to=...` fetches all accessible weeks (1-9 depending on billing cycle). Stores structured sessions in DynamoDB with `is_current_week`/`is_future` flags, including intervals and targets. EventBridge every 2h across the athlete's active window (05:00 to 21:00 UTC, 9 runs/day): a single daily run left the coach up to 13h behind, so a session completed during the day, or a plan edited mid-afternoon, stayed invisible. Only runs if campus_coach module is enabled. Athlete context (goal, assiduity, sport profile) persisted. All future weeks injected into coach context.

**Coach Agent** (`coach_agent.py`): Training feedback agent using Claude Sonnet 4.5 with LTM memory (`coaching_observations` write session; observations are extracted by the memory strategies and read back via the unified `/strategies/` namespaces with a session-type-aware query). Analyzes activity in context of athlete profile (objectives, history, experience, pace zones, personal records, FCmax), recent training trends (4 weeks via GSI query with EF pace@HR, CTL/Form, segment PRs), and historical observations. Produces training feedback focused on **progression and trends** (not session recap). Runs in parallel with content generation.

**Coach Context (injected):**

> **Figures the coach must never recompute.** Every weekly number the coach states
> is calculated in code and handed to it. This is not cosmetic: each figure left to
> the model was wrong in production (a rolling 7-day total presented as "cette
> semaine" with a bogus "+32% ramp rate" alert, "il reste 2 séances" when 4 were
> to do, "2 séances muscu" on a week holding one), while every figure moved into
> code has been right since. The prompt states these fields are the sole source and
> forbids recomputing them.
>
> - `week_overview` (`build_week_overview`) — the single merged view of the week:
>   `done_this_week` (runs/km/strength, **current activity included**, unlike
>   `weekly_breakdown` which skips it), `campus_remaining` (count, running_count,
>   titles) and `own_strength_program` (planned/done/remaining). It buckets on the
>   ISO week of the *activity*, not of "now", so a Sunday session processed on
>   Monday stays in its own week. Sets `counts_incomplete` on query failure rather
>   than letting the model fill the gap. The athlete's week is Campus running
>   sessions **plus** his own program, and the two are never merged into one count.
> - `campus_week_remaining` — remaining plan sessions for the week, resolved through
>   `effective_status`.
> - `campus_matched_session` — authoritative "this activity closes plan session X",
>   from the shared `match_campus_session`. Authoritative on *which* session was
>   done, never on what was done inside it: counts and paces always come from laps.
> - `recent_activities_by_week` — per-activity detail keyed by ISO week. Deliberately
>   not a flat dated list: that shape is what let the coach sum an arbitrary window.
> - `weekly_km` — keyed by ISO label (`2026-W32`), never a bare week number.

- Athlete profile + pace zones + personal records + FCmax
- **Strength program** (Upper A, Upper B, Rappel — exercises with sets/load/rest)
- **Strength history** (last 8 WeightTraining descriptions for progression tracking)
- Historical: all activities from 4 weeks (max 30) with EF, CTL, decoupling, prev_coach_note, training_load
- Fitness trend (CTL progression from Intervals.icu if available)
- Athlete HR zones (from Strava, fetched at OAuth)
- Best efforts PRs (auto-accumulated) + segment PRs (top 20)
- Computed metrics: EF (pace@HR), %FCmax, Zone 3 moderate time
- Campus Coach weekly plan (current week sessions with intervals and targets)
- Campus Coach future weeks (all synced future sessions for planning context)
- Campus Coach athlete context (goal, assiduity, sport profile)
- Training load + intensity per activity (from Intervals.icu)
- Past coaching observations (LTM memory)

### Authentication

**Cognito User Pool** (deployed in Frontend stack):
- `self_sign_up_enabled=False` — users created via `admin-create-user` only
- Email-based sign-in
- Password policy: 12+ characters
- First login requires password change (FORCE_CHANGE_PASSWORD)
- API Gateway uses Cognito authorizer (replaced API key auth)
- Frontend sends JWT token in `Authorization` header
- Sign Out button in TopNav layout

### Memory Strategy

The content generation memory (`content_gen_mem`) uses 3 strategies, all on the
unified namespace convention `/strategies/{memoryStrategyId}/actors/{actorId}/`
(see `docs/design/memory-improvements.md`):
- **Semantic** (`ComprehensiveLearning`): semantic extraction over conversation history — the source of the coach's long-term observations
- **UserPreference** (`StravaContentPreferences`): automatic extraction/consolidation of user content preferences from feedback diffs
- **Episodic** (`CoachingEpisodes`): per-session episodes + actor-level reflections (periodic consolidated insights)

All readers share one pattern: `RetrieveMemoryRecords` with the `/strategies/`
namespace **prefix** + a per-user `/actors/{userId}/` filter, and a
session-type-aware search query (a strength session retrieves strength
progression records, an interval session retrieves interval records). Readers:
the coach agent (past observations in feedback), the weekly recap Lambda
(trend observations for the audio script), the coach chat `get_coach_observations`
tool (continuity in conversation), and the content agent (learned preferences).

The feedback analyzer writes before/after diffs as conversational events
(ASSISTANT=generated, USER=edited). Modification detection threshold: **99.5%
similarity** (even minor edits trigger memory writes). The UserPreferenceStrategy
automatically extracts preferences (length, tone, emojis, structure, technical
detail) and consolidates them over time.

The whole strategy setup is reproducible and idempotent via
`scripts/configure_memory_strategy.py` (creates/updates the strategies and
migrates any records left in legacy namespaces).

### Deployment

```bash
./scripts/create_agentcore_memories.sh          # Step 1: Create the LTM memory (content_gen_mem)
./scripts/deploy_agentcore_agents.sh            # Step 2: Deploy agents
./scripts/configure_agentcore_integration.sh    # Step 3: Configure IAM + Lambda
python scripts/configure_memory_strategy.py     # Step 4: Configure the 3 memory strategies
```

---

## Deployment Procedures

### Full Deployment

**Prerequisites:**
- AWS credentials configured (`AWS_PROFILE`, or ambient credentials — the scripts pass
  `--profile` only when one is set)
- AWS CDK CLI installed (`npm install -g aws-cdk`)
- AgentCore CLI installed
- Python 3.12 in a project venv (`.venv-deploy`, `venv` or `.venv` — `deploy.sh` detects
  them in that order). Synth needs 3.11+ and `PyYAML` from `requirements.txt`: it is the
  only way `.bedrock_agentcore.yaml` is read, and without it the deploy would blank
  `BEDROCK_AGENTCORE_MEMORY_ID`. The preflight in `deploy.sh` checks all of this.

**Step 1: Deploy Infrastructure (includes Frontend stack)**
```bash
./scripts/deploy.sh dev
```

**Step 2: Validate Deployment**
```bash
./scripts/validate_deployment.sh dev
```

**Step 3: Create Cognito User**
```bash
aws cognito-idp admin-create-user \
  --user-pool-id <pool-id> \
  --username your@email.com \
  --temporary-password "TempPass123!" \
  --user-attributes Name=email,Value=your@email.com \
  --profile your-aws-profile --region us-east-1
```

**Step 4: Configure Webhook**
```bash
./scripts/configure_strava_webhook.sh dev --auto-configure
```

**Step 5: Deploy AgentCore (Optional)**
```bash
./scripts/create_agentcore_memories.sh
./scripts/deploy_agentcore_agents.sh
./scripts/configure_agentcore_integration.sh
```

**Frontend URL:** the `DistributionDomain` output of the Frontend stack (deployed automatically)

### Updating Existing Deployment

**Update CDK Stacks:**
```bash
cdk deploy --all --profile your-aws-profile
```

**Update Specific Stack:**
```bash
cdk deploy StravaAIBoost-ContentGenerationStack --profile your-aws-profile
```

**Update Frontend (rebuild + deploy to S3/CloudFront):**
```bash
cdk deploy StravaAIBoost-Frontend --profile your-aws-profile
```

**Update Lambda Function:**
```bash
# Modify lambda_functions/<package>/my_function.py
cdk deploy StravaAIBoost-ContentGenerationStack --profile your-aws-profile
```

**Update AgentCore Agent:**
```bash
./scripts/deploy_agentcore_agents.sh
```

---

## Common Tasks

### Adding a New Lambda Function

**Step 1: Create Function File**
```bash
touch lambda_functions/api/my_function.py  # or processing/, webhooks/, support/
```

**Step 2: Implement Handler**
```python
# lambda_functions/api/my_function.py
def handler(event, context):
    # Implementation
    return {'statusCode': 200, 'body': 'Success'}
```

**Step 3: Add to CDK Stack**
```python
# stacks/content_generation_stack.py
self.my_function = lambda_.Function(
    self, "MyFunction",
    runtime=lambda_.Runtime.PYTHON_3_12,
    handler="api.my_function.handler",
    code=lambda_.Code.from_asset("lambda_functions"),
    environment={...}
)
```

**Step 4: Deploy**
```bash
cdk deploy StravaAIBoost-ContentGenerationStack --profile your-aws-profile
```

### Adding a New DynamoDB Table

**Step 1: Add to Core Stack**
```python
# stacks/core_infrastructure_stack.py
self.my_table = dynamodb.Table(
    self, "MyTable",
    partition_key=dynamodb.Attribute(
        name="id",
        type=dynamodb.AttributeType.STRING
    ),
    billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST
)
```

**Step 2: Grant Permissions**
```python
# In the stack that needs access
core_stack.my_table.grant_read_write_data(self.my_function)
```

**Step 3: Deploy**
```bash
cdk deploy StravaAIBoost-CoreInfrastructureStack --profile your-aws-profile
```

### Adding a New API Endpoint

**Step 1: Add Route Handler**
```python
# lambda_functions/api/configuration_api.py
def handler(event, context):
    path = event['path']
    method = event['httpMethod']
    
    if path == '/my-endpoint' and method == 'GET':
        return handle_my_endpoint(event)
```

**Step 2: Update API Gateway**
```python
# stacks/api_gateway_stack.py
my_endpoint = api.root.add_resource('my-endpoint')
my_endpoint.add_method('GET', lambda_integration)
```

**Step 3: Deploy**
```bash
cdk deploy StravaAIBoost-ApiGatewayStack --profile your-aws-profile
```

---

## Troubleshooting

### Common Issues

**Issue: Lambda Function Timeout**
```
Solution: Increase timeout in CDK stack
timeout=Duration.seconds(300)
```

**Issue: DynamoDB Throttling**
```
Solution: Check capacity mode, consider on-demand
billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST
```

**Issue: AgentCore Connection Error**
```
Solution: Check IAM permissions and agent ARN
./scripts/configure_agentcore_integration.sh
```

**Issue: Strava API Rate Limit**
```
Solution: Check Lambda logs for rate limit errors, wait for reset
aws logs filter-log-events --log-group-name /aws/lambda/StravaAIBoost-ActivityProcessor --filter-pattern "rate" --profile your-aws-profile
```

### Debugging Lambda Functions

**View Logs:**
```bash
aws logs tail /aws/lambda/StravaAIBoost-ContentGenerator --follow --profile your-aws-profile
```

**Test Locally:**
```python
# Set env vars first (see tests/unit/conftest.py)
import os
os.environ['ACTIVITIES_TABLE'] = 'test-activities'
# ...

from processing.content_generator import handler
result = handler({'activity_id': '123', 'user_id': 'user1'}, None)
print(result)
```

### Debugging Step Functions

**View Executions:**
```bash
aws stepfunctions list-executions \
  --state-machine-arn <arn> \
  --profile your-aws-profile
```

**Get Execution Details:**
```bash
aws stepfunctions describe-execution \
  --execution-arn <arn> \
  --profile your-aws-profile
```

---

## Code Style Guidelines

### Python Style
- **PEP 8** compliance
- **Type hints** for function signatures
- **Docstrings** for all public functions
- **4 spaces** for indentation

### Naming Conventions
- **snake_case** for functions and variables
- **PascalCase** for classes
- **UPPER_CASE** for constants
- **Descriptive names** (avoid abbreviations)

### Error Handling
- **Try-except blocks** for external calls
- **Specific exceptions** (avoid bare except)
- **Logging** for all errors
- **Graceful degradation** where possible

---

## Next Steps (Backlog)

### P1 — Short Term (validate coach on real activities)
- [x] Fill Athlete Profile in Preferences (objectives, history, experience)
- [x] Set FCmax in Preferences (use Tanaka calculator or manual override)
- [x] Add Personal Records (5K, 10K, Semi times with dates)
- [ ] Run 3-5 activities and review coach feedback quality
- [ ] Verify strava_block talks about trends/progression (not session recap)
- [ ] Iterate on COACH_AGENT_SYSTEM_PROMPT based on real outputs
- [ ] Verify coach memory accumulates observations over time

### P2 — Medium Term ✅ DONE
- [x] Multi-user readiness: extract user_id from Cognito JWT instead of DEFAULT_USER_ID
  - Précision (vérifié 2026-07-27) : les endpoints Coach extraient `custom:strava_id` du JWT et **échouent fermés** (403 sans claim). Les endpoints dashboard retombent encore sur `DEFAULT_USER_ID` (single-user by design, cf. README). Le mécanisme JWT existe donc mais l'app reste mono-athlète — pas de hardening multi-tenant.
- [x] Coach adaptatif: add `recommendation_next` field to coach feedback output
- [x] With Campus Coach: suggest adjustments (rest day if fatigued, complementary renfo)
- [x] Without Campus Coach: propose mini weekly plan based on history + objectives
- [x] Compliance scoring: track plan adherence percentage
- [x] Weekly synthesis (EventBridge schedule, Sunday 20:00 UTC)
- [x] Frontend Coach page: display 'Prochaine séance recommandée' from coach output
- [x] Frontend Preferences: display auto-accumulated PRs from best_efforts
- [x] Add ramp rate explicit alert (flag >10%/week)
- [x] Conversational mode: chat widget on Coach page (initially a `/coach/ask` endpoint, since replaced by the `coach_chat` AgentCore Runtime)

### P3 — Long Term
- [ ] Morning briefing (pre-run guidance based on Form/fatigue/plan)
- [ ] Race readiness assessment (periodic check vs goal pace)
- [ ] Multi-tenant AgentCore (single agent, user context per session)
- [ ] HYROX-specific feedback (hybrid running + strength)
- [ ] Nothing to report logic (skip trivial sessions)

---

## Additional Resources

### Documentation
- **Roadmap:** `docs/ROADMAP.md`
- **Backlog:** `BACKLOG.md`
- **Scripts:** `scripts/README.md`
- **Tests:** `tests/README.md`
- **README:** `README.md`

### External Links
- **AWS CDK:** https://docs.aws.amazon.com/cdk/
- **Strava API:** https://developers.strava.com/
- **AgentCore:** https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/
