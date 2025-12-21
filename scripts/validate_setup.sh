#!/bin/bash

# Validate Strava AI Boost Setup
# Checks prerequisites and configuration before deployment

set -e

echo "🔍 Validating Strava AI Boost setup..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Check Python version
print_check "Python version (requires 3.12+)"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
    
    if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 12 ]; then
        print_pass "Python $PYTHON_VERSION found"
    else
        print_fail "Python 3.12+ required, found $PYTHON_VERSION"
    fi
else
    print_fail "Python 3 not found"
fi

# Check Node.js for CDK
print_check "Node.js (required for CDK)"
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    print_pass "Node.js $NODE_VERSION found"
else
    print_fail "Node.js not found (required for AWS CDK)"
fi

# Check AWS CDK
print_check "AWS CDK CLI"
if command -v cdk &> /dev/null; then
    CDK_VERSION=$(cdk --version)
    print_pass "AWS CDK $CDK_VERSION found"
else
    print_fail "AWS CDK CLI not found (install with: npm install -g aws-cdk)"
fi

# Check AWS CLI
print_check "AWS CLI"
if command -v aws &> /dev/null; then
    AWS_VERSION=$(aws --version 2>&1 | cut -d' ' -f1)
    print_pass "$AWS_VERSION found"
else
    print_fail "AWS CLI not found"
fi

# Check AWS profile
print_check "AWS profile configuration"
if aws sts get-caller-identity --profile "${AWS_PROFILE:-your-aws-profile}" &> /dev/null; then
    ACCOUNT_ID=$(aws sts get-caller-identity --profile "${AWS_PROFILE:-your-aws-profile}" --query Account --output text)
    print_pass "AWS profile ${AWS_PROFILE:-your-aws-profile} configured (Account: $ACCOUNT_ID)"
else
    print_fail "AWS profile ${AWS_PROFILE:-your-aws-profile} not configured or invalid"
fi

# Check AgentCore CLI
print_check "AgentCore CLI"
if command -v agentcore &> /dev/null; then
    print_pass "AgentCore CLI found"
else
    print_warning "AgentCore CLI not found (install from AgentCore documentation)"
fi

# Check Python dependencies
print_check "Python dependencies"
if [ -f "requirements.txt" ]; then
    if python3 -c "import aws_cdk_lib, boto3, pydantic" &> /dev/null; then
        print_pass "Core Python dependencies available"
    else
        print_warning "Some Python dependencies missing (run: pip install -r requirements.txt)"
    fi
else
    print_fail "requirements.txt not found"
fi

# Check project structure
print_check "Project structure"
REQUIRED_DIRS=("stacks" "lambda_functions" "src" "scripts" "local_interface")
MISSING_DIRS=()

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        MISSING_DIRS+=("$dir")
    fi
done

if [ ${#MISSING_DIRS[@]} -eq 0 ]; then
    print_pass "All required directories present"
else
    print_fail "Missing directories: ${MISSING_DIRS[*]}"
fi

# Check CDK configuration
print_check "CDK configuration"
if [ -f "cdk.json" ]; then
    print_pass "cdk.json found"
else
    print_fail "cdk.json not found"
fi

if [ -f "app.py" ]; then
    print_pass "CDK app.py found"
else
    print_fail "CDK app.py not found"
fi

# Check script permissions
print_check "Script permissions"
SCRIPTS=("scripts/deploy_agentcore.sh" "scripts/setup_memory.sh" "scripts/deploy_campus_coach_agent.sh")
NON_EXECUTABLE=()

for script in "${SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        if [ -x "$script" ]; then
            continue
        else
            NON_EXECUTABLE+=("$script")
        fi
    else
        NON_EXECUTABLE+=("$script (missing)")
    fi
done

if [ ${#NON_EXECUTABLE[@]} -eq 0 ]; then
    print_pass "All scripts are executable"
else
    print_warning "Non-executable scripts: ${NON_EXECUTABLE[*]} (run: chmod +x scripts/*.sh)"
fi

# Summary
echo ""
echo "📊 Validation Summary:"
echo "  ✅ Checks passed: $CHECKS_PASSED"
echo "  ❌ Checks failed: $CHECKS_FAILED"
echo "  ⚠️  Warnings: $WARNINGS"

if [ $CHECKS_FAILED -eq 0 ]; then
    echo ""
    print_pass "✨ Setup validation completed successfully!"
    echo ""
    print_info "🚀 Ready for deployment. Next steps:"
    echo "  1. Deploy AgentCore: ./scripts/deploy_agentcore.sh"
    echo "  2. Deploy CDK stacks: cdk deploy --all --profile \${AWS_PROFILE:-your-aws-profile}"
    echo "  3. Start local interface: cd local_interface && python app.py"
    exit 0
else
    echo ""
    print_fail "❌ Setup validation failed. Please fix the issues above before deployment."
    exit 1
fi