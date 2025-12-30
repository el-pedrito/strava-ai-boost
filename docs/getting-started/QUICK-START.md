# 🚀 Quick Start Guide

**Get Strava AI Boost running in 5 minutes with clear 3-step deployment!**

This guide uses a **3-step deployment approach** that eliminates circular dependencies and ensures your system is always functional.

## 📋 3-Step Deployment Strategy

### **Step 1: AWS Infrastructure (Required)**
- Deploys CDK stacks with Bedrock fallback mode
- System works immediately with Claude Sonnet 4.5
- No AgentCore dependencies

### **Step 2: AgentCore Agents (Optional)**
- Deploys AgentCore agents with persistent memory
- Creates AI agents for enhanced content generation
- Enables personalization capabilities

### **Step 3: AgentCore Integration (Optional)**
- Configures IAM permissions for AgentCore agents
- Updates Lambda environment variables with agent ARNs
- Enables seamless integration between infrastructure and AI agents

## Prerequisites

- AWS Account with CLI configured
- Python 3.12+
- Node.js (for CDK)
- AgentCore CLI (for Steps 2-3)

## Step 1: Deploy AWS Infrastructure (3 minutes)

```bash
# Clone and setup
git clone <repository-url>
cd strava-ai-boost
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set AWS profile
export AWS_PROFILE=your-aws-profile

# Deploy AWS infrastructure (Step 1 ONLY)
./scripts/deploy.sh dev
```

**What this does:**
- ✅ Deploys AWS infrastructure (5 CDK stacks)
- ✅ Creates DynamoDB tables, Lambda functions, Step Functions
- ✅ Sets up secrets placeholders and IAM roles
- ✅ Configures system to work with Bedrock fallback mode
- ✅ **System is immediately functional!**

## Step 2: Deploy AgentCore Agents (2 minutes) - Optional

```bash
# Deploy AgentCore agents with memory
./scripts/deploy_agentcore_agents.sh
```

**What this does:**
- ✅ Creates 2 AgentCore agents (`content_gen`, `campus_coach`)
- ✅ Sets up AgentCore Memory for personalization (`campus_coach_mem-Ns`)
- ✅ Uses `direct_code_deploy` (no Docker containers required)
- ✅ Validates agent deployment and memory creation

## Step 3: Configure AgentCore Integration (1 minute) - Optional

```bash
# Configure IAM permissions and Lambda integration
./scripts/configure_agentcore_integration.sh
```

**What this does:**
- ✅ Creates dynamic IAM permissions for AgentCore agents
- ✅ **Updates all 10 Lambda functions** with agent ARNs via AWS API
- ✅ Updates CDK context with agent information
- ✅ Creates `.env.agentcore` file for local development
- ✅ **No CDK redeploy needed - changes are immediately active**

## Configure Strava Integration (2 minutes)

### Step 1: Create Strava App
1. Go to https://www.strava.com/settings/api
2. Click "Create App" and fill:
   - **Application Name**: "My Strava AI Boost"
   - **Website**: http://localhost:3000
   - **Authorization Callback Domain**: localhost
