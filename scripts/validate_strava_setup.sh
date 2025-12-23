#!/bin/bash

# Validate Strava Application Configuration
# Comprehensive validation of Strava API application setup and connectivity
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/validate_strava_setup.sh [dev|prod] [--detailed] [--fix-issues]
#
# Options:
#   --detailed: Show detailed validation information
#   --fix-issues: Attempt to automatically fix common issues
#   --oauth-test: Test OAuth flow (requires user interaction)

set -e

# Configuration
ENVIRONMENT="${1:-dev}"
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
DETAILED_MODE=false
FIX_ISSUES=false
OAUTH_TEST=false

# Parse command line options
while [[ $# -gt 0 ]]; do
    case $1 in
        --detailed)
            DETAILED_MODE=true
            shift
            ;;
        --fix-issues)
            FIX_ISSUES=true
            shift
            ;;
        --oauth-test)
            OAUTH_TEST=true
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
CYAN='\033[0;36m'
NC='\033[0m'

# Validation counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

print_status() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED_CHECKS++))
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARNING_CHECKS++))
}

print_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED_CHECKS++))
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_section() {
    echo -e "${CYAN}[SECTION]${NC} $1"
}

print_check() {
    echo -e "${BLUE}[CHECK]${NC} $1"
    ((TOTAL_CHECKS++))
}

print_section "🔍 Validating Strava application configuration for $ENVIRONMENT"

# Validate environment
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    print_error "Invalid environment: $ENVIRONMENT. Use 'dev' or 'prod'"
    exit 1
fi

# Check 1: AWS Credentials and Profile
print_check "AWS credentials and profile configuration"
if aws sts get-caller-identity --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
    ACCOUNT_ID=$(aws sts get-caller-identity --profile "$PROFILE" --region "$REGION" --query Account --output text)
    print_status "AWS credentials valid (Account: $ACCOUNT_ID, Profile: $PROFILE)"
    
    if [ "$DETAILED_MODE" = true ]; then
        CALLER_IDENTITY=$(aws sts get-caller-identity --profile "$PROFILE" --region "$REGION")
        print_info "Caller Identity: $(echo "$CALLER_IDENTITY" | jq -c .)"
    fi
else
    print_error "AWS credentials not configured for profile: $PROFILE"
    if [ "$FIX_ISSUES" = true ]; then
        print_info "Fix: Run 'aws configure --profile $PROFILE' to set up credentials"
    fi
fi

# Check 2: Secrets Manager Configuration
print_check "Secrets Manager configuration"
SECRET_NAME="strava-ai-boost-oauth-tokens"

if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
    print_status "Secrets Manager secret exists: $SECRET_NAME"
    
    # Check secret contents
    SECRET_VALUE=$(aws secretsmanager get-secret-value --secret-id "$SECRET_NAME" --profile "$PROFILE" --region "$REGION" --query SecretString --output text 2>/dev/null)
    
    if [ -n "$SECRET_VALUE" ]; then
        # Parse and validate secret structure
        CLIENT_ID=$(echo "$SECRET_VALUE" | jq -r '.client_id // empty' 2>/dev/null)
        CLIENT_SECRET=$(echo "$SECRET_VALUE" | jq -r '.client_secret // empty' 2>/dev/null)
        WEBHOOK_VERIFY_TOKEN=$(echo "$SECRET_VALUE" | jq -r '.webhook_verify_token // empty' 2>/dev/null)
        
        if [ -n "$CLIENT_ID" ] && [ "$CLIENT_ID" != "null" ]; then
            print_status "Strava client ID configured"
            if [ "$DETAILED_MODE" = true ]; then
                print_info "Client ID: ${CLIENT_ID:0:8}... (truncated)"
            fi
        else
            print_error "Strava client ID missing in secret"
            if [ "$FIX_ISSUES" = true ]; then
                print_info "Fix: Update secret with your Strava application client ID"
                print_info "aws secretsmanager put-secret-value --secret-id '$SECRET_NAME' --secret-string '{\"client_id\":\"YOUR_CLIENT_ID\",\"client_secret\":\"YOUR_CLIENT_SECRET\"}' --profile $PROFILE"
            fi
        fi
        
        if [ -n "$CLIENT_SECRET" ] && [ "$CLIENT_SECRET" != "null" ]; then
            print_status "Strava client secret configured"
        else
            print_error "Strava client secret missing in secret"
            if [ "$FIX_ISSUES" = true ]; then
                print_info "Fix: Update secret with your Strava application client secret"
            fi
        fi
        
        if [ -n "$WEBHOOK_VERIFY_TOKEN" ] && [ "$WEBHOOK_VERIFY_TOKEN" != "null" ]; then
            print_status "Webhook verify token configured"
        else
            print_warning "Webhook verify token not configured (will use default)"
            if [ "$FIX_ISSUES" = true ]; then
                print_info "Fix: Add webhook_verify_token to secret for enhanced security"
            fi
        fi
    else
        print_error "Unable to read secret value"
    fi
