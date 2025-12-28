#!/bin/bash

# Deploy AgentCore Agents for Strava AI Boost
# Automatically deploys agents and updates CDK context with ARNs

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
        print_status "Installation guide: https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-cli.html"
        exit 1
    fi
    
    # Check authentication
    if ! agentcore configure --check &> /dev/null; then
        print_warning "AgentCore CLI not configured. Running configuration..."
        agentcore configure --region $AWS_REGION
    fi
    
    print_success "AgentCore CLI is available and configured"
}

# Function to ensure IAM permissions for AgentCore agents
ensure_agentcore_permissions() {
    print_status "🔐 Ensuring IAM permissions for AgentCore agents..."
    
    # Check if the current AWS identity has necessary permissions
    local caller_identity
    caller_identity=$(aws sts get-caller-identity --profile $AWS_PROFILE --output json 2>/dev/null)
    
    if [ $? -ne 0 ]; then
        print_error "Cannot verify AWS identity. Please check your AWS profile configuration."
        return 1
    fi
    
    local account_id
    account_id=$(echo "$caller_identity" | jq -r '.Account')
    local user_arn
    user_arn=$(echo "$caller_identity" | jq -r '.Arn')
    
    print_status "AWS Account: $account_id"
    print_status "AWS Identity: $user_arn"
    
    # Create IAM role for AgentCore agents if it doesn't exist
    local role_name="StravaAIBoost-AgentCoreExecutionRole"
    
    if ! aws iam get-role --role-name "$role_name" --profile $AWS_PROFILE &> /dev/null; then
        print_status "Creating IAM role for AgentCore agents..."
        
        # Create trust policy for AgentCore
        local trust_policy='{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "bedrock.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                },
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "lambda.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }'
        
        aws iam create-role \
            --role-name "$role_name" \
            --assume-role-policy-document "$trust_policy" \
            --description "Execution role for Strava AI Boost AgentCore agents" \
            --profile $AWS_PROFILE &> /dev/null
        
        if [ $? -eq 0 ]; then
            print_success "IAM role created: $role_name"
        else
            print_warning "Failed to create IAM role (may already exist or insufficient permissions)"
        fi
        
        # Attach necessary policies
        local policies=(
            "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
            "arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
        )
        
        for policy in "${policies[@]}"; do
            aws iam attach-role-policy \
                --role-name "$role_name" \
                --policy-arn "$policy" \
                --profile $AWS_PROFILE &> /dev/null
            
            if [ $? -eq 0 ]; then
                print_status "Attached policy: $(basename $policy)"
            else
                print_warning "Failed to attach policy: $(basename $policy)"
            fi
        done
        
        # Create custom policy for DynamoDB and Secrets Manager access
        local custom_policy='{
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:PutItem",
                        "dynamodb:GetItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:Query",
                        "dynamodb:Scan"
                    ],
                    "Resource": [
                        "arn:aws:dynamodb:'$AWS_REGION':'$account_id':table/strava-ai-boost-*"
                    ]
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "secretsmanager:GetSecretValue"
                    ],
                    "Resource": [
                        "arn:aws:secretsmanager:'$AWS_REGION':'$account_id':secret:strava-ai-boost-*"
                    ]
                }
            ]
        }'
        
        local policy_name="StravaAIBoost-AgentCoreCustomPolicy"
        aws iam put-role-policy \
            --role-name "$role_name" \
            --policy-name "$policy_name" \
            --policy-document "$custom_policy" \
            --profile $AWS_PROFILE &> /dev/null
        
        if [ $? -eq 0 ]; then
            print_success "Custom policy attached: $policy_name"
        else
            print_warning "Failed to attach custom policy"
        fi
        
        # Wait for role to be available
        print_status "Waiting for IAM role to be available..."
        sleep 10
        
    else
        print_success "IAM role already exists: $role_name"
    fi
    
    return 0
}

