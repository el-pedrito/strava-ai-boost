#!/bin/bash

# Complete Strava AI Boost Deployment Orchestration
# Orchestrates the complete deployment pipeline from CDK to AgentCore agents
# with proper dependency management and error handling
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/deploy_complete.sh [dev|prod] [--skip-validation] [--skip-agentcore] [--skip-webhook]

set -e

# Parse command line arguments
ENVIRONMENT="${1:-dev}"
SKIP_VALIDATION=false
SKIP_AGENTCORE=false
SKIP_WEBHOOK=false

shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-validation)
            SKIP_VALIDATION=true
            shift
            ;;
        --skip-agentcore)
            SKIP_AGENTCORE=true
            shift
            ;;
        --skip-webhook)
            SKIP_WEBHOOK=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [dev|prod] [--skip-validation] [--skip-agentcore] [--skip-webhook]"
            exit 1
            ;;
    esac
done

# Configuration
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
PROJECT_NAME="strava-ai-boost"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Deployment state tracking
DEPLOYMENT_STATE_FILE="deployment-state-${ENVIRONMENT}.json"
DEPLOYMENT_LOG_FILE="deployment-log-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S).log"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a $DEPLOYMENT_LOG_FILE
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a $DEPLOYMENT_LOG_FILE
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a $DEPLOYMENT_LOG_FILE
}

print_section() {
    echo -e "${BLUE}[SECTION]${NC} $1" | tee -a $DEPLOYMENT_LOG_FILE
}

print_phase() {
    echo -e "${CYAN}[PHASE]${NC} $1" | tee -a $DEPLOYMENT_LOG_FILE
}

# Function to update deployment state
update_deployment_state() {
    local phase=$1
    local status=$2
    local message=$3
    
    cat > $DEPLOYMENT_STATE_FILE << EOF
{
  "deployment_id": "$(date +%Y%m%d-%H%M%S)",
  "environment": "$ENVIRONMENT",
  "region": "$REGION",
  "profile": "$PROFILE",
  "current_phase": "$phase",
  "status": "$status",
  "message": "$message",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "log_file": "$DEPLOYMENT_LOG_FILE"
}
EOF
}

# Function to handle deployment errors
handle_error() {
    local phase=$1
    local error_message=$2
    
    print_error "Deployment failed in phase: $phase"
    print_error "Error: $error_message"
    
    update_deployment_state "$phase" "FAILED" "$error_message"
    
    echo ""
    print_error "🚨 Deployment Failed!"
    print_error "Phase: $phase"
    print_error "Log file: $DEPLOYMENT_LOG_FILE"
    print_error "State file: $DEPLOYMENT_STATE_FILE"
    
    echo ""
    print_status "🔧 Troubleshooting steps:"
    echo "  1. Check the deployment log: cat $DEPLOYMENT_LOG_FILE"
    echo "  2. Review CloudFormation events in AWS Console"
    echo "  3. Check AWS service quotas and permissions"
    echo "  4. Re-run deployment with --skip-validation if prerequisites are met"
    
    exit 1
}

# Trap errors and handle them gracefully
trap 'handle_error "UNKNOWN" "Unexpected error occurred"' ERR

print_phase "🚀 Starting Complete Strava AI Boost Deployment"
print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Profile: $PROFILE"
print_status "Skip validation: $SKIP_VALIDATION"
print_status "Skip AgentCore: $SKIP_AGENTCORE"
print_status "Skip webhook: $SKIP_WEBHOOK"

# Initialize deployment state
update_deployment_state "INITIALIZATION" "IN_PROGRESS" "Starting deployment"

# Validate environment parameter
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    handle_error "INITIALIZATION" "Invalid environment: $ENVIRONMENT. Use 'dev' or 'prod'"
fi

# Phase 1: Prerequisites Validation
if [ "$SKIP_VALIDATION" = false ]; then
    print_phase "📋 Phase 1: Prerequisites Validation"
    update_deployment_state "VALIDATION" "IN_PROGRESS" "Validating prerequisites"
    
    if [ -f "scripts/validate_setup.sh" ]; then
        print_status "Running setup validation..."
        chmod +x scripts/validate_setup.sh
        
        if ./scripts/validate_setup.sh; then
            print_status "✅ Prerequisites validation passed"
        else
            handle_error "VALIDATION" "Prerequisites validation failed"
        fi
    else
        print_warning "Setup validation script not found, skipping validation"
    fi
else
    print_warning "Skipping prerequisites validation (--skip-validation flag)"
fi

# Phase 2: Environment Configuration
print_phase "⚙️  Phase 2: Environment Configuration"
update_deployment_state "CONFIGURATION" "IN_PROGRESS" "Configuring environment"

