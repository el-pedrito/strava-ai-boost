#!/bin/bash
# Enable AWS X-Ray Transaction Search so AgentCore Observability can send traces
# to the CloudWatch GenAI Observability Dashboard.
#
# Prerequisite for AgentCore runtimes to show up in:
#   https://console.aws.amazon.com/cloudwatch/home#gen-ai-observability/agent-core
#
# Idempotent — safe to run multiple times.
#
# Usage:
#   export AWS_PROFILE=your-aws-profile
#   ./scripts/enable_agentcore_observability.sh

set -e

export AWS_PROFILE="${AWS_PROFILE:-your-aws-profile}"
export AWS_REGION="${AWS_REGION:-us-east-1}"

echo "🔭 Enabling X-Ray Transaction Search in $AWS_REGION..."

# 1. Transaction Search (spans log group + indexing) — safe to re-apply
aws xray update-trace-segment-destination \
    --destination CloudWatchLogs \
    --region "$AWS_REGION" > /dev/null 2>&1 \
    && echo "  ✅ X-Ray segment destination set to CloudWatchLogs" \
    || echo "  ⚠️  Could not update trace segment destination (may already be set)"

aws xray update-indexing-rule \
    --name Default \
    --rule '{"Probabilistic":{"DesiredSamplingPercentage":100.0}}' \
    --region "$AWS_REGION" > /dev/null 2>&1 \
    && echo "  ✅ X-Ray indexing rule at 100%" \
    || echo "  ⚠️  Could not update indexing rule (may already be 100%)"

echo ""
echo "✅ Observability ready. Next:"
echo "   ./scripts/deploy_agentcore_agents.sh"
echo ""
echo "📊 Dashboard:"
echo "   https://console.aws.amazon.com/cloudwatch/home?region=$AWS_REGION#gen-ai-observability/agent-core"
