# Strava AI Boost - Technical Architecture

**Version:** v0.1.0 - Infrastructure Complete  
**Last Updated:** 2025-12-21

This document provides detailed technical implementation information for the Strava AI Boost system, including AWS services configuration, data models, and integration patterns.

## Infrastructure Overview

### AWS CDK Stack Organization

The infrastructure is organized into 5 modular CDK stacks:

1. **CoreInfrastructureStack** - Foundation services (DynamoDB, IAM, Secrets)
2. **WebhookProcessingStack** - Strava webhook handling (SQS, Lambda, API Gateway)
3. **ContentGenerationStack** - AI content generation (Step Functions, Bedrock)
4. **ApiGatewayStack** - Local interface API (REST API, CORS)
5. **MonitoringStack** - Observability (CloudWatch, X-Ray, alarms)

### DynamoDB Tables

#### 1. strava-ai-boost-activities
```
Partition Key: activity_id (string)
Attributes:
- original_description (string)
- enhanced_description (string)
- processing_status (string)
- modules_used (string[])
- created_at (timestamp)
- updated_at (timestamp)
- streams_data (map)
- enhancement_metadata (map)

GSI: ProcessingStatusIndex
- Partition Key: processing_status
- Sort Key: created_at
```

#### 2. strava-ai-boost-user-configuration
```
Partition Key: user_id (string)
Attributes:
- strava_connected (boolean)
- modules_config (map)
- rate_limit_status (map)
- enhancement_paused (boolean)
- last_updated (timestamp)
- oauth_token_status (string)
```

#### 3. strava-ai-boost-rate-limits
```
Partition Key: limit_type (string) # 'short_term' | 'daily'
Attributes:
- current_usage (number)
- reset_time (timestamp)
- last_request (timestamp)
- ttl (number) # Auto-cleanup
```

#### 4. strava-ai-boost-campus-coaching-sessions
```
Partition Key: session_date (string)
Sort Key: session_id (string)
Attributes:
- session_data (map)
- week_number (string)
- extracted_at (timestamp)
- session_type (string)
- difficulty_level (string)

GSI: WeekNumberIndex
- Partition Key: week_number
- Sort Key: session_date
```

### Lambda Functions

#### 1. WebhookHandler
```python
Runtime: Python 3.12
Memory: 256 MB
Timeout: 30 seconds
Environment Variables:
- PROCESSING_QUEUE_URL
- ACTIVITIES_TABLE
- RATE_LIMITS_TABLE
- STRAVA_OAUTH_SECRET
```

#### 2. ActivityProcessor
```python
Runtime: Python 3.12
Memory: 512 MB
Timeout: 300 seconds (5 minutes)
Environment Variables:
- ACTIVITIES_TABLE
- RATE_LIMITS_TABLE
- STRAVA_OAUTH_SECRET
```

#### 3. RateLimiter
```python
Runtime: Python 3.12
Memory: 128 MB
Timeout: 60 seconds
Environment Variables:
- RATE_LIMITS_TABLE
```

### SQS Configuration

#### Main Processing Queue
```
Name: strava-ai-boost-activity-processing
Visibility Timeout: 35 minutes
Retention Period: 14 days
Encryption: KMS managed
Dead Letter Queue: Yes (maxReceiveCount: 3)
```

#### Dead Letter Queue
```
Name: strava-ai-boost-activity-processing-dlq
Retention Period: 14 days
Encryption: KMS managed
```

### IAM Roles and Policies

#### WebhookLambdaRole
```json
{
  "AssumeRolePolicyDocument": {
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  },
  "ManagedPolicyArns": [
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  ],
  "Policies": [{
    "PolicyName": "DynamoDBAccess",
    "PolicyDocument": {
      "Statement": [{
        "Effect": "Allow",
        "Action": [
          "dynamodb:PutItem",
          "dynamodb:GetItem", 
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ],
        "Resource": [
          "arn:aws:dynamodb:eu-west-1:*:table/strava-ai-boost-activities",
          "arn:aws:dynamodb:eu-west-1:*:table/strava-ai-boost-rate-limits"
        ]
      }]
    }
  }]
}
```