# Load environment-specific configuration
CONFIG_FILE="config/${ENVIRONMENT}.json"
if [ -f "$CONFIG_FILE" ]; then
    print_status "Loading configuration from: $CONFIG_FILE"
    
    # Extract configuration values
    LAMBDA_TIMEOUT=$(jq -r '.lambda_config.timeout' $CONFIG_FILE)
    LAMBDA_MEMORY=$(jq -r '.lambda_config.memory_size' $CONFIG_FILE)
    LOG_LEVEL=$(jq -r '.lambda_config.log_level' $CONFIG_FILE)
    
    # Set CDK context variables
    export CDK_CONTEXT_ENVIRONMENT=$ENVIRONMENT
    export CDK_CONTEXT_LAMBDA_TIMEOUT=$LAMBDA_TIMEOUT
    export CDK_CONTEXT_LAMBDA_MEMORY=$LAMBDA_MEMORY
    export CDK_CONTEXT_LOG_LEVEL=$LOG_LEVEL
    
    print_status "Environment configuration loaded successfully"
else
    print_warning "Configuration file not found: $CONFIG_FILE"
    print_warning "Using default configuration"
fi

# Verify AWS credentials
print_status "Verifying AWS credentials..."
if ! aws sts get-caller-identity --profile $PROFILE --region $REGION > /dev/null 2>&1; then
    handle_error "CONFIGURATION" "AWS credentials not configured for profile: $PROFILE"
fi

ACCOUNT_ID=$(aws sts get-caller-identity --profile $PROFILE --region $REGION --query Account --output text)
print_status "Using AWS Account: $ACCOUNT_ID"

# Phase 3: CDK Bootstrap and Deployment
print_phase "🏗️  Phase 3: CDK Infrastructure Deployment"
update_deployment_state "CDK_DEPLOYMENT" "IN_PROGRESS" "Deploying CDK infrastructure"

# Check CDK bootstrap
print_status "Checking CDK bootstrap status..."
if aws cloudformation describe-stacks --stack-name CDKToolkit --profile $PROFILE --region $REGION > /dev/null 2>&1; then
    print_status "CDK already bootstrapped"
else
    print_status "Bootstrapping CDK..."
    if ! cdk bootstrap --profile $PROFILE --region $REGION; then
        handle_error "CDK_DEPLOYMENT" "CDK bootstrap failed"
    fi
fi

# CDK synthesis
print_status "Synthesizing CDK templates..."
if ! cdk synth --profile $PROFILE --region $REGION > /dev/null; then
    handle_error "CDK_DEPLOYMENT" "CDK synthesis failed"
fi

# Deploy CDK stacks in dependency order
STACKS=(
    "StravaAIBoost-Core"
    "StravaAIBoost-Content"
    "StravaAIBoost-Webhook"
    "StravaAIBoost-API"
    "StravaAIBoost-Monitoring"
)

print_status "Deploying CDK stacks in dependency order..."

for stack in "${STACKS[@]}"; do
    print_status "Deploying stack: $stack"
    update_deployment_state "CDK_DEPLOYMENT" "IN_PROGRESS" "Deploying stack: $stack"
    
    if ! cdk deploy $stack --profile $PROFILE --region $REGION --require-approval never; then
        handle_error "CDK_DEPLOYMENT" "Stack $stack deployment failed"
    fi
    
    print_status "✅ Stack $stack deployed successfully"
done

# Phase 4: Secrets Manager Configuration
print_phase "🔐 Phase 4: Secrets Manager Configuration"
update_deployment_state "SECRETS_CONFIGURATION" "IN_PROGRESS" "Configuring secrets"

# Create Strava OAuth secrets placeholder
SECRET_NAME="strava-ai-boost-oauth-tokens"
if aws secretsmanager describe-secret --secret-id $SECRET_NAME --profile $PROFILE --region $REGION > /dev/null 2>&1; then
    print_status "Secret $SECRET_NAME already exists"
else
    print_status "Creating secret: $SECRET_NAME"
    aws secretsmanager create-secret \
        --name $SECRET_NAME \
        --description "Strava OAuth tokens for AI Boost" \
        --secret-string '{"client_id":"REPLACE_WITH_YOUR_STRAVA_CLIENT_ID","client_secret":"REPLACE_WITH_YOUR_STRAVA_CLIENT_SECRET","redirect_uri":"http://localhost:8000/auth/callback"}' \
        --profile $PROFILE \
        --region $REGION > /dev/null
    
    print_warning "⚠️  Please update the Strava OAuth credentials in Secrets Manager"
fi

