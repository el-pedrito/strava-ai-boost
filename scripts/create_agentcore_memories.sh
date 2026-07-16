#!/bin/bash

# Create AgentCore Long-Term Memories for Strava AI Boost
# This script creates LTM memories with semantic search strategy
# Run this BEFORE deploying agents

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
AWS_PROFILE="${AWS_PROFILE:-your-aws-profile}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Memory names (must match agent names + "_mem")
CONTENT_MEMORY_NAME="content_gen_mem"

# Cost allocation tags
TAGS_PROJECT="StravaAIBoost"
TAGS_ENVIRONMENT="${ENVIRONMENT:-dev}"
TAGS_OWNER="${OWNER_TAG:-admin}"
TAGS_COST_CENTER="strava-ai-boost"
TAGS_MANAGED_BY="AgentCore-CLI"

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to tag an AgentCore resource via boto3
tag_agentcore_resource() {
    local resource_arn="$1"
    local resource_label="$2"

    print_status "Tagging $resource_label..."

    python3 << EOF
import boto3
client = boto3.client('bedrock-agentcore-control', region_name='$AWS_REGION')
try:
    client.tag_resource(
        resourceArn='$resource_arn',
        tags={
            'Project': '$TAGS_PROJECT',
            'Environment': '$TAGS_ENVIRONMENT',
            'Owner': '$TAGS_OWNER',
            'CostCenter': '$TAGS_COST_CENTER',
            'ManagedBy': '$TAGS_MANAGED_BY',
        }
    )
    print('Tagged $resource_label')
except Exception as e:
    print(f'Failed to tag $resource_label: {e}')
EOF
}

# Function to tag memories after creation
tag_memories() {
    print_status "Applying cost allocation tags to memories..."

    python3 << EOF
import boto3
client = boto3.client('bedrock-agentcore-control', region_name='$AWS_REGION')
tags = {
    'Project': '$TAGS_PROJECT',
    'Environment': '$TAGS_ENVIRONMENT',
    'Owner': '$TAGS_OWNER',
    'CostCenter': '$TAGS_COST_CENTER',
    'ManagedBy': '$TAGS_MANAGED_BY',
}
memories = client.list_memories().get('memories', [])
for mem in memories:
    arn = mem.get('memoryArn', mem.get('arn', ''))
    name = arn.split('/')[-1] if arn else 'unknown'
    try:
        client.tag_resource(resourceArn=arn, tags=tags)
        print(f'  Tagged memory: {name}')
    except Exception as e:
        print(f'  Failed to tag {name}: {e}')
EOF
}

# Function to create LTM memory with semantic search
create_ltm_memory() {
    local memory_name="$1"
    
    print_status "Creating LTM memory: $memory_name..."
    
    # Check if memory already exists
    local existing_memory=$(agentcore memory list --region "$AWS_REGION" 2>/dev/null | grep "$memory_name" || echo "")
    
    if [ -n "$existing_memory" ]; then
        print_warning "Memory $memory_name already exists, skipping creation"
        
        # Check if it's ACTIVE
        local memory_status=$(agentcore memory list --region "$AWS_REGION" 2>/dev/null | grep "$memory_name" | awk '{print $2}' || echo "")
        if [ "$memory_status" = "ACTIVE" ]; then
            print_success "Memory $memory_name is ACTIVE and ready"
        else
            print_warning "Memory $memory_name status: $memory_status (may still be creating)"
        fi
        return 0
    fi
    
    # Create LTM memory with semantic search strategy (without --wait to avoid timeout)
    print_status "Creating memory with semantic search strategy (365-day retention)..."
    print_status "⏳ This process takes ~2 minutes and runs in the background..."
    
    agentcore memory create "$memory_name" \
        --description "LTM for Strava AI Boost: style, performance, preferences" \
        --event-expiry-days 365 \
        --strategies '[{"semanticMemoryStrategy":{"name":"ComprehensiveLearning"}}]' \
        --region "$AWS_REGION" || {
        print_error "Failed to initiate memory creation for $memory_name"
        return 1
    }
    
    print_success "Memory $memory_name creation initiated (processing in background)"
    
    return 0
}

# Main execution
main() {
    print_status "🧠 Creating AgentCore Long-Term Memories for Strava AI Boost..."
    
    # Set AWS profile
    export AWS_PROFILE="$AWS_PROFILE"
    export AWS_DEFAULT_REGION="$AWS_REGION"
    
    # Check AgentCore CLI
    if ! command -v agentcore &> /dev/null; then
        print_error "AgentCore CLI not found. Please install it first."
        print_status "Installation: pip install bedrock-agentcore-starter-toolkit"
        exit 1
    fi
    
    print_success "AgentCore CLI is available"
    
    # Create memories
    print_status "📦 Creating LTM memories with semantic search..."
    
    create_ltm_memory "$CONTENT_MEMORY_NAME"

    # Tag memories with cost allocation tags
    tag_memories

    # List all memories
    print_status ""
    print_status "📋 Memory Status:"
    agentcore memory list --region "$AWS_REGION"
    
    print_success ""
    print_success "🎉 LTM memory creation initiated!"
    print_status ""
    print_status "⏳ IMPORTANT: Memory creation takes ~2 minutes to complete."
    print_status "   The memories are being created in the background on AWS."
    print_status ""
    print_status "Memory Features:"
    print_status "  - Type: Long-Term Memory (LTM)"
    print_status "  - Strategy: Semantic search (ComprehensiveLearning)"
    print_status "  - Retention: 365 days"
    print_status "  - Purpose: Style learning, performance history, preferences"
    print_status ""
    print_status "📊 To check memory status:"
    print_status "  agentcore memory list --region $AWS_REGION"
    print_status ""
    print_status "  Wait until both memories show status 'ACTIVE' before deploying agents."
    print_status ""
    print_status "Next Step (after memories are ACTIVE):"
    print_status "  ./scripts/deploy_agentcore_agents.sh"
}

# Run main function
main "$@"
