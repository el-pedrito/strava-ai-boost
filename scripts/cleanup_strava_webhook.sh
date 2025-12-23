#!/bin/bash

# Cleanup Strava Webhook Subscriptions
# Removes all webhook subscriptions during uninstall process
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/cleanup_strava_webhook.sh [dev|prod]

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

print_section "🧹 Cleaning up Strava webhook subscriptions for $ENVIRONMENT"

# Validate environment
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    print_error "Invalid environment: $ENVIRONMENT. Use 'dev' or 'prod'"
    exit 1
fi

# Try to get Strava credentials from Secrets Manager
print_status "Retrieving Strava credentials from Secrets Manager..."

SECRET_NAME="strava-ai-boost-oauth-tokens"
STRAVA_CLIENT_SECRET=""

if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
    SECRET_VALUE=$(aws secretsmanager get-secret-value --secret-id "$SECRET_NAME" --profile "$PROFILE" --region "$REGION" --query SecretString --output text 2>/dev/null)
    
    if [ -n "$SECRET_VALUE" ]; then
        STRAVA_CLIENT_SECRET=$(echo "$SECRET_VALUE" | jq -r '.client_secret // empty' 2>/dev/null)
        
        if [ -n "$STRAVA_CLIENT_SECRET" ]; then
            print_status "✅ Retrieved Strava credentials from Secrets Manager"
        else
            print_warning "⚠️  No client_secret found in Secrets Manager"
        fi
    else
        print_warning "⚠️  Unable to read secret value"
    fi
else
    print_warning "⚠️  Secrets Manager secret not found: $SECRET_NAME"
fi

# If no credentials from Secrets Manager, check environment variables
if [ -z "$STRAVA_CLIENT_SECRET" ]; then
    if [ -n "$STRAVA_CLIENT_SECRET_ENV" ]; then
        STRAVA_CLIENT_SECRET="$STRAVA_CLIENT_SECRET_ENV"
        print_status "Using Strava credentials from environment variables"
    else
        print_warning "⚠️  No Strava credentials available"
        print_warning "Webhook subscriptions cannot be cleaned up automatically"
        print_warning "You may need to manually remove them at: https://www.strava.com/settings/api"
        exit 0
    fi
fi

# Get existing webhook subscriptions
print_status "Retrieving existing webhook subscriptions..."

SUBSCRIPTIONS=$(curl -s -X GET \
    "https://www.strava.com/api/v3/push_subscriptions" \
    -H "Authorization: Bearer $STRAVA_CLIENT_SECRET" \
    -H "Content-Type: application/json" 2>/dev/null || echo "[]")

# Check if request was successful
if echo "$SUBSCRIPTIONS" | jq -e '.errors' > /dev/null 2>&1; then
    print_error "❌ Failed to retrieve webhook subscriptions"
    ERROR_MESSAGE=$(echo "$SUBSCRIPTIONS" | jq -r '.errors[0].message // "Unknown error"' 2>/dev/null)
    print_error "Error: $ERROR_MESSAGE"
    
    if echo "$ERROR_MESSAGE" | grep -q -i "authorization"; then
        print_error "Invalid Strava API credentials"
        print_error "Check your client_secret in Secrets Manager or environment variables"
    fi
    
    exit 1
fi

SUBSCRIPTION_COUNT=$(echo "$SUBSCRIPTIONS" | jq '. | length' 2>/dev/null || echo "0")

if [ "$SUBSCRIPTION_COUNT" -eq 0 ]; then
    print_status "✅ No webhook subscriptions found to clean up"
    exit 0
fi

print_status "Found $SUBSCRIPTION_COUNT webhook subscription(s) to remove"

# Display subscription details before removal
echo ""
print_status "📋 Webhook subscriptions to be removed:"
echo "$SUBSCRIPTIONS" | jq -r '.[] | "  - ID: \(.id), URL: \(.callback_url), Created: \(.created_at)"' 2>/dev/null || echo "  Unable to parse subscription details"

echo ""
read -p "Proceed with removing all webhook subscriptions? (y/n): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_status "Webhook cleanup cancelled by user"
    exit 0
fi

# Remove each subscription
SUBSCRIPTION_IDS=$(echo "$SUBSCRIPTIONS" | jq -r '.[].id' 2>/dev/null || echo "")
REMOVED_COUNT=0
FAILED_COUNT=0

