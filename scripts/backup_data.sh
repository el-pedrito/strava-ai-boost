#!/bin/bash

# Strava AI Boost - Data Backup Script
# Creates comprehensive backup of all user data before uninstall
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/backup_data.sh [dev|prod] [--output-dir /path/to/backup]
#
# Options:
#   --output-dir    Custom backup directory (default: backup-YYYYMMDD-HHMMSS)

set -e

# Parse command line arguments
ENVIRONMENT="${1:-dev}"
OUTPUT_DIR=""

shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [dev|prod] [--output-dir /path/to/backup]"
            exit 1
            ;;
    esac
done

# Configuration
REGION="eu-west-1"
PROFILE="${AWS_PROFILE:-your-aws-profile}"
PROJECT_NAME="strava-ai-boost"

# Set default backup directory if not provided
if [ -z "$OUTPUT_DIR" ]; then
    OUTPUT_DIR="backup-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Log file
BACKUP_LOG_FILE="${OUTPUT_DIR}/backup-log.txt"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a $BACKUP_LOG_FILE
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a $BACKUP_LOG_FILE
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a $BACKUP_LOG_FILE
}

print_section() {
    echo -e "${BLUE}[SECTION]${NC} $1" | tee -a $BACKUP_LOG_FILE
}

print_phase() {
    echo -e "${CYAN}[PHASE]${NC} $1" | tee -a $BACKUP_LOG_FILE
}

print_phase "💾 Starting Strava AI Boost data backup"
print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Profile: $PROFILE"
print_status "Output directory: $OUTPUT_DIR"

# Validate environment parameter
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    print_error "Invalid environment: $ENVIRONMENT. Use 'dev' or 'prod'"
    exit 1
fi

# Create backup directory
mkdir -p $OUTPUT_DIR
mkdir -p $OUTPUT_DIR/dynamodb
mkdir -p $OUTPUT_DIR/secrets
mkdir -p $OUTPUT_DIR/lambda
mkdir -p $OUTPUT_DIR/cloudformation
mkdir -p $OUTPUT_DIR/agentcore

# Verify AWS credentials
print_status "Verifying AWS credentials..."
if ! aws sts get-caller-identity --profile $PROFILE --region $REGION > /dev/null 2>&1; then
    print_error "AWS credentials not configured for profile: $PROFILE"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --profile $PROFILE --region $REGION --query Account --output text)
print_status "Using AWS Account: $ACCOUNT_ID"

# Create backup metadata
cat > $OUTPUT_DIR/backup-metadata.json << EOF
{
  "backup_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "environment": "$ENVIRONMENT",
  "region": "$REGION",
  "account_id": "$ACCOUNT_ID",
  "profile": "$PROFILE",
  "project": "$PROJECT_NAME",
  "backup_version": "1.0"
}
EOF

print_status "✅ Backup metadata created"

# Phase 1: Backup DynamoDB Tables
print_phase "🗄️  Phase 1: Backing up DynamoDB tables"

TABLES=(
    "strava-ai-boost-activities"
    "strava-ai-boost-user-configuration"
    "strava-ai-boost-rate-limits"
    "strava-ai-boost-campus-coaching-sessions"
)

for table in "${TABLES[@]}"; do
    print_status "Backing up DynamoDB table: $table"
    
    if aws dynamodb describe-table --table-name $table --profile $PROFILE --region $REGION > /dev/null 2>&1; then
        # Backup table schema
        aws dynamodb describe-table --table-name $table --profile $PROFILE --region $REGION > "$OUTPUT_DIR/dynamodb/${table}-schema.json"
        
        # Backup table data
        print_status "Exporting data from table: $table"
        aws dynamodb scan --table-name $table --profile $PROFILE --region $REGION > "$OUTPUT_DIR/dynamodb/${table}-data.json"
        
        # Get item count for verification
        ITEM_COUNT=$(aws dynamodb scan --table-name $table --select COUNT --profile $PROFILE --region $REGION --query 'Count' --output text)
        print_status "✅ Table $table backed up ($ITEM_COUNT items)"
        
        # Create table-specific metadata
        cat > "$OUTPUT_DIR/dynamodb/${table}-metadata.json" << EOF
{
  "table_name": "$table",
  "item_count": $ITEM_COUNT,
  "backup_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "backup_method": "scan"
}
EOF
    else
        print_warning "Table $table not found, skipping"
    fi
