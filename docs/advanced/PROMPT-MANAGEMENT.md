# Prompt Management System

Centralized prompt management for Strava AI Boost agents and Bedrock fallbacks.

## Overview

The Strava AI Boost prompt management system provides centralized, externalized prompts for both AgentCore agents and Bedrock fallback operations. This system ensures consistency, maintainability, and easy updates without code changes.

**NEW in v1.8.0**: Added explicit tool usage instructions for AgentCore agents with structured JSON responses.

## Architecture

### System Components

```
agentcore/prompts/
├── system_prompts.py           # Core prompt management system
├── campus_coach_agent_prompt.md    # Campus Coach agent prompt
└── content_generation_agent_prompt.md  # Content generation agent prompt (UPDATED)
```

### Integration Points

- **AgentCore Agent Tools**: Reference prompts for consistency in tool implementations
- **Structured Tools**: NEW - Explicit tool usage instructions for JSON responses
- **Lambda Fallbacks**: Use Bedrock-optimized versions of the same prompts
- **Automatic Fallback**: Hardcoded prompts if external files unavailable

## Tool Integration (NEW v1.8.0)

### Content Generation Agent Tool Instructions

The content generation prompt now includes explicit tool usage instructions:

```markdown
## Tool Usage Instructions

**CRITICAL**: You have access to the `generate_strava_content` tool that handles all content generation logic. When processing a request:

1. **Always use the `generate_strava_content` tool** to generate content
2. **Pass all available data** to the tool (activity_data, streams_data, user_id, etc.)
3. **Return the tool's response directly** - do not modify the JSON structure
4. **The tool handles all analysis, personalization, and formatting**

**DO NOT** generate content manually - always use the tool to ensure proper JSON formatting and consistency.
```

### AgentCore YAML Configuration

```yaml
# agentcore/agents/content_generation_agent.yaml
agent:
  framework: strands
  prompt_file: ../prompts/content_generation_agent_prompt.md

tools:
  - name: generate_strava_content
    description: "Generate enhanced Strava activity content with personalization and memory integration"
    function: generate_strava_content
```

## Architecture Note

**Important**: The current AgentCore agents in `src/agents/` are **tool implementations** for AgentCore runtime, not standalone Strands agents. The prompt system is primarily used by:

1. **AgentCore Tools**: NEW - Structured tools with explicit usage instructions
2. **Lambda Fallbacks**: Direct Bedrock calls when AgentCore is unavailable
3. **Tool Reference**: AgentCore tools can reference prompts for consistency
4. **Future Extensions**: Framework for when full agent implementations are needed

## Core Classes

### PromptManager

Central class for loading and caching prompt files.

```python
from agentcore.prompts.system_prompts import PromptManager

# Initialize
prompt_manager = PromptManager()

# Load specific prompt
prompt = prompt_manager.load_prompt('content_generation_agent_prompt')

# Get system prompt for agent type
system_prompt = prompt_manager.get_system_prompt('content_generation')

# Get Bedrock-optimized prompt
bedrock_prompt = prompt_manager.get_bedrock_prompt('content_generation')
```

### Key Methods

| Method | Purpose | Returns |
|--------|---------|---------|
| `load_prompt(name)` | Load prompt file with caching | Prompt content string |
| `get_system_prompt(agent_type)` | Get prompt for specific agent | System prompt string |
| `get_bedrock_prompt(agent_type)` | Get Bedrock-optimized prompt | Bedrock prompt string |
| `clear_cache()` | Clear prompt cache | None |

## Usage Patterns

### AgentCore Agent Tools

```python
# In src/agents/content_agent.py (AgentCore tools)
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'agentcore', 'prompts'))

try:
    from system_prompts import get_content_generation_prompt
except ImportError:
    def get_content_generation_prompt():
        return "Content generation prompt not available"

# Tools can reference prompts for consistency
def generate_strava_content(activity_data, **kwargs):
    """Tool that uses externalized prompts for guidance"""
    # Tool implementation here
    pass
```

### Lambda Fallbacks

```python
# In lambda_functions/content_generator.py
try:
    from system_prompts import get_bedrock_content_generation_prompt
    base_prompt = get_bedrock_content_generation_prompt()
except ImportError:
    # Fallback to hardcoded prompt
    base_prompt = "Default Bedrock prompt..."

# Use in Bedrock API call
prompt = f"{base_prompt}\n\nCURRENT TASK: {task_description}"
```

## Prompt Types

### Agent Types Supported

| Agent Type | Prompt File | Usage |
|------------|-------------|-------|
| `campus_coach` | `campus_coach_agent_prompt.md` | Campus Coach session extraction |
| `content_generation` | `content_generation_agent_prompt.md` | Activity content generation |

### Bedrock Optimizations

Bedrock prompts include additional markers:

```markdown
BEDROCK DIRECT MODE: You are operating in direct Bedrock mode without AgentCore tools.
Provide complete responses based on the input data without tool calls.
Return structured JSON responses when appropriate.

[Original prompt content follows...]
```

## Deployment and Updates

### Initial Deployment

