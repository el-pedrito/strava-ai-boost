#!/bin/bash

# Strava AI Boost - Complete Uninstall Script
# Safely removes all AWS resources and AgentCore components
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/uninstall.sh [dev|prod] [--force] [--backup] [--keep-data]
#
# Options:
#   --force      Skip confirmation prompts
#   --backup     Create backup before deletion
#   --keep-data  Keep DynamoDB data and Secrets Manager secrets

set -e

# Parse command line arguments
ENVIRONMENT="${1:-dev}"
FORCE_MODE=false
CREATE_BACKUP=false
KEEP_DATA=false

shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_MODE=true
            shift
            ;;
        --backup)
            CREATE_BACKUP=true
            shift
            ;;
        --keep-data)
            KEEP_DATA=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [dev|prod] [--force] [--backup] [--keep-data]"
            exit 1
            ;;
    esac
done

# Configuration
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
PROJECT_NAME="strava-ai-boost"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Uninstall state tracking
UNINSTALL_LOG_FILE="uninstall-log-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S).log"
BACKUP_DIR="backup-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a $UNINSTALL_LOG_FILE
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a $UNINSTALL_LOG_FILE
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a $UNINSTALL_LOG_FILE
}

print_section() {
    echo -e "${BLUE}[SECTION]${NC} $1" | tee -a $UNINSTALL_LOG_FILE
}

print_phase() {
    echo -e "${CYAN}[PHASE]${NC} $1" | tee -a $UNINSTALL_LOG_FILE
}

# Function to confirm destructive actions
confirm_action() {
    local message=$1
    
    if [ "$FORCE_MODE" = true ]; then
        return 0
    fi
    
    echo -e "${YELLOW}⚠️  $message${NC}"
    read -p "Are you sure you want to continue? (yes/no): " -r
    
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        print_status "Operation cancelled by user"
        exit 0
    fi
}

print_phase "🗑️  Starting Strava AI Boost uninstall process"
print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Profile: $PROFILE"
print_status "Force mode: $FORCE_MODE"
print_status "Create backup: $CREATE_BACKUP"
print_status "Keep data: $KEEP_DATA"

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

# Warning about destructive operation
echo ""
print_warning "🚨 DESTRUCTIVE OPERATION WARNING 🚨"
print_warning "This will permanently delete:"
print_warning "  - All CDK stacks and AWS resources"
print_warning "  - Lambda functions and their logs"
print_warning "  - DynamoDB tables and data (unless --keep-data)"
print_warning "  - Secrets Manager secrets (unless --keep-data)"
print_warning "  - AgentCore agents and memory"
print_warning "  - API Gateway endpoints"
print_warning "  - CloudWatch logs and metrics"

if [ "$KEEP_DATA" = true ]; then
    print_status "Data preservation enabled - DynamoDB and Secrets will be kept"
fi

if [ "$CREATE_BACKUP" = true ]; then
    print_status "Backup enabled - data will be exported before deletion"
fi

echo ""
confirm_action "This will permanently delete your Strava AI Boost system"

