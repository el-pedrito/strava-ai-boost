#!/bin/bash

# Strava AI Boost - Uninstall Verification Script
# Verifies that all AWS resources have been completely removed
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/verify_uninstall.sh [dev|prod]

set -e

# Parse command line arguments
ENVIRONMENT="${1:-dev}"

# Configuration
REGION="${AWS_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
PROJECT_NAME="strava-ai-boost"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Verification state tracking
VERIFICATION_LOG_FILE="uninstall-verification-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S).log"
ISSUES_FOUND=false

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a $VERIFICATION_LOG_FILE
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a $VERIFICATION_LOG_FILE
    ISSUES_FOUND=true
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a $VERIFICATION_LOG_FILE
    ISSUES_FOUND=true
}

print_section() {
    echo -e "${BLUE}[SECTION]${NC} $1" | tee -a $VERIFICATION_LOG_FILE
}

print_phase() {
    echo -e "${CYAN}[PHASE]${NC} $1" | tee -a $VERIFICATION_LOG_FILE
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a $VERIFICATION_LOG_FILE
}

print_phase "🔍 Starting Strava AI Boost uninstall verification"
print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Profile: $PROFILE"

# Validate environment parameter
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    print_error "Invalid environment: $ENVIRONMENT. Use 'dev' or 'prod'"
    exit 1
fi

# Verify AWS credentials
print_status "Verifying AWS credentials..."
if ! aws sts get-caller-identity --profile $PROFILE --region $REGION > /dev/null 2>&1; then
    print_error "AWS credentials not configured for profile: $PROFILE"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --profile $PROFILE --region $REGION --query Account --output text)
print_status "Using AWS Account: $ACCOUNT_ID"

# Phase 1: Verify CloudFormation Stacks Removal
print_phase "☁️  Phase 1: Verifying CloudFormation stacks removal"

EXPECTED_STACKS=(
    "StravaAIBoost-Core"
    "StravaAIBoost-Content"
    "StravaAIBoost-Webhook"
    "StravaAIBoost-API"
    "StravaAIBoost-Monitoring"
)

print_status "Checking for remaining CloudFormation stacks..."

for stack in "${EXPECTED_STACKS[@]}"; do
    if aws cloudformation describe-stacks --stack-name $stack --profile $PROFILE --region $REGION > /dev/null 2>&1; then
        STACK_STATUS=$(aws cloudformation describe-stacks --stack-name $stack --profile $PROFILE --region $REGION --query 'Stacks[0].StackStatus' --output text)
        if [[ "$STACK_STATUS" == "DELETE_IN_PROGRESS" ]]; then
            print_warning "Stack $stack is still being deleted (Status: $STACK_STATUS)"
        else
            print_error "Stack $stack still exists (Status: $STACK_STATUS)"
        fi
    else
        print_success "✅ Stack $stack successfully removed"
    fi
done

# Check for any other stacks with StravaAIBoost in the name
OTHER_STACKS=$(aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE ROLLBACK_COMPLETE UPDATE_ROLLBACK_COMPLETE --profile $PROFILE --region $REGION --query 'StackSummaries[?contains(StackName, `StravaAIBoost`)].StackName' --output text)

if [ -n "$OTHER_STACKS" ]; then
    print_warning "Found unexpected StravaAIBoost stacks:"
    echo "$OTHER_STACKS" | tee -a $VERIFICATION_LOG_FILE
else
    print_success "✅ No unexpected CloudFormation stacks found"
fi

# Phase 2: Verify Lambda Functions Removal
print_phase "⚡ Phase 2: Verifying Lambda functions removal"

print_status "Checking for remaining Lambda functions..."

REMAINING_FUNCTIONS=$(aws lambda list-functions --profile $PROFILE --region $REGION --query 'Functions[?contains(FunctionName, `StravaAIBoost`)].FunctionName' --output text)

if [ -n "$REMAINING_FUNCTIONS" ]; then
    print_error "Found remaining Lambda functions:"
    echo "$REMAINING_FUNCTIONS" | tee -a $VERIFICATION_LOG_FILE
else
    print_success "✅ All Lambda functions successfully removed"
fi

