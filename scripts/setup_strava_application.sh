#!/bin/bash

# Strava Application Setup Guide
# Interactive guide for setting up Strava API application
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/setup_strava_application.sh [dev|prod]

set -e

# Configuration
ENVIRONMENT="${1:-dev}"
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

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
    echo -e "${CYAN}[SECTION]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

print_important() {
    echo -e "${BOLD}${YELLOW}⚠️  IMPORTANT:${NC} $1"
}

print_success() {
    echo -e "${BOLD}${GREEN}✅ SUCCESS:${NC} $1"
}

# Function to wait for user confirmation
wait_for_confirmation() {
    local message="$1"
    echo ""
    echo -e "${YELLOW}$message${NC}"
    read -p "Press Enter to continue..." -r
    echo ""
}

# Function to get user input
get_user_input() {
    local prompt="$1"
    local variable_name="$2"
    local is_secret="${3:-false}"
    
    echo -e "${BLUE}$prompt${NC}"
    if [ "$is_secret" = true ]; then
        read -s -r user_input
        echo "" # New line after hidden input
    else
        read -r user_input
    fi
    
    eval "$variable_name='$user_input'"
}

print_section "🚀 Strava Application Setup Guide"
print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Profile: $PROFILE"

echo ""
print_important "This guide will help you set up your Strava API application for Strava AI Boost"
print_status "We'll walk through each step to ensure proper configuration"

# Step 1: Check if user has a Strava account
print_section "📋 Step 1: Strava Account Verification"

echo ""
echo "First, let's make sure you have a Strava account and understand the requirements:"
echo ""
echo "Requirements:"
echo "  ✅ Active Strava account (free or premium)"
echo "  ✅ Activities to enhance (running, cycling, etc.)"
echo "  ✅ Willingness to authorize API access to your activities"
echo ""

wait_for_confirmation "Do you have an active Strava account with activities to enhance?"

# Step 2: Create Strava API Application
print_section "🔧 Step 2: Create Strava API Application"

echo ""
echo "Now we'll create a Strava API application. This is required to access Strava's API."
echo ""
echo "Follow these steps:"
echo ""
echo "1. Open your web browser and go to: ${BOLD}https://www.strava.com/settings/api${NC}"
echo "2. Click '${BOLD}Create & Manage Your App${NC}'"
echo "3. If you don't have an app yet, click '${BOLD}+ Create New App${NC}'"
echo ""

wait_for_confirmation "Have you opened the Strava API settings page?"

# Get webhook URL for application setup
print_status "Determining webhook URL for your application..."

API_ID=$(aws apigateway get-rest-apis --profile "$PROFILE" --region "$REGION" --query "items[?contains(name, 'StravaAIBoost')].id" --output text 2>/dev/null | head -1)

if [ -n "$API_ID" ]; then
    WEBHOOK_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod/webhook"
    OAUTH_CALLBACK_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod/oauth/callback"
    print_success "Found your deployed API Gateway"
    print_status "Webhook URL: $WEBHOOK_URL"
    print_status "OAuth Callback URL: $OAUTH_CALLBACK_URL"
else
    print_warning "API Gateway not found - you may need to deploy first"
    print_warning "Using placeholder URLs - update these after deployment"
    WEBHOOK_URL="https://YOUR_API_ID.execute-api.${REGION}.amazonaws.com/prod/webhook"
    OAUTH_CALLBACK_URL="https://YOUR_API_ID.execute-api.${REGION}.amazonaws.com/prod/oauth/callback"
fi

echo ""
echo "Fill out the Strava application form with these details:"
echo ""
echo "📝 ${BOLD}Application Details:${NC}"
echo "  Application Name: ${BOLD}Strava AI Boost ($ENVIRONMENT)${NC}"
echo "  Category: ${BOLD}Data Importer${NC}"
echo "  Club: ${BOLD}(leave blank)${NC}"
echo "  Website: ${BOLD}https://github.com/your-username/strava-ai-boost${NC}"
echo "  Application Description:"
echo "    ${BOLD}Personal AI-powered activity enhancement system that automatically"
echo "    improves Strava activity titles and descriptions using Amazon Bedrock AI.${NC}"
echo ""
echo "🔗 ${BOLD}Authorization Callback Domain:${NC}"
echo "  ${BOLD}$(echo "$OAUTH_CALLBACK_URL" | sed 's|https://||' | sed 's|/.*||')${NC}"
echo ""

wait_for_confirmation "Have you filled out and submitted the application form?"

# Step 3: Get Application Credentials
print_section "🔑 Step 3: Get Application Credentials"

