# 🚀 Quick Start Guide

**Get Strava AI Boost running in 5 minutes!**

This guide gets you up and running quickly. After deployment, follow the [First Activity Guide](FIRST-STEPS.md) to enhance your first activity.

## Prerequisites

- AWS Account with CLI configured
- Python 3.12+
- Node.js (for CDK)

## 1. Deploy Infrastructure (2 minutes)

```bash
# Clone and setup
git clone <repository-url>
cd strava-ai-boost
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set AWS profile
export AWS_PROFILE=your-aws-profile

# Deploy
cdk bootstrap --profile your-aws-profile
cdk deploy --profile your-aws-profile
```

## 2. Start Local Interface (30 seconds)

```bash
cd local_interface
AWS_PROFILE=your-aws-profile python app.py
```

Open http://localhost:3000 in your browser.

## 3. Configure Strava Integration (3 minutes)

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

### Step 3c: Configure Webhook
```bash
# Configure webhook subscription (tells Strava to notify us of new activities)
# Script automatically retrieves credentials from Secrets Manager
./scripts/configure_strava_webhook.sh dev --auto-configure
```

### Step 3d: Connect via Web Interface
```bash
# OAuth flow (gives us permission to read/modify your activities)
```
1. Open http://localhost:3000
2. Click "Connect with Strava"
3. Authorize the application

> **💡 Why Both?** Webhook = "Tell me when activities happen", OAuth = "Let me access the activity data"

## 4. Test (30 seconds)

Upload a new activity to Strava and watch it get enhanced automatically!

## Next Steps

- **Enable Modules**: [Configuration Guide](../user-guide/CONFIGURATION.md)
- **Customize Settings**: [Dashboard Guide](../user-guide/DASHBOARD.md)
- **Troubleshooting**: [Troubleshooting Guide](../user-guide/TROUBLESHOOTING.md)

## Need Help?

- **Common Issues**: [Troubleshooting Guide](../user-guide/TROUBLESHOOTING.md)
- **Full Setup**: [Complete Setup Guide](COMPLETE-SETUP.md)
- **Technical Details**: [Architecture](../reference/ARCHITECTURE.md)