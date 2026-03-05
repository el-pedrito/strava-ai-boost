# Project Audit - Strava AI Boost

**Date**: March 2026 | **Version**: v2.4.0

---

## Scores

| Category | Score | Summary |
|----------|-------|---------|
| Architecture | 8/10 | Clean serverless design, well-separated CDK stacks, proper async workflow |
| Security | 8/10 | Guardrails, encryption, least privilege IAM, secrets management |
| Code Quality | 6/10 | Functional but content_generator.py is a 2050-line monolith |
| Testing | 4/10 | 73 tests but all infrastructure/integration — zero Lambda unit tests |
| Frontend | 7/10 | Cloudscape + React 19, ErrorBoundary, code splitting, but no E2E tests |
| DevOps | 5/10 | Good scripts, no CI/CD pipeline, manual deployments |
| Documentation | 7/10 | Consolidated and clean, AGENTS.md provides good AI context |
| **Global** | **6.5/10** | **Production-functional, needs refactoring and test coverage** |

---

## Strengths

### Architecture
- 7 CDK stacks with clear separation of concerns (Core, Security, Webhook, Content, API, Monitoring, Feedback)
- Step Functions orchestration with SQS + DLQ — proper async event-driven design
- Dual-mode AI (AgentCore primary + Bedrock fallback) ensures resilience
- Modular system: Campus Coach and Enduraw are cleanly isolated modules
- Webhook infinite loop prevention with status tracking and cooldown

### Security
- Bedrock Guardrails for AI safety and prompt injection protection
- All DynamoDB tables encrypted, HTTPS enforced everywhere
- Secrets Manager for OAuth tokens and credentials (no hardcoded secrets)
- Scoped IAM policies with specific resource ARNs
- API Gateway with API key authentication

### Operational
- AWS Lambda Powertools: structured JSON logging, correlation IDs, metrics
- DLQ with reprocessing script for failed messages
- Comprehensive deployment/validation/uninstall scripts
- Shared utilities (`lambda_functions/shared/`) for cross-cutting concerns

### Frontend
- React 19 + TypeScript + Vite + Cloudscape Design System
- ErrorBoundary for graceful error recovery
- React.lazy code splitting for performance
- Clean API abstraction layer (no direct AWS SDK calls)

---

## Weaknesses

### Critical: content_generator.py (2050 lines)
The content generation Lambda is a monolith handling prompt construction, AgentCore invocation, Bedrock fallback, Strava update, and all module integrations. This file should be split into:
- `prompt_builder.py` — prompt construction and template management
- `ai_invoker.py` — AgentCore/Bedrock invocation with fallback logic
- `strava_updater.py` — Strava API update logic
- `module_enrichers/` — per-module enrichment (campus_coach, enduraw)

### Critical: Zero Lambda Unit Tests
All 73 tests are CDK infrastructure assertions or integration tests that hit live AWS. No unit tests for:
- `activity_fetcher.py` — data extraction and transformation logic
- `content_generator.py` — prompt building, fallback logic
- `webhook_handler.py` — event routing and deduplication
- `dashboard_api.py` — aggregation and response formatting

### High: No CI/CD Pipeline
- No GitHub Actions, no CodePipeline
- Deployments are manual (`./scripts/deploy.sh dev`)
- No automated security scanning, no lint checks on PR
- No automated test execution on push

### Medium: Dead Dependencies in requirements.txt
- `flask` — not used anywhere in Lambda code
- `psutil` — not used anywhere in Lambda code
- `typing_extensions` vendored as a 4317-line file (`lambda_functions/typing_extensions.py`) instead of being in requirements.txt

### Medium: Frontend Test Coverage
- Basic component render tests exist
- No E2E tests (Playwright/Cypress)
- No API mock tests for error scenarios
- No accessibility testing

### Low: Hardcoded Configuration
- Some Lambda timeout values and retry counts are hardcoded rather than parameterized
- Enduraw 2-minute wait is hardcoded in Step Functions definition
- Region `eu-west-1` appears in multiple places instead of being centralized

---

## Recommendations (Priority Order)

1. **Split content_generator.py** — Extract into 4-5 focused modules. This is the highest-impact refactor.
2. **Add Lambda unit tests** — Start with content_generator and webhook_handler. Use moto for DynamoDB mocks.
3. **Set up GitHub Actions** — Lint, test, `cdk synth`, security scan on every push. Deploy on merge to main.
4. **Clean requirements.txt** — Remove flask, psutil. Move typing_extensions to requirements.
5. **Add frontend E2E tests** — Playwright for critical flows (OAuth, configuration, dashboard).
6. **Deploy frontend on CloudFront + S3 + Cognito** — Eliminate localhost dependency (see IDEAS.md).

---

## Code Volume

| Component | Lines | Files | Notes |
|-----------|-------|-------|-------|
| Lambda functions | ~6,500 | 13 | content_generator.py alone is 2,050 |
| CDK infrastructure | ~2,800 | 7 stacks | Clean separation |
| Frontend (TSX/TS) | ~4,200 | ~30 | Cloudscape components |
| Tests | ~2,100 | 5 | Infrastructure + integration only |
| Scripts | ~1,800 | 12 | Deploy, validate, uninstall |
| **Total** | **~17,400** | **~67** | Excluding vendored typing_extensions (4,317 lines) |