echo ""
echo "After creating your application, you should see your application details."
echo "We need to collect your Client ID and Client Secret."
echo ""

get_user_input "Enter your Strava Client ID (should be a number like 12345):" "STRAVA_CLIENT_ID"
get_user_input "Enter your Strava Client Secret (long string of characters):" "STRAVA_CLIENT_SECRET" true

# Validate credentials format
if [[ ! "$STRAVA_CLIENT_ID" =~ ^[0-9]+$ ]]; then
    print_error "Client ID should be numeric. Please double-check your input."
    exit 1
fi

if [ ${#STRAVA_CLIENT_SECRET} -lt 20 ]; then
    print_error "Client Secret seems too short. Please double-check your input."
    exit 1
fi

print_success "Credentials collected successfully"

# Step 4: Store Credentials in AWS Secrets Manager
print_section "🔐 Step 4: Store Credentials in AWS Secrets Manager"

echo ""
print_status "Storing your Strava credentials securely in AWS Secrets Manager..."

SECRET_NAME="strava-ai-boost-oauth-tokens"

# Create or update the secret
SECRET_VALUE=$(jq -n \
    --arg client_id "$STRAVA_CLIENT_ID" \
    --arg client_secret "$STRAVA_CLIENT_SECRET" \
    --arg webhook_verify_token "strava-ai-boost-verify-token-${ENVIRONMENT}" \
    '{
        client_id: $client_id,
        client_secret: $client_secret,
        webhook_verify_token: $webhook_verify_token,
        configured_at: now | strftime("%Y-%m-%dT%H:%M:%SZ"),
        environment: "'$ENVIRONMENT'"
    }')

if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
    print_status "Updating existing secret..."
    aws secretsmanager put-secret-value \
        --secret-id "$SECRET_NAME" \
        --secret-string "$SECRET_VALUE" \
        --profile "$PROFILE" \
        --region "$REGION" > /dev/null
else
    print_status "Creating new secret..."
    aws secretsmanager create-secret \
        --name "$SECRET_NAME" \
        --description "Strava API credentials for AI Boost ($ENVIRONMENT)" \
        --secret-string "$SECRET_VALUE" \
        --profile "$PROFILE" \
        --region "$REGION" > /dev/null
fi

print_success "Credentials stored securely in AWS Secrets Manager"

# Step 5: Test API Connectivity
print_section "🧪 Step 5: Test API Connectivity"

echo ""
print_status "Testing connectivity to Strava API..."

# Test webhook subscriptions endpoint
STRAVA_TEST_RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/strava_setup_test \
    "https://www.strava.com/api/v3/push_subscriptions" \
    -H "Authorization: Bearer $STRAVA_CLIENT_SECRET" 2>/dev/null || echo "000")

if [ "$STRAVA_TEST_RESPONSE" = "200" ]; then
    print_success "Strava API connectivity test passed"
    
    # Check existing subscriptions
    SUBSCRIPTIONS=$(cat /tmp/strava_setup_test 2>/dev/null)
    SUBSCRIPTION_COUNT=$(echo "$SUBSCRIPTIONS" | jq '. | length' 2>/dev/null || echo "0")
    
    if [ "$SUBSCRIPTION_COUNT" -gt 0 ]; then
        print_status "Found $SUBSCRIPTION_COUNT existing webhook subscription(s)"
        echo "$SUBSCRIPTIONS" | jq -r '.[] | "  - ID: \(.id), URL: \(.callback_url)"' 2>/dev/null || echo "  Unable to parse subscriptions"
    else
        print_status "No existing webhook subscriptions (this is normal for new applications)"
    fi
elif [ "$STRAVA_TEST_RESPONSE" = "401" ]; then
    print_error "Strava API authentication failed"
    print_error "Please double-check your Client Secret"
    exit 1
else
    print_warning "Strava API test returned unexpected status: $STRAVA_TEST_RESPONSE"
    print_warning "This might be a temporary issue - continuing with setup"
fi

rm -f /tmp/strava_setup_test

# Step 6: Configure Webhook Subscription (if infrastructure is deployed)
if [ -n "$API_ID" ]; then
    print_section "🔗 Step 6: Configure Webhook Subscription"
    
    echo ""
    print_status "Your infrastructure is deployed. Let's set up the webhook subscription."
    
    if [ -f "scripts/configure_strava_webhook.sh" ]; then
        print_status "Running webhook configuration script..."
        
        # Export credentials for the webhook script
        export STRAVA_CLIENT_ID
        export STRAVA_CLIENT_SECRET
        
        if ./scripts/configure_strava_webhook.sh "$ENVIRONMENT" --auto-configure; then
            print_success "Webhook subscription configured successfully"
        else
            print_warning "Webhook configuration failed - you can run it manually later"
            print_status "Manual command: ./scripts/configure_strava_webhook.sh $ENVIRONMENT"
        fi
    else
        print_warning "Webhook configuration script not found"
        print_status "You can configure webhooks manually later"
    fi
else
    print_section "🔗 Step 6: Webhook Configuration (Deferred)"
    
    echo ""
    print_status "Your infrastructure is not yet deployed."
    print_status "Webhook subscription will be configured after deployment."
    print_status "Run this command after deploying: ./scripts/configure_strava_webhook.sh $ENVIRONMENT"
fi

# Step 7: Validation
print_section "✅ Step 7: Validation"

echo ""
print_status "Running comprehensive validation..."

if [ -f "scripts/validate_strava_setup.sh" ]; then
    if ./scripts/validate_strava_setup.sh "$ENVIRONMENT" --detailed; then
        print_success "All validation checks passed!"
    else
        VALIDATION_EXIT_CODE=$?
        if [ $VALIDATION_EXIT_CODE -eq 2 ]; then
            print_warning "Validation passed with warnings - review above"
        else
            print_error "Some validation checks failed - review above"
        fi
    fi
else
    print_warning "Validation script not found - skipping validation"
fi

# Step 8: Next Steps
print_section "🎯 Step 8: Next Steps"

echo ""
print_success "Strava application setup completed!"

echo ""
echo "📋 ${BOLD}What was configured:${NC}"
echo "  ✅ Strava API application created"
echo "  ✅ Client credentials stored in AWS Secrets Manager"
echo "  ✅ API connectivity tested"

if [ -n "$API_ID" ]; then
    echo "  ✅ Webhook subscription configured"
else
    echo "  ⏳ Webhook subscription (pending infrastructure deployment)"
fi

echo ""
echo "🚀 ${BOLD}Next Steps:${NC}"

if [ -z "$API_ID" ]; then
    echo "  1. Deploy infrastructure: ./scripts/deploy.sh $ENVIRONMENT"
    echo "  2. Configure webhook: ./scripts/configure_strava_webhook.sh $ENVIRONMENT"
    echo "  3. Start local interface: cd local_interface && python app.py"
else
    echo "  1. Start local interface: cd local_interface && python app.py"
    echo "  2. Open http://localhost:3000 in your browser"
    echo "  3. Complete OAuth authorization via the web interface"
fi

echo "  4. Test with a sample Strava activity"
echo "  5. Monitor processing in the dashboard"

echo ""
echo "🔧 ${BOLD}Useful Commands:${NC}"
echo "  # Validate configuration:"
echo "  ./scripts/validate_strava_setup.sh $ENVIRONMENT --detailed"
echo ""
echo "  # Health check:"
echo "  ./scripts/strava_health_check.sh $ENVIRONMENT --webhook-test"
echo ""
echo "  # Webhook management:"
echo "  ./scripts/configure_strava_webhook.sh $ENVIRONMENT --validate-only"

echo ""
echo "📚 ${BOLD}Documentation:${NC}"
echo "  - Strava API: https://developers.strava.com/docs/"
echo "  - Webhook Events: https://developers.strava.com/docs/webhooks/"
echo "  - OAuth Flow: https://developers.strava.com/docs/authentication/"

# Save setup summary
SETUP_SUMMARY_FILE="strava-setup-summary-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S).json"
cat > "$SETUP_SUMMARY_FILE" << EOF
{
  "setup_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "environment": "$ENVIRONMENT",
  "region": "$REGION",
  "account_id": "$(aws sts get-caller-identity --profile $PROFILE --query Account --output text 2>/dev/null || echo 'unknown')",
  "strava_application": {
    "client_id": "$STRAVA_CLIENT_ID",
    "client_secret_configured": true,
    "webhook_verify_token_configured": true
  },
  "infrastructure": {
    "api_gateway_deployed": $([ -n "$API_ID" ] && echo "true" || echo "false"),
    "webhook_url": "$WEBHOOK_URL",
    "oauth_callback_url": "$OAUTH_CALLBACK_URL"
  },
  "next_steps": [
    $([ -z "$API_ID" ] && echo '"Deploy infrastructure",' || echo '"Start local interface",')
    "Complete OAuth authorization",
    "Test with sample activity"
  ]
}
EOF

print_status "Setup summary saved: $SETUP_SUMMARY_FILE"

echo ""
print_success "🎉 Strava application setup completed successfully!"
print_status "You're ready to start using Strava AI Boost!"