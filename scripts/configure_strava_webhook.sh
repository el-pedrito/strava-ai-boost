#!/bin/bash

# Configure Strava Webhook Subscription - Enhanced Automation
# Fully automates the Strava webhook subscription process with validation and cleanup
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   export STRAVA_CLIENT_ID=your_client_id
#   export STRAVA_CLIENT_SECRET=your_client_secret
#   ./scripts/configure_strava_webhook.sh [dev|prod] [--auto-configure]
#
# Options:
#   --auto-configure: Automatically configure webhook without user prompts
#   --cleanup: Remove existing webhook subscriptions
#   --validate-only: Only validate current configuration

set -e

# Configuration
ENVIRONMENT="${1:-dev}"
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
VERIFY_TOKEN="strava-ai-boost-verify-token-${ENVIRONMENT}"
AUTO_CONFIGURE=false
CLEANUP_MODE=false
VALIDATE_ONLY=false

# Parse command line options
while [[ $# -gt 0 ]]; do
    case $1 in
        --auto-configure)
            AUTO_CONFIGURE=true
            shift
            ;;
        --cleanup)
            CLEANUP_MODE=true
            shift
            ;;
        --validate-only)
            VALIDATE_ONLY=true
            shift
            ;;
        dev|prod)
            ENVIRONMENT="$1"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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
    echo -e "${BLUE}[SECTION]${NC} $1"
}

