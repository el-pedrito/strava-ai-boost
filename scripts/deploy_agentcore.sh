#!/bin/bash

# Deploy AgentCore Infrastructure for Strava AI Boost
# This script deploys AgentCore agents and memory using official CLI commands
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./deploy_agentcore.sh
#
# Or set profile inline:
#   AWS_PROFILE=your-aws-profile ./deploy_agentcore.sh

set -e

echo "🚀 Deploying AgentCore infrastructure for Strava AI Boost..."

# Configuration
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
MEMORY_NAME="strava-ai-boost-memory"
CONTENT_AGENT_NAME="contentgen"
CAMPUS_COACH_AGENT_NAME="campuscoach"

# Agent files
CONTENT_AGENT_FILE="src/agents/content_generation_agent.py"
CAMPUS_COACH_AGENT_FILE="src/agents/campus_coach_agent.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if AgentCore CLI is installed
if ! command -v agentcore &> /dev/null; then
    print_error "AgentCore CLI not found. Please install with:"
    print_error "  pip install agentcore-cli"
    print_error "Or follow installation guide: https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-cli.html"
    exit 1
fi

# Check if agent files exist
if [ ! -f "$CONTENT_AGENT_FILE" ]; then
    print_error "Content generation agent file not found: $CONTENT_AGENT_FILE"
    exit 1
fi

if [ ! -f "$CAMPUS_COACH_AGENT_FILE" ]; then
    print_error "Campus Coach agent file not found: $CAMPUS_COACH_AGENT_FILE"
    exit 1
fi

# Verify AWS credentials
print_status "Verifying AWS credentials for profile: $PROFILE"
if ! aws sts get-caller-identity --profile $PROFILE > /dev/null 2>&1; then
    print_error "AWS credentials not configured for profile: $PROFILE"
    print_error "Please configure with: aws configure --profile $PROFILE"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --profile $PROFILE --query Account --output text)
print_status "Using AWS Account: $ACCOUNT_ID"
print_status "Using AWS Profile: $PROFILE"
print_status "Using AWS Region: $REGION"

# Step 1: Configure AgentCore CLI
print_status "Configuring AgentCore CLI..."
agentcore configure --region $REGION --profile $PROFILE

if [ $? -ne 0 ]; then
    print_error "Failed to configure AgentCore CLI"
    exit 1
fi

# Step 2: Create AgentCore Memory with LTM strategies
print_status "Setting up AgentCore Memory: $MEMORY_NAME..."

# Check if memory already exists
if agentcore memory list --profile $PROFILE 2>/dev/null | grep -q "$MEMORY_NAME"; then
    print_warning "Memory $MEMORY_NAME already exists, skipping creation"
    MEMORY_ID=$(agentcore memory list --profile $PROFILE | grep "$MEMORY_NAME" | awk '{print $1}' || echo $MEMORY_NAME)
else
    print_status "Creating AgentCore Memory with semantic search strategy..."
    
    # Create memory with proper LTM strategy for personalization
    MEMORY_CREATION_OUTPUT=$(agentcore memory create \
        --name $MEMORY_NAME \
        --description "Personal style and expression memory for Strava AI Boost content generation" \
        --ltm-strategy "semantic_search" \
        --profile $PROFILE \
        --region $REGION 2>&1)
    
    if [ $? -eq 0 ]; then
        print_status "AgentCore Memory created successfully"
        # Extract memory ID from output (format may vary)
        MEMORY_ID=$(echo "$MEMORY_CREATION_OUTPUT" | grep -o 'mem_[a-zA-Z0-9]*' | head -1)
        if [ -z "$MEMORY_ID" ]; then
            MEMORY_ID=$MEMORY_NAME
        fi
    else
        print_error "Failed to create AgentCore Memory"
        echo "$MEMORY_CREATION_OUTPUT"
        exit 1
    fi
fi

print_status "Memory ID: $MEMORY_ID"

# Step 3: Deploy Content Generation Agent
print_status "Deploying Content Generation Agent: $CONTENT_AGENT_NAME..."

