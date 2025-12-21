#!/bin/bash

# Deploy AgentCore Infrastructure for Strava AI Boost
# This script deploys AgentCore agents and memory using CLI commands
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./deploy_agentcore.sh
#
# Or set profile inline:
#   AWS_PROFILE=your-aws-profile ./deploy_agentcore.sh

set -e

echo "🚀 Deploying AgentCore infrastructure for Strava AI Boost..."

# Configuration
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
MEMORY_NAME="strava-ai-boost-memory"
CONTENT_AGENT_NAME="strava-ai-boost-content-generator"
CAMPUS_COACH_AGENT_NAME="strava-ai-boost-campus-coach-scraper"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if AgentCore CLI is installed
if ! command -v agentcore &> /dev/null; then
    print_error "AgentCore CLI not found. Please install AgentCore CLI first."
    exit 1
fi

# Configure AgentCore
print_status "Configuring AgentCore for region $REGION..."
agentcore configure --region $REGION --profile $PROFILE

# Deploy AgentCore Memory
print_status "Creating AgentCore Memory: $MEMORY_NAME..."
if agentcore memory create \
    --name $MEMORY_NAME \
    --description "Personal style and expression memory for Strava AI Boost" \
    --profile $PROFILE; then
    print_status "AgentCore Memory created successfully"
else
    print_warning "AgentCore Memory may already exist or creation failed"
fi

# Deploy Content Generation Agent
print_status "Deploying Content Generation Agent: $CONTENT_AGENT_NAME..."
if agentcore agent deploy \
    --name $CONTENT_AGENT_NAME \
    --runtime python \
    --memory $MEMORY_NAME \
    --file src/agents/content_generation_agent.py \
    --profile $PROFILE; then
    print_status "Content Generation Agent deployed successfully"
else
    print_error "Failed to deploy Content Generation Agent"
    exit 1
fi

# Deploy Campus Coach Browser Agent
print_status "Deploying Campus Coach Browser Agent: $CAMPUS_COACH_AGENT_NAME..."
if agentcore agent deploy \
    --name $CAMPUS_COACH_AGENT_NAME \
    --runtime browser \
    --file src/agents/campus_coach_agent.py \
    --profile $PROFILE; then
    print_status "Campus Coach Browser Agent deployed successfully"
else
    print_error "Failed to deploy Campus Coach Browser Agent"
    exit 1
fi

# Verify deployments
print_status "Verifying AgentCore deployments..."

echo ""
echo "📋 AgentCore Memory Status:"
agentcore memory list --profile $PROFILE | grep $MEMORY_NAME || print_warning "Memory not found in list"

echo ""
echo "📋 AgentCore Agents Status:"
agentcore agent list --profile $PROFILE | grep -E "($CONTENT_AGENT_NAME|$CAMPUS_COACH_AGENT_NAME)" || print_warning "Agents not found in list"

echo ""
print_status "✅ AgentCore deployment complete!"
print_status "Memory: $MEMORY_NAME"
print_status "Content Agent: $CONTENT_AGENT_NAME"
print_status "Campus Coach Agent: $CAMPUS_COACH_AGENT_NAME"

echo ""
print_warning "Note: Campus Coach Browser Agent has known cold start issues (~30% first-try success rate)"
print_warning "Retry logic is implemented in the Lambda invoker functions"

echo ""
print_status "🎯 Next steps:"
echo "1. Deploy CDK stacks: cdk deploy --all --profile \$PROFILE"
echo "2. Configure Strava OAuth in local web interface"
echo "3. Enable Campus Coach module with credentials"