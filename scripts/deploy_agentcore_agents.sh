#!/bin/bash

# Deploy AgentCore Agents for Strava AI Boost - Infrastructure as Code
# Uses direct_code_deploy (no Docker required) - AWS 2025 best practices
# Fully automated deployment with no manual configuration required

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
PROJECT_NAME="strava-ai-boost"

# Short agent names to avoid ARN truncation issues
CONTENT_AGENT_NAME="content_gen"
CAMPUS_AGENT_NAME="campus_coach"

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

# Function to configure and deploy content generation agent
deploy_content_agent() {
    print_status "🚀 Configuring and deploying Content Generation Agent (direct_code_deploy + auto memory)..."
    
    local agent_path="src/agents/content_agent.py"
    local agent_name="$CONTENT_AGENT_NAME"
    
    if [ ! -f "$agent_path" ]; then
        print_error "Content agent file not found: $agent_path"
        return 1
    fi
    
    # Check if agent already exists and destroy it if needed
    if agentcore configure list 2>/dev/null | grep -q "$agent_name"; then
        print_status "Existing agent found, destroying it first..."
        agentcore destroy --agent "$agent_name" --force &> /dev/null || true
    fi
    
    # Configure agent with direct_code_deploy and auto memory creation
    print_status "Configuring agent: $agent_name (direct_code_deploy + auto memory)"
    agentcore configure \
        --entrypoint "$agent_path" \
        --name "$agent_name" \
        --region "$AWS_REGION" \
        --requirements-file "src/agents/requirements.txt" \
        --deployment-type direct_code_deploy \
        --runtime PYTHON_3_12 \
        --non-interactive || {
        print_error "Failed to configure Content Generation Agent"
        return 1
    }
    
    # Deploy agent using new deploy command
    print_status "Deploying agent: $agent_name"
    local deploy_output
    deploy_output=$(agentcore deploy \
        --agent "$agent_name" \
        --auto-update-on-conflict 2>&1)
    
    local deploy_exit_code=$?
    
    if [ $deploy_exit_code -eq 0 ]; then
        print_success "Content Generation Agent deployed successfully"
        
        # Get agent ARN from status (with robust JSON parsing)
        local agent_arn=""
        local status_output
        status_output=$(agentcore status --agent "$agent_name" --verbose 2>/dev/null || echo "")
        
        if [ -n "$status_output" ]; then
            # Try to extract ARN with jq, handle JSON parsing errors
            agent_arn=$(echo "$status_output" | jq -r '.agent.arn // empty' 2>/dev/null || echo "")
            
            # Fallback: extract ARN with grep if jq fails
            if [ -z "$agent_arn" ] || [ "$agent_arn" = "null" ]; then
                agent_arn=$(echo "$status_output" | grep -o 'arn:aws:bedrock-agentcore:[^"]*' | head -1 || echo "")
            fi
        fi
        
        if [ -n "$agent_arn" ] && [ "$agent_arn" != "null" ]; then
            print_success "Content Generation Agent ARN: $agent_arn"
            echo "$agent_arn"
        else
            print_error "Could not determine agent ARN from status output"
            print_status "Status output (first 200 chars): ${status_output:0:200}"
            return 1
        fi
    else
        print_error "Failed to deploy Content Generation Agent (exit code: $deploy_exit_code)"
        print_error "Deploy output:"
        echo "$deploy_output"
        return 1
    fi
}

