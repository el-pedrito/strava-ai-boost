# Next Steps

## 1. Deploy Frontend on CloudFront + S3 + Cognito

- Host React app on S3 with CloudFront distribution (OAC, not OAI)
- Add Cognito User Pool with `selfSignUpEnabled: false` (admin-only registration)
- Replace API Key auth with Cognito tokens (SigV4 signed requests)
- HTTPS everywhere, security headers (HSTS, CSP, X-Frame-Options)
- Eliminates localhost dependency, enables mobile access
- WAF on CloudFront for OWASP protection

## 2. Lambda ARM64 (Graviton)

- Switch all Lambda functions to ARM64 architecture for ~20% cost reduction
- Update CDK: `architecture: lambda.Architecture.ARM_64` on all functions
- Verify Lambda Layer compatibility (rebuild with `--platform linux/arm64` if needed)
- Test all functions after migration (especially native dependencies)

## 3. Verify Observability Stack

- AgentCore Observability (`security_stack.py`) configures X-Ray + CloudWatch Logs via custom resources — not confirmed working end-to-end
- Check if traces appear in CloudWatch GenAI Observability dashboard (console link in stack output `ObservabilityDashboard`)
- Verify X-Ray `UpdateTraceSegmentDestination` and `UpdateIndexingRule` custom resources executed successfully
- Check CloudWatch Logs resource policy (`AgentCoreTransactionSearch`) is applied
- If no traces visible: check AgentCore runtime OpenTelemetry is enabled (not `--disable-otel` in deploy), verify X-Ray sampling at 100%
