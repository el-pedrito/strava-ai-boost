# Program Structure Reference

> See also: [Project Overview](../project-overview.md) | [Components](../architecture/components.md) | [Modules](../reference/api-reference.md)

## Directory Layout

```
strava-ai-boost/
├── app.py                          # CDK entry point — defines 7 stacks + dependencies
├── cdk.json                        # CDK configuration (region: eu-west-1, feature flags)
├── requirements.txt                # Python dev/CDK dependencies
├── .bedrock_agentcore.yaml         # AgentCore agent deployment config (2 agents)
├── .pre-commit-config.yaml         # Pre-commit hooks (detect-secrets, shellcheck)
├── .env.agentcore                  # AgentCore ARNs and memory IDs (gitignored)
│
├── stacks/                         # CDK Stack Definitions (7 stacks + 1 utility)
│   ├── __init__.py
│   ├── core_infrastructure_stack.py     # DynamoDB tables, IAM roles, Secrets, Lambda Layer
│   ├── security_stack.py               # Bedrock Guardrails, AgentCore Observability, Memory IAM
│   ├── content_generation_stack.py      # Step Functions, Content Generator, Activity Fetcher, Strava Updater, Campus Coach Invoker
│   ├── webhook_processing_stack.py      # SQS queues, Webhook Handler, Activity Processor, Error Handler, CloudWatch Alarms
│   ├── api_gateway_stack.py             # REST API, Config/Dashboard/Preferences/Health Check Lambdas
│   ├── monitoring_stack.py              # CloudWatch alarms, dashboard, SNS topic
│   ├── feedback_loop_stack.py           # Feedback Analyzer Lambda, EventBridge schedule
│   └── env_loader.py                   # Shared .env.agentcore file loader utility
│
├── lambda_functions/               # Lambda Function Code (12 handlers across 5 packages)
│   ├── __init__.py
│   ├── api/                        # API Gateway handlers
│   │   ├── __init__.py
│   │   ├── configuration_api.py         # OAuth, modules, enhancement control, Strava app config
│   │   ├── dashboard_api.py             # Statistics, activity history, system stats
│   │   ├── user_preferences_api.py      # User preferences (tone, length, language, emoji)
│   │   └── agentcore_health_check.py    # AgentCore agent runtime health check
│   │
│   ├── processing/                 # Step Functions workflow Lambdas
│   │   ├── __init__.py
│   │   ├── activity_fetcher.py          # Fetches Strava activity, laps, athlete stats, Intervals.icu
│   │   ├── content_generator.py         # Invokes AgentCore agent for content generation
│   │   ├── modules_processing.py        # Module discovery, activation, per-module processing
│   │   ├── strava_updater.py            # Updates Strava activity title + description
│   │   └── workout_analysis.py          # Workout classification from laps, Enduraw extraction
│   │
│   ├── webhooks/                   # Webhook and event-driven handlers
│   │   ├── __init__.py
│   │   ├── webhook_handler.py           # Strava webhook validation, verification, SQS queueing
│   │   ├── activity_processor.py        # SQS consumer, Step Functions launcher, Enduraw delay
│   │   └── campus_coach_invoker.py      # AgentCore Campus Coach agent invocation
│   │
│   ├── shared/                     # Shared utilities (Lambda Layer)
│   │   ├── __init__.py
│   │   ├── logger.py                    # AWS Lambda Powertools structured logging + metrics
│   │   ├── responses.py                 # CORS headers, success/error response builders
│   │   ├── env_validation.py            # Environment variable validation
│   │   └── strava_oauth.py              # Strava OAuth token refresh utility
│   │
│   └── support/                    # Support and error-handling Lambdas
│       ├── __init__.py
│       ├── feedback_analyzer.py         # Nightly feedback analysis + AgentCore Memory writes
│       └── stepfunctions_error_handler.py # Step Functions failure → DLQ routing
│
├── src/                            # Application Source (agents, modules, config)
│   ├── __init__.py
│   ├── agents/                     # AgentCore Agent Definitions
│   │   ├── __init__.py
│   │   ├── content_agent.py             # Content generation agent (Strands Agent + Memory + Guardrail)
│   │   ├── campus_coach_agent.py        # Campus Coach scraping agent (Browser Tool + Memory)
│   │   ├── embedded_prompts.py          # Complete system prompts (CONTENT_GENERATION_PROMPT, CAMPUS_COACH_PROMPT)
│   │   ├── content_generation_agent.yaml # AgentCore deployment config for content agent
│   │   └── campus_coach_agent.yaml      # AgentCore deployment config for campus coach
│   │
│   ├── modules/                    # Extensible Module System
│   │   ├── __init__.py
│   │   ├── base_module.py               # ABC BaseModule, ModuleRegistry, ModuleConfig, ModuleInsight (Pydantic)
│   │   ├── enduraw_module.py            # Enduraw integration (wind, elevation, weather analysis)
│   │   └── registry.py                  # Auto-registration of all modules on import
│   │
│   └── config/
│       └── llm_config.py               # Centralized LLM configuration (model ID, params, ARN)
│
├── frontend/                       # React + TypeScript Frontend
│   ├── package.json                     # Dependencies: React 19, Cloudscape, react-router-dom
│   ├── vite.config.ts                   # Vite 7 build config
│   ├── tsconfig.json                    # TypeScript 5.9 config
│   └── src/
│       ├── main.tsx                     # React entry point
│       ├── App.tsx                      # Router setup (Dashboard, Config, Preferences, Quality)
│       ├── config.ts                    # API Gateway URL + key configuration
│       ├── api/
│       │   └── client.ts               # Generic fetch wrapper with API key auth
│       ├── types/
│       │   └── index.ts                # TypeScript interfaces (Activity, UserPreferences, ModuleConfig, etc.)
│       ├── pages/
│       │   ├── Dashboard/              # DashboardPage, SystemOverview, ConnectionStatus, ModuleStatus, RecentActivities
│       │   ├── Configuration/          # ConfigurationPage, OAuthConnection, OAuthCallback, ModuleConfiguration, StravaAppSetup
│       │   ├── Preferences/            # PreferencesPage (tone, length, language, emoji, pace zones)
│       │   └── Quality/               # ContentQualityPage (confidence, edit rate, similarity)
│       ├── components/
│       │   ├── ErrorBoundary.tsx        # React error boundary
│       │   └── icons/                  # AppLogo, StravaLogo, AgentCoreLogo, CampusCoachLogo, EndurawLogo
│       ├── hooks/
│       │   ├── useAutoRefresh.ts       # Auto-refresh hook for dashboard polling
│       │   └── useFlashMessages.ts     # Flash message notification hook
│       ├── layouts/
│       │   └── AppLayout.tsx           # Cloudscape AppLayout with sidebar navigation
│       └── utils/
│           ├── formatDate.ts           # Date formatting utility
│           └── statusMapper.ts         # Status-to-badge color mapper
│
├── lambda_layer/                   # Lambda Layer Dependencies
│   └── requirements.txt                # requests, aws-lambda-powertools
│
├── scripts/                        # Deployment and Operations Scripts
│   ├── deploy.sh                        # Full CDK deployment script
│   ├── configure_strava_webhook.sh      # Strava webhook subscription setup
│   ├── cleanup_strava_webhook.sh        # Strava webhook cleanup
│   ├── deploy_agentcore_agents.sh       # AgentCore agent deployment
│   ├── configure_agentcore_integration.sh # AgentCore integration config
│   ├── create_agentcore_memories.sh     # AgentCore Memory setup
│   ├── setup_local_env.sh              # Local development environment setup
│   ├── validate_deployment.sh           # Post-deployment validation
│   ├── reprocess_dlq.sh               # DLQ message reprocessing
│   ├── uninstall.sh                    # Full stack uninstallation
│   └── verify_uninstall.sh            # Uninstallation verification
│
├── tests/                          # Test Suite
│   ├── unit/                       # Unit tests for Lambda functions
│   ├── frontend/                   # Frontend component tests (Vitest + Testing Library)
│   └── infrastructure/             # CDK infrastructure tests (Hypothesis property-based)
│
└── templates/                      # CloudFormation templates (if any)
```

