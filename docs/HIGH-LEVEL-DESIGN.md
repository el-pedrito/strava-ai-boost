# Strava AI Boost - High-Level Design

**Version:** v1.3.0 - AgentCore Integration Complete  
**Last Updated:** 2025-12-23

This document provides a comprehensive overview of the Strava AI Boost system architecture, design decisions, and visual diagrams for understanding the complete system.

## System Overview

Strava AI Boost is a simplified, modular serverless application that automatically enhances Strava activity titles and descriptions using Amazon Bedrock AI. The system prioritizes simplicity through a local web interface approach while maintaining enterprise-grade reliability and security.

### Design Principles

1. **Simplicity First**: Local web interface eliminates complex user management
2. **Modular Architecture**: Extensible module system for future integrations
3. **Serverless-Native**: Full AWS serverless stack for cost efficiency
4. **Data Privacy**: User controls their own AWS environment and data
5. **Reliability**: Built-in retry logic, error handling, and monitoring

## Architecture Diagrams

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        AWS Cloud Environment                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐    ┌──────────────────┐    ┌─────────────┐ │
│  │   Local Web     │    │   API Gateway    │    │   Strava    │ │
│  │   Interface     │◄──►│   (REST API)     │◄──►│   Webhook   │ │
│  │ (Cloudscape UI) │    │                  │    │   Handler   │ │
│  └─────────────────┘    └──────────────────┘    └─────────────┘ │
│                                                         │       │
│                                                         ▼       │
│  ┌─────────────────┐    ┌──────────────────┐    ┌─────────────┐ │
│  │   DynamoDB      │    │      SQS         │    │   Lambda    │ │
│  │   Tables        │◄──►│   Processing     │◄──►│  Activity   │ │
│  │                 │    │     Queue        │    │ Processor   │ │
│  └─────────────────┘    └──────────────────┘    └─────────────┘ │
│                                                         │       │
│                                                         ▼       │
│  ┌─────────────────┐    ┌──────────────────┐    ┌─────────────┐ │
│  │  Secrets        │    │  Step Functions  │    │   Amazon    │ │
│  │  Manager        │◄──►│   Workflow       │◄──►│   Bedrock   │ │
│  │                 │    │                  │    │  (Claude)   │ │
│  └─────────────────┘    └──────────────────┘    └─────────────┘ │
│                                                         │       │
│                                                         ▼       │
│  ┌─────────────────┐    ┌──────────────────┐    ┌─────────────┐ │
│  │   AgentCore     │    │   AgentCore      │    │   Campus    │ │
│  │   Memory        │◄──►│  Browser Tool    │◄──►│   Coach     │ │
│  │                 │    │                  │    │  (External) │ │
│  └─────────────────┘    └──────────────────┘    └─────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Strava    │    │   Webhook   │    │     SQS     │    │   Lambda    │
│   Activity  │───►│   Handler   │───►│   Queue     │───►│  Processor  │
│   Created   │    │             │    │             │    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                           │                                      │
                           ▼                                      ▼
                   ┌─────────────┐                        ┌─────────────┐
                   │  DynamoDB   │                        │    Step     │
                   │ Rate Limits │                        │  Functions  │
                   │   Check     │                        │  Workflow   │
                   └─────────────┘                        └─────────────┘
                                                                  │
                                                                  ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Strava    │    │  Enhanced   │    │   Bedrock   │    │  Activity   │
│   Update    │◄───│   Content   │◄───│    AI       │◄───│    Data     │
│             │    │ Generation  │    │ Generation  │    │  Analysis   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                           ▲                                      │
                           │                                      ▼
                   ┌─────────────┐                        ┌─────────────┐
                   │ AgentCore   │                        │   Campus    │
                   │   Memory    │                        │   Coach     │
                   │ (Personal   │                        │  Session    │
                   │   Style)    │                        │  Matching   │
                   └─────────────┘                        └─────────────┘
```

### CDK Stack Dependencies

```
┌─────────────────────────────────────────────────────────────────┐
│                     CDK Stack Architecture                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              CoreInfrastructureStack                        │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │ │
│  │  │  DynamoDB   │ │     IAM     │ │    Secrets Manager      │ │ │
│  │  │   Tables    │ │    Roles    │ │                         │ │ │
│  │  └─────────────┘ └─────────────┘ └─────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                │                                 │
│                                ▼                                 │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │             WebhookProcessingStack                          │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │ │
│  │  │     SQS     │ │   Lambda    │ │      API Gateway        │ │ │
│  │  │   Queues    │ │ Functions   │ │                         │ │ │
│  │  └─────────────┘ └─────────────┘ └─────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                │                                 │
│                                ▼                                 │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │           ContentGenerationStack                            │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │ │
│  │  │    Step     │ │   Bedrock   │ │      AgentCore          │ │ │
│  │  │  Functions  │ │Integration  │ │     Integration         │ │ │
│  │  └─────────────┘ └─────────────┘ └─────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                │                                 │
│                                ▼                                 │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              ApiGatewayStack                                │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │ │
│  │  │    Local    │ │    CORS     │ │     Configuration       │ │ │
│  │  │ Interface   │ │   Config    │ │        API              │ │ │
│  │  │     API     │ │             │ │                         │ │ │
│  │  └─────────────┘ └─────────────┘ └─────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                │                                 │
│                                ▼                                 │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              MonitoringStack                                │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │ │
│  │  │ CloudWatch  │ │   X-Ray     │ │        Alarms           │ │ │
│  │  │  Metrics    │ │  Tracing    │ │                         │ │ │
│  │  └─────────────┘ └─────────────┘ └─────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Infrastructure Layer
- **AWS CDK**: v2.219.0 with Python constructs
- **Python Runtime**: 3.12 for all Lambda functions
- **Region**: eu-west-1 (Ireland) for GDPR compliance
- **Deployment**: Infrastructure as Code with property-based testing