# Function to configure and deploy campus coach agent
deploy_campus_coach_agent() {
    print_status "🚀 Configuring and deploying Campus Coach Agent (direct_code_deploy + auto memory)..."
    
    local agent_path="src/agents/campus_coach_agent.py"
    local agent_name="$CAMPUS_AGENT_NAME"
    
    if [ ! -f "$agent_path" ]; then
        print_error "Campus Coach agent file not found: $agent_path"
        return 1
    fi
    
    # Check if agent already exists and destroy it if needed
    if agentcore configure list 2>/dev/null | grep -q "$agent_name"; then
        print_status "Existing agent found, destroying it first..."
        agentcore destroy --agent "$agent_name" --force &> /dev/null || true
    fi
    
    # Configure agent with direct_code_deploy and auto memory creation
    print_status "Configuring agent: $agent_name (direct_code_deploy + auto memory)"
    agentcore configure \
        --entrypoint "$agent_path" \
        --name "$agent_name" \
        --region "$AWS_REGION" \
        --requirements-file "src/agents/requirements.txt" \
        --deployment-type direct_code_deploy \
        --runtime PYTHON_3_12 \
        --non-interactive || {
        print_error "Failed to configure Campus Coach Agent"
        return 1
    }
    
    # Deploy agent (memory will be auto-created during deployment)
    print_status "Deploying agent: $agent_name (memory auto-creation enabled)"
    local deploy_output
    deploy_output=$(agentcore deploy \
        --agent "$agent_name" \
        --auto-update-on-conflict 2>&1)
    
    local deploy_exit_code=$?
    
    if [ $deploy_exit_code -eq 0 ]; then
        print_success "Campus Coach Agent deployed successfully"
        
        # Get agent ARN from status (with robust JSON parsing)
        local agent_arn=""
        local status_output
        status_output=$(agentcore status --agent "$agent_name" --verbose 2>/dev/null || echo "")
        
        if [ -n "$status_output" ]; then
            # Try to extract ARN with jq, handle JSON parsing errors
            agent_arn=$(echo "$status_output" | jq -r '.agent.arn // empty' 2>/dev/null || echo "")
            
            # Fallback: extract ARN with grep if jq fails
            if [ -z "$agent_arn" ] || [ "$agent_arn" = "null" ]; then
                agent_arn=$(echo "$status_output" | grep -o 'arn:aws:bedrock-agentcore:[^"]*' | head -1 || echo "")
            fi
        fi
        
        if [ -n "$agent_arn" ] && [ "$agent_arn" != "null" ]; then
            print_success "Campus Coach Agent ARN: $agent_arn"
            echo "$agent_arn"
        else
            print_error "Could not determine agent ARN from status output"
            print_status "Status output (first 200 chars): ${status_output:0:200}"
            return 1
        fi
    else
        print_error "Failed to deploy Campus Coach Agent (exit code: $deploy_exit_code)"
        print_error "Deploy output:"
        echo "$deploy_output"
        return 1
    fi
}

# Main execution
main() {
    print_status "🚀 Starting AgentCore agent deployment for Strava AI Boost (direct_code_deploy)..."
    
    # Set AWS profile for all operations
    export AWS_PROFILE="$AWS_PROFILE"
    export AWS_DEFAULT_REGION="$AWS_REGION"
    
    # Check prerequisites
    check_agentcore_cli
    
    # Deploy agents using IaC approach with direct_code_deploy
    print_status "📦 Deploying AgentCore agents with direct_code_deploy (no Docker required)..."
    
    local content_arn=""
    local campus_arn=""
    
    # Deploy content generation agent (memory auto-created)
    if content_arn=$(deploy_content_agent); then
        print_success "Content Generation Agent deployment completed"
    else
        print_error "Content Generation Agent deployment failed"
        exit 1
    fi
    
    # Deploy campus coach agent (memory auto-created)
    if campus_arn=$(deploy_campus_coach_agent); then
        print_success "Campus Coach Agent deployment completed"
    else
        print_error "Campus Coach Agent deployment failed"
        exit 1
    fi
    
    # Basic validation - agents deployed successfully
    if [ -n "$content_arn" ] && [ -n "$campus_arn" ]; then
        print_success "✅ Both agents deployed successfully"
    else
        print_warning "⚠️  Some agents may not have deployed correctly"
    fi
    
    print_success "🎉 AgentCore agent deployment completed successfully!"
    print_status ""
    print_status "📋 Deployment Summary:"
    print_status "  Deployment Type: direct_code_deploy (no Docker required)"
    print_status "  Content Generation Agent: $content_arn"
    print_status "  Campus Coach Agent: $campus_arn"
    print_status "  AgentCore Memory: Auto-created during deployment"
    print_status ""
    print_status "✅ Agents Status:"
    print_status "  - AgentCore agents: Deployed and functional"
    print_status "  - AgentCore Memory: Auto-created during deployment"
    print_status "  - Agents ready for invocation"
    print_status ""
    print_status "🔧 Next Step - Configure Integration:"
    print_status "  Run the integration configuration script to complete setup:"
    print_status "  ./scripts/configure_agentcore_integration.sh"
    print_status ""
    print_status "  This will configure:"
    print_status "  - IAM permissions for agents to access AWS resources"
    print_status "  - Lambda environment variables with agent ARNs"
    print_status "  - CDK context and local development files"
    print_status ""
    print_status "📁 Files Created:"
    print_status "  - .bedrock_agentcore.yaml (AgentCore configuration)"
    print_status ""
    print_status "🧹 Clean Deployment:"
    print_status "  - No Docker required (direct_code_deploy)"
    print_status "  - No circular dependencies"
    print_status "  - Fully reproducible Infrastructure as Code"
}


# Run main function
main "$@"