#!/bin/bash

# Strava AI Boost - Local Dashboard Startup Script
# This script configures the AWS profile and starts the Flask development server

echo "🚀 Starting Strava AI Boost Local Dashboard..."

# Configure AWS Profile
export AWS_PROFILE=your-aws-profile
export AWS_REGION=eu-west-1
export AWS_DEFAULT_REGION=eu-west-1

# Verify AWS credentials
echo "🔐 Verifying AWS credentials..."
aws sts get-caller-identity --profile $AWS_PROFILE > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "❌ AWS credentials not configured properly for profile: $AWS_PROFILE"
    echo "Please run: aws configure --profile $AWS_PROFILE"
    exit 1
fi

echo "✅ AWS credentials verified for profile: $AWS_PROFILE"

# Set Flask environment variables
export FLASK_ENV=development
export FLASK_DEBUG=1

# Start the Flask application
echo "🌐 Starting Flask development server on http://localhost:3000"
echo "📊 Dashboard will be available at: http://localhost:3000"
echo "⚙️  Configuration page: http://localhost:3000/config"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

cd "$(dirname "$0")"
python3 app.py