for SUBSCRIPTION_ID in $SUBSCRIPTION_IDS; do
    if [ -n "$SUBSCRIPTION_ID" ] && [ "$SUBSCRIPTION_ID" != "null" ]; then
        print_status "Removing subscription: $SUBSCRIPTION_ID"
        
        DELETE_RESPONSE=$(curl -s -X DELETE \
            "https://www.strava.com/api/v3/push_subscriptions/$SUBSCRIPTION_ID" \
            -H "Authorization: Bearer $STRAVA_CLIENT_SECRET" \
            -H "Content-Type: application/json" 2>/dev/null)
        
        # Check if deletion was successful
        if echo "$DELETE_RESPONSE" | jq -e '.errors' > /dev/null 2>&1; then
            ERROR_MESSAGE=$(echo "$DELETE_RESPONSE" | jq -r '.errors[0].message // "Unknown error"' 2>/dev/null)
            print_warning "⚠️  Failed to delete subscription $SUBSCRIPTION_ID: $ERROR_MESSAGE"
            ((FAILED_COUNT++))
        else
            print_status "✅ Successfully removed subscription $SUBSCRIPTION_ID"
            ((REMOVED_COUNT++))
        fi
    fi
done

# Clean up webhook configuration from Secrets Manager
print_status "Cleaning up webhook configuration from Secrets Manager..."

if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
    CURRENT_SECRET=$(aws secretsmanager get-secret-value --secret-id "$SECRET_NAME" --profile "$PROFILE" --region "$REGION" --query SecretString --output text 2>/dev/null || echo "{}")
    
    # Remove webhook-related fields
    UPDATED_SECRET=$(echo "$CURRENT_SECRET" | jq 'del(.webhook_verify_token, .webhook_callback_url, .webhook_subscription_id, .webhook_configured_at, .webhook_secret)' 2>/dev/null || echo "$CURRENT_SECRET")
    
    if [ "$UPDATED_SECRET" != "$CURRENT_SECRET" ]; then
        aws secretsmanager put-secret-value \
            --secret-id "$SECRET_NAME" \
            --secret-string "$UPDATED_SECRET" \
            --profile "$PROFILE" \
            --region "$REGION" > /dev/null 2>&1
        
        if [ $? -eq 0 ]; then
            print_status "✅ Cleaned up webhook configuration from Secrets Manager"
        else
            print_warning "⚠️  Failed to clean up webhook configuration from Secrets Manager"
        fi
    else
        print_status "No webhook configuration found in Secrets Manager to clean up"
    fi
fi

# Remove local webhook configuration files
print_status "Cleaning up local webhook configuration files..."

CONFIG_FILES=("webhook-config-${ENVIRONMENT}.json" "webhook-config-dev.json" "webhook-config-prod.json")
REMOVED_FILES=0

for CONFIG_FILE in "${CONFIG_FILES[@]}"; do
    if [ -f "$CONFIG_FILE" ]; then
        rm -f "$CONFIG_FILE"
        print_status "✅ Removed local config file: $CONFIG_FILE"
        ((REMOVED_FILES++))
    fi
done

if [ $REMOVED_FILES -eq 0 ]; then
    print_status "No local webhook configuration files found to clean up"
fi

# Summary
echo ""
print_section "📊 Webhook Cleanup Summary"
echo "  ✅ Webhook subscriptions removed: $REMOVED_COUNT"
echo "  ❌ Failed removals: $FAILED_COUNT"
echo "  🗂️  Local config files removed: $REMOVED_FILES"

if [ $FAILED_COUNT -gt 0 ]; then
    echo ""
    print_warning "⚠️  Some webhook subscriptions could not be removed automatically"
    print_warning "You may need to manually remove them at: https://www.strava.com/settings/api"
    print_warning "Look for subscriptions with callback URLs containing 'strava-ai-boost'"
fi

echo ""
if [ $REMOVED_COUNT -gt 0 ] || [ $REMOVED_FILES -gt 0 ]; then
    print_status "✅ Webhook cleanup completed successfully"
else
    print_status "✅ No webhook cleanup was necessary"
fi

print_status "🔗 Manual verification: https://www.strava.com/settings/api"