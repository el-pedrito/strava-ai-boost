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
AWS_PROFILE="${AWS_PROFILE:-your-aws-profile}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Only pass --profile when that profile actually carries usable credentials.
#
# Passing --profile makes the AWS CLI ignore credentials supplied through the
# environment (AWS_ACCESS_KEY_ID and friends), which is how sandboxes, CI runners
# and assumed-role sessions provide them. With `set -e` above, a --profile call
# that fails to locate credentials aborts the script before its own error guard
# can report anything, which surfaces as an unexplained failure.
AWS_PROFILE_ARGS=""
if aws sts get-caller-identity --profile "$AWS_PROFILE" >/dev/null 2>&1; then
    AWS_PROFILE_ARGS="--profile $AWS_PROFILE"
elif aws sts get-caller-identity >/dev/null 2>&1; then
    echo "INFO: profile '$AWS_PROFILE' unusable, falling back to ambient AWS credentials" >&2
    unset AWS_PROFILE
else
    echo "ERROR: no usable AWS credentials (neither profile '$AWS_PROFILE' nor the environment)" >&2
    exit 1
fi

# Agent and memory names
CONTENT_AGENT_NAME="content_gen"
COACH_AGENT_NAME="strava_ai_boost_coach"
CONTENT_MEMORY_NAME="content_gen_mem"

# Central Bedrock model registry (src/config/llm_config.py) — single source
# of truth. Injected into every runtime as BEDROCK_MODEL_ID.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEDROCK_MODEL_ID_CENTRAL=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR/../src')
from config.llm_config import get_bedrock_model_id
print(get_bedrock_model_id())" 2>/dev/null || echo "")
if [ -z "$BEDROCK_MODEL_ID_CENTRAL" ]; then
    echo "ERROR: could not read the model registry (src/config/llm_config.py)" >&2
    exit 1
fi

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

# Function to tag AgentCore resources (runtimes + memories + IAM roles) with cost allocation tags
# Delegates to scripts/tag_agentcore_resources.sh (DRY — same logic callable standalone)
tag_agentcore_resources() {
    print_status "Applying cost allocation tags to AgentCore resources..."
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    TAGS_PROJECT="$TAGS_PROJECT" \
    ENVIRONMENT="$TAGS_ENVIRONMENT" \
    OWNER_TAG="$TAGS_OWNER" \
    TAGS_COST_CENTER="$TAGS_COST_CENTER" \
    TAGS_MANAGED_BY="$TAGS_MANAGED_BY" \
    AWS_REGION="$AWS_REGION" \
    AWS_PROFILE="${AWS_PROFILE:-}" \
        bash "$script_dir/tag_agentcore_resources.sh"
}