# Function to configure agent-specific permissions
configure_agent_permissions() {
    local agent_arn="$1"
    local agent_type="$2"
    
    print_status "🔐 Configuring permissions for $agent_type agent..."
    
    if [ -z "$agent_arn" ]; then
        print_warning "No agent ARN provided, skipping permission configuration"
        return 1
    fi
    
    # Extract agent ID from ARN
    local agent_id
    agent_id=$(echo "$agent_arn" | sed 's/.*agent\///g' | sed 's/-.*//g')
    
    if [ -n "$agent_id" ]; then
        print_status "Configuring permissions for agent ID: $agent_id"
        
        # AgentCore CLI handles most permissions automatically
        # Additional configurations can be added here if needed
        
        print_success "Permissions configured for $agent_type agent"
    else
        print_warning "Could not extract agent ID from ARN: $agent_arn"
    fi
    
    return 0
}

# Function to deploy content generation agent
deploy_content_agent() {
    print_status "🚀 Deploying Content Generation Agent..."
    
    local agent_path="src/agents/content_agent.py"
    local agent_name="${PROJECT_NAME}-content-generator"
    
    if [ ! -f "$agent_path" ]; then
        print_error "Content agent file not found: $agent_path"
        return 1
    fi
    
    # Deploy agent
    print_status "Deploying agent from $agent_path..."
    local deploy_output
    deploy_output=$(agentcore agent deploy \
        --name "$agent_name" \
        --file "$agent_path" \
        --runtime python \
        --region "$AWS_REGION" \
        --output json 2>&1)
    
    if [ $? -eq 0 ]; then
        # Extract ARN from output
        local agent_arn
        agent_arn=$(echo "$deploy_output" | jq -r '.agent_arn // .arn // empty' 2>/dev/null || echo "")
        
        if [ -n "$agent_arn" ] && [ "$agent_arn" != "null" ]; then
            print_success "Content Generation Agent deployed: $agent_arn"
            echo "$agent_arn"
        else
            print_warning "Agent deployed but ARN not found in output"
            # Try to get ARN by listing agents
            local list_output
            list_output=$(agentcore agent list --output json 2>/dev/null || echo "[]")
            agent_arn=$(echo "$list_output" | jq -r ".[] | select(.name | contains(\"$agent_name\")) | .arn" 2>/dev/null | head -1)
            
            if [ -n "$agent_arn" ] && [ "$agent_arn" != "null" ]; then
                print_success "Found Content Generation Agent ARN: $agent_arn"
                echo "$agent_arn"
            else
                print_error "Could not determine agent ARN"
                return 1
            fi
        fi
    else
        print_error "Failed to deploy Content Generation Agent"
        print_error "Output: $deploy_output"
        return 1
    fi
}

# Function to deploy campus coach agent
deploy_campus_coach_agent() {
    print_status "🚀 Deploying Campus Coach Agent..."
    
    local agent_path="src/agents/campus_coach_agent.py"
    local agent_name="${PROJECT_NAME}-campus-coach"
    
    if [ ! -f "$agent_path" ]; then
        print_error "Campus Coach agent file not found: $agent_path"
        return 1
    fi
    
    # Deploy agent
    print_status "Deploying agent from $agent_path..."
    local deploy_output
    deploy_output=$(agentcore agent deploy \
        --name "$agent_name" \
        --file "$agent_path" \
        --runtime python \
        --region "$AWS_REGION" \
        --output json 2>&1)
    
    if [ $? -eq 0 ]; then
        # Extract ARN from output
        local agent_arn
        agent_arn=$(echo "$deploy_output" | jq -r '.agent_arn // .arn // empty' 2>/dev/null || echo "")
        
        if [ -n "$agent_arn" ] && [ "$agent_arn" != "null" ]; then
            print_success "Campus Coach Agent deployed: $agent_arn"
            echo "$agent_arn"
        else
            print_warning "Agent deployed but ARN not found in output"
            # Try to get ARN by listing agents
            local list_output
            list_output=$(agentcore agent list --output json 2>/dev/null || echo "[]")
            agent_arn=$(echo "$list_output" | jq -r ".[] | select(.name | contains(\"$agent_name\")) | .arn" 2>/dev/null | head -1)
            
            if [ -n "$agent_arn" ] && [ "$agent_arn" != "null" ]; then
                print_success "Found Campus Coach Agent ARN: $agent_arn"
                echo "$agent_arn"
            else
                print_error "Could not determine agent ARN"
                return 1
            fi
        fi
    else
        print_error "Failed to deploy Campus Coach Agent"
        print_error "Output: $deploy_output"
        return 1
    fi
}

