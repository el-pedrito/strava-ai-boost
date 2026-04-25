# Remediation Plan

> See also: [Summary](summary.md) | [Outdated Components](outdated-components.md) | [Maintenance Burden](maintenance-burden.md)

## Priority 1: Medium Severity — Dependency Management

### R-1: Pin Python dependency versions
**Severity**: Medium | **Effort**: Low

Replace `>=` specifiers with exact pinned versions in `requirements.txt`:
```
# Instead of: boto3>=1.34.0
# Use:        boto3==1.38.x  (latest known-good version)
```
- Use `pip freeze` or `pip-compile` (from `pip-tools`) to generate a locked requirements file
- Consider maintaining separate `requirements.txt` (loose) and `requirements.lock` (pinned) files
- Implement a periodic dependency update workflow (e.g., Dependabot, Renovate)

### R-2: Update AWS CDK lib regularly
**Severity**: Medium | **Effort**: Low

- Update `aws-cdk-lib` from `2.219.0` to the latest stable version
- Run `cdk diff` after update to review infrastructure changes
- Run full test suite (`pytest`) to validate CDK stack synthesis
- Add new CDK feature flags to `cdk.json` as they become available
- Consider using caret (`^2.219.0`) instead of pinned version for automatic minor/patch updates

### R-3: Automate Lambda Layer build process
**Severity**: Medium | **Effort**: Medium

- Create a `Makefile` or `scripts/build_layer.sh` that:
  1. Installs Lambda Layer dependencies to `lambda_layer/python/`
  2. Computes the new asset hash
  3. Updates `LAYER_ASSET_HASH` in `core_infrastructure_stack.py`
- Integrate this script into the deployment workflow (`scripts/deploy.sh`)
- Consider using CDK's built-in `PythonLayerVersion` construct which handles bundling automatically

## Priority 2: Low Severity — Dev Dependencies and Configuration

### R-4: Update CDK feature flags
**Severity**: Low | **Effort**: Low

- Run `cdk doctor` to identify missing feature flags
- Add all recommended flags to `cdk.json` with recommended values
- Test with `cdk synth` and `cdk diff` to verify no unexpected changes

### R-5: Update dev tool versions
**Severity**: Low | **Effort**: Low

- Update `pytest` to latest 8.x
- Update `moto` to latest 5.x
- Update `black` to latest 24.x+
- Update `flake8` to latest 7.x
- Run full test suite after each update to verify compatibility

### R-6: Fix token refresh in strava_updater.py
**Severity**: Low | **Effort**: Low

- `strava_updater.py` has a TODO comment for token expiry checking
- Implement token refresh logic similar to `activity_fetcher.py`'s `get_access_token()`
- Or refactor to use the shared `strava_oauth.py` module

### R-7: Remove unused retry constants
**Severity**: Low | **Effort**: Trivial

- `campus_coach_invoker.py` defines `MAX_RETRIES = 3` and `RETRY_DELAY_SECONDS = 5` but doesn't use them
- Either implement retry logic or remove the unused constants

## Priority 3: Future Improvements

### R-8: Add CI/CD pipeline
**Effort**: High

- Implement automated testing on push (pytest, vitest, cdk synth)
- Automate Lambda Layer build in CI
- Add automated dependency update mechanism (Dependabot/Renovate)
- Consider GitHub Actions, GitLab CI, or AWS CodePipeline

### R-9: Externalize system prompts
**Effort**: Medium

- Move large system prompts from `embedded_prompts.py` to external storage (S3, Parameter Store, or a prompt management system)
- Enable A/B testing of prompt strategies
- Support runtime prompt updates without redeployment

### R-10: Remove configuration migration code
**Effort**: Low

- After confirming all users have been migrated to nested `modules_config` format
- Remove the inline migration logic from `activity_fetcher.py` `fetch_user_configuration()`
- Add a one-time migration script instead if needed for new environments

### R-11: Multi-user architecture preparation
**Effort**: High

- If multi-user support is needed, refactor OAuth token storage to per-user secrets or DynamoDB
- Implement user-scoped data access patterns
- Remove `DEFAULT_USER_ID` fallback logic
