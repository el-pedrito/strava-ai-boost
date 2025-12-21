# Strava AI Boost - Design Document

## Overview

**Strava AI Boost** is a simplified, modular serverless application that automatically enhances Strava activity titles and descriptions using Amazon Bedrock AI. The system is designed as a radical simplification of the existing Strava AI Coach project, focusing on core functionality while maintaining modularity for future integrations.

The system uses a local web interface approach to avoid complexity of user management, authentication systems, and secure web hosting. This prioritizes simplicity and rapid deployment for individual users who can install the system in their own AWS environment.

### Key Design Principles

1. **Simplicity First**: Local web interface eliminates need for Cognito, CloudFront/S3 hosting
2. **Modular Architecture**: Extensible module system starting with Campus Coach integration
3. **Serverless-Native**: Full AWS serverless stack for cost efficiency and scalability
4. **Data Privacy**: User controls their own AWS environment and data
5. **Reliability**: Built-in retry logic, error handling, and monitoring

## Architecture

### High-Level Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Local Web     │    │   AWS Serverless │    │     Strava      │
│   Interface     │◄──►│    Backend       │◄──►│      API        │
│ (Cloudscape UI) │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │   Third-Party    │
                       │   Integrations   │
                       │ (Campus Coach,   │
                       │   Enduraw)       │
                       └──────────────────┘
```

### Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        AWS Cloud Environment                     │
├─────────────────────────────────────────────────────────────────┤
│  API Gateway ◄─── Local Web Interface (AWS Cloudscape)          │
│      │                                                           │
│      ▼                                                           │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    │
│  │   Strava    │    │    Step      │    │    Amazon       │    │
│  │  Webhook    │───►│  Functions   │───►│   Bedrock       │    │
│  │  Handler    │    │  Workflow    │    │   (Claude)      │    │
│  └─────────────┘    └──────────────┘    └─────────────────┘    │
│      │                      │                                   │
│      ▼                      ▼                                   │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    │
│  │     SQS     │    │   DynamoDB   │    │  AgentCore      │    │
│  │   Queue     │    │   Tables     │    │  Browser Tool   │    │
│  └─────────────┘    └──────────────┘    └─────────────────┘    │
│                                                  │               │
│                                                  ▼               │
│                                          ┌─────────────────┐    │
│                                          │ Campus Coach    │    │
│                                          │   Scraping      │    │
│                                          └─────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. Local Web Interface

**Backend**: Python Flask/FastAPI application
**Frontend**: AWS Cloudscape Design System components
**Purpose**: Configuration and monitoring interface

**Key Components**:
- **Configuration Panel**: Strava OAuth setup, module management
- **Dashboard**: Activity processing statistics, engagement metrics
- **Status Monitor**: Real-time processing status, error reporting
- **Module Manager**: Enable/disable integrations (Campus Coach, Enduraw)

**API Interface**:
```python
from typing import List, Dict, Any
from pydantic import BaseModel

class ConfigurationAPI:
    """Python Flask/FastAPI endpoints for local interface"""
    
    # OAuth Management
    async def initiate_strava_auth(self) -> Dict[str, str]:
        """Return Strava OAuth authorization URL"""
        pass
    
    async def get_connection_status(self) -> Dict[str, Any]:
        """Get current Strava connection status"""
        pass
    
    # Module Management
    async def get_available_modules(self) -> List[Dict[str, Any]]:
        """Get list of available modules"""
        pass
    
    async def enable_module(self, module_id: str, config: Dict[str, Any]) -> Dict[str, str]:
        """Enable module with configuration"""
        pass
    
    async def disable_module(self, module_id: str) -> Dict[str, str]:
        """Disable module"""
        pass
    
    # Dashboard Data
    async def get_activity_stats(self) -> Dict[str, Any]:
        """Get activity processing statistics"""
        pass
    
    async def get_processing_status(self) -> List[Dict[str, Any]]:
        """Get current processing status"""
        pass
```

### 2. Strava Integration Layer

**Components**:
- **Webhook Handler**: Receives activity notifications from Strava
- **OAuth Manager**: Handles token storage and refresh in Secrets Manager
- **API Client**: Manages Strava API calls with rate limiting
- **Rate Limiter**: Tracks and enforces 100/15min, 1000/day limits

**Rate Limiting Strategy**:
```python
class StravaRateLimiter:
    def __init__(self):
        self.short_term_limit = 100  # per 15 minutes
        self.daily_limit = 1000      # per day
        
    async def check_and_wait(self) -> bool:
        # Check DynamoDB for current usage
        # Implement exponential backoff if limits approached
        # Queue requests if limits exceeded
