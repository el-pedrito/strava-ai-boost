#!/bin/bash
# Tag AgentCore resources (runtimes + memories + IAM execution roles)
# + apply CloudWatch Data Protection Policy on runtime log groups.
#
# Idempotent — safe to run multiple times.
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/tag_agentcore_resources.sh
#
# Why: AgentCore cost allocation tags are a known gap (re:Post bug, Aug 2025).
# Tagging the underlying IAM execution roles enables per-agent Bedrock cost
# attribution via CUR 2.0 IAM Principal data (released 13 Apr 2026).
# The Data Protection Policy masks credentials leaking into OTEL tool-call
# spans (P1.3).

set -e

export AWS_PROFILE="${AWS_PROFILE:-your-aws-profile}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export TAGS_PROJECT="${TAGS_PROJECT:-StravaAIBoost}"
export TAGS_ENVIRONMENT="${ENVIRONMENT:-dev}"
export TAGS_OWNER="${OWNER_TAG:-admin}"
export TAGS_COST_CENTER="${TAGS_COST_CENTER:-strava-ai-boost}"
export TAGS_MANAGED_BY="${TAGS_MANAGED_BY:-AgentCore-CLI}"

echo "🏷️  Tagging AgentCore resources (region=$AWS_REGION, profile=$AWS_PROFILE)..."

python3 "$(dirname "$0")/tag_agentcore_resources.py"

echo ""
echo "✅ Done. Next steps (AWS Billing Console, manual):"
echo "   1. Cost Allocation Tags → User-defined → activate: agent, Project, CostCenter"
echo "   2. Wait 24-48h for propagation in Cost Explorer"
echo "   3. (Optional) Create CUR 2.0 export with IAM Principal data for"
echo "      per-agent Bedrock cost attribution."
