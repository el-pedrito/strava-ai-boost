# 🏗️ Technical Architecture

**Version:** v1.3.5 - Architecture Diagrams Complete  
**Last Updated:** 2025-12-23

This document provides detailed technical implementation information for the Strava AI Boost system, including AWS services configuration, data models, and integration patterns.

## System Architecture Overview

### Complete System Diagram

```mermaid
graph TB
    subgraph "User Environment"
        User[User]
        Browser[Web Browser]
        LocalApp[Local Flask App<br/>Port 8000]
    end
    
    subgraph "AWS Account - eu-west-1"
        subgraph "API & Webhook Layer"
            APIGW[API Gateway<br/>Configuration API]
            WebhookLambda[Webhook Handler<br/>Lambda Function]
            WebhookAPI[Webhook API<br/>Strava Integration]
        end
        
        subgraph "Message Processing"
            SQS[SQS Queue<br/>Activity Processing]
            DLQ[Dead Letter Queue<br/>Failed Messages]
        end
        
        subgraph "Orchestration"
            StepFunctions[Step Functions<br/>Activity Workflow]
            ProcessorLambda[Activity Processor<br/>Lambda Function]
        end
        
        subgraph "AI & Content Generation"
            Bedrock[Amazon Bedrock<br/>Claude Sonnet 4.5]
            AgentCoreMemory[AgentCore Memory<br/>Personalization]
            AgentCoreBrowser[AgentCore Browser<br/>Campus Coach Scraping]
        end
        
        subgraph "Data Storage"
            ActivitiesTable[(Activities Table<br/>DynamoDB)]
            ConfigTable[(User Config Table<br/>DynamoDB)]
            RateLimitsTable[(Rate Limits Table<br/>DynamoDB)]
            SessionsTable[(Campus Sessions<br/>DynamoDB)]
            SecretsManager[Secrets Manager<br/>OAuth Tokens]
        end
        
        subgraph "Monitoring"
            CloudWatch[CloudWatch<br/>Logs & Metrics]
            XRay[X-Ray<br/>Distributed Tracing]
        end
    end
    
    subgraph "External Services"
        StravaAPI[Strava API<br/>Activities & Webhooks]
        CampusCoach[Campus Coach<br/>Training Platform]
        Enduraw[Enduraw<br/>Enhanced Analytics]
    end
    
    %% User Flow
    User --> Browser
    Browser --> LocalApp
    LocalApp --> APIGW
    
    %% Webhook Flow
    StravaAPI --> WebhookAPI
    WebhookAPI --> WebhookLambda
    WebhookLambda --> SQS
    SQS --> StepFunctions
    StepFunctions --> ProcessorLambda
    
    %% Processing Flow
    ProcessorLambda --> StravaAPI
    ProcessorLambda --> Bedrock
    ProcessorLambda --> AgentCoreMemory
    ProcessorLambda --> AgentCoreBrowser
    AgentCoreBrowser --> CampusCoach
    
    %% Data Flow
    ProcessorLambda --> ActivitiesTable
    ProcessorLambda --> ConfigTable
    ProcessorLambda --> RateLimitsTable
    ProcessorLambda --> SessionsTable
    ProcessorLambda --> SecretsManager
    
    %% Monitoring
    ProcessorLambda --> CloudWatch
    ProcessorLambda --> XRay
    
    %% Error Handling
    SQS --> DLQ
```

### Data Flow Architecture

```mermaid
graph LR
    subgraph "Input Sources"
        SA[Strava Activity<br/>Webhook]
        CC[Campus Coach<br/>Sessions]
        ER[Enduraw<br/>Analytics]
    end
    
    subgraph "Processing Pipeline"
        WH[Webhook<br/>Handler]
        AP[Activity<br/>Processor]
        CG[Content<br/>Generator]
    end
    
    subgraph "AI Services"
        AC[AgentCore<br/>Memory]
        BR[Bedrock<br/>Claude]
        BT[Browser Tool<br/>Scraping]
    end
    
    subgraph "Storage"
        DB[(DynamoDB<br/>Tables)]
        SM[Secrets<br/>Manager]
    end
    
    subgraph "Output"
        SU[Strava<br/>Update]
        UI[Local<br/>Interface]
    end
    
    SA --> WH
    WH --> AP
    AP --> CG
    CG --> AC
    CG --> BR
    AP --> BT
    BT --> CC
    AP --> DB
    AP --> SM
    CG --> SU
    DB --> UI
    ER --> AP
```

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
          "arn:aws:bedrock:eu-west-1::foundation-model/global.anthropic.claude-sonnet-4-5-20250929-v1:0"
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

