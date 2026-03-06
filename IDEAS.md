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

### User Preferences — Enforce Impact on Content Generation

**Source of truth**: DynamoDB `USER_CONFIG_TABLE` → `get_user_configuration()` (`content_generator.py:158`) → `build_user_profile_from_config()` (`content_generator.py:183`) → `user_profile` dict passed to agent. AgentCore Memory is a secondary source (learned preferences from feedback) — DynamoDB always takes priority.

Current state: `user_profile` is fetched from DynamoDB per user and injected as raw JSON in the user prompt. The system prompt (~800 lines in `embedded_prompts.py`) is static and contains rules for ALL possible profiles. Only `content_length` has programmatic enforcement (character limit in prompt). All other preferences (tone, emoji, language, age, interests, sport_approach) rely entirely on the LLM following instructions — no post-processing validation.

#### P0: Post-processing validation of preferences
- **Problem**: Model can ignore emoji_usage (15 emojis with `none`), exceed content_length, or generate in wrong language — nothing catches it
- **Solution**: Add `enforce_preferences()` after generation:
  - Strip emojis if `emoji_usage: none`, limit count for `minimal` (2) / `moderate` (5)
  - Truncate description to content_length limit as safety net (short=300, medium=800, detailed=1500)
  - Detect language mismatch (basic heuristic or `langdetect`) and log warning
- **Files**: `src/agents/content_agent.py`, `lambda_functions/processing/content_generator.py`

#### P0: Replace raw JSON profile with direct style instructions
- **Problem**: User profile injected as raw JSON at line 762 of `content_agent.py` — model must interpret JSON and cross-reference with 800 lines of rules
- **Solution**: Build `build_preference_instructions(user_profile)` that generates imperative instructions:
  ```
  STYLE INSTRUCTIONS:
  - TONE: Conversational, use contractions, friendly language          ← content_tone
  - EMOJIS: Maximum 5 in description                                   ← emoji_usage
  - LENGTH: MAX 800 characters (medium)                                ← content_length
  - LANGUAGE: French                                                   ← content_language
  - FOCUS: Health & wellness — emphasize feeling good, stress relief   ← sport_approach
  - TECHNICAL: Intermediate — include key metrics, no deep stream analysis ← technical_detail
  - AGE CONTEXT: 26-35 — efficient, strategic, results-focused refs    ← age_range
  - INTERESTS: technology, competition — subtle data/challenge refs    ← interests
  ```
- **Files**: `src/agents/content_agent.py`

#### P1: Inject only relevant style rules (not full catalog)
- **Problem**: System prompt contains ALL rules for ALL profiles (6 sport_approaches x 5 tones x 5 age_ranges). Wastes tokens, increases cost, dilutes model focus
- **Solution**: Keep critical rules (REGLE #0-#5) static, build profile-specific examples dynamically. Target: ~300 lines static + ~100 lines dynamic (vs ~800 today)
- **Files**: `src/agents/embedded_prompts.py`, `src/agents/content_agent.py`

#### P1: Enforce `content_language` user preference
- **Problem**: The `content_language` preference (french/english/spanish/german/italian) is stored in DynamoDB and passed in user_profile, but the entire system prompt + all examples are in French. When a user sets `content_language: english`, the model still generates in French because the French-heavy context overrides the preference
- **Solution**: When `content_language` != `french`, add a strong override at TOP of user prompt:
  ```
  LANGUAGE OVERRIDE: User preference content_language is "english".
  Generate ALL content (title + description) in ENGLISH. Do NOT use French.
  ```
- **Files**: `src/agents/content_agent.py`

#### P2: Resolve DynamoDB vs AgentCore Memory conflicts
- **Problem**: `user_profile` (DynamoDB, explicit UI settings) and `feedback_instructions` (Memory, learned patterns) can contradict each other
- **Solution**: Add priority instruction: "If learned preferences conflict with USER PROFILE, USER PROFILE takes priority (explicit user choice)"
- **Files**: `src/agents/content_agent.py` (lines 356-373)

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