done

print_status "✅ DynamoDB backup completed"

# Phase 2: Backup Secrets Manager Secrets
print_phase "🔐 Phase 2: Backing up Secrets Manager secrets"

SECRETS=(
    "strava-ai-boost-oauth-tokens"
    "strava-ai-boost-campus-coach-credentials"
)

for secret in "${SECRETS[@]}"; do
    print_status "Backing up secret: $secret"
    
    if aws secretsmanager describe-secret --secret-id $secret --profile $PROFILE --region $REGION > /dev/null 2>&1; then
        # Backup secret metadata (without the actual secret value for security)
        aws secretsmanager describe-secret --secret-id $secret --profile $PROFILE --region $REGION > "$OUTPUT_DIR/secrets/${secret}-metadata.json"
        
        # Backup secret value (encrypted in backup)
        aws secretsmanager get-secret-value --secret-id $secret --profile $PROFILE --region $REGION > "$OUTPUT_DIR/secrets/${secret}-value.json"
        
        print_status "✅ Secret $secret backed up"
        
        # Create secret-specific metadata
        LAST_CHANGED=$(aws secretsmanager describe-secret --secret-id $secret --profile $PROFILE --region $REGION --query 'LastChangedDate' --output text)
        cat > "$OUTPUT_DIR/secrets/${secret}-backup-metadata.json" << EOF
{
  "secret_name": "$secret",
  "last_changed": "$LAST_CHANGED",
  "backup_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "backup_method": "get-secret-value"
}
EOF
    else
        print_warning "Secret $secret not found, skipping"
    fi
done

print_status "✅ Secrets Manager backup completed"

# Phase 3: Backup Lambda Function Configurations
print_phase "⚡ Phase 3: Backing up Lambda function configurations"

print_status "Discovering Lambda functions..."
LAMBDA_FUNCTIONS=$(aws lambda list-functions --profile $PROFILE --region $REGION --query 'Functions[?contains(FunctionName, `StravaAIBoost`)].FunctionName' --output text)

if [ -n "$LAMBDA_FUNCTIONS" ]; then
    for func in $LAMBDA_FUNCTIONS; do
        print_status "Backing up Lambda function: $func"
        
        # Backup function configuration
        aws lambda get-function --function-name $func --profile $PROFILE --region $REGION > "$OUTPUT_DIR/lambda/${func}-config.json"
        
        # Backup function code (download URL - code itself is in deployment package)
        aws lambda get-function --function-name $func --profile $PROFILE --region $REGION --query 'Code.Location' --output text > "$OUTPUT_DIR/lambda/${func}-code-url.txt"
        
        # Backup environment variables (if any)
        aws lambda get-function-configuration --function-name $func --profile $PROFILE --region $REGION --query 'Environment' > "$OUTPUT_DIR/lambda/${func}-environment.json" 2>/dev/null || echo "{}" > "$OUTPUT_DIR/lambda/${func}-environment.json"
        
        print_status "✅ Lambda function $func backed up"
    done
else
    print_status "No Lambda functions found"
fi

print_status "✅ Lambda backup completed"

# Phase 4: Backup CloudFormation Stack Templates
print_phase "☁️  Phase 4: Backing up CloudFormation stack templates"

STACKS=(
    "StravaAIBoost-Core"
    "StravaAIBoost-Content"
    "StravaAIBoost-Webhook"
    "StravaAIBoost-API"
    "StravaAIBoost-Monitoring"
)