3. **Save your Client ID and Client Secret** (you'll need them next)

### Step 2: Store Credentials in AWS
```bash
# Replace YOUR_CLIENT_ID and YOUR_CLIENT_SECRET with actual values
aws secretsmanager put-secret-value \
  --secret-id strava-ai-boost-app-config \
  --secret-string '{"client_id":"YOUR_CLIENT_ID","client_secret":"YOUR_CLIENT_SECRET"}' \
  --profile your-aws-profile
```

### Step 3: Start Local Interface
```bash
./local_interface/start_dashboard.sh
```

**What this script does:**
- ✅ Configures AWS profile (`your-aws-profile`) automatically
- ✅ Verifies AWS credentials before starting
- ✅ Sets Flask development environment
- ✅ Starts dashboard on http://localhost:3000

Open http://localhost:3000 in your browser.

### Step 4: Connect via Web Interface
1. Open http://localhost:3000
2. Click "Connect with Strava"
3. Authorize the application

### Step 5: Configure Your Preferences (Optional but Recommended) 🎨
1. Go to http://localhost:3000/preferences
2. Configure your personal profile:
   - **Age Range**: Adapts tone and cultural references
   - **Sport Approach**: health & wellness, performance & competition, social & fun, etc.
   - **Content Length**: short, medium, detailed, or adaptive
   - **Content Tone**: technical, motivational, casual, humorous, or authentic
   - **Emoji Usage**: none, minimal, moderate, or enthusiastic
   - **Technical Detail**: basic, intermediate, or advanced
   - **Interests**: Select from technology, music, travel, food, nature, photography, family, competition
3. Click "Save Preferences"
4. AI will now generate content tailored to your personality and preferences!

**Why configure preferences?**
- ✅ Content adapts to your age and life context
- ✅ Tone matches your personality (fun, technical, motivational, etc.)
- ✅ Subtle cultural references based on your interests
- ✅ Technical detail level matches your preference
- ✅ Emoji usage respects your style

### Step 6: Configure Webhook (Required - for real-time processing)
```bash
# Configure webhook subscription (tells Strava to notify us of new activities automatically)
./scripts/configure_strava_webhook.sh dev --auto-configure
```

**What this does:**
- ✅ Creates Strava webhook subscription for automatic activity notifications
- ✅ Automatically replaces any existing webhook with updated URL
- ✅ Enables real-time processing when you upload new activities to Strava
- ✅ **Required for the system to work automatically** - without this, activities won't be processed

## Test Your System (30 seconds)

Upload a new activity to Strava and watch it get enhanced automatically!

## System Architecture

Your deployed system includes:

### 🤖 Phase 1: Bedrock Fallback (Always Available)
- **Direct AI**: Claude Sonnet 4.5 integration
- **Smart Prompts**: Enhanced prompts with module insights
- **Reliability**: 99.9% availability, automatic operation
- **Performance**: 0.75-0.90 confidence scores

### ⚡ Phase 2: AgentCore Enhancement (Optional)
- **Content Generation Agent**: Personalized AI with persistent memory
- **Campus Coach Agent**: Automated session extraction (optional module)
- **AgentCore Memory**: Learns your writing style and avoids repetition
- **Performance**: 95% availability, 0.85-0.95 confidence scores

> **💡 How it works**: Phase 1 gives you a fully functional system immediately. Phase 2 adds enhanced personalization while maintaining the same reliability through automatic fallback.

## Deployment Architecture Benefits

### **✅ No Circular Dependencies**
- CDK deploys independently of AgentCore
- Lambda functions work with empty AgentCore variables
- Clean separation of infrastructure and AI agents

### **✅ Always Functional**
- System works immediately after Phase 1
- Phase 2 failure doesn't break the system
- Automatic fallback ensures reliability

### **✅ Easy Troubleshooting**
- Clear separation between infrastructure and enhancement
- Independent deployment phases
- Isolated failure domains

## Quick Troubleshooting

### If Phase 1 (CDK) deployment fails:
```bash
# Check CloudFormation console for detailed errors
# Ensure no resource conflicts exist
# Verify AWS credentials and permissions
```

### If Phase 2 (AgentCore) deployment fails:
```bash
# System still works with Bedrock fallback - no problem!
# You can retry AgentCore deployment later:
./scripts/deploy_agentcore_agents.sh
```

### If webhook isn't working:
```bash
# Check webhook configuration
./scripts/configure_strava_webhook.sh dev --check-status

# Reconfigure if needed
./scripts/configure_strava_webhook.sh dev --auto-configure
```

### Check system health:
```bash
# Validate everything is working
./scripts/validate_strava_setup.sh dev --detailed
```

## Alternative: Manual Phase-by-Phase Deployment

For more control, you can run each phase manually:

### Phase 1: CDK Infrastructure Only
```bash
# Bootstrap CDK (first time only)
cdk bootstrap --profile your-aws-profile

# Deploy CDK infrastructure
cdk deploy --all --profile your-aws-profile --require-approval never
```

### Phase 2: AgentCore Enhancement Only
```bash
# Deploy AgentCore agents and update Lambda environment variables
./scripts/deploy_agentcore_agents.sh
```

## Next Steps

- **Enable Modules**: [Configuration Guide](../user-guide/CONFIGURATION.md)
- **Customize Settings**: [Dashboard Guide](../user-guide/DASHBOARD.md)
- **Troubleshooting**: [Troubleshooting Guide](../user-guide/TROUBLESHOOTING.md)

## Need Help?

- **Common Issues**: [Troubleshooting Guide](../user-guide/TROUBLESHOOTING.md)
- **Full Setup**: [Complete Setup Guide](COMPLETE-SETUP.md)
- **Technical Details**: [Architecture](../reference/ARCHITECTURE.md)