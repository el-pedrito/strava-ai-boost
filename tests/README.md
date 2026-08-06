# Test Suite for Strava AI Boost

Integration test suite with dynamic AWS resource discovery.

> This README covers the **integration suite** (live AWS). Two other suites live alongside:
> - `tests/unit/` — 578 mocked Lambda unit tests, no AWS credentials (`pytest tests/unit/`)
> - `tests/regression/` — 43 prompt-regression & docs-sync tests + live runners (see `docs/design/regression-evals.md`)

## Test Files

| File | Tests | Description |
|------|-------|-------------|
| `conftest.py` | - | Pytest configuration and shared fixtures |
| `aws_config.py` | - | Dynamic AWS resource discovery |
| `test_api_gateway.py` | 27 | Live API Gateway endpoint testing |
| `test_cdk_infrastructure.py` | 25 | CDK stacks and infrastructure |
| `test_lambda_functions.py` | 8 | Lambda function structure |
| `test_end_to_end.py` | 10 | Integration tests with deployed AWS |

**Total: 70 tests**

## Quick Start

### Install Dependencies

```bash
# Same venv as the other suites (see CONTRIBUTING.md); Python 3.12 to match Lambda.
pip install -r requirements.txt
```

### Run All Tests

```bash
# Run complete test suite
pytest tests/ -v

# Measured 2026-08-06 without a profile: 29 passed, 15 failed, 26 skipped.
# The 26 skips are the live API tests (no COGNITO_ID_TOKEN - read the warning below).
# The 15 failures are NOT your setup; see "Known broken" in Test Coverage.
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

### Measured 2026-08-06 (`--cov=lambda_functions --cov=stacks --cov=src`)

Measured from the **offline** suites (`tests/unit/`, `tests/regression/`,
`tests/test_cdk_infrastructure.py`). The live API and end-to-end tests are excluded on
purpose — see the warning below.

| Component | Coverage | Notes |
|-----------|----------|-------|
| `lambda_functions/` | **45%** | processing 51%, webhooks 51%, shared 69%, api 35%, support 17% |
| `stacks/` | **67%** | via CDK synth tests; 4 of 8 stacks at 0% (feedback_loop, frontend_hosting, security, voice_debrief) |
| `src/` | **37%** | `coach_chat` 80%, `agents` 6% (agent bodies run on AgentCore, not locally) |
| API Gateway endpoints | functional only | live tests skip without `COGNITO_ID_TOKEN` |

Reproduce:

```bash
pytest tests/unit/ tests/regression/ tests/test_cdk_infrastructure.py \
  --cov=lambda_functions --cov=stacks --cov=src --cov-report=term
```

> ⚠️ **Known broken (pre-existing, verified at `386bd55`)** — the integration suite does not
> currently pass. Measured 2026-08-06: **29 passed, 15 failed, 26 skipped**.
>
> - **5 stale CDK resource counts** in `test_cdk_infrastructure.py`: expects 3 Secrets
>   Manager secrets (there are 4), 4 Lambdas in the Content stack (5), 6 in the API stack
>   (4), and an EventBridge rule that moved. The assertions need updating, not the stacks.
> - **10 discovery failures** caused by the harness, not by AWS. The session-scoped
>   `autouse` `setup_environment` fixture in `conftest.py` sets **fake AWS credentials** and
>   `AWS_REGION=eu-west-1` for every test under `tests/`, including this suite. Ambient
>   credentials are therefore clobbered, so a named `AWS_PROFILE` is **required** for a live
>   run — `profile_name` is the only path that bypasses the fake env credentials. Region is
>   read from `TEST_AWS_REGION` for the same reason.
>
> Properly separating the mocked env from the live suite (scoping the fixture to
> `tests/unit/`, or skipping it for integration) is the real fix and has not been done.

> 🛑 **Do not run the live API suite against a real account.**
> `test_api_gateway.py::test_preferences_update` POSTs a 4-field payload to `/preferences`,
> and the handler does `SET user_preferences = :prefs` — a wholesale replace, not a merge.
> On the live account that destroys `athlete_profile`, `pace_zones`, `personal_records`,
> `strength_program` and the full `strength_history` (64 entries as of 2026-08-06). The test
> reads the current values into `current` and never restores them. Point-in-time recovery is
> enabled on `strava-ai-boost-user-configuration`, so it is recoverable, but only by
> restoring the table. Fix the test to restore (or to use a throwaway user) before setting
> `COGNITO_ID_TOKEN`.

### What's Tested

**Infrastructure (CDK)**
- ✅ DynamoDB tables (4 tables, encryption, GSI, TTL)
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
- ✅ Error handling (400, 403, 404)
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

Done since this suite was written: **Lambda unit tests** (578 mocked tests in `tests/unit/`) and **agent prompt tests** (regression harness in `tests/regression/` + live V1/V2 runners). Remaining ideas:

1. **Load tests** - Test API Gateway under load
2. **Security tests** - Penetration testing for API endpoints
