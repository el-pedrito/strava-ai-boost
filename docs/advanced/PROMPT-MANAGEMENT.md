# Prompt Management System

Centralized prompt management for Strava AI Boost AgentCore agents.

**Version**: 1.17.0  
**Last Updated**: 2026-01-04

## Overview

The Strava AI Boost prompt management system uses **embedded prompts** directly in the agent code for maximum reliability and simplicity. All prompts are centralized in `src/agents/embedded_prompts.py`.

## Architecture

### System Components

```
src/agents/
├── embedded_prompts.py              # ALL prompts centralized here
├── content_agent.py                 # Content generation agent (uses CONTENT_GENERATION_PROMPT)
├── campus_coach_agent.py            # Campus Coach extraction agent (uses CAMPUS_COACH_PROMPT)
└── content_generation_agent.yaml   # AgentCore configuration
```

### Why Embedded Prompts?

- ✅ **Reliability**: No file loading errors, no path issues
- ✅ **Simplicity**: Single source of truth
- ✅ **Deployment**: Prompts deployed with agent code
- ✅ **Version Control**: Prompts versioned with code
- ✅ **Performance**: No file I/O overhead

## Prompt Structure

### CONTENT_GENERATION_PROMPT

Located in `src/agents/embedded_prompts.py`, this prompt contains:

#### ⚠️ RÈGLES CRITIQUES (Priority #1)

1. **PRÉSERVATION DU CONTENU ORIGINAL**
   - ALL elements from original title/description MUST be present
   - Reformulate clearly but preserve all information
   - Tone original = tone generated

2. **CAMPUS COACH - MATCHING INTELLIGENT UNIQUEMENT**
   - Do NOT force matching if doesn't correspond
   - When match identified: RECALL planned session + COMPARE + ANALYZE + CELEBRATE
   - Detect off-program activities (muscu, vélo, etc.)

3. **STREAMS COMPRESSÉS (30s blocks)**
   - Receives compressed blocks instead of raw streams
   - Includes route_landmarks for geographical context
   - 50K+ tokens → 2K tokens

#### Personalization Sections

- **User Profile Configuration**: age_range, interests, sport_approach, content_preferences
- **Age-Appropriate References**: 18-25, 26-35, 36-45, 46-55, 55+ with examples
- **Interest-Based Content**: Technology, Music, Nature, Competition, etc.
- **Sport Approach Adaptation**: Health & Wellness, Performance & Competition, Social & Fun
- **Content Structure Templates**: Short, Medium, Detailed formats
- **Module Integration**: Campus Coach, Enduraw
- **Quality Assurance**: Authenticity, Precision, NO HASHTAGS, NO MARKDOWN

### CAMPUS_COACH_PROMPT

Located in `src/agents/embedded_prompts.py`, this prompt contains:

- Authentication flow for Campus Coach website
- Session extraction logic
- Data structuring rules
- Error handling guidelines

## Usage in Agents

### Content Generation Agent

```python
# src/agents/content_agent.py
from embedded_prompts import CONTENT_GENERATION_PROMPT

@app.entrypoint
def invoke(payload, context=None):
    # Use embedded prompt as system prompt
    system_prompt = CONTENT_GENERATION_PROMPT
    
    agent = Agent(
        model=MODEL_ID,
        system_prompt=system_prompt,  # All logic is here
        hooks=[AgentCoreMemoryHook()] if MEMORY_ID else []
    )
    
    # Build simple JSON data prompt (no rules duplication)
    prompt = f"""Generate content for this activity.
    
    **DONNÉES JSON:**
    ```json
    {{
      "activity": {{...}},
      "original_input": {{...}},
      "user_profile": {{...}},
      "streams_compressed": {{...}}
    }}
    ```
    
    Return ONLY JSON: {{"title": "...", "description": "...", "confidence": 0.85}}
    """
    
    result = agent(prompt)
    return result
```

### Campus Coach Agent

```python
# src/agents/campus_coach_agent.py
from embedded_prompts import CAMPUS_COACH_PROMPT

@app.entrypoint
def invoke(payload, context=None):
    system_prompt = CAMPUS_COACH_PROMPT
    
    agent = Agent(
        model=MODEL_ID,
        system_prompt=system_prompt
    )
    
    # Simple extraction request
    prompt = "Extract Campus Coach sessions from the dashboard."
    result = agent(prompt)
    return result
```

## Updating Prompts

### Step 1: Edit embedded_prompts.py

```bash
# Edit the centralized prompt file
vim src/agents/embedded_prompts.py
```

### Step 2: Deploy AgentCore Agents

```bash
# Navigate to agents directory
cd src/agents

# Deploy content generation agent
agentcore deploy --env region=eu-west-1

# Verify deployment
agentcore list
```