for stack in "${STACKS[@]}"; do
    print_status "Backing up CloudFormation stack: $stack"
    
    if aws cloudformation describe-stacks --stack-name $stack --profile $PROFILE --region $REGION > /dev/null 2>&1; then
        # Backup stack description
        aws cloudformation describe-stacks --stack-name $stack --profile $PROFILE --region $REGION > "$OUTPUT_DIR/cloudformation/${stack}-description.json"
        
        # Backup stack template
        aws cloudformation get-template --stack-name $stack --profile $PROFILE --region $REGION > "$OUTPUT_DIR/cloudformation/${stack}-template.json"
        
        # Backup stack parameters
        aws cloudformation describe-stacks --stack-name $stack --profile $PROFILE --region $REGION --query 'Stacks[0].Parameters' > "$OUTPUT_DIR/cloudformation/${stack}-parameters.json"
        
        # Backup stack outputs
        aws cloudformation describe-stacks --stack-name $stack --profile $PROFILE --region $REGION --query 'Stacks[0].Outputs' > "$OUTPUT_DIR/cloudformation/${stack}-outputs.json"
        
        print_status "✅ Stack $stack backed up"
    else
        print_warning "Stack $stack not found, skipping"
    fi
done

print_status "✅ CloudFormation backup completed"

# Phase 5: Backup AgentCore Resources
print_phase "🤖 Phase 5: Backing up AgentCore resources"

if command -v agentcore &> /dev/null; then
    # Set AWS profile for AgentCore operations
    export AWS_PROFILE=$PROFILE
    
    print_status "AgentCore CLI found, backing up agents and memory..."
    
    # Backup agents
    print_status "Discovering AgentCore agents..."
    ALL_AGENTS=$(agentcore agent list --region $REGION 2>/dev/null || echo "")
    STRAVA_AGENTS=$(echo "$ALL_AGENTS" | grep "strava-ai-boost" || echo "")
    
    if [ -n "$STRAVA_AGENTS" ]; then
        print_status "Found Strava AI Boost agents, backing up..."
        echo "$STRAVA_AGENTS" > "$OUTPUT_DIR/agentcore/agents-list.txt"
        
        # Extract agent names and backup each one
        AGENT_NAMES=$(echo "$STRAVA_AGENTS" | awk '{print $1}' | grep "strava-ai-boost" || echo "")
        
        for agent_name in $AGENT_NAMES; do
            if [ -n "$agent_name" ]; then
                print_status "Backing up agent: $agent_name"
                
                # Backup agent configuration
                if agentcore agent describe --name "$agent_name" --region $REGION > "$OUTPUT_DIR/agentcore/${agent_name}-config.json" 2>/dev/null; then
                    print_status "✅ Agent $agent_name configuration backed up"
                else
                    print_warning "⚠️  Could not backup agent $agent_name configuration"
                fi
                
                # Backup agent logs (recent)
                if agentcore agent logs --name "$agent_name" --region $REGION --limit 1000 > "$OUTPUT_DIR/agentcore/${agent_name}-logs.txt" 2>/dev/null; then
                    print_status "✅ Agent $agent_name logs backed up"
                else
                    print_warning "⚠️  Could not backup agent $agent_name logs"
                fi
            fi
        done
    else
        print_status "No Strava AI Boost agents found"
    fi
    
    # Backup memory
    print_status "Discovering AgentCore memory..."
    ALL_MEMORY=$(agentcore memory list --region $REGION 2>/dev/null || echo "")
    STRAVA_MEMORY=$(echo "$ALL_MEMORY" | grep "strava-ai-boost" || echo "")
    
    if [ -n "$STRAVA_MEMORY" ]; then
        print_status "Found Strava AI Boost memory, backing up..."
        echo "$STRAVA_MEMORY" > "$OUTPUT_DIR/agentcore/memory-list.txt"
        
        # Extract memory names and backup each one
        MEMORY_NAMES=$(echo "$STRAVA_MEMORY" | awk '{print $1}' | grep "strava-ai-boost" || echo "")
        
        for memory_name in $MEMORY_NAMES; do
            if [ -n "$memory_name" ]; then
                print_status "Backing up memory: $memory_name"
                
                # Backup memory configuration
                if agentcore memory describe --name "$memory_name" --region $REGION > "$OUTPUT_DIR/agentcore/${memory_name}-config.json" 2>/dev/null; then
                    print_status "✅ Memory $memory_name configuration backed up"
                else
                    print_warning "⚠️  Could not backup memory $memory_name configuration"
                fi
                
                # Backup memory data
                if agentcore memory export --name "$memory_name" --region $REGION --output-file "$OUTPUT_DIR/agentcore/${memory_name}-data.json" 2>/dev/null; then
                    print_status "✅ Memory $memory_name data backed up"
                else
                    print_warning "⚠️  Could not backup memory $memory_name data"
                fi
            fi
        done
    else
        print_status "No Strava AI Boost memory found"
    fi
    
    print_status "✅ AgentCore backup completed"
