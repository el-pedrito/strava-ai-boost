#!/bin/bash

# Strava Application Health Check
# Comprehensive health monitoring for Strava integration
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/strava_health_check.sh [dev|prod] [--continuous] [--alert-threshold=80]
#
# Options:
#   --continuous: Run continuous monitoring (every 5 minutes)
#   --alert-threshold: Health score threshold for alerts (default: 80)
#   --webhook-test: Test webhook with sample payload
#   --rate-limit-check: Check current rate limit status

set -e

# Configuration
ENVIRONMENT="${1:-dev}"
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
CONTINUOUS_MODE=false
ALERT_THRESHOLD=80
WEBHOOK_TEST=false
RATE_LIMIT_CHECK=false

# Parse command line options
while [[ $# -gt 0 ]]; do
    case $1 in
        --continuous)
            CONTINUOUS_MODE=true
            shift
            ;;
        --alert-threshold=*)
            ALERT_THRESHOLD="${1#*=}"
            shift
            ;;
        --webhook-test)
            WEBHOOK_TEST=true
            shift
            ;;
        --rate-limit-check)
            RATE_LIMIT_CHECK=true
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

# Health metrics
HEALTH_SCORE=0
TOTAL_METRICS=0
CRITICAL_ISSUES=0
WARNING_ISSUES=0

print_status() {
    echo -e "${GREEN}[HEALTHY]${NC} $1"
    ((HEALTH_SCORE += 10))
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    ((WARNING_ISSUES++))
    ((HEALTH_SCORE += 5))
}

