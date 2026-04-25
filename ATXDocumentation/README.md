# Strava AI Boost — Documentation

## 📋 Quick Navigation

| Document | Description |
|---|---|
| [🎯 Technical Debt Report](technical-debt-report.md) | **Start here** — AWS Transformation recommendation + executive summary |
| [📖 Project Overview](project-overview.md) | Technology stack, key metrics, high-level architecture |
| [🏗️ System Overview](architecture/system-overview.md) | 7 CDK stacks, deployment model, architectural decisions |
| [⚡ Workflows](behavior/workflows.md) | Activity enhancement, OAuth, feedback loop workflows |
| [📊 Code Metrics](analysis/code-metrics.md) | LOC, file counts, complexity assessment |

---

## Table of Contents

### 🏗️ Architecture
- [System Overview](architecture/system-overview.md) — 7 CDK stacks, deployment model, key decisions
- [Components](architecture/components.md) — DynamoDB tables, Lambda functions, SQS, API Gateway, AgentCore agents
- [Dependencies](architecture/dependencies.md) — Internal and external dependency mapping with versions
- [Patterns](architecture/patterns.md) — 12 architectural patterns (serverless, event-driven, module pattern, etc.)

### ⚡ Behavior *(Early Access)*
- [Business Logic](behavior/business-logic.md) — Webhook validation, enhancement pipeline, Campus Coach, Enduraw, Intervals.icu
- [Workflows](behavior/workflows.md) — Activity enhancement, OAuth, configuration, feedback analysis workflows
- [Decision Logic](behavior/decision-logic.md) — Skip logic, module selection, content parameters, error routing
- [Error Handling](behavior/error-handling.md) — DLQ, batch failures, token refresh, guardrail fallbacks

### 🔴 Technical Debt
- [Technical Debt Report](technical-debt-report.md) — **Root-level** report with AWS Transformation Recommendation
- [Summary](technical-debt/summary.md) — Overview of all findings with severity ratings
- [Outdated Components](technical-debt/outdated-components.md) — Dependency version analysis
- [Maintenance Burden](technical-debt/maintenance-burden.md) — Lambda Layer, CDK flags, AgentCore reliability
- [Remediation Plan](technical-debt/remediation-plan.md) — Prioritized action items

### 📚 Reference
- [Program Structure](reference/program-structure.md) — Complete directory layout, entry points, module organization
- [Interfaces](reference/interfaces.md) — API Gateway endpoints, Lambda signatures, AgentCore interfaces
- [Data Models](reference/data-models.md) — DynamoDB schemas, Pydantic models, TypeScript types
- [API Reference / Modules](reference/api-reference.md) — Module registry, Lambda packages, CDK stack methods

### 📊 Analysis
- [Code Metrics](analysis/code-metrics.md) — File counts, LOC, function counts, complexity
- [Complexity Analysis](analysis/complexity-analysis.md) — Cyclomatic complexity hotspots, coupling analysis
- [Dependency Analysis](analysis/dependency-analysis.md) — Internal graph, external inventory, criticality
- [Security Patterns](analysis/security-patterns.md) — Guardrails, Secrets Manager, IAM, HMAC, CORS
- [Tech Debt Analysis](analysis/tech-debt.md) — Cross-reference to technical-debt/ directory

### 📐 Diagrams
- [Structural Diagrams](diagrams/structural/component-diagrams.md) — CDK stacks, Lambda packages, frontend hierarchy
- [Behavioral Diagrams](diagrams/behavioral/sequence-diagrams.md) — Activity enhancement sequence, status lifecycle, data flow
- [Architecture Diagrams](diagrams/architecture/system-context.md) — System context, service map, security boundaries

### 🚀 Migration
- [Component Order](migration/component-order.md) — Stack and Lambda deployment order
- [Test Specifications](migration/test-specifications.md) — Test categories, patterns, and commands
- [Validation Criteria](migration/validation-criteria.md) — Infrastructure, functional, and E2E validation

### 🔧 Specialized
- [Database Patterns](specialized/database-patterns.md) — DynamoDB table design, access patterns
- [API Documentation](specialized/api-documentation.md) — Endpoint request/response examples
- [Event Patterns](specialized/event-patterns.md) — SQS, EventBridge, webhook message formats
- [UI Components](specialized/ui-components.md) — React/Cloudscape page structure, routing

---

## Component Index

| Component | Documentation |
|---|---|
| `app.py` | [System Overview](architecture/system-overview.md) |
| `stacks/` | [System Overview](architecture/system-overview.md), [Components](architecture/components.md) |
| `lambda_functions/webhooks/` | [Business Logic](behavior/business-logic.md), [Workflows](behavior/workflows.md) |
| `lambda_functions/processing/` | [Business Logic](behavior/business-logic.md), [Workflows](behavior/workflows.md) |
| `lambda_functions/api/` | [Interfaces](reference/interfaces.md), [API Documentation](specialized/api-documentation.md) |
| `lambda_functions/shared/` | [API Reference](reference/api-reference.md) |
| `lambda_functions/support/` | [Error Handling](behavior/error-handling.md), [Workflows](behavior/workflows.md) |
| `src/agents/` | [Interfaces](reference/interfaces.md), [Patterns](architecture/patterns.md) |
| `src/modules/` | [API Reference](reference/api-reference.md), [Patterns](architecture/patterns.md) |
| `frontend/` | [UI Components](specialized/ui-components.md), [Program Structure](reference/program-structure.md) |
| DynamoDB tables | [Data Models](reference/data-models.md), [Database Patterns](specialized/database-patterns.md) |
| Step Functions | [Components](architecture/components.md), [Behavioral Diagrams](diagrams/behavioral/sequence-diagrams.md) |
| AgentCore agents | [Components](architecture/components.md), [Interfaces](reference/interfaces.md) |
