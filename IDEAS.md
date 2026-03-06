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

### ~~Prompt Engineering - More Storytelling~~ DONE

**What was implemented:**
- Added "Storytelling & Narrative Structure" section to `embedded_prompts.py` with 4-beat narrative arc (opening hook → rising action → climax → resolution)
- Narrative style adapts to `sport_approach`: competition → race narrative, wellness → mindfulness journey, challenge → hero's journey, stress relief → escape narrative, etc.
- `SPORT_APPROACH_EXAMPLES` in `content_agent.py` now includes `narrative` field injected into system prompt via `build_profile_context()`
- Route landmarks used as story anchors (not listed, but narrated through)
- Workout phases map to story progression (warm-up = setup, intervals = rising action, best split = climax, cool-down = resolution)
- Variety rules: 5 opener styles + 5 closer styles to rotate, avoiding repetitive patterns
- Full storytelling example included for LLM reference
- **Bug fix**: user description was stripped from agent payload (`content_generator.py` removed `'description'` key in `clean_activity_data`) — now preserved with AI signature cleanup only
- **Chain-of-thought**: agent now reasons through user sensations before generating (`<thinking>` block in user prompt)
- **Fun fact/joke**: always included before signature, adapted to activity context
- **No gear/shoes**: removed from Strava API fetch, prompt injection, and content generation
- **First-person voice**: all content written as "j'ai", "mon", "mes", "je"
- **User input at top of prompt**: original title+description moved to first position in user prompt + reminder at end
- **Prompt trimmed**: removed 265 redundant lines (-26%) — no regression
- Still TODO: A/B test prompt variations and track user edit rates as quality signal

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

### ~~Content Quality Dashboard~~ DONE

**What was implemented:**
- New frontend page at `/quality` with full Cloudscape UI
- 4 metric cards: Avg Confidence (90%), Edit Rate (10%), Avg Similarity (99%), Feedback Analyzed count
- Detailed table: Activity name (with sport icon), Date, Confidence (ProgressBar), User Edit status (Kept as-is/Edited/Pending), Similarity score, Processing time
- Backend: `dashboard_api.py` enriched with `confidence`, `description_modified`, `similarity_score`, `feedback_analyzed`, `generated_at` from `generation_metadata` + feedback fields
- Client-side stats computation from `/dashboard/activities?limit=100` endpoint
- Navigation: "Quality" button in top nav bar, breadcrumb support
- Auto-refresh every 60s, sorting enabled on columns
- Still TODO: Track trends over time (confidence/edit rate charts), memory effectiveness metrics

### Cost Optimization
- Lambda ARM64 (Graviton) for ~20% cost reduction
- Provisioned concurrency for content_generator (cold start sensitive)
- DynamoDB on-demand already in place, monitor for reserved capacity threshold
- Bedrock batch inference for non-real-time processing