```

### 3. Activity Processing Pipeline

**Step Functions Workflow**:
```
Start → Fetch Activity → Store Backup → Analyze Data → Generate Content → Update Strava → End
  │         │              │             │              │               │
  ▼         ▼              ▼             ▼              ▼               ▼
Error    Retry         DynamoDB      Bedrock AI    Content Gen     Success
Handler   Logic         Backup        Analysis       Lambda        Notification
```

**Processing States**:
1. **TransformInput**: Validate webhook data, handle null descriptions
2. **FetchActivityData**: Get complete activity data from Strava API
3. **StoreBackup**: Save original description to DynamoDB
4. **AnalyzeActivity**: Process activity data and streams for insights
5. **GenerateContent**: Use Bedrock AI to create enhanced content
6. **UpdateActivity**: Post enhanced content back to Strava
7. **NotifyCompletion**: Update status in local interface

### 4. AI Content Generation with AgentCore Memory

**Strands Agent with AgentCore Memory**:
- **Agent Framework**: Strands Agent for orchestration
- **Memory System**: AgentCore Memory for persistent personalization
- **Model**: Claude Sonnet 4.5 for intelligent analysis and content generation
- **Analysis Pipeline**: 
  - Activity data processing (67+ Strava fields)
  - Streams analysis (velocity, heart rate, altitude, time)
  - Pattern detection (intervals, effort zones, workout classification)
  - Personal style learning (via AgentCore Memory)

**Content Generation Agent with Memory**:
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
                             user_id: str,
                             modules: List[Module]) -> EnhancedContent:
        # Retrieve user's personal style from memory
        personal_style = await self.memory.get_user_style(user_id)
        previous_expressions = await self.memory.get_used_expressions(user_id)
        
        # Analyze activity patterns using Bedrock
        patterns = await self.analyze_patterns(streams_data)
        
        # Apply active modules (Campus Coach matching, etc.)
        module_insights = await self.apply_modules(activity_data, modules)
        
        # Generate personalized content avoiding repetition
        content = await self.bedrock_generate(
            patterns, 
            module_insights, 
            personal_style,
            previous_expressions
        )
        
        # Store new expressions and style updates in memory
        await self.memory.store_generated_content(user_id, content)
        await self.memory.update_user_style(user_id, content.style_elements)
        
        return content
```

**AgentCore Memory Integration**:
- **Personal Style Storage**: Learn and remember user's preferred tone and terminology
- **Expression Tracking**: Avoid repetitive phrases and vary content structure
- **Performance Memory**: Remember user's typical performance patterns for context
- **Module Preferences**: Store which modules user engages with most

### 5. Module System

**Base Module Interface**:
```python
class BaseModule:
    def __init__(self, config: ModuleConfig):
        self.config = config
        self.enabled = False
    
    async def analyze_activity(self, activity: ActivityData) -> ModuleInsight:
        raise NotImplementedError
    
    async def configure(self, credentials: Dict) -> bool:
        raise NotImplementedError
```

**Campus Coach Module**:
- **AgentCore Browser Tool**: Automated web scraping using browser automation agent
- **Known Issue**: Cold start problem requiring retry logic (30% first-try success rate)
- **Strands Agent Integration**: Session matching agent using Bedrock for intelligent analysis
- **Session Matching**: AI-powered matching of activities to planned sessions
- **Confidence Scoring**: Intelligent matching with threshold-based inclusion
- **Compliance Analysis**: Compare actual vs planned performance using streams data
- **Retry Strategy**: Exponential backoff for AgentCore Browser Tool invocations

**Enduraw Module**:
- **Wait Strategy**: 2-7 minute delay for Enduraw processing
- **Enhanced Metrics**: Pace without wind, weather impact, elevation cost
- **Integration Toggle**: Enable/disable via local interface

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
    # ... 67+ additional Strava fields as optional attributes

class StreamsData(BaseModel):
    """Strava streams data model"""
    velocity_smooth: List[float]
    heartrate: List[int]
    time: List[int]
    distance: List[float]
    altitude: List[float]

