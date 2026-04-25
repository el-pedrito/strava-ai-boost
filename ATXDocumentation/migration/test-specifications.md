# Test Specifications

> See also: [Validation Criteria](validation-criteria.md) | [Code Metrics](../analysis/code-metrics.md)

## Test Suite Overview

The project has approximately 236 tests across 3 test categories:

| Category | Approx Count | Framework | Location |
|---|---|---|---|
| Lambda unit tests | ~123 | pytest + moto | tests/unit/ |
| Frontend tests | ~40 | Vitest + Testing Library | frontend/src/**/__tests__/ |
| Infrastructure/integration | ~73 | pytest + Hypothesis | tests/infrastructure/ |

## Lambda Unit Tests (pytest + moto)

### Patterns
- **AWS mocking**: `moto` library mocks DynamoDB, SQS, Secrets Manager, Step Functions
- **Fixtures**: `@pytest.fixture` for common setup (DynamoDB tables, secrets, SQS queues)
- **Handler testing**: Each Lambda handler tested with synthetic API Gateway or SQS events
- **Error scenarios**: Tests cover success paths, error paths, missing data, and edge cases

### Key Test Areas
- Webhook validation (HMAC-SHA1 signature, verify token, data structure)
- Activity processor skip logic (completed, processing, Enduraw wait, update cooldown)
- Activity fetcher (token refresh, Strava API mocking, data storage)
- Content generator (AgentCore response parsing, preference enforcement, emoji limiting)
- Configuration API (OAuth flow, module management, enhancement control)
- Dashboard API (statistics queries, activity listing)
- User preferences (GET/POST operations, validation)

## Frontend Tests (Vitest + Testing Library)

### Patterns
- **Component rendering**: `@testing-library/react` `render()` with assertions on DOM content
- **User interaction**: `@testing-library/user-event` for simulating clicks, form inputs
- **API mocking**: `vi.mock()` for `api/client.ts` to mock API responses
- **Setup**: `frontend/src/test/setup.ts` configures jsdom environment

### Key Test Areas
- ErrorBoundary: Tests error catching and fallback UI rendering
- API client: Tests request building, error handling, API key inclusion
- Utility functions: `formatDate`, `statusMapper` unit tests

## Infrastructure Tests (pytest + Hypothesis)

### Patterns
- **CDK synthesis**: Tests that `cdk synth` produces valid CloudFormation templates
- **Property-based testing**: Hypothesis framework generates random inputs for configuration validation
- **Resource assertion**: Validates CDK-generated resources have correct properties (table names, Lambda configs, IAM policies)

### Key Test Areas
- Stack synthesis without errors
- DynamoDB table configuration (partition keys, GSIs, TTL, encryption)
- Lambda function configuration (runtime, timeout, memory, environment variables)
- IAM policy validation (least privilege, correct resource ARNs)
- Step Functions workflow structure
- SQS queue configuration (visibility timeout, DLQ, encryption)

## Running Tests

```bash
# Backend tests
pytest tests/ -v --cov=lambda_functions --cov=src

# Frontend tests
cd frontend && npm run test

# Infrastructure tests
pytest tests/infrastructure/ -v

# All tests
pytest && cd frontend && npm run test
```
