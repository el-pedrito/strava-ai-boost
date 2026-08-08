# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- **Webhook origin filtering** — Strava does not sign webhook events, so the
  previous "HMAC-SHA1 verification" was a no-op and anonymous POSTs traversed the
  whole pipeline. `validate_webhook_origin` now drops events whose
  `subscription_id` or `owner_id` do not match the known subscription/athletes,
  answers 200 (Strava disables subscriptions on non-200), and has a
  `WEBHOOK_STRICT_ORIGIN` kill switch. Validated against 339 real events
  (338/338 legitimate accepted, 1 forged rejected).
- **Authenticated path verified** — 21/21 API endpoints require Cognito; missing,
  malformed and forged JWTs are rejected 401; a real SRP-obtained token succeeds.

### Fixed

- **OAuth status uses the refresh token** — `/config/oauth` reported "reconnect"
  on access-token expiry alone (6h lifetime), showing "disconnected" most of the
  day while the pipeline auto-refreshes. Expired-with-refresh-token now reports
  connected (`expired_refreshable`).
- **Token refresh consolidated** — `activity_fetcher` and `feedback_analyzer` now
  delegate to `shared/strava_oauth.refresh_access_token` (was dead code);
  timezone-aware metadata everywhere (was naive `datetime.utcnow()` in one path).
- **Two responsive defects** — Quality table clipped its columns at iPad width
  (`overflow-hidden` → `overflow-x-auto`); FlashToasts overflowed left on 375px
  phones (anchored to both edges below the `sm` breakpoint).
- **Deterministic Lambda assets** — `Code.from_asset` excluded `__pycache__`/`.pyc`,
  so `cdk diff` is again a trustworthy deployed-equals-source signal.
- **npm advisories** — 8 HIGH → 0 (`postcss`, `eslint`, `react-router` 8 with
  `react-router-dom` consolidated, `react-leaflet` 5).
- **Operational scripts** — `reprocess_dlq.sh`, `configure_strava_webhook.sh`,
  `cleanup_strava_webhook.sh` now work with ambient AWS credentials (were hardcoded
  to a named profile; the DLQ recovery tool was unusable).

### Added

- **`scripts/deploy_frontend.sh`** — the frontend had no deploy tooling and
  production served an 11-day-old bundle. Build → S3 sync (preserving the runtime
  `config.json`) → CloudFront invalidation + wait → verify served bundle.
- **`frontend/eslint.config.js`** — `npm run lint` had never worked; flat config
  added, 0 errors / 24 tracked warnings.

### Docs

- Corrected the unfounded "HMAC-SHA1 webhook verification" claim across ROADMAP,
  BACKLOG and the project state.
- Documented the previously-undocumented `shared/` modules
  (`strength_exercises.py`, `campus_status.py`, `llm_models.py`) and the ESLint
  config in AGENTS.md; precised the multi-user readiness claim.
- Recorded remaining findings in BACKLOG (verify_token hardening, webhook
  throttling, uninstall.sh profile drift, stale CDK tests, deferred lint warnings).

## [0.2.1] - 2026-07-24

### Fixed

- **Coach session counting** — enforce `weekly_breakdown` as the sole source for session counts in coach feedback; no more hallucinated sliding window counts crossing ISO week boundaries
- **AgentCore deploy script** — `get_memory_id()` matches memory by ID prefix instead of broken `get_memory(name)` call (API no longer returns name field)
- **Regression baselines gitignored** — `.regression/baseline*.json` removed from tracking (contained deployment-specific ARNs with account ID)

### Docs

- Fix GSI count (was 3, actually 2 — IsoWeekIndex never deployed)
- Fix SECURITY.md branch reference (main → dev)
- Fix regression-evals.md stale "committed" references for baselines

## [0.2.0] - 2026-07-17

### Changed

- **Campus Coach: Browser Tool decommissioned** — the legacy AgentCore Browser
  Tool agent (`campus_coach_agent.py`) and its fallback invoker Lambda were
  removed (2026-07-16); the direct REST API sync (`campus_coach_sync.py`) had
  fully replaced them. Deterministic session matching stays in
  `modules_processing.py`.
- **Coach chat: 5th tool** — added `get_coach_observations` to the `coach_chat`
  runtime so the conversational coach reads long-term memory observations for
  continuity across conversations.
- **Memory fixes** — the coach read a namespace no strategy ever wrote to
  (zero observations retrieved since day one) and the weekly recap memory
  read was triple-broken (invalid namespace, pre-GA API shape, missing IAM):
  both fixed, with a session-type-aware search query. Added the Episodic
  strategy (`CoachingEpisodes`) and migrated all readers to the unified
  `/strategies/{memoryStrategyId}/actors/{actorId}/` namespaces on the single
  shared memory (`content_gen_mem`, 3 strategies); legacy preference records
  migrated (28 + 19 orphans); the leftover empty coach memory was deleted.

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

- **Architecture documentation** — `docs/architecture.md` (AgentCore building
  blocks, three planes, docs freshness contract) with three editable draw.io
  diagrams exported as GitHub-rendered `.drawio.svg` (high-level, detailed,
  AWS services with official icons).
- **Docs anti-drift guard** — `tests/regression/test_docs_sync.py` checks doc
  claims (stack/Lambda counts, single memory, no decommissioned components
  presented as current) against the code; also wired as a Kiro `stop` hook
  (`scripts/check_docs_sync.sh`).
- **Strava deauthorization test coverage** — the existing
  `DELETE /config/oauth` flow (Strava deauthorize + token wipe) covered by
  mocked unit tests.

### Fixed

- **Agent crashes caught by the regression harness** — `max_cadence` formatting
  crash (field never returned by the Strava API) and `average_speed`-as-string
  TypeError on manual/indoor activities.
- **Self-contradicting prompt examples** — four positive examples in the
  content/coach prompts contained banned AI clichés; the model was following
  them. Baseline now 0 fail.
- **Weekly synthesis IAM** — the role could never authorize its own inference
  profile invocation (missing inference-profile ARN); fixed via the central
  registry helpers.
- **Documentation accuracy pass** — all 21 tracked markdown files audited and
  corrected against verified ground truth (8 stacks, 18 Lambdas, single
  memory, MIT-0, current chat architecture in SECURITY.md/CHANGELOG).

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

[Unreleased]: https://github.com/el-pedrito/strava-ai-boost/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/el-pedrito/strava-ai-boost/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/el-pedrito/strava-ai-boost/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/el-pedrito/strava-ai-boost/releases/tag/v0.1.0
