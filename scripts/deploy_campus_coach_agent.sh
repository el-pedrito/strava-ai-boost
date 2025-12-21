#!/bin/bash

# Deploy Campus Coach Agent for Strava AI Boost
# Deploys AgentCore Browser Tool agent for automated Campus Coach session extraction
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./deploy_campus_coach_agent.sh

set -e

echo "🏃 Deploying Campus Coach Agent for Strava AI Boost..."

# Configuration
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
AGENT_NAME="strava-ai-boost-campus-coach-scraper"
AGENT_FILE="src/agents/campus_coach_agent.py"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if agent file exists
if [ ! -f "$AGENT_FILE" ]; then
    print_error "Agent file not found: $AGENT_FILE"
    print_error "Please ensure the Campus Coach agent is implemented"
    exit 1
fi

# Check if agent already exists
print_status "Checking if Campus Coach agent exists..."
if agentcore agent list --profile $PROFILE | grep -q $AGENT_NAME; then
    print_warning "Agent $AGENT_NAME already exists"
    read -p "Do you want to redeploy? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Deployment cancelled"
        exit 0
    fi
    
    print_status "Removing existing agent..."
    agentcore agent delete --name $AGENT_NAME --profile $PROFILE || print_warning "Could not delete existing agent"
fi

# Deploy Campus Coach Browser Agent
print_status "Deploying Campus Coach Browser Agent: $AGENT_NAME..."
print_status "Using AgentCore Browser Tool runtime for web scraping..."

if agentcore agent deploy \
    --name $AGENT_NAME \
    --runtime browser \
    --file $AGENT_FILE \
    --description "Campus Coach session extraction agent using Browser Tool" \
    --profile $PROFILE; then
    print_status "Campus Coach Browser Agent deployed successfully"
else
    print_error "Failed to deploy Campus Coach Browser Agent"
    exit 1
fi

# Test agent deployment
print_status "Testing agent deployment..."
if agentcore agent describe --name $AGENT_NAME --profile $PROFILE > /dev/null 2>&1; then
    print_status "Agent deployment verified"
else
    print_warning "Could not verify agent deployment"
fi

# Display agent information
echo ""
print_status "📋 Campus Coach Agent Information:"
agentcore agent describe --name $AGENT_NAME --profile $PROFILE || print_warning "Could not retrieve agent details"

echo ""
print_status "✅ Campus Coach Agent deployment complete!"
print_status "Agent Name: $AGENT_NAME"
print_status "Runtime: AgentCore Browser Tool"
print_status "Region: $REGION"

echo ""
print_warning "⚠️  Known Issues:"
print_warning "- Cold start problem: ~30% first-try success rate"
print_warning "- Retry logic implemented in Lambda invoker"
print_warning "- Browser automation may require warm-up time"

echo ""
print_status "🎯 Agent capabilities:"
echo "  - Automated Campus Coach login"
echo "  - Weekly training session extraction"
echo "  - Session data parsing and storage"
echo "  - Secure credential management"

echo ""
print_status "📝 Next steps:"
echo "1. Configure Campus Coach credentials in local web interface"
echo "2. Test agent invocation through Lambda function"
echo "3. Monitor agent logs for successful extractions"