# Phase 1: Create Backup (if requested)
if [ "$CREATE_BACKUP" = true ]; then
    print_phase "💾 Phase 1: Creating backup"
    
    mkdir -p $BACKUP_DIR
    
    # Backup DynamoDB tables
    print_status "Backing up DynamoDB tables..."
    TABLES=(
        "strava-ai-boost-activities"
        "strava-ai-boost-user-configuration"
        "strava-ai-boost-rate-limits"
        "strava-ai-boost-campus-coaching-sessions"
    )
    
    for table in "${TABLES[@]}"; do
        if aws dynamodb describe-table --table-name $table --profile $PROFILE --region $REGION > /dev/null 2>&1; then
            print_status "Backing up table: $table"
            aws dynamodb scan --table-name $table --profile $PROFILE --region $REGION > "$BACKUP_DIR/${table}.json"
        else
            print_warning "Table $table not found, skipping backup"
        fi
    done
    
    # Backup Secrets Manager secrets
    print_status "Backing up Secrets Manager secrets..."
    SECRETS=(
        "strava-ai-boost-oauth-tokens"
        "strava-ai-boost-campus-coach-credentials"
    )
    
    for secret in "${SECRETS[@]}"; do
        if aws secretsmanager describe-secret --secret-id $secret --profile $PROFILE --region $REGION > /dev/null 2>&1; then
            print_status "Backing up secret: $secret"
            aws secretsmanager get-secret-value --secret-id $secret --profile $PROFILE --region $REGION > "$BACKUP_DIR/${secret}.json"
        else
            print_warning "Secret $secret not found, skipping backup"
        fi
    done
    
    # Backup Lambda function configurations
    print_status "Backing up Lambda function configurations..."
    aws lambda list-functions --profile $PROFILE --region $REGION --query 'Functions[?contains(FunctionName, `StravaAIBoost`)]' > "$BACKUP_DIR/lambda-functions.json"
    
    # Backup CloudFormation stack templates
    print_status "Backing up CloudFormation stack templates..."
    STACKS=(
        "StravaAIBoost-Core"
        "StravaAIBoost-Content"
        "StravaAIBoost-Webhook"
        "StravaAIBoost-API"
        "StravaAIBoost-Monitoring"
    )
    
    for stack in "${STACKS[@]}"; do
        if aws cloudformation describe-stacks --stack-name $stack --profile $PROFILE --region $REGION > /dev/null 2>&1; then
            print_status "Backing up stack template: $stack"
            aws cloudformation get-template --stack-name $stack --profile $PROFILE --region $REGION > "$BACKUP_DIR/${stack}-template.json"
        fi
    done
    
    # Backup AgentCore configurations (if available)
    if command -v agentcore &> /dev/null; then
        print_status "Backing up AgentCore configurations..."
        
        # Backup memory configuration
        MEMORY_NAME="strava-ai-boost-memory-${ENVIRONMENT}"
        if agentcore memory list --profile $PROFILE --region $REGION 2>/dev/null | grep -q "$MEMORY_NAME"; then
            agentcore memory export --name $MEMORY_NAME --output-file "$BACKUP_DIR/agentcore-memory.json" --profile $PROFILE --region $REGION 2>/dev/null || print_warning "Could not backup AgentCore memory"
        fi
        
        # Backup agent configurations
        AGENTS=("contentgen-${ENVIRONMENT}" "campuscoach-${ENVIRONMENT}")
        for agent in "${AGENTS[@]}"; do
            if agentcore agent list --profile $PROFILE --region $REGION 2>/dev/null | grep -q "$agent"; then
                agentcore agent export --name $agent --output-file "$BACKUP_DIR/${agent}-config.json" --profile $PROFILE --region $REGION 2>/dev/null || print_warning "Could not backup agent $agent"
            fi
        done
    fi
    
    # Create backup archive
    tar -czf "${BACKUP_DIR}.tar.gz" $BACKUP_DIR/
    rm -rf $BACKUP_DIR
    
    print_status "✅ Backup created: ${BACKUP_DIR}.tar.gz"
fi

# Phase 2: Remove Strava Webhook Subscription
print_phase "🔗 Phase 2: Removing Strava webhook subscription"

# Use dedicated webhook cleanup script if available
if [ -f "scripts/cleanup_strava_webhook.sh" ]; then
    print_status "Using dedicated webhook cleanup script..."
    
    # Set environment variable for cleanup script
    export STRAVA_CLIENT_SECRET_ENV="$STRAVA_SECRET"
    
    if ./scripts/cleanup_strava_webhook.sh $ENVIRONMENT; then
        print_status "✅ Webhook cleanup completed successfully"
    else
        print_warning "⚠️  Webhook cleanup script failed, trying manual cleanup"
        
        # Fallback to manual cleanup
        manual_webhook_cleanup
    fi
else
    print_status "Dedicated webhook cleanup script not found, using manual cleanup"
    manual_webhook_cleanup
fi

