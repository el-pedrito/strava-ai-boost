# Code Metrics

> See also: [Dependency Analysis](dependency-analysis.md) | [Security Patterns](security-patterns.md) | [Project Overview](../project-overview.md)

## File Counts by Type

| Type | Count |
|---|---|
| Python (.py) | ~437 (including tests, venv excluded) |
| TypeScript/TSX | 34 |
| Shell scripts | 11 |
| YAML config | 4 (agent configs, pre-commit, agentcore) |
| JSON config | 3 (cdk.json, package.json, tsconfig) |

## Lines of Code by Component

| Component | LOC | Files | Purpose |
|---|---|---|---|
| stacks/ | ~2,485 | 9 | CDK infrastructure definitions |
| lambda_functions/ | ~5,973 | 24 | Lambda function code (all packages) |
| src/ (agents + modules + config) | ~4,145 | 12 | AgentCore agents, modules, LLM config |
| frontend/src/ | ~2,855 | 34 | React/TypeScript frontend |
| scripts/ | ~5,002 | 11 | Deployment and operations scripts |
| tests/ | ~2,679 | — | Unit, frontend, and infra tests |
| **Total application code** | **~23,139** | | Excluding tests and scripts |

## Function/Handler Counts

| Module | Handler Functions | Utility Functions |
|---|---|---|
| lambda_functions/api/ | 4 handlers | ~20 route handlers |
| lambda_functions/processing/ | 3 handlers | ~15 helper functions |
| lambda_functions/webhooks/ | 3 handlers | ~12 helper functions |
| lambda_functions/shared/ | 0 | 8 utility functions |
| lambda_functions/support/ | 2 handlers | ~5 helper functions |
| src/agents/ | 2 entrypoints | ~15 functions |
| src/modules/ | 0 | ~40 methods (BaseModule + Enduraw) |

## Cyclomatic Complexity Assessment (Key Functions)

| Function | File | Estimated Complexity | Notes |
|---|---|---|---|
| `should_skip_processing` | activity_processor.py | High | 6+ conditional branches for loop prevention |
| `invoke` (content agent) | content_agent.py | High | Large function (~400 lines) with many conditional paths |
| `classify_workout_from_laps` | workout_analysis.py | Medium | 4 classification paths based on pace variability |
| `fetch_intervals_icu_data` | activity_fetcher.py | Medium | Multiple API calls with fallback logic |
| `handle_webhook_notification` | webhook_handler.py | Medium | Signature verification + validation + SQS queueing |
| `_parse_agent_response` | content_generator.py | Medium | JSON parsing with multiple extraction strategies |
| `handler` (configuration_api) | configuration_api.py | Medium | Routes by resource path (6+ routes) |
| `enforce_preferences` | content_generator.py | Low-Medium | Emoji limiting + length enforcement |

## Largest Files (by LOC)

| File | Approximate LOC | Notes |
|---|---|---|
| `src/agents/content_agent.py` | ~700 | Content generation agent with full prompt building |
| `src/agents/embedded_prompts.py` | ~550 | System prompts (mostly text content) |
| `src/modules/enduraw_module.py` | ~600 | Enduraw integration with wind/elevation analysis |
| `src/modules/base_module.py` | ~350 | Base module + registry classes |
| `lambda_functions/processing/activity_fetcher.py` | ~450 | Strava API calls + data storage |
| `lambda_functions/processing/content_generator.py` | ~350 | AgentCore invocation + response parsing |
| `lambda_functions/webhooks/webhook_handler.py` | ~350 | Webhook validation + SQS queueing |
| `lambda_functions/webhooks/activity_processor.py` | ~300 | SQS consumer + Step Functions launcher |
| `stacks/content_generation_stack.py` | ~350 | Step Functions + Lambda definitions |
