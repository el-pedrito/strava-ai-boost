# 🚀 Quick Start Guide

**Get Strava AI Boost running in 5 minutes!**

This guide gets you up and running quickly with the **complete system** including AgentCore agents for enhanced personalization.

## Prerequisites

- AWS Account with CLI configured
- Python 3.12+
- Node.js (for CDK)

## 1. Deploy Complete System (3 minutes)

```bash
# Clone and setup
git clone <repository-url>
cd strava-ai-boost
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set AWS profile
export AWS_PROFILE=your-aws-profile

# Deploy everything (CDK + AgentCore agents)
./scripts/deploy.sh dev
```

**What this does:**
- ✅ Deploys AWS infrastructure (CDK stacks)
- ✅ Creates AgentCore agents with memory for personalization
- ✅ Sets up all permissions and configurations
- ✅ Creates secrets placeholders
- ✅ Configures dual-mode content generation

## 2. Start Local Interface (30 seconds)

```bash
cd local_interface
AWS_PROFILE=your-aws-profile python app.py
```

Open http://localhost:3000 in your browser.

## 3. Configure Strava Integration (2 minutes)

### Step 3a: Create Strava App
1. Go to https://www.strava.com/settings/api
2. Click "Create App" and fill:
   - **Application Name**: "My Strava AI Boost"
   - **Website**: http://localhost:3000
   - **Authorization Callback Domain**: localhost
3. **Save your Client ID and Client Secret** (you'll need them next)

### Step 3b: Store Credentials in AWS
```bash
# Replace YOUR_CLIENT_ID and YOUR_CLIENT_SECRET with actual values
aws secretsmanager put-secret-value \
  --secret-id strava-ai-boost-app-config \
  --secret-string '{"client_id":"YOUR_CLIENT_ID","client_secret":"YOUR_CLIENT_SECRET"}' \
  --profile your-aws-profile
```

### Step 3c: Connect via Web Interface
1. Open http://localhost:3000
2. Click "Connect with Strava"
3. Authorize the application

### Step 3d: Configure Webhook (Optional - for real-time processing)
```bash
# Configure webhook subscription (tells Strava to notify us of new activities)
./scripts/configure_strava_webhook.sh dev --auto-configure
```

## 4. Test Your System (30 seconds)

Upload a new activity to Strava and watch it get enhanced automatically!

## System Architecture

Your deployed system includes:

### 🤖 AgentCore Integration (Enhanced Mode)
- **Content Generation Agent**: Personalized AI with persistent memory
- **Campus Coach Agent**: Automated session extraction (optional module)
- **AgentCore Memory**: Learns your writing style and avoids repetition
- **Performance**: 95% availability, 0.85-0.95 confidence scores

### ⚡ Bedrock Fallback (Always Available)
- **Direct AI**: Claude Sonnet 4.5 integration
- **Smart Prompts**: Enhanced prompts with module insights
- **Reliability**: 99.9% availability, automatic fallback
- **Performance**: 0.75-0.90 confidence scores

> **💡 How it works**: The system automatically uses AgentCore agents when available, with seamless fallback to direct AI. You get personalized, high-quality content either way!

## Quick Troubleshooting

### If AgentCore deployment fails:
```bash
# System still works with direct AI - no problem!
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

## Next Steps

- **Enable Modules**: [Configuration Guide](../user-guide/CONFIGURATION.md)
- **Customize Settings**: [Dashboard Guide](../user-guide/DASHBOARD.md)
- **Troubleshooting**: [Troubleshooting Guide](../user-guide/TROUBLESHOOTING.md)

## Need Help?

- **Common Issues**: [Troubleshooting Guide](../user-guide/TROUBLESHOOTING.md)
- **Full Setup**: [Complete Setup Guide](COMPLETE-SETUP.md)
- **Technical Details**: [Architecture](../reference/ARCHITECTURE.md)