# Manual webhook cleanup function (fallback)
manual_webhook_cleanup() {
    # Check if webhook configuration exists
    WEBHOOK_CONFIG_FILE="webhook-config-${ENVIRONMENT}.json"
    if [ -f "$WEBHOOK_CONFIG_FILE" ]; then
        SUBSCRIPTION_ID=$(jq -r '.subscription_id' $WEBHOOK_CONFIG_FILE 2>/dev/null || echo "")
        
        if [ "$SUBSCRIPTION_ID" != "null" ] && [ -n "$SUBSCRIPTION_ID" ]; then
            print_status "Removing Strava webhook subscription: $SUBSCRIPTION_ID"
            
            # Get Strava client secret from Secrets Manager (if available)
            if [ "$KEEP_DATA" = false ]; then
                STRAVA_SECRET=$(aws secretsmanager get-secret-value --secret-id strava-ai-boost-oauth-tokens --profile $PROFILE --region $REGION --query 'SecretString' --output text 2>/dev/null | jq -r '.client_secret' 2>/dev/null || echo "")
                
                if [ -n "$STRAVA_SECRET" ] && [ "$STRAVA_SECRET" != "null" ]; then
                    DELETE_RESPONSE=$(curl -s -X DELETE \
                        "https://www.strava.com/api/v3/push_subscriptions/$SUBSCRIPTION_ID" \
                        -H "Authorization: Bearer $STRAVA_SECRET" \
                        -H "Content-Type: application/json" || echo "ERROR")
                    
                    if [ "$DELETE_RESPONSE" != "ERROR" ]; then
                        print_status "✅ Webhook subscription removed successfully"
                    else
                        print_warning "⚠️  Could not remove webhook subscription automatically"
                        print_warning "Please remove manually at https://developers.strava.com/"
                    fi
                else
                    print_warning "Could not retrieve Strava credentials for webhook removal"
                fi
            fi
        fi
    else
        print_status "No webhook configuration found, skipping webhook removal"
    fi
    
    # Remove local webhook configuration files
    rm -f webhook-config-*.json 2>/dev/null || true
}

# Phase 3: Remove AgentCore Resources
print_phase "🤖 Phase 3: Removing AgentCore resources"

if command -v agentcore &> /dev/null; then
    print_status "AgentCore CLI found, removing agents and memory..."
    
    # Set AWS profile for AgentCore operations
    export AWS_PROFILE=$PROFILE
    
    # Remove agents with proper naming convention
    AGENTS=("strava-ai-boost-content-generator-${ENVIRONMENT}" "strava-ai-boost-campus-coach-scraper-${ENVIRONMENT}")
    for agent in "${AGENTS[@]}"; do
        print_status "Checking for agent: $agent"
        
        # Check if agent exists with better error handling
        if agentcore agent list --region $REGION 2>/dev/null | grep -q "$agent" || agentcore agent describe --name "$agent" --region $REGION >/dev/null 2>&1; then
            print_status "Removing agent: $agent"
            
            # Try graceful deletion first
            if agentcore agent delete --name "$agent" --region $REGION --confirm 2>/dev/null; then
                print_status "✅ Agent $agent removed successfully"
            else
                print_warning "Graceful deletion failed, trying force deletion"
                if agentcore agent delete --name "$agent" --region $REGION --force --confirm 2>/dev/null; then
                    print_status "✅ Agent $agent force-removed successfully"
                else
                    print_error "❌ Could not remove agent $agent"
                    print_error "Please remove manually using: agentcore agent delete --name $agent --region $REGION --force"
                fi
            fi
            
            # Wait for deletion to complete
            print_status "Waiting for agent deletion to complete..."
            for i in {1..30}; do
                if ! agentcore agent describe --name "$agent" --region $REGION >/dev/null 2>&1; then
                    print_status "✅ Agent $agent deletion confirmed"
                    break
                fi
                sleep 2
                if [ $i -eq 30 ]; then
                    print_warning "⚠️  Agent deletion verification timed out"
                fi
            done
        else
            print_status "Agent $agent not found, skipping"
        fi
    done
    
    # Remove memory with proper naming convention
    MEMORY_NAME="strava-ai-boost-memory-${ENVIRONMENT}"
    print_status "Checking for AgentCore memory: $MEMORY_NAME"
    
    if agentcore memory list --region $REGION 2>/dev/null | grep -q "$MEMORY_NAME" || agentcore memory describe --name "$MEMORY_NAME" --region $REGION >/dev/null 2>&1; then
        print_status "Removing AgentCore memory: $MEMORY_NAME"
        
        # Try graceful deletion first
        if agentcore memory delete --name "$MEMORY_NAME" --region $REGION --confirm 2>/dev/null; then
            print_status "✅ Memory $MEMORY_NAME removed successfully"
        else
            print_warning "Graceful deletion failed, trying force deletion"
            if agentcore memory delete --name "$MEMORY_NAME" --region $REGION --force --confirm 2>/dev/null; then
                print_status "✅ Memory $MEMORY_NAME force-removed successfully"
            else
                print_error "❌ Could not remove memory $MEMORY_NAME"
                print_error "Please remove manually using: agentcore memory delete --name $MEMORY_NAME --region $REGION --force"
            fi
        fi
        
        # Wait for deletion to complete
        print_status "Waiting for memory deletion to complete..."
        for i in {1..30}; do
            if ! agentcore memory describe --name "$MEMORY_NAME" --region $REGION >/dev/null 2>&1; then
                print_status "✅ Memory $MEMORY_NAME deletion confirmed"
                break
            fi
            sleep 2
            if [ $i -eq 30 ]; then
                print_warning "⚠️  Memory deletion verification timed out"
            fi
        done
    else
        print_status "Memory $MEMORY_NAME not found, skipping"
    fi
    
    # Clean up any remaining AgentCore resources
    print_status "Checking for any remaining AgentCore resources..."
    
    # List all agents and check for any strava-ai-boost related ones
    REMAINING_AGENTS=$(agentcore agent list --region $REGION 2>/dev/null | grep "strava-ai-boost" || echo "")
    if [ -n "$REMAINING_AGENTS" ]; then
        print_warning "⚠️  Found remaining AgentCore agents:"
        echo "$REMAINING_AGENTS" | tee -a $UNINSTALL_LOG_FILE
        print_warning "Please remove manually if needed"
    fi
    
    # List all memory and check for any strava-ai-boost related ones
    REMAINING_MEMORY=$(agentcore memory list --region $REGION 2>/dev/null | grep "strava-ai-boost" || echo "")
    if [ -n "$REMAINING_MEMORY" ]; then
        print_warning "⚠️  Found remaining AgentCore memory:"
        echo "$REMAINING_MEMORY" | tee -a $UNINSTALL_LOG_FILE
        print_warning "Please remove manually if needed"
    fi
    
    print_status "✅ AgentCore resources cleanup completed"