class ProcessingStatus(BaseModel):
    """Activity processing status"""
    activity_id: str
    status: Literal['queued', 'processing', 'completed', 'failed']
    step: str
    timestamp: datetime
    error_message: Optional[str] = None
    modules_active: List[str]

class ModuleConfig(BaseModel):
    """Module configuration"""
    module_id: str
    enabled: bool
    credentials: Optional[Dict[str, str]] = None
    settings: Dict[str, Any]

class StravaRateLimit(BaseModel):
    """Rate limit tracking"""
    limit_type: Literal['short_term', 'daily']
    current_usage: int
    reset_time: datetime
    last_request: datetime
```

### DynamoDB Tables

**1. strava-activities**
```
Partition Key: activity_id (string)
Attributes:
- original_description (string)
- enhanced_description (string)
- processing_status (string)
- modules_used (string[])
- created_at (timestamp)
- updated_at (timestamp)
```

**2. user-configuration**
```
Partition Key: user_id (string)
Attributes:
- strava_connected (boolean)
- modules_config (map)
- rate_limit_status (map)
- last_updated (timestamp)
```

**3. strava-rate-limits**
```
Partition Key: limit_type (string) # 'short_term' | 'daily'
Attributes:
- current_usage (number)
- reset_time (timestamp)
- last_request (timestamp)
```

**4. campus-coaching-sessions**
```
Partition Key: session_date (string)
Sort Key: session_id (string)
Attributes:
- session_data (map)
- week_number (string)
- extracted_at (timestamp)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Based on the prework analysis, the following correctness properties have been identified from the acceptance criteria:

### Property 1: OAuth Token Security
*For any* OAuth authorization flow, when tokens are received, they should be securely stored in AWS Secrets Manager with proper encryption
**Validates: Requirements 1.3, 7.3**

### Property 2: Webhook Processing Reliability
*For any* valid webhook notification received, the system should queue the activity processing request in SQS for reliable processing
**Validates: Requirements 2.2**

### Property 3: Activity Data Backup
*For any* activity data retrieved from Strava API, the original description should be stored in DynamoDB before any modifications
**Validates: Requirements 2.5**

### Property 4: Comprehensive Data Analysis
*For any* activity analysis, all available Strava activity data (67+ fields) should be utilized for comprehensive analysis
**Validates: Requirements 2.7**

### Property 5: Streams Data Precision
*For any* detailed analysis requirement, complete Strava streams data (velocity_smooth, heartrate, time, distance, altitude) should be fetched with second-by-second granularity
**Validates: Requirements 2.8, 3.1**

### Property 6: AI Pattern Detection
*For any* streams data analyzed, Amazon Bedrock AI should intelligently detect effort patterns, intervals, heart rate zones, and workout classification
**Validates: Requirements 2.9, 3.2**

### Property 7: Content Personalization
*For any* content generation, the system should analyze previous activities to understand personal style and avoid repetitive expressions
**Validates: Requirements 2.10**

### Property 8: Activity Update Completion
*For any* generated enhanced content, the Strava activity should be successfully updated with the new content
**Validates: Requirements 2.12**

### Property 9: Error Recovery
*For any* processing failure at any step, SQS retry logic with exponential backoff and dead letter queue should be applied
**Validates: Requirements 2.13**

### Property 10: Campus Coach Session Matching
*For any* Campus Coach module activity processing, the system should intelligently match detected activity patterns against planned sessions with confidence scoring
**Validates: Requirements 3.3, 3.4**

### Property 11: Module Configuration Persistence
*For any* module setting change, the configuration should be saved to DynamoDB for persistence
**Validates: Requirements 4.4**

### Property 12: Secure Credential Storage
*For any* provided credentials (Campus Coach, etc.), they should be securely stored in AWS Secrets Manager
**Validates: Requirements 5.2**

### Property 13: Rate Limit Compliance
*For any* Strava API call, the system should track and respect both the 100 requests per 15 minutes and 1000 requests per day limits
**Validates: Requirements 10.1, 10.2**

### Property 14: Rate Limit Persistence
*For any* rate limit status change, tracking data should be stored in DynamoDB for persistence across Lambda invocations
**Validates: Requirements 10.5**

### Property 15: Data Encryption
*For any* user data stored, encryption at rest should be applied using AWS managed encryption
**Validates: Requirements 7.1**

### Property 16: Secure Communication
*For any* data transmission, HTTPS should be used for all communications
**Validates: Requirements 7.2**

