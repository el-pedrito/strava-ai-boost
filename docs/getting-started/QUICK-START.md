# 🚀 Quick Start Guide

**Get Strava AI Boost running with a clear 2-phase deployment!**

## 📋 Deployment Strategy

### **Phase 1: Infrastructure (Required)**
Deploy AWS infrastructure with Bedrock fallback mode. System works immediately!

### **Phase 2: AgentCore Enhancement (Optional)**
Add advanced personalization with Long-Term Memory and semantic search.

---

## Prerequisites

- AWS Account with CLI configured (`your-aws-profile` profile)
- Python 3.12+
- Node.js (for CDK)
- AgentCore CLI (for Phase 2 only)

---

## Phase 1: Infrastructure Deployment (Required)

### Step 1: Clone and Setup

```bash
git clone <repository-url>
cd strava-ai-boost
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set AWS profile
export AWS_PROFILE=your-aws-profile
```

### Step 2: Deploy AWS Infrastructure

```bash
./scripts/deploy.sh dev
```

**What this deploys:**
- ✅ 7 CDK stacks (Core, Security, Webhook, Content, API, Monitoring, Feedback)
- ✅ DynamoDB tables, Lambda functions, Step Functions
- ✅ Secrets Manager placeholders
- ✅ Bedrock fallback mode (Claude Sonnet 4.5)
- ✅ **System is immediately functional!**

### Step 3: Validate Deployment

```bash
./scripts/validate_deployment.sh dev
```

### Step 4: Setup Local Environment

```bash
./scripts/setup_local_env.sh
```

**What this does:**
- ✅ Retrieves API Gateway URL from CloudFormation
- ✅ Retrieves API Key from AWS
- ✅ Generates `local_interface/.env` file

### Step 5: Configure Strava Webhook

```bash
./scripts/configure_strava_webhook.sh dev --auto-configure
```

**What this does:**
- ✅ Retrieves Strava credentials from Secrets Manager (`strava-ai-boost-app-config`)
- ✅ Creates Strava webhook subscription
- ✅ Enables real-time activity processing
- ✅ **Required for automatic processing**

**Note:** Make sure your Strava app credentials are in Secrets Manager:
```bash
# If not already configured, add your credentials:
aws secretsmanager put-secret-value \
  --secret-id strava-ai-boost-app-config \
  --secret-string '{"client_id":"YOUR_CLIENT_ID","client_secret":"YOUR_CLIENT_SECRET"}' \
  --profile your-aws-profile \
  --region eu-west-1
```

### Step 6: Start Local Interface (30 sec)

```bash
cd local_interface
python app.py
```

Open http://localhost:3000 in your browser.

### Step 7: Connect with Strava

1. Open http://localhost:3000
2. Click "Connect with Strava"
3. Authorize the application
4. Configure your preferences (age, interests, style)
5. Test with a Strava activity!

**🎉 Phase 1 Complete! Your system is fully functional.**

---

## Phase 2: AgentCore Enhancement (Optional)

Add advanced personalization with Long-Term Memory.

### Step 1: Create AgentCore Memories

```bash
./scripts/create_agentcore_memories.sh
```

**What this creates:**
- ✅ 2 LTM memories with semantic search
- ✅ 365-day retention
- ✅ Persistent style learning

**Wait for memories to become ACTIVE:**
```bash
agentcore memory list --region eu-west-1
```

### Step 2: Deploy AgentCore Agents

```bash
./scripts/deploy_agentcore_agents.sh
```

**What this deploys:**
- ✅ `content_gen` agent (personalized content)
- ✅ `campus_coach` agent (session extraction)
- ✅ Bedrock Guardrails integration
- ✅ LTM memory configuration

### Step 3: Configure Integration

```bash
./scripts/configure_agentcore_integration.sh
```

**What this configures:**
- ✅ IAM permissions for AgentCore
- ✅ Lambda environment variables with agent ARNs
- ✅ Detects and configures Bedrock Guardrails
- ✅ Updates `.env.agentcore` with guardrail configuration

