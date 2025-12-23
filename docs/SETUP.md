# Strava AI Boost - Setup and Deployment Guide

**Version:** v1.3.0 - AgentCore Integration Complete  
**Last Updated:** 2025-12-23

This guide provides step-by-step instructions for setting up and deploying the Strava AI Boost system in your AWS environment.

## Prerequisites

### Required Accounts and Services

1. **AWS Account**
   - Administrative access or sufficient permissions for CDK deployment
   - Region: eu-west-1 (Ireland) recommended
   - Estimated cost: ~$2/month for 100 activities

2. **Strava Developer Account**
   - Create application at https://developers.strava.com/
   - Note your Client ID and Client Secret
   - Configure OAuth redirect URI

3. **Campus Coach Account** (Optional)
   - Active subscription required
   - Username and password for automation

4. **Enduraw Integration** (Optional)
   - Third-party Strava app for enhanced analytics
   - 2-7 minute processing delay when enabled

### Development Environment

#### Required Software

```bash
# Python 3.12+
python --version  # Should be 3.12 or higher

# Node.js (for AWS CDK)
node --version    # Should be 18+ or 20+
npm --version

# AWS CLI v2
aws --version     # Should be 2.x

# AWS CDK CLI
npm install -g aws-cdk
cdk --version     # Should be 2.x

# AgentCore CLI (will be installed during setup)
# Installation instructions provided in AgentCore setup section
```

#### AWS Profile Configuration

```bash
# Configure AWS profile
aws configure --profile your-aws-profile
# Enter your AWS Access Key ID
# Enter your AWS Secret Access Key
# Default region: eu-west-1
# Default output format: json

# Verify profile
aws sts get-caller-identity --profile your-aws-profile
```

## Installation

### 1. Clone and Setup Project

```bash
# Clone repository
git clone <repository-url>
cd strava-ai-boost

# Create Python virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install Lambda dependencies
pip install -r lambda_functions/requirements.txt
```

### 2. Environment Configuration

```bash
# Set AWS profile for session
export AWS_PROFILE=your-aws-profile
export AWS_REGION=eu-west-1

# Verify AWS access
aws sts get-caller-identity
```

### 3. CDK Bootstrap (First Time Only)

```bash
# Bootstrap CDK in your AWS account
cdk bootstrap --profile your-aws-profile

# Verify bootstrap
aws cloudformation describe-stacks --stack-name CDKToolkit --profile your-aws-profile
```

## Deployment

### Phase 1: Core Infrastructure

#### 1. Validate CDK Configuration

```bash
# Synthesize CloudFormation templates
cdk synth --profile your-aws-profile

# List available stacks
cdk list --profile your-aws-profile
# Expected output:
# StravaAIBoost-Core
# StravaAIBoost-Webhook
```

#### 2. Run Infrastructure Tests

```bash
# Run property-based security tests
python -m pytest tests/test_infrastructure_properties.py -v

# Expected output: 10 tests passed
# - Property 15: Data encryption at rest
# - Property 16: Secure HTTPS communication
# - Additional security and correctness tests
```

#### 3. Deploy Core Infrastructure

```bash
# Deploy core infrastructure stack
cdk deploy StravaAIBoost-Core --profile your-aws-profile

# Deploy webhook processing stack
cdk deploy StravaAIBoost-Webhook --profile your-aws-profile

# Deploy all stacks (alternative)
cdk deploy --all --profile your-aws-profile
```

#### 4. Verify Deployment

```bash
# Check DynamoDB tables
aws dynamodb list-tables --profile your-aws-profile | grep strava-ai-boost

# Check Lambda functions
aws lambda list-functions --profile your-aws-profile | grep StravaAIBoost

# Check SQS queues
aws sqs list-queues --profile your-aws-profile | grep strava-ai-boost

# Check Secrets Manager
aws secretsmanager list-secrets --profile your-aws-profile | grep strava-ai-boost
```

### Phase 2: AgentCore Setup

#### 1. Install AgentCore CLI

```bash
# Install AgentCore CLI (follow official documentation)
# This step will be updated when AgentCore CLI is available

# Verify installation
agentcore --version
```

#### 2. Configure AgentCore

```bash
# Configure AgentCore for your AWS account
agentcore configure --region eu-west-1 --profile your-aws-profile

# Verify configuration
agentcore status
```