else
    print_error "Secrets Manager secret not found: $SECRET_NAME"
    if [ "$FIX_ISSUES" = true ]; then
        print_info "Fix: Create secret with Strava application credentials"
        print_info "aws secretsmanager create-secret --name '$SECRET_NAME' --secret-string '{\"client_id\":\"YOUR_CLIENT_ID\",\"client_secret\":\"YOUR_CLIENT_SECRET\"}' --profile $PROFILE"
    fi
fi

# Check 3: Strava API Connectivity
print_check "Strava API connectivity"
if [ -n "$CLIENT_ID" ] && [ -n "$CLIENT_SECRET" ]; then
    # Test Strava API connectivity
    STRAVA_API_RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/strava_test_response \
        "https://www.strava.com/api/v3/athlete" \
        -H "Authorization: Bearer $CLIENT_SECRET" 2>/dev/null || echo "000")
    
    if [ "$STRAVA_API_RESPONSE" = "401" ]; then
        print_status "Strava API accessible (authentication required as expected)"
    elif [ "$STRAVA_API_RESPONSE" = "200" ]; then
        print_warning "Strava API returned 200 - client_secret might be an access token"
        if [ "$DETAILED_MODE" = true ]; then
            print_info "Response: $(cat /tmp/strava_test_response 2>/dev/null | head -c 200)"
        fi
    elif [ "$STRAVA_API_RESPONSE" = "000" ]; then
        print_error "Cannot reach Strava API (network/DNS issue)"
    else
        print_warning "Strava API returned unexpected status: $STRAVA_API_RESPONSE"
        if [ "$DETAILED_MODE" = true ]; then
            print_info "Response: $(cat /tmp/strava_test_response 2>/dev/null | head -c 200)"
        fi
    fi
    
    # Clean up temp file
    rm -f /tmp/strava_test_response
    
    # Test webhook subscriptions endpoint
    print_check "Strava webhook API access"
    WEBHOOK_API_RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/strava_webhook_test \
        "https://www.strava.com/api/v3/push_subscriptions" \
        -H "Authorization: Bearer $CLIENT_SECRET" 2>/dev/null || echo "000")
    
    if [ "$WEBHOOK_API_RESPONSE" = "200" ]; then
        print_status "Strava webhook API accessible"
        
        # Check existing subscriptions
        SUBSCRIPTIONS=$(cat /tmp/strava_webhook_test 2>/dev/null)
        SUBSCRIPTION_COUNT=$(echo "$SUBSCRIPTIONS" | jq '. | length' 2>/dev/null || echo "0")
        
        if [ "$SUBSCRIPTION_COUNT" -gt 0 ]; then
            print_info "Found $SUBSCRIPTION_COUNT existing webhook subscription(s)"
            if [ "$DETAILED_MODE" = true ]; then
                echo "$SUBSCRIPTIONS" | jq -r '.[] | "  - ID: \(.id), URL: \(.callback_url)"' 2>/dev/null || echo "  Unable to parse subscriptions"
            fi
        else
            print_info "No existing webhook subscriptions found"
        fi
    elif [ "$WEBHOOK_API_RESPONSE" = "401" ]; then
        print_error "Strava webhook API authentication failed"
        print_error "Check your client_secret - it should be the client secret, not an access token"
    else
        print_warning "Strava webhook API returned status: $WEBHOOK_API_RESPONSE"
    fi
    
    rm -f /tmp/strava_webhook_test
