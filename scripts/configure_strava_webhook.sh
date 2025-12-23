#!/bin/bash

# Configure Strava Webhook Subscription
# Automates the Strava webhook subscription process
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   export STRAVA_CLIENT_ID=your_client_id
#   export STRAVA_CLIENT_SECRET=your_client_secret
#   ./scripts/configure_strava_webhook.sh [dev|prod]

set -e

# Configuration
ENVIRONMENT="${1:-dev}"
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
VERIFY_TOKEN="strava-ai-boost-verify-token-${ENVIRONMENT}"

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

print_section "🔗 Configuring Strava webhook subscription for $ENVIRONMENT"

# Validate environment
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    print_error "Invalid environment: $ENVIRONMENT. Use 'dev' or 'prod'"
    exit 1
fi

# Check required environment variables
if [ -z "$STRAVA_CLIENT_ID" ]; then
    print_error "STRAVA_CLIENT_ID environment variable not set"
    print_error "Export your Strava application client ID:"
    print_error "  export STRAVA_CLIENT_ID=your_client_id"
    exit 1
fi

if [ -z "$STRAVA_CLIENT_SECRET" ]; then
    print_error "STRAVA_CLIENT_SECRET environment variable not set"
    print_error "Export your Strava application client secret:"
    print_error "  export STRAVA_CLIENT_SECRET=your_client_secret"
    exit 1
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
        read -p "Delete existing subscription and create new one? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
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
    
else
    print_error "❌ Failed to create webhook subscription"
    print_error "Response: $SUBSCRIPTION_RESPONSE"
    
    # Check for common error messages
    if echo "$SUBSCRIPTION_RESPONSE" | grep -q "callback_url"; then
        print_error "Callback URL validation failed"
        print_error "Make sure your webhook endpoint is accessible and responds correctly"
    elif echo "$SUBSCRIPTION_RESPONSE" | grep -q "client_id\|client_secret"; then
        print_error "Invalid Strava client credentials"
        print_error "Check your STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET"
    fi
    
    exit 1
fi

# Test webhook with a verification request
print_status "Testing webhook subscription..."

TEST_RESPONSE=$(curl -s -X GET \
    "$WEBHOOK_URL?hub.mode=subscribe&hub.challenge=test_challenge&hub.verify_token=$VERIFY_TOKEN" \
    || echo "ERROR")

if [ "$TEST_RESPONSE" = "test_challenge" ]; then
    print_status "✅ Webhook verification test passed"
else
    print_warning "⚠️  Webhook verification test failed"
    print_warning "Response: $TEST_RESPONSE"
    print_warning "This may be expected if webhook handler is not fully implemented"
fi

# Save webhook configuration
WEBHOOK_CONFIG_FILE="webhook-config-${ENVIRONMENT}.json"
cat > $WEBHOOK_CONFIG_FILE << EOF
{
  "subscription_id": "$SUBSCRIPTION_ID",
  "callback_url": "$WEBHOOK_URL",
  "verify_token": "$VERIFY_TOKEN",
  "environment": "$ENVIRONMENT",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "client_id": "$STRAVA_CLIENT_ID"
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

echo ""
print_status "🔧 Management Commands:"
echo "  # List subscriptions:"
echo "  curl -X GET 'https://www.strava.com/api/v3/push_subscriptions' -H 'Authorization: Bearer $STRAVA_CLIENT_SECRET'"
echo ""
echo "  # Delete subscription:"
echo "  curl -X DELETE 'https://www.strava.com/api/v3/push_subscriptions/$SUBSCRIPTION_ID' -H 'Authorization: Bearer $STRAVA_CLIENT_SECRET'"
echo ""
echo "  # View subscription details:"
echo "  curl -X GET 'https://www.strava.com/api/v3/push_subscriptions/$SUBSCRIPTION_ID' -H 'Authorization: Bearer $STRAVA_CLIENT_SECRET'"

print_status "✨ Webhook configuration completed successfully!"