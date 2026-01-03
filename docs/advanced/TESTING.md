# Testing Guide - Strava AI Boost

**Version:** 2.0.0  
**Last Updated:** 2026-01-03  
**Status:** Complete test suite with 100% pass rate

## Overview

Strava AI Boost uses a modern testing approach with **dynamic AWS resource discovery**:
- **73 tests** with **100% pass rate**
- **No hardcoded values** - automatic resource discovery
- **Real API testing** - validates deployed endpoints
- **Fast execution** - complete suite in <25 seconds

## Test Suite Structure

```
tests/
├── conftest.py                 # Pytest configuration and fixtures
├── aws_config.py              # Dynamic AWS resource discovery
├── test_api_gateway.py        # Live API Gateway endpoint tests (28 tests)
├── test_cdk_infrastructure.py # CDK stack tests (25 tests)
├── test_lambda_functions.py   # Lambda structure tests (10 tests)
├── test_end_to_end.py        # Integration tests (10 tests)
└── README.md                  # Test suite documentation
```

## Quick Start

### Install Dependencies

```bash
pip install pytest>=7.0.0 pytest-cov>=4.0.0 moto>=4.2.0 boto3>=1.26.0 requests>=2.28.0
```

### Run Tests

```bash
# Run complete test suite
export AWS_PROFILE=your-aws-profile
pytest tests/ -v

# Expected output: 73 passed in ~20s
```

### Run with Coverage

```bash
pytest tests/ --cov=lambda_functions --cov=stacks --cov=src --cov-report=html
open htmlcov/index.html
```

## Test Categories

### 1. API Gateway Tests (28 tests)

**File**: `tests/test_api_gateway.py`  
**Purpose**: Test real API Gateway endpoints with HTTP requests

**Coverage**:
- Health endpoints (`/health/agentcore`)
- Configuration endpoints (`/config/oauth`, `/config/modules`, `/config/enhancement`)
- Dashboard endpoints (`/dashboard/stats`, `/dashboard/activities`, `/dashboard/system`)
- User preferences (`/preferences`)
- Error handling (404, 403, 405)
- API Key validation
- Performance testing
- CORS configuration

**Example**:
```python
def test_agentcore_health(self, api_client):
    response = api_client.get('/health/agentcore')
    assert response.status_code in [200, 503]
    data = response.json()
    assert 'overall_status' in data
```

**Key Features**:
- ✅ Uses real API Gateway with dynamic URL/Key discovery
- ✅ Tests actual HTTP requests and responses
- ✅ Validates response structure and data
- ✅ Tests complete workflows (pause → resume)

### 2. CDK Infrastructure Tests (25 tests)

**File**: `tests/test_cdk_infrastructure.py`  
**Purpose**: Test CDK stack synthesis and resource configuration

**Coverage**:
- Core infrastructure (DynamoDB, IAM, Secrets Manager, Lambda Layer)
- Content generation stack (Lambda, Step Functions, EventBridge)
- Webhook processing stack (SQS, Lambda, API Gateway, CloudWatch)
- API Gateway stack (REST API, API Key, Usage Plan, CORS)
- Security compliance (encryption, IAM, secrets)

**Example**:
```python
def test_dynamodb_tables_created(self, core_stack):
    template = assertions.Template.from_stack(core_stack)
    template.resource_count_is("AWS::DynamoDB::Table", 4)
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "SSESpecification": {"SSEEnabled": True}
    })
```

**Coverage**: 91% for CDK stacks ✅

### 3. Lambda Function Tests (10 tests)

**File**: `tests/test_lambda_functions.py`  
**Purpose**: Test Lambda function structure and configuration

**Coverage**:
- Lambda handler existence
- Environment variables
- Module imports
- Event structure validation
- Rate limiting configuration

**Example**:
```python
def test_all_lambdas_have_handler(self):
    lambda_files = ['webhook_handler.py', 'content_generator.py', ...]
    for lambda_file in lambda_files:
        with open(file_path, 'r') as f:
            assert 'def handler(' in f.read()
```

### 4. Integration Tests (10 tests)

**File**: `tests/test_end_to_end.py`  
**Purpose**: Test deployed AWS resources and workflows

**Coverage**:
- DynamoDB tables (4 tables)
- Lambda functions (16 functions)
- SQS queues (2 queues)
- Step Functions (1 workflow)
- Secrets Manager (3 secrets)
- Complete workflow execution

**Example**:
```python
def test_dynamodb_tables_exist(self, aws_session):
    dynamodb = aws_session.client('dynamodb')
    tables = dynamodb.list_tables()
    boost_tables = [t for t in tables['TableNames'] 
                   if 'strava-ai-boost' in t.lower()]
    assert len(boost_tables) >= 4
```

## Dynamic Configuration

### AWS Resource Discovery

The test suite automatically discovers deployed AWS resources:

```python
from tests.aws_config import get_aws_config

config = get_aws_config()

# Discover all resources
resources = config.get_all_resources()

# Get specific resources
api_url = config.get_api_gateway_url()      # Finds Local Interface API
api_key = config.get_api_gateway_key()      # Retrieves actual API Key value
tables = config.get_dynamodb_tables()       # Lists all tables
lambdas = config.get_lambda_functions()     # Lists all Lambda functions

# Print summary
config.print_summary()
```

### Configuration Features

- ✅ **Automatic API Gateway discovery** - Finds "Local Interface API" (not Webhook API)
- ✅ **API Key retrieval** - Gets actual key value with `includeValues=True`
- ✅ **Profile support** - Uses `AWS_PROFILE` environment variable
- ✅ **CloudFormation integration** - Reads stack outputs when available
- ✅ **Caching** - Caches discovered resources for performance

## Running Tests

### Local Development

