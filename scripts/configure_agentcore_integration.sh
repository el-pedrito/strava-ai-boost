#!/bin/bash

# Configure AgentCore Integration for Strava AI Boost
# Post-deployment script to configure IAM permissions and Lambda environment variables
# Run after deploy_agentcore_agents.sh completes successfully

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

# Function to detect deployed AgentCore agents (simplified - no memory detection)
detect_deployed_agents() {
    local content_arn=""
    local campus_arn=""
    
    # Get Content Generation Agent ARN from .bedrock_agentcore.yaml
    if [ -f ".bedrock_agentcore.yaml" ]; then
        content_arn=$(grep -A 1 "agent_arn:" .bedrock_agentcore.yaml | grep "content_gen" -A 1 | grep "arn:aws" | sed 's/.*arn:/arn:/' | sed 's/[[:space:]]*$//' | head -1)
        campus_arn=$(grep -A 1 "agent_arn:" .bedrock_agentcore.yaml | grep "campus_coach" -A 1 | grep "arn:aws" | sed 's/.*arn:/arn:/' | sed 's/[[:space:]]*$//' | head -1)
    fi
    
    # Fallback: Get ARNs using agentcore status if YAML parsing fails
    if [ -z "$content_arn" ] && command -v agentcore &> /dev/null; then
        content_arn=$(agentcore status --agent "$CONTENT_AGENT_NAME" 2>/dev/null | grep -A 2 "Agent ARN:" | grep "arn:aws" | sed 's/│//g' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//' | head -1)
    fi
    
    if [ -z "$campus_arn" ] && command -v agentcore &> /dev/null; then
        campus_arn=$(agentcore status --agent "$CAMPUS_AGENT_NAME" 2>/dev/null | grep -A 2 "Agent ARN:" | grep "arn:aws" | sed 's/│//g' | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//' | head -1)
    fi
    
    # Validate detection results
    if [ -z "$content_arn" ] && [ -z "$campus_arn" ]; then
        return 1
    fi
    
    echo "$content_arn|$campus_arn"
}

# Function to update IAM permissions for Lambda roles to invoke AgentCore
update_lambda_iam_permissions() {
    local content_arn="$1"
    local campus_arn="$2"
    
    print_status "🔐 Updating Lambda IAM permissions for AgentCore invocation..."
    
    # Get account ID
    local account_id
    account_id=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query 'Account' --output text 2>/dev/null)
    
    if [ -z "$account_id" ]; then
        print_error "Failed to get AWS account ID"
        return 1
    fi
    
    # Get Lambda function roles that need AgentCore permissions
    local lambda_functions=(
        "StravaAIBoost-ContentGenerator"
        "StravaAIBoost-CampusCoachInvoker"
    )
    
    local updated_roles=0
    
    for function_name in "${lambda_functions[@]}"; do
        print_status "Updating AgentCore permissions for Lambda function: $function_name"
        
        # Get the Lambda function's role ARN
        local role_arn
        role_arn=$(aws lambda get-function-configuration \
            --function-name "$function_name" \
            --profile "$AWS_PROFILE" \
            --region "$AWS_REGION" \
            --query 'Role' \
            --output text 2>/dev/null)
        
        if [ $? -eq 0 ] && [ -n "$role_arn" ] && [ "$role_arn" != "None" ]; then
            local role_name=$(echo "$role_arn" | awk -F'/' '{print $NF}')
            print_status "Found Lambda role: $role_name"
            
            # Create AgentCore invocation policy for Lambda role (no memory permissions needed)
            local policy_name="StravaAIBoostAgentCoreInvocation-${role_name}-$(date +%s)"
            local policy_file="/tmp/lambda_agentcore_policy_${role_name}_$.json"
            
            cat > "$policy_file" << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:InvokeAgentRuntime"
            ],
            "Resource": [
                "$content_arn",
                "$content_arn/*",
                "$campus_arn",
                "$campus_arn/*"
            ]
        }
    ]
}
EOF
            
            # Create the policy
            local policy_arn
            policy_arn=$(aws iam create-policy \
                --policy-name "$policy_name" \
                --policy-document "file://$policy_file" \
                --description "AgentCore invocation permissions for Lambda: $function_name" \
                --profile "$AWS_PROFILE" \
                --region "$AWS_REGION" \
                --query 'Policy.Arn' \
                --output text 2>/dev/null)
            
            # Clean up temporary file
            rm -f "$policy_file"
            
            if [ $? -eq 0 ] && [ -n "$policy_arn" ] && [[ "$policy_arn" == arn:* ]]; then
                print_success "Created AgentCore policy: $policy_arn"
                
                # Attach policy to Lambda role
                if aws iam attach-role-policy \
                    --role-name "$role_name" \
                    --policy-arn "$policy_arn" \
                    --profile "$AWS_PROFILE" \
                    --region "$AWS_REGION" > /dev/null 2>&1; then
                    print_success "✅ Attached AgentCore policy to Lambda role: $role_name"
                    ((updated_roles++))
                else
                    print_warning "⚠️  Failed to attach policy to Lambda role: $role_name"
                fi
            else
                print_warning "⚠️  Failed to create AgentCore policy for Lambda role: $role_name"
            fi
        else
            print_warning "⚠️  Lambda function $function_name not found or no role"
        fi
    done
    
    print_success "Lambda IAM permissions updated for $updated_roles roles"
    return 0
}