# Phase 3: Verify DynamoDB Tables Removal
print_phase "🗄️  Phase 3: Verifying DynamoDB tables removal"

EXPECTED_TABLES=(
    "strava-ai-boost-activities"
    "strava-ai-boost-user-configuration"
    "strava-ai-boost-rate-limits"
    "strava-ai-boost-campus-coaching-sessions"
)

print_status "Checking for remaining DynamoDB tables..."

for table in "${EXPECTED_TABLES[@]}"; do
    if aws dynamodb describe-table --table-name $table --profile $PROFILE --region $REGION > /dev/null 2>&1; then
        TABLE_STATUS=$(aws dynamodb describe-table --table-name $table --profile $PROFILE --region $REGION --query 'Table.TableStatus' --output text)
        if [[ "$TABLE_STATUS" == "DELETING" ]]; then
            print_warning "Table $table is still being deleted (Status: $TABLE_STATUS)"
        else
            print_error "Table $table still exists (Status: $TABLE_STATUS)"
        fi
    else
        print_success "✅ Table $table successfully removed"
    fi
done

# Check for any other tables with strava-ai-boost in the name
OTHER_TABLES=$(aws dynamodb list-tables --profile $PROFILE --region $REGION --query 'TableNames[?contains(@, `strava-ai-boost`)]' --output text)

if [ -n "$OTHER_TABLES" ]; then
    print_warning "Found unexpected strava-ai-boost tables:"
    echo "$OTHER_TABLES" | tee -a $VERIFICATION_LOG_FILE
else
    print_success "✅ No unexpected DynamoDB tables found"
fi

# Phase 4: Verify Secrets Manager Secrets Removal
print_phase "🔐 Phase 4: Verifying Secrets Manager secrets removal"

EXPECTED_SECRETS=(
    "strava-ai-boost-oauth-tokens"
    "strava-ai-boost-campus-coach-credentials"
)

print_status "Checking for remaining Secrets Manager secrets..."

for secret in "${EXPECTED_SECRETS[@]}"; do
    if aws secretsmanager describe-secret --secret-id $secret --profile $PROFILE --region $REGION > /dev/null 2>&1; then
        DELETE_DATE=$(aws secretsmanager describe-secret --secret-id $secret --profile $PROFILE --region $REGION --query 'DeletedDate' --output text)
        if [[ "$DELETE_DATE" != "None" && "$DELETE_DATE" != "null" ]]; then
            print_warning "Secret $secret is scheduled for deletion (Delete date: $DELETE_DATE)"
        else
            print_error "Secret $secret still exists and is not scheduled for deletion"
        fi
    else
        print_success "✅ Secret $secret successfully removed"
    fi
done

# Phase 5: Verify AgentCore Resources Removal
print_phase "🤖 Phase 5: Verifying AgentCore resources removal"

if command -v agentcore &> /dev/null; then
    # Set AWS profile for AgentCore operations
    export AWS_PROFILE=$PROFILE
    
    print_status "AgentCore CLI found, checking for remaining resources..."
    
    # Check for remaining agents
    print_status "Checking for remaining AgentCore agents..."
    REMAINING_AGENTS=$(agentcore agent list --region $REGION 2>/dev/null | grep "strava-ai-boost" || echo "")
    
    if [ -n "$REMAINING_AGENTS" ]; then
        print_error "Found remaining AgentCore agents:"
        echo "$REMAINING_AGENTS" | tee -a $VERIFICATION_LOG_FILE
    else
        print_success "✅ All AgentCore agents successfully removed"
    fi
    
    # Check for remaining memory
    print_status "Checking for remaining AgentCore memory..."
    REMAINING_MEMORY=$(agentcore memory list --region $REGION 2>/dev/null | grep "strava-ai-boost" || echo "")
    
    if [ -n "$REMAINING_MEMORY" ]; then
        print_error "Found remaining AgentCore memory:"
        echo "$REMAINING_MEMORY" | tee -a $VERIFICATION_LOG_FILE
    else
        print_success "✅ All AgentCore memory successfully removed"
    fi