#### ContentLambdaRole
```json
{
  "Policies": [{
    "PolicyName": "BedrockAccess",
    "PolicyDocument": {
      "Statement": [{
        "Effect": "Allow",
        "Action": [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ],
        "Resource": [
          "arn:aws:bedrock:eu-west-1::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
        ]
      }]
    }
  }, {
    "PolicyName": "AgentCoreAccess", 
    "PolicyDocument": {
      "Statement": [{
        "Effect": "Allow",
        "Action": [
          "bedrock-agentcore:InvokeAgent",
          "bedrock-agentcore:GetAgent",
          "bedrock-agentcore:ListAgents"
        ],
        "Resource": "*"
      }]
    }
  }]
}
```

### Secrets Manager

#### strava-ai-boost-oauth-tokens
```json
{
  "access_token": "string",
  "refresh_token": "string", 
  "expires_at": "timestamp",
  "token_type": "Bearer",
  "scope": "read,activity:write"
}
```

#### strava-ai-boost-campus-coach-credentials
```json
{
  "username": "string",
  "password": "string",
  "login_url": "https://campus.coach/login",
  "session_cookies": "map"
}
```

## Data Models

### Core Data Structures

```python
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel
from datetime import datetime

class ActivityData(BaseModel):
    """Strava activity data model"""
    id: str
    name: str
    description: Optional[str]
    type: Literal['Run', 'Ride', 'Swim', 'Workout']
    distance: float
    moving_time: int
    elapsed_time: int
    total_elevation_gain: float
    start_date: datetime
    average_speed: Optional[float]
    max_speed: Optional[float]
    average_heartrate: Optional[int]
    max_heartrate: Optional[int]
    # ... 67+ additional Strava fields

class StreamsData(BaseModel):
    """Strava streams data model"""
    velocity_smooth: List[float]
    heartrate: List[int]
    time: List[int]
    distance: List[float]
    altitude: List[float]
    cadence: Optional[List[int]]
    watts: Optional[List[int]]
    temp: Optional[List[int]]

class ProcessingStatus(BaseModel):
    """Activity processing status"""
    activity_id: str
    status: Literal['queued', 'processing', 'completed', 'failed', 'paused']
    step: str
    timestamp: datetime
    error_message: Optional[str] = None
    modules_active: List[str]
    retry_count: int = 0

class ModuleConfig(BaseModel):
    """Module configuration"""
    module_id: str
    enabled: bool
    credentials: Optional[Dict[str, str]] = None
    settings: Dict[str, Any]
    last_updated: datetime

class StravaRateLimit(BaseModel):
    """Rate limit tracking"""
    limit_type: Literal['short_term', 'daily']
    current_usage: int
    limit_value: int
    reset_time: datetime
    last_request: datetime
```

## Integration Patterns

### Strava API Integration

#### Rate Limiting Strategy
```python
class StravaRateLimiter:
    def __init__(self):
        self.short_term_limit = 100  # per 15 minutes
        self.daily_limit = 1000      # per day
        
    async def check_and_wait(self) -> bool:
        # Check DynamoDB for current usage
        short_term_usage = await self.get_usage('short_term')
        daily_usage = await self.get_usage('daily')
        
        if short_term_usage >= self.short_term_limit:
            wait_time = await self.get_reset_time('short_term')
            await asyncio.sleep(wait_time)
            
        if daily_usage >= self.daily_limit:
            raise RateLimitExceededError("Daily limit reached")
            
        return True
```

#### OAuth Token Management
```python
class StravaOAuthManager:
    async def get_valid_token(self) -> str:
        secret = await self.secrets_client.get_secret_value(
            SecretId='strava-ai-boost-oauth-tokens'
        )
        token_data = json.loads(secret['SecretString'])
        
        if datetime.now() >= token_data['expires_at']:
            token_data = await self.refresh_token(token_data['refresh_token'])
            await self.store_token(token_data)
            
        return token_data['access_token']
```

### AgentCore Integration

#### Memory-Based Content Generation
```python
from strands import Agent
from agentcore_memory import MemoryClient

class ContentGenerationAgent(Agent):
    def __init__(self):
        super().__init__()
        self.memory = MemoryClient()
        self.bedrock_client = BedrockClient()
    
    async def generate_content(self, activity_data: ActivityData, 
                             streams_data: StreamsData,
                             user_id: str) -> EnhancedContent:
        # Retrieve user's personal style from memory
        personal_style = await self.memory.get_user_style(user_id)
        previous_expressions = await self.memory.get_used_expressions(user_id)
        
        # Analyze activity patterns using Bedrock
        patterns = await self.analyze_patterns(streams_data)
        
        # Generate personalized content avoiding repetition
        content = await self.bedrock_generate(
            patterns, 
            personal_style,
            previous_expressions
        )
        
        # Store new expressions and style updates in memory
        await self.memory.store_generated_content(user_id, content)
        
        return content
```

