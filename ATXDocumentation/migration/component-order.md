# Component Migration Order

> See also: [System Overview](../architecture/system-overview.md) | [Dependencies](../architecture/dependencies.md)

## Stack Deployment Order

Stacks must be deployed in dependency order. This is the recommended sequence:

| Order | Stack | Depends On | Critical Resources |
|---|---|---|---|
| 1 | **CoreInfrastructureStack** | None | DynamoDB tables, IAM roles, Secrets Manager, Lambda Layer |
| 2 | **SecurityStack** | None | Bedrock Guardrail, Memory Execution Role, Observability |
| 3 | **ContentGenerationStack** | Core, Security | Step Functions, Content/Fetcher/Updater/Coach Lambdas |
| 4 | **WebhookProcessingStack** | Core, Content | SQS queues, Webhook/Processor Lambdas, Error Handler |
| 5 | **ApiGatewayStack** | Core | REST API, Config/Dashboard/Preferences/Health Lambdas |
| 6 | **FeedbackLoopStack** | Core | FeedbackAnalyzer Lambda, EventBridge Schedule |
| 7 | **MonitoringStack** | Core, Content, Webhook, API | CloudWatch Alarms, Dashboard, SNS |

## Lambda Code Migration Order

Within the Lambda function codebase:

| Order | Component | Rationale |
|---|---|---|
| 1 | **shared/** (logger, responses, env_validation, strava_oauth) | Foundation utilities used by all other Lambda packages |
| 2 | **src/config/llm_config.py** | LLM configuration imported by stacks |
| 3 | **src/modules/** (base_module, registry, enduraw_module) | Module system used by processing Lambdas |
| 4 | **lambda_functions/processing/** (workout_analysis, modules_processing first) | Utilities before handlers |
| 5 | **lambda_functions/processing/** (activity_fetcher, content_generator, strava_updater) | Step Functions task handlers |
| 6 | **lambda_functions/webhooks/** (webhook_handler, activity_processor, campus_coach_invoker) | Event-driven handlers |
| 7 | **lambda_functions/api/** (configuration_api, dashboard_api, user_preferences_api, agentcore_health_check) | API handlers |
| 8 | **lambda_functions/support/** (feedback_analyzer, stepfunctions_error_handler) | Background handlers |
| 9 | **src/agents/** (embedded_prompts, content_agent, campus_coach_agent) | AgentCore agents (deployed separately) |

## Frontend Migration
The frontend is independently deployable and has no compile-time dependency on the backend. Migration order:
1. **config.ts** — API Gateway URL and key configuration
2. **types/index.ts** — TypeScript interfaces
3. **api/client.ts** — API client
4. **utils/** — Formatting utilities
5. **hooks/** — Custom React hooks
6. **components/** — Shared components (ErrorBoundary, icons)
7. **layouts/** — AppLayout
8. **pages/** — Page components (Dashboard, Configuration, Preferences, Quality)
9. **App.tsx, main.tsx** — Application shell
