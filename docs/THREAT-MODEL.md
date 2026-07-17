# Threat Model — Strava AI Boost

> One-page STRIDE threat model for the sample. Scope: single-user personal deployment on AWS.
> Last updated: 2026-07-17. See [SECURITY.md](../SECURITY.md) for reporting vulnerabilities.

## System Overview & Trust Boundaries

```
[Internet]                          │ Trust boundary: public internet → AWS
  Browser ──HTTPS──> CloudFront ──OAC──> S3 (private, frontend)
  Browser ──JWT────> API Gateway (Cognito authorizer) ──> API Lambdas ──> DynamoDB
  Browser ──Bearer JWT──> AgentCore Runtime data plane (coach_chat, customJWT) ──> Bedrock
  Strava ──verify_token──> Webhook API ──> SQS ──> Step Functions ──> processing Lambdas
                                    │ Trust boundary: AWS → external APIs
  processing Lambdas ──HTTPS──> Strava API / Campus Coach / Intervals.icu / Enduraw
  processing Lambdas ──IAM────> AgentCore agents (Bedrock, Guardrails, Memory)
```

**Sensitive assets**: Strava OAuth tokens, Campus Coach password, Intervals.icu API key (all in Secrets Manager) · athlete health/GPS data (DynamoDB, AWS-managed encryption) · Cognito credentials · audio debriefs (private S3).

## STRIDE Analysis

| ID | Threat | STRIDE | Severity | Status | Mitigation |
|----|--------|--------|----------|--------|------------|
| T1 | Forged Strava webhook events trigger processing of arbitrary activity IDs | Spoofing | Medium | ✅ Mitigated | `hub.verify_token` validated at subscription; events only reference activity IDs — data is re-fetched from Strava with the user's OAuth token, so forged payloads cannot inject content |
| T2 | Unauthorized access to API endpoints (dashboard, config, preferences) | Spoofing / EoP | High | ✅ Mitigated | Cognito authorizer on all API Gateway routes; JWT required; no self-registration (`selfSignUpEnabled: false`); 12+ char password policy |
| T3 | Unauthenticated access to the conversational coach | Spoofing | High | ✅ Mitigated | The `coach_chat` AgentCore Runtime uses a **customJWT** authorizer bound to the Cognito User Pool; the browser sends the Cognito ID token as a `Bearer` header and `user_id` is derived from the `custom:strava_id` claim (never trusted from the body). No Function URL, no Identity Pool, no unauthenticated path — unauthenticated calls return HTTP 401 |
| T4 | Prompt injection via activity title/description (user-controlled Strava text flows into LLM prompts) | Tampering | Medium | ⚠️ Partial | Bedrock Guardrails on agent outputs; single-user design limits attacker to self-injection. Residual: a malicious activity description could still steer generated content — acceptable for personal use, review before multi-tenant |
| T5 | Secrets leakage (OAuth tokens, Campus Coach password) in code, logs, or git history | Info. Disclosure | Critical | ✅ Mitigated | All credentials in Secrets Manager; CloudWatch Data Protection masks passwords/emails/auth headers in AgentCore logs; repo scanned (`scan-opensource`), git history scrubbed before publication |
| T6 | Public exposure of frontend S3 bucket or athlete data | Info. Disclosure | High | ✅ Mitigated | S3 `BLOCK_ALL` public access, CloudFront OAC only; DynamoDB AWS-managed encryption; audio files served via 1h presigned URLs |
| T7 | LLM data leakage — coach/content agents exposing memory contents or other users' data | Info. Disclosure | Low | ✅ Mitigated (single-user) | AgentCore Memory namespaces are per-user; single-athlete deployment means no cross-user data exists. Re-assess for multi-tenant |
| T8 | Cost attack — flooding the webhook to trigger unbounded Bedrock/AgentCore invocations | DoS (cost) | Medium | ⚠️ Partial | Webhook dedup (skips `processing`/`completed` activities, 1h cooldown on failures); SQS + DLQ absorb bursts; AWS Budget alert ($35/mo) + SNS ops alarms. Residual: no WAF/rate-limit on the webhook endpoint itself — acceptable at personal scale |
| T9 | Strava API rate-limit exhaustion breaking the pipeline | DoS | Low | ✅ Mitigated | Rate-limit tracking table; retries with backoff; DLQ + `reprocess_dlq.sh` |
| T10 | Over-privileged Lambda roles enabling lateral movement | EoP | Medium | ✅ Mitigated | Least-privilege IAM with scoped resource ARNs (`grant_read_data`/`grant_write_data` per table/function); no wildcard policies |
| T11 | Missing audit trail for content changes pushed to Strava | Repudiation | Low | ✅ Accepted | Structured logs (Powertools, correlation IDs) + DynamoDB processing status per activity. No further action for a personal sample |
| T12 | Supply chain — malicious or vulnerable dependencies | Tampering | Medium | ⚠️ Ongoing | `pip-audit` + `npm audit` at 0 known vulns (2026-07); lock files committed. Residual: no automated dependency scanning (no CI) — deployers should re-run audits |
| T13 | Campus Coach undocumented API — credentials sent to a third party, API may change silently | Info. Disclosure | Medium | ⚠️ Accepted | Credentials encrypted in Secrets Manager, HTTPS only; documented in SECURITY.md (use a dedicated password). Inherent risk of third-party integration |

## Deployment Threats (public sample)

- **Credential leakage from git history** — history rewritten with `git filter-repo` before publication (account IDs, user IDs, agent IDs, API keys replaced). Verified with a full-history scan.
- **Infrastructure replication** — anyone can deploy this stack; costs and security are the deployer's responsibility (stated in README disclaimer).
- **Fork-based attacks** — no CI/CD secrets exist in the repo; nothing to exfiltrate via workflow injection.

## Key Assumptions

1. Single trusted user (the deployer/athlete) — no untrusted user input beyond Strava activity text.
2. AWS account is personal and isolated; no cross-account trust.
3. Third-party APIs (Strava, Campus Coach, Intervals.icu, Enduraw) are trusted for the data they return.
4. This model must be revisited before any multi-tenant or shared deployment (T4, T7 in particular).