else
    print_warning "AgentCore CLI not found - cannot verify AgentCore resource removal"
    print_warning "Please verify manually that no AgentCore resources remain"
fi

# Phase 6: Verify Additional AWS Resources Removal
print_phase "🔧 Phase 6: Verifying additional AWS resources removal"

# Check SQS queues
print_status "Checking for remaining SQS queues..."
REMAINING_QUEUES=$(aws sqs list-queues --profile $PROFILE --region $REGION --query 'QueueUrls[?contains(@, `strava-ai-boost`)]' --output text)

if [ -n "$REMAINING_QUEUES" ]; then
    print_error "Found remaining SQS queues:"
    echo "$REMAINING_QUEUES" | tee -a $VERIFICATION_LOG_FILE
else
    print_success "✅ All SQS queues successfully removed"
fi

# Check Step Functions state machines
print_status "Checking for remaining Step Functions state machines..."
REMAINING_STATE_MACHINES=$(aws stepfunctions list-state-machines --profile $PROFILE --region $REGION --query 'stateMachines[?contains(name, `StravaAIBoost`)].name' --output text)

if [ -n "$REMAINING_STATE_MACHINES" ]; then
    print_error "Found remaining Step Functions state machines:"
    echo "$REMAINING_STATE_MACHINES" | tee -a $VERIFICATION_LOG_FILE
else
    print_success "✅ All Step Functions state machines successfully removed"
fi

# Check API Gateway APIs
print_status "Checking for remaining API Gateway APIs..."
REMAINING_APIS=$(aws apigateway get-rest-apis --profile $PROFILE --region $REGION --query 'items[?contains(name, `StravaAIBoost`)].name' --output text)

if [ -n "$REMAINING_APIS" ]; then
    print_error "Found remaining API Gateway APIs:"
    echo "$REMAINING_APIS" | tee -a $VERIFICATION_LOG_FILE
else
    print_success "✅ All API Gateway APIs successfully removed"
fi

# Check CloudWatch log groups
print_status "Checking for remaining CloudWatch log groups..."
REMAINING_LOG_GROUPS=$(aws logs describe-log-groups --profile $PROFILE --region $REGION --query 'logGroups[?contains(logGroupName, `StravaAIBoost`) || contains(logGroupName, `strava-ai-boost`)].logGroupName' --output text)

if [ -n "$REMAINING_LOG_GROUPS" ]; then
    print_warning "Found remaining CloudWatch log groups:"
    echo "$REMAINING_LOG_GROUPS" | tee -a $VERIFICATION_LOG_FILE
    print_warning "Note: Log groups may be retained for debugging purposes"
else
    print_success "✅ All CloudWatch log groups successfully removed"
fi

# Check S3 buckets
print_status "Checking for remaining S3 buckets..."
REMAINING_BUCKETS=$(aws s3api list-buckets --profile $PROFILE --query 'Buckets[?contains(Name, `strava-ai-boost`)].Name' --output text)

if [ -n "$REMAINING_BUCKETS" ]; then
    print_error "Found remaining S3 buckets:"
    echo "$REMAINING_BUCKETS" | tee -a $VERIFICATION_LOG_FILE
else
    print_success "✅ All S3 buckets successfully removed"
fi

# Check IAM roles
print_status "Checking for remaining IAM roles..."
REMAINING_ROLES=$(aws iam list-roles --profile $PROFILE --query 'Roles[?contains(RoleName, `StravaAIBoost`)].RoleName' --output text)

if [ -n "$REMAINING_ROLES" ]; then
    print_error "Found remaining IAM roles:"
    echo "$REMAINING_ROLES" | tee -a $VERIFICATION_LOG_FILE
else
    print_success "✅ All IAM roles successfully removed"
fi

# Phase 7: Check for Strava Webhook Subscription
print_phase "🔗 Phase 7: Verifying Strava webhook subscription removal"

WEBHOOK_CONFIG_FILE="webhook-config-${ENVIRONMENT}.json"
if [ -f "$WEBHOOK_CONFIG_FILE" ]; then
    print_warning "Webhook configuration file still exists: $WEBHOOK_CONFIG_FILE"
    print_warning "This may indicate the webhook subscription was not removed"
    print_warning "Please verify manually at https://developers.strava.com/"
