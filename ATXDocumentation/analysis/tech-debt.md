# Technical Debt Analysis

> See also: [Technical Debt Report](../technical-debt-report.md) | [Summary](../technical-debt/summary.md) | [Outdated Components](../technical-debt/outdated-components.md) | [Remediation Plan](../technical-debt/remediation-plan.md)

## Overview

This document provides a cross-reference to the comprehensive technical debt analysis in the `technical-debt/` directory.

## Key Findings

### No High Severity Issues
- Python 3.12 — current and supported until October 2028
- React 19, TypeScript 5.9, Vite 7.3 — all current major versions
- No EOL/deprecated runtimes or frameworks detected

### Medium Severity Items (3)
1. **Unpinned Python dependencies** (`>=` specifiers) — risk of non-reproducible builds → [Remediation R-1](../technical-debt/remediation-plan.md)
2. **CDK lib at 2.219.0** — needs periodic updates → [Remediation R-2](../technical-debt/remediation-plan.md)
3. **Lambda Layer manual asset hash** — deployment risk → [Remediation R-3](../technical-debt/remediation-plan.md)

### Low Severity Items (4)
4. CDK feature flags gaps → [Remediation R-4](../technical-debt/remediation-plan.md)
5. Dev tool versions (pytest, moto, black, flake8) → [Remediation R-5](../technical-debt/remediation-plan.md)
6. Missing token refresh in strava_updater.py → [Remediation R-6](../technical-debt/remediation-plan.md)
7. Unused constants in campus_coach_invoker.py → [Remediation R-7](../technical-debt/remediation-plan.md)

### Maintenance Burden Areas
- Lambda Layer cross-stack export constraint (mitigated with pinned hash)
- AgentCore Browser Tool cold start reliability
- Manual Lambda dependency build process
- Single-user architecture assumption
- Large embedded system prompts

See [Maintenance Burden](../technical-debt/maintenance-burden.md) for detailed analysis of each area.

## Complexity Hotspots
| File | Concern |
|---|---|
| `content_agent.py` | ~700 LOC, large `invoke()` function with many conditional paths |
| `activity_processor.py` | `should_skip_processing()` has complex multi-branch logic |
| `embedded_prompts.py` | ~550 LOC of prompt text — difficult to diff and review |
| `enduraw_module.py` | ~600 LOC with many analysis methods, some with duplicate logic |
