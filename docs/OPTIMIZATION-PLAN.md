# Strava AI Boost — Cost Optimization Retrospective

> Historical record of the April 2026 cost optimization pass.
> Diagnostic → decisions → what worked → what was abandoned.

---

## 1. Diagnostic (April 2026)

**Monthly bill: $512.72**, with a single service dominating:

| Service | Cost | Share |
|---|---|---|
| Amazon Bedrock (Claude Sonnet 4.5) | $492.89 | **96.3%** |
| Amazon CloudWatch | $9.74 | 1.9% |
| Amazon Bedrock AgentCore | $7.39 | 1.4% |
| AWS Secrets Manager | $1.28 | 0.2% |
| Other (SQS, S3, Lambda, DynamoDB, Step Functions, API GW) | $1.42 | <1% |

### Root cause

The **Campus Coach Browser Tool** agent accounted for ~96 % of Bedrock cost:

- 6 335 Bedrock invocations in April for only 60 Lambda invocations
- 273 LLM turns per scraping session (two retry attempts of ~130 turns each)
- No `max_turns` configured → agent looped indefinitely on auth failures
- Daily cron despite the training plan only changing once per week

### Secondary issues

- Campus Coach credentials (email + password) leaked in OpenTelemetry `gen_ai.*` spans on CloudWatch because the agent task prompt interpolated them as an f-string
- Cost allocation tags don't propagate to AgentCore invocations (known AWS bug, August 2025)
- Memory strategy used Sonnet 4.5 for extraction/consolidation, a classification task that doesn't need Sonnet
- A `MonitoringStack` duplicated metrics that AgentCore Observability and default AWS namespaces already provide

---

## 2. Decisions

### Campus Coach scraping: weekly + mark sessions done on match

Plan changes once a week, but session status (pending/done) changes daily.
We scrape on **Monday at 05:00 UTC** and keep session statuses fresh by flipping
`status="Fait"` in DynamoDB whenever the content agent matches an activity
(confidence > 0.8). The `"À faire"` filter used by `modules_processing` keeps
returning the right view between scrapes.

### Model choice: Haiku for scraping & memory extraction, Sonnet for content

- Campus Coach scraping → Haiku 4.5 (~4× cheaper than Sonnet, good enough for browser piloting)
- Memory UserPreferenceStrategy extraction + consolidation → Haiku 4.5
- Content generation → Sonnet 4.5 (reasoning quality matters for storytelling)

### Cost attribution: IAM role tagging + CUR 2.0 IAM Principal data

AgentCore resource tags don't show up in Cost Explorer. Workaround:
tag the IAM execution roles assumed by each runtime (`agent=campus_coach`
or `agent=content_gen`). The new CUR 2.0 IAM Principal data feature (April 2026)
captures the principal ARN on each Bedrock invocation so we can group costs
by agent in Cost Explorer.

### No custom MonitoringStack

Removed 5 CloudWatch alarms and a dashboard that nobody subscribed to.
The AgentCore runtimes publish natively to the **CloudWatch GenAI
Observability Dashboard** (latency, tool calls, tokens, X-Ray traces).
Default AWS namespaces cover Lambda, SQS, Step Functions.

### Credentials leak: CloudWatch Data Protection Policy

The agent task prompt template interpolates credentials as an f-string.
Refactoring this without risking regression on scraping reliability would
have been complex. Instead, we apply a **CloudWatch Data Protection Policy**
on the agent runtime log groups: built-in identifiers for `EmailAddress`
and `AwsSecretKey`, plus custom regexes for `Password:` patterns and
`Authorization:` headers. Masks all future log events.

**Note:** old log events (before the policy was applied) still contain
the raw credentials. The Campus Coach password must be rotated manually.

---

## 3. What worked

| ID | Change | Where | Impact |
|---|---|---|---|
| P0.1 | Campus Coach cron daily → weekly (MON 05:00 UTC) | `stacks/content_generation_stack.py` | -$458/mo |
| P0.2 | Content agent returns `matched_session_id`; Lambda flips session to `"Fait"` | `src/agents/embedded_prompts.py`, `lambda_functions/processing/content_generator.py` | Preserves weekly scrape semantics |
| P0.3 | `MaxToolCountsHook` stops the agent loop at 150 tool calls | `src/agents/campus_coach_agent.py` | Prevents infinite loops |
| P0.4 | Agent only aborts on *real* invalid credentials, retries on transient network errors | `src/agents/campus_coach_agent.py` | Avoids losing a weekly scrape to a 30-second page load |
| P0.5 | Tag AgentCore runtimes/memories + their IAM execution roles | `scripts/tag_agentcore_resources.{sh,py}` | Per-agent cost visibility in CUR 2.0 |
| P0.6 | Campus Coach → Haiku 4.5 | `src/agents/campus_coach_agent.py` | ~4× cheaper per scraping session |
| P1.2 | Bedrock prompt caching on content agent system prompt | `src/agents/content_agent.py` (`SystemContentBlock` + `cachePoint`) | Input tokens at 10% on cache hit |
| P1.3 | CloudWatch Data Protection Policy on AgentCore runtime logs | `scripts/tag_agentcore_resources.py` | Credentials no longer leak in new logs |
| P2.3 | Memory extraction/consolidation → Haiku 4.5 | `scripts/configure_memory_strategy.py` | ~4× cheaper per memory event |
| P2.4 | Remove custom `MonitoringStack` | `stacks/monitoring_stack.py` deleted, `app.py` updated | -$8/mo |