### Step 4: Configure Memory Strategy

```bash
python scripts/configure_memory_strategy.py
```

**What this does:**
- ✅ Adds UserPreferenceStrategy to content generation memory
- ✅ Automatic extraction of user preferences from feedback diffs
- ✅ Custom prompts for preference consolidation over time

### Step 5: Redeploy Agents with Guardrails

```bash
./scripts/deploy_agentcore_agents.sh
```

### Step 6: Final CDK Deployment

```bash
cdk deploy --all --require-approval never
```

**What this does:**
- ✅ Updates Lambda environment variables with agent ARNs
- ✅ Loads configuration from `.env.agentcore`
- ✅ Completes AgentCore integration

**🎉 Phase 2 Complete! Advanced personalization enabled.**

---

## System Architecture

### Phase 1: Bedrock Fallback (Always Available)
- **Direct AI**: Claude Sonnet 4.5
- **Smart Prompts**: Enhanced with module insights
- **Reliability**: 99.9% availability
- **Performance**: 0.75-0.90 confidence scores

### Phase 2: AgentCore Enhancement (Optional)
- **Content Generation Agent**: Personalized AI with LTM
- **Campus Coach Agent**: Automated session extraction
- **Semantic Memory**: Pattern recognition and style adaptation
- **Performance**: 95% availability, 0.85-0.95 confidence scores

> **💡 How it works**: Phase 1 gives you a fully functional system. Phase 2 adds enhanced personalization with automatic fallback.

---

## Quick Troubleshooting

### Phase 1 deployment fails:
```bash
# Check CloudFormation console for errors
# Verify AWS credentials and permissions
```

### Phase 2 deployment fails:
```bash
# System still works with Bedrock fallback!
# Retry memory creation:
./scripts/create_agentcore_memories.sh

# Retry agent deployment:
./scripts/deploy_agentcore_agents.sh

# Retry integration configuration:
./scripts/configure_agentcore_integration.sh

# Redeploy agents with guardrails:
./scripts/deploy_agentcore_agents.sh

# Final CDK deployment:
cdk deploy --all --profile your-aws-profile --require-approval never
```

### Webhook not working:
```bash
# Validate webhook configuration
./scripts/configure_strava_webhook.sh dev --validate-only

# Reconfigure if needed
./scripts/configure_strava_webhook.sh dev --auto-configure
```

### Check system health:
```bash
./scripts/validate_deployment.sh dev
```

---

## Available Scripts

All scripts are documented in **[scripts/README.md](../../scripts/README.md)**.

**Deployment (2):**
- `deploy.sh` - Main infrastructure deployment
- `deploy_agentcore_agents.sh` - AgentCore agents with LTM

**Configuration (4):**
- `setup_local_env.sh` - Local environment setup
- `create_agentcore_memories.sh` - LTM memories
- `configure_agentcore_integration.sh` - IAM and Lambda
- `configure_strava_webhook.sh` - Webhook setup

**Maintenance (2):**
- `cleanup_strava_webhook.sh` - Webhook cleanup
- `reprocess_dlq.sh` - DLQ reprocessing

**Validation (1):**
- `validate_deployment.sh` - Post-deployment validation

**Uninstall (2):**
- `uninstall.sh` - Complete removal
- `verify_uninstall.sh` - Uninstall verification

---

## Next Steps

- **Enable Modules**: [Configuration Guide](../user-guide/CONFIGURATION.md)
- **Customize Settings**: [Dashboard Guide](../user-guide/DASHBOARD.md)
- **Troubleshooting**: [Troubleshooting Guide](../user-guide/TROUBLESHOOTING.md)
- **Full Setup**: [Complete Setup Guide](COMPLETE-SETUP.md)
- **Technical Details**: [Architecture](../reference/ARCHITECTURE.md)

---

**Need Help?** Check the [Troubleshooting Guide](../user-guide/TROUBLESHOOTING.md) or [Complete Setup Guide](COMPLETE-SETUP.md).