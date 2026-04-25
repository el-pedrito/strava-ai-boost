# Dependencies

> See also: [System Overview](system-overview.md) | [Dependency Analysis](../analysis/dependency-analysis.md) | [Outdated Components](../technical-debt/outdated-components.md)

## Internal Dependencies

### Stack-to-Stack Dependencies (app.py)
```
CoreInfrastructureStack ─────────────────────────────────────────┐
    │                                                             │
    ├──→ SecurityStack (no dependency on Core)                    │
    │       │                                                     │
    │       └──→ ContentGenerationStack                           │
    │               ├── depends_on: Core (tables, roles, secrets) │
    │               └── depends_on: Security (guardrail)          │
    │                       │                                     │
    │                       └──→ WebhookProcessingStack           │
    │                               ├── depends_on: Core          │
    │                               └── depends_on: Content (state_machine_arn)
    │                                                             │
    ├──→ ApiGatewayStack                                          │
    │       └── depends_on: Core                                  │
    │                                                             │
    ├──→ MonitoringStack                                          │
    │       ├── depends_on: Core                                  │
    │       ├── depends_on: Content                               │
    │       ├── depends_on: Webhook                               │
    │       └── depends_on: API                                   │
    │                                                             │
    └──→ FeedbackLoopStack                                        │
            └── depends_on: Core                                  │
```

### Cross-Stack Resource Sharing
| Producing Stack | Resource | Consuming Stacks |
|---|---|---|
| Core | `activities_table` | Content, Webhook, API, Monitoring, Feedback |
| Core | `user_config_table` | Content, Webhook, API |
| Core | `coaching_sessions_table` | Content, API |
| Core | `dependencies_layer` | Content, Webhook, API, Feedback |
| Core | `strava_oauth_secret` | Content, Webhook, API, Feedback |
| Core | `strava_app_secret` | Content, Feedback |
| Core | `campus_coach_secret` | Content, API |
| Core | `intervals_icu_secret` | Content, API |
| Core | `webhook_lambda_role` | API (shared for config/dashboard/preferences/health Lambdas) |
| Security | `guardrail_id` | Content (via env var in content_agent.py) |
| Content | `state_machine_arn` | Webhook (for StartExecution) |

### Lambda-to-Shared Dependencies
All Lambda functions import from `shared/`:
- `shared.logger` → `get_logger()`, `metrics`, `MetricUnit` (used by all processing/webhook Lambdas)
- `shared.responses` → `create_success_response()`, `create_error_response()`, CORS headers (used by API Lambdas)
- `shared.env_validation` → `validate_env_vars()` (used selectively)
- `shared.strava_oauth` → `refresh_access_token()` (used by activity_fetcher, feedback_analyzer)

### Lambda Processing Dependencies
- `content_generator.py` imports from `processing.workout_analysis` and `processing.modules_processing`
- `modules_processing.py` imports from `modules.registry` and `modules.base_module`
- `activity_processor.py` reads `modules_config` from DynamoDB for Enduraw delay logic

### Frontend-to-API Dependencies
Frontend `api/client.ts` → API Gateway (all endpoints require `x-api-key` header):
- Dashboard page → `GET /dashboard/stats`, `GET /dashboard/activities`, `GET /dashboard/system`
- Configuration page → `GET/POST/DELETE /config/oauth`, `GET/POST /config/modules`, `PUT/DELETE /config/modules/{module_id}`, `GET/POST /config/enhancement`, `GET /config/strava`, `GET /test/strava-connection`
- Preferences page → `GET/POST /preferences`
- Quality page → `GET /dashboard/activities` (with quality metrics)
- Health check → `GET /health/agentcore`

## External Dependencies

