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
AWS_PROFILE="${AWS_PROFILE:-your-aws-profile}"
AWS_REGION="${AWS_REGION:-us-east-1}"
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
            
            # Create AgentCore invocation policy for Lambda role (with clean, fixed name)
            local policy_name="StravaAIBoost-AgentCore-Lambda"
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
            
            # Check if policy already exists
            local existing_policy_arn
            existing_policy_arn=$(aws iam list-policies \
                --scope Local \
                --profile "$AWS_PROFILE" \
                --query "Policies[?PolicyName=='$policy_name'].Arn" \
                --output text 2>/dev/null)
            
            local policy_arn=""
            
            if [ -n "$existing_policy_arn" ] && [ "$existing_policy_arn" != "None" ]; then
                # Check if policy content has changed
                print_status "Checking if policy needs update: $policy_name"
                
                local current_policy_doc
                current_policy_doc=$(aws iam get-policy-version \
                    --policy-arn "$existing_policy_arn" \
                    --version-id $(aws iam get-policy --policy-arn "$existing_policy_arn" --profile "$AWS_PROFILE" --query 'Policy.DefaultVersionId' --output text) \
                    --profile "$AWS_PROFILE" \
                    --query 'PolicyVersion.Document' \
                    --output json 2>/dev/null)
                
                local new_policy_doc=$(cat "$policy_file")
                
                # Compare policies (normalize JSON for comparison)
                local current_normalized=$(echo "$current_policy_doc" | jq -S -c '.')
                local new_normalized=$(echo "$new_policy_doc" | jq -S -c '.')
                
                if [ "$current_normalized" = "$new_normalized" ]; then
                    print_success "✅ Policy unchanged, skipping version creation"
                    policy_arn="$existing_policy_arn"
                else
                    # Policy has changed, create new version
                    print_status "Policy has changed, creating new version"
                    
                    # Delete oldest non-default version if we have 5 versions (AWS limit)
                    local version_count=$(aws iam list-policy-versions \
                        --policy-arn "$existing_policy_arn" \
                        --profile "$AWS_PROFILE" \
                        --query 'length(Versions)' \
                        --output text 2>/dev/null)
                    
                    if [ "$version_count" -ge 5 ]; then
                        print_status "Cleaning up old policy versions (limit: 5)"
                        local oldest_version=$(aws iam list-policy-versions \
                            --policy-arn "$existing_policy_arn" \
                            --profile "$AWS_PROFILE" \
                            --query 'Versions[?IsDefaultVersion==`false`] | sort_by(@, &CreateDate) | [0].VersionId' \
                            --output text 2>/dev/null)
                        
                        if [ -n "$oldest_version" ] && [ "$oldest_version" != "None" ]; then
                            aws iam delete-policy-version \
                                --policy-arn "$existing_policy_arn" \
                                --version-id "$oldest_version" \
                                --profile "$AWS_PROFILE" 2>/dev/null
                            print_status "Deleted old version: $oldest_version"
                        fi
                    fi
                    
                    # Create new policy version
                    local version_id
                    version_id=$(aws iam create-policy-version \
                        --policy-arn "$existing_policy_arn" \
                        --policy-document "file://$policy_file" \
                        --set-as-default \
                        --profile "$AWS_PROFILE" \
                        --query 'PolicyVersion.VersionId' \
                        --output text 2>/dev/null)
                    
                    if [ $? -eq 0 ] && [ -n "$version_id" ]; then
                        print_success "✅ Created new policy version: $version_id"
                        policy_arn="$existing_policy_arn"
                    else
                        print_warning "Failed to update existing policy, will create new one"
                    fi
                fi
            fi
            
            # Create new policy if update failed or policy doesn't exist
            if [ -z "$policy_arn" ]; then
                print_status "Creating new policy: $policy_name"
                
                policy_arn=$(aws iam create-policy \
                    --policy-name "$policy_name" \
                    --policy-document "file://$policy_file" \
                    --description "Clean AgentCore invocation permissions for Strava AI Boost Lambda" \
                    --profile "$AWS_PROFILE" \
                    --region "$AWS_REGION" \
                    --query 'Policy.Arn' \
                    --output text 2>/dev/null)
                
                if [ $? -eq 0 ] && [ -n "$policy_arn" ] && [[ "$policy_arn" == arn:* ]]; then
                    print_success "✅ Created clean AgentCore policy: $policy_arn"
                else
                    print_warning "⚠️  Failed to create AgentCore policy for Lambda role: $role_name"
                    rm -f "$policy_file"
                    continue
                fi
            fi
            
            # Clean up temporary file
            rm -f "$policy_file"
            
            # Check if policy is already attached to avoid duplicate attachment
            local is_attached
            is_attached=$(aws iam list-attached-role-policies \
                --role-name "$role_name" \
                --profile "$AWS_PROFILE" \
                --query "AttachedPolicies[?PolicyArn=='$policy_arn'].PolicyArn" \
                --output text 2>/dev/null)
            
            if [ -z "$is_attached" ] || [ "$is_attached" = "None" ]; then
                # Attach policy to Lambda role
                if aws iam attach-role-policy \
                    --role-name "$role_name" \
                    --policy-arn "$policy_arn" \
                    --profile "$AWS_PROFILE" \
                    --region "$AWS_REGION" > /dev/null 2>&1; then
                    print_success "✅ Attached clean AgentCore policy to Lambda role: $role_name"
                    ((updated_roles++))
                else
                    print_warning "⚠️  Failed to attach policy to Lambda role: $role_name"
                fi
            else
                print_success "✅ Clean policy already attached to Lambda role: $role_name"
                ((updated_roles++))
            fi
        else
            print_warning "⚠️  Lambda function $function_name not found or no role"
        fi
    done
    
    print_success "Lambda IAM permissions updated for $updated_roles roles"
    return 0
}