### Property 17: Enduraw Wait Logic
*For any* activity processing when Enduraw integration is active, the system should wait 2-7 minutes for Enduraw analysis
**Validates: Requirements 9.3**

### Property 18: Enhanced Metrics Integration
*For any* retrieved Enduraw data, enhanced metrics should be included in the content generation process
**Validates: Requirements 9.5**

### Property 19: Real-time Status Display
*For any* activity being processed, processing status should be displayed in real-time in the local web interface
**Validates: Requirements 11.4, 12.1**

### Property 20: Error Message Clarity
*For any* error occurrence, clear error messages with suggested actions should be displayed
**Validates: Requirements 12.3**

### Property 21: Enhancement Pause Control
*For any* webhook received when the system is paused, the webhook should be acknowledged but no processing should occur, and the pause state should persist across system restarts
**Validates: Requirements 13.3, 13.7**

## Error Handling

### Error Categories and Strategies

**1. External API Failures**
- **Strava API**: Rate limiting, temporary unavailability, invalid tokens
- **Strategy**: Exponential backoff, token refresh, request queuing
- **Implementation**: SQS with DLQ, CloudWatch alarms

**2. AWS Service Failures**
- **Bedrock**: Model unavailability, throttling
- **DynamoDB**: Throttling, capacity issues
- **Strategy**: Retry with jitter, circuit breaker pattern
- **Implementation**: AWS SDK built-in retries + custom logic

**3. Module-Specific Failures**
- **Campus Coach**: AgentCore Browser Tool cold start issues, scraping failures, authentication issues
- **AgentCore Cold Start**: Known issue with ~30% first-try success rate
- **Enduraw**: Timeout waiting for analysis
- **Strategy**: Retry logic with exponential backoff, graceful degradation, fallback to basic content
- **Implementation**: Multi-retry Campus Coach invocation, try-catch with fallback content generation

**4. Data Processing Failures**
- **Invalid activity data**: Missing fields, corrupted streams
- **AI analysis failures**: Bedrock errors, timeout
- **Strategy**: Validation, sanitization, default values
- **Implementation**: Schema validation, error boundaries

### Error Recovery Mechanisms

```python
class ErrorHandler:
    async def handle_processing_error(self, error: Exception, context: ProcessingContext):
        if isinstance(error, StravaRateLimitError):
            await self.queue_for_retry(context, delay=error.retry_after)
        elif isinstance(error, BedrockThrottleError):
            await self.exponential_backoff_retry(context)
        elif isinstance(error, ModuleError):
            await self.fallback_to_basic_generation(context)
        else:
            await self.send_to_dlq(context, error)
```

## Testing Strategy

### Dual Testing Approach

The system will use both unit testing and property-based testing to ensure comprehensive coverage:

**Unit Tests**: Verify specific examples, edge cases, and error conditions
**Property Tests**: Verify universal properties that should hold across all inputs

Together they provide comprehensive coverage: unit tests catch concrete bugs, property tests verify general correctness.

### Property-Based Testing Framework

**Framework**: Hypothesis (Python) for property-based testing
**Configuration**: Minimum 100 iterations per property test
**Tagging**: Each property-based test tagged with format: `**Feature: strava-ai-boost, Property {number}: {property_text}**`

### Unit Testing Strategy

Unit tests will focus on:
- **API Integration Points**: Strava OAuth, webhook handling, Bedrock calls
- **Data Transformation**: Activity data processing, streams analysis
- **Error Scenarios**: Rate limiting, authentication failures, malformed data
- **Module Integration**: Campus Coach matching, Enduraw integration

### Integration Testing

- **End-to-End Workflows**: Complete activity processing pipeline
- **AWS Service Integration**: DynamoDB operations, SQS messaging, Step Functions
- **External API Mocking**: Strava API responses, Bedrock model responses

### Testing Infrastructure

```python
# Property-based test example
@given(activity_data=activity_strategy(), streams_data=streams_strategy())
def test_comprehensive_data_analysis_property(activity_data, streams_data):
    """
    **Feature: strava-ai-boost, Property 4: Comprehensive Data Analysis**
    For any activity analysis, all available Strava activity data should be utilized
    """
    analyzer = ActivityAnalyzer()
    result = analyzer.analyze(activity_data, streams_data)
    
    # Verify all available fields were considered
    assert len(result.analyzed_fields) >= 67
    assert all(field in result.analyzed_fields for field in activity_data.keys())
```