else
    print_error "Cannot test Strava API - missing credentials"
fi

# Check 4: Strava Application Configuration
print_check "Strava application configuration validation"
if [ -n "$CLIENT_ID" ]; then
    # Validate client ID format (should be numeric)
    if [[ "$CLIENT_ID" =~ ^[0-9]+$ ]]; then
        print_status "Client ID format valid (numeric)"
    else
        print_error "Client ID format invalid (should be numeric)"
    fi
    
    # Check client ID length (typical Strava client IDs are 5-6 digits)
    CLIENT_ID_LENGTH=${#CLIENT_ID}
    if [ "$CLIENT_ID_LENGTH" -ge 4 ] && [ "$CLIENT_ID_LENGTH" -le 8 ]; then
        print_status "Client ID length reasonable ($CLIENT_ID_LENGTH digits)"
    else
        print_warning "Client ID length unusual ($CLIENT_ID_LENGTH digits)"
    fi
else
    print_error "Cannot validate application configuration - missing client ID"
fi

# Check 5: AWS Infrastructure Deployment
print_check "AWS infrastructure deployment"

# Check API Gateway
API_ID=$(aws apigateway get-rest-apis --profile "$PROFILE" --region "$REGION" --query "items[?contains(name, 'StravaAIBoost')].id" --output text 2>/dev/null | head -1)

if [ -n "$API_ID" ]; then
    print_status "API Gateway deployed (ID: $API_ID)"
    
    # Test webhook endpoint
    WEBHOOK_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod/webhook"
    print_check "Webhook endpoint accessibility"
    
    WEBHOOK_TEST_RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/webhook_test \
        "$WEBHOOK_URL?hub.mode=subscribe&hub.challenge=test&hub.verify_token=test" 2>/dev/null || echo "000")
    
    if [ "$WEBHOOK_TEST_RESPONSE" = "200" ]; then
        print_status "Webhook endpoint accessible and responding"
        
        # Check if it returns the challenge
        CHALLENGE_RESPONSE=$(cat /tmp/webhook_test 2>/dev/null)
        if echo "$CHALLENGE_RESPONSE" | jq -e '.["hub.challenge"]' > /dev/null 2>&1; then
            RETURNED_CHALLENGE=$(echo "$CHALLENGE_RESPONSE" | jq -r '.["hub.challenge"]')
            if [ "$RETURNED_CHALLENGE" = "test" ]; then
                print_status "Webhook verification working correctly"
            else
                print_warning "Webhook returned wrong challenge: $RETURNED_CHALLENGE"
            fi
        else
            print_warning "Webhook response format unexpected: $CHALLENGE_RESPONSE"
        fi
    else
        print_error "Webhook endpoint not accessible (HTTP $WEBHOOK_TEST_RESPONSE)"
        if [ "$FIX_ISSUES" = true ]; then
            print_info "Fix: Deploy CDK stacks first: cdk deploy --all --profile $PROFILE"
        fi
    fi
    
    rm -f /tmp/webhook_test
else
    print_error "API Gateway not found - CDK stacks not deployed"
    if [ "$FIX_ISSUES" = true ]; then
        print_info "Fix: Deploy infrastructure: ./scripts/deploy.sh $ENVIRONMENT"
    fi
fi

# Check Lambda functions
print_check "Lambda functions deployment"
LAMBDA_FUNCTIONS=$(aws lambda list-functions --profile "$PROFILE" --region "$REGION" --query 'Functions[?contains(FunctionName, `StravaAIBoost`)].FunctionName' --output text 2>/dev/null)