#### Campus Coach Browser Agent
```python
class CampusCoachAgent:
    def __init__(self):
        self.agentcore_client = AgentCoreClient()
        
    async def extract_sessions(self, credentials: Dict[str, str]) -> List[Session]:
        # Known issue: Cold start problem with ~30% first-try success rate
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self.agentcore_client.invoke_agent(
                    agent_name='campus-coach-scraper',
                    input_data={
                        'credentials': credentials,
                        'action': 'extract_sessions'
                    }
                )
                return response['sessions']
            except AgentCoreError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    await asyncio.sleep(wait_time)
                else:
                    raise
```

## Security Configuration

### Encryption at Rest
- **DynamoDB**: AWS managed encryption (SSE-S3)
- **SQS**: KMS managed encryption
- **Secrets Manager**: Automatic encryption with rotation
- **S3** (if used): Server-side encryption (SSE-S3)

### Encryption in Transit
- **API Gateway**: TLS 1.2+ enforced
- **Internal AWS**: Service-to-service encryption
- **Local Interface**: HTTPS with self-signed certificates

### IAM Security
- **Principle of Least Privilege**: All roles have minimal required permissions
- **AWS Managed Policies**: Prefer AWS managed over custom policies
- **Cross-Service Access**: Only where explicitly required
- **Resource-Level Permissions**: Specific table/queue ARNs where possible

## Performance Metrics

### Current Performance (v0.1.0)
- **CDK Synthesis**: 4-5 seconds for complete infrastructure
- **Property Tests**: 100 iterations per test in <5 seconds
- **Infrastructure Validation**: 10 comprehensive tests
- **DynamoDB Operations**: <100ms average latency
- **Lambda Cold Start**: <2 seconds for Python 3.12

### Target Performance
- **Webhook Processing**: <5 seconds to queue
- **Content Generation**: <30 seconds end-to-end
- **AgentCore Memory Lookup**: <500ms
- **Dashboard Loading**: <2 seconds
- **Configuration Changes**: <1 second

## Cost Estimation

### Per Activity Cost Breakdown
- **Lambda Executions**: $0.001
- **DynamoDB Operations**: $0.001
- **Step Functions**: $0.003
- **Bedrock API Calls**: $0.005
- **SQS Messages**: $0.0001
- **AgentCore Memory**: $0.001
- **Total Estimated**: ~$0.02 per activity

### Monthly Cost (100 activities)
- **Compute**: ~$1.00
- **Storage**: ~$0.50
- **API Calls**: ~$0.50
- **Total**: ~$2.00/month

## Monitoring and Observability

### CloudWatch Metrics
- Activity processing success rate
- API call latency and error rates
- Rate limit utilization
- Cost per activity
- Lambda function performance

### Alarms
- Processing failure rate > 5%
- Rate limit utilization > 80%
- Daily cost exceeds threshold
- Campus Coach extraction failures

### X-Ray Tracing
- Step Functions workflow tracing
- Request correlation across services
- Performance bottleneck identification

## Dependencies

### Python Dependencies (Development)
```
aws-cdk-lib==2.219.0
constructs>=10.0.0,<11.0.0
boto3>=1.34.0
pydantic>=2.0.0
flask>=3.0.0
pytest>=7.0.0
hypothesis>=6.0.0
moto>=4.2.0
```

### Python Dependencies (Lambda Runtime)
```
boto3>=1.34.0
requests>=2.31.0
requests-oauthlib>=1.3.1
pydantic>=2.0.0
typing-extensions>=4.0.0
```

### AWS Services
- **CDK**: v2.219.0
- **Python Runtime**: 3.12
- **Region**: eu-west-1 (Ireland)
- **Bedrock Model**: anthropic.claude-3-5-sonnet-20241022-v2:0

## Deployment Configuration

### Environment Variables
```bash
AWS_PROFILE=your-aws-profile
AWS_REGION=eu-west-1
CDK_DEFAULT_REGION=eu-west-1
```

### CDK Context
```json
{
  "region": "eu-west-1",
  "environment": "development",
  "removal_policy": "DESTROY"
}
```

---

**Version:** v0.1.0 - Infrastructure Complete  
**Last Updated:** 2025-12-21  
**Next Version:** v0.2.0 - Strava OAuth Integration