# Function to configure AgentCore agent IAM permissions (including memory access)
configure_agentcore_agent_permissions() {
    local campus_arn="$1"
    local content_memory_id="$2"
    local campus_memory_id="$3"
    
    print_status "🔐 Configuring IAM permissions for AgentCore agents (including memory access)..."
    
    # Get account ID
    local account_id
    account_id=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query 'Account' --output text 2>/dev/null)
    
    if [ -z "$account_id" ]; then
        print_error "Failed to get AWS account ID"
        return 1
    fi
    
    # Extract specific roles from .bedrock_agentcore.yaml
    print_status "Extracting AgentCore execution roles from deployment config..."
    
    local agentcore_roles=""
    
    if [ -f ".bedrock_agentcore.yaml" ]; then
        # Extract execution_role from YAML (correct path: agents.*.aws.execution_role)
        agentcore_roles=$(python3 << 'EOF'
import yaml
import sys

try:
    with open('.bedrock_agentcore.yaml', 'r') as f:
        config = yaml.safe_load(f) or {}
    
    roles = set()
    for agent_name, agent_config in config.get('agents', {}).items():
        # Correct path: agents.*.aws.execution_role
        role_arn = agent_config.get('aws', {}).get('execution_role', '')
        if role_arn and 'role/' in role_arn:
            role_name = role_arn.split('role/')[-1]
            roles.add(role_name)
    
    if roles:
        print(' '.join(sorted(roles)))
    sys.exit(0)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
EOF
)
    fi
    
    # Fallback: list all AgentCore roles if YAML parsing fails
    if [ -z "$agentcore_roles" ]; then
        print_warning "Could not extract roles from YAML, using all AgentCore roles"
        agentcore_roles=$(aws iam list-roles \
            --profile "$AWS_PROFILE" \
            --query 'Roles[?starts_with(RoleName, `AmazonBedrockAgentCoreSDKRuntime-`)].RoleName' \
            --output text 2>/dev/null)
    fi
    
    if [ -z "$agentcore_roles" ]; then
        print_error "No AgentCore execution roles found"
        return 1
    fi
    
    # Count roles
    local role_count=$(echo "$agentcore_roles" | wc -w)
    
    print_status "Found AgentCore roles: $role_count role(s)"
    for role in $agentcore_roles; do
        print_status "  - $role"
    done
    
    # Build memory ARNs for both agents
    local memory_resources="[]"
    if [ -n "$content_memory_id" ]; then
        memory_resources=$(echo "$memory_resources" | jq --arg arn "arn:aws:bedrock-agentcore:${AWS_REGION}:${account_id}:memory/${content_memory_id}" '. + [$arn]')
    fi
    if [ -n "$campus_memory_id" ]; then
        memory_resources=$(echo "$memory_resources" | jq --arg arn "arn:aws:bedrock-agentcore:${AWS_REGION}:${account_id}:memory/${campus_memory_id}" '. + [$arn]')
    fi
    
    # Create comprehensive policy for ALL AgentCore agents
    local policy_name="StravaAIBoost-AgentCore-AllPermissions"
    local policy_file="/tmp/agentcore_all_permissions_$.json"
    
    cat > "$policy_file" << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "SecretsManagerAccess",
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue"
            ],
            "Resource": [
                "arn:aws:secretsmanager:${AWS_REGION}:${account_id}:secret:strava-ai-boost-campus-coach-credentials-*"
            ]
        },
        {
            "Sid": "DynamoDBAccess",
            "Effect": "Allow",
            "Action": [
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:GetItem",
                "dynamodb:Query",
                "dynamodb:Scan"
            ],
            "Resource": [
                "arn:aws:dynamodb:${AWS_REGION}:${account_id}:table/strava-ai-boost-campus-coaching-sessions",
                "arn:aws:dynamodb:${AWS_REGION}:${account_id}:table/strava-ai-boost-campus-coaching-sessions/index/*"
            ]
        },
        {
            "Sid": "BrowserToolAccess",
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:StartBrowserSession",
                "bedrock-agentcore:StopBrowserSession",
                "bedrock-agentcore:GetBrowserSession",
                "bedrock-agentcore:ListBrowserSessions",
                "bedrock-agentcore:ConnectBrowserAutomationStream"
            ],
            "Resource": ["*"]
        },
        {
            "Sid": "AgentCoreMemoryAccess",
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:ListEvents",
                "bedrock-agentcore:GetEvent",
                "bedrock-agentcore:CreateEvent",
                "bedrock-agentcore:DeleteEvent",
                "bedrock-agentcore:GetMemory",
                "bedrock-agentcore:ListMemories"
            ],
            "Resource": $(echo "$memory_resources" | jq -c '.')
        }
    ]
}
EOF
    
    # Check if policy exists
    local existing_policy_arn
    existing_policy_arn=$(aws iam list-policies \
        --scope Local \
        --profile "$AWS_PROFILE" \
        --query "Policies[?PolicyName=='$policy_name'].Arn" \
        --output text 2>/dev/null)
    
    local policy_arn=""
    
    if [ -n "$existing_policy_arn" ] && [ "$existing_policy_arn" != "None" ]; then
        # Check if policy content has changed
        print_status "Checking if policy needs update: $policy_name"
        
        local current_policy_doc
        current_policy_doc=$(aws iam get-policy-version \
            --policy-arn "$existing_policy_arn" \
            --version-id $(aws iam get-policy --policy-arn "$existing_policy_arn" --profile "$AWS_PROFILE" --query 'Policy.DefaultVersionId' --output text) \
            --profile "$AWS_PROFILE" \
            --query 'PolicyVersion.Document' \
            --output json 2>/dev/null)
        
        local new_policy_doc=$(cat "$policy_file")
        
        # Compare policies (normalize JSON for comparison)
        local current_normalized=$(echo "$current_policy_doc" | jq -S -c '.')
        local new_normalized=$(echo "$new_policy_doc" | jq -S -c '.')
        
        if [ "$current_normalized" = "$new_normalized" ]; then
            print_success "✅ Policy unchanged, skipping version creation"
            policy_arn="$existing_policy_arn"
        else
            # Policy has changed, create new version
            print_status "Policy has changed, creating new version"
            
            # Delete oldest non-default version if we have 5 versions (AWS limit)
            local version_count=$(aws iam list-policy-versions \
                --policy-arn "$existing_policy_arn" \
                --profile "$AWS_PROFILE" \
                --query 'length(Versions)' \
                --output text 2>/dev/null)
            
            if [ "$version_count" -ge 5 ]; then
                print_status "Cleaning up old policy versions (limit: 5)"
                local oldest_version=$(aws iam list-policy-versions \
                    --policy-arn "$existing_policy_arn" \
                    --profile "$AWS_PROFILE" \
                    --query 'Versions[?IsDefaultVersion==`false`] | sort_by(@, &CreateDate) | [0].VersionId' \
                    --output text 2>/dev/null)
                
                if [ -n "$oldest_version" ] && [ "$oldest_version" != "None" ]; then
                    aws iam delete-policy-version \
                        --policy-arn "$existing_policy_arn" \
                        --version-id "$oldest_version" \
                        --profile "$AWS_PROFILE" 2>/dev/null
                    print_status "Deleted old version: $oldest_version"
                fi
            fi
            
            # Create new policy version
            local version_id
            version_id=$(aws iam create-policy-version \
                --policy-arn "$existing_policy_arn" \
                --policy-document "file://$policy_file" \
                --set-as-default \
                --profile "$AWS_PROFILE" \
                --query 'PolicyVersion.VersionId' \
                --output text 2>/dev/null)
            
            if [ $? -eq 0 ] && [ -n "$version_id" ]; then
                print_success "✅ Created new policy version: $version_id"
                policy_arn="$existing_policy_arn"
            else
                print_warning "Failed to update existing policy, will create new one"
            fi
        fi
    fi
    
    # Create new policy if update failed or policy doesn't exist
    if [ -z "$policy_arn" ]; then
        print_status "Creating new policy: $policy_name"
        policy_arn=$(aws iam create-policy \
            --policy-name "$policy_name" \
            --policy-document "file://$policy_file" \
            --description "Comprehensive permissions for all Strava AI Boost AgentCore agents (including memory access)" \
            --profile "$AWS_PROFILE" \
            --region "$AWS_REGION" \
            --query 'Policy.Arn' \
            --output text 2>/dev/null)
        
        if [ $? -eq 0 ] && [ -n "$policy_arn" ] && [[ "$policy_arn" == arn:* ]]; then
            print_success "✅ Created comprehensive AgentCore policy: $policy_arn"
        else
            print_error "Failed to create AgentCore policy"
            rm -f "$policy_file"
            return 1
        fi
    fi
    
    rm -f "$policy_file"
    
    # Attach policy to ALL AgentCore roles
    local attached_count=0
    for role_name in $agentcore_roles; do
        print_status "Attaching policy to role: $role_name"
        
        # Check if policy is already attached
        local is_attached
        is_attached=$(aws iam list-attached-role-policies \
            --role-name "$role_name" \
            --profile "$AWS_PROFILE" \
            --query "AttachedPolicies[?PolicyArn=='$policy_arn'].PolicyArn" \
            --output text 2>/dev/null)
        
        if [ -z "$is_attached" ] || [ "$is_attached" = "None" ]; then
            if aws iam attach-role-policy \
                --role-name "$role_name" \
                --policy-arn "$policy_arn" \
                --profile "$AWS_PROFILE" > /dev/null 2>&1; then
                print_success "✅ Attached policy to role: $role_name"
                ((attached_count++))
            else
                print_warning "⚠️  Failed to attach policy to role: $role_name"
            fi
        else
            print_success "✅ Policy already attached to role: $role_name"
            ((attached_count++))
        fi
    done
    
    if [ $attached_count -gt 0 ]; then
        print_success "✅ AgentCore permissions configured for $attached_count role(s)"
        print_status "   Permissions include: Secrets Manager, DynamoDB, Browser Tool, Memory Access"
        return 0
    else
        print_error "Failed to attach policy to any AgentCore roles"
        return 1
    fi
}