# Function definitions (must be before usage)
validate_environment_variables() {
    # Validate required environment variables and provide helpful error messages
    local missing_vars=()
    
    if [ -z "$STRAVA_CLIENT_ID" ]; then
        missing_vars+=("STRAVA_CLIENT_ID")
    fi
    
    if [ -z "$STRAVA_CLIENT_SECRET" ]; then
        missing_vars+=("STRAVA_CLIENT_SECRET")
    fi
    
    if [ ${#missing_vars[@]} -gt 0 ] && [ "$AUTO_CONFIGURE" = false ]; then
        print_error "Missing required environment variables: ${missing_vars[*]}"
        print_error ""
        print_error "Option 1: Export environment variables:"
        for var in "${missing_vars[@]}"; do
            print_error "  export $var=your_value"
        done
        print_error ""
        print_error "Option 2: Store credentials in AWS Secrets Manager and use --auto-configure"
        print_error "  aws secretsmanager put-secret-value --secret-id strava-ai-boost-oauth-tokens \\"
        print_error "    --secret-string '{\"client_id\":\"YOUR_ID\",\"client_secret\":\"YOUR_SECRET\"}' \\"
        print_error "    --profile $PROFILE"
        exit 1
    fi
}

retrieve_strava_credentials_from_secrets() {
    # Retrieve Strava credentials from AWS Secrets Manager
    local secret_name="strava-ai-boost-oauth-tokens"
    
    print_status "Retrieving Strava credentials from Secrets Manager..."
    
    if ! aws secretsmanager describe-secret --secret-id "$secret_name" --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
        print_error "Secrets Manager secret '$secret_name' not found"
        print_error "Please create the secret with your Strava application credentials:"
        print_error "  aws secretsmanager create-secret --name '$secret_name' \\"
        print_error "    --secret-string '{\"client_id\":\"YOUR_ID\",\"client_secret\":\"YOUR_SECRET\"}' \\"
        print_error "    --profile $PROFILE --region $REGION"
        exit 1
    fi
    
    local secret_value
    secret_value=$(aws secretsmanager get-secret-value --secret-id "$secret_name" --profile "$PROFILE" --region "$REGION" --query SecretString --output text)
    
    if [ $? -ne 0 ]; then
        print_error "Failed to retrieve secret value from Secrets Manager"
        exit 1
    fi
    
    # Parse JSON and extract credentials
    STRAVA_CLIENT_ID=$(echo "$secret_value" | jq -r '.client_id // empty')
    STRAVA_CLIENT_SECRET=$(echo "$secret_value" | jq -r '.client_secret // empty')
    
    if [ -z "$STRAVA_CLIENT_ID" ] || [ -z "$STRAVA_CLIENT_SECRET" ]; then
        print_error "Invalid credentials in Secrets Manager"
        print_error "Secret must contain 'client_id' and 'client_secret' fields"
        exit 1
    fi
    
    print_status "✅ Successfully retrieved Strava credentials from Secrets Manager"
}

cleanup_webhook_subscriptions() {
    # Remove all existing webhook subscriptions
    print_status "Retrieving existing webhook subscriptions..."
    
    local subscriptions
    subscriptions=$(curl -s -X GET \
        "https://www.strava.com/api/v3/push_subscriptions" \
        -H "Authorization: Bearer $STRAVA_CLIENT_SECRET" \
        -H "Content-Type: application/json" || echo "[]")
    
    local subscription_count
    subscription_count=$(echo "$subscriptions" | jq '. | length' 2>/dev/null || echo "0")
    
    if [ "$subscription_count" -eq 0 ]; then
        print_status "No webhook subscriptions found to clean up"
        return 0
    fi
    
    print_status "Found $subscription_count webhook subscription(s) to remove"
    
    # Remove each subscription
    local subscription_ids
    subscription_ids=$(echo "$subscriptions" | jq -r '.[].id' 2>/dev/null || echo "")
    
    for subscription_id in $subscription_ids; do
        if [ -n "$subscription_id" ] && [ "$subscription_id" != "null" ]; then
            print_status "Removing subscription: $subscription_id"
            
            local delete_response
            delete_response=$(curl -s -X DELETE \
                "https://www.strava.com/api/v3/push_subscriptions/$subscription_id" \
                -H "Authorization: Bearer $STRAVA_CLIENT_SECRET" \
                -H "Content-Type: application/json")
            
            if echo "$delete_response" | jq -e '.errors' > /dev/null 2>&1; then
                print_warning "Failed to delete subscription $subscription_id: $delete_response"
            else
                print_status "✅ Successfully removed subscription $subscription_id"
            fi
        fi
    done
    
    print_status "✅ Webhook cleanup completed"
}

validate_webhook_configuration() {
    # Validate current webhook configuration and provide status report
    print_status "Validating webhook configuration..."
    
    local validation_results=()
    local overall_status="✅ PASS"
    
    # Check 1: API Gateway deployment
    print_status "Checking API Gateway deployment..."
    local api_id
    api_id=$(aws apigateway get-rest-apis --profile "$PROFILE" --region "$REGION" --query "items[?contains(name, 'StravaAIBoost')].id" --output text | head -1)
    
    if [ -n "$api_id" ]; then
        local webhook_url="https://${api_id}.execute-api.${REGION}.amazonaws.com/prod/webhook"
        validation_results+=("✅ API Gateway deployed: $webhook_url")
        
        # Test webhook endpoint
        print_status "Testing webhook endpoint availability..."
        local http_status
        http_status=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$webhook_url?hub.mode=subscribe&hub.challenge=test&hub.verify_token=$VERIFY_TOKEN" || echo "000")
        
        if [ "$http_status" = "200" ]; then
            validation_results+=("✅ Webhook endpoint responding correctly")
        else
            validation_results+=("❌ Webhook endpoint not responding (HTTP $http_status)")
            overall_status="❌ FAIL"
        fi
    else
        validation_results+=("❌ API Gateway not found - deploy CDK stacks first")
        overall_status="❌ FAIL"
    fi
    
    # Check 2: Secrets Manager configuration
    print_status "Checking Secrets Manager configuration..."
    local secret_name="strava-ai-boost-oauth-tokens"
    
    if aws secretsmanager describe-secret --secret-id "$secret_name" --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
        local secret_value
        secret_value=$(aws secretsmanager get-secret-value --secret-id "$secret_name" --profile "$PROFILE" --region "$REGION" --query SecretString --output text 2>/dev/null)
        
        if [ -n "$secret_value" ]; then
            local has_client_id has_client_secret has_verify_token
            has_client_id=$(echo "$secret_value" | jq -r '.client_id // empty' | grep -c . || echo "0")
            has_client_secret=$(echo "$secret_value" | jq -r '.client_secret // empty' | grep -c . || echo "0")
            has_verify_token=$(echo "$secret_value" | jq -r '.webhook_verify_token // empty' | grep -c . || echo "0")
            
            if [ "$has_client_id" -gt 0 ] && [ "$has_client_secret" -gt 0 ]; then
                validation_results+=("✅ Strava API credentials configured")
            else
                validation_results+=("❌ Strava API credentials missing in Secrets Manager")
                overall_status="❌ FAIL"
            fi
            
            if [ "$has_verify_token" -gt 0 ]; then
                validation_results+=("✅ Webhook verify token configured")
            else
                validation_results+=("⚠️  Webhook verify token not configured (will use default)")
            fi
        else
            validation_results+=("❌ Unable to read secret value")
            overall_status="❌ FAIL"
        fi
    else
        validation_results+=("❌ Secrets Manager secret not found")
        overall_status="❌ FAIL"
    fi
    
    # Check 3: Current webhook subscriptions
    print_status "Checking existing webhook subscriptions..."
    
    if [ -n "$STRAVA_CLIENT_SECRET" ] || retrieve_strava_credentials_from_secrets 2>/dev/null; then
        local subscriptions
        subscriptions=$(curl -s -X GET \
            "https://www.strava.com/api/v3/push_subscriptions" \
            -H "Authorization: Bearer $STRAVA_CLIENT_SECRET" \
            -H "Content-Type: application/json" 2>/dev/null || echo "[]")
        
        local subscription_count
        subscription_count=$(echo "$subscriptions" | jq '. | length' 2>/dev/null || echo "0")
        
        if [ "$subscription_count" -gt 0 ]; then
            validation_results+=("✅ Found $subscription_count active webhook subscription(s)")
            
            # Check if our URL is registered
            if [ -n "$webhook_url" ]; then
                local matching_subscriptions
                matching_subscriptions=$(echo "$subscriptions" | jq -r --arg url "$webhook_url" '.[] | select(.callback_url == $url) | .id' 2>/dev/null || echo "")
                
                if [ -n "$matching_subscriptions" ]; then
                    validation_results+=("✅ Webhook subscription configured for our endpoint")
                else
                    validation_results+=("⚠️  Webhook subscription exists but not for our endpoint")
                fi
            fi
        else
            validation_results+=("⚠️  No webhook subscriptions found")
        fi
    else
        validation_results+=("❌ Cannot check webhook subscriptions - missing credentials")
        overall_status="❌ FAIL"
    fi
    
    # Check 4: Lambda function configuration
    print_status "Checking Lambda function configuration..."
    local lambda_functions
    lambda_functions=$(aws lambda list-functions --profile "$PROFILE" --region "$REGION" --query 'Functions[?contains(FunctionName, `StravaAIBoost`) && contains(FunctionName, `WebhookHandler`)].FunctionName' --output text)
    
    if [ -n "$lambda_functions" ]; then
        validation_results+=("✅ Webhook handler Lambda function deployed")
    else
        validation_results+=("❌ Webhook handler Lambda function not found")
        overall_status="❌ FAIL"
    fi
    
    # Display validation results
    echo ""
    print_section "📋 Webhook Configuration Validation Results"
    echo ""
    
    for result in "${validation_results[@]}"; do
        echo "  $result"
    done
    
    echo ""
    print_section "🎯 Overall Status: $overall_status"
    
    if [ "$overall_status" = "❌ FAIL" ]; then
        echo ""
        print_error "❌ Webhook configuration validation failed"
        print_error "Please fix the issues above before proceeding"
        return 1
    else
        echo ""
        print_status "✅ Webhook configuration validation passed"
        return 0
    fi
}

print_section "🔗 Configuring Strava webhook subscription for $ENVIRONMENT"

# Validate environment
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    print_error "Invalid environment: $ENVIRONMENT. Use 'dev' or 'prod'"
    exit 1
fi

# Handle cleanup mode
if [ "$CLEANUP_MODE" = true ]; then
    print_section "🧹 Cleanup mode: Removing existing webhook subscriptions"
    cleanup_webhook_subscriptions
    exit 0
fi

# Handle validate-only mode
if [ "$VALIDATE_ONLY" = true ]; then
    print_section "🔍 Validation mode: Checking webhook configuration"
    validate_webhook_configuration
    exit 0
fi

# Check required environment variables
validate_environment_variables

# Auto-detect Strava credentials from Secrets Manager if not provided
if [ -z "$STRAVA_CLIENT_ID" ] || [ -z "$STRAVA_CLIENT_SECRET" ]; then
    print_status "Attempting to retrieve Strava credentials from Secrets Manager..."
    retrieve_strava_credentials_from_secrets
fi

# Get webhook URL from API Gateway
print_status "Retrieving webhook URL from API Gateway..."

API_ID=$(aws apigateway get-rest-apis --profile $PROFILE --region $REGION --query "items[?contains(name, 'StravaAIBoost')].id" --output text | head -1)

if [ -z "$API_ID" ]; then
    print_error "Could not find StravaAIBoost API Gateway"
    print_error "Make sure CDK stacks are deployed first"
    exit 1
fi

WEBHOOK_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod/webhook"
print_status "Webhook URL: $WEBHOOK_URL"

# Test webhook endpoint availability
print_status "Testing webhook endpoint availability..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$WEBHOOK_URL?hub.mode=subscribe&hub.challenge=test&hub.verify_token=$VERIFY_TOKEN" || echo "000")

if [ "$HTTP_STATUS" = "200" ]; then
    print_status "✅ Webhook endpoint is responding correctly"
elif [ "$HTTP_STATUS" = "000" ]; then
    print_error "❌ Could not reach webhook endpoint"
    print_error "Check if API Gateway is deployed and accessible"
    exit 1
else
    print_warning "⚠️  Webhook endpoint returned HTTP $HTTP_STATUS"
    print_warning "This may be expected if webhook validation is not fully implemented"
fi

# Check if webhook subscription already exists
print_status "Checking existing webhook subscriptions..."

# Get existing subscriptions
EXISTING_SUBSCRIPTIONS=$(curl -s -X GET \
    "https://www.strava.com/api/v3/push_subscriptions" \
    -H "Authorization: Bearer $STRAVA_CLIENT_SECRET" \
    -H "Content-Type: application/json" || echo "[]")

# Parse response to check for existing subscription
SUBSCRIPTION_COUNT=$(echo "$EXISTING_SUBSCRIPTIONS" | jq '. | length' 2>/dev/null || echo "0")

if [ "$SUBSCRIPTION_COUNT" -gt 0 ]; then
    print_status "Found $SUBSCRIPTION_COUNT existing webhook subscription(s)"
    
    # Check if our callback URL is already registered
    EXISTING_URL=$(echo "$EXISTING_SUBSCRIPTIONS" | jq -r ".[0].callback_url" 2>/dev/null || echo "")
    
    if [ "$EXISTING_URL" = "$WEBHOOK_URL" ]; then
        print_status "✅ Webhook subscription already configured with correct URL"
        SUBSCRIPTION_ID=$(echo "$EXISTING_SUBSCRIPTIONS" | jq -r ".[0].id" 2>/dev/null || echo "")
        print_status "Subscription ID: $SUBSCRIPTION_ID"
        
        # Verify subscription is active
        print_status "Verifying subscription status..."
        SUBSCRIPTION_DETAILS=$(curl -s -X GET \
            "https://www.strava.com/api/v3/push_subscriptions/$SUBSCRIPTION_ID" \
            -H "Authorization: Bearer $STRAVA_CLIENT_SECRET" \
            -H "Content-Type: application/json" || echo "{}")
        
        echo "$SUBSCRIPTION_DETAILS" | jq '.' 2>/dev/null || echo "Could not parse subscription details"
        
        print_status "✅ Webhook subscription verification complete"
        exit 0
    else
        print_warning "⚠️  Existing subscription uses different URL: $EXISTING_URL"
        print_warning "You may want to delete the old subscription and create a new one"
        
        # Ask user if they want to delete existing subscription
        if [ "$AUTO_CONFIGURE" = true ]; then
            print_status "Auto-configure mode: Deleting existing subscription and creating new one"
            REPLY="y"
        else
            read -p "Delete existing subscription and create new one? (y/n): " -n 1 -r
            echo
        fi
        if [[ $REPLY =~ ^[Yy]$ ]] || [ "$AUTO_CONFIGURE" = true ]; then
            SUBSCRIPTION_ID=$(echo "$EXISTING_SUBSCRIPTIONS" | jq -r ".[0].id" 2>/dev/null || echo "")
            
            if [ -n "$SUBSCRIPTION_ID" ]; then
                print_status "Deleting existing subscription: $SUBSCRIPTION_ID"
                
                DELETE_RESPONSE=$(curl -s -X DELETE \
                    "https://www.strava.com/api/v3/push_subscriptions/$SUBSCRIPTION_ID" \
                    -H "Authorization: Bearer $STRAVA_CLIENT_SECRET" \
                    -H "Content-Type: application/json")
                
                print_status "Delete response: $DELETE_RESPONSE"
            fi
        else
            print_status "Keeping existing subscription. Manual configuration may be required."
            exit 0
        fi
    fi
fi

# Create new webhook subscription
print_status "Creating new webhook subscription..."

SUBSCRIPTION_RESPONSE=$(curl -s -X POST \
    "https://www.strava.com/api/v3/push_subscriptions" \
    -H "Content-Type: application/json" \
    -d "{
        \"client_id\": \"$STRAVA_CLIENT_ID\",
        \"client_secret\": \"$STRAVA_CLIENT_SECRET\",
        \"callback_url\": \"$WEBHOOK_URL\",
        \"verify_token\": \"$VERIFY_TOKEN\"
    }")

# Check if subscription was created successfully
if echo "$SUBSCRIPTION_RESPONSE" | jq -e '.id' > /dev/null 2>&1; then
    SUBSCRIPTION_ID=$(echo "$SUBSCRIPTION_RESPONSE" | jq -r '.id')
    print_status "✅ Webhook subscription created successfully!"
    print_status "Subscription ID: $SUBSCRIPTION_ID"
    print_status "Callback URL: $WEBHOOK_URL"
    print_status "Verify Token: $VERIFY_TOKEN"
    
    # Display subscription details
    echo ""
    print_status "📋 Subscription Details:"
    echo "$SUBSCRIPTION_RESPONSE" | jq '.' 2>/dev/null || echo "$SUBSCRIPTION_RESPONSE"
    
    # Store configuration in Secrets Manager
    store_webhook_configuration "$SUBSCRIPTION_ID" "$WEBHOOK_URL"
    
    # Perform end-to-end testing
    test_webhook_end_to_end "$WEBHOOK_URL"
    
    # Save webhook configuration file
    WEBHOOK_CONFIG_FILE="webhook-config-${ENVIRONMENT}.json"
    cat > $WEBHOOK_CONFIG_FILE << EOF
{
  "subscription_id": "$SUBSCRIPTION_ID",
  "callback_url": "$WEBHOOK_URL",
  "verify_token": "$VERIFY_TOKEN",
  "environment": "$ENVIRONMENT",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "client_id": "$STRAVA_CLIENT_ID",
  "auto_configured": $AUTO_CONFIGURE
}
EOF
    
    print_status "Webhook configuration saved to: $WEBHOOK_CONFIG_FILE"
    
    echo ""
    print_status "🎉 Strava webhook configuration complete!"
    print_status "Your Strava activities will now trigger webhook events to: $WEBHOOK_URL"
    
    echo ""
    print_status "🧪 Testing Instructions:"
    echo "  1. Create or update an activity in Strava"
    echo "  2. Monitor webhook logs:"
    echo "     aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile $PROFILE"
    echo "  3. Check SQS queue for messages:"
    echo "     aws sqs get-queue-attributes --queue-url <queue-url> --profile $PROFILE"
    
    # Generate management commands
    generate_webhook_management_commands "$SUBSCRIPTION_ID" "$WEBHOOK_URL"
    
else
    print_error "❌ Failed to create webhook subscription"
    print_error "Response: $SUBSCRIPTION_RESPONSE"
    
    # Check for common error messages and provide specific guidance
    if echo "$SUBSCRIPTION_RESPONSE" | grep -q "callback_url"; then
        print_error "Callback URL validation failed"
        print_error "Make sure your webhook endpoint is accessible and responds correctly"
        print_error "Test manually: curl -X GET '$WEBHOOK_URL?hub.mode=subscribe&hub.challenge=test&hub.verify_token=$VERIFY_TOKEN'"
    elif echo "$SUBSCRIPTION_RESPONSE" | grep -q "client_id\|client_secret"; then
        print_error "Invalid Strava client credentials"
        print_error "Check your STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET"
        print_error "Verify at: https://www.strava.com/settings/api"
    elif echo "$SUBSCRIPTION_RESPONSE" | grep -q "verify_token"; then
        print_error "Verify token validation failed"
        print_error "Make sure your webhook handler validates the verify token correctly"
    elif echo "$SUBSCRIPTION_RESPONSE" | grep -q "subscription_limit"; then
        print_error "Subscription limit reached"
        print_error "Delete existing subscriptions first:"
        print_error "  ./scripts/configure_strava_webhook.sh $ENVIRONMENT --cleanup"
    else
        print_error "Unknown error occurred"
        print_error "Check Strava API documentation: https://developers.strava.com/docs/webhooks/"
    fi
    
    # Provide troubleshooting steps
    echo ""
    print_error "🔧 Troubleshooting Steps:"
    echo "  1. Validate webhook configuration:"
    echo "     ./scripts/configure_strava_webhook.sh $ENVIRONMENT --validate-only"
    echo "  2. Check API Gateway deployment:"
    echo "     aws apigateway get-rest-apis --profile $PROFILE"
    echo "  3. Test webhook endpoint manually:"
    echo "     curl -X GET '$WEBHOOK_URL?hub.mode=subscribe&hub.challenge=test&hub.verify_token=$VERIFY_TOKEN'"
    echo "  4. Check Lambda function logs:"
    echo "     aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --profile $PROFILE"
    
    exit 1
fi

print_status "✨ Webhook configuration completed successfully!"