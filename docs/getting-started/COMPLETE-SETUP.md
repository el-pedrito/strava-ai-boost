# 📖 Complete Setup Guide

**Comprehensive deployment with all configuration options**

This guide covers the complete setup process including advanced configurations, security hardening, and production considerations.

## Prerequisites

### Required Software

```bash
# Check versions
python --version  # 3.12+
node --version    # 18+
aws --version     # 2.0+
cdk --version     # 2.0+
```

### AWS Account Setup

1. **AWS CLI Configuration**:
   ```bash
   aws configure --profile your-aws-profile
   # Enter your AWS Access Key ID
   # Enter your AWS Secret Access Key
   # Default region: eu-west-1
   # Default output format: json
   ```

2. **Verify Access**:
   ```bash
   aws sts get-caller-identity --profile your-aws-profile
   ```

3. **Required Permissions**:
   - CloudFormation full access
   - Lambda full access
   - DynamoDB full access
   - Secrets Manager full access
   - Step Functions full access
   - API Gateway full access
   - IAM role creation
   - Bedrock access

### Strava API Application

1. **Create Application**:
   - Go to https://www.strava.com/settings/api
   - Click "Create App"
   - Fill required fields:
     - **Application Name**: "My Strava AI Boost"
     - **Category**: "Data Importer"
     - **Website**: http://localhost:3000
     - **Application Description**: "Personal Strava activity enhancement using AI"
     - **Authorization Callback Domain**: localhost

