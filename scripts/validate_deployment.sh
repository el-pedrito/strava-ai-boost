#!/bin/bash

# Validate Strava AI Boost Deployment
# Comprehensive validation of deployed infrastructure and services
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/validate_deployment.sh [dev|prod]

set -e

# Configuration
ENVIRONMENT="${1:-dev}"
REGION="${AWS_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
PROJECT_NAME="strava-ai-boost"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Counters
CHECKS_PASSED=0
CHECKS_FAILED=0
WARNINGS=0

print_check() {
    echo -e "${BLUE}[CHECK]${NC} $1"
}

print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((CHECKS_PASSED++))
}

print_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((CHECKS_FAILED++))
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    ((WARNINGS++))
}

print_section() {
    echo -e "${BLUE}[SECTION]${NC} $1"
}

print_section "🔍 Validating Strava AI Boost deployment for $ENVIRONMENT environment"

# Validate environment parameter
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    print_fail "Invalid environment: $ENVIRONMENT. Use 'dev' or 'prod'"
    exit 1
fi

# Section 1: AWS Connectivity and Permissions
print_section "1. AWS Connectivity and Permissions"

print_check "AWS profile configuration"
if aws sts get-caller-identity --profile $PROFILE --region $REGION > /dev/null 2>&1; then
    ACCOUNT_ID=$(aws sts get-caller-identity --profile $PROFILE --region $REGION --query Account --output text)
    print_pass "AWS profile $PROFILE configured (Account: $ACCOUNT_ID)"
else
    print_fail "AWS profile $PROFILE not configured or invalid"
fi

print_check "AWS region accessibility"
if aws ec2 describe-regions --region $REGION --profile $PROFILE > /dev/null 2>&1; then
    print_pass "Region $REGION is accessible"
else
    print_fail "Region $REGION is not accessible"
fi

# Section 2: CloudFormation Stacks
print_section "2. CloudFormation Stacks"

EXPECTED_STACKS=(
    "StravaAIBoost-Core"
    "StravaAIBoost-Content"
    "StravaAIBoost-Webhook"
    "StravaAIBoost-API"
    "StravaAIBoost-Monitoring"
)

for stack in "${EXPECTED_STACKS[@]}"; do
    print_check "CloudFormation stack: $stack"
    
    STACK_STATUS=$(aws cloudformation describe-stacks --stack-name $stack --profile $PROFILE --region $REGION --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NOT_FOUND")
    
    case $STACK_STATUS in
        "CREATE_COMPLETE"|"UPDATE_COMPLETE")
            print_pass "Stack $stack is deployed and healthy"
            ;;
        "CREATE_IN_PROGRESS"|"UPDATE_IN_PROGRESS")
            print_warning "Stack $stack is still deploying"
            ;;
        "CREATE_FAILED"|"UPDATE_FAILED"|"ROLLBACK_COMPLETE")
            print_fail "Stack $stack deployment failed (Status: $STACK_STATUS)"
            ;;
        "NOT_FOUND")
            print_fail "Stack $stack not found"
            ;;
        *)
            print_warning "Stack $stack has unexpected status: $STACK_STATUS"
            ;;
    esac
done

# Section 3: DynamoDB Tables
print_section "3. DynamoDB Tables"

EXPECTED_TABLES=(
    "strava-ai-boost-activities"
    "strava-ai-boost-user-configuration"
    "strava-ai-boost-rate-limits"
)

for table in "${EXPECTED_TABLES[@]}"; do
    print_check "DynamoDB table: $table"
    
    TABLE_STATUS=$(aws dynamodb describe-table --table-name $table --profile $PROFILE --region $REGION --query 'Table.TableStatus' --output text 2>/dev/null || echo "NOT_FOUND")
    
    case $TABLE_STATUS in
        "ACTIVE")
            print_pass "Table $table is active"
            
            # Check encryption
            ENCRYPTION=$(aws dynamodb describe-table --table-name $table --profile $PROFILE --region $REGION --query 'Table.SSEDescription.Status' --output text 2>/dev/null || echo "NONE")
            if [ "$ENCRYPTION" = "ENABLED" ]; then
                print_pass "Table $table has encryption enabled"
            else
                print_warning "Table $table encryption status: $ENCRYPTION"
            fi
            ;;
        "CREATING")
            print_warning "Table $table is still being created"
            ;;
        "NOT_FOUND")
            print_fail "Table $table not found"
            ;;
        *)
            print_fail "Table $table has unexpected status: $TABLE_STATUS"
            ;;
    esac
