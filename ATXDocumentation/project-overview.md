# Strava AI Boost — Project Overview

## Purpose

Strava AI Boost is a **serverless, AI-powered activity enhancement system** that automatically generates personalized titles and descriptions for Strava activities. When an athlete completes a workout and uploads it to Strava, the system intercepts the webhook event, fetches comprehensive activity data (laps, athlete stats, fitness metrics from Intervals.icu, training sessions from Campus Coach), and uses Amazon Bedrock (Claude Sonnet 4.5) via AgentCore to generate rich, first-person narratives that reflect the athlete's personal style, training plan, and physiological context.

## Technology Stack

| Layer | Technology | Version |
|---|---|---|
| **Infrastructure-as-Code** | AWS CDK (Python) | 2.219.0 |
| **Runtime** | Python | 3.12 |
| **AI/ML** | Amazon Bedrock (Claude Sonnet 4.5), AgentCore (Strands Agents) | strands-agents ≥1.0.0, bedrock-agentcore ≥1.3.0 |
| **Compute** | AWS Lambda (12 functions) | Python 3.12 runtime |
| **Orchestration** | AWS Step Functions | Standard workflows |
| **Messaging** | Amazon SQS (with DLQ) | — |
| **Database** | Amazon DynamoDB (3 tables) | On-demand billing |
| **API** | Amazon API Gateway (REST, 2 APIs) | Regional endpoint |
| **Secrets** | AWS Secrets Manager (4 secrets) | — |
| **Monitoring** | Amazon CloudWatch, X-Ray, SNS | — |
| **Scheduling** | Amazon EventBridge | Cron rules |
| **Frontend** | React 19, TypeScript 5.9, Vite 7.3, Cloudscape Design System | — |
| **External APIs** | Strava API v3, Intervals.icu API, Campus Coach (web scraping) | — |

## Key Metrics

| Metric | Value |
|---|---|
| Source files (Python) | ~437 |
| Source files (TypeScript/TSX) | 34 |
| Shell scripts | 11 |
| Lines of code (stacks) | ~2,485 |
| Lines of code (lambda_functions) | ~5,973 |
| Lines of code (src/agents + modules) | ~4,145 |
| Lines of code (frontend) | ~2,855 |
| Lines of code (scripts) | ~5,002 |
| Lines of code (tests) | ~2,679 |
| CDK Stacks | 7 |
| Lambda Functions | 12 |
| DynamoDB Tables | 3 |
| API Gateway APIs | 2 (Local Interface + Webhook) |
| Secrets Manager Secrets | 4 |
| AgentCore Agents | 2 (Content Generation, Campus Coach) |

## System Architecture (High Level)

```
Strava Webhook → API Gateway → Lambda (Webhook Handler)
                                      ↓
                               SQS Queue (with DLQ)
                                      ↓
                          Lambda (Activity Processor)
                                      ↓
                          Step Functions Workflow
                          ┌─────────────────────┐
                          │ 1. Fetch Activity    │ (Strava API + Intervals.icu)
                          │ 2. Generate Content  │ (AgentCore + Bedrock)
                          │ 3. Update Strava     │ (Strava API PUT)
                          └─────────────────────┘

React Frontend → API Gateway → Lambda (Config/Dashboard/Preferences)
                                      ↓
                              DynamoDB + Secrets Manager

EventBridge Schedule → Lambda (Feedback Analyzer) → AgentCore Memory
EventBridge Schedule → Lambda (Campus Coach Invoker) → AgentCore Browser Tool → DynamoDB
```

## CDK Stack Dependency Graph

```
CoreInfrastructureStack (DynamoDB, IAM, Secrets, Lambda Layer)
    ├── SecurityStack (Bedrock Guardrails, AgentCore Observability)
    │       └── ContentGenerationStack (Step Functions, Content Generator, Activity Fetcher, Strava Updater, Campus Coach Invoker)
    │               └── WebhookProcessingStack (SQS, Webhook Handler, Activity Processor, Error Handler)
    ├── ApiGatewayStack (REST API, Config/Dashboard/Preferences/Health Lambdas)
    ├── MonitoringStack (CloudWatch Alarms, Dashboard, SNS)
    └── FeedbackLoopStack (Feedback Analyzer, EventBridge Schedule)
```

## Key Architectural Decisions

1. **Serverless-first**: All compute runs on AWS Lambda with no persistent infrastructure
2. **Dual-mode AI**: AgentCore (primary) with Bedrock direct invoke as fallback
3. **Zero AWS SDK in frontend**: React app communicates exclusively via API Gateway REST endpoints with API key auth
4. **DynamoDB as data bus**: Activity data stored in DynamoDB to avoid Step Functions 256KB payload limit
5. **Infinite loop prevention**: Status-based skip logic prevents webhook update loops
6. **Module pattern**: Extensible module system (base_module + registry) for Campus Coach, Enduraw, Intervals.icu
7. **Memory-driven personalization**: AgentCore Memory (STM + LTM) learns user preferences from feedback diffs

## Related Documentation

- [Architecture Overview](architecture/system-overview.md)
- [Technical Debt Report](technical-debt-report.md)
- [Behavioral Documentation](behavior/workflows.md)
- [Reference: Program Structure](reference/program-structure.md)
