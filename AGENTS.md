# AGENTS.md - AI Assistant Context for Strava AI Boost

**Version:** 4.0.0
**Last Updated:** 2026-05-10
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

Strava AI Boost is a **serverless AWS application** that automatically enhances Strava activity titles and descriptions using AI. The system uses a **React + Cloudscape frontend** hosted on CloudFront (with Cognito authentication) that calls API Gateway directly.

### Key Statistics
- **~16,600 LOC** in core components
- **14 Lambda functions** (4 API, 3 processing, 3 webhooks, 2 support, 2 coach)
- **3 AgentCore agents**
- **7 CDK stacks**
- **167 tests** (127 backend + 40 frontend)
- **Python 3.12** runtime, **React 19 + TypeScript + Vite** frontend
- **Cognito authentication** (JWT, no self-registration)
- **CloudFront + S3** frontend hosting (OAC)

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
Coach Generator: DynamoDB → athlete profile + activity history → AgentCore coach_agent → coaching feedback
Assembly Lambda: Merge content + coach outputs → update Strava + store results
Campus Coach: Sessions stored in DynamoDB → passed to content_gen agent prompt → LLM does the matching
```

---

## Directory Structure

```
strava-ai-boost/
├── scripts/                    # Deployment and maintenance (12 scripts)
│   ├── deploy.sh              # Main CDK deployment
│   ├── deploy_agentcore_agents.sh
│   ├── configure_agentcore_integration.sh
│   ├── create_agentcore_memories.sh
│   ├── configure_memory_strategy.py  # Memory UserPreferenceStrategy config
│   ├── configure_strava_webhook.sh
│   ├── setup_local_env.sh
│   ├── validate_deployment.sh
│   ├── cleanup_strava_webhook.sh
│   ├── reprocess_dlq.sh
│   ├── uninstall.sh
│   └── verify_uninstall.sh
│
├── stacks/                     # CDK infrastructure (7 stacks)
│   ├── core_infrastructure_stack.py    # DynamoDB, Secrets, Layer
│   ├── security_stack.py               # Guardrails, Memory Execution Role, Observability
│   ├── webhook_processing_stack.py     # Webhook, SQS, Processor
│   ├── content_generation_stack.py     # Step Functions, Lambdas
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
│   │   └── agentcore_health_check.py   # Health check
│   ├── processing/                     # Content pipeline
│   │   ├── activity_fetcher.py         # Data fetcher
│   │   ├── content_generator.py        # AI content generation
│   │   ├── coach_generator.py          # AI coaching feedback generation
│   │   ├── assembly_lambda.py          # Merge content + coach → Strava update
│   │   ├── strava_updater.py           # Strava API updater
│   │   ├── workout_analysis.py         # Workout classification from laps, Enduraw extraction
│   │   └── modules_processing.py       # Module discovery, Campus Coach session retrieval
│   ├── webhooks/                       # Event ingestion
│   │   ├── webhook_handler.py          # Webhook receiver
│   │   ├── activity_processor.py       # SQS processor
│   │   └── campus_coach_invoker.py     # Session retrieval
│   ├── support/                        # Operational utilities
│   │   ├── feedback_analyzer.py        # Feedback loop
│   │   └── stepfunctions_error_handler.py  # Error handler
│   └── shared/                         # Shared utilities module
│       ├── __init__.py
│       ├── logger.py                   # Powertools Logger, Metrics, correlation IDs
│       ├── env_validation.py           # Environment variable validation
│       ├── responses.py                # Standardized API responses
│       └── strava_oauth.py             # OAuth token management
│
├── src/
│   ├── agents/                 # AgentCore agents (3 agents)
│   │   ├── content_agent.py            # Content generation agent
│   │   ├── campus_coach_agent.py       # Campus Coach scraper
│   │   ├── coach_agent.py              # Training coach agent
│   │   └── embedded_prompts.py         # Prompt templates
│   │
│   ├── modules/                # Module system (Enduraw only)
│   │   ├── base_module.py              # Base class & registry
│   │   ├── enduraw_module.py           # Enduraw integration (fetches its own streams independently)
│   │   └── registry.py                 # Module registration
│   │   # Campus Coach: no module — sessions fetched from DynamoDB by modules_processing.py, matching done by content_gen agent
│   │   # Intervals.icu: integrated directly in activity_fetcher.py + content_agent.py (no separate module file)
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
│   │   ├── components/                 # Cloudscape components + tests
│   │   ├── pages/                      # Page components (Dashboard, Config, Preferences, Quality, Coach, LoginPage)
│   │   ├── layouts/                    # Layout components (Shell, TopNav w/ Sign Out, Breadcrumbs)
│   │   ├── utils/                      # Pure utility functions + tests
│   │   ├── test/                       # Test setup (Vitest + Testing Library)
│   │   └── config.ts                   # Runtime configuration
│   ├── package.json                    # Dependencies
│   └── vite.config.ts                  # Vite + Vitest configuration
│
├── tests/                      # Test suite
│   ├── unit/                           # Lambda unit tests (127 tests)
│   │   ├── conftest.py                 # Env vars for Lambda imports
│   │   ├── test_webhook_handler.py     # 30 tests: validation, routing, signature
│   │   ├── test_content_generator.py   # 36 tests: DynamoDB, parsing, storage
│   │   ├── test_workout_analysis.py    # Laps classification, pace zones, Enduraw extraction
│   │   └── test_dashboard_api.py       # 27 tests: validation, routing, caching
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
├── docs/                       # User documentation
│   ├── getting-started/
│   ├── user-guide/
│   ├── advanced/
│   └── reference/
│
├── .agents/                    # AI assistant documentation
│   └── summary/
│       ├── index.md                    # Knowledge base index
│       ├── codebase_info.md
│       ├── architecture.md
│       ├── components.md
│       ├── interfaces.md
│       ├── data_models.md
│       ├── workflows.md
│       ├── dependencies.md
│       └── review_notes.md
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