# Function to get memory ID from AWS
get_memory_id() {
    local memory_name="$1"
    
    # Use AgentCore Python toolkit to list memories and match by ID prefix
    # (the list API returns id/memoryId but not a separate 'name' field)
    local memory_id=$(python3 << EOF
from bedrock_agentcore_starter_toolkit.operations.memory.manager import MemoryManager

try:
    manager = MemoryManager(region_name='$AWS_REGION')
    memories = manager.list_memories()
    
    for memory in memories:
        mem_id = memory.get('id') or memory.get('memoryId', '')
        if mem_id.startswith('$memory_name'):
            print(mem_id)
            break
except Exception:
    pass
EOF
)
    
    # If toolkit doesn't work, try from YAML
    if [ -z "$memory_id" ] && [ -f ".bedrock_agentcore.yaml" ]; then
        memory_id=$(grep -B 2 "memory_name: ${memory_name}" .bedrock_agentcore.yaml | grep "memory_id:" | head -1 | awk '{print $2}' | tr -d "'" || echo "")
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

# Function to add guardrail environment variables to YAML
update_agent_guardrail_config() {
    local agent_name="$1"
    local guardrail_id="$2"
    local guardrail_version="$3"
    
    print_status "📝 Adding guardrail config to $agent_name YAML..."
    
    if [ ! -f ".bedrock_agentcore.yaml" ]; then
        print_error ".bedrock_agentcore.yaml not found!"
        return 1
    fi
    
    # Update YAML using Python
    AGENT_NAME="$agent_name" GUARDRAIL_ID="$guardrail_id" GUARDRAIL_VERSION="$guardrail_version" python3 << 'EOF'
import yaml
import sys
import os

try:
    agent_name = os.environ['AGENT_NAME']
    guardrail_id = os.environ['GUARDRAIL_ID']
    guardrail_version = os.environ['GUARDRAIL_VERSION']
    
    with open('.bedrock_agentcore.yaml', 'r') as f:
        config = yaml.safe_load(f) or {}
    
    if 'agents' not in config or agent_name not in config['agents']:
        print(f"✗ Agent {agent_name} not found in YAML", file=sys.stderr)
        sys.exit(1)
    
    # Add environment variables section if not exists
    if 'environment' not in config['agents'][agent_name]:
        config['agents'][agent_name]['environment'] = {}
    
    # Set guardrail environment variables
    config['agents'][agent_name]['environment']['GUARDRAIL_ENABLED'] = 'true'
    config['agents'][agent_name]['environment']['GUARDRAIL_ID'] = guardrail_id
    config['agents'][agent_name]['environment']['GUARDRAIL_VERSION'] = guardrail_version
    
    with open('.bedrock_agentcore.yaml', 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    print(f"✓ Added guardrail config to {agent_name}")
    sys.exit(0)
except Exception as e:
    print(f"✗ Failed to update YAML: {e}", file=sys.stderr)
    sys.exit(1)
EOF
    
    if [ $? -eq 0 ]; then
        print_success "Guardrail configuration added to $agent_name"
    else
        print_error "Failed to add guardrail configuration"
        return 1
    fi
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
    
    # Launch agent with environment variables
    print_status "Deploying agent: $agent_name..."
    
    # Get guardrail configuration from .env.agentcore
    GUARDRAIL_ENABLED=$(grep "^GUARDRAIL_ENABLED=" .env.agentcore 2>/dev/null | cut -d'=' -f2 || echo "false")
    GUARDRAIL_ID=$(grep "^GUARDRAIL_ID=" .env.agentcore 2>/dev/null | cut -d'=' -f2 || echo "")
    GUARDRAIL_VERSION=$(grep "^GUARDRAIL_VERSION=" .env.agentcore 2>/dev/null | cut -d'=' -f2 || echo "1")
    
    # Build agentcore deploy command with environment variables
    DEPLOY_CMD="agentcore deploy --agent $agent_name --auto-update-on-conflict"

    # Central model registry
    DEPLOY_CMD="$DEPLOY_CMD --env BEDROCK_MODEL_ID=$BEDROCK_MODEL_ID_CENTRAL"
    
    # Add memory ID
    DEPLOY_CMD="$DEPLOY_CMD --env BEDROCK_AGENTCORE_MEMORY_ID=$memory_id"
    
    # Add guardrail variables if enabled
    if [ "$GUARDRAIL_ENABLED" = "true" ] && [ -n "$GUARDRAIL_ID" ]; then
        print_status "🛡️  Guardrails enabled: $GUARDRAIL_ID v$GUARDRAIL_VERSION"
        DEPLOY_CMD="$DEPLOY_CMD --env GUARDRAIL_ENABLED=true"
        DEPLOY_CMD="$DEPLOY_CMD --env GUARDRAIL_ID=$GUARDRAIL_ID"
        DEPLOY_CMD="$DEPLOY_CMD --env GUARDRAIL_VERSION=$GUARDRAIL_VERSION"
    else
        print_status "⚠️  Guardrails not configured (GUARDRAIL_ENABLED=$GUARDRAIL_ENABLED)"
    fi
    
    # Execute deployment
    eval $DEPLOY_CMD || {
        print_error "Failed to deploy $agent_name"
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
deploy_coach_chat_runtime() {
    # Conversational coach on AgentCore Runtime (chantier A1+A2b):
    # AGUI protocol + Cognito customJWT authorizer + DynamoDB tool permissions.
    # Fully self-contained: discovers Cognito from CloudFormation outputs.
    local agent_name="coach_chat"
    local memory_id="$1"

    print_status ""
    print_status "🤖 Deploying conversational coach runtime: $agent_name (AGUI + customJWT)..."

    # Discover Cognito User Pool + client from the Frontend stack outputs
    local pool_id client_id
    pool_id=$(aws cloudformation describe-stacks --stack-name StravaAIBoost-Frontend \
        --region "$AWS_REGION" ${AWS_PROFILE_ARGS} \
        --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' --output text 2>/dev/null)
    client_id=$(aws cloudformation describe-stacks --stack-name StravaAIBoost-Frontend \
        --region "$AWS_REGION" ${AWS_PROFILE_ARGS} \
        --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' --output text 2>/dev/null)
    if [ -z "$pool_id" ] || [ -z "$client_id" ]; then
        print_error "Could not discover Cognito pool/client from StravaAIBoost-Frontend outputs"
        return 1
    fi
    # The frontend sends the Cognito ID token: validate its `aud` claim
    # (allowedAudience), NOT client_id (see design doc deploy notes).
    local authorizer_config="{\"customJWTAuthorizer\":{\"discoveryUrl\":\"https://cognito-idp.${AWS_REGION}.amazonaws.com/${pool_id}/.well-known/openid-configuration\",\"allowedAudience\":[\"${client_id}\"]}}"

    print_status "Configuring $agent_name (protocol AGUI, audience $client_id)"
    agentcore configure \
        --entrypoint "src/coach_chat/coach_chat_agent.py" \
        --name "$agent_name" \
        --region "$AWS_REGION" \
        --requirements-file "src/coach_chat/requirements.txt" \
        --deployment-type direct_code_deploy \
        --runtime PYTHON_3_12 \
        --protocol AGUI \
        --disable-memory \
        --authorizer-config "$authorizer_config" \
        --non-interactive || { print_error "Failed to configure $agent_name"; return 1; }

    # Guardrail (same resource as the content pipeline) + default identity
    local guardrail_id guardrail_version default_user_id
    guardrail_id=$(grep "^GUARDRAIL_ID=" .env.agentcore 2>/dev/null | cut -d'=' -f2 || echo "")
    guardrail_version=$(grep "^GUARDRAIL_VERSION=" .env.agentcore 2>/dev/null | cut -d'=' -f2 || echo "1")
    default_user_id=$(python3 -c "import json;print(json.load(open('cdk.context.json')).get('default_user_id',''))" 2>/dev/null || echo "")

    local deploy_cmd="agentcore deploy --agent $agent_name --auto-update-on-conflict"
    deploy_cmd="$deploy_cmd --env BEDROCK_MODEL_ID=$BEDROCK_MODEL_ID_CENTRAL"
    deploy_cmd="$deploy_cmd --env BEDROCK_AGENTCORE_MEMORY_ID=$memory_id"
    [ -n "$guardrail_id" ] && deploy_cmd="$deploy_cmd --env GUARDRAIL_ID=$guardrail_id --env GUARDRAIL_VERSION=$guardrail_version"
    [ -n "$default_user_id" ] && deploy_cmd="$deploy_cmd --env DEFAULT_USER_ID=$default_user_id"

    eval $deploy_cmd || { print_error "Failed to deploy $agent_name"; return 1; }

    # Grant the execution role read access for the agent's data tools
    # (auto-created policy covers Bedrock/logs but NOT DynamoDB nor Memory data plane).
    local account_id role_name
    account_id=$(aws sts get-caller-identity ${AWS_PROFILE_ARGS} --query Account --output text)
    role_name=$(grep -A 40 "^  ${agent_name}:" .bedrock_agentcore.yaml | grep "execution_role:" | head -1 | awk -F'role/' '{print $2}')
    if [ -z "$role_name" ]; then
        print_error "Could not resolve $agent_name execution role from .bedrock_agentcore.yaml"
        return 1
    fi
    print_status "Attaching tool data-access policy to role: $role_name"
    aws iam put-role-policy ${AWS_PROFILE_ARGS} \
        --role-name "$role_name" \
        --policy-name "CoachChatToolsDataAccess" \
        --policy-document "{
          \"Version\": \"2012-10-17\",
          \"Statement\": [
            {
              \"Sid\": \"ActivitiesRead\",
              \"Effect\": \"Allow\",
              \"Action\": [\"dynamodb:Query\"],
              \"Resource\": [
                \"arn:aws:dynamodb:${AWS_REGION}:${account_id}:table/strava-ai-boost-activities\",
                \"arn:aws:dynamodb:${AWS_REGION}:${account_id}:table/strava-ai-boost-activities/index/*\"
              ]
            },
            {
              \"Sid\": \"UserConfigRead\",
              \"Effect\": \"Allow\",
              \"Action\": [\"dynamodb:GetItem\"],
              \"Resource\": \"arn:aws:dynamodb:${AWS_REGION}:${account_id}:table/strava-ai-boost-user-configuration\"
            },
            {
              \"Sid\": \"CampusSessionsRead\",
              \"Effect\": \"Allow\",
              \"Action\": [\"dynamodb:Scan\"],
              \"Resource\": \"arn:aws:dynamodb:${AWS_REGION}:${account_id}:table/strava-ai-boost-campus-coaching-sessions\"
            },
            {
              \"Sid\": \"MemoryDataPlane\",
              \"Effect\": \"Allow\",
              \"Action\": [\"bedrock-agentcore:CreateEvent\", \"bedrock-agentcore:RetrieveMemoryRecords\"],
              \"Resource\": \"arn:aws:bedrock-agentcore:${AWS_REGION}:${account_id}:memory/${memory_id}\"
            }
          ]
        }" || { print_error "Failed to attach data-access policy"; return 1; }

    local agent_arn
    agent_arn=$(grep -A 40 "^  ${agent_name}:" .bedrock_agentcore.yaml | grep "agent_arn:" | head -1 | awk '{print $2}')
    print_success "$agent_name deployed: $agent_arn"
    print_status "➡️  Frontend activation (phase A): set coachRuntimeArn=\"$agent_arn\" in frontend/public/config.json"
    echo "$agent_arn"
}


main() {
    print_status "🚀 Starting AgentCore agent deployment with LTM..."
    
    # Propagate the profile only when one is actually usable: exporting an empty
    # AWS_PROFILE would make boto3 look for a profile that does not exist and
    # ignore the ambient credentials we just validated.
    if [ -n "${AWS_PROFILE:-}" ]; then
        export AWS_PROFILE="$AWS_PROFILE"
    fi
    export AWS_DEFAULT_REGION="$AWS_REGION"
    
    # Check prerequisites
    check_agentcore_cli

    # Enable AWS X-Ray Transaction Search for CloudWatch GenAI Observability Dashboard
    print_status ""
    print_status "🔭 Enabling AgentCore Observability prerequisites..."
    bash "$(dirname "${BASH_SOURCE[0]}")/enable_agentcore_observability.sh" || \
        print_warning "Observability setup warnings (non-fatal)"

    # Verify memories exist
    print_status ""
    print_status "🔍 Verifying LTM memories exist..."
    
    local content_mem_id=$(get_memory_id "$CONTENT_MEMORY_NAME")
    
    if [ -z "$content_mem_id" ]; then
        print_error "LTM memories not found!"
        print_status "Please run: ./scripts/create_agentcore_memories.sh first"
        print_status ""
        print_status "Then wait ~2 minutes for memories to become ACTIVE"
        print_status "Check status with: agentcore memory list --region $AWS_REGION"
        exit 1
    fi
    
    print_success "Found LTM memories:"
    print_status "  - $CONTENT_MEMORY_NAME: $content_mem_id"
    
    # Deploy agents
    print_status ""
    print_status "📦 Deploying agents with LTM..."
    
    local content_arn=""
    
    # Deploy content generation agent
    if content_arn=$(deploy_agent_with_ltm "$CONTENT_AGENT_NAME" "src/agents/content_agent.py" "$CONTENT_MEMORY_NAME"); then
        print_success "✅ Content Generation Agent deployed"
    else
        print_error "❌ Content Generation Agent deployment failed"
        exit 1
    fi
    
    # Deploy coach agent (shares content_gen_mem with coaching_observations namespace)
    local coach_arn=""
    if coach_arn=$(deploy_agent_with_ltm "$COACH_AGENT_NAME" "src/agents/coach_agent.py" "$CONTENT_MEMORY_NAME"); then
        print_success "✅ Coach Agent deployed"
    else
        print_error "❌ Coach Agent deployment failed"
        exit 1
    fi

    # Conversational coach runtime (A1+A2b): AGUI + customJWT + tool permissions
    if coach_chat_arn=$(deploy_coach_chat_runtime "$content_mem_id"); then
        print_success "✅ Coach Chat runtime deployed"
    else
        print_error "❌ Coach Chat runtime deployment failed"
        exit 1
    fi
    
    # Apply cost allocation tags to all AgentCore resources
    tag_agentcore_resources

    # Configure UserPreferenceStrategy on content_gen_mem (Haiku extraction/consolidation)
    # Idempotent: adds strategy if missing, updates modelId if already present.
    print_status ""
    print_status "🧠 Configuring Memory UserPreferenceStrategy (Haiku 4.5)..."
    if python3 "$(dirname "${BASH_SOURCE[0]}")/configure_memory_strategy.py"; then
        print_success "Memory strategy configured"
    else
        print_warning "Memory strategy configuration failed (non-fatal)"
    fi

    # Summary
    print_success ""
    print_success "🎉 AgentCore agents deployed successfully with LTM!"
    print_status ""
    print_status "📋 Deployment Summary:"
    print_status "  Memory Type: Long-Term Memory (LTM) with semantic search"
    print_status "  Memory Retention: 365 days"
    print_status "  Content Agent: $content_arn"
    print_status "  Coach Agent: $coach_arn"
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
