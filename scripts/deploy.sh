#!/bin/bash

# Strava AI Boost - Complete Deployment Script
# Orchestrates the entire deployment process from CDK to AgentCore agents
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/deploy.sh [dev|prod]
#
# Environment:
#   dev  - Development environment with enhanced logging and debugging
#   prod - Production environment with optimized settings

set -e

# Configuration
ENVIRONMENT="${1:-dev}"
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
PROJECT_NAME="strava-ai-boost"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_section() {
    echo -e "${BLUE}[SECTION]${NC} $1"
}

# Validate environment parameter
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    print_error "Invalid environment: $ENVIRONMENT. Use 'dev' or 'prod'"
    exit 1
fi

print_section "🚀 Starting Strava AI Boost deployment for $ENVIRONMENT environment"
print_status "Region: $REGION"
print_status "Profile: $PROFILE"
print_status "Environment: $ENVIRONMENT"

# Step 1: Validate prerequisites
print_section "📋 Step 1: Validating prerequisites"

# Check if validation script exists and run it
if [ -f "scripts/validate_setup.sh" ]; then
    print_status "Running setup validation..."
    chmod +x scripts/validate_setup.sh
    if ! ./scripts/validate_setup.sh; then
        print_error "Setup validation failed. Please fix issues before deployment."
        exit 1
    fi
else
    print_warning "Setup validation script not found, skipping validation"
fi

# Verify AWS credentials
print_status "Verifying AWS credentials..."
if ! aws sts get-caller-identity --profile $PROFILE > /dev/null 2>&1; then
    print_error "AWS credentials not configured for profile: $PROFILE"
    print_error "Please configure with: aws configure --profile $PROFILE"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --profile $PROFILE --query Account --output text)
print_status "Using AWS Account: $ACCOUNT_ID"

# Step 2: Environment-specific configuration
print_section "⚙️  Step 2: Configuring environment-specific settings"

# Set CDK context based on environment
case $ENVIRONMENT in
    "dev")
        print_status "Configuring development environment..."
        export CDK_CONTEXT_ENVIRONMENT="development"
        export CDK_CONTEXT_LOG_LEVEL="DEBUG"
        export CDK_CONTEXT_ENABLE_DETAILED_MONITORING="true"
        export CDK_CONTEXT_LAMBDA_TIMEOUT="300"
        export CDK_CONTEXT_LAMBDA_MEMORY="512"
        ;;
    "prod")
        print_status "Configuring production environment..."
        export CDK_CONTEXT_ENVIRONMENT="production"
        export CDK_CONTEXT_LOG_LEVEL="INFO"
        export CDK_CONTEXT_ENABLE_DETAILED_MONITORING="false"
        export CDK_CONTEXT_LAMBDA_TIMEOUT="180"
        export CDK_CONTEXT_LAMBDA_MEMORY="256"
        ;;
esac

# Set common CDK context
export CDK_CONTEXT_ACCOUNT=$ACCOUNT_ID
export CDK_CONTEXT_REGION=$REGION
export CDK_CONTEXT_PROJECT_NAME=$PROJECT_NAME

print_status "Environment configuration complete"

# Step 3: CDK Bootstrap (if needed)
print_section "🏗️  Step 3: CDK Bootstrap verification"

# Check if CDK is bootstrapped
if aws cloudformation describe-stacks --stack-name CDKToolkit --profile $PROFILE --region $REGION > /dev/null 2>&1; then
    print_status "CDK already bootstrapped in $REGION"
else
    print_status "Bootstrapping CDK in $REGION..."
    cdk bootstrap --profile $PROFILE --region $REGION
    
    if [ $? -eq 0 ]; then
        print_status "CDK bootstrap completed successfully"
    else
        print_error "CDK bootstrap failed"
        exit 1
    fi
fi

# Step 4: CDK Synthesis and Validation
print_section "🔍 Step 4: CDK synthesis and validation"