### Step 3: Verify Changes

```bash
# Test agent invocation
agentcore invoke content_gen --input '{"activity_data": {...}}'

# Check logs
aws logs tail /aws/bedrock-agentcore/runtimes/content_gen-* --follow --profile your-aws-profile
```

## Input Data Structure

### Content Generation Agent Input

```json
{
  "activity": {
    "type": "Run",
    "distance_km": 10.5,
    "duration_min": 52,
    "elevation_m": 150,
    "avg_speed_kmh": 12.1,
    "avg_hr": 155,
    "achievements": 2,
    "prs": 1
  },
  "original_input": {
    "title": "sortie tranquille",
    "description": "fatigue mais ça fait du bien"
  },
  "location": {
    "city": "Paris",
    "country": "France",
    "weather": {"temperature": 15, "wind_speed": 10}
  },
  "user_profile": {
    "age_range": "26-35",
    "interests": ["competition"],
    "sport_approach": "performance & competition",
    "content_preferences": {
      "length": "detailed",
      "tone": "technical & analytical",
      "emoji_usage": "moderate",
      "technical_detail": "advanced",
      "language": "french"
    }
  },
  "athlete_context": "Power-to-Weight: 3.2 W/kg...",
  "gear_context": "Equipment: Nike Vaporfly...",
  "achievements_context": "2 PRs, 1 achievement...",
  "athlete_stats_context": "YTD: 450km in 45 runs...",
  "campus_coach_session": {...},
  "enduraw_data": {...},
  "streams_compressed": {
    "blocks": [...],
    "route_landmarks": [...]
  },
  "active_modules": ["campus_coach", "enduraw"]
}
```

## Output Format

### Content Generation Output

```json
{
  "title": "Enhanced activity title (max 50 chars)",
  "description": "Enhanced activity description\n\n@Generated by Strava AI Boost",
  "confidence": 0.85
}
```

**CRITICAL**: 
- Return ONLY JSON, no explanations
- Title max 50 characters
- Description ends with "\n\n@Generated by Strava AI Boost"

## Best Practices

### Prompt Development

1. **Centralization**: All prompts in `embedded_prompts.py`
2. **Testing**: Test changes locally before deploying
3. **Consistency**: Maintain consistent terminology
4. **Documentation**: Document changes in CHANGELOG.md
5. **Examples**: Include concrete examples for each rule

### Code Organization

1. **Separation**: Prompts in `embedded_prompts.py`, logic in agent files
2. **No Duplication**: Agent code passes JSON data, doesn't duplicate rules
3. **Maintainability**: Update prompt once, affects all agents
4. **Version Control**: Commit prompt changes with descriptive messages

### Performance

1. **No File I/O**: Embedded prompts = no loading overhead
2. **Memory**: Prompts loaded once per Lambda cold start
3. **Caching**: DynamoDB caches processed data (streams, landmarks)
4. **Token Optimization**: Compressed data reduces token usage

## Monitoring

### CloudWatch Logs

Monitor agent behavior through logs:

```bash
# Content generation agent logs
aws logs tail /aws/lambda/StravaAIBoost-ContentGenerator --follow --profile your-aws-profile

# AgentCore runtime logs
aws logs tail /aws/bedrock-agentcore/runtimes/content_gen-* --follow --profile your-aws-profile

# Search for specific patterns
aws logs filter-log-events \
  --log-group-name "/aws/lambda/StravaAIBoost-ContentGenerator" \
  --filter-pattern "RÈGLE CRITIQUE" \
  --profile your-aws-profile
```

### Key Metrics

- Prompt length (characters)
- Token usage (input + output)
- Content generation success rate
- Fallback usage frequency
- Campus Coach matching accuracy

## Troubleshooting

### Common Issues

**Issue**: Agent not following new rules
```bash
# Solution: Redeploy agent
cd src/agents
agentcore deploy --env region=eu-west-1
```

**Issue**: Prompt too long (context overflow)
```bash
# Solution: Reduce examples in embedded_prompts.py
# Keep rules, reduce examples to 1-2 per section
```

**Issue**: Content not preserving original input
```bash
# Solution: Check RÈGLE #1 in CONTENT_GENERATION_PROMPT
# Verify original_input is passed in JSON data
```

## Related Documentation

- [AgentCore Integration Guide](AGENTCORE.md)
- [Architecture Overview](../reference/ARCHITECTURE.md)
- [Changelog](../reference/CHANGELOG.md)

---

**Note**: This system uses embedded prompts for maximum reliability. All prompt logic is centralized in `src/agents/embedded_prompts.py` for easy maintenance.
