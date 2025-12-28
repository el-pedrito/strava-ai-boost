# AgentCore Guide

Complete guide to AgentCore integration in Strava AI Boost.

## Overview

AgentCore provides the AI agent runtime and memory system for Strava AI Boost, enabling:

- **Persistent Memory**: Learns your writing style and avoids repetition
- **Browser Tool**: Automated Campus Coach session extraction
- **Agent Runtime**: Scalable, serverless AI agent execution

## Architecture

### AgentCore Components

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   AgentCore     │    │   AgentCore      │    │   AgentCore     │
│    Memory       │◄──►│    Runtime       │◄──►│  Browser Tool   │
│                 │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Personalized   │    │  Content Gen     │    │  Campus Coach   │
│  Content Gen    │    │     Agent        │    │   Extraction    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Integration Points

1. **Content Generation Agent**: Uses AgentCore Memory for personalization
2. **Campus Coach Agent**: Uses AgentCore Browser Tool for web scraping
3. **Lambda Functions**: Invoke agents via Bedrock Agent Runtime
4. **Step Functions**: Orchestrate agent workflows

## AgentCore Memory

### Purpose

AgentCore Memory provides persistent, intelligent memory for AI agents:

- **Style Learning**: Remembers your preferred writing style
- **Expression Tracking**: Avoids repetitive phrases across activities
- **Context Retention**: Maintains conversation history and preferences
- **Semantic Search**: Finds relevant past interactions

### Memory Types

**Event Memory**:
- Stores specific activity enhancements
- Tracks successful content patterns
- Records user feedback and preferences

**Semantic Memory**:
- Learns writing style patterns
- Identifies preferred vocabulary
- Understands tone preferences
- Recognizes content structure preferences

### Configuration

```yaml
# AgentCore Memory Configuration
memory:
  name: "strava-ai-boost-memory"
  type: "hybrid"  # Event + Semantic
  retention_policy:
    event_memory: "90_days"
    semantic_memory: "permanent"
  indexing:
    embedding_model: "amazon.titan-embed-text-v1"
    dimensions: 1536
```

### Usage in Content Generation

```python
# Example: Content generation with memory
from agentcore import Memory

memory = Memory("strava-ai-boost-memory")

# Store successful content
memory.store_event({
    "activity_id": "12345",
    "generated_content": "Epic trail run through...",
    "user_feedback": "positive",
    "style_elements": ["technical", "motivational", "detailed"]
})

# Retrieve style preferences
style_context = memory.semantic_search(
    query="user writing style preferences",
    limit=5
)

# Generate personalized content
content = generate_content(
    activity_data=activity,
    style_context=style_context,
    avoid_phrases=memory.get_recent_phrases(days=30)
)
```

## AgentCore Browser Tool

### Purpose

AgentCore Browser Tool enables automated web interaction for:

- **Campus Coach Session Extraction**: Automated login and data scraping
- **Dynamic Content Handling**: JavaScript-rendered pages
- **Secure Credential Management**: Encrypted credential storage
- **Retry Logic**: Handles network issues and rate limiting

### Browser Tool Configuration

```yaml
# Campus Coach Browser Agent
agent:
  name: "strava-ai-boost-campus-coach"
  runtime: "browser"
  tools:
    - name: "browser"
      config:
        headless: true
        timeout: 30000
        viewport:
          width: 1920
          height: 1080
        user_agent: "Mozilla/5.0 (compatible; StravaAIBoost/1.0)"
```

### Campus Coach Extraction Workflow

1. **Authentication**:
   ```python
   # Navigate to login page
   await browser.goto("https://campus.coach/login")
   
   # Enter credentials from Secrets Manager
   await browser.fill("#username", credentials["username"])
   await browser.fill("#password", credentials["password"])
   await browser.click("#login-button")
   ```

2. **Session Navigation**:
   ```python
   # Navigate to training sessions
   await browser.goto("https://campus.coach/training/sessions")
   
   # Extract current week sessions
   sessions = await browser.evaluate("""
       () => {
           const sessionElements = document.querySelectorAll('.session-card');
           return Array.from(sessionElements).map(el => ({
               title: el.querySelector('.session-title').textContent,
               description: el.querySelector('.session-description').textContent,
               date: el.querySelector('.session-date').textContent,
               type: el.querySelector('.session-type').textContent
           }));
       }
   """)
   ```

3. **Data Processing**:
   ```python
   # Process and store sessions
   for session in sessions:
       processed_session = {
           "session_id": generate_session_id(session),
           "title": clean_text(session["title"]),
           "description": parse_description(session["description"]),
           "planned_date": parse_date(session["date"]),
           "session_type": normalize_type(session["type"]),
           "extracted_at": datetime.now(UTC).isoformat()
       }
       
       # Store in DynamoDB
       store_session(processed_session)
   ```

### Error Handling