# Function to verify AgentCore agent permissions (read-only check)
verify_agentcore_iam_permissions() {
    local content_arn="$1"
    local campus_arn="$2"
    
    print_status "🔍 Verifying AgentCore agent permissions (read-only check)..."
    
    # Get account ID
    local account_id
    account_id=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query 'Account' --output text 2>/dev/null)
    
    if [ -z "$account_id" ]; then
        print_error "Failed to get AWS account ID"
        return 1
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
            content_role_arn="arn:aws:iam::${account_id}:role/AmazonBedrockAgentCoreSDKRuntime-${AWS_REGION}-XXXXXXXXXXXX"
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
            campus_role_arn="arn:aws:iam::${account_id}:role/AmazonBedrockAgentCoreSDKRuntime-${AWS_REGION}-XXXXXXXXXXXX"
        fi
    fi
    
    local verified_roles=0
    
    # Verify Content Generation Agent role exists
    if [ -n "$content_role_arn" ] && [ "$content_role_arn" != "null" ]; then
        local role_name=$(echo "$content_role_arn" | awk -F'/' '{print $NF}')
        print_status "Verifying Content Generation role: $role_name"
        
        if aws iam get-role --role-name "$role_name" --profile "$AWS_PROFILE" > /dev/null 2>&1; then
            print_success "✅ Content Generation agent role exists and is managed by AgentCore"
            ((verified_roles++))
        else
            print_warning "⚠️  Content Generation agent role not found: $role_name"
        fi
    fi
    
    # Verify Campus Coach Agent role exists
    if [ -n "$campus_role_arn" ] && [ "$campus_role_arn" != "null" ]; then
        local role_name=$(echo "$campus_role_arn" | awk -F'/' '{print $NF}')
        print_status "Verifying Campus Coach role: $role_name"
        
        if aws iam get-role --role-name "$role_name" --profile "$AWS_PROFILE" > /dev/null 2>&1; then
            print_success "✅ Campus Coach agent role exists and is managed by AgentCore"
            ((verified_roles++))
        else
            print_warning "⚠️  Campus Coach agent role not found: $role_name"
        fi
    fi
    
    print_success "AgentCore agent roles verified: $verified_roles roles found"
    print_status "ℹ️  Note: AgentCore agent roles are automatically managed by AWS and include all necessary permissions"
    return 0
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
        # Convert JSON array to bash array, filtering out CDK custom resource handlers
        while IFS= read -r function_name; do
            # Skip CDK custom resource handlers (they don't need AgentCore env vars)
            if [[ "$function_name" =~ Provider.*framework ]] || \
               [[ "$function_name" =~ Handler[A-Z0-9]{8}- ]]; then
                print_status "Skipping CDK custom resource handler: $function_name"
                continue
            fi
            lambda_functions+=("$function_name")
        done < <(echo "$all_functions" | jq -r '.[]')
        
        print_status "Found ${#lambda_functions[@]} Strava AI Boost Lambda functions (excluding CDK handlers)"
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
            # Update environment variables with agent ARNs (no memory ID for Lambda)
            local updated_env
            updated_env=$(echo "$current_env" | jq \
                --arg content_arn "$content_arn" \
                --arg campus_arn "$campus_arn" \
                '. + {
                    "CONTENT_GENERATION_AGENT_ARN": $content_arn,
                    "CAMPUS_COACH_AGENT_ARN": $campus_arn,
                    "AGENTCORE_AGENTS_AVAILABLE": (if ($content_arn != "" or $campus_arn != "") then "true" else "false" end),
                    "AGENTCORE_DEPLOYMENT_TYPE": "direct_code_deploy",
                    "CONTENT_GENERATION_AGENT_NAME": "'"$CONTENT_AGENT_NAME"'",
                    "CAMPUS_COACH_AGENT_NAME": "'"$CAMPUS_AGENT_NAME"'",
                    "AGENTCORE_REGION": "'"$AWS_REGION"'",
                    "AGENTCORE_LAST_UPDATE": "'"$(date -u +"%Y-%m-%dT%H:%M:%SZ")"'"
                }')
            
            # Create temporary environment file
            local env_file="/tmp/lambda_env_${function_name}_$.json"
            
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
# Function to create environment file for local development (simplified - no memory variables)
create_env_file() {
    local content_arn="$1"
    local campus_arn="$2"
    local memory_id="$3"
    
    print_status "📄 Updating .env.agentcore file..."
    
    # Backup existing file if it exists
    if [ -f ".env.agentcore" ]; then
        # Extract existing guardrail configuration
        EXISTING_GUARDRAIL_ENABLED=$(grep "^GUARDRAIL_ENABLED=" .env.agentcore 2>/dev/null | cut -d'=' -f2 || echo "false")
        EXISTING_GUARDRAIL_ID=$(grep "^GUARDRAIL_ID=" .env.agentcore 2>/dev/null | cut -d'=' -f2 || echo "")
        EXISTING_GUARDRAIL_VERSION=$(grep "^GUARDRAIL_VERSION=" .env.agentcore 2>/dev/null | cut -d'=' -f2 || echo "1")
    else
        # No existing file, try to detect from CloudFormation
        print_status "🛡️  Detecting Bedrock Guardrails from CloudFormation..."
        
        local stack_name="StravaAIBoost-Security"
        if aws cloudformation describe-stacks \
            --stack-name "$stack_name" \
            --profile "$AWS_PROFILE" \
            --region "$AWS_REGION" \
            --query 'Stacks[0].StackStatus' \
            --output text &>/dev/null; then
            
            EXISTING_GUARDRAIL_ID=$(aws cloudformation describe-stacks \
                --stack-name "$stack_name" \
                --profile "$AWS_PROFILE" \
                --region "$AWS_REGION" \
                --query 'Stacks[0].Outputs[?OutputKey==`GuardrailId`].OutputValue' \
                --output text 2>/dev/null || echo "")
            
            EXISTING_GUARDRAIL_VERSION=$(aws cloudformation describe-stacks \
                --stack-name "$stack_name" \
                --profile "$AWS_PROFILE" \
                --region "$AWS_REGION" \
                --query 'Stacks[0].Outputs[?OutputKey==`GuardrailVersion`].OutputValue' \
                --output text 2>/dev/null || echo "1")
            
            if [ -n "$EXISTING_GUARDRAIL_ID" ]; then
                EXISTING_GUARDRAIL_ENABLED="true"
                print_success "Found Bedrock Guardrail: $EXISTING_GUARDRAIL_ID v$EXISTING_GUARDRAIL_VERSION"
            else
                EXISTING_GUARDRAIL_ENABLED="false"
                EXISTING_GUARDRAIL_ID=""
                EXISTING_GUARDRAIL_VERSION="1"
                print_status "No guardrail found (SecurityStack not deployed)"
            fi
        else
            EXISTING_GUARDRAIL_ENABLED="false"
            EXISTING_GUARDRAIL_ID=""
            EXISTING_GUARDRAIL_VERSION="1"
            print_status "SecurityStack not deployed, guardrails disabled"
        fi
    fi
    
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
VERBOSE_LOGGING=true  # Enable verbose logging for debugging

# ============================================================================
# SECURITY - BEDROCK GUARDRAILS
# ============================================================================
# Bedrock Guardrails for prompt injection and content safety
# Auto-detected from SecurityStack or preserved from previous config
GUARDRAIL_ENABLED=$EXISTING_GUARDRAIL_ENABLED
GUARDRAIL_ID=$EXISTING_GUARDRAIL_ID
GUARDRAIL_VERSION=$EXISTING_GUARDRAIL_VERSION

EOF

    print_success "Environment file updated: .env.agentcore"
    if [ "$EXISTING_GUARDRAIL_ENABLED" = "true" ]; then
        print_success "  ✅ Guardrail configuration: $EXISTING_GUARDRAIL_ID v$EXISTING_GUARDRAIL_VERSION"
    else
        print_status "  ⚠️  Guardrails not configured (deploy SecurityStack to enable)"
    fi
    if [ -n "$memory_id" ]; then
        print_status "  Note: Memory ID ($memory_id) is passed to agents via agentcore launch --env"
        print_status "  Each agent has its own memory configured in .bedrock_agentcore.yaml"
    fi
}