### Python Dependencies (requirements.txt)
| Package | Version Spec | Purpose | Category |
|---|---|---|---|
| `aws-cdk-lib` | ==2.219.0 | AWS CDK infrastructure-as-code | Dev/Build |
| `constructs` | >=10.0.0,<11.0.0 | CDK constructs library | Dev/Build |
| `boto3` | >=1.34.0 | AWS SDK for Python | Dev (local) |
| `pydantic` | >=2.0.0 | Data models with validation | Dev (local) |
| `pytest` | >=7.0.0 | Test framework | Dev/Test |
| `pytest-cov` | >=4.0.0 | Test coverage | Dev/Test |
| `pytest-asyncio` | >=0.21.0 | Async test support | Dev/Test |
| `hypothesis` | >=6.0.0 | Property-based testing | Dev/Test |
| `moto` | >=4.2.0 | AWS service mocking | Dev/Test |
| `black` | >=23.0.0 | Code formatter | Dev/Tool |
| `flake8` | >=6.0.0 | Linter | Dev/Tool |
| `mypy` | >=1.0.0 | Type checker | Dev/Tool |
| `typing-extensions` | >=4.0.0 | Typing backports | Dev/Tool |
| `strands-agents` | >=1.0.0 | Strands Agent framework | Runtime (AgentCore) |
| `strands-agents-tools` | >=0.2.0 | Strands Agent tools (Browser) | Runtime (AgentCore) |
| `bedrock-agentcore-starter-toolkit` | >=0.1.21 | AgentCore deployment toolkit | Dev/Build |
| `bedrock-agentcore` | >=1.3.0 | AgentCore runtime SDK | Runtime (AgentCore) |

### Lambda Layer Dependencies (lambda_layer/requirements.txt)
| Package | Version Spec | Purpose |
|---|---|---|
| `requests` | >=2.31.0 | HTTP client for Strava/Intervals.icu APIs |
| `aws-lambda-powertools` | >=2.40.0 | Structured logging, metrics, tracing |

### Frontend Dependencies (frontend/package.json)

**Production Dependencies:**
| Package | Version | Purpose |
|---|---|---|
| `@cloudscape-design/components` | ^3.0.1217 | AWS Cloudscape UI component library |
| `@cloudscape-design/design-tokens` | ^3.0.72 | Cloudscape design tokens |
| `@cloudscape-design/global-styles` | ^1.0.51 | Cloudscape global CSS |
| `react` | ^19.2.0 | UI framework |
| `react-dom` | ^19.2.0 | React DOM renderer |
| `react-router-dom` | ^7.13.1 | Client-side routing |

**Dev Dependencies:**
| Package | Version | Purpose |
|---|---|---|
| `typescript` | ~5.9.3 | TypeScript compiler |
| `vite` | ^7.3.1 | Build tool and dev server |
| `vitest` | ^4.0.18 | Test runner |
| `@vitejs/plugin-react` | ^5.1.1 | React support for Vite |
| `eslint` | ^9.39.1 | Linter |
| `@eslint/js` | ^9.39.1 | ESLint core |
| `eslint-plugin-react-hooks` | ^7.0.1 | React hooks linting |
| `eslint-plugin-react-refresh` | ^0.4.24 | React refresh linting |
| `typescript-eslint` | ^8.48.0 | TypeScript ESLint parser |
| `@testing-library/jest-dom` | ^6.9.1 | DOM matchers for tests |
| `@testing-library/react` | ^16.3.2 | React testing utilities |
| `@testing-library/user-event` | ^14.6.1 | User event simulation |
| `@types/node` | ^24.10.1 | Node.js type definitions |
| `@types/react` | ^19.2.7 | React type definitions |
| `@types/react-dom` | ^19.2.3 | React DOM type definitions |
| `globals` | ^16.5.0 | Global variable definitions |
| `jsdom` | ^28.1.0 | DOM implementation for tests |

### External Service Dependencies
| Service | Usage | Authentication |
|---|---|---|
| Strava API v3 | Activity CRUD, athlete stats, laps, OAuth | OAuth 2.0 (access/refresh tokens) |
| Intervals.icu API v1 | Wellness (CTL/ATL/Form), activities (decoupling) | HTTP Basic Auth (API key) |
| Campus Coach (app.campus.coach) | Training session extraction via web scraping | Username/password via Browser Tool |
| Amazon Bedrock | Claude Sonnet 4.5 model invocation | IAM role-based |
| AgentCore Runtime | Agent invocation, memory operations | IAM role-based |