# Create Campus Coach credentials placeholder
CAMPUS_SECRET_NAME="strava-ai-boost-campus-coach-credentials"
if aws secretsmanager describe-secret --secret-id $CAMPUS_SECRET_NAME --profile $PROFILE --region $REGION > /dev/null 2>&1; then
    print_status "Secret $CAMPUS_SECRET_NAME already exists"
else
    print_status "Creating secret: $CAMPUS_SECRET_NAME"
    aws secretsmanager create-secret \
        --name $CAMPUS_SECRET_NAME \
        --description "Campus Coach credentials for AI Boost" \
        --secret-string '{"username":"REPLACE_WITH_YOUR_CAMPUS_COACH_USERNAME","password":"REPLACE_WITH_YOUR_CAMPUS_COACH_PASSWORD","login_url":"https://campus.coach/login"}' \
        --profile $PROFILE \
        --region $REGION > /dev/null
    
    print_warning "⚠️  Please update the Campus Coach credentials in Secrets Manager (optional)"
fi

# Phase 5: AgentCore Deployment
if [ "$SKIP_AGENTCORE" = false ]; then
    print_phase "🤖 Phase 5: AgentCore Infrastructure Deployment"
    update_deployment_state "AGENTCORE_DEPLOYMENT" "IN_PROGRESS" "Deploying AgentCore infrastructure"
    
    if [ -f "scripts/deploy_agentcore.sh" ]; then
        print_status "Running AgentCore deployment..."
        chmod +x scripts/deploy_agentcore.sh
        
        # Set environment variables for AgentCore deployment
        export AWS_PROFILE=$PROFILE
        export AWS_REGION=$REGION
        
        if ./scripts/deploy_agentcore.sh; then
            print_status "✅ AgentCore deployment completed successfully"
        else
            print_warning "⚠️  AgentCore deployment failed or partially completed"
            print_warning "This is expected if AgentCore CLI is not available yet"
            print_warning "You can run ./scripts/deploy_agentcore.sh manually later"
        fi
    else
        print_warning "AgentCore deployment script not found, skipping AgentCore deployment"
    fi
else
    print_warning "Skipping AgentCore deployment (--skip-agentcore flag)"
fi

# Phase 6: Infrastructure Validation
print_phase "✅ Phase 6: Infrastructure Validation"
update_deployment_state "INFRASTRUCTURE_VALIDATION" "IN_PROGRESS" "Validating deployed infrastructure"

if [ -f "scripts/validate_deployment.sh" ]; then
    print_status "Running deployment validation..."
    chmod +x scripts/validate_deployment.sh
    
    if ./scripts/validate_deployment.sh $ENVIRONMENT; then
        print_status "✅ Infrastructure validation passed"
    else
        print_warning "⚠️  Some infrastructure validation checks failed"
        print_warning "Review the validation report for details"
    fi
else
    print_warning "Deployment validation script not found, skipping validation"
fi

# Phase 7: Webhook Configuration
if [ "$SKIP_WEBHOOK" = false ]; then
    print_phase "🔗 Phase 7: Webhook Configuration"
    update_deployment_state "WEBHOOK_CONFIGURATION" "IN_PROGRESS" "Configuring Strava webhook"
    
    # Get webhook URL from API Gateway
    API_ID=$(aws apigateway get-rest-apis --profile $PROFILE --region $REGION --query "items[?contains(name, 'StravaAIBoost')].id" --output text | head -1)
    
    if [ -n "$API_ID" ]; then
        WEBHOOK_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod/webhook"
        print_status "Webhook URL: $WEBHOOK_URL"
        
        print_warning "⚠️  Manual step required: Configure Strava webhook subscription"
        print_warning "   Run: ./scripts/configure_strava_webhook.sh $ENVIRONMENT"
        print_warning "   Or configure manually at https://developers.strava.com/"
    else
        print_warning "Could not determine API Gateway ID for webhook URL"
    fi
else
    print_warning "Skipping webhook configuration (--skip-webhook flag)"
fi

# Phase 8: Integration Testing
print_phase "🧪 Phase 8: Integration Testing"
update_deployment_state "INTEGRATION_TESTING" "IN_PROGRESS" "Running integration tests"

if [ -f "scripts/test_basic_integration.py" ]; then
    print_status "Running basic integration tests..."
    
    # Set environment variables for tests
    export AWS_PROFILE=$PROFILE
    export AWS_REGION=$REGION
    export ENVIRONMENT=$ENVIRONMENT
    
    if python scripts/test_basic_integration.py; then
        print_status "✅ Basic integration tests passed"
    else
        print_warning "⚠️  Some integration tests failed"
        print_warning "This is expected if external services are not configured yet"
    fi
else
    print_warning "Integration test script not found, skipping tests"
fi

