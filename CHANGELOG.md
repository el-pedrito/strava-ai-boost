# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Campus Coach: Browser Tool decommissioned** — the legacy AgentCore Browser
  Tool agent (`campus_coach_agent.py`) and its fallback invoker Lambda were
  removed (2026-07-16); the direct REST API sync (`campus_coach_sync.py`) had
  fully replaced them. Deterministic session matching stays in
  `modules_processing.py`.
- **Coach chat: 5th tool** — added `get_coach_observations` to the `coach_chat`
  runtime so the conversational coach reads long-term memory observations for
  continuity across conversations.
- **Memory fixes** — coach feedback loop no longer re-ingests its own outputs;
  added the Episodic strategy (`CoachingEpisodes`) and migrated all readers to
  the unified `/strategies/{memoryStrategyId}/actors/{actorId}/` namespaces on
  the single shared memory (`content_gen_mem`, 3 strategies); the leftover
  coach-specific memory was deleted (2026-07-17).

### Added

- **Strength training extraction + charts** — structured strength program in
  user preferences (Upper A / Upper B / Rappel), automatic extraction of
  exercises/sets/loads from Strava WeightTraining descriptions, progression
  charts in the frontend.
- **Health anomaly detection** — dashboard surfaces training-health anomalies
  (e.g., abnormal HR/pace combinations) computed from activity history.
- **Prompt regression harness (V1 + V2)** — V1 deterministic checks against the
  deployed `content_gen` runtime (`scripts/run_prompt_regression.py`), V2
  managed AgentCore Evaluations with built-in + custom LLM-as-a-Judge evaluators
  (`scripts/run_managed_evals.py`), sharing 8 synthetic fixtures; 36 evaluator
  unit tests run offline.
- **Centralized LLM registry** — all Bedrock model IDs come from
  `src/config/llm_config.py` (mirrored for Lambda bundling), with an anti-drift
  sync test forbidding model-id literals elsewhere.

## [0.1.0] - 2026-07-15

Initial public release — an inspiration sample for building an event-driven,
AI-powered application with Amazon Bedrock, AgentCore, and AWS CDK. Not intended
for production use (see the disclaimer in the README).

### Added

- **Event-driven enhancement pipeline** — Strava webhook → SQS → Step Functions
  (parallel content + coach generation) → assembly → Strava update. 18 Lambda
  functions across 8 CDK stacks.
- **AI content generation** — AgentCore `content_gen` agent (Claude Sonnet 4.5)
  with AgentCore Memory (semantic + user-preference strategies on a single
  shared memory), Bedrock Guardrails, and anti-AI-writing rules. Bedrock
  fallback mode always available.
- **AI training coach** — `coach_agent` writing long-term observations
  (`coaching_observations` session on the shared memory), per-activity feedback
  focused on trends and progression, athlete profile / pace zones / PRs /
  strength program context.
- **Conversational coach** — agentic chat on a dedicated AgentCore Runtime
  (`coach_chat`, FastAPI + Strands): token-by-token streaming over the AG-UI
  protocol, browser POSTs directly to the AgentCore data plane with a customJWT
  authorizer (Cognito ID token as Bearer; `user_id` derived from the
  `custom:strava_id` claim), no proxy and no buffered fallback.
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

- Cognito authentication on all API and frontend routes; the coach chat runtime
  rejects unauthenticated calls (customJWT authorizer, HTTP 401).
- Secrets in AWS Secrets Manager; DynamoDB/S3 encryption; least-privilege IAM;
  CloudWatch Data Protection masking in AgentCore logs.
- Published with a one-page threat model ([docs/THREAT-MODEL.md](docs/THREAT-MODEL.md))
  and an ASH security scan summary ([docs/SECURITY-SCAN.md](docs/SECURITY-SCAN.md)).
- Git history scrubbed of account IDs, user IDs, credentials, and internal
  identifiers prior to release; dependency audits (`pip-audit`, `npm audit`) clean.

[Unreleased]: https://github.com/el-pedrito/strava-ai-boost/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/el-pedrito/strava-ai-boost/releases/tag/v0.1.0
