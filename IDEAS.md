# Next Implementation Ideas

## High Priority

### Deploy Frontend on CloudFront + S3 + Cognito
- Host React app on S3 with CloudFront distribution (OAC, not OAI)
- Add Cognito User Pool with `selfSignUpEnabled: false` (admin-only registration)
- Replace API Key auth with Cognito tokens (SigV4 signed requests)
- HTTPS everywhere, security headers (HSTS, CSP, X-Frame-Options)
- Eliminates localhost dependency, enables mobile access
- WAF on CloudFront for OWASP protection

### Restructure lambda_functions/ into packages
- Current: 16 flat Python files, hard to navigate
- Group by role:
  - `api/` — configuration_api, dashboard_api, user_preferences_api
  - `processing/` — activity_fetcher, activity_processor, content_generator, strava_updater, streams_analysis, modules_processing
  - `webhooks/` — webhook_handler, campus_coach_invoker
  - `support/` — agentcore_health_check, feedback_analyzer, stepfunctions_error_handler
- Requires CDK handler path updates (e.g. `handler="api/configuration_api.handler"`)
- Move `typing_extensions.py` to requirements.txt, delete vendored file (-4317 lines)

### Prompt Engineering - More Storytelling
- Current prompts are functional but could generate more engaging narratives
- Add storytelling elements: race metaphors, journey arcs, emotional beats
- Experiment with different Claude system prompts for varied writing styles
- A/B test prompt variations and track user edit rates as quality signal
- Leverage route landmarks and workout phases for narrative structure

### Integration Testing
- Test the full webhook > SQS > Step Functions > Bedrock > Strava update flow end-to-end
- Add mocked unit tests for Lambda handlers (currently only integration + CDK tests)
- Test AgentCore memory retrieval and feedback loop
- Test Enduraw wait/fallback mechanism
- CI/CD pipeline with GitHub Actions

## Medium Priority

### Intervals.icu Integration
- Module skeleton already exists in code (`intervals_icu` in module config)
- Intervals.icu provides advanced training metrics (CTL, ATL, TSB, HRV)
- Would enrich content with fitness/fatigue context
- Free API with athlete-level access

### Content Quality Dashboard
- Track edit rate: how often users modify AI-generated content
- Track AgentCore confidence scores over time
- Memory effectiveness: does content variety improve over time?
- Feedback loop metrics: preference extraction success rate

### Cost Optimization
- Lambda ARM64 (Graviton) for ~20% cost reduction
- Provisioned concurrency for content_generator (cold start sensitive)
- DynamoDB on-demand already in place, monitor for reserved capacity threshold
- Bedrock batch inference for non-real-time processing