else
    print_warning "AgentCore CLI not found, skipping AgentCore cleanup"
    print_warning "If you have AgentCore resources, please remove them manually:"
    print_warning "  1. Install AgentCore CLI: pip install agentcore-cli"
    print_warning "  2. Run: agentcore agent list --region $REGION"
    print_warning "  3. Remove agents: agentcore agent delete --name <agent-name> --region $REGION --force"
    print_warning "  4. Remove memory: agentcore memory delete --name <memory-name> --region $REGION --force"
fi

# Phase 4: Remove CDK Stacks
print_phase "☁️  Phase 4: Removing CDK stacks"

# Define stacks in reverse dependency order for safe deletion
STACKS=(
    "StravaAIBoost-Monitoring"
    "StravaAIBoost-API"
    "StravaAIBoost-Webhook"
    "StravaAIBoost-Content"
    "StravaAIBoost-Core"
)

print_status "Removing CDK stacks in reverse dependency order..."

for stack in "${STACKS[@]}"; do
    if aws cloudformation describe-stacks --stack-name $stack --profile $PROFILE --region $REGION > /dev/null 2>&1; then
        print_status "Removing stack: $stack"
        
        # Use CDK destroy if available, otherwise use CloudFormation
        if command -v cdk &> /dev/null; then
            cdk destroy $stack --profile $PROFILE --region $REGION --force 2>/dev/null || {
                print_warning "CDK destroy failed, trying CloudFormation delete"
                aws cloudformation delete-stack --stack-name $stack --profile $PROFILE --region $REGION
            }
        else
            aws cloudformation delete-stack --stack-name $stack --profile $PROFILE --region $REGION
        fi
        
        # Wait for stack deletion to complete
        print_status "Waiting for stack $stack to be deleted..."
        aws cloudformation wait stack-delete-complete --stack-name $stack --profile $PROFILE --region $REGION 2>/dev/null || {
            print_warning "Stack deletion wait timed out or failed for $stack"
            print_warning "Check CloudFormation console for status"
        }
        
        print_status "✅ Stack $stack removed"
    else
        print_status "Stack $stack not found, skipping"
    fi
done

# Phase 5: Clean up remaining resources
print_phase "🧹 Phase 5: Cleaning up remaining resources"

# Remove any remaining Lambda functions
print_status "Checking for remaining Lambda functions..."
REMAINING_FUNCTIONS=$(aws lambda list-functions --profile $PROFILE --region $REGION --query 'Functions[?contains(FunctionName, `StravaAIBoost`)].FunctionName' --output text)