# Function to update IAM permissions for AgentCore agents (simplified - no memory permissions)
update_agentcore_iam_permissions() {
    local content_arn="$1"
    local campus_arn="$2"
    
    print_status "🔐 Updating IAM permissions for AgentCore agents (simplified permissions)..."
    
    # Get actual deployed resources for dynamic permissions
    local account_id
    account_id=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query 'Account' --output text 2>/dev/null)
    
    if [ -z "$account_id" ]; then
        print_error "Failed to get AWS account ID"
        return 1
    fi
    
    # Get actual DynamoDB table names from CDK context or AWS
    local actual_tables
    actual_tables=$(aws dynamodb list-tables --profile "$AWS_PROFILE" --region "$AWS_REGION" --query 'TableNames[?starts_with(@, `strava-ai-boost-`) || starts_with(@, `campus-coaching-sessions`)]' --output json 2>/dev/null)
    
    if [ -z "$actual_tables" ] || [ "$actual_tables" = "[]" ]; then
        print_warning "No Strava AI Boost tables found, using pattern-based permissions"
        actual_tables='["strava-ai-boost-*", "campus-coaching-sessions"]'
    fi
    
    # Get actual Secrets Manager secrets
    local actual_secrets
    actual_secrets=$(aws secretsmanager list-secrets --profile "$AWS_PROFILE" --region "$AWS_REGION" --query 'SecretList[?contains(Name, `strava-ai-boost`)].ARN' --output json 2>/dev/null)
    
    if [ -z "$actual_secrets" ] || [ "$actual_secrets" = "[]" ]; then
        print_warning "No Strava AI Boost secrets found, using pattern-based permissions"
        actual_secrets='["arn:aws:secretsmanager:'$AWS_REGION':'$account_id':secret:strava-ai-boost-*"]'
    fi
    
    # Get execution role ARNs from agent status (with robust parsing)
    local content_role_arn=""
    local campus_role_arn=""
    
    if [ -n "$content_arn" ]; then
        # Use direct AWS CLI to get the role ARN from the agent runtime
        local content_runtime_id=$(echo "$content_arn" | awk -F'/' '{print $NF}')
        content_role_arn=$(aws bedrock-agentcore get-agent-runtime \
            --agent-runtime-id "$content_runtime_id" \
            --profile "$AWS_PROFILE" \
            --region "$AWS_REGION" \
            --query 'roleArn' \
            --output text 2>/dev/null || echo "")
        
        # Fallback: use known pattern for content generation agent
        if [ -z "$content_role_arn" ] || [ "$content_role_arn" = "None" ]; then
            content_role_arn="arn:aws:iam::${account_id}:role/AmazonBedrockAgentCoreSDKRuntime-eu-west-1-XXXXXXXXXXXX"
        fi
    fi
    
    if [ -n "$campus_arn" ]; then
        # Use direct AWS CLI to get the role ARN from the agent runtime
        local campus_runtime_id=$(echo "$campus_arn" | awk -F'/' '{print $NF}')
        campus_role_arn=$(aws bedrock-agentcore get-agent-runtime \
            --agent-runtime-id "$campus_runtime_id" \
            --profile "$AWS_PROFILE" \
            --region "$AWS_REGION" \
            --query 'roleArn' \
            --output text 2>/dev/null || echo "")
        
        # Fallback: use known pattern for campus coach agent
        if [ -z "$campus_role_arn" ] || [ "$campus_role_arn" = "None" ]; then
            campus_role_arn="arn:aws:iam::${account_id}:role/AmazonBedrockAgentCoreSDKRuntime-eu-west-1-XXXXXXXXXXXX"
        fi
    fi
    
    # Build dynamic DynamoDB resources
    local dynamodb_resources=""
    if [ "$actual_tables" != "[]" ]; then
        # Convert table names to ARNs properly
        local table_arns=""
        while IFS= read -r table_name; do
            if [ -n "$table_name" ]; then
                if [ -n "$table_arns" ]; then
                    table_arns="$table_arns,"
                fi
                table_arns="$table_arns\"arn:aws:dynamodb:$AWS_REGION:$account_id:table/$table_name\",\"arn:aws:dynamodb:$AWS_REGION:$account_id:table/$table_name/index/*\""
            fi
        done < <(echo "$actual_tables" | jq -r '.[]' 2>/dev/null)
        
        if [ -n "$table_arns" ]; then
            dynamodb_resources="[$table_arns]"
        fi
    fi
    
    # Fallback to pattern-based if no tables found
    if [ -z "$dynamodb_resources" ] || [ "$dynamodb_resources" = "[]" ]; then
        dynamodb_resources='[
            "arn:aws:dynamodb:'$AWS_REGION':'$account_id':table/strava-ai-boost-*",
            "arn:aws:dynamodb:'$AWS_REGION':'$account_id':table/strava-ai-boost-*/index/*",
            "arn:aws:dynamodb:'$AWS_REGION':'$account_id':table/campus-coaching-sessions",
            "arn:aws:dynamodb:'$AWS_REGION':'$account_id':table/campus-coaching-sessions/index/*"
        ]'
    fi
    
    # Update permissions for each role
    local updated_roles=0
    
    # Process Content Generation Agent role
    if [ -n "$content_role_arn" ] && [ "$content_role_arn" != "null" ]; then
        local role_name=$(echo "$content_role_arn" | awk -F'/' '{print $NF}')
        print_status "Updating simplified permissions for Content Generation role: $role_name"
        
        if update_single_role_permissions "$role_name" "$dynamodb_resources" "$actual_secrets"; then
            ((updated_roles++))
        fi
    fi
    
    # Process Campus Coach Agent role
    if [ -n "$campus_role_arn" ] && [ "$campus_role_arn" != "null" ]; then
        local role_name=$(echo "$campus_role_arn" | awk -F'/' '{print $NF}')
        print_status "Updating simplified permissions for Campus Coach role: $role_name"
        
        if update_single_role_permissions "$role_name" "$dynamodb_resources" "$actual_secrets"; then
            ((updated_roles++))
        fi
    fi
    
    print_success "Simplified IAM permissions updated for $updated_roles roles"
    return 0
}