**Lambda Unit Tests (127 tests, ~0.7s):**
```bash
pytest tests/unit/ -v
```

**Infrastructure/Integration Tests (73 tests):**
```bash
export AWS_PROFILE=your-aws-profile
pytest tests/ -v --ignore=tests/unit/
```

**Frontend Tests (40 tests, ~4s):**
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

**Content Agent** (`content_agent.py`): Generate enhanced activity content with LTM memory, Claude Sonnet 4.5, Guardrails enabled. Receives device-recorded laps (from Strava Laps API), Campus Coach sessions, Enduraw reports, and Intervals.icu data (CTL/ATL/Form/HRV/Decoupling). Handles all matching logic (Campus Coach session matching, workout classification) via prompt rules in `embedded_prompts.py`.

**Anti-AI Writing Rules** (enforced in content generation prompts):
- Em dash (—) and en dash (–) are **banned** from all generated content
- Banned cliché expressions: "la machine", "le corps se réveille", "chaque foulée", "repousser les limites", etc.
- Pierre's real writing style examples used as positive anchors in prompts
- Goal: authentic, personal voice — not generic AI-sounding text

**Campus Coach Agent** (`campus_coach_agent.py`): Extract training sessions via Browser Tool, Claude Sonnet 4.5. Stores sessions in DynamoDB — no analysis, matching is done by the content agent.

**Coach Agent** (`coach_agent.py`): Training feedback agent using Claude Sonnet 4.5 with LTM memory (`coaching_observations` namespace). Analyzes activity in context of athlete profile (objectives, history, experience), recent training trends, and historical observations. Produces training feedback, trend analysis, and personalized recommendations. Runs in parallel with content generation.

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

The content generation memory (`content_gen_mem`) uses 2 strategies:
- **Semantic** (`ComprehensiveLearning`): Semantic search over conversation history
- **UserPreference** (`StravaContentPreferences`): Automatic extraction/consolidation of user content preferences from feedback diffs

The coach agent uses the same memory resource with a dedicated `coaching_observations` namespace for storing training observations, trends, and athlete progression data.

The feedback analyzer writes before/after diffs as conversational events (ASSISTANT=generated, USER=edited). Modification detection threshold: **99.5% similarity** (even minor edits trigger memory writes). The UserPreferenceStrategy automatically extracts preferences (length, tone, emojis, structure, technical detail) and consolidates them over time.

The content agent reads preferences via `RetrieveMemoryRecords` semantic search across user-specific namespaces.

### Deployment

```bash
./scripts/create_agentcore_memories.sh          # Step 1: Create LTM memories
./scripts/deploy_agentcore_agents.sh            # Step 2: Deploy agents
./scripts/configure_agentcore_integration.sh    # Step 3: Configure IAM + Lambda
python scripts/configure_memory_strategy.py     # Step 4: Configure UserPreferenceStrategy
```

---

## Deployment Procedures

### Full Deployment

**Prerequisites:**
- AWS CLI configured with profile `your-aws-profile`
- AWS CDK CLI installed
- AgentCore CLI installed
- Python 3.12+

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

**Frontend URL:** https://d1p03w7uoqpahh.cloudfront.net (deployed automatically with the Frontend stack)

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

## Additional Resources

### Documentation
- **User Documentation:** `docs/`
- **Scripts Documentation:** `scripts/README.md`
- **README:** `README.md`

### External Links
- **AWS CDK:** https://docs.aws.amazon.com/cdk/
- **Strava API:** https://developers.strava.com/
- **AgentCore:** https://docs.aws.amazon.com/bedrock/latest/userguide/agents-core.html
