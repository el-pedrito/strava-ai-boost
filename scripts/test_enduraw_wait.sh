#!/bin/bash

# Test Enduraw Wait Logic Implementation
# This script tests the 2-minute SQS delay for Enduraw Report processing

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
AWS_PROFILE="your-aws-profile"
AWS_REGION="eu-west-1"
USER_CONFIG_TABLE="strava-ai-boost-user-configuration"
ACTIVITIES_TABLE="strava-ai-boost-activities"
QUEUE_NAME="strava-ai-boost-activity-processing"

echo -e "${BLUE}=== Enduraw Wait Logic Test ===${NC}\n"

# Function to print status
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Check if user ID is provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: User ID required${NC}"
    echo "Usage: $0 <user_id> [activity_id]"
    echo ""
    echo "Example:"
    echo "  $0 123456789"
    echo "  $0 123456789 987654321  # Test with specific activity"
    exit 1
fi

USER_ID="$1"
ACTIVITY_ID="${2:-test-$(date +%s)}"

echo -e "${BLUE}Test Configuration:${NC}"
echo "  User ID: $USER_ID"
echo "  Activity ID: $ACTIVITY_ID"
echo "  AWS Profile: $AWS_PROFILE"
echo "  AWS Region: $AWS_REGION"
echo ""

# Step 1: Check current user configuration
echo -e "${BLUE}Step 1: Checking user configuration...${NC}"
USER_CONFIG=$(aws dynamodb get-item \
    --table-name "$USER_CONFIG_TABLE" \
    --key "{\"user_id\": {\"S\": \"$USER_ID\"}}" \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    2>/dev/null || echo "{}")