# Function to update permissions for a single role
update_single_role_permissions() {
    local role_name="$1"
    local memory_resources="$2"
    local dynamodb_resources="$3"
    local actual_secrets="$4"
    
    # Create comprehensive policy with actual deployed resources
    local policy_file="/tmp/agentcore_policy_${role_name}_$$.json"
    
    cat > "$policy_file" << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:ListEvents",
                "bedrock-agentcore:CreateEvent",
                "bedrock-agentcore:GetEvent",
                "bedrock-agentcore:UpdateEvent",
                "bedrock-agentcore:DeleteEvent",
                "bedrock-agentcore:QueryMemory",
                "bedrock-agentcore:InvokeAgent"
            ],
            "Resource": $memory_resources
        },
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:Query",
                "dynamodb:Scan"
            ],
            "Resource": $dynamodb_resources
        },
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
            ],
            "Resource": $actual_secrets
        },
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": [
                "arn:aws:bedrock:${AWS_REGION}::foundation-model/anthropic.claude-*",
                "arn:aws:bedrock:${AWS_REGION}::foundation-model/global.anthropic.claude-*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": [
                "arn:aws:logs:${AWS_REGION}:${account_id}:log-group:/aws/bedrock-agentcore/*"
            ]
        }
    ]
}
EOF
    
    # Create policy name with timestamp and role
    local policy_name="StravaAIBoostAgentCorePolicy-${role_name}-$(date +%s)"
    
    # Create the policy
    local policy_arn
    local policy_creation_output
    policy_creation_output=$(aws iam create-policy \
        --policy-name "$policy_name" \
        --policy-document "file://$policy_file" \
        --description "Dynamic permissions for Strava AI Boost AgentCore role: $role_name" \
        --profile "$AWS_PROFILE" \
        --region "$AWS_REGION" \
        --query 'Policy.Arn' \
        --output text 2>&1)
    
    local policy_creation_exit_code=$?
    
    # Clean up temporary file
    rm -f "$policy_file"
    
    if [ $policy_creation_exit_code -eq 0 ] && [ -n "$policy_creation_output" ] && [[ "$policy_creation_output" == arn:* ]]; then
        policy_arn="$policy_creation_output"
        print_success "Created dynamic policy: $policy_arn"
        
        # Attach policy to role
        if aws iam attach-role-policy \
            --role-name "$role_name" \
            --policy-arn "$policy_arn" \
            --profile "$AWS_PROFILE" \
            --region "$AWS_REGION" > /dev/null 2>&1; then
            print_success "✅ Attached dynamic policy to role: $role_name"
            return 0
        else
            print_warning "⚠️  Failed to attach policy to role: $role_name"
            return 1
        fi
    else
        print_warning "⚠️  Failed to create IAM policy for role: $role_name"
        return 1
    fi
}