done

# Section 4: Lambda Functions
print_section "4. Lambda Functions"

EXPECTED_FUNCTIONS=(
    "StravaAIBoost-WebhookHandler"
    "StravaAIBoost-ActivityProcessor"
    "StravaAIBoost-ContentGenerator"
    "StravaAIBoost-ActivityFetcher"
    "StravaAIBoost-StravaUpdater"
    "StravaAIBoost-CampusCoachInvoker"
    "StravaAIBoost-ConfigurationAPI"
    "StravaAIBoost-DashboardAPI"
    "StravaAIBoost-StatusAPI"
)

LAMBDA_FUNCTIONS=$(aws lambda list-functions --profile $PROFILE --region $REGION --query 'Functions[].FunctionName' --output text)

for function in "${EXPECTED_FUNCTIONS[@]}"; do
    print_check "Lambda function: $function"
    
    if echo "$LAMBDA_FUNCTIONS" | grep -q "$function"; then
        print_pass "Function $function exists"
        
        # Check function configuration
        RUNTIME=$(aws lambda get-function --function-name $function --profile $PROFILE --region $REGION --query 'Configuration.Runtime' --output text 2>/dev/null || echo "UNKNOWN")
        if [ "$RUNTIME" = "python3.12" ]; then
            print_pass "Function $function uses correct runtime: $RUNTIME"
        else
            print_warning "Function $function uses runtime: $RUNTIME (expected python3.12)"
        fi
        
        # Check function state
        STATE=$(aws lambda get-function --function-name $function --profile $PROFILE --region $REGION --query 'Configuration.State' --output text 2>/dev/null || echo "UNKNOWN")
        if [ "$STATE" = "Active" ]; then
            print_pass "Function $function is active"
        else
            print_warning "Function $function state: $STATE"
        fi
    else
        print_fail "Function $function not found"
    fi
done

# Section 5: SQS Queues
print_section "5. SQS Queues"

print_check "SQS queues"
SQS_QUEUES=$(aws sqs list-queues --profile $PROFILE --region $REGION --query 'QueueUrls[]' --output text 2>/dev/null || echo "")

if echo "$SQS_QUEUES" | grep -q "strava-ai-boost"; then
    QUEUE_COUNT=$(echo "$SQS_QUEUES" | grep -c "strava-ai-boost" || echo "0")
    print_pass "Found $QUEUE_COUNT SQS queue(s) for strava-ai-boost"
    
    # Check main processing queue
    MAIN_QUEUE_URL=$(echo "$SQS_QUEUES" | grep "strava-ai-boost-activity-processing" | head -1)
    if [ -n "$MAIN_QUEUE_URL" ]; then
        print_pass "Main processing queue exists"
        
        # Check queue attributes
        VISIBILITY_TIMEOUT=$(aws sqs get-queue-attributes --queue-url "$MAIN_QUEUE_URL" --attribute-names VisibilityTimeout --profile $PROFILE --region $REGION --query 'Attributes.VisibilityTimeout' --output text 2>/dev/null || echo "UNKNOWN")
        print_pass "Queue visibility timeout: ${VISIBILITY_TIMEOUT}s"
    else
        print_fail "Main processing queue not found"
    fi
    
    # Check dead letter queue
    DLQ_URL=$(echo "$SQS_QUEUES" | grep "strava-ai-boost.*dlq\|strava-ai-boost.*dead" | head -1)
    if [ -n "$DLQ_URL" ]; then
        print_pass "Dead letter queue exists"
    else
        print_warning "Dead letter queue not found"
    fi
else
    print_fail "No SQS queues found for strava-ai-boost"
fi

# Section 6: Step Functions
print_section "6. Step Functions"

print_check "Step Functions state machines"
STATE_MACHINES=$(aws stepfunctions list-state-machines --profile $PROFILE --region $REGION --query 'stateMachines[].name' --output text 2>/dev/null || echo "")

