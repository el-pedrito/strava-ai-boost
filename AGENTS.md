# AGENTS.md - AI Assistant Context for Strava AI Boost

**Version:** 2.4.0
**Last Updated:** 2026-03-05
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

Strava AI Boost is a **serverless AWS application** that automatically enhances Strava activity titles and descriptions using AI. The system uses a **React + Cloudscape frontend** that calls API Gateway directly.

### Key Statistics
- **1,701 files** total
- **~23,051 LOC** in core components
- **13 Lambda functions**
- **2 AgentCore agents**
- **7 CDK stacks**
- **Python 3.12** runtime

### Architecture Pattern
**Event-Driven Serverless:**
```
Strava Webhook → SQS → Step Functions → Lambda Pipeline → Strava Update
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
│   ├── api_gateway_stack.py            # REST API, API Lambdas
│   ├── monitoring_stack.py             # CloudWatch, Alarms
│   └── feedback_loop_stack.py          # Feedback analyzer
│
├── lambda_functions/           # Lambda handlers (13 functions)
│   ├── shared/                         # Shared utilities module
│   │   ├── __init__.py
│   │   └── logger.py                   # Powertools Logger, Metrics, correlation IDs
│   ├── webhook_handler.py              # Webhook receiver
│   ├── activity_processor.py           # SQS processor
│   ├── activity_fetcher.py             # Data fetcher
│   ├── content_generator.py            # AI content generation
│   ├── strava_updater.py               # Strava API updater
│   ├── configuration_api.py            # Config API
│   ├── dashboard_api.py                # Dashboard API
│   ├── user_preferences_api.py         # Preferences API
│   ├── rate_limiter.py                 # Rate limiting
│   ├── campus_coach_invoker.py         # Session retrieval
│   ├── agentcore_health_check.py       # Health check
│   ├── stepfunctions_error_handler.py  # Error handler
│   └── feedback_analyzer.py            # Feedback loop
│
├── src/
│   ├── agents/                 # AgentCore agents (2 agents)
│   │   ├── content_agent.py            # Content generation agent
│   │   ├── campus_coach_agent.py       # Campus Coach scraper
│   │   └── embedded_prompts.py         # Prompt templates
│   │
│   ├── modules/                # Module system (3 modules)
│   │   ├── base_module.py              # Base class & registry
│   │   ├── campus_coach_module.py      # Campus Coach integration
│   │   ├── enduraw_module.py           # Enduraw integration
│   │   └── registry.py                 # Module registration
│   │
│   └── config/                 # Configuration
│       └── llm_config.py               # LLM configuration
│
├── frontend/                   # React web application
│   ├── src/                            # React + TypeScript source
│   ├── public/                         # Static assets
│   ├── package.json                    # Dependencies
│   └── vite.config.ts                  # Vite configuration
│
├── tests/                      # Test suite
│   ├── test_cdk_infrastructure.py      # Stack tests
│   ├── test_api_gateway.py             # API tests
│   ├── test_lambda_functions.py        # Lambda tests
│   ├── test_end_to_end.py              # E2E tests
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

**All Tests:**
```bash
cd .
pytest tests/ -v
```

**Specific Test File:**
```bash
pytest tests/test_api_gateway.py -v
```

**Specific Test:**
```bash
pytest tests/test_api_gateway.py::TestHealthEndpoints::test_agentcore_health -v
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

**Location:** `tests/conftest.py`

**Common Fixtures:**
```python
@pytest.fixture
def aws_credentials():
    """Mock AWS credentials."""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'

@pytest.fixture
def sample_activity_data():
    """Sample activity data for testing."""
    return {
        'activity_id': '123456',
        'name': 'Morning Run',
        'type': 'Run',
        'distance': 10000,
        'moving_time': 3600
    }
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

**Content Agent** (`content_agent.py`): Generate enhanced activity content with LTM memory, Claude Sonnet 4.5, Guardrails enabled.

**Campus Coach Agent** (`campus_coach_agent.py`): Extract training sessions via Browser Tool, Claude Sonnet 4.5.

### Memory Strategy

The content generation memory (`content_gen_mem`) uses 2 strategies:
- **Semantic** (`ComprehensiveLearning`): Semantic search over conversation history
- **UserPreference** (`StravaContentPreferences`): Automatic extraction/consolidation of user content preferences from feedback diffs

The feedback analyzer writes before/after diffs as conversational events (ASSISTANT=generated, USER=edited). The UserPreferenceStrategy automatically extracts preferences (length, tone, emojis, structure, technical detail) and consolidates them over time.

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

**Step 1: Deploy Infrastructure**
```bash
./scripts/deploy.sh dev
```

**Step 2: Validate Deployment**
```bash
./scripts/validate_deployment.sh dev
```

**Step 3: Setup Local Environment**
```bash
./scripts/setup_local_env.sh
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

### Updating Existing Deployment

**Update CDK Stacks:**
```bash
cdk deploy --all --profile your-aws-profile
```

**Update Specific Stack:**
```bash
cdk deploy StravaAIBoost-ContentGenerationStack --profile your-aws-profile
```

**Update Lambda Function:**
```bash
# Modify lambda_functions/my_function.py
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
touch lambda_functions/my_function.py
```

**Step 2: Implement Handler**
```python
# lambda_functions/my_function.py
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
    handler="my_function.handler",
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
# lambda_functions/configuration_api.py
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
Solution: Check rate_limits table, wait for reset
aws dynamodb scan --table-name strava-ai-boost-rate-limits --profile your-aws-profile
```

### Debugging Lambda Functions

**View Logs:**
```bash
aws logs tail /aws/lambda/StravaAIBoost-ContentGenerator --follow --profile your-aws-profile
```

**Test Locally:**
```python
# Create test event
event = {'key': 'value'}
context = {}

# Import and test
from lambda_functions.my_function import handler
result = handler(event, context)
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