# Function to update Lambda environment variables with agent ARNs (direct AWS API)
update_lambda_environment_variables() {
    local content_arn="$1"
    local campus_arn="$2"
    local memory_id="$3"
    
    print_status "🔄 Updating Lambda environment variables with agent ARNs (direct AWS API)..."
    
    # Detect actual Lambda functions that need AgentCore environment variables
    local lambda_functions=()
    
    # Get all Lambda functions with Strava AI Boost prefix
    local all_functions
    all_functions=$(aws lambda list-functions \
        --profile "$AWS_PROFILE" \
        --region "$AWS_REGION" \
        --query 'Functions[?starts_with(FunctionName, `StravaAIBoost-`)].FunctionName' \
        --output json 2>/dev/null)
    
    if [ $? -eq 0 ] && [ "$all_functions" != "null" ] && [ "$all_functions" != "[]" ]; then
        # Convert JSON array to bash array
        while IFS= read -r function_name; do
            lambda_functions+=("$function_name")
        done < <(echo "$all_functions" | jq -r '.[]')
        
        print_status "Found ${#lambda_functions[@]} Strava AI Boost Lambda functions"
    else
        print_warning "No Strava AI Boost Lambda functions found, using fallback list"
        # Fallback to expected function names
        lambda_functions=(
            "StravaAIBoost-ContentGenerator"
            "StravaAIBoost-CampusCoachInvoker"
        )
    fi
    
    local updated_count=0
    local failed_count=0
    
    for function_name in "${lambda_functions[@]}"; do
        print_status "Updating environment variables for $function_name..."
        
        # Get current environment variables
        local current_env
        current_env=$(aws lambda get-function-configuration \
            --function-name "$function_name" \
            --profile "$AWS_PROFILE" \
            --region "$AWS_REGION" \
            --query 'Environment.Variables' \
            --output json 2>/dev/null)
        
        if [ $? -eq 0 ] && [ "$current_env" != "null" ]; then
            # Update environment variables with agent ARNs
            local updated_env
            updated_env=$(echo "$current_env" | jq \
                --arg content_arn "$content_arn" \
                --arg campus_arn "$campus_arn" \
                --arg memory_id "$memory_id" \
                '. + {
                    "CONTENT_GENERATION_AGENT_ARN": $content_arn,
                    "CAMPUS_COACH_AGENT_ARN": $campus_arn,
                    "BEDROCK_AGENTCORE_MEMORY_ID": $memory_id,
                    "AGENTCORE_AGENTS_AVAILABLE": (if ($content_arn != "" or $campus_arn != "") then "true" else "false" end),
                    "AGENTCORE_DEPLOYMENT_TYPE": "direct_code_deploy",
                    "CONTENT_GENERATION_AGENT_NAME": "'"$CONTENT_AGENT_NAME"'",
                    "CAMPUS_COACH_AGENT_NAME": "'"$CAMPUS_AGENT_NAME"'",
                    "AGENTCORE_REGION": "'"$AWS_REGION"'",
                    "AGENTCORE_LAST_UPDATE": "'"$(date -u +"%Y-%m-%dT%H:%M:%SZ")"'"
                }')
            
            # Create temporary environment file
            local env_file="/tmp/lambda_env_${function_name}_$$.json"
            
            cat > "$env_file" << EOF
{
  "Variables": $updated_env
}
EOF
            
            # Apply the updated environment variables directly via AWS API
            if aws lambda update-function-configuration \
                --function-name "$function_name" \
                --environment "file://$env_file" \
                --profile "$AWS_PROFILE" \
                --region "$AWS_REGION" > /dev/null 2>&1; then
                print_success "✅ Updated environment variables for $function_name"
                ((updated_count++))
                
                # Wait for function update to complete to avoid conflicts
                print_status "Waiting for function update to complete..."
                aws lambda wait function-updated \
                    --function-name "$function_name" \
                    --profile "$AWS_PROFILE" \
                    --region "$AWS_REGION" 2>/dev/null || true
            else
                print_warning "⚠️  Failed to update environment variables for $function_name"
                ((failed_count++))
            fi
            
            # Clean up temporary file
            rm -f "$env_file"
        else
            print_warning "⚠️  Lambda function $function_name not found or no environment variables"
            ((failed_count++))
        fi
    done
    
    print_status "Lambda environment variables update summary:"
    print_status "  ✅ Successfully updated: $updated_count functions"
    if [ $failed_count -gt 0 ]; then
        print_warning "  ⚠️  Failed to update: $failed_count functions"
    fi
    
    print_success "✅ Lambda environment variables updated directly (no CDK redeploy needed)"
    print_status "Changes are immediately active - no circular dependency risk"
    
    return 0
}

