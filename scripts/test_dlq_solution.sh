#!/bin/bash

# Test Script for DLQ Solution
# Tests both Lambda failures and Step Functions failures

set -e

PROFILE="your-aws-profile"
REGION="eu-west-1"

echo "🧪 Testing DLQ Solution for Strava AI Boost"
echo "============================================"
echo ""

# Get queue URLs
echo "📋 Getting queue URLs..."
PROCESSING_QUEUE_URL=$(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing --profile $PROFILE --region $REGION --query 'QueueUrl' --output text)
DLQ_URL=$(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing-dlq --profile $PROFILE --region $REGION --query 'QueueUrl' --output text)

echo "✅ Processing Queue: $PROCESSING_QUEUE_URL"
echo "✅ DLQ: $DLQ_URL"
echo ""

# Function to check DLQ messages
check_dlq() {
    local count=$(aws sqs get-queue-attributes \
        --queue-url $DLQ_URL \
        --attribute-names ApproximateNumberOfMessagesVisible \
        --profile $PROFILE \
        --region $REGION \
        --query 'Attributes.ApproximateNumberOfMessagesVisible' \
        --output text)
    echo $count
}

# Function to check processing queue messages
check_processing_queue() {
    local count=$(aws sqs get-queue-attributes \
        --queue-url $PROCESSING_QUEUE_URL \
        --attribute-names ApproximateNumberOfMessagesVisible \
        --profile $PROFILE \
        --region $REGION \
        --query 'Attributes.ApproximateNumberOfMessagesVisible' \
        --output text)
    echo $count
}

echo "📊 Initial Queue Status"
echo "----------------------"
echo "Processing Queue Messages: $(check_processing_queue)"
echo "DLQ Messages: $(check_dlq)"
echo ""

# Test 1: Lambda Failure (Malformed Message)
echo "🧪 Test 1: Lambda Failure (Malformed Message)"
echo "---------------------------------------------"
echo "Sending malformed message to trigger Lambda failure..."

MALFORMED_MESSAGE='{"invalid": "data", "missing": "activity_id"}'

aws sqs send-message \
    --queue-url $PROCESSING_QUEUE_URL \
    --message-body "$MALFORMED_MESSAGE" \
    --profile $PROFILE \
    --region $REGION > /dev/null

echo "✅ Malformed message sent"
echo "⏳ Waiting for 3 retries (this will take ~5 minutes)..."
echo ""
echo "You can monitor the logs with:"
echo "aws logs tail /aws/lambda/StravaAIBoost-ActivityProcessor --follow --profile $PROFILE"
echo ""
echo "Press Enter when you want to check the DLQ (after ~5 minutes)..."
read

DLQ_COUNT=$(check_dlq)
echo "📊 DLQ Messages: $DLQ_COUNT"

if [ "$DLQ_COUNT" -gt "0" ]; then
    echo "✅ Test 1 PASSED: Message moved to DLQ after retries"
    echo ""
    echo "📄 DLQ Message Content:"
    aws sqs receive-message \
        --queue-url $DLQ_URL \
        --max-number-of-messages 1 \
        --profile $PROFILE \
        --region $REGION | jq '.Messages[0].Body | fromjson'
else
    echo "❌ Test 1 FAILED: Message not in DLQ"
fi

echo ""
echo "---"
echo ""

# Test 2: Step Functions Failure
echo "🧪 Test 2: Step Functions Failure"
echo "----------------------------------"
echo "This test requires manually triggering a Step Functions failure."
echo ""
echo "Options to trigger a Step Functions failure:"
echo "1. Send a valid webhook for an activity that doesn't exist on Strava"
echo "2. Temporarily disable Bedrock access"
echo "3. Manually fail a Step Functions execution"
echo ""
echo "To manually test:"
echo "1. Get the Step Functions ARN:"
echo "   aws stepfunctions list-state-machines --profile $PROFILE --query 'stateMachines[?name==\`StravaAIBoost-ActivityProcessing\`].stateMachineArn' --output text"
echo ""
echo "2. Start an execution that will fail:"
echo "   aws stepfunctions start-execution \\"
echo "     --state-machine-arn <ARN> \\"
echo "     --name test-failure-\$(date +%s) \\"
echo "     --input '{\"activity_id\": \"999999999\", \"user_id\": \"test\", \"webhook_data\": {}}' \\"
echo "     --profile $PROFILE"
echo ""
echo "3. Wait for the execution to fail (~1-2 minutes)"
echo ""
echo "4. Check the DLQ:"
echo "   aws sqs receive-message --queue-url $DLQ_URL --profile $PROFILE | jq '.Messages[0].Body | fromjson'"
echo ""
echo "5. Check the error handler logs:"
echo "   aws logs tail /aws/lambda/StravaAIBoost-StepFunctionsErrorHandler --follow --profile $PROFILE"
echo ""

# Cleanup option
echo ""
echo "🧹 Cleanup"
echo "----------"
echo "Do you want to purge the DLQ? (y/N)"
read -r response

if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "Purging DLQ..."
    aws sqs purge-queue --queue-url $DLQ_URL --profile $PROFILE --region $REGION
    echo "✅ DLQ purged"
else
    echo "Skipping cleanup"
fi

echo ""
echo "✅ Testing complete!"
echo ""
echo "📊 Final Queue Status"
echo "--------------------"
echo "Processing Queue Messages: $(check_processing_queue)"
echo "DLQ Messages: $(check_dlq)"
echo ""
echo "📚 For more information, see:"
echo "  - docs/SQS_DLQ_SOLUTION.md"
echo "  - docs/DLQ_ARCHITECTURE.md"
