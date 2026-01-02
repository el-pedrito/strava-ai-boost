# 📖 Complete Setup Guide

**Comprehensive deployment with all configuration options**

This guide covers the complete setup process including advanced configurations, security hardening, and production considerations.

## Deployment Architecture

Strava AI Boost uses a **4-step deployment strategy** to avoid circular dependencies between AWS infrastructure and AgentCore agents:

### **Step 1: AWS Infrastructure**
- Deploys CDK stacks with empty AgentCore environment variables
- Creates DynamoDB tables, Lambda functions, Step Functions, etc.
- System works immediately with Bedrock fallback mode
- No dependencies on AgentCore agents

### **Step 2: AgentCore Long-Term Memory**
- Creates LTM memories with semantic search strategy
- 365-day retention for persistent learning
- Semantic search enables style pattern recognition
- Takes ~3 minutes per memory to provision

### **Step 3: AgentCore Agents**
- Deploys AgentCore agents using `direct_code_deploy`
- Configures agents to use pre-created LTM memories
- Creates AI agents for enhanced content generation
- Independent of Lambda environment configuration

### **Step 4: AgentCore Integration**
- Configures dynamic IAM permissions for AgentCore agents
- **Updates Lambda environment variables** with agent ARNs via AWS API
- Enables seamless integration between infrastructure and AI agents
- No CDK redeploy required - changes are immediately active

This approach ensures:
- ✅ **No circular dependencies**
- ✅ **System always functional** (even if AgentCore fails)
- ✅ **Clean separation of concerns**
- ✅ **Easy troubleshooting and maintenance**
- ✅ **Long-term learning** with semantic memory

## Complete Deployment Process

### Option 1: Automated Deployment (Recommended)

```bash
# Step 1: Deploy AWS Infrastructure (includes SecurityStack with Guardrails)
./scripts/deploy.sh dev

# Step 2: Create AgentCore Long-Term Memories (~6 minutes)
./scripts/create_agentcore_memories.sh

# Step 3: Deploy AgentCore Agents (initial deployment)
./scripts/deploy_agentcore_agents.sh

# Step 4: Configure AgentCore Integration (detects and configures guardrails)
./scripts/configure_agentcore_integration.sh

# Step 5: Redeploy Agents with Guardrails
./scripts/deploy_agentcore_agents.sh

# Step 6: Final CDK deployment (load agent ARNs)
cdk deploy --all --profile your-aws-profile --require-approval never
```

**Why Step 5?** After Step 4 detects guardrails and updates `.env.agentcore`, agents need to be redeployed to receive the guardrail configuration.

### Option 2: Manual Step-by-Step Deployment

If you prefer manual control or need to troubleshoot:

#### Step 1: Deploy AWS Infrastructure
```bash
# Bootstrap CDK (first time only)
cdk bootstrap --profile your-aws-profile

# Deploy all CDK stacks (includes SecurityStack)
cdk deploy --all --profile your-aws-profile --require-approval never
```

#### Step 2: Create AgentCore Long-Term Memories
```bash
# Create LTM memories with semantic search (~6 minutes total)
./scripts/create_agentcore_memories.sh

# Verify memories are ACTIVE
agentcore memory list --region eu-west-1
```

#### Step 3: Deploy AgentCore Agents (Initial)
```bash
# Deploy agents with pre-created LTM memories
./scripts/deploy_agentcore_agents.sh
```

#### Step 4: Configure AgentCore Integration
```bash
# Configure IAM permissions, Lambda integration, and detect guardrails
./scripts/configure_agentcore_integration.sh
```

**This step:**
- Detects Bedrock Guardrails from SecurityStack
- Updates `.env.agentcore` with guardrail configuration
- Configures IAM permissions
- Updates Lambda environment variables

#### Step 5: Redeploy Agents with Guardrails
```bash
# Redeploy agents to enable guardrails
./scripts/deploy_agentcore_agents.sh
```

**Verification:**
```bash
# Check logs for guardrail confirmation
aws logs tail /aws/bedrock-agentcore/runtimes/content_gen-* --since 5m --profile your-aws-profile | grep guardrail
aws logs tail /aws/bedrock-agentcore/runtimes/campus_coach-* --since 5m --profile your-aws-profile | grep guardrail

# Should see: "Creating agent with guardrails: <id> v1"
```

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

Choose your deployment method:

#### Option A: Automated Deployment (Recommended)
```bash
# Single command deploys everything
./scripts/deploy.sh dev

# This automatically handles:
# - CDK infrastructure deployment (Phase 1)
# - AgentCore agents deployment (Phase 2)  
# - Lambda environment variable updates
# - Secrets Manager configuration
```

