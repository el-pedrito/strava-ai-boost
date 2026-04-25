# Dependency Analysis

> See also: [Architecture Dependencies](../architecture/dependencies.md) | [Outdated Components](../technical-debt/outdated-components.md) | [Code Metrics](code-metrics.md)

## Internal Dependency Graph

### Stack Dependencies
```
Core ←── Security (independent)
Core ←── Content (depends: Core, Security)
Core ←── Webhook (depends: Core, Content)
Core ←── API (depends: Core)
Core ←── Monitoring (depends: Core, Content, Webhook, API)
Core ←── Feedback (depends: Core)
```

### Lambda Import Dependencies
```
processing/content_generator.py
  ├── processing/workout_analysis.py (classify_workout_from_laps, extract_enduraw_report)
  ├── processing/modules_processing.py (get_active_modules, apply_module_processing)
  └── shared/logger.py (get_logger)

processing/modules_processing.py
  ├── modules/__init__.py → modules/registry.py (module_registry, ModuleConfig)
  └── shared/logger.py

processing/activity_fetcher.py
  └── shared/logger.py

webhooks/activity_processor.py
  └── shared/logger.py (get_logger, metrics, MetricUnit)

webhooks/webhook_handler.py
  └── shared/logger.py

api/*.py
  └── shared/responses.py (create_success_response, create_error_response, CORS_HEADERS)
  └── shared/logger.py (selective)
```

### Frontend Import Dependencies
```
App.tsx → pages/{Dashboard, Configuration, Preferences, Quality}
       → layouts/AppLayout.tsx
       → components/ErrorBoundary.tsx

pages/* → api/client.ts (api.get, api.post, api.delete)
       → types/index.ts
       → hooks/useFlashMessages.ts, useAutoRefresh.ts
       → utils/formatDate.ts, statusMapper.ts
       → components/icons/*

api/client.ts → config.ts (getConfig → apiGatewayUrl, apiGatewayKey)
```

## External Dependency Criticality

### Critical (system fails without)
| Dependency | Used By | Impact |
|---|---|---|
| `boto3` (AWS SDK) | All Lambda functions | Core AWS service access |
| `requests` | Activity Fetcher, Feedback Analyzer, Enduraw Module | Strava API, Intervals.icu API |
| `aws-lambda-powertools` | All Lambda functions | Structured logging, metrics |
| `strands-agents` | Content Agent, Campus Coach Agent | AI agent framework |
| `bedrock-agentcore` | Content Agent, Campus Coach Agent | AgentCore runtime |
| `react`, `react-dom` | Frontend | UI framework |
| `@cloudscape-design/components` | Frontend | Component library |

### Important (degraded operation without)
| Dependency | Used By | Impact |
|---|---|---|
| `pydantic` | BaseModule, ModuleConfig, ModuleInsight | Data validation for modules |
| `react-router-dom` | Frontend | Page navigation |
| `strands-agents-tools` | Campus Coach Agent | Browser Tool for scraping |

### Dev/Build Only
| Dependency | Used By |
|---|---|
| `aws-cdk-lib`, `constructs` | CDK stack synthesis |
| `pytest`, `moto`, `hypothesis` | Testing |
| `black`, `flake8`, `mypy` | Code quality |
| `vite`, `vitest`, `typescript` | Frontend build and test |
| `eslint`, `typescript-eslint` | Linting |

## Transitive Dependencies (Lambda Layer)

The Lambda Layer includes `requests` and `aws-lambda-powertools`. Key transitive dependencies:
- `requests` → `urllib3`, `certifi`, `charset-normalizer`, `idna`
- `aws-lambda-powertools` → `jmespath`, `typing-extensions` (Powertools pulls in minimal transitive deps)

These are packaged in the Lambda Layer and shared across all 12 Lambda functions.

## Dependency Version Risk Assessment

| Risk Level | Packages | Concern |
|---|---|---|
| **Low risk** | Frontend packages (caret ranges + modern base) | npm auto-resolves compatible versions |
| **Medium risk** | Python packages (minimum version specifiers) | `pip install` resolves latest compatible, could introduce breaking changes |
| **No risk** | CDK lib (pinned at 2.219.0) | Deterministic, but misses updates |