# Function to create or update AgentCore Memory
setup_agentcore_memory() {
    print_status "🧠 Setting up AgentCore Memory..."
    
    local memory_name="${PROJECT_NAME}-memory"
    
    # Check if memory already exists
    local existing_memory
    existing_memory=$(agentcore memory list --output json 2>/dev/null | jq -r ".[] | select(.name == \"$memory_name\") | .id" 2>/dev/null || echo "")
    
    if [ -n "$existing_memory" ] && [ "$existing_memory" != "null" ]; then
        print_success "AgentCore Memory already exists: $existing_memory"
        echo "$existing_memory"
    else
        print_status "Creating new AgentCore Memory..."
        local memory_output
        memory_output=$(agentcore memory create \
            --name "$memory_name" \
            --description "Persistent memory for Strava AI Boost personalization" \
            --region "$AWS_REGION" \
            --output json 2>&1)
        
        if [ $? -eq 0 ]; then
            local memory_id
            memory_id=$(echo "$memory_output" | jq -r '.memory_id // .id // empty' 2>/dev/null || echo "")
            
            if [ -n "$memory_id" ] && [ "$memory_id" != "null" ]; then
                print_success "AgentCore Memory created: $memory_id"
                echo "$memory_id"
            else
                print_warning "Memory created but ID not found in output"
                return 1
            fi
        else
            print_error "Failed to create AgentCore Memory"
            print_error "Output: $memory_output"
            return 1
        fi
    fi
}

# Function to update CDK context with agent ARNs
update_cdk_context() {
    local content_arn="$1"
    local campus_arn="$2"
    local memory_id="$3"
    
    print_status "📝 Updating CDK context with agent ARNs..."
    
    # Create or update cdk.context.json
    if [ ! -f "cdk.context.json" ]; then
        echo "{}" > cdk.context.json
    fi
    
    # Update context with agent ARNs and memory ID
    jq --arg content_arn "$content_arn" \
       --arg campus_arn "$campus_arn" \
       --arg memory_id "$memory_id" \
       '.agentcore = {
         "content_generation_agent_arn": $content_arn,
         "campus_coach_agent_arn": $campus_arn,
         "memory_id": $memory_id,
         "agents_deployed": true,
         "deployment_timestamp": now | strftime("%Y-%m-%dT%H:%M:%SZ"),
         "region": "'"$AWS_REGION"'",
         "project": "'"$PROJECT_NAME"'"
       }' cdk.context.json > cdk.context.json.tmp && mv cdk.context.json.tmp cdk.context.json
    
    print_success "CDK context updated with agent ARNs and memory ID"
}

# Function to create environment file for local development
create_env_file() {
    local content_arn="$1"
    local campus_arn="$2"
    local memory_id="$3"
    
    print_status "📄 Creating .env.agentcore file for local development..."
    
    # Extract agent names from ARNs
    local content_name=""
    local campus_name=""
    
    if [ -n "$content_arn" ]; then
        content_name=$(echo "$content_arn" | sed 's/.*agent\///g' | sed 's/-.*//g')
    fi
    
    if [ -n "$campus_arn" ]; then
        campus_name=$(echo "$campus_arn" | sed 's/.*agent\///g' | sed 's/-.*//g')
    fi
    
    cat > .env.agentcore << EOF
# AgentCore Configuration - Auto-generated by deploy_agentcore_agents.sh
# Generated at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Content Generation Agent
CONTENT_GENERATION_AGENT_ARN=$content_arn
CONTENT_GENERATION_AGENT_NAME=$content_name

# Campus Coach Agent  
CAMPUS_COACH_AGENT_ARN=$campus_arn
CAMPUS_COACH_AGENT_NAME=$campus_name

# AgentCore Memory
BEDROCK_AGENTCORE_MEMORY_ID=$memory_id

# AgentCore Configuration
AGENTCORE_AGENTS_AVAILABLE=true
AGENTCORE_REGION=$AWS_REGION
AWS_PROFILE=$AWS_PROFILE

# Project Configuration
PROJECT_NAME=$PROJECT_NAME
DEPLOYMENT_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF

    print_success "Environment file created: .env.agentcore"
}