# Deploy agent with memory integration
CONTENT_DEPLOY_CMD="agentcore agent deploy \
    --name $CONTENT_AGENT_NAME \
    --runtime python \
    --file $CONTENT_AGENT_FILE \
    --description \"Strands Agent for personalized Strava content generation with AgentCore Memory\" \
    --profile $PROFILE \
    --region $REGION"

# Add memory integration if available
if [ -n "$MEMORY_ID" ]; then
    CONTENT_DEPLOY_CMD="$CONTENT_DEPLOY_CMD --memory $MEMORY_ID"
    print_status "Integrating Content Agent with memory: $MEMORY_ID"
fi

# Add environment variables for Lambda integration
CONTENT_DEPLOY_CMD="$CONTENT_DEPLOY_CMD \
    --env REGION=$REGION \
    --env PROFILE=$PROFILE \
    --env MEMORY_NAME=$MEMORY_NAME"

if eval $CONTENT_DEPLOY_CMD; then
    print_status "Content Generation Agent deployed successfully"
else
    print_error "Failed to deploy Content Generation Agent"
    exit 1
fi

# Step 4: Deploy Campus Coach Browser Agent
print_status "Deploying Campus Coach Browser Agent: $CAMPUS_COACH_AGENT_NAME..."

# Deploy browser agent with retry configuration
CAMPUS_DEPLOY_CMD="agentcore agent deploy \
    --name $CAMPUS_COACH_AGENT_NAME \
    --runtime browser \
    --file $CAMPUS_COACH_AGENT_FILE \
    --description \"AgentCore Browser Tool agent for Campus Coach session extraction with retry logic\" \
    --profile $PROFILE \
    --region $REGION"

# Add environment variables for Lambda integration
CAMPUS_DEPLOY_CMD="$CAMPUS_DEPLOY_CMD \
    --env REGION=$REGION \
    --env PROFILE=$PROFILE \
    --env MAX_RETRIES=3 \
    --env RETRY_DELAY=5"

if eval $CAMPUS_DEPLOY_CMD; then
    print_status "Campus Coach Browser Agent deployed successfully"
else
    print_error "Failed to deploy Campus Coach Browser Agent"
    exit 1
fi

# Step 5: Add IAM permissions for AWS services access
print_status "Adding IAM permissions for AWS services access..."

# Get Agent ARN and role name for Campus Coach agent
CAMPUS_AGENT_ARN=$(agentcore agent describe --name $CAMPUS_COACH_AGENT_NAME --profile $PROFILE | grep -o 'arn:aws:bedrock-agentcore:[^"]*' | head -1)
if [ -n "$CAMPUS_AGENT_ARN" ]; then
    # Extract role name from agent ARN or configuration
    CAMPUS_ROLE_NAME=$(agentcore agent describe --name $CAMPUS_COACH_AGENT_NAME --profile $PROFILE | grep -i "execution.*role" | awk -F'/' '{print $NF}' | head -1)
    
    if [ -n "$CAMPUS_ROLE_NAME" ]; then
        print_status "Adding permissions to Campus Coach agent role: $CAMPUS_ROLE_NAME"
        
        # Create IAM policy for Campus Coach agent
        cat > /tmp/campus-coach-permissions.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "SecretsManagerAccess",
            "Effect": "Allow",
            "Action": ["secretsmanager:GetSecretValue"],
            "Resource": [
                "arn:aws:secretsmanager:$REGION:*:secret:strava-ai-boost-campus-coach-*",
                "arn:aws:secretsmanager:$REGION:*:secret:campus-coach-credentials-*"
            ]
        },
        {
            "Sid": "DynamoDBAccess",
            "Effect": "Allow",
            "Action": [
                "dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem"
            ],
            "Resource": [
                "arn:aws:dynamodb:$REGION:*:table/campus-coaching-sessions",
                "arn:aws:dynamodb:$REGION:*:table/campus-coaching-sessions/index/*",
                "arn:aws:dynamodb:$REGION:*:table/strava-ai-boost-user-configuration",
                "arn:aws:dynamodb:$REGION:*:table/strava-ai-boost-user-configuration/index/*"
            ]
        },
        {
            "Sid": "BedrockAgentCoreBrowser",
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:StartBrowserSession",
                "bedrock-agentcore:StopBrowserSession",
                "bedrock-agentcore:GetBrowserSession",
                "bedrock-agentcore:ListBrowserSessions",
                "bedrock-agentcore:ConnectBrowserAutomationStream"
            ],
            "Resource": ["arn:aws:bedrock-agentcore:*:aws:browser/*"]
        }
    ]
}
EOF
        
        # Apply IAM policy to Campus Coach agent role
        aws iam put-role-policy \
            --role-name $CAMPUS_ROLE_NAME \
            --policy-name "CampusCoachAgentPermissions" \
            --policy-document file:///tmp/campus-coach-permissions.json \
            --region $REGION \
            --profile $PROFILE
        
        if [ $? -eq 0 ]; then
            print_status "IAM permissions added successfully to Campus Coach agent"
        else
            print_warning "Failed to add IAM permissions to Campus Coach agent"
        fi
        
        # Clean up temporary file
        rm -f /tmp/campus-coach-permissions.json
    else
        print_warning "Could not determine Campus Coach agent role name for IAM permissions"
    fi