if echo "$STATE_MACHINES" | grep -q "StravaAIBoost"; then
    STATE_MACHINE_COUNT=$(echo "$STATE_MACHINES" | grep -c "StravaAIBoost" || echo "0")
    print_pass "Found $STATE_MACHINE_COUNT Step Functions state machine(s)"
    
    # Get state machine ARN and check status
    STATE_MACHINE_ARN=$(aws stepfunctions list-state-machines --profile $PROFILE --region $REGION --query 'stateMachines[?contains(name, `StravaAIBoost`)].stateMachineArn' --output text | head -1)
    
    if [ -n "$STATE_MACHINE_ARN" ]; then
        STATE_MACHINE_STATUS=$(aws stepfunctions describe-state-machine --state-machine-arn "$STATE_MACHINE_ARN" --profile $PROFILE --region $REGION --query 'status' --output text 2>/dev/null || echo "UNKNOWN")
        
        if [ "$STATE_MACHINE_STATUS" = "ACTIVE" ]; then
            print_pass "State machine is active"
        else
            print_warning "State machine status: $STATE_MACHINE_STATUS"
        fi
    fi
else
    print_fail "No Step Functions state machines found for StravaAIBoost"
fi

# Section 7: API Gateway
print_section "7. API Gateway"

print_check "API Gateway REST APIs"
REST_APIS=$(aws apigateway get-rest-apis --profile $PROFILE --region $REGION --query 'items[].name' --output text 2>/dev/null || echo "")

if echo "$REST_APIS" | grep -q "StravaAIBoost"; then
    API_COUNT=$(echo "$REST_APIS" | grep -c "StravaAIBoost" || echo "0")
    print_pass "Found $API_COUNT API Gateway REST API(s)"
    
    # Get API ID and test endpoint
    API_ID=$(aws apigateway get-rest-apis --profile $PROFILE --region $REGION --query 'items[?contains(name, `StravaAIBoost`)].id' --output text | head -1)
    
    if [ -n "$API_ID" ]; then
        WEBHOOK_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod/webhook"
        print_pass "Webhook URL: $WEBHOOK_URL"
        
        # Test webhook endpoint (basic connectivity)
        HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$WEBHOOK_URL" --max-time 10 || echo "000")
        
        if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "405" ]; then
            print_pass "Webhook endpoint is accessible (HTTP $HTTP_STATUS)"
        elif [ "$HTTP_STATUS" = "000" ]; then
            print_warning "Could not reach webhook endpoint (timeout or network error)"
        else
            print_warning "Webhook endpoint returned HTTP $HTTP_STATUS"
        fi
    fi
else
    print_fail "No API Gateway REST APIs found for StravaAIBoost"
fi

# Section 8: Secrets Manager
print_section "8. Secrets Manager"

EXPECTED_SECRETS=(
    "strava-ai-boost-oauth-tokens"
    "strava-ai-boost-campus-coach-credentials"
)