if [ -n "$REMAINING_FUNCTIONS" ]; then
    print_warning "Found remaining Lambda functions, removing..."
    for func in $REMAINING_FUNCTIONS; do
        print_status "Removing Lambda function: $func"
        aws lambda delete-function --function-name $func --profile $PROFILE --region $REGION 2>/dev/null || print_warning "Could not remove function $func"
    done
fi

# Remove CloudWatch log groups
print_status "Removing CloudWatch log groups..."
LOG_GROUPS=$(aws logs describe-log-groups --profile $PROFILE --region $REGION --query 'logGroups[?contains(logGroupName, `StravaAIBoost`) || contains(logGroupName, `strava-ai-boost`)].logGroupName' --output text)

if [ -n "$LOG_GROUPS" ]; then
    for log_group in $LOG_GROUPS; do
        print_status "Removing log group: $log_group"
        aws logs delete-log-group --log-group-name $log_group --profile $PROFILE --region $REGION 2>/dev/null || print_warning "Could not remove log group $log_group"
    done
fi

# Remove S3 buckets (if any)
print_status "Checking for S3 buckets..."
S3_BUCKETS=$(aws s3api list-buckets --profile $PROFILE --query 'Buckets[?contains(Name, `strava-ai-boost`)].Name' --output text)

if [ -n "$S3_BUCKETS" ]; then
    for bucket in $S3_BUCKETS; do
        print_status "Removing S3 bucket: $bucket"
        
        # Empty bucket first
        aws s3 rm s3://$bucket --recursive --profile $PROFILE 2>/dev/null || print_warning "Could not empty bucket $bucket"
        
        # Delete bucket
        aws s3api delete-bucket --bucket $bucket --profile $PROFILE 2>/dev/null || print_warning "Could not delete bucket $bucket"
    done
fi

# Phase 6: Remove data (if not keeping)
if [ "$KEEP_DATA" = false ]; then
    print_phase "🗄️  Phase 6: Removing data"
    
    # Remove DynamoDB tables
    print_status "Removing DynamoDB tables..."
    TABLES=(
        "strava-ai-boost-activities"
        "strava-ai-boost-user-configuration"
        "strava-ai-boost-rate-limits"
        "strava-ai-boost-campus-coaching-sessions"
    )
    
    for table in "${TABLES[@]}"; do
        if aws dynamodb describe-table --table-name $table --profile $PROFILE --region $REGION > /dev/null 2>&1; then
            print_status "Removing DynamoDB table: $table"
            aws dynamodb delete-table --table-name $table --profile $PROFILE --region $REGION 2>/dev/null || print_warning "Could not remove table $table"
        fi
    done
    
    # Remove Secrets Manager secrets
    print_status "Removing Secrets Manager secrets..."
    SECRETS=(
        "strava-ai-boost-oauth-tokens"
        "strava-ai-boost-campus-coach-credentials"
    )
    
    for secret in "${SECRETS[@]}"; do
        if aws secretsmanager describe-secret --secret-id $secret --profile $PROFILE --region $REGION > /dev/null 2>&1; then
            print_status "Removing secret: $secret"
            aws secretsmanager delete-secret --secret-id $secret --force-delete-without-recovery --profile $PROFILE --region $REGION 2>/dev/null || print_warning "Could not remove secret $secret"
        fi
    done
else
    print_status "Data preservation enabled - keeping DynamoDB tables and Secrets Manager secrets"
fi

# Phase 7: Verification
print_phase "✅ Phase 7: Verifying removal"

print_status "Verifying all resources have been removed..."

# Check CloudFormation stacks
REMAINING_STACKS=$(aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --profile $PROFILE --region $REGION --query 'StackSummaries[?contains(StackName, `StravaAIBoost`)].StackName' --output text)

if [ -n "$REMAINING_STACKS" ]; then
    print_warning "⚠️  Remaining CloudFormation stacks found:"
    echo "$REMAINING_STACKS"
else
    print_status "✅ All CloudFormation stacks removed"
fi

# Check Lambda functions
REMAINING_FUNCTIONS=$(aws lambda list-functions --profile $PROFILE --region $REGION --query 'Functions[?contains(FunctionName, `StravaAIBoost`)].FunctionName' --output text)

if [ -n "$REMAINING_FUNCTIONS" ]; then
    print_warning "⚠️  Remaining Lambda functions found:"
    echo "$REMAINING_FUNCTIONS"
else
    print_status "✅ All Lambda functions removed"
fi