### Current Performance (v1.3.0)
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

## Automation Scripts

### Strava Application Setup Automation

The system includes comprehensive automation scripts for Strava application setup, validation, and maintenance. These scripts provide administrative tools that work alongside the user-facing web interface.

#### Script Overview

| Script | Purpose | Usage | Requirements |
|--------|---------|-------|--------------|
| `setup_strava_application.sh` | Interactive Strava app setup guide | Manual setup assistance | Strava Developer Account |
| `configure_strava_webhook.sh` | Automated webhook subscription | Deployment automation | Valid Strava app credentials |
| `validate_strava_setup.sh` | Comprehensive setup validation | Health checks, troubleshooting | Deployed infrastructure |
| `strava_health_check.sh` | Continuous health monitoring | Monitoring, alerting | Active Strava connection |
| `cleanup_strava_webhook.sh` | Webhook cleanup during uninstall | System cleanup | Webhook subscription exists |

#### 1. setup_strava_application.sh

**Purpose**: Interactive guide for Strava application creation and configuration

**Features**:
- Step-by-step Strava Developer Portal guidance
- Automated credential validation
- Integration with local web interface
- Best practices recommendations

**Usage**:
```bash
# Interactive setup guide
./scripts/setup_strava_application.sh

# Automated mode (CI/CD)
./scripts/setup_strava_application.sh --non-interactive
```

**Workflow**:
1. Guides user through Strava app creation
2. Validates Client ID and Secret format
3. Tests API connectivity
4. Configures redirect URIs
5. Provides next steps for web interface setup

#### 2. configure_strava_webhook.sh

**Purpose**: Automated Strava webhook subscription management

**Features**:
- Automatic webhook URL detection from CDK outputs
- Subscription creation with proper verification
- Callback URL validation
- Subscription status monitoring

**Usage**:
```bash
# Auto-configure webhook (recommended)
./scripts/configure_strava_webhook.sh --auto

# Manual configuration with custom URL
./scripts/configure_strava_webhook.sh --webhook-url https://your-api-gateway-url/webhook

# Validation mode only
./scripts/configure_strava_webhook.sh --validate-only
```

**Integration Points**:
- Called automatically by `deploy.sh` during deployment
- Integrated with `uninstall.sh` for cleanup
- Used by health check scripts for validation

#### 3. validate_strava_setup.sh

**Purpose**: Comprehensive Strava application and integration validation

**Features**:
- Multi-layer validation (credentials, API, webhook, processing)
- Detailed error reporting with remediation suggestions
- Integration testing with AWS services
- Performance benchmarking

**Validation Layers**:
```bash
# Layer 1: Credential Validation
- Client ID/Secret format validation
- Secrets Manager connectivity
- OAuth token validity

# Layer 2: API Connectivity
- Strava API endpoint reachability
- Rate limit status checking
- Authentication flow testing

# Layer 3: Webhook Integration
- Webhook subscription verification
- Callback URL accessibility
- Event processing validation

# Layer 4: Processing Pipeline
- Lambda function connectivity
- DynamoDB table access
- Step Functions workflow validation
```

**Usage**:
```bash
# Complete validation suite
./scripts/validate_strava_setup.sh

# Quick validation (credentials + API only)
./scripts/validate_strava_setup.sh --quick

# Specific component validation
./scripts/validate_strava_setup.sh --component webhook
./scripts/validate_strava_setup.sh --component processing
```

#### 4. strava_health_check.sh

**Purpose**: Continuous monitoring and health assessment

**Features**:
- Real-time system health monitoring
- Automated issue detection and alerting
- Performance metrics collection
- Proactive maintenance recommendations

