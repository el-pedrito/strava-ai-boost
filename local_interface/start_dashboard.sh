#!/bin/bash

# Start Strava AI Boost Local Dashboard
# Automatically configures AWS profile and starts Flask application

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting Strava AI Boost Dashboard...${NC}"

# Set AWS profile
export AWS_PROFILE=your-aws-profile
export AWS_DEFAULT_REGION=eu-west-1

# Verify AWS credentials
echo -e "${BLUE}🔍 Verifying AWS credentials...${NC}"
if ! aws sts get-caller-identity --profile $AWS_PROFILE > /dev/null 2>&1; then
    echo "❌ AWS credentials not configured for profile: $AWS_PROFILE"
    echo "Please configure your AWS credentials first"
    exit 1
fi

echo -e "${GREEN}✅ AWS credentials verified${NC}"

# Set Flask environment
export FLASK_ENV=development
export FLASK_DEBUG=1

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Start Flask application
echo -e "${BLUE}🌐 Starting Flask application on http://localhost:3000${NC}"
echo -e "${GREEN}✅ Dashboard will be available at: http://localhost:3000${NC}"
echo ""
echo "Press CTRL+C to stop the server"
echo ""

cd "$SCRIPT_DIR"
python3 app.py