2. **Note Credentials**:
   - Save Client ID and Client Secret (you'll need these later)
   - Keep these secure and never commit to version control

## Infrastructure Deployment

### 1. Project Setup

```bash
# Clone repository
git clone <repository-url>
cd strava-ai-boost

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
npm install  # For CDK dependencies
```

### 2. Environment Configuration

```bash
# Set AWS profile
export AWS_PROFILE=your-aws-profile

# Optional: Set custom region
export AWS_DEFAULT_REGION=eu-west-1

# Optional: Set environment name
export ENVIRONMENT=dev  # or prod
```

### 3. CDK Bootstrap

```bash
# Bootstrap CDK (first time only)
cdk bootstrap --profile your-aws-profile

# Verify bootstrap
aws cloudformation describe-stacks --stack-name CDKToolkit --profile your-aws-profile
```

### 4. Deploy Infrastructure

```bash
# Deploy all stacks
cdk deploy --all --profile your-aws-profile

# Or deploy individually
cdk deploy StravaAIBoostCoreStack --profile your-aws-profile
cdk deploy StravaAIBoostWebhookStack --profile your-aws-profile
cdk deploy StravaAIBoostContentStack --profile your-aws-profile
cdk deploy StravaAIBoostAPIStack --profile your-aws-profile
cdk deploy StravaAIBoostMonitoringStack --profile your-aws-profile
```

### 5. Verify Deployment

```bash
# Check stack status
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --profile your-aws-profile

# Test Lambda functions
aws lambda list-functions --profile your-aws-profile | grep StravaAIBoost

# Check DynamoDB tables
aws dynamodb list-tables --profile your-aws-profile | grep strava-ai-boost
```

## AgentCore Setup

### 1. AgentCore CLI Installation

```bash
# Install AgentCore CLI (if not already installed)
pip install agentcore-cli

# Verify installation
agentcore --version
```

### 2. Configure AgentCore

```bash
# Configure AgentCore for your AWS account
agentcore configure --region eu-west-1 --profile your-aws-profile

# Verify configuration
agentcore status
```

### 3. Deploy AgentCore Components

```bash
# Deploy AgentCore Memory
./scripts/setup_memory.sh

# Deploy Content Generation Agent
./scripts/deploy_agentcore.sh

# Deploy Campus Coach Agent (optional)
./scripts/deploy_campus_coach_agent.sh
```

### 4. Verify AgentCore Deployment

```bash
# List deployed agents
agentcore agent list --profile your-aws-profile

# Check memory status
agentcore memory list --profile your-aws-profile

# Test agent connectivity
agentcore invoke strava-ai-boost-content-generator --input '{"test": true}'
```

## Local Interface Setup

### 1. Environment Configuration

```bash
# Create local environment file
cd local_interface
cp .env.example .env

# Edit .env with your values
API_GATEWAY_URL=https://your-api-gateway-url
SECRET_KEY=your-secure-secret-key
```

### 2. Start Local Interface

```bash
# Install local dependencies
pip install -r requirements.txt

# Start Flask application
python app.py
```

### 3. Verify Local Interface

- Open http://localhost:3000
- Check system status indicators
- Verify API connectivity

## Strava Integration

### 1. Configure OAuth via Web Interface

1. **Open Dashboard**: http://localhost:3000
2. **Go to Configuration**: Click Configuration tab
3. **Configure Strava App**:
   - Enter Client ID from Strava
   - Enter Client Secret from Strava
   - Click "Save Configuration"
4. **Connect Account**:
   - Click "Connect with Strava"
   - Authorize on Strava
   - Verify successful connection

### 2. Webhook Subscription

```bash
# Set environment variables
export STRAVA_CLIENT_ID=your_client_id
export STRAVA_CLIENT_SECRET=your_client_secret

# Configure webhook
./scripts/configure_strava_webhook.sh
```

### 3. Test Integration

1. Upload a test activity to Strava
2. Monitor processing in dashboard
3. Verify enhanced content appears

## Module Configuration

### Campus Coach Module

**Prerequisites**:
- Active Campus Coach subscription
- Campus Coach account credentials

**Setup**:
1. Go to Configuration → Modules
2. Enable "Campus Coach"
3. Enter credentials:
   - Username: Your Campus Coach username
   - Password: Your Campus Coach password
4. Click "Save Configuration"
5. Wait for initial session extraction

**Verification**:
- Check "Last Extraction" timestamp
- Upload a training activity
- Verify session matching in enhanced content

### Enduraw Module

**Prerequisites**:
- Enduraw app connected to Strava account

**Setup**:
1. Install Enduraw from Strava App Store
2. Go to Configuration → Modules
3. Enable "Enduraw Integration"
4. Configure wait time (5 minutes recommended)
5. Click "Save Configuration"

**Verification**:
- Upload an outdoor activity
- Wait for Enduraw processing
- Check for weather/wind analysis in enhanced content

## Security Configuration

### 1. Secrets Management

```bash
# Verify secrets are created
aws secretsmanager list-secrets --profile your-aws-profile | grep strava-ai-boost

# Check secret values (OAuth tokens managed by web interface)
aws secretsmanager get-secret-value --secret-id strava-ai-boost-oauth-tokens --profile your-aws-profile
```

### 2. IAM Roles and Policies

```bash
# List created roles
aws iam list-roles --profile your-aws-profile | grep StravaAIBoost

# Check role policies
aws iam list-attached-role-policies --role-name StravaAIBoostWebhookHandlerRole --profile your-aws-profile
```

### 3. Network Security

- Local interface only accepts localhost connections
- All AWS communication uses HTTPS
- API Gateway has rate limiting configured
- Lambda functions have minimal required permissions

## Monitoring and Logging

### 1. CloudWatch Setup

```bash
# List log groups
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/StravaAIBoost --profile your-aws-profile

# Monitor real-time logs
aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile your-aws-profile
```

### 2. Dashboard Monitoring

- System health indicators
- Processing queue depth
- Success/failure rates
- Performance metrics

### 3. Alerting (Optional)

```bash
# Create CloudWatch alarms for critical metrics
aws cloudwatch put-metric-alarm \
  --alarm-name "StravaAIBoost-HighErrorRate" \
  --alarm-description "High error rate in webhook processing" \
  --metric-name "Errors" \
  --namespace "AWS/Lambda" \
  --statistic "Sum" \
  --period 300 \
  --threshold 5 \
  --comparison-operator "GreaterThanThreshold" \
  --profile your-aws-profile
```

## Performance Optimization

### 1. Lambda Configuration

- **Memory**: Start with 512MB, adjust based on usage
- **Timeout**: 30 seconds for webhook, 5 minutes for content generation
- **Concurrency**: Reserved concurrency for critical functions

### 2. DynamoDB Optimization

- **Billing Mode**: On-demand for variable workloads
- **Indexes**: GSI for efficient queries
- **TTL**: Automatic cleanup of old data

### 3. Cost Optimization

```bash
# Monitor costs
aws ce get-cost-and-usage \
  --time-period Start=2025-12-01,End=2025-12-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --profile your-aws-profile
```

## Backup and Recovery

### 1. Configuration Backup

```bash
# Backup system configuration
./scripts/backup_data.sh

# Verify backup
ls -la backups/
```

### 2. Disaster Recovery

```bash
# Export CloudFormation templates
aws cloudformation get-template --stack-name StravaAIBoostCoreStack --profile your-aws-profile > backup-core-template.json

# Backup DynamoDB data
aws dynamodb scan --table-name strava-ai-boost-user-configuration --profile your-aws-profile > backup-config.json
```

## Troubleshooting

### Common Issues

1. **CDK Bootstrap Fails**: Check AWS permissions
2. **Lambda Timeout**: Increase timeout in CDK configuration
3. **DynamoDB Throttling**: Switch to on-demand billing
4. **OAuth Fails**: Verify Strava app configuration

### Debug Commands

```bash
# Check CDK diff
cdk diff --profile your-aws-profile

# Validate CloudFormation templates
aws cloudformation validate-template --template-body file://cdk.out/StravaAIBoostCoreStack.template.json --profile your-aws-profile

# Test Lambda functions
aws lambda invoke --function-name StravaAIBoost-WebhookHandler --payload '{"test": true}' response.json --profile your-aws-profile
```

## Production Considerations

### 1. Environment Separation

```bash
# Deploy to production
export ENVIRONMENT=prod
cdk deploy --all --profile your-aws-profile
```

### 2. Security Hardening

- Enable CloudTrail logging
- Set up AWS Config rules
- Implement least privilege access
- Regular security audits

### 3. Scaling Considerations

- Monitor Lambda concurrency limits
- Plan for DynamoDB scaling
- Consider Step Functions execution limits
- Monitor Bedrock API quotas

## Maintenance

### 1. Regular Updates

```bash
# Update dependencies
pip install -r requirements.txt --upgrade
npm update

# Update CDK
npm install -g aws-cdk@latest
```

### 2. Health Checks

- Weekly dashboard review
- Monthly cost analysis
- Quarterly security review
- Regular backup verification

### 3. Cleanup

```bash
# Clean up old logs
aws logs delete-log-group --log-group-name /aws/lambda/old-function --profile your-aws-profile

# Remove unused resources
cdk destroy --profile your-aws-profile  # When decommissioning
```

## Next Steps

After successful deployment:

1. **Test System**: [First Steps Guide](FIRST-STEPS.md)
2. **Daily Usage**: [Dashboard Guide](../user-guide/DASHBOARD.md)
3. **Customization**: [Configuration Guide](../user-guide/CONFIGURATION.md)
4. **Troubleshooting**: [Troubleshooting Guide](../user-guide/TROUBLESHOOTING.md)