## Security Considerations

### Data Protection

**Encryption at Rest**:
- DynamoDB tables: AWS managed encryption (KMS)
- Secrets Manager: Automatic encryption with rotation
- S3 buckets (if used): Server-side encryption (SSE-S3)

**Encryption in Transit**:
- All API communications: TLS 1.2+
- Internal AWS service calls: AWS service-to-service encryption
- Local web interface: HTTPS with self-signed certificates

### Access Control

**IAM Policies**:
- Principle of least privilege
- Service-specific roles with minimal permissions
- Cross-service access only where required

**API Security**:
- Strava OAuth 2.0 with PKCE
- Rate limiting at API Gateway level
- Request validation and sanitization

### Credential Management

**AWS Secrets Manager**:
- Automatic rotation for supported services
- Encryption with customer-managed KMS keys
- Access logging and monitoring

**Local Interface Security**:
- Local-only access (127.0.0.1)
- Session-based authentication
- CSRF protection

## Performance Optimization

### Latency Targets

- **Webhook Processing**: < 5 seconds to queue
- **Content Generation**: < 30 seconds end-to-end
- **Dashboard Loading**: < 2 seconds
- **Configuration Changes**: < 1 second

### Scalability Patterns

**Serverless Auto-scaling**:
- Lambda: Automatic concurrency scaling
- DynamoDB: On-demand billing mode
- SQS: Unlimited throughput

**Caching Strategy**:
- Activity data: 24-hour cache in DynamoDB
- Campus Coach sessions: Weekly refresh
- Rate limit status: In-memory + DynamoDB persistence

### Cost Optimization

**Estimated Costs per Activity**:
- Lambda executions: $0.001
- DynamoDB operations: $0.001
- Step Functions: $0.003
- Bedrock API calls: $0.005
- SQS messages: $0.0001
- **Total**: ~$0.02 per activity

**Cost Control Measures**:
- Intelligent caching to reduce API calls
- Batch processing for Campus Coach extraction
- Reserved capacity for predictable workloads

## Deployment Architecture

### Infrastructure as Code

**Technology Stack**:
- **Language**: Python 3.12
- **Infrastructure**: AWS CDK (Python) + AgentCore CLI scripts
- **AI Framework**: Strands Agents for agent orchestration
- **Memory System**: AgentCore Memory for persistent personalization
- **Browser Automation**: AgentCore Browser Tool for Campus Coach scraping
- **AgentCore Deployment**: Shell scripts using AgentCore CLI (not CDK L2 due to experimental status)
- **AWS Services**: Lambda, DynamoDB, Step Functions, Bedrock, SQS, Secrets Manager

**AWS CDK Stack Organization**:
```
strava-ai-boost/
├── app.py                              # CDK app entry point
├── stacks/
│   ├── core_infrastructure_stack.py    # DynamoDB, IAM roles
│   ├── api_gateway_stack.py           # Local interface API
│   ├── webhook_processing_stack.py    # Strava webhooks, SQS
│   ├── content_generation_stack.py    # Step Functions, Bedrock
│   └── monitoring_stack.py            # CloudWatch, alarms
├── scripts/
│   ├── deploy_agentcore.sh            # AgentCore CLI deployment
│   ├── setup_memory.sh                # AgentCore Memory configuration
│   └── deploy_campus_coach_agent.sh   # Campus Coach agent deployment
├── lambda_functions/
│   ├── webhook_handler.py             # Strava webhook processing
│   ├── activity_processor.py          # Activity data processing
│   ├── content_generator.py           # Bedrock content generation
│   └── campus_coach_invoker.py        # AgentCore invocation
├── src/
│   ├── agents/
│   │   ├── content_generation_agent.py # Strands Agent with AgentCore Memory
│   │   ├── campus_coach_agent.py       # AgentCore Browser Tool agent
│   │   └── session_matching_agent.py   # Strands Agent for matching
│   ├── modules/
│   │   ├── base_module.py             # Base module interface
│   │   ├── campus_coach_module.py     # Campus Coach integration
│   │   └── enduraw_module.py          # Enduraw integration
│   └── utils/
│       ├── strava_client.py           # Strava API client
│       ├── rate_limiter.py            # Rate limiting logic
│       └── data_models.py             # Pydantic models
└── local_interface/
    ├── app.py                         # Flask/FastAPI application
    └── static/                        # Cloudscape UI components
```