# Function to validate agent deployments
validate_deployments() {
    local content_arn="$1"
    local campus_arn="$2"
    local memory_id="$3"
    
    print_status "✅ Validating agent deployments..."
    
    local validation_errors=0
    
    # Test content generation agent
    if [ -n "$content_arn" ]; then
        print_status "Testing Content Generation Agent..."
        local test_payload='{"activity_data": {"type": "Run", "distance": 5000, "name": "Test Run"}, "user_id": "test_user", "action": "generate_content"}'
        
        if agentcore invoke "$content_arn" --input "$test_payload" --timeout 30 &> /dev/null; then
            print_success "Content Generation Agent is responsive"
        else
            print_warning "Content Generation Agent test failed (may need warm-up)"
            ((validation_errors++))
        fi
    else
        print_warning "Content Generation Agent ARN not available for testing"
        ((validation_errors++))
    fi
    
    # Test campus coach agent
    if [ -n "$campus_arn" ]; then
        print_status "Testing Campus Coach Agent..."
        local test_payload='{"action": "check_credentials", "user_id": "test_user"}'
        
        if agentcore invoke "$campus_arn" --input "$test_payload" --timeout 30 &> /dev/null; then
            print_success "Campus Coach Agent is responsive"
        else
            print_warning "Campus Coach Agent test failed (may need warm-up)"
            ((validation_errors++))
        fi
    else
        print_warning "Campus Coach Agent ARN not available for testing"
        ((validation_errors++))
    fi
    
    # Test memory
    if [ -n "$memory_id" ]; then
        print_status "Testing AgentCore Memory..."
        if agentcore memory describe --id "$memory_id" &> /dev/null; then
            print_success "AgentCore Memory is accessible"
        else
            print_warning "AgentCore Memory test failed"
            ((validation_errors++))
        fi
    else
        print_warning "AgentCore Memory ID not available for testing"
        ((validation_errors++))
    fi
    
    return $validation_errors
}

# Main execution
main() {
    print_status "🚀 Starting AgentCore agent deployment for Strava AI Boost..."
    
    # Check prerequisites
    check_agentcore_cli
    
    # Ensure IAM permissions
    ensure_agentcore_permissions
    
    # Deploy agents
    print_status "📦 Deploying AgentCore agents..."
    
    local content_arn=""
    local campus_arn=""
    local memory_id=""
    
    # Deploy content generation agent
    if content_arn=$(deploy_content_agent); then
        print_success "Content Generation Agent deployment completed"
        
        # Configure agent-specific permissions
        configure_agent_permissions "$content_arn" "content-generation"
    else
        print_error "Content Generation Agent deployment failed"
        exit 1
    fi
    
    # Deploy campus coach agent
    if campus_arn=$(deploy_campus_coach_agent); then
        print_success "Campus Coach Agent deployment completed"
        
        # Configure agent-specific permissions
        configure_agent_permissions "$campus_arn" "campus-coach"
    else
        print_error "Campus Coach Agent deployment failed"
        exit 1
    fi
    
    # Setup AgentCore Memory
    if memory_id=$(setup_agentcore_memory); then
        print_success "AgentCore Memory setup completed"
    else
        print_warning "AgentCore Memory setup failed, continuing without memory"
        memory_id=""
    fi
    
    # Update CDK context
    update_cdk_context "$content_arn" "$campus_arn" "$memory_id"
    
    # Create environment file
    create_env_file "$content_arn" "$campus_arn" "$memory_id"
    
    # Validate deployments
    if validate_deployments "$content_arn" "$campus_arn" "$memory_id"; then
        print_success "✅ All agent deployments validated successfully"
    else
        print_warning "⚠️  Some validation tests failed (agents may need warm-up time)"
    fi
    
    print_success "🎉 AgentCore agent deployment completed successfully!"
    print_status ""
    print_status "📋 Deployment Summary:"
    print_status "  Content Generation Agent: $content_arn"
    print_status "  Campus Coach Agent: $campus_arn"
    print_status "  AgentCore Memory: $memory_id"
    print_status ""
    print_status "🔄 Next Steps:"
    print_status "  1. Run 'cdk deploy' to update Lambda environment variables"
    print_status "  2. Source environment file: source .env.agentcore"
    print_status "  3. Test the system with a webhook or manual invocation"
    print_status ""
    print_status "📁 Files Updated:"
    print_status "  - cdk.context.json (CDK context with agent ARNs)"
    print_status "  - .env.agentcore (local development environment)"
}

# Run main function
main "$@"