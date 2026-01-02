#!/bin/bash

# Deploy AgentCore Agents for Strava AI Boost with Long-Term Memory
# Prerequisites: Run scripts/create_agentcore_memories.sh first
# Uses direct_code_deploy (no Docker required)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
AWS_PROFILE="your-aws-profile"
AWS_REGION="eu-west-1"

# Agent and memory names
CONTENT_AGENT_NAME="content_gen"
CAMPUS_AGENT_NAME="campus_coach"
CONTENT_MEMORY_NAME="content_gen_mem"
CAMPUS_MEMORY_NAME="campus_coach_mem"

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

# Function to get memory ID from AWS
get_memory_id() {
    local memory_name="$1"
    
    # Use AgentCore Python toolkit to list memories and match by name
    local memory_id=$(python3 << EOF
from bedrock_agentcore_starter_toolkit.operations.memory.manager import MemoryManager

try:
    manager = MemoryManager(region_name='$AWS_REGION')
    memories = manager.list_memories()
    
    # List returns IDs, we need to check each one
    for memory in memories:
        mem_id = memory.get('id')
        if mem_id:
            # Get full memory details to check name
            try:
                mem_details = manager.get_memory(mem_id)
                if mem_details.get('name') == '$memory_name':
                    print(mem_id)
                    break
            except:
                continue
except Exception:
    pass
EOF
)
    
    # If toolkit doesn't work, try from YAML
    if [ -z "$memory_id" ] && [ -f ".bedrock_agentcore.yaml" ]; then
        memory_id=$(grep -B 2 "memory_name: ${memory_name}" .bedrock_agentcore.yaml | grep "memory_id:" | awk '{print $2}' | tr -d "'" || echo "")
        if [ "$memory_id" = "null" ]; then
            memory_id=""
        fi
    fi
    
    echo "$memory_id"
}

