# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.4](https://github.com/el-pedrito/strava-ai-boost/compare/v0.2.3...v0.2.4) (2026-08-20)


### Bug Fixes

* **coach:** ground every published figure in a computed fact ([8e665de](https://github.com/el-pedrito/strava-ai-boost/commit/8e665de7fc9002c700a1bc313a0e0e98a1c677a9))
* **coach:** ground every published figure in a computed fact ([18e7054](https://github.com/el-pedrito/strava-ai-boost/commit/18e70543e77c965b84353773fd6e9e50ce0c4a30))

## [0.2.3](https://github.com/el-pedrito/strava-ai-boost/compare/v0.2.2...v0.2.3) (2026-08-09)


### Features

* **coach:** always publish the weekly recap, injected in code ([3fb8a67](https://github.com/el-pedrito/strava-ai-boost/commit/3fb8a67d3017fee60d1c0d0a29b22a9e9b69e2b9))


### Bug Fixes

* **coach:** code-owned weekly recap line + claim-level verifier ([e638f50](https://github.com/el-pedrito/strava-ai-boost/commit/e638f502ad1bfd300ed47f216e9b65467def4b3a))
* **coach:** don't count the Campus PPG as an own muscu (week totals) ([2049022](https://github.com/el-pedrito/strava-ai-boost/commit/2049022ae5deb36757e3e3dd2c9a512790962922))
* **coach:** verifier catches PPG counted as muscu + wrong weekly total ([daaeb56](https://github.com/el-pedrito/strava-ai-boost/commit/daaeb56c71167ecf5d5268c6962df1da6b0de3fc))

## [0.2.2](https://github.com/el-pedrito/strava-ai-boost/compare/v0.2.1...v0.2.2) (2026-08-08)


### Features

* **coach_chat:** give the chat code-computed figures instead of raw lists ([eb9c4c2](https://github.com/el-pedrito/strava-ai-boost/commit/eb9c4c2aced865cc9575e3cb3990e2ddd640382c))
* **coach:** verify stated figures against computed ones before publishing ([da5cd6f](https://github.com/el-pedrito/strava-ai-boost/commit/da5cd6f1bc74a6ec58e52783228ad33271c641f4))
* **frontend:** chart the per-session strength totals ([386bd55](https://github.com/el-pedrito/strava-ai-boost/commit/386bd5582950487b6b3dd62441cf2c7895cbd112))
* **preferences:** structured body weight and height ([c5697e1](https://github.com/el-pedrito/strava-ai-boost/commit/c5697e1ac49a7e7c0d90066ca5b4abec5d53d148))
* **scripts:** add the missing frontend deployment script ([69fc66a](https://github.com/el-pedrito/strava-ai-boost/commit/69fc66a4143d5186abc9d90a2702bd7770dd85e6))
* **strength:** single code-authoritative definition of session tonnage ([a6b08b5](https://github.com/el-pedrito/strava-ai-boost/commit/a6b08b5b407a0413e380e7be634fe5c4868499a1))


### Bug Fixes

* **campus:** capture PPG exercise names + reps in sync ([0f056c4](https://github.com/el-pedrito/strava-ai-boost/commit/0f056c4464e8d2b6651e4f6a0b0de98fccb53b36))
* **campus:** capture PPG exercise names and reps in sync ([2bba166](https://github.com/el-pedrito/strava-ai-boost/commit/2bba16631bf6a967a1f3ed8abb94bd5f98b5af7e))
* **campus:** retire the legacy status field as a completion source ([234da78](https://github.com/el-pedrito/strava-ai-boost/commit/234da7807284163876b7578fa44a59509ca7d584))
* **campus:** stop closing the planned PPG on every gym session ([b27d6e4](https://github.com/el-pedrito/strava-ai-boost/commit/b27d6e4f44170de58585b1aa41e005fce7b2927f))
* **cdk:** exclude bytecode caches from Lambda assets for deterministic deploys ([0f1b1d2](https://github.com/el-pedrito/strava-ai-boost/commit/0f1b1d2801107643a787937d48e0417ba6dfa089))
* **coach:** compute every weekly figure in code, with disjoint coverage ([806f8ed](https://github.com/el-pedrito/strava-ai-boost/commit/806f8edcb0eaeca3e9afe1e28828b0c7543055a0))
* **coach:** flag sliding-window weekly counts (N courses en N jours) ([e4a9b9b](https://github.com/el-pedrito/strava-ai-boost/commit/e4a9b9b5d516b43a6a8b3761598a00b673a89172))
* **coach:** flag sliding-window weekly counts (N courses en N jours) ([d4e6d42](https://github.com/el-pedrito/strava-ai-boost/commit/d4e6d4209b67831c960468413c895f05055b5a6d))
* **coach:** normalize strength exercise names ([be2b987](https://github.com/el-pedrito/strava-ai-boost/commit/be2b987e2063eb5e8411f80cf046ece2bb768e8c))
* **coach:** secure summaries and preserve Campus state ([e420d36](https://github.com/el-pedrito/strava-ai-boost/commit/e420d36fff98a312d6c17646ff0e952e7e13f683))
* **coach:** stop the week gate being walked around, and log the strip ([48ec25a](https://github.com/el-pedrito/strava-ai-boost/commit/48ec25aa86f26874f3817caf3a5227b844dcd3df))
* **content:** faithful PPG exercise naming, no invented loads ([4a07b8b](https://github.com/el-pedrito/strava-ai-boost/commit/4a07b8b04e77bc1b34f8da0d5fb3449b649bb19a))
* **content:** feed agent the preserved original description, not current Strava text ([3afd34d](https://github.com/el-pedrito/strava-ai-boost/commit/3afd34d7672966a35b265d8bd37226ed37b9a6cf))
* **content:** full Campus PPG integration + load mapping + bodyweight default ([4a3422f](https://github.com/el-pedrito/strava-ai-boost/commit/4a3422f7ba9daab596ad77487095f715e0229702))
* **content:** ground HR zone in Strava data + release-please CI ([7d53599](https://github.com/el-pedrito/strava-ai-boost/commit/7d5359998a9a746571ee7ebdd8de07bff10c0441))
* **content:** ground HR zone in Strava data, stop agent inventing zone 1 ([a75a5db](https://github.com/el-pedrito/strava-ai-boost/commit/a75a5dbf9504ebfc0c0156b8baa3a1b524cec34c))
* **content:** integrate full Campus PPG session, map loads, bodyweight default ([fb82b9c](https://github.com/el-pedrito/strava-ai-boost/commit/fb82b9c31c2e159258d151b131ea9281fc663023))
* **content:** invented time-of-day + rando/rendo garble ([f720239](https://github.com/el-pedrito/strava-ai-boost/commit/f720239e34a3ca7f29d8cfd0a111dc0d9f04aae7))
* **content:** name PPG exercises from Campus data, no invented loads ([5f47418](https://github.com/el-pedrito/strava-ai-boost/commit/5f474188c484511dd7a7bbbaeffe4fbdf8c6c0be))
* **content:** stop invented time-of-day and rando/rendo garble ([0c2b66c](https://github.com/el-pedrito/strava-ai-boost/commit/0c2b66c67232fa126782eecfc8822037609ab449))
* **content:** use preserved original description for the agent input ([d215de6](https://github.com/el-pedrito/strava-ai-boost/commit/d215de64e76efac343b74368814b87845f31fb34))
* **deploy:** fail the preflight on the toolchain gaps that bite silently ([93ccfc1](https://github.com/el-pedrito/strava-ai-boost/commit/93ccfc1e640f9485bf7b7182fe2c0e8d3252dff6))
* **frontend:** clear all npm security advisories ([48571fc](https://github.com/el-pedrito/strava-ai-boost/commit/48571fc31bf6364999b44fb74e80c6e93b5d1929))
* **frontend:** localize and improve Coach chart accessibility ([71746ba](https://github.com/el-pedrito/strava-ai-boost/commit/71746ba02114e034863a8553d5fa60111d435661))
* **frontend:** repair two responsive defects on authenticated pages ([536a7fb](https://github.com/el-pedrito/strava-ai-boost/commit/536a7fbc69c1548a44d4219f65215db414712900))
* **frontend:** WCAG AA contrast + de-eyebrow coach labels ([9252684](https://github.com/el-pedrito/strava-ai-boost/commit/9252684d5bbfe71f5d58634a972b8c7b587d6399))
* **metrics:** flush the metrics that were being recorded and dropped ([0eb78b1](https://github.com/el-pedrito/strava-ai-boost/commit/0eb78b112b8b650df781cbcae89b0a1b93c2a207))
* **oauth:** base connection status on the refresh token and unify token refresh ([584c811](https://github.com/el-pedrito/strava-ai-boost/commit/584c811207945481484fb4ddc506100d8c5c3961))
* **prompts:** route every figure to its single source, in both prompts ([b7359e2](https://github.com/el-pedrito/strava-ai-boost/commit/b7359e2669c75eabcf7b519ea0a9702ce777760f))
* **renfo:** stop reprocess feedback loop + keep athlete's real loads ([18f1467](https://github.com/el-pedrito/strava-ai-boost/commit/18f146769c879099cc06f77471381893e95c2fcf))
* **renfo:** stop reprocess feedback loop, preserve athlete's real loads ([9d0cfa9](https://github.com/el-pedrito/strava-ai-boost/commit/9d0cfa9e114c93dd22ec7276c632fcf627ba0e12))
* **scripts:** stop depending on a named AWS profile, sync Campus more often ([c77b406](https://github.com/el-pedrito/strava-ai-boost/commit/c77b40646be6e1db7d372d34b61b2324c2c26da6))
* **scripts:** support ambient AWS credentials and repair validation drift ([e479ed9](https://github.com/el-pedrito/strava-ai-boost/commit/e479ed9a678e997c426520150290f84d8148538c))
* **scripts:** support ambient AWS credentials in operational scripts ([eafd4a3](https://github.com/el-pedrito/strava-ai-boost/commit/eafd4a3bf3404fb59bed06385ac1a546b10fecc9))
* **strength:** repair the history write, and stop the lossy extraction schema ([b9bdb64](https://github.com/el-pedrito/strava-ai-boost/commit/b9bdb6496bb9a357bb4a999c4fed42fa0bf2c360))
* **synth:** stop a missing PyYAML silently blanking the AgentCore memory id ([d01768d](https://github.com/el-pedrito/strava-ai-boost/commit/d01768d7c2cf422220e548081e7ac4c0cfd4b3cc))
* **webhook:** drop events that do not come from our own subscription ([309f091](https://github.com/el-pedrito/strava-ai-boost/commit/309f0912212b5259df009aef3c01406126872ec6))
* **weeks:** make the ISO week label the only week identity ([2e04494](https://github.com/el-pedrito/strava-ai-boost/commit/2e044948f2b2ba32fba7f9339501f891717bc791))


### Performance Improvements

* **frontend:** lazy-load English locale out of the initial bundle ([bbe7c24](https://github.com/el-pedrito/strava-ai-boost/commit/bbe7c24938df09089e469831531271ad41693bd1))

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