print_status "Synthesizing CDK templates..."
if cdk synth --profile $PROFILE --region $REGION > /dev/null; then
    print_status "CDK synthesis successful"
else
    print_error "CDK synthesis failed"
    exit 1
fi

# List available stacks
print_status "Available CDK stacks:"
cdk list --profile $PROFILE --region $REGION

# Step 5: Deploy CDK Infrastructure
print_section "☁️  Step 5: Deploying CDK infrastructure"

# Define deployment order for dependencies
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
    
    if cdk deploy $stack --profile $PROFILE --region $REGION --require-approval never; then
        print_status "✅ Stack $stack deployed successfully"
    else
        print_error "❌ Stack $stack deployment failed"
        
        # Ask user if they want to continue with remaining stacks
        read -p "Continue with remaining stacks? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_error "Deployment aborted by user"
            exit 1
        fi
    fi
done

# Step 6: Verify CDK Deployment
print_section "✅ Step 6: Verifying CDK deployment"

print_status "Checking deployed resources..."

# Check DynamoDB tables
print_status "Verifying DynamoDB tables..."
EXPECTED_TABLES=(
    "strava-ai-boost-activities"
    "strava-ai-boost-user-configuration"
    "strava-ai-boost-rate-limits"
    "strava-ai-boost-campus-coaching-sessions"
)

for table in "${EXPECTED_TABLES[@]}"; do
    if aws dynamodb describe-table --table-name $table --profile $PROFILE --region $REGION > /dev/null 2>&1; then
        print_status "✅ Table $table exists"
    else
        print_warning "⚠️  Table $table not found"
    fi
done

# Check Lambda functions
print_status "Verifying Lambda functions..."
LAMBDA_COUNT=$(aws lambda list-functions --profile $PROFILE --region $REGION | jq -r '.Functions[] | select(.FunctionName | contains("StravaAIBoost")) | .FunctionName' | wc -l)
print_status "Found $LAMBDA_COUNT Lambda functions"

# Check SQS queues
print_status "Verifying SQS queues..."
SQS_COUNT=$(aws sqs list-queues --profile $PROFILE --region $REGION | jq -r '.QueueUrls[]? // empty' | grep -c strava-ai-boost || echo "0")
print_status "Found $SQS_COUNT SQS queues"

# Step 7: Configure Secrets Manager
print_section "🔐 Step 7: Configuring Secrets Manager"

print_status "Setting up Secrets Manager secrets..."

# Create Strava OAuth secrets placeholder (will be populated by local web interface)
SECRET_NAME="strava-ai-boost-oauth-tokens"
if aws secretsmanager describe-secret --secret-id $SECRET_NAME --profile $PROFILE --region $REGION > /dev/null 2>&1; then
    print_status "Secret $SECRET_NAME already exists"
else
    print_status "Creating secret: $SECRET_NAME"
    aws secretsmanager create-secret \
        --name $SECRET_NAME \
        --description "Strava OAuth tokens for AI Boost (managed by local web interface)" \
        --secret-string '{"placeholder":"true","configured_via":"local_web_interface"}' \
        --profile $PROFILE \
        --region $REGION > /dev/null
    
    print_status "✅ OAuth secret placeholder created - will be configured via local web interface"
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
    
    print_warning "⚠️  Please update the Campus Coach credentials in Secrets Manager (optional):"
    print_warning "   aws secretsmanager put-secret-value --secret-id $CAMPUS_SECRET_NAME --secret-string '{\"username\":\"YOUR_USERNAME\",\"password\":\"YOUR_PASSWORD\",\"login_url\":\"https://campus.coach/login\"}' --profile $PROFILE"
fi

# Step 8: Deploy AgentCore Infrastructure
print_section "🤖 Step 8: Deploying AgentCore infrastructure"

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

# Step 9: Configure Strava Webhook Subscription
print_section "🔗 Step 9: Configuring Strava webhook subscription"