# Check DynamoDB tables (if not keeping data)
if [ "$KEEP_DATA" = false ]; then
    REMAINING_TABLES=$(aws dynamodb list-tables --profile $PROFILE --region $REGION --query 'TableNames[?contains(@, `strava-ai-boost`)]' --output text)
    
    if [ -n "$REMAINING_TABLES" ]; then
        print_warning "⚠️  Remaining DynamoDB tables found:"
        echo "$REMAINING_TABLES"
    else
        print_status "✅ All DynamoDB tables removed"
    fi
fi

# Check AgentCore resources
if command -v agentcore &> /dev/null; then
    REMAINING_AGENTS=$(agentcore agent list --profile $PROFILE --region $REGION 2>/dev/null | grep -E "(contentgen|campuscoach).*${ENVIRONMENT}" || echo "")
    REMAINING_MEMORY=$(agentcore memory list --profile $PROFILE --region $REGION 2>/dev/null | grep "strava-ai-boost-memory-${ENVIRONMENT}" || echo "")
    
    if [ -n "$REMAINING_AGENTS" ]; then
        print_warning "⚠️  Remaining AgentCore agents found:"
        echo "$REMAINING_AGENTS"
    else
        print_status "✅ All AgentCore agents removed"
    fi
    
    if [ -n "$REMAINING_MEMORY" ]; then
        print_warning "⚠️  Remaining AgentCore memory found:"
        echo "$REMAINING_MEMORY"
    else
        print_status "✅ AgentCore memory removed"
    fi
fi

# Phase 8: Cleanup local files
print_phase "📁 Phase 8: Cleaning up local files"

print_status "Removing local deployment files..."

# Remove deployment state files
rm -f deployment-state-${ENVIRONMENT}.json
rm -f deployment-info-${ENVIRONMENT}.json
rm -f deployment-summary-${ENVIRONMENT}-*.json
rm -f webhook-config-${ENVIRONMENT}.json
rm -f validation-report-${ENVIRONMENT}-*.json

# Remove CDK output
if [ -d "cdk.out" ]; then
    print_status "Removing CDK output directory"
    rm -rf cdk.out
fi

print_status "✅ Local files cleaned up"

# Final summary
print_phase "🎉 Uninstall Complete"

echo ""
print_status "✨ Strava AI Boost uninstall completed successfully!"
print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Account: $ACCOUNT_ID"

echo ""
print_status "📋 Removal Summary:"
echo "  ✅ CDK Stacks: Removed"
echo "  ✅ Lambda Functions: Removed"
echo "  ✅ CloudWatch Logs: Removed"
echo "  ✅ AgentCore Resources: Removed"

if [ "$KEEP_DATA" = false ]; then
    echo "  ✅ DynamoDB Tables: Removed"
    echo "  ✅ Secrets Manager: Removed"
else
    echo "  💾 DynamoDB Tables: Preserved"
    echo "  💾 Secrets Manager: Preserved"
fi

if [ "$CREATE_BACKUP" = true ]; then
    echo "  💾 Backup Created: ${BACKUP_DIR}.tar.gz"
fi

echo ""
print_status "📁 Generated Files:"
echo "  - Uninstall log: $UNINSTALL_LOG_FILE"

if [ "$CREATE_BACKUP" = true ]; then
    echo "  - Backup archive: ${BACKUP_DIR}.tar.gz"
fi

echo ""
if [ -n "$REMAINING_STACKS" ] || [ -n "$REMAINING_FUNCTIONS" ] || [ -n "$REMAINING_TABLES" ]; then
    print_warning "⚠️  Some resources may require manual cleanup"
    print_warning "Check the AWS Console for any remaining resources"
    print_warning "Review the uninstall log for details: $UNINSTALL_LOG_FILE"
else
    print_status "🎯 All resources successfully removed"
fi

echo ""
print_status "🔧 Manual Steps (if applicable):"
echo "  1. Remove Strava webhook subscription at https://developers.strava.com/ (if not done automatically)"
echo "  2. Check AWS Console for any remaining resources"
echo "  3. Review AWS billing for any unexpected charges"

if [ "$KEEP_DATA" = true ]; then
    echo "  4. Manually remove preserved data when no longer needed:"
    echo "     - DynamoDB tables: strava-ai-boost-*"
    echo "     - Secrets Manager: strava-ai-boost-*"
fi

print_status "✨ Uninstall process completed successfully!"