print_error() {
    echo -e "${RED}[CRITICAL]${NC} $1"
    ((CRITICAL_ISSUES++))
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_section() {
    echo -e "${CYAN}[SECTION]${NC} $1"
}

increment_metric() {
    ((TOTAL_METRICS++))
}

run_health_check() {
    local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    
    print_section "🏥 Strava Application Health Check - $timestamp"
    print_info "Environment: $ENVIRONMENT | Region: $REGION"
    
    # Reset counters
    HEALTH_SCORE=0
    TOTAL_METRICS=0
    CRITICAL_ISSUES=0
    WARNING_ISSUES=0
    
    # Health Check 1: AWS Services Status
    print_section "☁️  AWS Services Health"
    
    # Check API Gateway
    increment_metric
    API_ID=$(aws apigateway get-rest-apis --profile "$PROFILE" --region "$REGION" --query "items[?contains(name, 'StravaAIBoost')].id" --output text 2>/dev/null | head -1)
    
    if [ -n "$API_ID" ]; then
        # Test API Gateway response time
        START_TIME=$(date +%s%N)
        WEBHOOK_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod/webhook"
        HTTP_STATUS=$(curl -s -w "%{http_code}" -o /dev/null "$WEBHOOK_URL?hub.mode=subscribe&hub.challenge=health_check&hub.verify_token=test" 2>/dev/null || echo "000")
        END_TIME=$(date +%s%N)
        RESPONSE_TIME=$(( (END_TIME - START_TIME) / 1000000 )) # Convert to milliseconds
        
        if [ "$HTTP_STATUS" = "200" ]; then
            if [ $RESPONSE_TIME -lt 1000 ]; then
                print_status "API Gateway healthy (${RESPONSE_TIME}ms response time)"
            elif [ $RESPONSE_TIME -lt 3000 ]; then
                print_warning "API Gateway slow (${RESPONSE_TIME}ms response time)"
            else
                print_error "API Gateway very slow (${RESPONSE_TIME}ms response time)"
            fi
        else
            print_error "API Gateway unhealthy (HTTP $HTTP_STATUS)"
        fi
    else
        print_error "API Gateway not found"
    fi
    
    # Check Lambda functions
    increment_metric
    LAMBDA_FUNCTIONS=$(aws lambda list-functions --profile "$PROFILE" --region "$REGION" --query 'Functions[?contains(FunctionName, `StravaAIBoost`)].FunctionName' --output text 2>/dev/null)
    
    if [ -n "$LAMBDA_FUNCTIONS" ]; then
        FUNCTION_COUNT=$(echo "$LAMBDA_FUNCTIONS" | wc -w)
        
        # Check for errors in recent invocations
        ERROR_COUNT=0
        for func in $LAMBDA_FUNCTIONS; do
            RECENT_ERRORS=$(aws logs filter-log-events \
                --log-group-name "/aws/lambda/$func" \
                --start-time $(( $(date +%s) * 1000 - 3600000 )) \
                --filter-pattern "ERROR" \
                --profile "$PROFILE" \
                --region "$REGION" \
                --query 'events | length(@)' \
                --output text 2>/dev/null || echo "0")
            
            ERROR_COUNT=$((ERROR_COUNT + RECENT_ERRORS))
        done
        
        if [ $ERROR_COUNT -eq 0 ]; then
            print_status "Lambda functions healthy ($FUNCTION_COUNT functions, no recent errors)"
        elif [ $ERROR_COUNT -lt 5 ]; then
            print_warning "Lambda functions have minor issues ($ERROR_COUNT errors in last hour)"
        else
            print_error "Lambda functions have significant issues ($ERROR_COUNT errors in last hour)"
        fi
    else
        print_error "No Lambda functions found"
    fi
    
    # Check DynamoDB tables
    increment_metric
    EXPECTED_TABLES=(
        "strava-ai-boost-activities"
        "strava-ai-boost-user-configuration"
        "strava-ai-boost-rate-limits"
        "strava-ai-boost-campus-coaching-sessions"
    )
    
    HEALTHY_TABLES=0
    for table in "${EXPECTED_TABLES[@]}"; do
        TABLE_STATUS=$(aws dynamodb describe-table --table-name "$table" --profile "$PROFILE" --region "$REGION" --query 'Table.TableStatus' --output text 2>/dev/null || echo "NOT_FOUND")
        
        if [ "$TABLE_STATUS" = "ACTIVE" ]; then
            ((HEALTHY_TABLES++))
        fi
    done
    
    if [ $HEALTHY_TABLES -eq ${#EXPECTED_TABLES[@]} ]; then
        print_status "DynamoDB tables healthy (${HEALTHY_TABLES}/${#EXPECTED_TABLES[@]} active)"
    elif [ $HEALTHY_TABLES -gt 0 ]; then
        print_warning "Some DynamoDB tables unhealthy (${HEALTHY_TABLES}/${#EXPECTED_TABLES[@]} active)"
    else
        print_error "All DynamoDB tables unhealthy or missing"
    fi
    
    # Health Check 2: Strava API Integration
    print_section "🚴 Strava API Integration Health"
    
    # Get Strava credentials
    SECRET_NAME="strava-ai-boost-oauth-tokens"
    CLIENT_SECRET=""
    
    if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
        SECRET_VALUE=$(aws secretsmanager get-secret-value --secret-id "$SECRET_NAME" --profile "$PROFILE" --region "$REGION" --query SecretString --output text 2>/dev/null)
        CLIENT_SECRET=$(echo "$SECRET_VALUE" | jq -r '.client_secret // empty' 2>/dev/null)
    fi
    
    # Test Strava API connectivity
    increment_metric
    if [ -n "$CLIENT_SECRET" ]; then
        START_TIME=$(date +%s%N)
        STRAVA_STATUS=$(curl -s -w "%{http_code}" -o /tmp/strava_health_test \
            "https://www.strava.com/api/v3/push_subscriptions" \
            -H "Authorization: Bearer $CLIENT_SECRET" 2>/dev/null || echo "000")
        END_TIME=$(date +%s%N)
        STRAVA_RESPONSE_TIME=$(( (END_TIME - START_TIME) / 1000000 ))
        
        if [ "$STRAVA_STATUS" = "200" ]; then
            if [ $STRAVA_RESPONSE_TIME -lt 2000 ]; then
                print_status "Strava API healthy (${STRAVA_RESPONSE_TIME}ms response time)"
            else
                print_warning "Strava API slow (${STRAVA_RESPONSE_TIME}ms response time)"
            fi
            
            # Check webhook subscriptions
            SUBSCRIPTIONS=$(cat /tmp/strava_health_test 2>/dev/null)
            SUBSCRIPTION_COUNT=$(echo "$SUBSCRIPTIONS" | jq '. | length' 2>/dev/null || echo "0")
            
            if [ "$SUBSCRIPTION_COUNT" -gt 0 ]; then
                print_status "Webhook subscriptions active ($SUBSCRIPTION_COUNT subscriptions)"
            else
                print_warning "No webhook subscriptions found"
            fi
        elif [ "$STRAVA_STATUS" = "401" ]; then
            print_error "Strava API authentication failed"
        elif [ "$STRAVA_STATUS" = "000" ]; then
            print_error "Cannot reach Strava API"
        else
            print_warning "Strava API returned unexpected status: $STRAVA_STATUS"
        fi
        
        rm -f /tmp/strava_health_test
    else
        print_error "Strava credentials not configured"
    fi
    
    # Health Check 3: Rate Limiting Status
    if [ "$RATE_LIMIT_CHECK" = true ]; then
        print_section "⏱️  Rate Limiting Health"
        
        increment_metric
        RATE_LIMITS_TABLE="strava-ai-boost-rate-limits"
        
        if aws dynamodb describe-table --table-name "$RATE_LIMITS_TABLE" --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
            # Get current rate limit status
            SHORT_TERM_USAGE=$(aws dynamodb get-item \
                --table-name "$RATE_LIMITS_TABLE" \
                --key '{"limit_type":{"S":"short_term"}}' \
                --profile "$PROFILE" \
                --region "$REGION" \
                --query 'Item.current_usage.N' \
                --output text 2>/dev/null || echo "0")
            
            DAILY_USAGE=$(aws dynamodb get-item \
                --table-name "$RATE_LIMITS_TABLE" \
                --key '{"limit_type":{"S":"daily"}}' \
                --profile "$PROFILE" \
                --region "$REGION" \
                --query 'Item.current_usage.N' \
                --output text 2>/dev/null || echo "0")
            
            # Calculate usage percentages
            SHORT_TERM_PERCENT=$(( SHORT_TERM_USAGE * 100 / 100 )) # 100 requests per 15 minutes
            DAILY_PERCENT=$(( DAILY_USAGE * 100 / 1000 )) # 1000 requests per day
            
            if [ $SHORT_TERM_PERCENT -lt 70 ] && [ $DAILY_PERCENT -lt 70 ]; then
                print_status "Rate limits healthy (${SHORT_TERM_PERCENT}% short-term, ${DAILY_PERCENT}% daily)"
            elif [ $SHORT_TERM_PERCENT -lt 90 ] && [ $DAILY_PERCENT -lt 90 ]; then
                print_warning "Rate limits elevated (${SHORT_TERM_PERCENT}% short-term, ${DAILY_PERCENT}% daily)"
            else
                print_error "Rate limits critical (${SHORT_TERM_PERCENT}% short-term, ${DAILY_PERCENT}% daily)"
            fi
        else
            print_error "Rate limits table not found"
        fi
    fi
    
    # Health Check 4: Webhook Testing
    if [ "$WEBHOOK_TEST" = true ] && [ -n "$WEBHOOK_URL" ]; then
        print_section "🔗 Webhook Health Test"
        
        increment_metric
        # Test webhook with sample payload
        TEST_PAYLOAD='{"object_type":"activity","object_id":12345,"aspect_type":"create","owner_id":67890,"event_time":1234567890}'
        
        START_TIME=$(date +%s%N)
        WEBHOOK_RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/webhook_health_test \
            "$WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "$TEST_PAYLOAD" 2>/dev/null || echo "000")
        END_TIME=$(date +%s%N)
        WEBHOOK_RESPONSE_TIME=$(( (END_TIME - START_TIME) / 1000000 ))
        
        if [ "$WEBHOOK_RESPONSE" = "200" ]; then
            RESPONSE_BODY=$(cat /tmp/webhook_health_test 2>/dev/null)
            if echo "$RESPONSE_BODY" | jq -e '.status' > /dev/null 2>&1; then
                STATUS=$(echo "$RESPONSE_BODY" | jq -r '.status')
                print_status "Webhook processing healthy (${WEBHOOK_RESPONSE_TIME}ms, status: $STATUS)"
            else
                print_warning "Webhook responded but format unexpected"
            fi
        else
            print_error "Webhook test failed (HTTP $WEBHOOK_RESPONSE)"
        fi
        
        rm -f /tmp/webhook_health_test
    fi
    
    # Health Check 5: System Performance Metrics
    print_section "📊 Performance Metrics"
    
    increment_metric
    # Check recent activity processing
    ACTIVITIES_TABLE="strava-ai-boost-activities"
    
    if aws dynamodb describe-table --table-name "$ACTIVITIES_TABLE" --profile "$PROFILE" --region "$REGION" > /dev/null 2>&1; then
        # Count activities processed in last 24 hours
        YESTERDAY_TIMESTAMP=$(( $(date +%s) - 86400 ))
        
        RECENT_ACTIVITIES=$(aws dynamodb scan \
            --table-name "$ACTIVITIES_TABLE" \
            --filter-expression "#ts > :yesterday" \
            --expression-attribute-names '{"#ts":"created_at"}' \
            --expression-attribute-values "{\":yesterday\":{\"N\":\"$YESTERDAY_TIMESTAMP\"}}" \
            --select COUNT \
            --profile "$PROFILE" \
            --region "$REGION" \
            --query 'Count' \
            --output text 2>/dev/null || echo "0")
        
        if [ "$RECENT_ACTIVITIES" -gt 0 ]; then
            print_status "Activity processing active ($RECENT_ACTIVITIES activities in last 24h)"
        else
            print_warning "No recent activity processing (0 activities in last 24h)"
        fi
    else
        print_error "Activities table not accessible"
    fi
    
    # Calculate overall health score
    if [ $TOTAL_METRICS -gt 0 ]; then
        FINAL_HEALTH_SCORE=$(( HEALTH_SCORE * 100 / (TOTAL_METRICS * 10) ))
    else
        FINAL_HEALTH_SCORE=0
    fi
    
    # Health summary
    print_section "🎯 Health Summary"
    
    echo ""
    echo "Timestamp: $timestamp"
    echo "Environment: $ENVIRONMENT"
    echo "Health Score: $FINAL_HEALTH_SCORE/100"
    echo "Critical Issues: $CRITICAL_ISSUES"
    echo "Warnings: $WARNING_ISSUES"
    echo "Metrics Checked: $TOTAL_METRICS"
    
    # Determine overall status
    if [ $CRITICAL_ISSUES -eq 0 ] && [ $FINAL_HEALTH_SCORE -ge $ALERT_THRESHOLD ]; then
        echo -e "${GREEN}Overall Status: HEALTHY${NC}"
        OVERALL_STATUS="HEALTHY"
    elif [ $CRITICAL_ISSUES -eq 0 ] && [ $FINAL_HEALTH_SCORE -ge 60 ]; then
        echo -e "${YELLOW}Overall Status: DEGRADED${NC}"
        OVERALL_STATUS="DEGRADED"
    else
        echo -e "${RED}Overall Status: UNHEALTHY${NC}"
        OVERALL_STATUS="UNHEALTHY"
    fi
    
    # Save health report
    HEALTH_REPORT_FILE="health-report-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S).json"
    cat > "$HEALTH_REPORT_FILE" << EOF
{
  "timestamp": "$timestamp",
  "environment": "$ENVIRONMENT",
  "region": "$REGION",
  "overall_status": "$OVERALL_STATUS",
  "health_score": $FINAL_HEALTH_SCORE,
  "alert_threshold": $ALERT_THRESHOLD,
  "metrics": {
    "total_checked": $TOTAL_METRICS,
    "critical_issues": $CRITICAL_ISSUES,
    "warnings": $WARNING_ISSUES
  },
  "services": {
    "api_gateway_healthy": $([ -n "$API_ID" ] && [ "$HTTP_STATUS" = "200" ] && echo "true" || echo "false"),
    "lambda_functions_healthy": $([ -n "$LAMBDA_FUNCTIONS" ] && [ $ERROR_COUNT -lt 5 ] && echo "true" || echo "false"),
    "dynamodb_healthy": $([ $HEALTHY_TABLES -eq ${#EXPECTED_TABLES[@]} ] && echo "true" || echo "false"),
    "strava_api_healthy": $([ "$STRAVA_STATUS" = "200" ] && echo "true" || echo "false")
  }
}
EOF
    
    if [ "$FINAL_HEALTH_SCORE" -lt $ALERT_THRESHOLD ]; then
        echo ""
        print_error "🚨 HEALTH ALERT: Score below threshold ($FINAL_HEALTH_SCORE < $ALERT_THRESHOLD)"
        echo "Health report saved: $HEALTH_REPORT_FILE"
        
        # Return error code for alerting systems
        return 1
    else
        echo "Health report saved: $HEALTH_REPORT_FILE"
        return 0
    fi
}

# Main execution
if [ "$CONTINUOUS_MODE" = true ]; then
    print_info "Starting continuous health monitoring (every 5 minutes)"
    print_info "Alert threshold: $ALERT_THRESHOLD"
    print_info "Press Ctrl+C to stop"
    
    while true; do
        run_health_check
        echo ""
        print_info "Waiting 5 minutes for next check..."
        sleep 300
    done
else
    run_health_check
fi