#### Option B: Manual Phase-by-Phase Deployment
```bash
# Phase 1: Deploy CDK infrastructure
cdk deploy --all --profile your-aws-profile --require-approval never

# Phase 2: Deploy AgentCore agents and update Lambda environment variables
./scripts/deploy_agentcore_agents.sh
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

**If you used automated deployment (`./scripts/deploy.sh`), this is already done!**

For manual deployment:

```bash
# Deploy AgentCore agents and update Lambda environment variables
./scripts/deploy_agentcore_agents.sh

# This script automatically:
# 1. Deploys content generation agent
# 2. Deploys campus coach agent  
# 3. Sets up AgentCore Memory
# 4. Updates Lambda environment variables with agent ARNs
# 5. Updates CDK context for future deployments
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

### 5. **IMPORTANT: Redeploy After Agent Configuration**

After deploying AgentCore agents, you **MUST redeploy the CDK stacks** to update Lambda environment variables with agent ARNs:

```bash
# Redeploy to update Lambda environment variables
cdk deploy --all --profile your-aws-profile --require-approval never
```

**Why this is required:**
- AgentCore agents are deployed independently of CDK
- Lambda functions need agent ARNs in their environment variables
- The AgentCore Health Check Lambda reads ARNs from `.env.agentcore`
- CDK loads `.env.agentcore` at deployment time, not runtime
- Without redeployment, the dashboard won't show correct AgentCore status

**When to redeploy:**
- ✅ After initial AgentCore agent deployment
- ✅ After updating agent ARNs in `.env.agentcore`
- ✅ After redeploying AgentCore agents with new versions
- ❌ Not needed for module configuration (Campus Coach credentials, etc.)

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

# Start Flask application with proper AWS configuration
./local_interface/start_dashboard.sh
```

**Benefits of using `start_dashboard.sh`:**
- Automatic AWS profile configuration
- Credential verification before startup
- Proper environment variable setup
- Clear error messages if AWS setup is incorrect

### 3. Verify Local Interface

- Open http://localhost:3000
- Check system status indicators
- Verify API connectivity

## Strava Integration

### 1. Store Strava Credentials in AWS Secrets Manager

**First, store your Strava app credentials securely:**

```bash
# Replace with your actual Strava app credentials
export STRAVA_CLIENT_ID=your_client_id
export STRAVA_CLIENT_SECRET=your_client_secret

# Store in AWS Secrets Manager
aws secretsmanager put-secret-value \
  --secret-id strava-ai-boost-oauth-tokens \
  --secret-string "{\"client_id\":\"$STRAVA_CLIENT_ID\",\"client_secret\":\"$STRAVA_CLIENT_SECRET\"}" \
  --profile your-aws-profile

# Verify storage
aws secretsmanager get-secret-value \
  --secret-id strava-ai-boost-oauth-tokens \
  --profile your-aws-profile \
  --query SecretString --output text | jq '.'
```

### 2. Configure Webhook Subscription

**Set up Strava webhook to receive activity notifications:**

> **💡 Webhook Purpose:** Tells Strava "notify my system when activities are created/updated"

```bash
# Configure webhook with automatic setup
./scripts/configure_strava_webhook.sh dev --auto-configure

# Or configure manually (interactive)
./scripts/configure_strava_webhook.sh dev

# Verify webhook is active
./scripts/configure_strava_webhook.sh dev --validate-only
```

### 3. Configure OAuth via Web Interface

> **💡 OAuth Purpose:** Gives your system permission to read and modify your Strava activity data

1. **Open Dashboard**: http://localhost:3000
2. **Go to Configuration**: Click Configuration tab
3. **Verify Strava App Status**: Should show "Configured" (credentials from Secrets Manager)
4. **Connect Account**:
   - Click "Connect with Strava"
   - Authorize on Strava
   - Verify successful connection

> **🔄 How They Work Together:** Webhook receives "new activity" notifications → OAuth tokens allow fetching/updating that activity's data

### 4. Test Integration

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
5. **Automatic extraction starts immediately**

**Automatic Daily Extraction**:
- ⏰ **Scheduled Time**: Every morning at 6 AM Paris time (5 UTC)
- 🔄 **Automatic Activation**: EventBridge scheduler enabled when you activate the module
- ⏸️ **Automatic Deactivation**: Scheduler disabled when you deactivate the module
- 📊 **Zero Manual Work**: Sessions always up-to-date without intervention
- 🎯 **Smart Matching**: New activities automatically matched with latest sessions

**How It Works**:
1. You enable Campus Coach in dashboard → EventBridge scheduler activates
2. Every morning at 6 AM → Lambda invokes Campus Coach agent
3. Agent scrapes latest sessions → Saves to DynamoDB
4. Your activities → Automatically matched with fresh sessions
5. You disable Campus Coach → Scheduler deactivates (no more extractions)

**Verification**:
- Check "Last Extraction" timestamp in dashboard
- Upload a training activity
- Verify session matching in enhanced content (e.g., "✅ Session Campus Coach validée : Endurance Fondamentale")

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