### Environment Configuration

**Development Environment**:
- Single AWS account deployment
- Reduced timeouts for faster iteration
- Enhanced logging and debugging

**Production Environment**:
- Multi-AZ deployment for reliability
- Production timeouts and retry logic
- Minimal logging for cost optimization

### Monitoring and Observability

**CloudWatch Metrics**:
- Activity processing success rate
- API call latency and error rates
- Rate limit utilization
- Cost per activity

**Alarms and Notifications**:
- Processing failure rate > 5%
- Rate limit utilization > 80%
- Daily cost exceeds threshold
- Campus Coach extraction failures

**Distributed Tracing**:
- X-Ray integration for Step Functions
- Request correlation across services
- Performance bottleneck identification

## Future Extensibility

### Module System Design

The modular architecture allows for easy addition of new integrations:

**Planned Modules**:
- **Runna Integration**: Training plan matching similar to Campus Coach
- **TrainingPeaks**: Structured workout analysis
- **Garmin Connect**: Enhanced device data integration
- **Weather APIs**: Environmental context enhancement

**Module Interface**:
```python
class BaseModule:
    def __init__(self, config: ModuleConfig):
        self.config = config
    
    async def analyze_activity(self, activity: ActivityData) -> ModuleInsight:
        """Analyze activity and return insights"""
        pass
    
    async def enhance_content(self, base_content: str, insights: ModuleInsight) -> str:
        """Enhance content with module-specific information"""
        pass
```

### API Evolution

**Versioning Strategy**:
- API Gateway versioning for backward compatibility
- Schema evolution for DynamoDB tables
- Feature flags for gradual rollouts

**Extension Points**:
- Custom content templates
- User-defined enhancement rules
- Third-party webhook integrations
- Multi-language support

This design provides a solid foundation for the Strava AI Boost system while maintaining the simplicity and modularity principles outlined in the requirements. The architecture leverages proven patterns from the existing strava-ai-coach project while simplifying deployment and user management through the local web interface approach.

### AgentCore Integration Strategy

**Deployment Approach**:
- **CLI-Based Deployment**: Use AgentCore CLI for stable deployment (avoiding experimental CDK L2)
- **Shell Scripts**: Automated deployment scripts for agents and memory configuration
- **CDK Integration**: Lambda functions invoke AgentCore agents via AWS SDK calls
- **Agent Management**: Deploy and manage agents through shell scripts using AgentCore CLI
- **Memory Configuration**: Set up AgentCore Memory through CLI commands

**AgentCore CLI Deployment Scripts**:
```bash
# scripts/deploy_agentcore.sh
#!/bin/bash
set -e

echo "🚀 Deploying AgentCore infrastructure..."

# Configure AgentCore
agentcore configure --region eu-west-1 --profile your-aws-profile

# Deploy Memory service
agentcore memory create --name strava-ai-boost-memory \
  --description "Personal style and expression memory for Strava AI Boost"

# Deploy Content Generation Agent with Memory
agentcore agent deploy \
  --name content-generation-agent \
  --runtime python \
  --memory strava-ai-boost-memory \
  --file src/agents/content_generation_agent.py

# Deploy Campus Coach Browser Agent
agentcore agent deploy \
  --name campus-coach-scraper \
  --runtime browser \
  --file src/agents/campus_coach_agent.py

echo "✅ AgentCore deployment complete"
```

**Lambda Integration with AgentCore**:
```python
import boto3
from agentcore_client import AgentCoreClient

class AgentCoreInvoker:
    def __init__(self):
        self.agentcore = AgentCoreClient(region='eu-west-1')
    
    async def invoke_content_agent(self, activity_data: dict, user_id: str) -> dict:
        """Invoke content generation agent with memory"""
        response = await self.agentcore.invoke_agent(
            agent_name='content-generation-agent',
            input_data={
                'activity_data': activity_data,
                'user_id': user_id,
                'memory_context': True
            }
        )
        return response
    
    async def invoke_campus_coach_agent(self, credentials: dict) -> dict:
        """Invoke Campus Coach scraping agent"""
        response = await self.agentcore.invoke_agent(
            agent_name='campus-coach-scraper',
            input_data={
                'credentials': credentials,
                'action': 'extract_sessions'
            }
        )
        return response
```