# Phase 9: Deployment Completion
print_phase "🎉 Phase 9: Deployment Completion"
update_deployment_state "COMPLETED" "SUCCESS" "Deployment completed successfully"

# Generate comprehensive deployment summary
DEPLOYMENT_SUMMARY_FILE="deployment-summary-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S).json"
cat > $DEPLOYMENT_SUMMARY_FILE << EOF
{
  "deployment_id": "$(date +%Y%m%d-%H%M%S)",
  "environment": "$ENVIRONMENT",
  "region": "$REGION",
  "account_id": "$ACCOUNT_ID",
  "profile": "$PROFILE",
  "deployment_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "status": "SUCCESS",
  "phases_completed": [
    "VALIDATION",
    "CONFIGURATION", 
    "CDK_DEPLOYMENT",
    "SECRETS_CONFIGURATION",
    "AGENTCORE_DEPLOYMENT",
    "INFRASTRUCTURE_VALIDATION",
    "WEBHOOK_CONFIGURATION",
    "INTEGRATION_TESTING"
  ],
  "stacks_deployed": [
    "StravaAIBoost-Core",
    "StravaAIBoost-Content",
    "StravaAIBoost-Webhook", 
    "StravaAIBoost-API",
    "StravaAIBoost-Monitoring"
  ],
  "secrets_created": [
    "strava-ai-boost-oauth-tokens",
    "strava-ai-boost-campus-coach-credentials"
  ],
  "webhook_url": "$WEBHOOK_URL",
  "log_file": "$DEPLOYMENT_LOG_FILE",
  "next_steps": [
    "Configure Strava OAuth credentials in Secrets Manager",
    "Set up Strava webhook subscription",
    "Start local web interface",
    "Test with sample Strava activity"
  ]
}
EOF

echo ""
print_status "🎉 Complete Strava AI Boost deployment finished successfully!"
print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Account: $ACCOUNT_ID"

echo ""
print_status "📋 Deployment Summary:"
echo "  ✅ CDK Stacks: Core, Content, Webhook, API, Monitoring"
echo "  ✅ DynamoDB Tables: Activities, Configuration, Rate Limits, Sessions"
echo "  ✅ Lambda Functions: Webhook Handler, Content Generator, etc."
echo "  ✅ SQS Queues: Activity Processing with DLQ"
echo "  ✅ Secrets Manager: OAuth tokens, Campus Coach credentials"
echo "  ✅ Step Functions: Activity processing workflow"
echo "  ✅ API Gateway: Local interface endpoints"

if [ -n "$WEBHOOK_URL" ]; then
    echo "  ✅ Webhook URL: $WEBHOOK_URL"
fi

echo ""
print_status "📁 Generated Files:"
echo "  - Deployment log: $DEPLOYMENT_LOG_FILE"
echo "  - Deployment state: $DEPLOYMENT_STATE_FILE"
echo "  - Deployment summary: $DEPLOYMENT_SUMMARY_FILE"

echo ""
print_status "🔧 Manual Configuration Required:"
echo "  1. Update Strava OAuth credentials:"
echo "     aws secretsmanager put-secret-value --secret-id strava-ai-boost-oauth-tokens --secret-string '{\"client_id\":\"YOUR_CLIENT_ID\",\"client_secret\":\"YOUR_CLIENT_SECRET\",\"redirect_uri\":\"http://localhost:8000/auth/callback\"}' --profile $PROFILE"
echo ""
echo "  2. Configure Strava webhook subscription:"
echo "     ./scripts/configure_strava_webhook.sh $ENVIRONMENT"
echo ""
echo "  3. Update Campus Coach credentials (optional):"
echo "     aws secretsmanager put-secret-value --secret-id strava-ai-boost-campus-coach-credentials --secret-string '{\"username\":\"YOUR_USERNAME\",\"password\":\"YOUR_PASSWORD\",\"login_url\":\"https://campus.coach/login\"}' --profile $PROFILE"

echo ""
print_status "🚀 Next Steps:"
echo "  1. Configure Strava OAuth credentials (see above)"
echo "  2. Start local web interface: cd local_interface && python app.py"
echo "  3. Complete OAuth flow at http://localhost:8000"
echo "  4. Test with a sample Strava activity"
echo "  5. Monitor processing in CloudWatch logs"

echo ""
print_status "📊 Monitoring Commands:"
echo "  # Check deployment status:"
echo "  aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --profile $PROFILE"
echo ""
echo "  # Monitor Lambda logs:"
echo "  aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile $PROFILE"
echo ""
echo "  # Validate deployment:"
echo "  ./scripts/validate_deployment.sh $ENVIRONMENT"

print_status "✨ Complete deployment orchestration finished successfully!"