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
AGENT_NAME="campuscoach"
AGENT_FILE="src/agents/campus_coach_agent.py"
MEMORY_NAME="${AGENTCORE_MEMORY_NAME:-strava-ai-boost-memory}"

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

# Validate AWS profile
print_status "Validating AWS profile: $PROFILE"
if ! aws sts get-caller-identity --profile $PROFILE > /dev/null 2>&1; then
    print_error "AWS profile '$PROFILE' not configured or invalid"
    exit 1
fi

# Configure AgentCore
print_status "Configuring AgentCore CLI..."
agentcore configure --region $REGION --profile $PROFILE

# Check if agent file exists
if [ ! -f "$AGENT_FILE" ]; then
    print_error "Agent file not found: $AGENT_FILE"
    print_error "Please ensure the Campus Coach agent is implemented"
    exit 1
fi

# Validate memory exists
print_status "Validating AgentCore Memory: $MEMORY_NAME"
if ! agentcore memory list --profile $PROFILE 2>/dev/null | grep -q $MEMORY_NAME; then
    print_warning "Memory $MEMORY_NAME not found"
    print_warning "Run ./setup_memory.sh first to create the memory"
    read -p "Continue without memory integration? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Deployment cancelled"
        exit 0
    fi
    MEMORY_NAME=""
fi

# Check if agent already exists
print_status "Checking if Campus Coach agent exists..."
if agentcore agent list --profile $PROFILE 2>/dev/null | grep -q $AGENT_NAME; then
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

# Prepare deployment command
DEPLOY_CMD="agentcore agent deploy \
    --name $AGENT_NAME \
    --runtime browser \
    --file $AGENT_FILE \
    --description \"Campus Coach session extraction agent using Browser Tool with retry logic\" \
    --profile $PROFILE \
    --region $REGION"

# Add memory integration if available
if [ -n "$MEMORY_NAME" ]; then
    DEPLOY_CMD="$DEPLOY_CMD --memory $MEMORY_NAME"
    print_status "Integrating with memory: $MEMORY_NAME"
fi

# Add environment variables for Lambda integration
DEPLOY_CMD="$DEPLOY_CMD \
    --env REGION=$REGION \
    --env PROFILE=$PROFILE \
    --env MEMORY_NAME=$MEMORY_NAME"

# Execute deployment
if eval $DEPLOY_CMD; then
    print_status "Campus Coach Browser Agent deployed successfully"
else
    print_error "Failed to deploy Campus Coach Browser Agent"
    print_error "Check AgentCore CLI installation and AWS permissions"
    exit 1
fi

# Test agent deployment
print_status "Testing agent deployment..."
if agentcore agent describe --name $AGENT_NAME --profile $PROFILE > /dev/null 2>&1; then
    print_status "Agent deployment verified"
else
    print_warning "Could not verify agent deployment"
fi

# Configure agent for retry logic (cold start mitigation)
print_status "Configuring agent for cold start retry logic..."
agentcore agent configure \
    --name $AGENT_NAME \
    --timeout 300 \
    --max-retries 3 \
    --retry-delay 5 \
    --profile $PROFILE \
    --region $REGION 2>/dev/null || print_warning "Agent configuration not supported in current version"

# Display agent information
echo ""
print_status "📋 Campus Coach Agent Information:"
agentcore agent describe --name $AGENT_NAME --profile $PROFILE || print_warning "Could not retrieve agent details"

echo ""
print_status "✅ Campus Coach Agent deployment complete!"
print_status "Agent Name: $AGENT_NAME"
print_status "Runtime: AgentCore Browser Tool"
print_status "Region: $REGION"
print_status "Profile: $PROFILE"
if [ -n "$MEMORY_NAME" ]; then
    print_status "Memory Integration: $MEMORY_NAME"
fi

echo ""
print_warning "⚠️  Known Issues & Mitigations:"
print_warning "- Cold start problem: ~30% first-try success rate"
print_warning "- Retry logic implemented in Lambda invoker (3 attempts)"
print_warning "- Exponential backoff: 2s, 4s, 8s delays"
print_warning "- Browser automation may require warm-up time"

echo ""
print_status "🎯 Agent capabilities:"
echo "  - Automated Campus Coach login with secure credential handling"
echo "  - Weekly training session extraction with intelligent parsing"
echo "  - Session data validation and storage in DynamoDB"
echo "  - Retry logic for reliability (handles cold starts)"
echo "  - Integration with Bedrock AI for session matching"

echo ""
print_status "📝 Next steps:"
echo "1. Configure Campus Coach credentials in AWS Secrets Manager"
echo "2. Test agent invocation through Lambda function"
echo "3. Monitor agent logs for successful extractions:"
echo "   aws logs tail /aws/bedrock-agentcore/runtimes/$AGENT_NAME-* --follow --profile $PROFILE --region $REGION"
echo "4. Verify session data storage in DynamoDB"

# Set environment variable for other scripts
export AGENTCORE_CAMPUS_COACH_AGENT=$AGENT_NAME
print_status "Environment variable AGENTCORE_CAMPUS_COACH_AGENT set to: $AGENT_NAME"