if echo "$USER_CONFIG" | grep -q "Item"; then
    print_status "User configuration found"
    
    # Check if Enduraw is enabled
    ENDURAW_ENABLED=$(echo "$USER_CONFIG" | jq -r '.Item.modules_config.M.enduraw.M.enabled.BOOL // false')
    
    if [ "$ENDURAW_ENABLED" = "true" ]; then
        print_status "Enduraw module is ENABLED"
    else
        print_info "Enduraw module is DISABLED"
        echo ""
        read -p "Enable Enduraw module for testing? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            aws dynamodb update-item \
                --table-name "$USER_CONFIG_TABLE" \
                --key "{\"user_id\": {\"S\": \"$USER_ID\"}}" \
                --update-expression "SET modules_config.enduraw.enabled = :enabled" \
                --expression-attribute-values '{":enabled": {"BOOL": true}}' \
                --profile "$AWS_PROFILE" \
                --region "$AWS_REGION"
            print_status "Enduraw module enabled"
        else
            print_error "Test requires Enduraw to be enabled. Exiting."
            exit 1
        fi
    fi
else
    print_error "User configuration not found"
    echo ""
    echo "Create user configuration first:"
    echo "  aws dynamodb put-item \\"
    echo "    --table-name $USER_CONFIG_TABLE \\"
    echo "    --item '{\"user_id\": {\"S\": \"$USER_ID\"}, \"modules_config\": {\"M\": {\"enduraw\": {\"M\": {\"enabled\": {\"BOOL\": true}}}}}}' \\"
    echo "    --profile $AWS_PROFILE"
    exit 1
fi

echo ""

# Step 2: Get SQS queue URL
echo -e "${BLUE}Step 2: Getting SQS queue URL...${NC}"
QUEUE_URL=$(aws sqs get-queue-url \
    --queue-name "$QUEUE_NAME" \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --query 'QueueUrl' \
    --output text)

if [ -n "$QUEUE_URL" ]; then
    print_status "Queue URL: $QUEUE_URL"
else
    print_error "Failed to get queue URL"
    exit 1
fi

echo ""

# Step 3: Send test message to SQS
echo -e "${BLUE}Step 3: Sending test message to SQS...${NC}"

TEST_MESSAGE=$(cat <<EOF
{
  "activity_id": "$ACTIVITY_ID",
  "user_id": "$USER_ID",
  "webhook_data": {
    "object_type": "activity",
    "object_id": $ACTIVITY_ID,
    "aspect_type": "create",
    "owner_id": $USER_ID,
    "event_time": $(date +%s)
  },
  "test_mode": true,
  "test_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

MESSAGE_ID=$(aws sqs send-message \
    --queue-url "$QUEUE_URL" \
    --message-body "$TEST_MESSAGE" \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --query 'MessageId' \
    --output text)

if [ -n "$MESSAGE_ID" ]; then
    print_status "Message sent: $MESSAGE_ID"
else
    print_error "Failed to send message"
    exit 1
fi

echo ""

# Step 4: Monitor Lambda logs
echo -e "${BLUE}Step 4: Monitoring Lambda logs...${NC}"
print_info "Watching for Enduraw wait logic (Ctrl+C to stop)"
echo ""

LAMBDA_NAME="StravaAIBoost-ActivityProcessor"
LOG_GROUP="/aws/lambda/$LAMBDA_NAME"

echo -e "${YELLOW}Expected log sequence:${NC}"
echo "  1. 'Enduraw module enabled for activity $ACTIVITY_ID, delaying by 2 minutes'"
echo "  2. 'Activity $ACTIVITY_ID requeued with 2-minute delay'"
echo "  3. [2 minutes later] 'Enduraw wait completed for activity $ACTIVITY_ID'"
echo ""

# Watch logs for 3 minutes
timeout 180 aws logs tail "$LOG_GROUP" \
    --follow \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --filter-pattern "$ACTIVITY_ID" \
    2>/dev/null || true

echo ""
echo -e "${BLUE}=== Test Complete ===${NC}"
echo ""

# Step 5: Check activity status
echo -e "${BLUE}Step 5: Checking activity status...${NC}"

ACTIVITY_STATUS=$(aws dynamodb get-item \
    --table-name "$ACTIVITIES_TABLE" \
    --key "{\"activity_id\": {\"S\": \"$ACTIVITY_ID\"}}" \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    2>/dev/null || echo "{}")

if echo "$ACTIVITY_STATUS" | grep -q "Item"; then
    STATUS=$(echo "$ACTIVITY_STATUS" | jq -r '.Item.processing_status.S // "unknown"')
    print_status "Activity status: $STATUS"
    
    if [ "$STATUS" = "waiting_enduraw" ]; then
        print_info "Activity is waiting for Enduraw processing (expected)"
    elif [ "$STATUS" = "processing" ] || [ "$STATUS" = "completed" ]; then
        print_status "Activity processed successfully"
    fi
else
    print_info "Activity not found in DynamoDB (may not have been created yet)"
fi

echo ""

# Step 6: Check SQS for delayed message
echo -e "${BLUE}Step 6: Checking SQS for delayed message...${NC}"

QUEUE_ATTRS=$(aws sqs get-queue-attributes \
    --queue-url "$QUEUE_URL" \
    --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesDelayed \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION")

VISIBLE_MESSAGES=$(echo "$QUEUE_ATTRS" | jq -r '.Attributes.ApproximateNumberOfMessages')
DELAYED_MESSAGES=$(echo "$QUEUE_ATTRS" | jq -r '.Attributes.ApproximateNumberOfMessagesDelayed')

echo "  Visible messages: $VISIBLE_MESSAGES"
echo "  Delayed messages: $DELAYED_MESSAGES"

if [ "$DELAYED_MESSAGES" -gt 0 ]; then
    print_status "Delayed message found (Enduraw wait in progress)"
else
    print_info "No delayed messages (may have already been processed)"
fi

echo ""
echo -e "${GREEN}=== Test Summary ===${NC}"
echo ""
echo "✓ User configuration verified"
echo "✓ Test message sent to SQS"
echo "✓ Lambda logs monitored"
echo "✓ Activity status checked"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Wait 2 minutes for Enduraw delay to complete"
echo "2. Check Lambda logs again for 'Enduraw wait completed' message"
echo "3. Verify activity processes normally after delay"
echo ""
echo "Monitor logs:"
echo "  aws logs tail $LOG_GROUP --follow --profile $AWS_PROFILE --region $AWS_REGION"
echo ""
echo "Check activity status:"
echo "  aws dynamodb get-item --table-name $ACTIVITIES_TABLE --key '{\"activity_id\": {\"S\": \"$ACTIVITY_ID\"}}' --profile $AWS_PROFILE"
echo ""