if [ -n "$LAMBDA_FUNCTIONS" ]; then
    FUNCTION_COUNT=$(echo "$LAMBDA_FUNCTIONS" | wc -w)
    print_status "Lambda functions deployed ($FUNCTION_COUNT functions)"
    
    if [ "$DETAILED_MODE" = true ]; then
        for func in $LAMBDA_FUNCTIONS; do
            print_info "  - $func"
        done
    fi
    
    # Check webhook handler specifically
    if echo "$LAMBDA_FUNCTIONS" | grep -q "WebhookHandler"; then
        print_status "Webhook handler Lambda function found"
    else
        print_warning "Webhook handler Lambda function not found"
    fi
else
    print_error "No Lambda functions found"
fi

# Check DynamoDB tables
print_check "DynamoDB tables deployment"
EXPECTED_TABLES=(
    "strava-ai-boost-activities"
    "strava-ai-boost-user-configuration"
    "strava-ai-boost-rate-limits"
    "strava-ai-boost-campus-coaching-sessions"
)

TABLES_FOUND=0
for table in "${EXPECTED_TABLES[@]}"; do
    if aws dynamodb describe-table --table-name "$table" --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
        ((TABLES_FOUND++))
        if [ "$DETAILED_MODE" = true ]; then
            print_info "  ✅ Table $table exists"
        fi
    else
        if [ "$DETAILED_MODE" = true ]; then
            print_info "  ❌ Table $table missing"
        fi
    fi
done

