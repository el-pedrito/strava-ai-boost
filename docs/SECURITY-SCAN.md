# Security Scan Summary — ASH

> [AWS Automated Security Helper](https://github.com/awslabs/automated-security-helper) (ASH) v3.5.7
> Scan date: 2026-07-15 · Threshold: MEDIUM · Scope: full repository.

## Result

**No actionable security findings in published first-party code.** All scanner findings are one of: build artifacts (gitignored), test-file assertions, vendored third-party dependencies, or false-positive keyword matches. `npm-audit` and `semgrep` pass clean; `bandit` reports **zero findings** on first-party application code (Lambdas, stacks, agents) excluding tests and vendored deps.

## Scanner Results

| Scanner | Critical | High | Medium | Low | Verdict |
|---------|---------:|-----:|-------:|----:|---------|
| bandit | 0 | 0 | 87 | 2325 | ✅ All in tests / vendored deps (see below) |
| checkov | 132 | 0 | 0 | 0 | ✅ All in `cdk.out/` synthesized templates (gitignored) |
| detect-secrets | 46 | 0 | 0 | 0 | ✅ False positives (UI labels) + `cdk.out/` |
| npm-audit | 0 | 0 | 0 | 0 | ✅ PASSED |
| semgrep | 0 | 0 | 0 | 0 | ✅ PASSED |
| cdk-nag, cfn-nag, grype, opengrep, syft | — | — | — | — | Not run (tooling not available locally) |

## Triage

Findings by location: **1819 in `cdk.out/`** (gitignored build artifacts, never published) vs **771 in tracked paths**. The tracked-path findings break down as:

- **Test files** (`tests/**`, ~380 findings) — `bandit` B101 `assert_used`, expected in pytest, and hardcoded sample data. Not applicable.
- **Vendored dependencies** bundled into `lambda_functions/` for the Lambda Layer cross-stack workaround (`click/`, `starlette/`, `uvicorn/`, `requests/`, `typing_extensions`, etc.) — third-party code, gitignored, not first-party.
- **i18n JSON** (`frontend/src/i18n/{en,fr}.json`) — `detect-secrets` keyword matches on UI strings like `"Client Secret"` label and password-policy help text. False positives.
- **`stacks/core_infrastructure_stack.py`** (9 findings) — `bandit` B106 / secret-keyword on `secret_name="strava-ai-boost-..."` (Secrets Manager resource **names**, not values) and a `SECRET-HEX-HIGH-ENTROPY-STRING` on `LAYER_ASSET_HASH` (a SHA-256 build hash). All false positives.

## Actions Taken

- Added `.ash/` to `.gitignore` so scan output is not committed.
- Confirmed `cdk.out/` is already gitignored — the bulk of raw findings never reach the public repo.
- No code changes required: `pip-audit` (0 vulns) and `npm-audit` (0 vulns) already clean per the OSS release prerequisites.

## Reproduce

```bash
ash --source-dir . --output-dir .ash/ash_output
# Summary: .ash/ash_output/reports/ash.summary.md
```