**Projected monthly cost: $513 → ~$26** (5% of original).

All changes are reproducible from a fresh clone:

```bash
./scripts/deploy.sh dev                     # Phase 1: CDK (P0.1, P0.2, P2.4 applied)
./scripts/create_agentcore_memories.sh      # Phase 2: AgentCore memories
./scripts/deploy_agentcore_agents.sh        # Phase 2: Agents (P0.3-P0.6, P1.2, P1.3, P2.3)
```

`deploy_agentcore_agents.sh` automatically calls `enable_agentcore_observability.sh`,
`tag_agentcore_resources.sh`, and `configure_memory_strategy.py`.

---

## 4. What was abandoned (and why)

### P2.1 — Reduce the content agent system prompt

**Abandoned.** The static dictionaries (`AGE_CONTEXT`, `INTEREST_EXPRESSIONS`,
`SPORT_APPROACH_EXAMPLES`) were already outside the prompt; `build_profile_context`
only injects the section matching the current user's profile (~800 characters).
The remaining ~29 KB of `CONTENT_GENERATION_PROMPT` contains business-critical
rules (Campus Coach matching, storytelling arcs, fun-fact injection, landmark
integration, JSON output format) that cannot be trimmed without regression risk.
Prompt caching (P1.2) already gives the intended savings.

### P2.2 — Re-enable the Short-Term Memory write hook

**Abandoned.** The STM write hook is disabled on purpose. Re-enabling it would
cause the agent to learn from its own generations rather than from real user
edits (which is what the scheduled `feedback_analyzer` Lambda already does by
computing diffs between generated and user-modified Strava descriptions).
The design is correct as-is.

### Langfuse / third-party observability

Not worth it for two agents. CloudWatch Logs Insights + the GenAI Observability
Dashboard + IAM Principal cost allocation cover everything we need. Revisit
if the project ever scales to 10+ agents.

### Bedrock Projects

Evaluated and rejected: API surface is OpenAI-compatible only, so would
require rewriting agent invocations for a feature we don't currently need.

---

## 5. Open issues

### AgentCore Browser Tool — Playwright `networkidle` trap

**Symptom:** `browser.navigate('https://app.campus.coach/auth')` times out
after ~35 seconds even though the page loads fine in a regular browser
(confirmed via Chrome DevTools MCP test).

**Root cause:** The Campus Coach site displays an Axeptio cookie consent
popup that keeps sending analytics requests to its backend. Playwright's
default `wait_until='networkidle'` never resolves because the network
never goes idle. This is a [known Playwright issue](https://github.com/microsoft/playwright/issues/19835).

**Fix applied (commit `4f53a22`):** Prompt-level instruction. The agent
is told explicitly that `navigate` timeout is *normal* on Campus Coach,
that the page is loaded behind the timeout, and to use `get_html`/`evaluate`
to inspect the DOM rather than retrying `navigate`. Also prioritizes
clicking "Accepter les cookies" early to unblock network events.

**Validated in prod (2026-04-25):** 3 sessions correctly scraped and
saved to DynamoDB after the prompt fix. Scrape takes ~110s end-to-end
(vs. previously failing after 3 minutes of timeouts).

### Lambda invoker → AgentCore runtime sync call timeout

The Campus Coach invoker Lambda has a 120-second timeout but full AgentCore
cold start + scraping can exceed that. When Lambda times out, AgentCore appears
to retry the async task, producing duplicate invocations. Not cost-prohibitive
at weekly cadence, but worth watching if scrape frequency ever increases.

---

## 6. References

- [Bedrock IAM Principal cost allocation (April 13, 2026)](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/iam-principal-cost-allocation.html)
- [Bedrock prompt caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)
- [AgentCore Observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)
- [CloudWatch Logs Data Protection Policy](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/mask-sensitive-log-data-create.html)
- [re:Post — AgentCore Agent tags not showing in Cost Explorer](https://repost.aws/questions/QUrOgFusewSaCAvERQ7h0R-w)
- [Strands Agents — hooks API](https://strandsagents.com/docs/user-guide/concepts/agents/hooks/)
- [AgentCore Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
