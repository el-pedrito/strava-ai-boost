#!/bin/bash

# Reprocess DLQ Messages Script
# Moves messages from DLQ back to processing queue after fixing issues

set -e

PROFILE="${AWS_PROFILE:-your-aws-profile}"
REGION="eu-west-1"

echo "🔄 DLQ Reprocessing Tool"
echo "======================="
echo ""

# Get queue URLs
DLQ_URL=$(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing-dlq --profile $PROFILE --region $REGION --query 'QueueUrl' --output text)
PROCESSING_URL=$(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing --profile $PROFILE --region $REGION --query 'QueueUrl' --output text)

echo "📋 Queue URLs:"
echo "  DLQ: $DLQ_URL"
echo "  Processing: $PROCESSING_URL"
echo ""

# Check DLQ message count
DLQ_COUNT=$(aws sqs get-queue-attributes \
    --queue-url $DLQ_URL \
    --attribute-names ApproximateNumberOfMessages \
    --profile $PROFILE \
    --region $REGION \
    --query 'Attributes.ApproximateNumberOfMessages' \
    --output text)

echo "📊 DLQ Status: $DLQ_COUNT messages"
echo ""

if [ "$DLQ_COUNT" -eq "0" ]; then
    echo "✅ DLQ is empty, nothing to reprocess"
    exit 0
fi

# Ask for confirmation
echo "⚠️  This will reprocess $DLQ_COUNT messages from DLQ"
echo "Make sure you've fixed the underlying issue before proceeding!"
echo ""
echo "Options:"
echo "  1) Reprocess ALL messages"
echo "  2) Reprocess ONE message (for testing)"
echo "  3) Inspect messages only (no reprocessing)"
echo "  4) Cancel"
echo ""
read -p "Choose option (1-4): " option

case $option in
    1)
        echo ""
        echo "🔄 Reprocessing ALL messages..."
        REPROCESSED=0
        
        while true; do
            # Receive message
            MESSAGE=$(aws sqs receive-message \
                --queue-url $DLQ_URL \
                --max-number-of-messages 1 \
                --profile $PROFILE \
                --region $REGION)
            
            # Check if queue is empty
            MSG_COUNT=$(echo "$MESSAGE" | jq -r '.Messages | length' 2>/dev/null || echo "0")
            if [ -z "$MSG_COUNT" ] || [ "$MSG_COUNT" -eq "0" ]; then
                echo "✅ DLQ is now empty"
                break
            fi
            
            # Extract body and receipt handle
            BODY=$(echo "$MESSAGE" | jq -r '.Messages[0].Body')
            RECEIPT_HANDLE=$(echo "$MESSAGE" | jq -r '.Messages[0].ReceiptHandle')
            
            # Check if body is valid
            if [ -z "$BODY" ] || [ "$BODY" = "null" ]; then
                echo "⚠️  Invalid message, skipping"
                continue
            fi
            
            # Resend to processing queue
            aws sqs send-message \
                --queue-url $PROCESSING_URL \
                --message-body "$BODY" \
                --profile $PROFILE \
                --region $REGION > /dev/null
            
            # Delete from DLQ
            aws sqs delete-message \
                --queue-url $DLQ_URL \
                --receipt-handle "$RECEIPT_HANDLE" \
                --profile $PROFILE \
                --region $REGION
            
            REPROCESSED=$((REPROCESSED + 1))
            echo "  ✓ Reprocessed message $REPROCESSED"
            sleep 0.5
        done
        
        echo ""
        echo "✅ Reprocessing complete: $REPROCESSED messages moved to processing queue"
        ;;
        
    2)
        echo ""
        echo "🔄 Reprocessing ONE message..."
        
        # Receive one message
        MESSAGE=$(aws sqs receive-message \
            --queue-url $DLQ_URL \
            --max-number-of-messages 1 \
            --profile $PROFILE \
            --region $REGION)
        
        if [ "$(echo $MESSAGE | jq '.Messages | length')" -eq "0" ]; then
            echo "❌ No messages in DLQ"
            exit 1
        fi
        
        # Show message content
        echo ""
        echo "📄 Message content:"
        echo $MESSAGE | jq '.Messages[0].Body | fromjson'
        echo ""
        
        read -p "Reprocess this message? (y/N): " confirm
        if [[ "$confirm" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            BODY=$(echo $MESSAGE | jq -r '.Messages[0].Body')
            RECEIPT_HANDLE=$(echo $MESSAGE | jq -r '.Messages[0].ReceiptHandle')
            
            # Resend to processing queue
            aws sqs send-message \
                --queue-url $PROCESSING_URL \
                --message-body "$BODY" \
                --profile $PROFILE \
                --region $REGION > /dev/null
            
            # Delete from DLQ
            aws sqs delete-message \
                --queue-url $DLQ_URL \
                --receipt-handle "$RECEIPT_HANDLE" \
                --profile $PROFILE \
                --region $REGION
            
            echo "✅ Message reprocessed"
        else
            echo "Cancelled"
        fi
        ;;
        
    3)
        echo ""
        echo "🔍 Inspecting DLQ messages..."
        echo ""
        
        # Receive up to 10 messages without deleting
        MESSAGES=$(aws sqs receive-message \
            --queue-url $DLQ_URL \
            --max-number-of-messages 10 \
            --attribute-names All \
            --message-attribute-names All \
            --profile $PROFILE \
            --region $REGION)
        
        MESSAGE_COUNT=$(echo $MESSAGES | jq '.Messages | length')
        
        if [ "$MESSAGE_COUNT" -eq "0" ]; then
            echo "No messages to inspect"
            exit 0
        fi
        
        echo "📊 Showing $MESSAGE_COUNT messages:"
        echo ""
        
        for i in $(seq 0 $((MESSAGE_COUNT - 1))); do
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "Message $((i + 1)):"
            echo ""
            echo $MESSAGES | jq ".Messages[$i].Body | fromjson"
            echo ""
        done
        
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "💡 Tip: Messages are NOT deleted during inspection"
        ;;
        
    4)
        echo "Cancelled"
        exit 0
        ;;
        
    *)
        echo "Invalid option"
        exit 1
        ;;
esac

echo ""
echo "📊 Final DLQ Status:"
aws sqs get-queue-attributes \
    --queue-url $DLQ_URL \
    --attribute-names ApproximateNumberOfMessages \
    --profile $PROFILE \
    --region $REGION \
    --query 'Attributes.ApproximateNumberOfMessages' \
    --output text | xargs -I {} echo "  {} messages remaining"