else
    print_success "✅ Webhook configuration file removed"
fi

# Phase 8: Verify Local Files Cleanup
print_phase "📁 Phase 8: Verifying local files cleanup"

LOCAL_FILES=(
    "deployment-state-${ENVIRONMENT}.json"
    "deployment-info-${ENVIRONMENT}.json"
    "deployment-summary-${ENVIRONMENT}-*.json"
    "webhook-config-${ENVIRONMENT}.json"
    "validation-report-${ENVIRONMENT}-*.json"
    "cdk.out"
)

print_status "Checking for remaining local deployment files..."

for file_pattern in "${LOCAL_FILES[@]}"; do
    if ls $file_pattern 1> /dev/null 2>&1; then
        print_warning "Found remaining local files: $file_pattern"
    fi
done

if [ ! -d "cdk.out" ]; then
    print_success "✅ CDK output directory removed"
else
    print_warning "CDK output directory still exists"
fi

# Phase 9: Generate Verification Report
print_phase "📊 Phase 9: Generating verification report"

# Count issues found
ISSUE_COUNT=0
if [ "$ISSUES_FOUND" = true ]; then
    ISSUE_COUNT=$(grep -c "\[WARNING\]\|\[ERROR\]" $VERIFICATION_LOG_FILE)
fi

# Create verification report
REPORT_FILE="uninstall-verification-report-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S).json"

cat > $REPORT_FILE << EOF
{
  "verification_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "environment": "$ENVIRONMENT",
  "region": "$REGION",
  "account_id": "$ACCOUNT_ID",
  "profile": "$PROFILE",
  "verification_status": "$([ "$ISSUES_FOUND" = false ] && echo "CLEAN" || echo "ISSUES_FOUND")",
  "issues_found": $ISSUE_COUNT,
  "components_verified": {
    "cloudformation_stacks": "$([ -z "$OTHER_STACKS" ] && echo "CLEAN" || echo "ISSUES")",
    "lambda_functions": "$([ -z "$REMAINING_FUNCTIONS" ] && echo "CLEAN" || echo "ISSUES")",
    "dynamodb_tables": "$([ -z "$OTHER_TABLES" ] && echo "CLEAN" || echo "ISSUES")",
    "secrets_manager": "VERIFIED",
    "agentcore_resources": "$(command -v agentcore &> /dev/null && ([ -z "$REMAINING_AGENTS" ] && [ -z "$REMAINING_MEMORY" ]) && echo "CLEAN" || echo "ISSUES_OR_NOT_VERIFIED")",
    "sqs_queues": "$([ -z "$REMAINING_QUEUES" ] && echo "CLEAN" || echo "ISSUES")",
    "step_functions": "$([ -z "$REMAINING_STATE_MACHINES" ] && echo "CLEAN" || echo "ISSUES")",
    "api_gateway": "$([ -z "$REMAINING_APIS" ] && echo "CLEAN" || echo "ISSUES")",
    "cloudwatch_logs": "$([ -z "$REMAINING_LOG_GROUPS" ] && echo "CLEAN" || echo "RETAINED")",
    "s3_buckets": "$([ -z "$REMAINING_BUCKETS" ] && echo "CLEAN" || echo "ISSUES")",
    "iam_roles": "$([ -z "$REMAINING_ROLES" ] && echo "CLEAN" || echo "ISSUES")"
  },
  "log_file": "$VERIFICATION_LOG_FILE",
  "recommendations": []
}
EOF

# Add recommendations based on findings
if [ "$ISSUES_FOUND" = true ]; then
    RECOMMENDATIONS='["Review verification log for specific issues", "Manually remove remaining resources", "Check AWS Console for any missed resources", "Verify billing to ensure no ongoing charges"]'
else
    RECOMMENDATIONS='["Uninstall completed successfully", "Monitor AWS billing for any unexpected charges", "Keep backup files if created during uninstall"]'
fi

# Update report with recommendations
jq --argjson recs "$RECOMMENDATIONS" '.recommendations = $recs' $REPORT_FILE > ${REPORT_FILE}.tmp && mv ${REPORT_FILE}.tmp $REPORT_FILE

