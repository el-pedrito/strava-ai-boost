#!/bin/bash

# Strava AI Boost - Frontend Deployment Script
#
# The Frontend CDK stack only creates the S3 bucket and the CloudFront
# distribution: it contains no BucketDeployment, and scripts/deploy.sh does not
# touch the frontend. Publishing the built site was therefore a manual,
# undocumented step -- which is how production ended up serving a bundle that
# was 11 days behind the repository (missing npm CVE fixes and responsive
# fixes) with nothing signalling the drift.
#
# This script performs the whole sequence, in the only order that is correct:
#   build -> upload -> invalidate CloudFront -> wait -> verify what is served.
# Skipping the invalidation leaves users on the previous cached bundle.
#
# Usage:
#   export AWS_PROFILE=your-aws-profile   # optional: omit to use ambient credentials
#   ./scripts/deploy_frontend.sh [dev|prod]
#
# Options:
#   --skip-build   Reuse the existing frontend/dist (must already be built)
#   --dry-run      Show what would be uploaded/deleted, change nothing

set -e

ENVIRONMENT="dev"
SKIP_BUILD=false
DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        dev|prod) ENVIRONMENT="$arg" ;;
        --skip-build) SKIP_BUILD=true ;;
        --dry-run) DRY_RUN=true ;;
        *) echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done

REGION="${AWS_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-}"
FRONTEND_STACK="StravaAIBoost-Frontend"

# Only pass --profile when one is configured; otherwise rely on the ambient
# credentials (environment variables, instance role, container role...).
if [ -n "$PROFILE" ]; then
    PROFILE_ARGS=(--profile "$PROFILE")
else
    PROFILE_ARGS=()
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status()  { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# 1. Resolve the target from CloudFormation (never hardcode account resources)
# ---------------------------------------------------------------------------
print_status "Resolving frontend stack outputs ($FRONTEND_STACK)..."

stack_output() {
    aws cloudformation describe-stacks \
        --stack-name "$FRONTEND_STACK" \
        --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
        --output text --region "$REGION" "${PROFILE_ARGS[@]}" 2>/dev/null
}

BUCKET="$(stack_output BucketName)"
DISTRIBUTION_ID="$(stack_output DistributionId)"
DOMAIN="$(stack_output DistributionDomain)"

if [ -z "$BUCKET" ] || [ "$BUCKET" = "None" ] \
   || [ -z "$DISTRIBUTION_ID" ] || [ "$DISTRIBUTION_ID" = "None" ]; then
    print_error "Could not read BucketName/DistributionId from $FRONTEND_STACK."
    print_error "Deploy the infrastructure first: ./scripts/deploy.sh $ENVIRONMENT"
    exit 1
fi

print_status "  Bucket:       $BUCKET"
print_status "  Distribution: $DISTRIBUTION_ID"
print_status "  Domain:       https://$DOMAIN"

# ---------------------------------------------------------------------------
# 2. Build
# ---------------------------------------------------------------------------
if [ "$SKIP_BUILD" = true ]; then
    print_warning "Skipping build (--skip-build); using the existing frontend/dist"
    [ -d frontend/dist ] || { print_error "frontend/dist does not exist"; exit 1; }
else
    print_status "Building the frontend..."
    (cd frontend && npm run build)
fi

[ -f frontend/dist/index.html ] || { print_error "frontend/dist/index.html missing after build"; exit 1; }

# ---------------------------------------------------------------------------
# 3. Upload
#
# config.json holds the RUNTIME configuration (API URL, Cognito ids,
# coachRuntimeArn) and is populated in S3 by deploy_agentcore_agents.sh. The
# copy in frontend/public/ is a local, gitignored convenience file, so the
# deployed one is authoritative and must never be overwritten from here.
# ---------------------------------------------------------------------------
SYNC_ARGS=(frontend/dist/ "s3://$BUCKET/" --delete --exclude config.json)

if [ "$DRY_RUN" = true ]; then
    print_warning "Dry run: showing planned changes only"
    aws s3 sync "${SYNC_ARGS[@]}" --dryrun --region "$REGION" "${PROFILE_ARGS[@]}"
    print_status "Dry run complete; nothing was changed."
    exit 0
fi

print_status "Uploading to S3 (config.json preserved)..."
aws s3 sync "${SYNC_ARGS[@]}" --region "$REGION" "${PROFILE_ARGS[@]}"

# ---------------------------------------------------------------------------
# 4. Invalidate CloudFront and WAIT
#
# Without this, visitors keep receiving the previous bundle from the edge cache
# and the deployment silently appears to have had no effect.
# ---------------------------------------------------------------------------
print_status "Creating CloudFront invalidation..."
INVALIDATION_ID="$(aws cloudfront create-invalidation \
    --distribution-id "$DISTRIBUTION_ID" --paths '/*' \
    --query 'Invalidation.Id' --output text "${PROFILE_ARGS[@]}")"
print_status "  Invalidation: $INVALIDATION_ID (waiting for completion...)"
aws cloudfront wait invalidation-completed \
    --distribution-id "$DISTRIBUTION_ID" --id "$INVALIDATION_ID" "${PROFILE_ARGS[@]}"
print_status "  Invalidation completed"

# ---------------------------------------------------------------------------
# 5. Verify what is actually served (not merely what was uploaded)
# ---------------------------------------------------------------------------
print_status "Verifying the deployed site..."

LOCAL_BUNDLE="$(grep -oE 'assets/index-[A-Za-z0-9_-]+\.js' frontend/dist/index.html | head -1)"
SERVED_BUNDLE="$(curl -fsS -H 'Cache-Control: no-cache' "https://$DOMAIN/" \
    | grep -oE 'assets/index-[A-Za-z0-9_-]+\.js' | head -1 || true)"
HTTP_CODE="$(curl -fsS -o /dev/null -w '%{http_code}' "https://$DOMAIN/" || echo 000)"
CONFIG_CODE="$(curl -fsS -o /dev/null -w '%{http_code}' "https://$DOMAIN/config.json" || echo 000)"

print_status "  HTTP /            : $HTTP_CODE"
print_status "  HTTP /config.json : $CONFIG_CODE"
print_status "  bundle built      : ${LOCAL_BUNDLE:-unknown}"
print_status "  bundle served     : ${SERVED_BUNDLE:-unknown}"

FAILED=false
[ "$HTTP_CODE" = "200" ] || { print_error "Site did not return 200"; FAILED=true; }
[ "$CONFIG_CODE" = "200" ] || { print_error "config.json is not reachable"; FAILED=true; }
if [ -n "$LOCAL_BUNDLE" ] && [ -n "$SERVED_BUNDLE" ] && [ "$LOCAL_BUNDLE" != "$SERVED_BUNDLE" ]; then
    print_error "Served bundle does not match the build (stale cache?)"
    FAILED=true
fi

if [ "$FAILED" = true ]; then
    print_error "Frontend deployment verification FAILED"
    exit 1
fi

print_status "Frontend deployed and verified: https://$DOMAIN"