#### 3. Deploy AgentCore Resources

```bash
# Make deployment script executable
chmod +x scripts/deploy_agentcore.sh

# Run AgentCore deployment
./scripts/deploy_agentcore.sh

# Verify AgentCore deployment
agentcore agent list --profile your-aws-profile
agentcore memory list --profile your-aws-profile
```

### Phase 3: Strava Integration

#### 1. Configure Strava OAuth

```bash
# Store Strava OAuth credentials in Secrets Manager
aws secretsmanager put-secret-value \
  --secret-id strava-ai-boost-oauth-tokens \
  --secret-string '{
    "client_id": "YOUR_STRAVA_CLIENT_ID",
    "client_secret": "YOUR_STRAVA_CLIENT_SECRET",
    "redirect_uri": "http://localhost:8000/auth/callback"
  }' \
  --profile your-aws-profile
```

#### 2. Configure Campus Coach (Optional)

```bash
# Store Campus Coach credentials in Secrets Manager
aws secretsmanager put-secret-value \
  --secret-id strava-ai-boost-campus-coach-credentials \
  --secret-string '{
    "username": "YOUR_CAMPUS_COACH_USERNAME",
    "password": "YOUR_CAMPUS_COACH_PASSWORD",
    "login_url": "https://campus.coach/login"
  }' \
  --profile your-aws-profile
```

### Phase 4: Local Interface Setup

#### 1. Install Local Interface Dependencies

```bash
# Install additional dependencies for local interface
pip install flask flask-cors

# Verify installation
python -c "import flask; print(flask.__version__)"
```

#### 2. Configure Local Interface

```bash
# Create local configuration file
cp local_interface/config.example.py local_interface/config.py

# Edit configuration
# Update AWS region, profile, and other settings
```

#### 3. Start Local Interface

```bash
# Start local web interface
cd local_interface
python app.py

# Access interface at http://localhost:8000
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# AWS Configuration
AWS_PROFILE=your-aws-profile
AWS_REGION=eu-west-1

# Application Configuration
FLASK_ENV=development
FLASK_DEBUG=true

# Strava Configuration
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
STRAVA_REDIRECT_URI=http://localhost:8000/auth/callback

# AgentCore Configuration
AGENTCORE_REGION=eu-west-1
AGENTCORE_MEMORY_NAME=strava-ai-boost-memory
```

### DynamoDB Table Configuration

The following tables are automatically created during deployment:

1. **strava-ai-boost-activities**
   - Stores activity data and processing status
   - GSI: ProcessingStatusIndex

2. **strava-ai-boost-user-configuration**
   - Stores user settings and module configurations
   - Single-user setup initially

3. **strava-ai-boost-rate-limits**
   - Tracks Strava API rate limit usage
   - TTL enabled for automatic cleanup

4. **strava-ai-boost-campus-coaching-sessions**
   - Stores extracted Campus Coach sessions
   - GSI: WeekNumberIndex

### Lambda Function Configuration

Lambda functions are automatically configured with:

- **Runtime**: Python 3.12
- **Memory**: 256MB - 512MB (function-specific)
- **Timeout**: 30s - 300s (function-specific)
- **Environment Variables**: Automatically set by CDK

## Validation

### 1. Infrastructure Validation

```bash
# Run comprehensive test suite
python -m pytest tests/ -v

# Run specific property tests
python -m pytest tests/test_infrastructure_properties.py::TestInfrastructureSecurityProperties -v

# Check CDK synthesis
cdk synth --profile your-aws-profile
```

### 2. AWS Resource Validation

```bash
# Validate DynamoDB tables
aws dynamodb describe-table --table-name strava-ai-boost-activities --profile your-aws-profile

# Validate Lambda functions
aws lambda get-function --function-name StravaAIBoost-WebhookHandler --profile your-aws-profile

# Validate SQS queues
aws sqs get-queue-attributes --queue-url $(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing --profile your-aws-profile --query 'QueueUrl' --output text) --profile your-aws-profile

# Validate Secrets Manager
aws secretsmanager describe-secret --secret-id strava-ai-boost-oauth-tokens --profile your-aws-profile
```

### 3. AgentCore Validation

```bash
# Check AgentCore status
agentcore status --profile your-aws-profile

# List deployed agents
agentcore agent list --profile your-aws-profile

# Check memory service
agentcore memory list --profile your-aws-profile

# Test agent invocation (when implemented)
# agentcore invoke content-generation-agent --input '{"test": true}'
```

