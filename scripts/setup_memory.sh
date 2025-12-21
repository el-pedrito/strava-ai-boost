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

# Check if memory exists
print_status "Checking if AgentCore Memory exists..."
if agentcore memory list --profile $PROFILE | grep -q $MEMORY_NAME; then
    print_status "Memory $MEMORY_NAME already exists"
else
    print_status "Creating AgentCore Memory: $MEMORY_NAME..."
    agentcore memory create \
        --name $MEMORY_NAME \
        --description "Personal style and expression memory for Strava AI Boost" \
        --profile $PROFILE
    
    if [ $? -eq 0 ]; then
        print_status "Memory created successfully"
    else
        print_error "Failed to create memory"
        exit 1
    fi
fi

# Configure memory settings
print_status "Configuring memory settings..."

# TODO: Add memory configuration commands when AgentCore CLI supports it
# Example:
# agentcore memory configure \
#     --name $MEMORY_NAME \
#     --retention-days 365 \
#     --max-entries 10000 \
#     --profile $PROFILE

print_status "Memory configuration complete"

# Display memory information
echo ""
print_status "📋 Memory Information:"
agentcore memory describe --name $MEMORY_NAME --profile $PROFILE || print_warning "Could not retrieve memory details"

echo ""
print_status "✅ AgentCore Memory setup complete!"
print_status "Memory Name: $MEMORY_NAME"
print_status "Region: $REGION"

echo ""
print_status "🎯 Memory will be used for:"
echo "  - Personal style learning and storage"
echo "  - Expression tracking to avoid repetition"
echo "  - Performance pattern memory for context"
echo "  - Module preference storage"