```python
# Retry logic for browser operations
async def extract_with_retry(max_retries=3):
    for attempt in range(max_retries):
        try:
            return await extract_sessions()
        except TimeoutError:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise
        except AuthenticationError:
            # Refresh credentials and retry
            credentials = await refresh_credentials()
            continue
```

## AgentCore Runtime

### Deployment

AgentCore agents are deployed using CLI scripts:

```bash
# Deploy AgentCore Agents (Content Generation + Campus Coach)
./scripts/deploy_agentcore_agents.sh
./scripts/deploy_campus_coach_agent.sh

# Setup AgentCore Memory
./scripts/setup_memory.sh
```

### Agent Invocation

Agents are invoked from Lambda functions via Bedrock Agent Runtime:

```python
import boto3
from botocore.exceptions import ClientError

bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='eu-west-1')

def invoke_content_generation_agent(activity_data, user_id):
    try:
        response = bedrock_agent_runtime.invoke_agent(
            agentId='strava-ai-boost-content-generator',
            agentAliasId='TSTALIASID',
            sessionId=f"session-{user_id}-{int(time.time())}",
            inputText=json.dumps({
                "activity_data": activity_data,
                "user_id": user_id,
                "task": "generate_enhanced_content"
            })
        )
        
        # Process streaming response
        content = ""
        for event in response['completion']:
            if 'chunk' in event:
                content += event['chunk']['bytes'].decode('utf-8')
        
        return json.loads(content)
        
    except ClientError as e:
        logger.error(f"AgentCore invocation failed: {e}")
        raise
```

### Monitoring

```bash
# Monitor AgentCore agent logs
aws logs tail /aws/bedrock-agentcore/runtimes/strava-ai-boost-content-generator --follow --profile your-aws-profile

# Check agent status
agentcore agent list --profile your-aws-profile

# Monitor memory usage
agentcore memory stats --name strava-ai-boost-memory --profile your-aws-profile
```

## Performance Optimization

### Memory Optimization

```python
# Optimize memory queries
memory_config = {
    "max_results": 10,
    "similarity_threshold": 0.8,
    "cache_ttl": 300,  # 5 minutes
    "batch_size": 50
}

# Use semantic search efficiently
relevant_memories = memory.semantic_search(
    query=f"writing style for {activity_type} activities",
    filters={"user_id": user_id, "feedback": "positive"},
    **memory_config
)
```

### Browser Tool Optimization

```yaml
# Optimized browser configuration
browser_config:
  headless: true
  disable_images: true
  disable_javascript: false  # Required for Campus Coach
  timeout: 15000
  navigation_timeout: 10000
  connection_pool_size: 5
```

### Agent Runtime Optimization

- **Warm Agents**: Keep agents warm to reduce cold start latency
- **Batch Processing**: Process multiple activities together when possible
- **Caching**: Cache frequently accessed data in memory
- **Async Operations**: Use async/await for I/O operations

## Troubleshooting

### Common Issues

**"AgentCore agent not found"**
```bash
# Check agent deployment
agentcore agent list --profile your-aws-profile

# Redeploy if missing
./scripts/deploy_agentcore_agents.sh
```

**"Memory service unavailable"**
```bash
# Check memory status
agentcore memory list --profile your-aws-profile

# Recreate memory if needed
./scripts/setup_memory.sh
```

**"Browser Tool timeout"**
- Increase timeout in agent configuration
- Check Campus Coach website availability
- Verify credentials are valid

### Debug Commands

```bash
# Test agent connectivity
agentcore invoke strava-ai-boost-content-generator --input '{"test": true}'

# Check memory connectivity
agentcore memory query --name strava-ai-boost-memory --query "test"

# Monitor browser agent logs
aws logs filter-log-events --log-group-name /aws/bedrock-agentcore/runtimes/strava-ai-boost-campus-coach --filter-pattern "ERROR" --profile your-aws-profile
```

## Security Considerations

### Credential Management

- Campus Coach credentials stored in AWS Secrets Manager
- Automatic credential rotation (when supported)
- Encrypted in transit and at rest
- Access logged and monitored

### Memory Security

- User data isolated by user_id
- Encryption at rest using AWS KMS
- Access controlled via IAM policies
- Regular security audits

### Browser Tool Security

- Sandboxed browser environment
- No persistent storage of sensitive data
- Network traffic monitoring
- Secure credential injection

## Best Practices

### Memory Management

1. **Regular Cleanup**: Remove old, irrelevant memories
2. **Quality Control**: Store only high-quality interactions
3. **Privacy**: Respect user privacy preferences
4. **Performance**: Monitor memory query performance

### Browser Automation

1. **Respectful Scraping**: Follow rate limits and robots.txt
2. **Error Handling**: Graceful degradation on failures
3. **Monitoring**: Track success rates and performance
4. **Maintenance**: Regular updates for website changes

### Agent Development

1. **Modular Design**: Separate concerns into different agents
2. **Error Recovery**: Implement retry logic and fallbacks
3. **Logging**: Comprehensive logging for debugging
4. **Testing**: Regular testing of agent functionality