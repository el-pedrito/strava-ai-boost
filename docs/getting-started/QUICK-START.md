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
python app.py
```

Open http://localhost:3000 in your browser.

## 3. Connect Strava (2 minutes)

1. **Create Strava App**: Go to https://www.strava.com/settings/api
   - Application Name: "My Strava AI Boost"
   - Website: http://localhost:3000
   - Authorization Callback Domain: localhost

2. **Configure in Interface**:
   - Click "Configure Strava App" in the web interface
   - Enter your Client ID and Client Secret
   - Click "Connect with Strava"
   - Authorize the application

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