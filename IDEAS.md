# Next Implementation Ideas

## High Priority

### Deploy Frontend on CloudFront + S3 + Cognito
- Host React app on S3 with CloudFront distribution (OAC, not OAI)
- Add Cognito User Pool with `selfSignUpEnabled: false` (admin-only registration)
- Replace API Key auth with Cognito tokens (SigV4 signed requests)
- HTTPS everywhere, security headers (HSTS, CSP, X-Frame-Options)
- Eliminates localhost dependency, enables mobile access
- WAF on CloudFront for OWASP protection

### ~~Restructure lambda_functions/ into packages~~ DONE
- Grouped into 4 packages: api/, processing/, webhooks/, support/
- CDK handler paths updated
- Still TODO: Move `typing_extensions.py` to requirements.txt, delete vendored file (-4317 lines)

### Prompt Engineering - More Storytelling
- Current prompts are functional but could generate more engaging narratives
- Add storytelling elements: race metaphors, journey arcs, emotional beats
- Adapt storytelling style to user preferences (tone, sport_approach, age_range) — e.g. competition-focused users get race narratives, wellness users get mindfulness arcs
- Experiment with different Claude system prompts for varied writing styles
- A/B test prompt variations and track user edit rates as quality signal
- Leverage route landmarks and workout phases for narrative structure

### ~~User Preferences — Enforce Impact on Content Generation~~ DONE

**Source of truth**: DynamoDB `USER_CONFIG_TABLE` → `get_user_configuration()` (`content_generator.py:158`) → `build_user_profile_from_config()` (`content_generator.py:183`) → `user_profile` dict passed to agent. AgentCore Memory is a secondary source (learned preferences from feedback) — DynamoDB always takes priority.

**What was implemented:**
- `enforce_preferences()` in `content_generator.py` — post-processing safety net: strips/limits emojis per `emoji_usage`, truncates description per `content_length` (adaptive→1500 upper bound)
- `build_preference_instructions()` in `content_agent.py` — converts `user_profile` into imperative STYLE INSTRUCTIONS (tone, emoji, length, language, focus, technical) instead of raw JSON
- `build_profile_context()` in `content_agent.py` — injects only the matching age/interests/sport_approach expressions+examples into system prompt (dicts `AGE_CONTEXT`, `INTEREST_EXPRESSIONS`, `SPORT_APPROACH_EXAMPLES`), replacing the full ~100-line catalog removed from `embedded_prompts.py`
- Language override at TOP of user prompt when `content_language` != `french`
- Priority instruction in feedback_instructions: DynamoDB STYLE INSTRUCTIONS > Memory learned preferences
- Bug fixes: `user_profile` None guard, removed dead variables (`start_latlng`, `kudos_count`), `adaptive` length handled in enforce_preferences

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