if [ $TABLES_FOUND -eq ${#EXPECTED_TABLES[@]} ]; then
    print_status "All DynamoDB tables deployed ($TABLES_FOUND/${#EXPECTED_TABLES[@]})"
else
    print_warning "Some DynamoDB tables missing ($TABLES_FOUND/${#EXPECTED_TABLES[@]})"
fi

# Check 6: OAuth Flow Test (if requested)
if [ "$OAUTH_TEST" = true ]; then
    print_check "OAuth flow test (interactive)"
    
    if [ -n "$CLIENT_ID" ] && [ -n "$WEBHOOK_URL" ]; then
        print_info "Starting OAuth flow test..."
        print_info "This will open a browser window for Strava authorization"
        
        # Generate OAuth URL
        REDIRECT_URI="${WEBHOOK_URL%/webhook}/oauth/callback"
        STATE="test_$(date +%s)"
        OAUTH_URL="https://www.strava.com/oauth/authorize?client_id=$CLIENT_ID&response_type=code&redirect_uri=$REDIRECT_URI&approval_prompt=force&scope=read,activity:read_all&state=$STATE"
        
        print_info "OAuth URL: $OAUTH_URL"
        print_info "Redirect URI: $REDIRECT_URI"
        
        # Try to open browser (macOS/Linux)
        if command -v open > /dev/null 2>&1; then
            open "$OAUTH_URL"
        elif command -v xdg-open > /dev/null 2>&1; then
            xdg-open "$OAUTH_URL"
        else
            print_info "Please open this URL in your browser: $OAUTH_URL"
        fi
        
        print_warning "OAuth flow test requires manual verification"
        print_info "Check if the redirect URI is configured in your Strava application"
    else
        print_error "Cannot test OAuth flow - missing client ID or webhook URL"
    fi
fi

# Check 7: Rate Limiting Configuration
print_check "Rate limiting configuration"
RATE_LIMITS_TABLE="strava-ai-boost-rate-limits"

if aws dynamodb describe-table --table-name "$RATE_LIMITS_TABLE" --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
    print_status "Rate limiting table exists"
    
    # Check for existing rate limit data
    RATE_LIMIT_ITEMS=$(aws dynamodb scan --table-name "$RATE_LIMITS_TABLE" --profile "$PROFILE" --region "$REGION" --select COUNT --query 'Count' --output text 2>/dev/null || echo "0")
    
    if [ "$RATE_LIMIT_ITEMS" -gt 0 ]; then
        print_info "Rate limiting data present ($RATE_LIMIT_ITEMS items)"
    else
        print_info "Rate limiting table empty (will be populated during use)"
    fi
else
    print_error "Rate limiting table not found"
fi

# Check 8: Security Configuration
print_check "Security configuration"

# Check IAM roles
IAM_ROLES=$(aws iam list-roles --profile "$PROFILE" --query 'Roles[?contains(RoleName, `StravaAIBoost`)].RoleName' --output text 2>/dev/null)

if [ -n "$IAM_ROLES" ]; then
    ROLE_COUNT=$(echo "$IAM_ROLES" | wc -w)
    print_status "IAM roles configured ($ROLE_COUNT roles)"
    
    if [ "$DETAILED_MODE" = true ]; then
        for role in $IAM_ROLES; do
            print_info "  - $role"
        done
    fi
else
    print_warning "No IAM roles found with StravaAIBoost prefix"
fi

# Check encryption settings
print_check "Encryption configuration"

# Check DynamoDB encryption
ENCRYPTED_TABLES=0
for table in "${EXPECTED_TABLES[@]}"; do
    if aws dynamodb describe-table --table-name "$table" --profile "$PROFILE" --region "$REGION" --query 'Table.SSEDescription.Status' --output text 2>/dev/null | grep -q "ENABLED"; then
        ((ENCRYPTED_TABLES++))
    fi
done

if [ $ENCRYPTED_TABLES -gt 0 ]; then
    print_status "DynamoDB encryption enabled ($ENCRYPTED_TABLES tables)"
else
    print_warning "DynamoDB encryption status unclear"
fi

# Generate validation report
print_section "📊 Validation Summary"

echo ""
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo ""
echo "Validation Results:"
echo "  ✅ Passed: $PASSED_CHECKS"
echo "  ⚠️  Warnings: $WARNING_CHECKS"
echo "  ❌ Failed: $FAILED_CHECKS"
echo "  📊 Total: $TOTAL_CHECKS"

# Calculate success rate
if [ $TOTAL_CHECKS -gt 0 ]; then
    SUCCESS_RATE=$(( (PASSED_CHECKS * 100) / TOTAL_CHECKS ))
    echo "  📈 Success Rate: $SUCCESS_RATE%"
else
    SUCCESS_RATE=0
fi

# Overall status
echo ""
if [ $FAILED_CHECKS -eq 0 ]; then
    if [ $WARNING_CHECKS -eq 0 ]; then
        print_status "🎉 All validations passed! Strava application is fully configured."
        OVERALL_STATUS="PASS"
    else
        print_warning "⚠️  Validations passed with warnings. Review warnings above."
        OVERALL_STATUS="PASS_WITH_WARNINGS"
    fi
else
    print_error "❌ Some validations failed. Fix issues before proceeding."
    OVERALL_STATUS="FAIL"
fi

# Save validation report
REPORT_FILE="strava-validation-report-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S).json"
cat > "$REPORT_FILE" << EOF
{
  "validation_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "environment": "$ENVIRONMENT",
  "region": "$REGION",
  "account_id": "$ACCOUNT_ID",
  "overall_status": "$OVERALL_STATUS",
  "success_rate": $SUCCESS_RATE,
  "checks": {
    "total": $TOTAL_CHECKS,
    "passed": $PASSED_CHECKS,
    "warnings": $WARNING_CHECKS,
    "failed": $FAILED_CHECKS
  },
  "configuration": {
    "client_id_configured": $([ -n "$CLIENT_ID" ] && echo "true" || echo "false"),
    "client_secret_configured": $([ -n "$CLIENT_SECRET" ] && echo "true" || echo "false"),
    "webhook_verify_token_configured": $([ -n "$WEBHOOK_VERIFY_TOKEN" ] && echo "true" || echo "false"),
    "api_gateway_deployed": $([ -n "$API_ID" ] && echo "true" || echo "false"),
    "lambda_functions_deployed": $([ -n "$LAMBDA_FUNCTIONS" ] && echo "true" || echo "false"),
    "dynamodb_tables_deployed": $([ $TABLES_FOUND -eq ${#EXPECTED_TABLES[@]} ] && echo "true" || echo "false")
  },
  "recommendations": []
}
EOF

print_info "Validation report saved: $REPORT_FILE"

# Exit with appropriate code
if [ "$OVERALL_STATUS" = "FAIL" ]; then
    exit 1
elif [ "$OVERALL_STATUS" = "PASS_WITH_WARNINGS" ]; then
    exit 2
else
    exit 0
fi