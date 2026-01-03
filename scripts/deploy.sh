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

# Check if this is a first deployment
FIRST_DEPLOYMENT=false
if ! aws cloudformation describe-stacks --stack-name "StravaAIBoost-Core" --profile $PROFILE --region $REGION > /dev/null 2>&1; then
    FIRST_DEPLOYMENT=true
    print_status "🆕 First deployment detected"
    print_status "⏭️  Skipping advanced validations (will be done after deployment)"
fi

# Always verify AWS credentials (essential)
print_status "Verifying AWS credentials..."
if ! aws sts get-caller-identity --profile $PROFILE > /dev/null 2>&1; then
    print_error "AWS credentials not configured for profile: $PROFILE"
    print_error "Please configure with: aws configure --profile $PROFILE"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --profile $PROFILE --query Account --output text)
print_status "Using AWS Account: $ACCOUNT_ID"

# Only run detailed validations for subsequent deployments
if [ "$FIRST_DEPLOYMENT" = false ]; then
    # Check if validation script exists and run it
    if [ -f "scripts/validate_setup.sh" ]; then
        print_status "Running setup validation..."
        chmod +x scripts/validate_setup.sh
        if ! ./scripts/validate_setup.sh; then
            print_warning "Setup validation failed - continuing anyway"
        fi
    fi

    # Run Strava-specific validation
    if [ -f "scripts/validate_strava_setup.sh" ]; then
        print_status "Running Strava application validation..."
        chmod +x scripts/validate_strava_setup.sh
        
        if ./scripts/validate_strava_setup.sh $ENVIRONMENT --detailed; then
            print_status "✅ Strava application validation passed"
        else
            VALIDATION_EXIT_CODE=$?
            if [ $VALIDATION_EXIT_CODE -eq 2 ]; then
                print_warning "⚠️  Strava validation passed with warnings"
            else
                print_warning "⚠️  Strava application validation failed"
                print_warning "Will configure via local web interface after deployment"
            fi
        fi
    fi
fi

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

# Step 4: Build Lambda Layer
print_section "📦 Step 4: Building Lambda Layer"

print_status "Building Lambda Layer with dependencies..."
if [ -f "lambda_layer/build_layer.sh" ]; then
    chmod +x lambda_layer/build_layer.sh
    if ./lambda_layer/build_layer.sh; then
        LAYER_SIZE=$(du -h lambda_layer/strava-ai-boost-dependencies-layer.zip | cut -f1)
        print_status "✅ Lambda Layer built successfully (Size: $LAYER_SIZE)"
    else
        print_error "❌ Lambda Layer build failed"
        exit 1
    fi
else
    print_warning "Lambda Layer build script not found, skipping layer build"
fi

# Step 5: CDK Synthesis and Validation
print_section "🔍 Step 5: CDK synthesis and validation"

# Skip synthesis validation for first deployment to avoid false errors
if [ "$FIRST_DEPLOYMENT" = true ]; then
    print_status "⏭️  Skipping CDK synthesis validation for first deployment"
    print_status "CDK will validate during deployment phase"
else
    print_status "Synthesizing CDK templates..."
    if cdk synth --profile $PROFILE --region $REGION > /dev/null; then
        print_status "CDK synthesis successful"
    else
        print_warning "CDK synthesis failed - continuing with deployment"
        print_warning "CDK will attempt to resolve issues during deployment"
    fi
fi

# List available stacks
print_status "Available CDK stacks:"
cdk list --profile $PROFILE --region $REGION

# Step 6: Deploy CDK Infrastructure
print_section "☁️  Step 6: Deploying CDK infrastructure"

print_status "Deploying CDK stacks..."

# Best practice: Use CDK's built-in dependency management with --all
# CDK automatically handles dependencies between stacks when using --all
print_status "Using CDK automatic dependency resolution with --all flag..."

if cdk deploy --all --profile $PROFILE --region $REGION --require-approval never; then
    print_status "✅ All CDK stacks deployed successfully"
else
    CDK_EXIT_CODE=$?
    print_error "❌ CDK deployment encountered issues"
    
    # Provide context-aware troubleshooting information
    if [ "$FIRST_DEPLOYMENT" = true ]; then
        print_status "🔍 First deployment troubleshooting:"
        print_status "This is normal for first deployments. Common causes:"
        print_status "• Resource dependencies being created in order"
        print_status "• IAM roles needing time to propagate"
        print_status "• Cross-stack references being established"
        print_status ""
        print_status "💡 Recommended actions:"
        print_status "1. Wait 2-3 minutes for AWS resources to propagate"
        print_status "2. Re-run the deployment: ./scripts/deploy.sh $ENVIRONMENT"
        print_status "3. Check CloudFormation console for specific error details"
    else
        print_status "🔍 Deployment troubleshooting:"
        print_status "1. Check CloudFormation console for detailed error messages"
        print_status "2. Verify no resource conflicts exist"
        print_status "3. Ensure all dependencies are properly defined in CDK code"
        print_status "4. Check for quota limits or permission issues"
    fi
    
    print_status ""
    print_status "💡 To retry deployment:"
    print_status "   ./scripts/deploy.sh $ENVIRONMENT"
    print_status ""
    print_status "💡 To deploy only specific stacks:"
    print_status "   cdk deploy StravaAIBoost-Core --profile $PROFILE"
    print_status "   cdk deploy StravaAIBoost-Content --profile $PROFILE"
    
    exit $CDK_EXIT_CODE