# Function to update YAML with LTM memory configuration
update_agent_memory_config() {
    local agent_name="$1"
    local memory_id="$2"
    local memory_name="$3"
    
    if [ -z "$memory_id" ]; then
        print_error "No memory ID provided for $agent_name"
        return 1
    fi
    
    print_status "📝 Configuring $agent_name to use LTM memory: $memory_id..."
    
    if [ ! -f ".bedrock_agentcore.yaml" ]; then
        print_error ".bedrock_agentcore.yaml not found!"
        return 1
    fi
    
    # Get memory ARN
    local memory_arn="arn:aws:bedrock-agentcore:${AWS_REGION}:*:memory/${memory_id}"
    
    # Update YAML using Python
    AGENT_NAME="$agent_name" MEMORY_ID="$memory_id" MEMORY_ARN="$memory_arn" MEMORY_NAME="$memory_name" python3 << 'EOF'
import yaml
import sys
import os

try:
    agent_name = os.environ['AGENT_NAME']
    memory_id = os.environ['MEMORY_ID']
    memory_arn = os.environ['MEMORY_ARN']
    memory_name = os.environ['MEMORY_NAME']
    
    with open('.bedrock_agentcore.yaml', 'r') as f:
        config = yaml.safe_load(f) or {}
    
    if 'agents' not in config or agent_name not in config['agents']:
        print(f"✗ Agent {agent_name} not found in YAML", file=sys.stderr)
        sys.exit(1)
    
    if 'memory' not in config['agents'][agent_name]:
        config['agents'][agent_name]['memory'] = {}
    
    # Set LTM configuration - use STM_AND_LTM mode (required by AgentCore)
    config['agents'][agent_name]['memory']['mode'] = 'STM_AND_LTM'
    config['agents'][agent_name]['memory']['memory_id'] = memory_id
    config['agents'][agent_name]['memory']['memory_arn'] = memory_arn
    config['agents'][agent_name]['memory']['memory_name'] = memory_name
    config['agents'][agent_name]['memory']['event_expiry_days'] = 365
    config['agents'][agent_name]['memory']['was_created_by_toolkit'] = False
    
    with open('.bedrock_agentcore.yaml', 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    print(f"✓ Updated {agent_name} to use LTM memory")
    sys.exit(0)
except Exception as e:
    print(f"✗ Failed to update YAML: {e}", file=sys.stderr)
    sys.exit(1)
EOF
    
    if [ $? -eq 0 ]; then
        print_success "Memory configuration updated for $agent_name"
    else
        print_error "Failed to update memory configuration"
        return 1
    fi
}

# Function to deploy an agent with LTM
deploy_agent_with_ltm() {
    local agent_name="$1"
    local agent_path="$2"
    local memory_name="$3"
    
    print_status "🚀 Deploying $agent_name with LTM..."
    
    if [ ! -f "$agent_path" ]; then
        print_error "Agent file not found: $agent_path"
        return 1
    fi
    
    # Get memory ID from AWS
    print_status "Looking up LTM memory: $memory_name..."
    local memory_id
    memory_id=$(get_memory_id "$memory_name")
    
    if [ -z "$memory_id" ]; then
        print_error "Memory $memory_name not found!"
        print_status "Please run: ./scripts/create_agentcore_memories.sh first"
        return 1
    fi
    
    print_success "Found LTM memory: $memory_id"
    
    # Configure agent WITHOUT auto-creating memory
    print_status "Configuring agent: $agent_name (with --disable-memory)"
    
    agentcore configure \
        --entrypoint "$agent_path" \
        --name "$agent_name" \
        --region "$AWS_REGION" \
        --requirements-file "src/agents/requirements.txt" \
        --deployment-type direct_code_deploy \
        --runtime PYTHON_3_12 \
        --disable-memory \
        --non-interactive || {
        print_error "Failed to configure $agent_name"
        return 1
    }
    
    # Update YAML to use LTM memory
    update_agent_memory_config "$agent_name" "$memory_id" "$memory_name" || {
        print_error "Failed to configure memory for $agent_name"
        return 1
    }
    
    # Launch agent with memory ID as environment variable
    print_status "Launching agent: $agent_name with memory ID: $memory_id..."
    
    # Get guardrail configuration from .env.agentcore
    GUARDRAIL_ENABLED=$(grep "^GUARDRAIL_ENABLED=" .env.agentcore 2>/dev/null | cut -d'=' -f2 || echo "false")
    GUARDRAIL_ID=$(grep "^GUARDRAIL_ID=" .env.agentcore 2>/dev/null | cut -d'=' -f2 || echo "")
    GUARDRAIL_VERSION=$(grep "^GUARDRAIL_VERSION=" .env.agentcore 2>/dev/null | cut -d'=' -f2 || echo "1")
    
    # Build environment variables
    ENV_VARS="BEDROCK_AGENTCORE_MEMORY_ID=$memory_id"
    
    if [ "$GUARDRAIL_ENABLED" = "true" ] && [ -n "$GUARDRAIL_ID" ]; then
        print_status "🛡️  Guardrails enabled: $GUARDRAIL_ID v$GUARDRAIL_VERSION"
        ENV_VARS="$ENV_VARS,GUARDRAIL_ENABLED=true,GUARDRAIL_ID=$GUARDRAIL_ID,GUARDRAIL_VERSION=$GUARDRAIL_VERSION"
    else
        print_status "⚠️  Guardrails not configured (GUARDRAIL_ENABLED=$GUARDRAIL_ENABLED)"
    fi
    
    agentcore launch \
        --agent "$agent_name" \
        --env "$ENV_VARS" \
        --auto-update-on-conflict || {
        print_error "Failed to launch $agent_name"
        return 1
    }
    
    print_success "$agent_name deployed successfully"
    
    # Get agent ARN
    local agent_arn=$(agentcore status --agent "$agent_name" --verbose 2>/dev/null | jq -r '.agent.arn // empty' 2>/dev/null || echo "")
    
    if [ -z "$agent_arn" ]; then
        agent_arn=$(grep "agent_arn:" .bedrock_agentcore.yaml | grep "$agent_name" -A 20 | grep "agent_arn:" | head -1 | awk '{print $2}' || echo "")
    fi
    
    if [ -n "$agent_arn" ]; then
        print_success "Agent ARN: $agent_arn"
        echo "$agent_arn"
    else
        print_warning "Could not determine agent ARN"
        echo ""
    fi
}

# Main execution
main() {
    print_status "🚀 Starting AgentCore agent deployment with LTM..."
    
    # Set AWS profile
    export AWS_PROFILE="$AWS_PROFILE"
    export AWS_DEFAULT_REGION="$AWS_REGION"
    
    # Check prerequisites
    check_agentcore_cli
    
    # Auto-configure guardrails if Security Stack is deployed
    print_status ""
    print_status "🛡️  Checking for Bedrock Guardrails..."
    configure_guardrails_if_available
    
    # Verify memories exist
    print_status ""
    print_status "🔍 Verifying LTM memories exist..."
    
    local content_mem_id=$(get_memory_id "$CONTENT_MEMORY_NAME")
    local campus_mem_id=$(get_memory_id "$CAMPUS_MEMORY_NAME")
    
    if [ -z "$content_mem_id" ] || [ -z "$campus_mem_id" ]; then
        print_error "LTM memories not found!"
        print_status "Please run: ./scripts/create_agentcore_memories.sh first"
        print_status ""
        print_status "Then wait ~2 minutes for memories to become ACTIVE"
        print_status "Check status with: agentcore memory list --region $AWS_REGION"
        exit 1
    fi
    
    print_success "Found LTM memories:"
    print_status "  - $CONTENT_MEMORY_NAME: $content_mem_id"
    print_status "  - $CAMPUS_MEMORY_NAME: $campus_mem_id"
    
    # Deploy agents
    print_status ""
    print_status "📦 Deploying agents with LTM..."
    
    local content_arn=""
    local campus_arn=""
    
    # Deploy content generation agent
    if content_arn=$(deploy_agent_with_ltm "$CONTENT_AGENT_NAME" "src/agents/content_agent.py" "$CONTENT_MEMORY_NAME"); then
        print_success "✅ Content Generation Agent deployed"
    else
        print_error "❌ Content Generation Agent deployment failed"
        exit 1
    fi
    
    # Deploy campus coach agent
    if campus_arn=$(deploy_agent_with_ltm "$CAMPUS_AGENT_NAME" "src/agents/campus_coach_agent.py" "$CAMPUS_MEMORY_NAME"); then
        print_success "✅ Campus Coach Agent deployed"
    else
        print_error "❌ Campus Coach Agent deployment failed"
        exit 1
    fi
    
    # Summary
    print_success ""
    print_success "🎉 AgentCore agents deployed successfully with LTM!"
    print_status ""
    print_status "📋 Deployment Summary:"
    print_status "  Memory Type: Long-Term Memory (LTM) with semantic search"
    print_status "  Memory Retention: 365 days"
    print_status "  Content Agent: $content_arn"
    print_status "  Campus Agent: $campus_arn"
    print_status ""
    print_status "🧠 Memory Features:"
    print_status "  - Semantic search for style patterns"
    print_status "  - Long-term learning across activities"
    print_status "  - Persistent user personalization"
    print_status ""
    print_status "🔧 Next Step:"
    print_status "  Configure Lambda integration:"
    print_status "  ./scripts/configure_agentcore_integration.sh"
}

# Function to check AgentCore CLI availability
check_agentcore_cli() {
    print_status "🔍 Checking AgentCore CLI availability..."
    
    if ! command -v agentcore &> /dev/null; then
        print_error "AgentCore CLI not found. Please install it first."
        print_status "Installation: pip install bedrock-agentcore-starter-toolkit"
        exit 1
    fi
    
    print_success "AgentCore CLI is available"
}

# Function to auto-configure guardrails from CloudFormation
configure_guardrails_if_available() {
    local stack_name="StravaAIBoost-Security"
    local env_file=".env.agentcore"
    
    # Check if Security Stack is deployed
    if ! aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --profile "$AWS_PROFILE" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text &>/dev/null; then
        
        print_warning "Security Stack not deployed - guardrails disabled"
        print_status "To enable guardrails: cdk deploy StravaAIBoost-Security --profile $AWS_PROFILE"
        
        # Ensure guardrails are disabled in .env.agentcore
        if [ -f "$env_file" ]; then
            if grep -q "^GUARDRAIL_ENABLED=" "$env_file"; then
                sed -i.tmp "s|^GUARDRAIL_ENABLED=.*|GUARDRAIL_ENABLED=false|" "$env_file"
                rm -f "${env_file}.tmp"
            fi
        fi
        return 0
    fi
    
    # Get guardrail ID from CloudFormation
    local guardrail_id=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --profile "$AWS_PROFILE" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`GuardrailId`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    local guardrail_version=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --profile "$AWS_PROFILE" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`GuardrailVersion`].OutputValue' \
        --output text 2>/dev/null || echo "1")
    
    if [ -z "$guardrail_id" ]; then
        print_warning "Guardrail ID not found in Security Stack outputs"
        return 0
    fi
    
    print_success "Found Bedrock Guardrail: $guardrail_id v$guardrail_version"
    
    # Update .env.agentcore automatically
    if [ -f "$env_file" ]; then
        print_status "📝 Updating $env_file with guardrail configuration..."
        
        # Backup
        cp "$env_file" "${env_file}.backup.$(date +%s)"
        
        # Update or add guardrail configuration
        if grep -q "^GUARDRAIL_ENABLED=" "$env_file"; then
            sed -i.tmp "s|^GUARDRAIL_ENABLED=.*|GUARDRAIL_ENABLED=true|" "$env_file"
            sed -i.tmp "s|^GUARDRAIL_ID=.*|GUARDRAIL_ID=$guardrail_id|" "$env_file"
            sed -i.tmp "s|^GUARDRAIL_VERSION=.*|GUARDRAIL_VERSION=$guardrail_version|" "$env_file"
            rm -f "${env_file}.tmp"
        else
            # Add guardrail section
            cat >> "$env_file" << EOF

# ============================================================================
# SECURITY - BEDROCK GUARDRAILS
# ============================================================================
GUARDRAIL_ENABLED=true
GUARDRAIL_ID=$guardrail_id
GUARDRAIL_VERSION=$guardrail_version
EOF
        fi
        
        print_success "Guardrails configured: ENABLED=true, ID=$guardrail_id"
    else
        print_warning "$env_file not found - guardrails not configured"
    fi
}

# Function to check AgentCore CLI availability
check_agentcore_cli() {
    print_status "🔍 Checking AgentCore CLI availability..."
    
    if ! command -v agentcore &> /dev/null; then
        print_error "AgentCore CLI not found. Please install it first."
        print_status "Installation: pip install bedrock-agentcore-starter-toolkit"
        exit 1
    fi
    
    print_success "AgentCore CLI is available"
}

# Run main function
main "$@"