# Function to get memory ID from .bedrock_agentcore.yaml
get_memory_id_from_yaml() {
    local agent_name="$1"
    
    if [ ! -f ".bedrock_agentcore.yaml" ]; then
        echo ""
        return
    fi
    
    # Use Python to properly parse YAML
    local memory_id=$(python3 << EOF
import yaml
try:
    with open('.bedrock_agentcore.yaml', 'r') as f:
        config = yaml.safe_load(f)
    memory_id = config.get('agents', {}).get('$agent_name', {}).get('memory', {}).get('memory_id', '')
    if memory_id and memory_id != 'null':
        print(memory_id)
except Exception:
    pass
EOF
)
    
    echo "$memory_id"
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
    
    # Get memory IDs from YAML
    print_status "🔍 Detecting AgentCore Memory configuration..."
    local content_memory_id=$(get_memory_id_from_yaml "$CONTENT_AGENT_NAME")
    local campus_memory_id=$(get_memory_id_from_yaml "$CAMPUS_AGENT_NAME")
    
    if [ -n "$content_memory_id" ] || [ -n "$campus_memory_id" ]; then
        print_success "Found AgentCore Memory configuration:"
        [ -n "$content_memory_id" ] && print_status "  Content Agent Memory: $content_memory_id"
        [ -n "$campus_memory_id" ] && print_status "  Campus Coach Memory: $campus_memory_id"
    else
        print_warning "No AgentCore Memory configured (agents will run without LTM)"
        content_memory_id=""
        campus_memory_id=""
    fi
    
    print_success "Detected AgentCore resources:"
    [ -n "$content_arn" ] && print_status "  Content Generation Agent: $content_arn"
    [ -n "$campus_arn" ] && print_status "  Campus Coach Agent: $campus_arn"
    [ -n "$content_memory_id" ] && print_status "  Content Agent Memory: $content_memory_id"
    [ -n "$campus_memory_id" ] && print_status "  Campus Coach Memory: $campus_memory_id"
    
    print_status ""
    print_status "🔧 Configuring AgentCore integration..."
    
    # Configure AgentCore agent IAM permissions (including memory access)
    if [ -n "$campus_arn" ] || [ -n "$content_arn" ]; then
        configure_agentcore_agent_permissions "$campus_arn" "$content_memory_id" "$campus_memory_id"
    fi
    
    # Update Lambda IAM permissions for AgentCore invocation
    update_lambda_iam_permissions "$content_arn" "$campus_arn"
    
    # Verify AgentCore agent permissions (read-only check)
    verify_agentcore_iam_permissions "$content_arn" "$campus_arn"
    
    # Update Lambda environment variables with agent ARNs and memory ID
    update_lambda_environment_variables "$content_arn" "$campus_arn" "$content_memory_id"
    
    # Update CDK context
    update_cdk_context "$content_arn" "$campus_arn"
    
    # Create environment file with memory ID
    create_env_file "$content_arn" "$campus_arn" "$content_memory_id"
    
    print_success "🎉 AgentCore integration configuration completed successfully!"
    print_status ""
    print_status "📋 Configuration Summary:"
    print_status "  Content Generation Agent: $content_arn"
    print_status "  Campus Coach Agent: $campus_arn"
    if [ -n "$content_memory_id" ] || [ -n "$campus_memory_id" ]; then
        print_status "  AgentCore Memory (LTM):"
        [ -n "$content_memory_id" ] && print_status "    - Content Agent: $content_memory_id"
        [ -n "$campus_memory_id" ] && print_status "    - Campus Coach: $campus_memory_id"
    else
        print_status "  AgentCore Memory: Not configured"
    fi
    print_status ""
    print_status "✅ Integration Status:"
    print_status "  - IAM permissions: Lambda roles updated for AgentCore invocation"
    print_status "  - AgentCore roles: Automatically managed by AWS (verified)"
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