**Health Check Categories**:
```bash
# OAuth Health
- Token expiration monitoring
- Refresh token validity
- Authentication success rates

# API Health  
- Rate limit utilization tracking
- API response time monitoring
- Error rate analysis

# Processing Health
- Queue depth monitoring
- Processing success rates
- End-to-end latency tracking

# Integration Health
- Webhook delivery success
- Module availability status
- AgentCore connectivity
```

**Usage**:
```bash
# Continuous monitoring (recommended for cron)
./scripts/strava_health_check.sh --monitor

# One-time health assessment
./scripts/strava_health_check.sh --check-now

# Generate health report
./scripts/strava_health_check.sh --report --output health-report.json
```

#### 5. cleanup_strava_webhook.sh

**Purpose**: Clean webhook subscriptions during system uninstall

**Features**:
- Safe webhook subscription removal
- Verification of cleanup completion
- Backup of subscription data before removal
- Integration with uninstall process

**Usage**:
```bash
# Standard cleanup (with confirmation)
./scripts/cleanup_strava_webhook.sh

# Force cleanup (no confirmation)
./scripts/cleanup_strava_webhook.sh --force

# Backup only (no removal)
./scripts/cleanup_strava_webhook.sh --backup-only
```

### Script Integration Architecture

```mermaid
graph TB
    subgraph "User Workflow"
        User[User] --> WebInterface[Local Web Interface<br/>OAuth Configuration]
    end
    
    subgraph "Administrative Scripts"
        Setup[setup_strava_application.sh<br/>Interactive Setup Guide]
        Configure[configure_strava_webhook.sh<br/>Webhook Automation]
        Validate[validate_strava_setup.sh<br/>Health Validation]
        Monitor[strava_health_check.sh<br/>Continuous Monitoring]
        Cleanup[cleanup_strava_webhook.sh<br/>Uninstall Cleanup]
    end
    
    subgraph "AWS Infrastructure"
        Secrets[Secrets Manager<br/>OAuth Tokens]
        API[API Gateway<br/>Webhook Endpoint]
        Lambda[Lambda Functions<br/>Processing Pipeline]
    end
    
    User --> Setup
    Setup --> WebInterface
    WebInterface --> Secrets
    Configure --> API
    Validate --> Lambda
    Monitor --> Secrets
    Monitor --> API
    Monitor --> Lambda
    Cleanup --> API
```

### Script Execution Context

**Development Environment**:
- Interactive setup and validation
- Detailed error reporting and guidance
- Integration with local development tools

**CI/CD Pipeline**:
- Automated validation and health checks
- Non-interactive modes for automation
- Integration with deployment scripts

**Production Monitoring**:
- Continuous health monitoring via cron jobs
- Automated alerting on health issues
- Performance metrics collection

### Error Handling and Recovery

All scripts implement comprehensive error handling:

```bash
# Standard error handling pattern
set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Logging with timestamps
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" >&2
}

# Error recovery with user guidance
handle_error() {
    local exit_code=$1
    local error_context=$2
    
    log "ERROR: $error_context (exit code: $exit_code)"
    
    case $exit_code in
        1) log "SOLUTION: Check AWS credentials and permissions" ;;
        2) log "SOLUTION: Verify Strava application configuration" ;;
        3) log "SOLUTION: Check network connectivity and API endpoints" ;;
        *) log "SOLUTION: Run with --verbose for detailed diagnostics" ;;
    esac
    
    exit $exit_code
}
```

### Security Considerations

**Credential Handling**:
- No credentials stored in scripts
- Secure retrieval from AWS Secrets Manager
- Temporary credential usage with automatic cleanup

**Access Control**:
- Scripts require appropriate AWS IAM permissions
- Validation of user permissions before execution
- Audit logging of all administrative actions

**Network Security**:
- HTTPS-only communication with external APIs
- Webhook URL validation and verification
- Rate limiting and abuse prevention

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
- **Bedrock Model**: global.anthropic.claude-sonnet-4-5-20250929-v1:0

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

**Version:** v1.3.0 - AgentCore Integration Complete  
**Last Updated:** 2025-12-23  
**Next Version:** v1.4.0 - Local Web Interface Enhancement