```bash
# Deploy with CDK (includes Lambda functions)
cdk deploy --profile your-aws-profile

# Deploy AgentCore agents
agentcore agent deploy --name content_gen
agentcore agent deploy --name campus_coach
```

### Updating Prompts

1. **Edit Prompt File**:
   ```bash
   # Edit the prompt file
   vim agentcore/prompts/content_generation_agent_prompt.md
   ```

2. **Deploy Changes**:
   ```bash
   # For Lambda functions (primary usage)
   cdk deploy --profile your-aws-profile
   
   # For AgentCore agents (if using prompts in tools)
   agentcore agent deploy --name content_gen
   ```

3. **Verify Deployment**:
   ```bash
   # Check Lambda logs for prompt loading
   aws logs tail /aws/lambda/StravaAIBoost-ContentGenerator --follow --profile your-aws-profile
   
   # Test AgentCore agent
   agentcore invoke content_gen --input '{"test": true}'
   ```

## Error Handling

### Fallback Mechanisms

The system includes multiple fallback layers:

1. **Primary**: Load from external `.md` files
2. **Secondary**: Use hardcoded prompts in code
3. **Tertiary**: Basic error handling with minimal prompts

### Common Issues

| Issue | Symptoms | Solution |
|-------|----------|----------|
| File not found | `FileNotFoundError` in logs | Check file exists in `agentcore/prompts/` |
| Import error | `ImportError` in logs | Verify path configuration |
| Cache issues | Stale prompts | Call `prompt_manager.clear_cache()` |
| Permission error | Access denied | Check file permissions |

### Debugging

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Test prompt loading
from system_prompts import PromptManager
pm = PromptManager()
try:
    prompt = pm.load_prompt('content_generation_agent_prompt')
    print(f"Loaded prompt: {len(prompt)} characters")
except Exception as e:
    print(f"Error: {e}")
```

## Best Practices

### Prompt Development

1. **Version Control**: Always commit prompt changes with descriptive messages
2. **Testing**: Test prompts in both AgentCore and Bedrock modes
3. **Consistency**: Maintain consistent terminology across prompts
4. **Documentation**: Document prompt changes in CHANGELOG.md

### File Management

1. **Naming**: Use descriptive, consistent file names
2. **Structure**: Keep prompts well-organized with clear sections
3. **Size**: Keep prompts reasonable in size (< 10KB recommended)
4. **Encoding**: Use UTF-8 encoding for all prompt files

### Performance

1. **Caching**: Prompts are cached automatically for performance
2. **Loading**: Prompts are loaded once per Lambda cold start
3. **Memory**: Cached prompts consume minimal memory
4. **Latency**: No significant impact on response times

## Security Considerations

### Access Control

- Prompt files are deployed with Lambda functions (read-only)
- No sensitive information should be stored in prompts
- AgentCore agents load prompts from secure runtime environment

### Content Safety

- Prompts should include appropriate safety guidelines
- Avoid prompts that could generate harmful content
- Include content filtering instructions where appropriate

## Monitoring

### CloudWatch Metrics

Monitor prompt loading through Lambda logs:

```bash
# Search for prompt loading errors
aws logs filter-log-events \
  --log-group-name "/aws/lambda/StravaAIBoost-ContentGenerator" \
  --filter-pattern "prompt" \
  --profile your-aws-profile
```

### Key Metrics to Track

- Prompt loading success rate
- Fallback usage frequency
- Content generation quality scores
- Error rates by prompt type

## Troubleshooting

### Common Problems

**Problem**: Prompts not updating after deployment
```bash
# Solution: Clear Lambda cache by updating environment variable
aws lambda update-function-configuration \
  --function-name StravaAIBoost-ContentGenerator \
  --environment Variables='{PROMPT_VERSION="'$(date +%s)'"}' \
  --profile your-aws-profile
```

**Problem**: AgentCore agents using old prompts
```bash
# Solution: Redeploy agents
agentcore agent deploy --name content_gen --force
```

**Problem**: Import errors in Lambda
```bash
# Solution: Check Lambda layer includes prompt files
aws lambda get-layer-version \
  --layer-name strava-ai-boost-dependencies \
  --version-number 1 \
  --profile your-aws-profile
```

## Future Enhancements

### Planned Features

1. **Dynamic Prompt Loading**: Hot-reload prompts without redeployment
2. **A/B Testing**: Support for multiple prompt versions
3. **Prompt Analytics**: Detailed metrics on prompt performance
4. **Template System**: Parameterized prompts with variables

### Migration Path

When adding new prompt types:

1. Create new `.md` file in `agentcore/prompts/`
2. Add mapping in `system_prompts.py`
3. Update agents/lambdas to use new prompt
4. Deploy and test

## Related Documentation

- [AgentCore Integration Guide](AGENTCORE.md)
- [Content Generation System](../user-guide/CONTENT-GENERATION.md)
- [Campus Coach Module](../user-guide/CAMPUS-COACH.md)
- [Architecture Overview](../reference/ARCHITECTURE.md)

---

**Note**: This prompt management system is designed for production use with automatic fallbacks and comprehensive error handling. Always test prompt changes in development before deploying to production.