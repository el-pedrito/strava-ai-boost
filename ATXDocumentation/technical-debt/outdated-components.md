# Outdated Components Analysis

> See also: [Summary](summary.md) | [Remediation Plan](remediation-plan.md) | [Dependencies](../architecture/dependencies.md)

## Runtime and Framework Versions

| Component | Current Version | Status | Severity |
|---|---|---|---|
| **Python** | 3.12 | ✅ Current (supported until Oct 2028) | — |
| **React** | ^19.2.0 | ✅ Current (latest major) | — |
| **TypeScript** | ~5.9.3 | ✅ Current | — |
| **Vite** | ^7.3.1 | ✅ Current | — |
| **AWS Lambda Runtime** | Python 3.12 | ✅ Current | — |

## AWS CDK and Constructs

| Package | Version Spec | Notes | Severity |
|---|---|---|---|
| `aws-cdk-lib` | ==2.219.0 | Pinned version; CDK releases new versions frequently. Consider updating periodically for bug fixes and new constructs | **Medium** |
| `constructs` | >=10.0.0,<11.0.0 | Range specifier, compatible with CDK 2.x | — |

## Python Dependencies (requirements.txt)

| Package | Version Spec | Notes | Severity |
|---|---|---|---|
| `boto3` | >=1.34.0 | Minimum version; latest updates automatically. Consider pinning for reproducibility | **Medium** |
| `pydantic` | >=2.0.0 | Minimum version; Pydantic 2.x is current | — |
| `strands-agents` | >=1.0.0 | Minimum version; relatively new framework | — |
| `strands-agents-tools` | >=0.2.0 | Minimum version | — |
| `bedrock-agentcore-starter-toolkit` | >=0.1.21 | Minimum version; early-stage SDK | — |
| `bedrock-agentcore` | >=1.3.0 | Minimum version; managed by AWS | — |
| `pytest` | >=7.0.0 | Minimum version; pytest 8.x is available | **Low** |
| `pytest-cov` | >=4.0.0 | Minimum version; pytest-cov 5.x available | **Low** |
| `pytest-asyncio` | >=0.21.0 | Minimum version; 0.24.x available | **Low** |
| `hypothesis` | >=6.0.0 | Minimum version; Hypothesis 6.x is current major | — |
| `moto` | >=4.2.0 | Minimum version; moto 5.x available | **Low** |
| `black` | >=23.0.0 | Minimum version; black 24.x+ available | **Low** |
| `flake8` | >=6.0.0 | Minimum version; flake8 7.x available | **Low** |
| `mypy` | >=1.0.0 | Minimum version; mypy 1.x is current | — |
| `typing-extensions` | >=4.0.0 | Minimum version | — |

## Lambda Layer Dependencies (lambda_layer/requirements.txt)

| Package | Version Spec | Notes | Severity |
|---|---|---|---|
| `requests` | >=2.31.0 | Minimum version; requests 2.32.x available | — |
| `aws-lambda-powertools` | >=2.40.0 | Minimum version; Powertools releases frequently with new features | — |

## Frontend Production Dependencies (package.json)

| Package | Version Spec | Notes | Severity |
|---|---|---|---|
| `@cloudscape-design/components` | ^3.0.1217 | Caret range; auto-updates within 3.x | — |
| `@cloudscape-design/design-tokens` | ^3.0.72 | Caret range | — |
| `@cloudscape-design/global-styles` | ^1.0.51 | Caret range | — |
| `react` | ^19.2.0 | ✅ Current | — |
| `react-dom` | ^19.2.0 | ✅ Current | — |
| `react-router-dom` | ^7.13.1 | ✅ Current (v7 is latest) | — |

## Frontend Dev Dependencies (package.json)

| Package | Version Spec | Notes | Severity |
|---|---|---|---|
| `@eslint/js` | ^9.39.1 | ✅ Current | — |
| `@testing-library/jest-dom` | ^6.9.1 | ✅ Current | — |
| `@testing-library/react` | ^16.3.2 | ✅ Current | — |
| `@testing-library/user-event` | ^14.6.1 | ✅ Current | — |
| `@types/node` | ^24.10.1 | ✅ Current | — |
| `@types/react` | ^19.2.7 | ✅ Current | — |
| `@types/react-dom` | ^19.2.3 | ✅ Current | — |
| `@vitejs/plugin-react` | ^5.1.1 | ✅ Current | — |
| `eslint` | ^9.39.1 | ✅ Current | — |
| `eslint-plugin-react-hooks` | ^7.0.1 | ✅ Current | — |
| `eslint-plugin-react-refresh` | ^0.4.24 | ✅ Current | — |
| `globals` | ^16.5.0 | ✅ Current | — |
| `jsdom` | ^28.1.0 | ✅ Current | — |
| `typescript` | ~5.9.3 | ✅ Current | — |
| `typescript-eslint` | ^8.48.0 | ✅ Current | — |
| `vite` | ^7.3.1 | ✅ Current | — |
| `vitest` | ^4.0.18 | ✅ Current | — |

## Pre-commit Hooks

| Tool | Version | Notes | Severity |
|---|---|---|---|
| `detect-secrets` | v1.5.0 | Current | — |
| `nbstripout` | 0.7.1 | Current | — |
| `shellcheck-py` | v0.10.0.1 | Current | — |
| `pre-commit-hooks` | v4.6.0 | Current | — |

## Summary

- **No High severity issues** — no EOL/deprecated runtimes or frameworks
- **3 Medium severity issues** — dependency version management and CDK currency
- **6 Low severity issues** — dev dependency versions could be updated
- Frontend dependencies are **all current** thanks to caret (`^`) and tilde (`~`) version specifiers with recent base versions