### Compute Layer
- **AWS Lambda**: Serverless compute for all processing
- **Step Functions**: Workflow orchestration for complex processes
- **AgentCore Runtime**: Browser automation and memory services
- **API Gateway**: REST API for local interface communication

### Storage Layer
- **DynamoDB**: NoSQL database with AWS managed encryption
- **Secrets Manager**: Secure credential storage with rotation
- **SQS**: Message queuing with dead letter queues
- **AgentCore Memory**: Persistent AI memory for personalization

### AI/ML Layer
- **Amazon Bedrock**: Claude Sonnet 4.5 for content generation
- **Strands Agents**: Agent orchestration framework
- **AgentCore Browser Tool**: Automated web scraping
- **Pattern Recognition**: Intelligent activity analysis

### Interface Layer
- **Python Flask/FastAPI**: Local web application backend
- **AWS Cloudscape**: Frontend UI component library
- **Real-time Dashboard**: Activity processing monitoring
- **Module Management**: Configuration interface

## Design Decisions

### 1. Local Web Interface vs. Hosted Solution

**Decision**: Local web interface with Python Flask/FastAPI  
**Rationale**: 
- Eliminates complexity of Cognito, CloudFront, S3 hosting
- Reduces security surface area (local-only access)
- Faster development and deployment
- User maintains full control of their environment

**Trade-offs**:
- ✅ Simplified architecture and deployment
- ✅ Enhanced privacy and security
- ✅ Reduced AWS costs
- ❌ Requires local setup for each user
- ❌ No multi-user support out of the box

### 2. AgentCore CLI vs. CDK L2 Constructs

**Decision**: Shell scripts using AgentCore CLI  
**Rationale**:
- CDK L2 constructs for AgentCore are experimental
- CLI provides stable, documented interface
- Better error handling and debugging
- Easier to maintain and update

**Implementation**:
```bash
# scripts/deploy_agentcore.sh
agentcore configure --region eu-west-1
agentcore memory create --name strava-ai-boost-memory
agentcore agent deploy --name content-generation-agent
```

### 3. Property-Based Testing for Infrastructure

**Decision**: Hypothesis framework for infrastructure validation  
**Rationale**:
- Validates security properties across all possible inputs
- Catches edge cases that unit tests might miss
- Provides mathematical confidence in security properties
- Aligns with formal verification principles

**Implementation**:
```python
@given(table_name=st.text(min_size=1, max_size=50))
def test_property_15_data_encryption_at_rest(self, table_name):
    """Property 15: All DynamoDB tables must have encryption enabled"""
    # Test validates encryption across all possible table configurations
```

### 4. Modular Architecture with Base Classes

**Decision**: Abstract base classes for extensible modules  
**Rationale**:
- Easy addition of new integrations (Runna, TrainingPeaks, etc.)
- Consistent interface across all modules
- Configuration persistence in DynamoDB
- Graceful degradation when modules fail

**Implementation**:
```python
class BaseModule:
    async def analyze_activity(self, activity: ActivityData) -> ModuleInsight:
        raise NotImplementedError
    
    async def configure(self, credentials: Dict) -> bool:
        raise NotImplementedError
```

### 5. Rate Limiting Strategy

**Decision**: DynamoDB-based rate limiting with TTL  
**Rationale**:
- Persistent across Lambda invocations
- Automatic cleanup with TTL
- Supports both short-term (15min) and daily limits
- Enables intelligent request queuing

**Implementation**:
```python
class StravaRateLimiter:
    short_term_limit = 100  # per 15 minutes
    daily_limit = 1000      # per day
    
    async def check_and_wait(self) -> bool:
        # Check current usage in DynamoDB
        # Queue requests if limits approached
        # Exponential backoff for exceeded limits
```

## Security Architecture

### Defense in Depth

1. **Network Security**
   - API Gateway with HTTPS enforcement
   - Local interface bound to 127.0.0.1 only
   - No public endpoints except webhook receiver