else
    print_warning "Could not determine Campus Coach agent ARN for IAM permissions"
fi

# Get Agent ARN and role name for Content Generation agent
CONTENT_AGENT_ARN=$(agentcore agent describe --name $CONTENT_AGENT_NAME --profile $PROFILE | grep -o 'arn:aws:bedrock-agentcore:[^"]*' | head -1)
if [ -n "$CONTENT_AGENT_ARN" ]; then
    # Extract role name from agent ARN or configuration
    CONTENT_ROLE_NAME=$(agentcore agent describe --name $CONTENT_AGENT_NAME --profile $PROFILE | grep -i "execution.*role" | awk -F'/' '{print $NF}' | head -1)
    
    if [ -n "$CONTENT_ROLE_NAME" ]; then
        print_status "Adding permissions to Content Generation agent role: $CONTENT_ROLE_NAME"
        
        # Create IAM policy for Content Generation agent
        cat > /tmp/content-generation-permissions.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "DynamoDBMemoryAccess",
            "Effect": "Allow",
            "Action": [
                "dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem"
            ],
            "Resource": [
                "arn:aws:dynamodb:$REGION:*:table/strava-ai-boost-user-memory",
                "arn:aws:dynamodb:$REGION:*:table/strava-ai-boost-user-memory/index/*",
                "arn:aws:dynamodb:$REGION:*:table/strava-ai-boost-activities",
                "arn:aws:dynamodb:$REGION:*:table/strava-ai-boost-activities/index/*"
            ]
        },
        {
            "Sid": "BedrockAgentRuntimeAccess",
            "Effect": "Allow",
            "Action": [
                "bedrock-agent-runtime:InvokeAgent",
                "bedrock-agent-runtime:Retrieve",
                "bedrock-agent-runtime:RetrieveAndGenerate"
            ],
            "Resource": ["*"]
        }
    ]
}
EOF
        
        # Apply IAM policy to Content Generation agent role
        aws iam put-role-policy \
            --role-name $CONTENT_ROLE_NAME \
            --policy-name "ContentGenerationAgentPermissions" \
            --policy-document file:///tmp/content-generation-permissions.json \
            --region $REGION \
            --profile $PROFILE
        
        if [ $? -eq 0 ]; then
            print_status "IAM permissions added successfully to Content Generation agent"
        else
            print_warning "Failed to add IAM permissions to Content Generation agent"
        fi
        
        # Clean up temporary file
        rm -f /tmp/content-generation-permissions.json
    else
        print_warning "Could not determine Content Generation agent role name for IAM permissions"
    fi
else
    print_warning "Could not determine Content Generation agent ARN for IAM permissions"
fi

# Step 6: Verify deployments
print_status "Verifying AgentCore deployments..."

