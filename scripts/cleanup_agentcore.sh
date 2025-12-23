#!/bin/bash

# Strava AI Boost - AgentCore Cleanup Script
# Specialized script for cleaning up AgentCore resources
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/cleanup_agentcore.sh [dev|prod] [--force] [--backup]
#
# Options:
#   --force      Skip confirmation prompts
#   --backup     Create backup before deletion

set -e

# Parse command line arguments
ENVIRONMENT="${1:-dev}"
FORCE_MODE=false
CREATE_BACKUP=false

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
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [dev|prod] [--force] [--backup]"
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

# Log file
CLEANUP_LOG_FILE="agentcore-cleanup-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S).log"
BACKUP_DIR="agentcore-backup-${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a $CLEANUP_LOG_FILE
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a $CLEANUP_LOG_FILE
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a $CLEANUP_LOG_FILE
}

print_section() {
    echo -e "${BLUE}[SECTION]${NC} $1" | tee -a $CLEANUP_LOG_FILE
}

print_phase() {
    echo -e "${CYAN}[PHASE]${NC} $1" | tee -a $CLEANUP_LOG_FILE
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

print_phase "🤖 Starting AgentCore cleanup for Strava AI Boost"
print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Profile: $PROFILE"
print_status "Force mode: $FORCE_MODE"
print_status "Create backup: $CREATE_BACKUP"

# Validate environment parameter
if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
    print_error "Invalid environment: $ENVIRONMENT. Use 'dev' or 'prod'"
    exit 1
fi

# Check if AgentCore CLI is available
if ! command -v agentcore &> /dev/null; then
    print_error "AgentCore CLI not found"
    print_error "Please install AgentCore CLI first:"
    print_error "  pip install agentcore-cli"
    print_error "Or remove AgentCore resources manually from AWS Console"
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

# Set AWS profile for AgentCore operations
export AWS_PROFILE=$PROFILE

# Warning about destructive operation
echo ""
print_warning "🚨 AGENTCORE CLEANUP WARNING 🚨"
print_warning "This will permanently delete:"
print_warning "  - All Strava AI Boost AgentCore agents"
print_warning "  - AgentCore Memory with all learned personalization data"
print_warning "  - Agent configurations and prompts"
print_warning "  - All agent execution history and logs"

if [ "$CREATE_BACKUP" = true ]; then
    print_status "Backup enabled - configurations will be exported before deletion"
fi

echo ""
confirm_action "This will permanently delete your AgentCore resources"

# Phase 1: Discovery and Inventory
print_phase "🔍 Phase 1: Discovering AgentCore resources"

print_status "Scanning for Strava AI Boost AgentCore resources..."

# Discover agents
print_status "Discovering agents..."
ALL_AGENTS=$(agentcore agent list --region $REGION 2>/dev/null || echo "")
STRAVA_AGENTS=$(echo "$ALL_AGENTS" | grep "strava-ai-boost" || echo "")

if [ -n "$STRAVA_AGENTS" ]; then
    print_status "Found Strava AI Boost agents:"
    echo "$STRAVA_AGENTS" | tee -a $CLEANUP_LOG_FILE
else
    print_status "No Strava AI Boost agents found"
fi

# Discover memory
print_status "Discovering memory resources..."
ALL_MEMORY=$(agentcore memory list --region $REGION 2>/dev/null || echo "")
STRAVA_MEMORY=$(echo "$ALL_MEMORY" | grep "strava-ai-boost" || echo "")

if [ -n "$STRAVA_MEMORY" ]; then
    print_status "Found Strava AI Boost memory:"
    echo "$STRAVA_MEMORY" | tee -a $CLEANUP_LOG_FILE
else
    print_status "No Strava AI Boost memory found"
fi

# Check if there's anything to clean up
if [ -z "$STRAVA_AGENTS" ] && [ -z "$STRAVA_MEMORY" ]; then
    print_status "✅ No Strava AI Boost AgentCore resources found"
    print_status "Cleanup complete - nothing to remove"
    exit 0
fi

# Phase 2: Create Backup (if requested)
if [ "$CREATE_BACKUP" = true ]; then
    print_phase "💾 Phase 2: Creating AgentCore backup"
    
    mkdir -p $BACKUP_DIR
    
    # Backup agent configurations
    if [ -n "$STRAVA_AGENTS" ]; then
        print_status "Backing up agent configurations..."
        
        # Extract agent names from the list
        AGENT_NAMES=$(echo "$STRAVA_AGENTS" | awk '{print $1}' | grep "strava-ai-boost" || echo "")
        
        for agent_name in $AGENT_NAMES; do
            if [ -n "$agent_name" ]; then
                print_status "Backing up agent: $agent_name"
                
                # Export agent configuration
                if agentcore agent describe --name "$agent_name" --region $REGION > "$BACKUP_DIR/${agent_name}-config.json" 2>/dev/null; then
                    print_status "✅ Agent $agent_name configuration backed up"
                else
                    print_warning "⚠️  Could not backup agent $agent_name configuration"
                fi
                
                # Export agent logs (if available)
                if agentcore agent logs --name "$agent_name" --region $REGION --limit 1000 > "$BACKUP_DIR/${agent_name}-logs.txt" 2>/dev/null; then
                    print_status "✅ Agent $agent_name logs backed up"
                else
                    print_warning "⚠️  Could not backup agent $agent_name logs"
                fi
            fi
        done
    fi
    
    # Backup memory data
    if [ -n "$STRAVA_MEMORY" ]; then
        print_status "Backing up memory data..."
        
        # Extract memory names from the list
        MEMORY_NAMES=$(echo "$STRAVA_MEMORY" | awk '{print $1}' | grep "strava-ai-boost" || echo "")
        
        for memory_name in $MEMORY_NAMES; do
            if [ -n "$memory_name" ]; then
                print_status "Backing up memory: $memory_name"
                
                # Export memory configuration
                if agentcore memory describe --name "$memory_name" --region $REGION > "$BACKUP_DIR/${memory_name}-config.json" 2>/dev/null; then
                    print_status "✅ Memory $memory_name configuration backed up"
                else
                    print_warning "⚠️  Could not backup memory $memory_name configuration"
                fi
                
                # Export memory data (if available)
                if agentcore memory export --name "$memory_name" --region $REGION --output-file "$BACKUP_DIR/${memory_name}-data.json" 2>/dev/null; then
                    print_status "✅ Memory $memory_name data backed up"
                else
                    print_warning "⚠️  Could not backup memory $memory_name data"
                fi
            fi
        done
    fi
    
    # Create backup archive
    if [ -d "$BACKUP_DIR" ] && [ "$(ls -A $BACKUP_DIR)" ]; then
        tar -czf "${BACKUP_DIR}.tar.gz" $BACKUP_DIR/
        rm -rf $BACKUP_DIR
        print_status "✅ Backup created: ${BACKUP_DIR}.tar.gz"
    else
        print_warning "⚠️  No backup data to archive"
        rm -rf $BACKUP_DIR
    fi
fi

# Phase 3: Remove Agents
if [ -n "$STRAVA_AGENTS" ]; then
    print_phase "🤖 Phase 3: Removing AgentCore agents"
    
    # Extract agent names from the list
    AGENT_NAMES=$(echo "$STRAVA_AGENTS" | awk '{print $1}' | grep "strava-ai-boost" || echo "")
    
    for agent_name in $AGENT_NAMES; do
        if [ -n "$agent_name" ]; then
            print_status "Removing agent: $agent_name"
            
            # Check if agent still exists
            if agentcore agent describe --name "$agent_name" --region $REGION >/dev/null 2>&1; then
                # Try graceful deletion first
                if agentcore agent delete --name "$agent_name" --region $REGION --confirm 2>/dev/null; then
                    print_status "✅ Agent $agent_name removed successfully"
                else
                    print_warning "Graceful deletion failed, trying force deletion"
                    if agentcore agent delete --name "$agent_name" --region $REGION --force --confirm 2>/dev/null; then
                        print_status "✅ Agent $agent_name force-removed successfully"
                    else
                        print_error "❌ Could not remove agent $agent_name"
                        print_error "Please remove manually using: agentcore agent delete --name $agent_name --region $REGION --force"
                        continue
                    fi
                fi
                
                # Wait for deletion to complete
                print_status "Waiting for agent deletion to complete..."
                for i in {1..30}; do
                    if ! agentcore agent describe --name "$agent_name" --region $REGION >/dev/null 2>&1; then
                        print_status "✅ Agent $agent_name deletion confirmed"
                        break
                    fi
                    sleep 2
                    if [ $i -eq 30 ]; then
                        print_warning "⚠️  Agent deletion verification timed out"
                    fi
                done
            else
                print_status "Agent $agent_name no longer exists, skipping"
            fi
        fi
    done
else
    print_status "No agents to remove"
fi

# Phase 4: Remove Memory
if [ -n "$STRAVA_MEMORY" ]; then
    print_phase "🧠 Phase 4: Removing AgentCore memory"
    
    # Extract memory names from the list
    MEMORY_NAMES=$(echo "$STRAVA_MEMORY" | awk '{print $1}' | grep "strava-ai-boost" || echo "")
    
    for memory_name in $MEMORY_NAMES; do
        if [ -n "$memory_name" ]; then
            print_status "Removing memory: $memory_name"
            
            # Check if memory still exists
            if agentcore memory describe --name "$memory_name" --region $REGION >/dev/null 2>&1; then
                # Try graceful deletion first
                if agentcore memory delete --name "$memory_name" --region $REGION --confirm 2>/dev/null; then
                    print_status "✅ Memory $memory_name removed successfully"
                else
                    print_warning "Graceful deletion failed, trying force deletion"
                    if agentcore memory delete --name "$memory_name" --region $REGION --force --confirm 2>/dev/null; then
                        print_status "✅ Memory $memory_name force-removed successfully"
                    else
                        print_error "❌ Could not remove memory $memory_name"
                        print_error "Please remove manually using: agentcore memory delete --name $memory_name --region $REGION --force"
                        continue
                    fi
                fi
                
                # Wait for deletion to complete
                print_status "Waiting for memory deletion to complete..."
                for i in {1..30}; do
                    if ! agentcore memory describe --name "$memory_name" --region $REGION >/dev/null 2>&1; then
                        print_status "✅ Memory $memory_name deletion confirmed"
                        break
                    fi
                    sleep 2
                    if [ $i -eq 30 ]; then
                        print_warning "⚠️  Memory deletion verification timed out"
                    fi
                done
            else
                print_status "Memory $memory_name no longer exists, skipping"
            fi
        fi
    done
else
    print_status "No memory to remove"
fi

# Phase 5: Final Verification
print_phase "✅ Phase 5: Verifying AgentCore cleanup"

print_status "Verifying all AgentCore resources have been removed..."

# Check for remaining agents
REMAINING_AGENTS=$(agentcore agent list --region $REGION 2>/dev/null | grep "strava-ai-boost" || echo "")
if [ -n "$REMAINING_AGENTS" ]; then
    print_warning "⚠️  Remaining AgentCore agents found:"
    echo "$REMAINING_AGENTS" | tee -a $CLEANUP_LOG_FILE
    print_warning "Please remove manually if needed"
else
    print_status "✅ All Strava AI Boost agents removed"
fi

# Check for remaining memory
REMAINING_MEMORY=$(agentcore memory list --region $REGION 2>/dev/null | grep "strava-ai-boost" || echo "")
if [ -n "$REMAINING_MEMORY" ]; then
    print_warning "⚠️  Remaining AgentCore memory found:"
    echo "$REMAINING_MEMORY" | tee -a $CLEANUP_LOG_FILE
    print_warning "Please remove manually if needed"
else
    print_status "✅ All Strava AI Boost memory removed"
fi

# Phase 6: Cleanup Summary
print_phase "🎉 AgentCore Cleanup Complete"

echo ""
print_status "✨ AgentCore cleanup completed successfully!"
print_status "Environment: $ENVIRONMENT"
print_status "Region: $REGION"
print_status "Account: $ACCOUNT_ID"

echo ""
print_status "📋 Cleanup Summary:"
if [ -z "$REMAINING_AGENTS" ]; then
    echo "  ✅ AgentCore Agents: All removed"
else
    echo "  ⚠️  AgentCore Agents: Some remain (see log)"
fi

if [ -z "$REMAINING_MEMORY" ]; then
    echo "  ✅ AgentCore Memory: All removed"
else
    echo "  ⚠️  AgentCore Memory: Some remain (see log)"
fi

if [ "$CREATE_BACKUP" = true ]; then
    echo "  💾 Backup Created: ${BACKUP_DIR}.tar.gz"
fi

echo ""
print_status "📁 Generated Files:"
echo "  - Cleanup log: $CLEANUP_LOG_FILE"

if [ "$CREATE_BACKUP" = true ] && [ -f "${BACKUP_DIR}.tar.gz" ]; then
    echo "  - Backup archive: ${BACKUP_DIR}.tar.gz"
fi

echo ""
if [ -n "$REMAINING_AGENTS" ] || [ -n "$REMAINING_MEMORY" ]; then
    print_warning "⚠️  Some AgentCore resources may require manual cleanup"
    print_warning "Check the cleanup log for details: $CLEANUP_LOG_FILE"
    print_warning "Use the following commands to remove remaining resources:"
    echo "  agentcore agent delete --name <agent-name> --region $REGION --force"
    echo "  agentcore memory delete --name <memory-name> --region $REGION --force"
else
    print_status "🎯 All AgentCore resources successfully removed"
fi

echo ""
print_status "🔧 Manual Verification Steps:"
echo "  1. Run: agentcore agent list --region $REGION"
echo "  2. Run: agentcore memory list --region $REGION"
echo "  3. Verify no strava-ai-boost resources remain"
echo "  4. Check AWS Console for any remaining AgentCore resources"

print_status "✨ AgentCore cleanup process completed successfully!"