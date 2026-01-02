# ⚡ Performance Optimization
This guide provides comprehensive instructions for optimizing the performance of your Strava AI Boost system, including AgentCore Memory tuning, Browser Tool optimization, and overall system performance improvements.

## Table of Contents

1. [Performance Overview](#performance-overview)
2. [Lambda Function Optimization](#lambda-function-optimization)
3. [AgentCore Memory Tuning](#agentcore-memory-tuning)
4. [Browser Tool Optimization](#browser-tool-optimization)
5. [DynamoDB Performance](#dynamodb-performance)
6. [Step Functions Optimization](#step-functions-optimization)
7. [Cost Optimization](#cost-optimization)
8. [Monitoring and Metrics](#monitoring-and-metrics)

## Performance Overview

### Current Performance Targets

The Strava AI Boost system is designed to meet these performance targets:

#### Processing Times
- **Webhook Processing**: < 5 seconds to queue
- **Content Generation**: < 30 seconds end-to-end
- **Campus Coach Extraction**: 3-4 minutes (daily batch)
- **AgentCore Memory Lookup**: < 500ms
- **Dashboard Loading**: < 2 seconds

#### Success Rates
- **Overall Processing**: 98% success rate
- **Campus Coach Agent**: 90% after retries (30% first-try)
- **Content Generation**: 99% success rate
- **Memory Operations**: 99.9% success rate

#### Cost Targets
- **Per Activity Processing**: ~$0.02
- **Monthly Cost (100 activities)**: ~$2.00
- **AgentCore Memory**: $0.001 per lookup
- **Bedrock API**: $0.005 per generation

### Performance Bottlenecks

Common performance bottlenecks and their solutions:

1. **Lambda Cold Starts**: Use provisioned concurrency for critical functions
2. **DynamoDB Throttling**: Switch to on-demand billing or increase capacity
3. **AgentCore Memory Latency**: Optimize memory configuration and caching
4. **Campus Coach Cold Starts**: Implement retry logic and warm pools
5. **Bedrock API Latency**: Optimize prompts and use caching

## Lambda Function Optimization

### Memory and Timeout Configuration

#### Webhook Handler Optimization

```bash
# Current configuration
aws lambda get-function-configuration --function-name StravaAIBoost-WebhookHandler --profile your-aws-profile --query '{MemorySize:MemorySize,Timeout:Timeout,Runtime:Runtime}'

# Optimal configuration for webhook processing
aws lambda update-function-configuration \
  --function-name StravaAIBoost-WebhookHandler \
  --memory-size 256 \
  --timeout 30 \
  --profile your-aws-profile

# Monitor performance after changes
aws logs filter-log-events \
  --log-group-name /aws/lambda/StravaAIBoost-WebhookHandler \
  --filter-pattern "REPORT" \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --profile your-aws-profile
```

#### Content Generator Optimization

```bash
# Optimal configuration for content generation
aws lambda update-function-configuration \
  --function-name StravaAIBoost-ContentGenerator \
  --memory-size 512 \
  --timeout 180 \
  --profile your-aws-profile

# Enable provisioned concurrency for consistent performance
aws lambda put-provisioned-concurrency-config \
  --function-name StravaAIBoost-ContentGenerator \
  --provisioned-concurrency-config ProvisionedConcurrencyCount=2 \
  --profile your-aws-profile
```

#### Campus Coach Invoker Optimization

```bash
# Configuration for Campus Coach agent invocation
aws lambda update-function-configuration \
  --function-name StravaAIBoost-CampusCoachInvoker \
  --memory-size 256 \
  --timeout 300 \
  --environment Variables='{
    "MAX_RETRIES": "3",
    "RETRY_DELAY": "5",
    "EXPONENTIAL_BACKOFF": "true",
    "WARM_UP_DELAY": "30"
  }' \
  --profile your-aws-profile
```

### Environment Variable Optimization

#### Performance-Related Environment Variables

```python
# Optimal environment variables for Lambda functions
PERFORMANCE_ENV_VARS = {
    # Logging optimization
    "LOG_LEVEL": "INFO",  # Use INFO in production, DEBUG for troubleshooting
    "STRUCTURED_LOGGING": "true",
    
    # Connection optimization
    "CONNECTION_POOL_SIZE": "10",
    "CONNECTION_TIMEOUT": "30",
    "READ_TIMEOUT": "60",
    
    # Caching configuration
    "ENABLE_CACHING": "true",
    "CACHE_TTL": "300",  # 5 minutes
    "CACHE_SIZE": "100",
    
    # Retry configuration
    "MAX_RETRIES": "3",
    "RETRY_DELAY": "2",
    "EXPONENTIAL_BACKOFF": "true",
    
    # Memory optimization
    "MEMORY_OPTIMIZATION": "true",
    "GC_THRESHOLD": "0.8"
}
```

### Code Optimization

#### Connection Pooling

```python
# Optimize boto3 client initialization
import boto3
from botocore.config import Config

# Configure boto3 with connection pooling
config = Config(
    max_pool_connections=50,
    retries={'max_attempts': 3, 'mode': 'adaptive'},
    read_timeout=60,
    connect_timeout=30
)

# Reuse clients across invocations
dynamodb = boto3.client('dynamodb', config=config)
bedrock = boto3.client('bedrock-runtime', config=config)
```

#### Caching Implementation

```python
# Implement in-memory caching for Lambda functions
import functools
import time
from typing import Dict, Any

class LambdaCache:
    def __init__(self, ttl: int = 300):
        self.cache: Dict[str, tuple] = {}
        self.ttl = ttl
    
    def get(self, key: str) -> Any:
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any):
        self.cache[key] = (value, time.time())

# Global cache instance
cache = LambdaCache(ttl=300)

@functools.lru_cache(maxsize=128)
def get_strava_activity(activity_id: str):
    """Cache Strava API responses"""
    # Implementation here
    pass
```

## AgentCore Memory Tuning

### Memory Configuration Optimization

#### Memory Size and Decay Rate

```bash
# Analyze current memory usage
agentcore memory stats --name strava-ai-boost-memory --profile your-aws-profile

# Optimize memory size based on usage patterns
# For active users (>50 activities/month)
agentcore memory configure \
  --name strava-ai-boost-memory \
  --max-memory-size 2000 \
  --memory-decay-rate 0.05 \
  --profile your-aws-profile

# For moderate users (10-50 activities/month)
agentcore memory configure \
  --name strava-ai-boost-memory \
  --max-memory-size 1000 \
  --memory-decay-rate 0.1 \
  --profile your-aws-profile

# For light users (<10 activities/month)
agentcore memory configure \
  --name strava-ai-boost-memory \
  --max-memory-size 500 \
  --memory-decay-rate 0.2 \
  --profile your-aws-profile
```

#### Lookup Optimization

```bash
# Optimize memory lookup performance
agentcore memory configure \
  --name strava-ai-boost-memory \
  --lookup-timeout 10 \
  --max-results 5 \
  --similarity-threshold 0.7 \
  --profile your-aws-profile
```

### Memory Usage Patterns

#### Optimal Memory Structure

```python
# Structure memory data for optimal retrieval
MEMORY_STRUCTURE = {
    "personal_style": {
        "tone": "motivational",
        "technical_level": "intermediate", 
        "emoji_usage": "moderate",
        "preferred_length": "medium",
        "confidence": 0.85
    },
    "expression_patterns": {
        "used_expressions": [
            {"phrase": "crushed it", "frequency": 5, "last_used": "2025-12-20"},
            {"phrase": "feeling strong", "frequency": 3, "last_used": "2025-12-18"}
        ],
        "avoided_expressions": ["easy run", "just jogging"],
        "preferred_expressions": ["solid effort", "great session"]
    },
    "performance_context": {
        "typical_pace": "5:30/km",
        "preferred_distance": "10km",
        "training_focus": "endurance",
        "seasonal_patterns": {"winter": "indoor", "summer": "outdoor"}
    }
}
```

#### Memory Cleanup Strategy

```python
# Implement memory cleanup for optimal performance
async def optimize_memory():
    """Clean up old or irrelevant memory entries"""
    
    # Remove low-confidence entries
    await agentcore_memory.cleanup(
        confidence_threshold=0.3,
        age_threshold_days=90
    )
    
    # Consolidate similar expressions
    await agentcore_memory.consolidate_expressions(
        similarity_threshold=0.8
    )
    
    # Update decay rates based on usage
    usage_stats = await agentcore_memory.get_usage_stats()
    if usage_stats['lookup_frequency'] > 10:  # High usage
        await agentcore_memory.configure(memory_decay_rate=0.03)
    elif usage_stats['lookup_frequency'] < 2:  # Low usage
        await agentcore_memory.configure(memory_decay_rate=0.15)
```

### Memory Performance Monitoring

```bash
# Monitor memory performance metrics
agentcore memory metrics \
  --name strava-ai-boost-memory \
  --start-time $(date -d '24 hours ago' -u +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --profile your-aws-profile

# Key metrics to monitor:
# - Lookup latency (target: <500ms)
# - Hit rate (target: >80%)
# - Memory utilization (target: <90%)
# - Cleanup frequency (target: weekly)
```

## Browser Tool Optimization

### Cold Start Mitigation

#### Warm Pool Configuration

```bash
# Configure warm pool for Campus Coach agent
agentcore agent configure \
  --name campuscoach \
  --warm-pool-size 2 \
  --warm-pool-timeout 300 \
  --warm-pool-delay 30 \
  --profile your-aws-profile
```

#### Retry Logic Optimization

```python
# Optimized retry logic for Campus Coach agent
import asyncio
import random

class CampusCoachRetryHandler:
    def __init__(self):
        self.max_retries = 3
        self.base_delay = 5
        self.max_delay = 60
        self.jitter = True
    
    async def invoke_with_retry(self, agent_name: str, input_data: dict):
        """Invoke Campus Coach agent with optimized retry logic"""
        
        for attempt in range(self.max_retries + 1):
            try:
                # Add warm-up delay for first attempt
                if attempt == 0:
                    await asyncio.sleep(30)  # Browser tool warm-up
                
                response = await self.agentcore_client.invoke_agent(
                    agent_name=agent_name,
                    input_data=input_data,
                    timeout=300
                )
                
                if response.get('success'):
                    return response
                    
            except Exception as e:
                if attempt == self.max_retries:
                    raise e
                
                # Calculate delay with exponential backoff and jitter
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                if self.jitter:
                    delay += random.uniform(0, delay * 0.1)
                
                await asyncio.sleep(delay)
        
        raise Exception("Max retries exceeded")
```

### Browser Session Optimization

#### Session Management

```python
# Optimize browser session lifecycle
class BrowserSessionManager:
    def __init__(self):
        self.session_pool = {}
        self.max_sessions = 5
        self.session_timeout = 300  # 5 minutes
    
    async def get_session(self, session_id: str = None):
        """Get or create browser session"""
        
        if session_id and session_id in self.session_pool:
            session = self.session_pool[session_id]
            if not session.is_expired():
                return session
        
        # Create new session if needed
        if len(self.session_pool) < self.max_sessions:
            session = await self.create_browser_session()
            self.session_pool[session.id] = session
            return session
        
        # Reuse oldest session
        oldest_session = min(self.session_pool.values(), 
                           key=lambda s: s.created_at)
        await oldest_session.reset()
        return oldest_session
    
    async def cleanup_expired_sessions(self):
        """Clean up expired browser sessions"""
        expired_sessions = [
            session_id for session_id, session in self.session_pool.items()
            if session.is_expired()
        ]
        
        for session_id in expired_sessions:
            await self.session_pool[session_id].close()
            del self.session_pool[session_id]
```

#### Navigation Optimization

```python
# Optimize Campus Coach navigation
class CampusCoachNavigator:
    def __init__(self, browser_session):
        self.session = browser_session
        self.cache = {}
    
    async def navigate_to_calendar(self):
        """Optimized navigation to training calendar"""
        
        # Check if already on calendar page
        current_url = await self.session.get_current_url()
        if 'calendar' in current_url:
            return True
        
        # Use cached navigation path if available
        if 'calendar_path' in self.cache:
            path = self.cache['calendar_path']
            await self.session.navigate(path)
        else:
            # Discover and cache navigation path
            path = await self.discover_calendar_path()
            self.cache['calendar_path'] = path
            await self.session.navigate(path)
        
        return await self.verify_calendar_page()
    
    async def extract_sessions_optimized(self, week_number: str):
        """Optimized session extraction"""
        
        # Use CSS selectors for faster element location
        session_elements = await self.session.find_elements(
            'div[data-week="{}"] .training-session'.format(week_number)
        )
        
        # Batch extract session data
        sessions = []
        for element in session_elements:
            session_data = await self.extract_session_data_batch(element)
            sessions.append(session_data)
        
        return sessions
```

## DynamoDB Performance

### Table Configuration Optimization

#### Billing Mode Optimization

```bash
# Analyze table usage patterns
aws dynamodb describe-table --table-name strava-ai-boost-activities --profile your-aws-profile --query 'Table.{ItemCount:ItemCount,TableSizeBytes:TableSizeBytes,BillingMode:BillingModeSummary.BillingMode}'

# For predictable workloads, use provisioned capacity
aws dynamodb modify-table \
  --table-name strava-ai-boost-activities \
  --billing-mode PROVISIONED \
  --provisioned-throughput ReadCapacityUnits=10,WriteCapacityUnits=5 \
  --profile your-aws-profile

# For variable workloads, use on-demand
aws dynamodb modify-table \
  --table-name strava-ai-boost-activities \
  --billing-mode PAY_PER_REQUEST \
  --profile your-aws-profile
```

#### Global Secondary Index Optimization

```bash
# Create optimized GSI for common query patterns
aws dynamodb update-table \
  --table-name strava-ai-boost-activities \
  --attribute-definitions \
    AttributeName=processing_status,AttributeType=S \
    AttributeName=created_at,AttributeType=S \
  --global-secondary-index-updates \
    'Create={
      IndexName=ProcessingStatusIndex,
      KeySchema=[
        {AttributeName=processing_status,KeyType=HASH},
        {AttributeName=created_at,KeyType=RANGE}
      ],
      Projection={ProjectionType=INCLUDE,NonKeyAttributes=[activity_id,updated_at]},
      ProvisionedThroughput={ReadCapacityUnits=5,WriteCapacityUnits=2}
    }' \
  --profile your-aws-profile
```

### Query Optimization

#### Efficient Query Patterns

```python
# Optimize DynamoDB queries
import boto3
from boto3.dynamodb.conditions import Key, Attr

class OptimizedDynamoDBClient:
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table('strava-ai-boost-activities')
    
    def get_recent_activities(self, limit: int = 10):
        """Optimized query for recent activities"""
        
        response = self.table.query(
            IndexName='ProcessingStatusIndex',
            KeyConditionExpression=Key('processing_status').eq('completed'),
            ScanIndexForward=False,  # Descending order
            Limit=limit,
            ProjectionExpression='activity_id, created_at, enhanced_description'
        )
        
        return response['Items']
    
    def batch_get_activities(self, activity_ids: list):
        """Batch get multiple activities efficiently"""
        
        # Use batch_get_item for multiple items
        response = self.dynamodb.batch_get_item(
            RequestItems={
                'strava-ai-boost-activities': {
                    'Keys': [{'activity_id': aid} for aid in activity_ids],
                    'ProjectionExpression': 'activity_id, processing_status, enhanced_description'
                }
            }
        )
        
        return response['Responses']['strava-ai-boost-activities']
    
    def update_activity_optimized(self, activity_id: str, updates: dict):
        """Optimized update with condition checks"""
        
        update_expression = "SET "
        expression_values = {}
        
        for key, value in updates.items():
            update_expression += f"{key} = :{key}, "
            expression_values[f":{key}"] = value
        
        update_expression = update_expression.rstrip(', ')
        
        self.table.update_item(
            Key={'activity_id': activity_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ConditionExpression=Attr('activity_id').exists(),
            ReturnValues='UPDATED_NEW'
        )
```

### Connection Pooling

```python
# Optimize DynamoDB connection pooling
from botocore.config import Config

# Configure connection pooling for DynamoDB
config = Config(
    max_pool_connections=50,
    retries={
        'max_attempts': 3,
        'mode': 'adaptive'
    }
)

dynamodb = boto3.resource('dynamodb', config=config)
```

## Step Functions Optimization

### Infinite Loop Prevention (Critical Optimization)

#### Problem Statement
Strava webhooks can create infinite execution loops when our system updates activities:
```
Activity Update → Webhook 'update' → Step Functions → Activity Update → Webhook 'update' → ∞
```

This can result in:
- Hundreds of unnecessary Step Functions executions
- 90%+ increase in AWS costs
- Strava API rate limit exhaustion
- System instability

#### Solution Implementation
**Pre-execution Status Check** in `activity_processor.py`:

```python
def should_skip_processing(activity_id: str, message_body: Dict[str, Any]) -> bool:
    """Prevent infinite webhook loops by checking activity status"""
    
    # Get activity from DynamoDB
    activity = get_activity_from_db(activity_id)
    
    if not activity:
        return False  # New activity, process it
    
    status = activity.get('processing_status')
    webhook_type = message_body.get('webhook_data', {}).get('aspect_type')
    
    # Skip if already completed or processing
    if status in ['completed', 'processing']:
        logger.info(f"Skipping activity {activity_id} - status: {status}")
        return True
    
    # For update webhooks, be more restrictive
    if webhook_type == 'update':
        if status in ['completed', 'processing']:
            return True
        
        # 1-hour cooldown for failed activities
        if status == 'failed' and failed_within_last_hour(activity):
            logger.info(f"Skipping activity {activity_id} - recent failure cooldown")
            return True
    
    return False  # Allow processing
```

#### Performance Impact
- ✅ **Execution Reduction**: 90%+ fewer unnecessary executions
- ✅ **Cost Savings**: Eliminates redundant processing costs
- ✅ **Rate Limit Protection**: Prevents API exhaustion
- ✅ **System Stability**: Maintains consistent performance

#### Monitoring
```bash
# Monitor skipped activities (should see update webhooks being skipped)
aws logs filter-log-events \
  --log-group-name "/aws/lambda/StravaAIBoost-ActivityProcessor" \
  --filter-pattern "Skipping activity" \
  --profile your-aws-profile

# Check Step Functions execution count (should be ~1 per activity)
aws stepfunctions list-executions \
  --state-machine-arn YOUR_STATE_MACHINE_ARN \
  --status-filter RUNNING \
  --profile your-aws-profile
```

### Workflow Optimization

#### Parallel Processing

```json
{
  "Comment": "Optimized Strava AI Boost workflow",
  "StartAt": "ProcessActivity",
  "States": {
    "ProcessActivity": {
      "Type": "Parallel",
      "Branches": [
        {
          "StartAt": "FetchActivityData",
          "States": {
            "FetchActivityData": {
              "Type": "Task",
              "Resource": "arn:aws:lambda:eu-west-1:ACCOUNT:function:StravaAIBoost-ActivityFetcher",
              "TimeoutSeconds": 30,
              "Retry": [
                {
                  "ErrorEquals": ["States.TaskFailed"],
                  "IntervalSeconds": 2,
                  "MaxAttempts": 3,
                  "BackoffRate": 2.0
                }
              ],
              "End": true
            }
          }
        },
        {
          "StartAt": "CheckModuleConfiguration",
          "States": {
            "CheckModuleConfiguration": {
              "Type": "Task",
              "Resource": "arn:aws:lambda:eu-west-1:ACCOUNT:function:StravaAIBoost-ConfigurationAPI",
              "TimeoutSeconds": 10,
              "End": true
            }
          }
        }
      ],
      "Next": "GenerateContent"
    },
    "GenerateContent": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:eu-west-1:ACCOUNT:function:StravaAIBoost-ContentGenerator",
      "TimeoutSeconds": 180,
      "Retry": [
        {
          "ErrorEquals": ["States.TaskFailed"],
          "IntervalSeconds": 5,
          "MaxAttempts": 2,
          "BackoffRate": 2.0
        }
      ],
      "Next": "UpdateActivity"
    }
  }
}
```

#### Error Handling Optimization

```json
{
  "Catch": [
    {
      "ErrorEquals": ["States.ALL"],
      "Next": "HandleError",
      "ResultPath": "$.error"
    }
  ],
  "HandleError": {
    "Type": "Task",
    "Resource": "arn:aws:lambda:eu-west-1:ACCOUNT:function:StravaAIBoost-ErrorHandler",
    "Parameters": {
      "error.$": "$.error",
      "input.$": "$",
      "retry_count": 0
    },
    "Next": "DecideRetry"
  },
  "DecideRetry": {
    "Type": "Choice",
    "Choices": [
      {
        "Variable": "$.retry_count",
        "NumericLessThan": 3,
        "Next": "RetryProcessing"
      }
    ],
    "Default": "SendToDeadLetterQueue"
  }
}
```

## Cost Optimization

### Resource Right-Sizing

#### Lambda Function Sizing

```bash
# Analyze Lambda function performance vs cost
aws logs filter-log-events \
  --log-group-name /aws/lambda/StravaAIBoost-ContentGenerator \
  --filter-pattern "REPORT" \
  --start-time $(date -d '7 days ago' +%s)000 \
  --profile your-aws-profile \
  --query 'events[*].message' --output text | \
  grep -E "Duration|Memory Size|Max Memory Used" | \
  awk '{print $3, $6, $10}' | \
  sort -n
```

#### DynamoDB Cost Optimization

```python
# Monitor DynamoDB costs and optimize
def analyze_dynamodb_costs():
    """Analyze DynamoDB usage patterns for cost optimization"""
    
    # Get table metrics
    cloudwatch = boto3.client('cloudwatch')
    
    # Check read/write patterns
    read_metrics = cloudwatch.get_metric_statistics(
        Namespace='AWS/DynamoDB',
        MetricName='ConsumedReadCapacityUnits',
        Dimensions=[{'Name': 'TableName', 'Value': 'strava-ai-boost-activities'}],
        StartTime=datetime.utcnow() - timedelta(days=7),
        EndTime=datetime.utcnow(),
        Period=3600,
        Statistics=['Sum', 'Average']
    )
    
    # Analyze patterns and recommend billing mode
    avg_reads = sum(point['Average'] for point in read_metrics['Datapoints']) / len(read_metrics['Datapoints'])
    
    if avg_reads < 5:  # Low consistent usage
        return "Switch to on-demand billing"
    elif avg_reads > 20:  # High consistent usage
        return "Use provisioned capacity with auto-scaling"
    else:
        return "Current configuration optimal"
```

### Caching Strategy

#### Multi-Level Caching

```python
# Implement multi-level caching for cost optimization
class MultiLevelCache:
    def __init__(self):
        self.memory_cache = {}  # In-memory cache
        self.redis_cache = None  # Optional Redis cache
        self.s3_cache = boto3.client('s3')  # S3 for long-term cache
    
    async def get(self, key: str, cache_level: str = 'all'):
        """Get from appropriate cache level"""
        
        # Level 1: Memory cache (fastest, most expensive)
        if cache_level in ['all', 'memory'] and key in self.memory_cache:
            return self.memory_cache[key]
        
        # Level 2: Redis cache (fast, moderate cost)
        if cache_level in ['all', 'redis'] and self.redis_cache:
            value = await self.redis_cache.get(key)
            if value:
                self.memory_cache[key] = value  # Promote to memory
                return value
        
        # Level 3: S3 cache (slow, cheapest)
        if cache_level in ['all', 's3']:
            try:
                response = self.s3_cache.get_object(
                    Bucket='strava-ai-boost-cache',
                    Key=key
                )
                value = response['Body'].read()
                self.memory_cache[key] = value  # Promote to memory
                return value
            except:
                pass
        
        return None
    
    async def set(self, key: str, value: any, ttl: int = 3600):
        """Set in all cache levels"""
        
        # Store in memory
        self.memory_cache[key] = value
        
        # Store in Redis with TTL
        if self.redis_cache:
            await self.redis_cache.setex(key, ttl, value)
        
        # Store in S3 for long-term caching
        self.s3_cache.put_object(
            Bucket='strava-ai-boost-cache',
            Key=key,
            Body=value,
            Metadata={'ttl': str(int(time.time()) + ttl)}
        )
```

## Monitoring and Metrics

### GenAI Observability Dashboard (v1.16.0+)

**Automatic Setup**: Configured via CDK SecurityStack

Access comprehensive agent monitoring:
- 📊 **Agent Metrics**: Invocations, latency, errors, token usage
- 🔍 **Trace Visualization**: Detailed execution timeline
- 🔗 **Session Tracking**: Group related invocations
- 🛡️ **Guardrail Monitoring**: Security interventions

**Dashboard URL**: https://console.aws.amazon.com/cloudwatch/home?region=eu-west-1#gen-ai-observability/agent-core/agents

**Key Metrics**:
- Content Gen Latency: Target <5s
- Campus Coach Latency: Target <180s
- Token Usage: ~1,850 avg per activity
- Error Rate: Target <2%
- Guardrail Blocks: Target <1%

**Reference**: See Observability section in `docs/advanced/AGENTCORE.md`

### Custom CloudWatch Metrics

```python
# Publish custom performance metrics
import boto3

class PerformanceMetrics:
    def __init__(self):
        self.cloudwatch = boto3.client('cloudwatch')
    
    def publish_processing_time(self, function_name: str, duration: float):
        """Publish processing time metrics"""
        
        self.cloudwatch.put_metric_data(
            Namespace='StravaAIBoost/Performance',
            MetricData=[
                {
                    'MetricName': 'ProcessingDuration',
                    'Value': duration,
                    'Unit': 'Seconds',
                    'Dimensions': [
                        {
                            'Name': 'FunctionName',
                            'Value': function_name
                        }
                    ]
                }
            ]
        )
    
    def publish_success_rate(self, component: str, success_count: int, total_count: int):
        """Publish success rate metrics"""
        
        success_rate = (success_count / total_count) * 100 if total_count > 0 else 0
        
        self.cloudwatch.put_metric_data(
            Namespace='StravaAIBoost/Performance',
            MetricData=[
                {
                    'MetricName': 'SuccessRate',
                    'Value': success_rate,
                    'Unit': 'Percent',
                    'Dimensions': [
                        {
                            'Name': 'Component',
                            'Value': component
                        }
                    ]
                }
            ]
        )
```

### Performance Dashboards

```bash
# Create performance monitoring dashboard
aws cloudwatch put-dashboard \
  --dashboard-name "StravaAIBoost-Performance" \
  --dashboard-body '{
    "widgets": [
      {
        "type": "metric",
        "properties": {
          "metrics": [
            ["StravaAIBoost/Performance", "ProcessingDuration", "FunctionName", "ContentGenerator"],
            ["AWS/Lambda", "Duration", "FunctionName", "StravaAIBoost-ContentGenerator"]
          ],
          "period": 300,
          "stat": "Average",
          "region": "eu-west-1",
          "title": "Content Generation Performance"
        }
      },
      {
        "type": "metric",
        "properties": {
          "metrics": [
            ["StravaAIBoost/Performance", "SuccessRate", "Component", "CampusCoach"],
            ["StravaAIBoost/Performance", "SuccessRate", "Component", "ContentGeneration"]
          ],
          "period": 300,
          "stat": "Average",
          "region": "eu-west-1",
          "title": "Success Rates"
        }
      }
    ]
  }' \
  --profile your-aws-profile
```

### Automated Performance Optimization

```python
# Automated performance optimization based on metrics
class AutoOptimizer:
    def __init__(self):
        self.cloudwatch = boto3.client('cloudwatch')
        self.lambda_client = boto3.client('lambda')
    
    async def optimize_lambda_memory(self, function_name: str):
        """Automatically optimize Lambda memory based on usage"""
        
        # Get memory utilization metrics
        metrics = self.cloudwatch.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='Duration',
            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
            StartTime=datetime.utcnow() - timedelta(days=7),
            EndTime=datetime.utcnow(),
            Period=3600,
            Statistics=['Average', 'Maximum']
        )
        
        avg_duration = sum(point['Average'] for point in metrics['Datapoints']) / len(metrics['Datapoints'])
        max_duration = max(point['Maximum'] for point in metrics['Datapoints'])
        
        # Get current configuration
        config = self.lambda_client.get_function_configuration(FunctionName=function_name)
        current_memory = config['MemorySize']
        timeout = config['Timeout']
        
        # Optimize memory if duration is consistently high
        if avg_duration > timeout * 0.8:  # Using >80% of timeout
            new_memory = min(current_memory * 1.5, 3008)  # Increase by 50%
            
            self.lambda_client.update_function_configuration(
                FunctionName=function_name,
                MemorySize=int(new_memory)
            )
            
            return f"Increased memory from {current_memory}MB to {new_memory}MB"
        
        elif avg_duration < timeout * 0.3:  # Using <30% of timeout
            new_memory = max(current_memory * 0.8, 128)  # Decrease by 20%
            
            self.lambda_client.update_function_configuration(
                FunctionName=function_name,
                MemorySize=int(new_memory)
            )
            
            return f"Decreased memory from {current_memory}MB to {new_memory}MB"
        
        return "Memory configuration optimal"
```

---