2. **Identity and Access Management**
   - Least privilege IAM roles
   - AWS managed policies where possible
   - Resource-level permissions
   - Cross-service access only where required

3. **Data Protection**
   - Encryption at rest for all storage (DynamoDB, SQS)
   - Encryption in transit (TLS 1.2+)
   - Secrets Manager for credential storage
   - Automatic secret rotation

4. **Application Security**
   - Input validation with Pydantic models
   - SQL injection prevention (NoSQL)
   - CSRF protection in local interface
   - Request rate limiting

### Security Properties Validated

- **Property 15**: Data encryption at rest for all DynamoDB tables
- **Property 16**: Secure HTTPS communication for all API endpoints
- **IAM Compliance**: Least privilege principle enforcement
- **Secret Management**: No hardcoded credentials in environment variables
- **Network Security**: Regional endpoints with proper TLS configuration

## Performance Architecture

### Latency Optimization

1. **Cold Start Mitigation**
   - Python 3.12 for faster startup
   - Minimal dependencies in Lambda packages
   - Connection pooling for DynamoDB
   - AgentCore agent warming strategies

2. **Caching Strategy**
   - Activity data: 24-hour cache in DynamoDB
   - Campus Coach sessions: Weekly refresh
   - Rate limit status: In-memory + DynamoDB persistence
   - OAuth tokens: Cached until expiration

3. **Parallel Processing**
   - SQS for asynchronous processing
   - Step Functions for workflow orchestration
   - Concurrent Lambda invocations
   - Batch processing for Campus Coach extraction

### Scalability Patterns

1. **Serverless Auto-scaling**
   - Lambda: Automatic concurrency scaling
   - DynamoDB: On-demand billing mode
   - SQS: Unlimited throughput
   - API Gateway: Built-in scaling

2. **Resource Optimization**
   - Right-sized Lambda memory allocation
   - DynamoDB GSI for efficient queries
   - SQS batch processing
   - Connection reuse across invocations

## Cost Architecture

### Cost Optimization Strategies

1. **Serverless-First Approach**
   - Pay-per-use pricing model
   - No idle resource costs
   - Automatic scaling down to zero
   - Reserved capacity only for predictable workloads

2. **Intelligent Caching**
   - Reduce API calls through caching
   - Batch operations where possible
   - TTL-based automatic cleanup
   - Efficient data structures

3. **Resource Right-Sizing**
   - Lambda memory optimization
   - DynamoDB capacity planning
   - SQS message batching
   - Bedrock API call optimization

### Cost Breakdown (Per Activity)

| Service | Cost | Percentage |
|---------|------|------------|
| Lambda Executions | $0.001 | 5% |
| DynamoDB Operations | $0.001 | 5% |
| Step Functions | $0.003 | 15% |
| Bedrock API Calls | $0.005 | 25% |
| SQS Messages | $0.0001 | 0.5% |
| AgentCore Memory | $0.001 | 5% |
| AgentCore Browser Tool | $0.009 | 44.5% |
| **Total** | **~$0.02** | **100%** |

## Reliability Architecture

### Error Handling Strategy

1. **Retry Logic**
   - Exponential backoff with jitter
   - Circuit breaker pattern
   - Dead letter queues for failed messages
   - Maximum retry limits

2. **Graceful Degradation**
   - Module-specific error boundaries
   - Fallback to basic content generation
   - Partial functionality when services unavailable
   - User notification of service issues

3. **Monitoring and Alerting**
   - CloudWatch metrics and alarms
   - X-Ray distributed tracing
   - Real-time error notifications
   - Performance bottleneck identification

### Known Issues and Mitigations

1. **AgentCore Browser Tool Cold Start**
   - **Issue**: ~30% first-try success rate
   - **Mitigation**: Exponential backoff retry logic
   - **Monitoring**: Success rate tracking and alerting

2. **Strava API Rate Limits**
   - **Issue**: 100/15min, 1000/day limits
   - **Mitigation**: Intelligent queuing and backoff
   - **Monitoring**: Rate limit utilization tracking

## Future Architecture Considerations

### Planned Enhancements

1. **Multi-User Support**
   - User isolation in DynamoDB
   - Per-user configuration management
   - Shared infrastructure with tenant separation

2. **Additional Integrations**
   - Runna training platform
   - TrainingPeaks structured workouts
   - Garmin Connect device data
   - Weather API integration

3. **Advanced AI Features**
   - Multi-modal content generation
   - Image analysis for activity photos
   - Predictive performance insights
   - Personalized training recommendations

4. **Performance Optimizations**
   - Lambda provisioned concurrency
   - DynamoDB Global Tables
   - CloudFront distribution
   - Edge computing with Lambda@Edge

---

**Version:** v1.3.0 - AgentCore Integration Complete  
**Last Updated:** 2025-12-23  
**Next Milestone:** v1.4.0 - Local Web Interface Enhancement