for secret in "${EXPECTED_SECRETS[@]}"; do
    print_check "Secret: $secret"
    
    SECRET_STATUS=$(aws secretsmanager describe-secret --secret-id $secret --profile $PROFILE --region $REGION --query 'Name' --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [ "$SECRET_STATUS" != "NOT_FOUND" ]; then
        print_pass "Secret $secret exists"
        
        # Check if secret has a value
        SECRET_VALUE=$(aws secretsmanager get-secret-value --secret-id $secret --profile $PROFILE --region $REGION --query 'SecretString' --output text 2>/dev/null || echo "")
        
        if [ -n "$SECRET_VALUE" ] && [ "$SECRET_VALUE" != "null" ]; then
            # Check if it's still placeholder values
            if echo "$SECRET_VALUE" | grep -q "REPLACE_WITH_YOUR"; then
                print_warning "Secret $secret contains placeholder values - needs configuration"
            else
                print_pass "Secret $secret has been configured"
            fi
        else
            print_warning "Secret $secret exists but has no value"
        fi
    else
        print_fail "Secret $secret not found"
    fi
done

# Section 9: AgentCore Resources (if available)
print_section "9. AgentCore Resources"

print_check "AgentCore CLI availability"
if command -v agentcore &> /dev/null; then
    print_pass "AgentCore CLI is available"
    
    # Check AgentCore memory
    print_check "AgentCore Memory"
    MEMORY_NAME="strava-ai-boost-memory-${ENVIRONMENT}"
    
    if agentcore memory list --profile $PROFILE --region $REGION 2>/dev/null | grep -q "$MEMORY_NAME"; then
        print_pass "AgentCore Memory $MEMORY_NAME exists"
    else
        print_warning "AgentCore Memory $MEMORY_NAME not found"
    fi
    
    # Check AgentCore agents
    print_check "AgentCore Agents"
    CONTENT_AGENT_NAME="contentgen-${ENVIRONMENT}"
    CAMPUS_AGENT_NAME="campuscoach-${ENVIRONMENT}"
    
    AGENT_LIST=$(agentcore agent list --profile $PROFILE --region $REGION 2>/dev/null || echo "")
    
    if echo "$AGENT_LIST" | grep -q "$CONTENT_AGENT_NAME"; then
        print_pass "Content generation agent $CONTENT_AGENT_NAME exists"
    else
        print_warning "Content generation agent $CONTENT_AGENT_NAME not found"
    fi
    
    if echo "$AGENT_LIST" | grep -q "$CAMPUS_AGENT_NAME"; then
        print_pass "Campus Coach agent $CAMPUS_AGENT_NAME exists"
    else
        print_warning "Campus Coach agent $CAMPUS_AGENT_NAME not found"
    fi
else
    print_warning "AgentCore CLI not available - skipping AgentCore validation"
fi

# Section 10: Integration Tests
print_section "10. Basic Integration Tests"

print_check "DynamoDB write/read test"
TEST_ITEM_ID="validation-test-$(date +%s)"

# Write test item
if aws dynamodb put-item \
    --table-name "strava-ai-boost-user-configuration" \
    --item "{\"user_id\":{\"S\":\"$TEST_ITEM_ID\"},\"test_data\":{\"S\":\"validation\"}}" \
    --profile $PROFILE --region $REGION > /dev/null 2>&1; then
    
    # Read test item
    if aws dynamodb get-item \
        --table-name "strava-ai-boost-user-configuration" \
        --key "{\"user_id\":{\"S\":\"$TEST_ITEM_ID\"}}" \
        --profile $PROFILE --region $REGION > /dev/null 2>&1; then
        
        print_pass "DynamoDB read/write test successful"
        
        # Clean up test item
        aws dynamodb delete-item \
            --table-name "strava-ai-boost-user-configuration" \
            --key "{\"user_id\":{\"S\":\"$TEST_ITEM_ID\"}}" \
            --profile $PROFILE --region $REGION > /dev/null 2>&1
    else
        print_fail "DynamoDB read test failed"
    fi
else
    print_fail "DynamoDB write test failed"
fi

# Summary
print_section "📊 Validation Summary"

echo ""
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo "Account: ${ACCOUNT_ID:-unknown}"
echo ""
echo "Results:"
echo "  ✅ Checks passed: $CHECKS_PASSED"
echo "  ❌ Checks failed: $CHECKS_FAILED"
echo "  ⚠️  Warnings: $WARNINGS"

# Generate validation report
VALIDATION_REPORT="validation-report-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S).json"
cat > $VALIDATION_REPORT << EOF
{
  "validation_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "environment": "$ENVIRONMENT",
  "region": "$REGION",
  "account_id": "${ACCOUNT_ID:-unknown}",
  "profile": "$PROFILE",
  "results": {
    "checks_passed": $CHECKS_PASSED,
    "checks_failed": $CHECKS_FAILED,
    "warnings": $WARNINGS,
    "total_checks": $((CHECKS_PASSED + CHECKS_FAILED))
  },
  "status": "$([ $CHECKS_FAILED -eq 0 ] && echo "HEALTHY" || echo "ISSUES_FOUND")"
}
EOF

echo ""
echo "Validation report saved to: $VALIDATION_REPORT"

if [ $CHECKS_FAILED -eq 0 ]; then
    echo ""
    print_pass "✨ Deployment validation completed successfully!"
    echo ""
    echo "🚀 Next steps:"
    echo "  1. Configure Strava OAuth credentials in Secrets Manager"
    echo "  2. Set up Strava webhook subscription: ./scripts/configure_strava_webhook.sh $ENVIRONMENT"
    echo "  3. Start local web interface: cd local_interface && python app.py"
    echo "  4. Test with a sample Strava activity"
    exit 0
else
    echo ""
    print_fail "❌ Deployment validation found issues that need attention."
    echo ""
    echo "🔧 Troubleshooting:"
    echo "  1. Check CloudFormation stack events for deployment errors"
    echo "  2. Verify AWS permissions and quotas"
    echo "  3. Review CloudWatch logs for Lambda function errors"
    echo "  4. Re-run deployment if resources are missing"
    exit 1
fi