## Entry Points

| Entry Point | File | Purpose |
|---|---|---|
| CDK App | `app.py` | Defines and synthesizes all 7 CDK stacks |
| Frontend | `frontend/src/main.tsx` | React application entry point |
| Webhook Handler | `lambda_functions/webhooks/webhook_handler.handler` | Strava webhook GET/POST |
| Activity Processor | `lambda_functions/webhooks/activity_processor.handler` | SQS → Step Functions |
| Activity Fetcher | `lambda_functions/processing/activity_fetcher.handler` | Step Functions task 1 |
| Content Generator | `lambda_functions/processing/content_generator.handler` | Step Functions task 2 |
| Strava Updater | `lambda_functions/processing/strava_updater.handler` | Step Functions task 3 |
| Campus Coach Invoker | `lambda_functions/webhooks/campus_coach_invoker.handler` | EventBridge → AgentCore |
| Configuration API | `lambda_functions/api/configuration_api.handler` | REST API config endpoints |
| Dashboard API | `lambda_functions/api/dashboard_api.handler` | REST API dashboard endpoints |
| User Preferences API | `lambda_functions/api/user_preferences_api.handler` | REST API preferences endpoints |
| AgentCore Health | `lambda_functions/api/agentcore_health_check.handler` | REST API health endpoint |
| Feedback Analyzer | `lambda_functions/support/feedback_analyzer.lambda_handler` | EventBridge schedule |
| SF Error Handler | `lambda_functions/support/stepfunctions_error_handler.handler` | EventBridge rule |
| Content Agent | `src/agents/content_agent.py` (`app.entrypoint`) | AgentCore runtime |
| Campus Coach Agent | `src/agents/campus_coach_agent.py` (`app.entrypoint`) | AgentCore runtime |

## Module Organization

### Lambda Function Packages
Lambda functions are organized into 5 packages, all deployed as a single code asset (`lambda_functions/`) with a shared Lambda Layer for dependencies:

- **api/** — API Gateway Lambda integrations (4 handlers)
- **processing/** — Step Functions workflow Lambdas (5 files, 3 handlers + 2 utilities)
- **webhooks/** — Event-driven handlers (3 handlers)
- **shared/** — Common utilities available to all Lambdas via imports (4 modules)
- **support/** — Background/error-handling Lambdas (2 handlers)

### CDK Stack Dependencies
Stacks are deployed in dependency order as defined in `app.py`:
1. `CoreInfrastructureStack` — Foundation (no dependencies)
2. `SecurityStack` — Security layer (no dependencies)
3. `ContentGenerationStack` — depends on Core + Security
4. `WebhookProcessingStack` — depends on Core + Content
5. `ApiGatewayStack` — depends on Core
6. `MonitoringStack` — depends on Core + Webhook + Content + API
7. `FeedbackLoopStack` — depends on Core