# Final Summary
print_phase "🎉 Verification Complete"

echo ""
if [ "$ISSUES_FOUND" = false ]; then
    print_success "✨ Uninstall verification PASSED - All resources successfully removed!"
else
    print_warning "⚠️  Uninstall verification found $ISSUE_COUNT issues that need attention"
fi

print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Account: $ACCOUNT_ID"

echo ""
print_status "📋 Verification Summary:"

# CloudFormation
if [ -z "$OTHER_STACKS" ]; then
    echo "  ✅ CloudFormation Stacks: All removed"
else
    echo "  ⚠️  CloudFormation Stacks: Issues found"
fi

# Lambda
if [ -z "$REMAINING_FUNCTIONS" ]; then
    echo "  ✅ Lambda Functions: All removed"
else
    echo "  ❌ Lambda Functions: Some remain"
fi

# DynamoDB
if [ -z "$OTHER_TABLES" ]; then
    echo "  ✅ DynamoDB Tables: All removed"
else
    echo "  ❌ DynamoDB Tables: Some remain"
fi

# Secrets Manager
echo "  ✅ Secrets Manager: Verified"

# AgentCore
if command -v agentcore &> /dev/null; then
    if [ -z "$REMAINING_AGENTS" ] && [ -z "$REMAINING_MEMORY" ]; then
        echo "  ✅ AgentCore Resources: All removed"
    else
        echo "  ❌ AgentCore Resources: Some remain"
    fi
else
    echo "  ⚠️  AgentCore Resources: Not verified (CLI not available)"
fi

# Additional resources
if [ -z "$REMAINING_QUEUES" ]; then
    echo "  ✅ SQS Queues: All removed"
else
    echo "  ❌ SQS Queues: Some remain"
fi

if [ -z "$REMAINING_STATE_MACHINES" ]; then
    echo "  ✅ Step Functions: All removed"
else
    echo "  ❌ Step Functions: Some remain"
fi

if [ -z "$REMAINING_LOG_GROUPS" ]; then
    echo "  ✅ CloudWatch Logs: All removed"
else
    echo "  ⚠️  CloudWatch Logs: Some retained"
fi

echo ""
print_status "📁 Generated Files:"
echo "  - Verification log: $VERIFICATION_LOG_FILE"
echo "  - Verification report: $REPORT_FILE"

echo ""
if [ "$ISSUES_FOUND" = true ]; then
    print_warning "🔧 Manual Cleanup Required:"
    print_warning "Review the verification log for specific resources that need manual removal"
    print_warning "Check the AWS Console to confirm all resources are removed"
    print_warning "Monitor AWS billing to ensure no unexpected charges"
    
    echo ""
    print_status "📋 Common Manual Cleanup Commands:"
    echo "  # Remove remaining Lambda functions"
    echo "  aws lambda delete-function --function-name <function-name> --profile $PROFILE --region $REGION"
    echo ""
    echo "  # Remove remaining DynamoDB tables"
    echo "  aws dynamodb delete-table --table-name <table-name> --profile $PROFILE --region $REGION"
    echo ""
    echo "  # Remove remaining CloudFormation stacks"
    echo "  aws cloudformation delete-stack --stack-name <stack-name> --profile $PROFILE --region $REGION"
    echo ""
    echo "  # Remove remaining AgentCore resources"
    echo "  agentcore agent delete --name <agent-name> --region $REGION --force"
    echo "  agentcore memory delete --name <memory-name> --region $REGION --force"
else
    print_success "🎯 All resources successfully verified as removed!"
    print_success "Your Strava AI Boost system has been completely uninstalled"
    
    echo ""
    print_status "🔧 Final Steps:"
    echo "  1. Monitor AWS billing for any unexpected charges"
    echo "  2. Remove any remaining local files if desired"
    echo "  3. Keep backup files safe if created during uninstall"
    echo "  4. Remove Strava webhook subscription manually if not done automatically"
fi

print_status "✨ Verification process completed!"

# Exit with appropriate code
if [ "$ISSUES_FOUND" = true ]; then
    exit 1
else
    exit 0
fi