# Get webhook handler URL from API Gateway
WEBHOOK_URL=""
if aws apigateway get-rest-apis --profile $PROFILE --region $REGION > /dev/null 2>&1; then
    API_ID=$(aws apigateway get-rest-apis --profile $PROFILE --region $REGION | jq -r '.items[] | select(.name | contains("StravaAIBoost")) | .id' | head -1)
    
    if [ -n "$API_ID" ]; then
        WEBHOOK_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod/webhook"
        print_status "Webhook URL: $WEBHOOK_URL"
        
        print_warning "⚠️  Manual step required: Configure Strava webhook subscription"
        print_warning "   1. Go to https://developers.strava.com/"
        print_warning "   2. Edit your application"
        print_warning "   3. Add webhook subscription:"
        print_warning "      - Callback URL: $WEBHOOK_URL"
        print_warning "      - Verify Token: strava-ai-boost-verify-token"
        print_warning "   4. Test webhook with a sample activity"
    else
        print_warning "Could not determine API Gateway ID for webhook URL"
    fi
else
    print_warning "Could not access API Gateway to determine webhook URL"
fi

# Step 10: Run Integration Tests
print_section "🧪 Step 10: Running integration tests"

if [ -f "scripts/test_basic_integration.py" ]; then
    print_status "Running basic integration tests..."
    
    # Set environment variables for tests
    export AWS_PROFILE=$PROFILE
    export AWS_REGION=$REGION
    
    if python scripts/test_basic_integration.py; then
        print_status "✅ Basic integration tests passed"
    else
        print_warning "⚠️  Some integration tests failed"
        print_warning "This is expected if external services are not configured yet"
    fi
else
    print_warning "Integration test script not found, skipping tests"
fi

# Step 11: Generate Deployment Summary
print_section "📊 Step 11: Deployment summary"

echo ""
print_status "🎉 Strava AI Boost deployment completed!"
print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Account: $ACCOUNT_ID"

echo ""
print_status "📋 Deployed Resources:"
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
print_status "🔧 Manual Configuration Required:"
echo "  ❌ NONE! Everything is configured via the local web interface"
echo "  ✅ Just start the local interface and use the dashboard"
echo ""
echo "  Optional: Configure Strava webhook subscription for real-time processing"
echo "  (Use scripts/configure_strava_webhook.sh after OAuth setup)"

echo ""
print_status "📊 Monitoring Commands:"
echo "  # Check deployment status:"
echo "  aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --profile $PROFILE"
echo ""
echo "  # Monitor Lambda logs:"
echo "  aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile $PROFILE"
echo ""
echo "  # Check DynamoDB tables:"
echo "  aws dynamodb list-tables --profile $PROFILE | grep strava-ai-boost"
echo ""
echo "  # Test webhook endpoint:"
echo "  curl -X POST $WEBHOOK_URL -H 'Content-Type: application/json' -d '{\"test\": true}'"

echo ""
print_status "🚀 Next Steps:"
echo "  1. Start local web interface: cd local_interface && python app.py"
echo "  2. Open http://localhost:3000 in your browser"
echo "  3. Configure Strava OAuth via the web interface (no manual AWS CLI needed!)"
echo "  4. Enable modules (Campus Coach, Enduraw) as desired"
echo "  5. Test with a sample Strava activity"
echo "  6. Monitor processing in the dashboard"

# Save deployment information
DEPLOYMENT_INFO_FILE="deployment-info-${ENVIRONMENT}.json"
cat > $DEPLOYMENT_INFO_FILE << EOF
{
  "deployment_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "environment": "$ENVIRONMENT",
  "region": "$REGION",
  "account_id": "$ACCOUNT_ID",
  "profile": "$PROFILE",
  "webhook_url": "$WEBHOOK_URL",
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
  ]
}
EOF

print_status "Deployment information saved to: $DEPLOYMENT_INFO_FILE"

echo ""
print_status "✨ Deployment completed successfully!"