# Function to update CDK context with agent ARNs (simplified - no memory)
update_cdk_context() {
    local content_arn="$1"
    local campus_arn="$2"
    
    print_status "📝 Updating CDK context with agent ARNs..."
    
    # Create or update cdk.context.json
    if [ ! -f "cdk.context.json" ]; then
        echo "{}" > cdk.context.json
    fi
    
    # Update context with agent ARNs (no memory ID)
    jq --arg content_arn "$content_arn" \
       --arg campus_arn "$campus_arn" \
       '.agentcore = {
         "content_generation_agent_arn": $content_arn,
         "campus_coach_agent_arn": $campus_arn,
         "agents_deployed": true,
         "deployment_timestamp": now | strftime("%Y-%m-%dT%H:%M:%SZ"),
         "deployment_type": "direct_code_deploy",
         "region": "'"$AWS_REGION"'",
         "project": "'"$PROJECT_NAME"'"
       }' cdk.context.json > cdk.context.json.tmp && mv cdk.context.json.tmp cdk.context.json
    
    print_success "CDK context updated with agent ARNs"
}

# Function to create environment file for local development (simplified - no memory variables)
create_env_file() {
    local content_arn="$1"
    local campus_arn="$2"
    
    print_status "📄 Creating .env.agentcore file for local development..."
    
    cat > .env.agentcore << EOF
# AgentCore Configuration - Strava AI Boost
# Auto-generated by configure_agentcore_integration.sh
# Generated at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Deployment Type: direct_code_deploy (no Docker required)

# ============================================================================
# CONTENT GENERATION AGENT
# ============================================================================
# Handles personalized content generation with memory integration
CONTENT_GENERATION_AGENT_ARN=$content_arn
CONTENT_GENERATION_AGENT_NAME=$CONTENT_AGENT_NAME

# ============================================================================
# CAMPUS COACH AGENT
# ============================================================================
# Browser Tool agent for Campus Coach session extraction
CAMPUS_COACH_AGENT_ARN=$campus_arn
CAMPUS_COACH_AGENT_NAME=$CAMPUS_AGENT_NAME

# ============================================================================
# AGENTCORE MEMORY
# ============================================================================
# Memory is managed automatically by AgentCore in STM_ONLY mode
# No manual Memory ARN/ID configuration required

# ============================================================================
# AGENTCORE CONFIGURATION
# ============================================================================
AGENTCORE_AGENTS_AVAILABLE=true
AGENTCORE_REGION=$AWS_REGION
AGENTCORE_DEPLOYMENT_TYPE=direct_code_deploy
AGENTCORE_RUNTIME_TIMEOUT=300
AGENTCORE_MEMORY_ENABLED=true

# ============================================================================
# AWS CONFIGURATION
# ============================================================================
AWS_PROFILE=$AWS_PROFILE
AWS_REGION=$AWS_REGION
AWS_DEFAULT_REGION=$AWS_REGION

# ============================================================================
# PROJECT CONFIGURATION
# ============================================================================
PROJECT_NAME=$PROJECT_NAME
PROJECT_VERSION=0.1.0
DEPLOYMENT_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ENVIRONMENT=development

# ============================================================================
# PERFORMANCE SETTINGS
# ============================================================================
# Content generation timeout (seconds)
CONTENT_GENERATION_TIMEOUT=30
# Campus Coach extraction timeout (seconds)
CAMPUS_COACH_TIMEOUT=300
# Memory lookup timeout (milliseconds)
MEMORY_LOOKUP_TIMEOUT=500

# ============================================================================
# FEATURE FLAGS
# ============================================================================
# Enable/disable specific modules
CAMPUS_COACH_MODULE_ENABLED=true
ENDURAW_MODULE_ENABLED=true
AGENTCORE_MEMORY_PERSONALIZATION=true
VERBOSE_LOGGING=false

EOF

    print_success "Environment file created: .env.agentcore"
}