echo ""
echo "📋 AgentCore Memory Status:"
agentcore memory describe --name $MEMORY_NAME --profile $PROFILE || print_warning "Could not get memory status"

echo ""
echo "📋 AgentCore Agents Status:"
print_status "Content Generation Agent:"
agentcore agent describe --name $CONTENT_AGENT_NAME --profile $PROFILE || print_warning "Could not get content agent status"

echo ""
print_status "Campus Coach Browser Agent:"
agentcore agent describe --name $CAMPUS_COACH_AGENT_NAME --profile $PROFILE || print_warning "Could not get campus coach agent status"

# Step 7: Test agent connectivity
print_status "Testing agent connectivity..."

echo ""
print_status "Testing Content Generation Agent..."
agentcore agent test --name $CONTENT_AGENT_NAME --profile $PROFILE 2>/dev/null || print_warning "Agent test not supported or failed"

echo ""
print_status "Testing Campus Coach Browser Agent..."
agentcore agent test --name $CAMPUS_COACH_AGENT_NAME --profile $PROFILE 2>/dev/null || print_warning "Agent test not supported or failed"

echo ""
print_status "✅ AgentCore deployment complete!"
print_status "Memory: $MEMORY_NAME (ID: $MEMORY_ID)"
print_status "Content Agent: $CONTENT_AGENT_NAME"
print_status "Campus Coach Agent: $CAMPUS_COACH_AGENT_NAME"
print_status "Region: $REGION"
print_status "Profile: $PROFILE"

echo ""
print_warning "⚠️  Known Issues & Mitigations:"
print_warning "- Campus Coach Browser Agent has cold start issues (~30% first-try success rate)"
print_warning "- Retry logic implemented in Lambda invoker (3 attempts with exponential backoff)"
print_warning "- Memory provisioning may take 2-3 minutes to become fully active"
print_warning "- Browser automation requires warm-up time for first invocation"

echo ""
print_status "🎯 Next steps:"
echo "1. Wait for memory to become fully active (check status periodically)"
echo "2. Deploy CDK stacks: cdk deploy --all --profile $PROFILE"
echo "3. Update Lambda environment variables with AgentCore details"
echo "4. Configure Strava OAuth credentials in AWS Secrets Manager"
echo "5. Configure Campus Coach credentials in AWS Secrets Manager"
echo "6. Test end-to-end workflow with local web interface"

echo ""
print_status "📝 Environment Variables for Lambda Functions:"
echo "export AGENTCORE_MEMORY_NAME=$MEMORY_NAME"
echo "export AGENTCORE_MEMORY_ID=$MEMORY_ID"
echo "export CONTENT_GENERATION_AGENT_NAME=$CONTENT_AGENT_NAME"
echo "export CAMPUS_COACH_AGENT_NAME=$CAMPUS_COACH_AGENT_NAME"
echo "export AWS_REGION=$REGION"

echo ""
print_status "📊 Monitoring Commands:"
echo "# Check memory status:"
echo "agentcore memory describe --name $MEMORY_NAME --profile $PROFILE"
echo ""
echo "# Check agent status:"
echo "agentcore agent describe --name $CONTENT_AGENT_NAME --profile $PROFILE"
echo "agentcore agent describe --name $CAMPUS_COACH_AGENT_NAME --profile $PROFILE"
echo ""
echo "# Monitor agent logs:"
echo "aws logs tail /aws/bedrock-agentcore/runtimes/$CONTENT_AGENT_NAME-* --follow --profile $PROFILE --region $REGION"
echo "aws logs tail /aws/bedrock-agentcore/runtimes/$CAMPUS_COACH_AGENT_NAME-* --follow --profile $PROFILE --region $REGION"

# Export environment variables for subsequent scripts
export AGENTCORE_MEMORY_NAME=$MEMORY_NAME
export AGENTCORE_MEMORY_ID=$MEMORY_ID
export CONTENT_GENERATION_AGENT_NAME=$CONTENT_AGENT_NAME
export CAMPUS_COACH_AGENT_NAME=$CAMPUS_COACH_AGENT_NAME

print_status "Environment variables exported for subsequent scripts"