```bash
# Quick test run
export AWS_PROFILE=your-aws-profile
pytest tests/ -x --ff

# Test specific functionality
pytest tests/test_api_gateway.py::TestHealthEndpoints -v

# Test with detailed output
pytest tests/ -v -s
```

### CI/CD Pipeline

```bash
# Full test suite with coverage
pytest tests/ -v --cov=. --cov-report=xml --cov-report=term

# Generate HTML coverage report
pytest tests/ --cov=. --cov-report=html
```

### Performance Testing

```bash
# Measure test execution time
time pytest tests/ -v

# Profile test performance
pytest tests/ --durations=10

# Test API response times
pytest tests/test_api_gateway.py::TestAPIPerformance -v
```

## Test Results Summary

### Execution Time

- **Unit tests** (CDK + Lambda): ~10s
- **API Gateway tests**: ~10s
- **Integration tests**: ~5s
- **Complete suite**: ~25s

### Pass Rate

- **73/73 tests pass** (100%) ✅
- **0 skipped** (all tests run)
- **0 failed** (all tests pass)

### Coverage by Component

| Component | Lines | Covered | % | Status |
|-----------|-------|---------|---|--------|
| CDK Stacks | 356 | 324 | 91% | ✅ Excellent |
| API Gateway Stack | 75 | 74 | 99% | ✅ Perfect |
| Webhook Stack | 64 | 62 | 97% | ✅ Excellent |
| Core Stack | 54 | 47 | 87% | ✅ Good |
| Content Stack | 97 | 83 | 86% | ✅ Good |
| LLM Config | 35 | 29 | 83% | ✅ Good |
| Lambda Functions | 2607 | 130 | 5% | ⚠️ Integration |
| Agents | 494 | 0 | 0% | ⚠️ AgentCore |
| Modules | 1304 | 0 | 0% | ⚠️ Complex |

**Overall**: 8% (misleading - infrastructure is 91% covered)

## Advanced Testing

### API Gateway Live Testing

Tests real HTTP requests to deployed API Gateway:

```python
class TestHealthEndpoints:
    def test_agentcore_health(self, api_client):
        response = api_client.get('/health/agentcore')
        assert response.status_code in [200, 503]
        assert 'overall_status' in response.json()
```

**Features**:
- Real HTTP requests with `requests` library
- Dynamic API URL and Key discovery
- Response validation (status, structure, data)
- Performance testing (response times)
- Error scenario testing

### CDK Infrastructure Testing

Tests CDK stack synthesis and resource configuration:

```python
def test_dynamodb_tables_created(self, core_stack):
    template = assertions.Template.from_stack(core_stack)
    template.resource_count_is("AWS::DynamoDB::Table", 4)
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "SSESpecification": {"SSEEnabled": True}
    })
```

**Features**:
- CDK template synthesis
- Resource count validation
- Property assertions
- Security compliance checks

### Integration Testing

Tests deployed AWS resources:

```python
def test_dynamodb_tables_exist(self, aws_session):
    dynamodb = aws_session.client('dynamodb')
    tables = dynamodb.list_tables()
    boost_tables = [t for t in tables['TableNames'] 
                   if 'strava-ai-boost' in t.lower()]
    assert len(boost_tables) >= 4
```

**Features**:
- Uses real AWS resources
- Validates deployment
- Tests resource accessibility
- Verifies configuration

## Troubleshooting

### Common Issues

#### API Gateway Tests Fail (403)

```bash
# Verify API Gateway URL and Key
python tests/aws_config.py

# Test manually
export API_URL=$(python -c "from tests.aws_config import get_aws_config; print(get_aws_config().get_api_gateway_url())")
export API_KEY=$(python -c "from tests.aws_config import get_aws_config; print(get_aws_config().get_api_gateway_key())")
curl -H "X-API-Key: $API_KEY" "$API_URL/health/agentcore"
```

#### CDK Tests Fail

```bash
# Verify CDK can synthesize
cdk synth --profile your-aws-profile

# Check Python syntax
python -m py_compile stacks/*.py
```

#### Integration Tests Fail

```bash
# Verify AWS credentials
aws sts get-caller-identity --profile your-aws-profile

# Check resources are deployed
aws cloudformation list-stacks --profile your-aws-profile --query 'StackSummaries[?contains(StackName, `StravaAIBoost`)].StackName'
```

#### Import Errors

```bash
# Verify Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest tests/ -v
```

## Best Practices

### 1. Test Isolation

- Each test is independent
- Uses fixtures for setup/teardown
- Mocks external dependencies for unit tests
- Uses real AWS for integration tests

### 2. Test Data

- Dynamic resource discovery (no hardcoded values)
- Realistic test scenarios
- Proper cleanup after tests

### 3. Assertions

- Test one thing per test
- Descriptive assertion messages
- Verify both success and failure cases

### 4. Performance

- Unit tests: <1s each
- Integration tests: <2s each
- Complete suite: <25s total

## Future Enhancements

### Planned Improvements

1. **Lambda unit tests** - Add mocked tests for Lambda handlers
2. **Agent tests** - Test agent prompts and logic locally
3. **Module tests** - Test Campus Coach and Enduraw modules
4. **Load tests** - Test API Gateway under concurrent load
5. **Security tests** - Penetration testing for API endpoints
6. **Performance benchmarks** - Track response times over time

### Test Automation

1. **Pre-commit hooks** - Run tests before commit
2. **Automated test data** - Generate realistic test scenarios
3. **Continuous testing** - Run tests on every push
4. **Performance regression** - Detect performance degradation

---

**For detailed test documentation**: See `tests/README.md`  
**For test execution examples**: Run `pytest tests/ -v`  
**For resource discovery**: Run `python tests/aws_config.py`