# Main execution
main() {
    print_status "🔧 Starting AgentCore integration configuration for Strava AI Boost..."
    
    # Set AWS profile for all operations
    export AWS_PROFILE="$AWS_PROFILE"
    export AWS_DEFAULT_REGION="$AWS_REGION"
    
    # Detect deployed agents (silent)
    print_status "🔍 Detecting deployed AgentCore agents..."
    local agent_info
    agent_info=$(detect_deployed_agents)
    
    if [ $? -ne 0 ] || [ -z "$agent_info" ]; then
        print_error "No AgentCore agents found. Please run deploy_agentcore_agents.sh first."
        exit 1
    fi
    
    # Parse agent information
    IFS='|' read -r content_arn campus_arn <<< "$agent_info"
    
    print_success "Detected AgentCore resources:"
    [ -n "$content_arn" ] && print_status "  Content Generation Agent: $content_arn"
    [ -n "$campus_arn" ] && print_status "  Campus Coach Agent: $campus_arn"
    
    print_status ""
    print_status "🔧 Configuring AgentCore integration..."
    
    # Update Lambda IAM permissions for AgentCore invocation
    update_lambda_iam_permissions "$content_arn" "$campus_arn"
    
    # Update IAM permissions for AgentCore agents (simplified)
    update_agentcore_iam_permissions "$content_arn" "$campus_arn"
    
    # Update Lambda environment variables with agent ARNs (simplified)
    update_lambda_environment_variables "$content_arn" "$campus_arn"
    
    # Update CDK context
    update_cdk_context "$content_arn" "$campus_arn"
    
    # Create environment file
    create_env_file "$content_arn" "$campus_arn"
    
    print_success "🎉 AgentCore integration configuration completed successfully!"
    print_status ""
    print_status "📋 Configuration Summary:"
    print_status "  Content Generation Agent: $content_arn"
    print_status "  Campus Coach Agent: $campus_arn"
    print_status "  AgentCore Memory: Managed automatically (STM_ONLY mode)"
    print_status ""
    print_status "✅ Integration Status:"
    print_status "  - IAM permissions: Updated with simplified resources"
    print_status "  - Lambda env vars: Updated directly (immediately active)"
    print_status "  - CDK context: Updated with agent ARNs"
    print_status "  - Environment file: Created for local development"
    print_status ""
    print_status "🚀 System Ready:"
    print_status "  The system is fully integrated with AgentCore"
    print_status "  Lambda functions can now invoke AgentCore agents"
    print_status "  AgentCore Memory is managed automatically"
    print_status ""
    print_status "📁 Files Updated:"
    print_status "  - cdk.context.json (CDK context with agent ARNs)"
    print_status "  - .env.agentcore (local development environment)"
}

# Run main function
main "$@"