else
    print_warning "AgentCore CLI not found, skipping AgentCore backup"
    echo "AgentCore CLI not available during backup" > "$OUTPUT_DIR/agentcore/agentcore-not-available.txt"
fi

# Phase 6: Backup Additional AWS Resources
print_phase "🔧 Phase 6: Backing up additional AWS resources"

# Backup SQS queues
print_status "Backing up SQS queues..."
SQS_QUEUES=$(aws sqs list-queues --profile $PROFILE --region $REGION --query 'QueueUrls[?contains(@, `strava-ai-boost`)]' --output text)

if [ -n "$SQS_QUEUES" ]; then
    mkdir -p $OUTPUT_DIR/sqs
    for queue_url in $SQS_QUEUES; do
        QUEUE_NAME=$(basename $queue_url)
        print_status "Backing up SQS queue: $QUEUE_NAME"
        
        # Backup queue attributes
        aws sqs get-queue-attributes --queue-url $queue_url --attribute-names All --profile $PROFILE --region $REGION > "$OUTPUT_DIR/sqs/${QUEUE_NAME}-attributes.json"
        
        print_status "✅ SQS queue $QUEUE_NAME backed up"
    done
else
    print_status "No SQS queues found"
fi

# Backup Step Functions state machines
print_status "Backing up Step Functions state machines..."
STATE_MACHINES=$(aws stepfunctions list-state-machines --profile $PROFILE --region $REGION --query 'stateMachines[?contains(name, `StravaAIBoost`)].stateMachineArn' --output text)

if [ -n "$STATE_MACHINES" ]; then
    mkdir -p $OUTPUT_DIR/stepfunctions
    for state_machine_arn in $STATE_MACHINES; do
        STATE_MACHINE_NAME=$(basename $state_machine_arn)
        print_status "Backing up Step Functions state machine: $STATE_MACHINE_NAME"
        
        # Backup state machine definition
        aws stepfunctions describe-state-machine --state-machine-arn $state_machine_arn --profile $PROFILE --region $REGION > "$OUTPUT_DIR/stepfunctions/${STATE_MACHINE_NAME}-definition.json"
        
        print_status "✅ State machine $STATE_MACHINE_NAME backed up"
    done
else
    print_status "No Step Functions state machines found"
fi

print_status "✅ Additional resources backup completed"

# Phase 7: Create Backup Archive and Verification
print_phase "📦 Phase 7: Creating backup archive and verification"

# Create backup summary
BACKUP_SIZE=$(du -sh $OUTPUT_DIR | cut -f1)
FILE_COUNT=$(find $OUTPUT_DIR -type f | wc -l)

