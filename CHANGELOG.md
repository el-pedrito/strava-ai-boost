# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-15

Initial public release — an inspiration sample for building an event-driven,
AI-powered application with Amazon Bedrock, AgentCore, and AWS CDK. Not intended
for production use (see the disclaimer in the README).

### Added

- **Event-driven enhancement pipeline** — Strava webhook → SQS → Step Functions
  (parallel content + coach generation) → assembly → Strava update. 17 Lambda
  functions across 7 CDK stacks.
- **AI content generation** — AgentCore `content_gen` agent (Claude Sonnet 4.5)
  with AgentCore Memory (semantic + user-preference strategies), Bedrock Guardrails,
  and anti-AI-writing rules. Bedrock fallback mode always available.
- **AI training coach** — `coach_agent` with long-term memory
  (`coaching_observations`), per-activity feedback focused on trends and progression,
  athlete profile / pace zones / PRs / strength program context.
- **Conversational coach** — token-by-token streaming over the AG-UI protocol
  (Starlette + Lambda Web Adapter, Function URL with `AWS_IAM` + SigV4 via Cognito
  Identity Pool), with transparent fallback to a buffered endpoint.
- **Module system** — Campus Coach (direct REST API sync, deterministic session
  matching), Enduraw (weather/wind), Intervals.icu (CTL/ATL/Form/HRV/decoupling).
- **Voice features** — per-activity audio debrief and weekly audio recap
  (Bedrock → Polly Generative).
- **React + Tailwind frontend** — CloudFront + S3 (OAC), Cognito authentication
  (no self-registration), dark/light mode, mobile-first, i18n FR/EN, PWA,
  onboarding flow, Dashboard / Coach / Quality / Configuration / Preferences pages.
- **Observability & ops** — AWS Lambda Powertools structured logging, CloudWatch
  GenAI dashboard, DLQ + alarms → SNS, monthly budget alert, cost allocation tags.
- **209 tests** (165 backend + 44 frontend).

### Security

- Cognito authentication on all API and frontend routes; coach streaming endpoint
  uses `AWS_IAM` (never `NONE`).
- Secrets in AWS Secrets Manager; DynamoDB/S3 encryption; least-privilege IAM;
  CloudWatch Data Protection masking in AgentCore logs.
- Published with a one-page threat model ([docs/THREAT-MODEL.md](docs/THREAT-MODEL.md))
  and an ASH security scan summary ([docs/SECURITY-SCAN.md](docs/SECURITY-SCAN.md)).
- Git history scrubbed of account IDs, user IDs, credentials, and internal
  identifiers prior to release; dependency audits (`pip-audit`, `npm audit`) clean.

[0.1.0]: https://github.com/el-pedrito/strava-ai-boost/releases/tag/v0.1.0
