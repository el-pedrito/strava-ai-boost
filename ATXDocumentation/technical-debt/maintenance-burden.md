# Maintenance Burden

> See also: [Summary](summary.md) | [Remediation Plan](remediation-plan.md) | [Architecture Patterns](../architecture/patterns.md)

## Lambda Layer Cross-Stack Export Constraint
**Severity**: Medium | **Impact**: Deployment reliability

The Lambda Layer (`strava-ai-boost-dependencies`) is created in `CoreInfrastructureStack` and shared across all other stacks via CDK property references. This creates a CloudFormation cross-stack export. If the Layer's asset hash changes unexpectedly (e.g., due to macOS filesystem metadata like xattrs), CloudFormation will try to replace the Layer, which fails because other stacks reference it.

**Current Mitigation**: The team manually pins `LAYER_ASSET_HASH` in `core_infrastructure_stack.py` with a SHA-256 hash. This hash must be updated manually whenever `lambda_layer/requirements.txt` changes and the layer is rebuilt.

**Risk**: Forgetting to update the hash after a dependency change could deploy stale Lambda dependencies. Conversely, an accidental hash change breaks all stack deployments.

## CDK Feature Flags
**Severity**: Low | **Impact**: CDK CLI warnings, potential behavior changes

The `cdk.json` file configures approximately 35 feature flags, but CDK 2.219.0 has approximately 58+ recognized flags. Missing flags produce warnings during `cdk synth` and `cdk deploy`. On CDK version upgrades, new flags may default to legacy behavior unless explicitly set.

**Risk**: CDK upgrade could introduce subtle behavior changes for unconfigured flags. The warnings are informational but clutter the deployment output.

## AgentCore Browser Tool Reliability
**Severity**: Medium | **Impact**: Campus Coach extraction reliability

The Campus Coach agent uses AgentCore's Browser Tool (headless Chrome) for web scraping. This tool has inherent reliability challenges:
- Cold start on first invocation after idle period can fail or timeout
- The Campus Coach website may change its UI structure, breaking the scraping agent
- Browser Tool interactions depend on page load timing, cookie popups, and JavaScript execution
- The agent uses async fire-and-forget pattern, making failure detection delayed

**Current Mitigation**: The agent is invoked asynchronously (fire-and-forget), so failures don't block the activity enhancement pipeline. Sessions are stored in DynamoDB and reused across multiple activities. The Memory hook stores extraction history for learning.

**Implementation gotcha**: True fire-and-forget requires spawning a `threading.Thread` with its own event loop (`asyncio.run(...)`) inside the `@app.entrypoint`. Using `asyncio.create_task(...)` instead keeps the coroutine attached to the AgentCore worker loop, which blocks the HTTP response until the task finishes (caused 120s Lambda timeouts before the fix in commit `69486ef`).

## Manual Lambda Dependency Build
**Severity**: Low | **Impact**: Developer experience, deployment reliability

Lambda Layer dependencies require manual installation:
1. `pip install -t lambda_layer/python -r lambda_layer/requirements.txt`
2. Update `LAYER_ASSET_HASH` in `core_infrastructure_stack.py`
3. `cdk deploy`

There is no automated CI/CD pipeline, Makefile, or pre-deploy script that ensures the Lambda Layer is built and hash-updated before deployment.

**Risk**: New team members or infrequent deploys may forget the Layer build step, deploying with stale or missing dependencies.

## Single-User Architecture Assumption
**Severity**: Low | **Impact**: Scalability to multi-user

The application is designed for single-user operation:
- OAuth tokens stored in a single Secrets Manager secret (not per-user)
- `DEFAULT_USER_ID` environment variable used as fallback
- Token refresh in `strava_updater.py` does not handle multi-user scenarios (has a TODO comment)
- User ID mismatch handling in `activity_fetcher.py` has a permissive fallback for "default" user

**Risk**: If the system needs to support multiple Strava athletes, significant refactoring would be required for per-user token management and data isolation.

## Embedded System Prompts
**Severity**: Low | **Impact**: Maintainability

The content generation system prompt in `embedded_prompts.py` is approximately 20,000+ characters of detailed instructions including French-language examples, age-specific expressions, interest-based metaphors, and sport approach narratives. This makes the prompt:
- Difficult to version and diff in code reviews
- Hard to A/B test different prompt strategies
- Coupled to the agent deployment cycle

**Current Mitigation**: Prompts are in a separate file (`embedded_prompts.py`) rather than inline in agent code, providing some separation of concerns.

## Configuration Migration Pattern
**Severity**: Low | **Impact**: Code complexity

`activity_fetcher.py` contains inline migration logic for converting old flat user configuration format to nested `modules_config` format. This migration runs on every activity fetch, adding unnecessary processing for already-migrated users.

**Risk**: Minor performance impact; the migration code will become dead code once all users have been migrated.