cat > $OUTPUT_DIR/backup-summary.json << EOF
{
  "backup_completed": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "backup_size": "$BACKUP_SIZE",
  "file_count": $FILE_COUNT,
  "environment": "$ENVIRONMENT",
  "region": "$REGION",
  "account_id": "$ACCOUNT_ID",
  "components_backed_up": {
    "dynamodb_tables": $(ls $OUTPUT_DIR/dynamodb/*-data.json 2>/dev/null | wc -l),
    "secrets": $(ls $OUTPUT_DIR/secrets/*-value.json 2>/dev/null | wc -l),
    "lambda_functions": $(ls $OUTPUT_DIR/lambda/*-config.json 2>/dev/null | wc -l),
    "cloudformation_stacks": $(ls $OUTPUT_DIR/cloudformation/*-template.json 2>/dev/null | wc -l),
    "agentcore_agents": $(ls $OUTPUT_DIR/agentcore/*-config.json 2>/dev/null | wc -l),
    "agentcore_memory": $(ls $OUTPUT_DIR/agentcore/*-data.json 2>/dev/null | wc -l)
  }
}
EOF

# Create backup verification script
cat > $OUTPUT_DIR/verify-backup.sh << 'EOF'
#!/bin/bash
# Backup Verification Script
# Run this script to verify backup integrity

echo "🔍 Verifying Strava AI Boost backup..."

# Check backup metadata
if [ -f "backup-metadata.json" ]; then
    echo "✅ Backup metadata found"
    BACKUP_DATE=$(jq -r '.backup_timestamp' backup-metadata.json)
    echo "   Backup date: $BACKUP_DATE"
else
    echo "❌ Backup metadata missing"
fi

# Check backup summary
if [ -f "backup-summary.json" ]; then
    echo "✅ Backup summary found"
    BACKUP_SIZE=$(jq -r '.backup_size' backup-summary.json)
    FILE_COUNT=$(jq -r '.file_count' backup-summary.json)
    echo "   Backup size: $BACKUP_SIZE"
    echo "   File count: $FILE_COUNT"
else
    echo "❌ Backup summary missing"
fi

# Verify directory structure
EXPECTED_DIRS=("dynamodb" "secrets" "lambda" "cloudformation" "agentcore")
for dir in "${EXPECTED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        FILE_COUNT=$(find "$dir" -type f | wc -l)
        echo "✅ $dir directory found ($FILE_COUNT files)"
    else
        echo "⚠️  $dir directory not found"
    fi
done

# Verify critical files
echo ""
echo "📋 Critical Files Check:"

# DynamoDB data files
DYNAMODB_FILES=$(find dynamodb -name "*-data.json" 2>/dev/null | wc -l)
echo "   DynamoDB data files: $DYNAMODB_FILES"

# Secrets files
SECRET_FILES=$(find secrets -name "*-value.json" 2>/dev/null | wc -l)
echo "   Secret files: $SECRET_FILES"

# Lambda config files
LAMBDA_FILES=$(find lambda -name "*-config.json" 2>/dev/null | wc -l)
echo "   Lambda config files: $LAMBDA_FILES"

echo ""
echo "✅ Backup verification completed"
EOF

chmod +x $OUTPUT_DIR/verify-backup.sh

# Create restore instructions
cat > $OUTPUT_DIR/RESTORE-INSTRUCTIONS.md << 'EOF'
# Strava AI Boost - Restore Instructions

This backup contains all data and configurations for your Strava AI Boost system.

## Backup Contents

- **DynamoDB Tables**: All activity data, user configuration, rate limits, and coaching sessions
- **Secrets Manager**: OAuth tokens and Campus Coach credentials
- **Lambda Functions**: Function configurations and environment variables
- **CloudFormation**: Stack templates, parameters, and outputs
- **AgentCore**: Agent configurations, memory data, and logs
- **Additional Resources**: SQS queues, Step Functions state machines

## Restore Process

### 1. Verify Backup Integrity
```bash
./verify-backup.sh
```

### 2. Restore DynamoDB Tables
```bash
# For each table in dynamodb/ directory:
aws dynamodb create-table --cli-input-json file://dynamodb/TABLE-NAME-schema.json
aws dynamodb batch-write-item --request-items file://dynamodb/TABLE-NAME-data.json
```

### 3. Restore Secrets Manager
```bash
# For each secret in secrets/ directory:
aws secretsmanager create-secret --name SECRET-NAME --secret-string file://secrets/SECRET-NAME-value.json
```

### 4. Restore AgentCore Resources
```bash
# Install AgentCore CLI if not available
pip install agentcore-cli

# For each agent in agentcore/ directory:
agentcore agent create --config file://agentcore/AGENT-NAME-config.json

# For each memory in agentcore/ directory:
agentcore memory create --config file://agentcore/MEMORY-NAME-config.json
agentcore memory import --name MEMORY-NAME --input-file agentcore/MEMORY-NAME-data.json
```

### 5. Redeploy Infrastructure
```bash
# Use the CloudFormation templates to recreate the infrastructure
cdk deploy --all
```

## Important Notes

- **Secrets**: Handle secret files with care - they contain sensitive authentication data
- **AgentCore**: Ensure AgentCore CLI is properly configured before restoring agents
- **Dependencies**: Restore in order: Secrets → DynamoDB → AgentCore → Infrastructure
- **Validation**: Test the restored system thoroughly before using in production

## Support

If you encounter issues during restore:
1. Check the backup-log.txt for any warnings during backup creation
2. Verify AWS credentials and permissions
3. Ensure all required AWS services are available in your region
4. Check the backup-summary.json for component counts
EOF

# Create backup archive
print_status "Creating backup archive..."
ARCHIVE_NAME="${OUTPUT_DIR}.tar.gz"
tar -czf $ARCHIVE_NAME $OUTPUT_DIR/

# Calculate archive size and checksum
ARCHIVE_SIZE=$(du -sh $ARCHIVE_NAME | cut -f1)
ARCHIVE_CHECKSUM=$(shasum -a 256 $ARCHIVE_NAME | cut -d' ' -f1)

print_status "✅ Backup archive created: $ARCHIVE_NAME"
print_status "Archive size: $ARCHIVE_SIZE"
print_status "SHA256 checksum: $ARCHIVE_CHECKSUM"

# Update backup summary with archive info
jq --arg archive_name "$ARCHIVE_NAME" \
   --arg archive_size "$ARCHIVE_SIZE" \
   --arg checksum "$ARCHIVE_CHECKSUM" \
   '. + {
     "archive_name": $archive_name,
     "archive_size": $archive_size,
     "sha256_checksum": $checksum
   }' $OUTPUT_DIR/backup-summary.json > $OUTPUT_DIR/backup-summary-updated.json

mv $OUTPUT_DIR/backup-summary-updated.json $OUTPUT_DIR/backup-summary.json

# Final Summary
print_phase "🎉 Backup Complete"

echo ""
print_status "✨ Strava AI Boost data backup completed successfully!"
print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Account: $ACCOUNT_ID"

echo ""
print_status "📦 Backup Details:"
echo "  📁 Directory: $OUTPUT_DIR"
echo "  📦 Archive: $ARCHIVE_NAME"
echo "  📏 Size: $ARCHIVE_SIZE"
echo "  🔍 Files: $FILE_COUNT"
echo "  🔐 Checksum: $ARCHIVE_CHECKSUM"

echo ""
print_status "📋 Components Backed Up:"
echo "  🗄️  DynamoDB Tables: $(ls $OUTPUT_DIR/dynamodb/*-data.json 2>/dev/null | wc -l)"
echo "  🔐 Secrets: $(ls $OUTPUT_DIR/secrets/*-value.json 2>/dev/null | wc -l)"
echo "  ⚡ Lambda Functions: $(ls $OUTPUT_DIR/lambda/*-config.json 2>/dev/null | wc -l)"
echo "  ☁️  CloudFormation Stacks: $(ls $OUTPUT_DIR/cloudformation/*-template.json 2>/dev/null | wc -l)"
echo "  🤖 AgentCore Agents: $(ls $OUTPUT_DIR/agentcore/*-config.json 2>/dev/null | wc -l)"
echo "  🧠 AgentCore Memory: $(ls $OUTPUT_DIR/agentcore/*-data.json 2>/dev/null | wc -l)"

echo ""
print_status "📁 Generated Files:"
echo "  - Backup directory: $OUTPUT_DIR/"
echo "  - Backup archive: $ARCHIVE_NAME"
echo "  - Backup log: $BACKUP_LOG_FILE"
echo "  - Verification script: $OUTPUT_DIR/verify-backup.sh"
echo "  - Restore instructions: $OUTPUT_DIR/RESTORE-INSTRUCTIONS.md"

echo ""
print_status "🔧 Next Steps:"
echo "  1. Verify backup integrity: cd $OUTPUT_DIR && ./verify-backup.sh"
echo "  2. Store backup archive in a safe location"
echo "  3. Test restore process in a separate environment (recommended)"
echo "  4. Keep backup archive and checksum for future reference"

echo ""
print_status "⚠️  Security Reminder:"
echo "  - Backup contains sensitive data (OAuth tokens, credentials)"
echo "  - Store backup archive securely and encrypt if needed"
echo "  - Limit access to backup files to authorized personnel only"

print_status "✨ Backup process completed successfully!"