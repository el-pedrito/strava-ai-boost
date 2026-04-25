#!/bin/bash
# Tag AgentCore resources (runtimes + memories + IAM execution roles)
# for cost allocation tracking in Cost Explorer / CUR 2.0.
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
#
# Prerequisites:
#   - AWS CLI configured (AWS_PROFILE)
#   - python3 + boto3
#   - Agents already deployed via scripts/deploy_agentcore_agents.sh

set -e

AWS_PROFILE="${AWS_PROFILE:-your-aws-profile}"
AWS_REGION="${AWS_REGION:-us-east-1}"
TAGS_PROJECT="${TAGS_PROJECT:-StravaAIBoost}"
TAGS_ENVIRONMENT="${ENVIRONMENT:-dev}"
TAGS_OWNER="${OWNER_TAG:-admin}"
TAGS_COST_CENTER="${TAGS_COST_CENTER:-strava-ai-boost}"
TAGS_MANAGED_BY="${TAGS_MANAGED_BY:-AgentCore-CLI}"

export AWS_PROFILE AWS_REGION

echo "🏷️  Tagging AgentCore resources (region=$AWS_REGION, profile=$AWS_PROFILE)..."

python3 << EOF
import boto3
import os

client = boto3.client('bedrock-agentcore-control', region_name=os.environ['AWS_REGION'])
iam = boto3.client('iam')

base_tags = {
    'Project': '$TAGS_PROJECT',
    'Environment': '$TAGS_ENVIRONMENT',
    'Owner': '$TAGS_OWNER',
    'CostCenter': '$TAGS_COST_CENTER',
    'ManagedBy': '$TAGS_MANAGED_BY',
}

# Runtimes + their IAM execution roles
for rt in client.list_agent_runtimes().get('agentRuntimes', []):
    arn = rt.get('agentRuntimeArn', '')
    name = rt.get('agentRuntimeName', 'unknown')
    try:
        client.tag_resource(resourceArn=arn, tags=base_tags)
        print(f'  ✅ Runtime tagged: {name}')
    except Exception as e:
        print(f'  ❌ Runtime {name}: {e}')
    try:
        details = client.get_agent_runtime(agentRuntimeId=rt.get('agentRuntimeId', ''))
        role_arn = details.get('roleArn', '')
        role_name = role_arn.split('/')[-1] if role_arn else ''
        if role_name:
            role_tags = [{'Key': 'agent', 'Value': name}] + [
                {'Key': k, 'Value': v} for k, v in base_tags.items()
            ]
            iam.tag_role(RoleName=role_name, Tags=role_tags)
            print(f'  ✅ IAM role tagged: {role_name} (agent={name})')
    except Exception as e:
        print(f'  ❌ IAM role for {name}: {e}')

# Memories
for mem in client.list_memories().get('memories', []):
    arn = mem.get('memoryArn', mem.get('arn', ''))
    name = arn.split('/')[-1] if arn else 'unknown'
    try:
        client.tag_resource(resourceArn=arn, tags=base_tags)
        print(f'  ✅ Memory tagged: {name}')
    except Exception as e:
        print(f'  ❌ Memory {name}: {e}')
EOF

echo ""
echo "✅ Done. Next steps (AWS Billing Console, manual):"
echo "   1. Cost Allocation Tags → User-defined → activate: agent, Project, CostCenter"
echo "   2. Wait 24-48h for propagation in Cost Explorer"
echo "   3. (Optional) Create CUR 2.0 export with IAM Principal data for"
echo "      per-agent Bedrock cost attribution."
