# Security Policy

## Scope

Strava AI Boost is a **personal-use sample project**, not production software. It is provided as-is (MIT-0 license) with no security SLA. That said, security reports are welcome and will be addressed on a best-effort basis.

## Supported Versions

Only the latest version on the `dev` branch is supported. There are no backported security fixes.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, use [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) on this repository (Security tab → "Report a vulnerability").

Please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce
- Affected component (Lambda function, CDK stack, frontend, agent)

You can expect an acknowledgment within a week, best-effort.

## Security Design Notes for Deployers

If you deploy this sample, be aware of its security posture (see also [docs/THREAT-MODEL.md](docs/THREAT-MODEL.md)):

- **Authentication**: Cognito User Pool with self-registration disabled — users must be created by an admin. The coach chat AgentCore Runtime uses a customJWT authorizer bound to the Cognito User Pool: the frontend sends the Cognito ID token as a Bearer header to the AgentCore data plane, and `user_id` is derived server-side from the `custom:strava_id` claim (never trusted from the request body).
- **Secrets**: all credentials (Strava OAuth, Campus Coach, Intervals.icu) live in AWS Secrets Manager — never commit them.
- **Data**: DynamoDB tables use AWS-managed encryption; the frontend S3 bucket is private (CloudFront OAC only).
- **AI safety**: Bedrock Guardrails are applied to agent outputs; CloudWatch Data Protection masks credentials in AgentCore logs.
- **Single-user design**: per-user isolation exists but has not been hardened for multi-tenant use. Do not expose this to untrusted users without additional review.
- **Third-party APIs**: Campus Coach integration uses an undocumented API with password credentials — use a dedicated password.

## Dependencies

Run `pip-audit` and `npm audit` before deploying. Dependency vulnerabilities in this sample are patched opportunistically, not on a schedule.
