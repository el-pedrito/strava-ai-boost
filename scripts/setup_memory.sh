#!/bin/bash

# Setup AgentCore Memory for Strava AI Boost
# Configures memory service for personal style storage and expression tracking
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./setup_memory.sh

set -e

echo "🧠 Setting up AgentCore Memory for Strava AI Boost..."

# Configuration
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
MEMORY_NAME="strava-ai-boost-memory"

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
    print_error "Please configure your AWS profile first:"
    print_error "  aws configure --profile $PROFILE"
    exit 1
fi

# Configure AgentCore for the region and profile
print_status "Configuring AgentCore CLI..."
agentcore configure --region $REGION --profile $PROFILE

if [ $? -ne 0 ]; then
    print_error "Failed to configure AgentCore CLI"
    exit 1
fi

# Check if memory exists
print_status "Checking if AgentCore Memory exists..."
if agentcore memory list --profile $PROFILE 2>/dev/null | grep -q $MEMORY_NAME; then
    print_status "Memory $MEMORY_NAME already exists"
    
    # Get existing memory details
    print_status "Retrieving existing memory details..."
    agentcore memory describe --name $MEMORY_NAME --profile $PROFILE
else
    print_status "Creating AgentCore Memory: $MEMORY_NAME..."
    
    # Create memory with LTM (Long Term Memory) strategy for personalization
    agentcore memory create \
        --name $MEMORY_NAME \
        --description "Personal style and expression memory for Strava AI Boost content generation" \
        --ltm-strategy "semantic_search" \
        --profile $PROFILE \
        --region $REGION
    
    if [ $? -eq 0 ]; then
        print_status "Memory created successfully with semantic search LTM strategy"
    else
        print_error "Failed to create memory"
        print_error "Check AgentCore CLI installation and AWS permissions"
        exit 1
    fi
fi

# Configure memory settings for personalization
print_status "Configuring memory for personalization..."

# Set memory configuration for content generation use case
agentcore memory configure \
    --name $MEMORY_NAME \
    --max-memory-size 1000 \
    --memory-decay-rate 0.1 \
    --profile $PROFILE \
    --region $REGION

if [ $? -eq 0 ]; then
    print_status "Memory configuration updated for personalization"
else
    print_warning "Memory configuration update failed (may not be supported in current version)"
fi

# Display memory information
echo ""
print_status "📋 Memory Information:"
agentcore memory describe --name $MEMORY_NAME --profile $PROFILE || print_warning "Could not retrieve memory details"

# Test memory connectivity
print_status "Testing memory connectivity..."
if agentcore memory test --name $MEMORY_NAME --profile $PROFILE 2>/dev/null; then
    print_status "Memory connectivity test passed"
else
    print_warning "Memory connectivity test failed or not supported"
fi

echo ""
print_status "✅ AgentCore Memory setup complete!"
print_status "Memory Name: $MEMORY_NAME"
print_status "Region: $REGION"
print_status "Profile: $PROFILE"
print_status "LTM Strategy: semantic_search"

echo ""
print_status "🎯 Memory will be used for:"
echo "  - Personal style learning and storage"
echo "  - Expression tracking to avoid repetition"
echo "  - Performance pattern memory for context"
echo "  - Module preference storage"
echo "  - Semantic search for relevant past activities"

echo ""
print_status "📝 Next steps:"
echo "1. Deploy content generation agent with memory integration"
echo "2. Test memory storage and retrieval in Lambda functions"
echo "3. Monitor memory usage and performance"

# Set environment variable for other scripts
export AGENTCORE_MEMORY_NAME=$MEMORY_NAME
print_status "Environment variable AGENTCORE_MEMORY_NAME set to: $MEMORY_NAME"