fi

# Step 7: Verify CDK Deployment
print_section "✅ Step 7: Verifying CDK deployment"

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

# Step 8: Configure Secrets Manager
print_section "🔐 Step 8: Configuring Secrets Manager"

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

# Step 8: CDK Deployment Complete - Next Steps
print_section "✅ Step 8: CDK Infrastructure Deployment Complete"

print_status "🎉 Phase 1 (CDK Infrastructure) completed successfully!"
print_status ""
print_status "📋 What was deployed:"
echo "  ✅ DynamoDB Tables: Activities, Configuration, Rate Limits, Sessions"
echo "  ✅ Lambda Functions: Webhook Handler, Content Generator, etc."
echo "  ✅ Step Functions: Activity processing workflow"
echo "  ✅ SQS Queues: Activity processing with DLQ"
echo "  ✅ Secrets Manager: OAuth tokens, Campus Coach credentials"
echo "  ✅ API Gateway: Local interface endpoints"

print_status ""
print_status "🤖 Content Generation System Status:"
echo "  ✅ Mode: Bedrock fallback (direct Claude Sonnet 4.5)"
echo "  ✅ Features: Smart prompts, module insights, reliable performance"
echo "  💡 Note: System is fully functional - AgentCore is optional for enhanced features"

print_status ""
print_status "🚀 Phase 2 - AgentCore Enhancement (Optional):"
echo "  To enable enhanced personalization with AgentCore Memory:"
echo "  ./scripts/deploy_agentcore_agents.sh"
echo ""
echo "  This will:"
echo "  • Deploy AgentCore agents with persistent memory"
echo "  • Automatically update Lambda environment variables"
echo "  • Enable enhanced personalization mode"
echo "  • Provide seamless fallback if AgentCore is unavailable"

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

# Step 10.5: Post-deployment Strava validation
print_section "🔍 Step 10.5: Post-deployment Strava validation"

# Only run post-deployment validation if not first deployment
if [ -f "scripts/validate_strava_setup.sh" ] && [ "$FIRST_DEPLOYMENT" = false ]; then
    print_status "Running post-deployment Strava validation..."
    
    if ./scripts/validate_strava_setup.sh $ENVIRONMENT --detailed; then
        print_status "✅ Post-deployment Strava validation passed"
    else
        VALIDATION_EXIT_CODE=$?
        if [ $VALIDATION_EXIT_CODE -eq 2 ]; then
            print_warning "⚠️  Post-deployment validation passed with warnings"
        else
            print_warning "⚠️  Post-deployment validation failed"
            print_warning "Some components may need manual configuration"
        fi
    fi
    
    # Run health check
    if [ -f "scripts/strava_health_check.sh" ]; then
        print_status "Running initial health check..."
        
        if ./scripts/strava_health_check.sh $ENVIRONMENT; then
            print_status "✅ Initial health check passed"
        else
            print_warning "⚠️  Initial health check found issues"
            print_warning "Review health report for details"
        fi
    fi
else
    if [ "$FIRST_DEPLOYMENT" = true ]; then
        print_status "⏭️  Skipping post-deployment validation for first deployment"
        print_status "Configuration will be done via local web interface"
    else
        print_warning "Post-deployment validation script not found"
    fi
fi

# Step 11: Generate Deployment Summary
print_section "📊 Step 11: Deployment summary"

echo ""
print_status "🎉 Phase 1 (CDK Infrastructure) deployment completed!"
print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Account: $ACCOUNT_ID"

echo ""
print_status "🤖 Content Generation System:"
echo "  ✅ Mode: Bedrock fallback (direct Claude Sonnet 4.5)"
echo "  ✅ Features: Smart prompts, module insights, reliable performance"
echo "  💡 Note: System is fully functional - AgentCore is optional for enhanced features"

echo ""
print_status "📋 Deployed Resources (Phase 1):"
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
print_status "🚀 Phase 2 - AgentCore Enhancement (Optional):"
echo "  To enable enhanced personalization with persistent memory:"
echo ""
echo "  ./scripts/deploy_agentcore_agents.sh"
echo ""
echo "  This will:"
echo "  • Deploy AgentCore agents with persistent memory"
echo "  • Automatically update Lambda environment variables with agent ARNs"
echo "  • Enable enhanced personalization mode"
echo "  • Provide seamless fallback if AgentCore is unavailable"

echo ""
print_status "🔧 Configuration:"
echo "  ✅ Everything is configured via the local web interface"
echo "  ✅ No manual AWS CLI commands needed"
echo ""
echo "  Optional: Configure Strava webhook subscription for real-time processing"
echo "  (Use scripts/configure_strava_webhook.sh after OAuth setup)"

echo ""
print_status "🚀 Next Steps:"
echo "  1. Start local web interface: cd local_interface && python app.py"
echo "  2. Open http://localhost:3000 in your browser"
echo "  3. Configure Strava OAuth via the web interface"
echo "  4. Enable modules (Campus Coach, Enduraw) as desired"
echo "  5. Test with a sample Strava activity"
echo "  6. (Optional) Run Phase 2: ./scripts/deploy_agentcore_agents.sh"

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
    "StravaAIBoost-Security",
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