### 4. Local Interface Validation

```bash
# Test local interface startup
cd local_interface
python app.py &

# Test API endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/status

# Stop local interface
pkill -f "python app.py"
```

## Monitoring Setup

### CloudWatch Dashboards

```bash
# Create monitoring dashboard (when MonitoringStack is deployed)
aws cloudwatch put-dashboard \
  --dashboard-name "StravaAIBoost-Monitoring" \
  --dashboard-body file://monitoring/dashboard.json \
  --profile your-aws-profile
```

### Alarms Configuration

```bash
# Set up basic alarms
aws cloudwatch put-metric-alarm \
  --alarm-name "StravaAIBoost-HighErrorRate" \
  --alarm-description "High error rate in processing" \
  --metric-name "Errors" \
  --namespace "AWS/Lambda" \
  --statistic "Sum" \
  --period 300 \
  --threshold 5 \
  --comparison-operator "GreaterThanThreshold" \
  --evaluation-periods 2 \
  --profile your-aws-profile
```

## Troubleshooting

### Common Issues

#### 1. CDK Bootstrap Issues

```bash
# Error: "CDK toolkit stack not found"
# Solution: Run bootstrap command
cdk bootstrap --profile your-aws-profile

# Error: "Insufficient permissions"
# Solution: Ensure your AWS user has AdministratorAccess or required permissions
```

#### 2. Lambda Deployment Issues

```bash
# Error: "Code size too large"
# Solution: Check lambda_functions/requirements.txt for unnecessary dependencies

# Error: "Runtime not supported"
# Solution: Ensure Python 3.12 is specified in CDK stack
```

#### 3. DynamoDB Issues

```bash
# Error: "Table already exists"
# Solution: Check if previous deployment failed, clean up manually if needed
aws dynamodb delete-table --table-name strava-ai-boost-activities --profile your-aws-profile
```

#### 4. AgentCore Issues

```bash
# Error: "AgentCore CLI not found"
# Solution: Install AgentCore CLI following official documentation

# Error: "Agent deployment failed"
# Solution: Check AgentCore logs and retry with exponential backoff
```

### Debugging Commands

```bash
# Check CloudFormation stack status
aws cloudformation describe-stacks --stack-name StravaAIBoost-Core --profile your-aws-profile

# View Lambda logs
aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile your-aws-profile

# Check SQS queue messages
aws sqs receive-message --queue-url <queue-url> --profile your-aws-profile

# Monitor DynamoDB operations
aws dynamodb scan --table-name strava-ai-boost-activities --profile your-aws-profile | jq '.Items | length'
```

## Cleanup

### Partial Cleanup (Keep Data)

```bash
# Remove Lambda functions only
cdk destroy StravaAIBoost-Webhook --profile your-aws-profile

# Keep DynamoDB tables and data
```

### Complete Cleanup

```bash
# Destroy all CDK stacks
cdk destroy --all --profile your-aws-profile

# Clean up AgentCore resources
agentcore agent delete --name content-generation-agent --profile your-aws-profile
agentcore memory delete --name strava-ai-boost-memory --profile your-aws-profile

# Remove Secrets Manager secrets (optional)
aws secretsmanager delete-secret --secret-id strava-ai-boost-oauth-tokens --force-delete-without-recovery --profile your-aws-profile
aws secretsmanager delete-secret --secret-id strava-ai-boost-campus-coach-credentials --force-delete-without-recovery --profile your-aws-profile
```

## Next Steps

After successful deployment:

1. **Configure Strava OAuth** - Complete OAuth flow in local interface
2. **Test Webhook Processing** - Create test activity in Strava
3. **Enable Campus Coach Module** - Configure credentials and test extraction
4. **Monitor Performance** - Set up CloudWatch dashboards and alarms
5. **Implement Content Generation** - Deploy Bedrock integration (Task 2)

## Support

For issues and questions:

1. Check [Known Issues](KNOWN-ISSUES.md) documentation
2. Review CloudWatch logs for error details
3. Validate AWS permissions and quotas
4. Test individual components in isolation

---

**Version:** v1.3.0 - AgentCore Integration Complete  
**Last Updated:** 2025-12-23  
**Next Phase:** Local Web Interface Enhancement (Task 16+)