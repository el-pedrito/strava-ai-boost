# Test Suite for Strava AI Boost

Integration test suite with dynamic AWS resource discovery.

> This README covers the **integration suite** (live AWS). Two other suites live alongside:
> - `tests/unit/` — 316 mocked Lambda unit tests, no AWS credentials (`pytest tests/unit/`)
> - `tests/regression/` — 41 prompt-regression & docs-sync tests + live runners (see `docs/design/regression-evals.md`)

## Test Files

| File | Tests | Description |
|------|-------|-------------|
| `conftest.py` | - | Pytest configuration and shared fixtures |
| `aws_config.py` | - | Dynamic AWS resource discovery |
| `test_api_gateway.py` | 28 | Live API Gateway endpoint testing |
| `test_cdk_infrastructure.py` | 25 | CDK stacks and infrastructure |
| `test_lambda_functions.py` | 10 | Lambda function structure |
| `test_end_to_end.py` | 10 | Integration tests with deployed AWS |

**Total: 73 tests**

## Quick Start

### Install Dependencies

```bash
pip install pytest pytest-cov moto boto3 requests
```

### Run All Tests

```bash
# Run complete test suite
export AWS_PROFILE=your-aws-profile
pytest tests/ -v

# Expected: 73 passed in ~20s
```

### Run Specific Test Categories

```bash
# API Gateway endpoints (live tests with real API)
pytest tests/test_api_gateway.py -v

# CDK infrastructure
pytest tests/test_cdk_infrastructure.py -v

# Lambda functions
pytest tests/test_lambda_functions.py -v

# Integration tests
pytest tests/test_end_to_end.py -v
```

### Run with Coverage

```bash
pytest tests/ --cov=lambda_functions --cov=stacks --cov=src --cov-report=html
open htmlcov/index.html
```

## Test Coverage

### Current Coverage (73 tests)

| Component | Coverage | Status |
|-----------|----------|--------|
| **CDK Stacks** | 91% | ✅ Excellent |
| **API Gateway** | 100% functional | ✅ Perfect |
| **Lambda Structure** | 100% | ✅ Perfect |
| **AWS Integration** | 100% | ✅ Perfect |
| **Lambda Logic** | 5% | ⚠️ Integration only |
| **Agents** | 0% | ⚠️ Deployed on AgentCore |

### What's Tested

**Infrastructure (CDK)**
- ✅ DynamoDB tables (3 tables, encryption, GSI, TTL)
- ✅ Lambda functions (per-stack resource counts, configuration)
- ✅ SQS queues (main + DLQ, encryption)
- ✅ Step Functions (workflow, error handling)
- ✅ API Gateway (REST API, Cognito authorizer)
- ✅ Secrets Manager (4 secrets, encryption)
- ✅ IAM roles and policies
- ✅ CloudWatch alarms

**API Gateway Endpoints**
- ✅ `/health/agentcore` - AgentCore health check
- ✅ `/config/oauth` - OAuth status
- ✅ `/config/modules` - Module management
- ✅ `/config/enhancement` - Pause/resume
- ✅ `/dashboard/stats` - Activity statistics
- ✅ `/dashboard/activities` - Activity list
- ✅ `/dashboard/system` - System status
- ✅ `/preferences` - User preferences

**Advanced Testing**
- ✅ Error handling (404, 403, 405)
- ✅ Cognito JWT validation (valid/invalid/missing token)
- ✅ Performance (response times <5-10s)
- ✅ Data structure validation
- ✅ CORS configuration
- ✅ Complete workflows (pause → resume)

## Dynamic Configuration

### AWS Resource Discovery

Tests automatically discover deployed AWS resources:

```python
from tests.aws_config import get_aws_config

config = get_aws_config()

# Discover resources
tables = config.get_dynamodb_tables()
lambdas = config.get_lambda_functions()
api_url = config.get_api_gateway_url()

# Print summary
config.print_summary()
```

> Live API Gateway tests authenticate with a Cognito JWT: set the
> `COGNITO_ID_TOKEN` environment variable (ID token from a logged-in user);
> tests are skipped if it is absent.

### Benefits

- ✅ **No hardcoded values** - Works on any environment
- ✅ **Automatic discovery** - Finds resources via CloudFormation/AWS APIs
- ✅ **Cognito auth** - Live API tests use a real Cognito JWT (`COGNITO_ID_TOKEN`)
- ✅ **Profile support** - Uses configured AWS profile

## Test Categories

### Unit Tests (Mock AWS)

Tests that use mocked AWS services (fast, no AWS required):
- Lambda structure and imports
- CDK stack synthesis
- Configuration validation

```bash
# Run unit tests only
pytest tests/test_lambda_functions.py tests/test_cdk_infrastructure.py -v
```

### Integration Tests (Real AWS)

Tests that use deployed AWS resources (requires deployment):
- API Gateway endpoints
- DynamoDB tables
- Step Functions workflows
- Complete end-to-end scenarios

```bash
# Run integration tests
pytest tests/test_api_gateway.py tests/test_end_to_end.py -v
```

## Writing New Tests

### API Gateway Endpoint Test

```python
def test_new_endpoint(self, api_client):
    """Test new API endpoint"""
    response = api_client.get('/new/endpoint')
    
    assert response.status_code == 200
    data = response.json()
    assert 'expected_field' in data
```

### CDK Infrastructure Test

```python
def test_new_resource(self):
    """Test new CDK resource"""
    app = cdk.App()
    stack = MyStack(app, "TestStack")
    template = assertions.Template.from_stack(stack)
    
    template.resource_count_is("AWS::Service::Resource", 1)
```

### Integration Test

```python
def test_new_workflow(self, aws_session):
    """Test new workflow"""
    client = aws_session.client('service')
    response = client.some_operation()
    
    assert response['Status'] == 'Success'
```

## Troubleshooting

### API Gateway Tests Fail

```bash
# Verify API Gateway is deployed
aws apigateway get-rest-apis --profile your-aws-profile

# Check resource discovery
python tests/aws_config.py

# Test manually (Cognito JWT in the Authorization header)
curl -H "Authorization: $COGNITO_ID_TOKEN" "https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod/health/agentcore"
```

### CDK Tests Fail

```bash
# Verify CDK can synthesize
cdk synth --profile your-aws-profile

# Check for syntax errors
python -m py_compile stacks/*.py
```

### Integration Tests Fail

```bash
# Verify AWS credentials
aws sts get-caller-identity --profile your-aws-profile

# Check deployed resources
aws cloudformation list-stacks --profile your-aws-profile
```

## Performance

- **Unit tests**: <5s
- **CDK tests**: <10s  
- **API Gateway tests**: <10s
- **Integration tests**: <5s
- **Complete suite**: <25s

## Next Steps

Done since this suite was written: **Lambda unit tests** (316 mocked tests in `tests/unit/`) and **agent prompt tests** (regression harness in `tests/regression/` + live V1/V2 runners). Remaining ideas:

1. **Load tests** - Test API Gateway under load
2. **Security tests** - Penetration testing for API endpoints
