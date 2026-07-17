#!/usr/bin/env python3
"""
Configure UserPreferenceStrategy with custom override on AgentCore Memory.

This script updates the existing memory resource to add a UserPreferenceStrategy
that automatically extracts and consolidates user content preferences from
feedback diffs (generated vs user-modified Strava descriptions).

Prerequisites:
- Memory execution role deployed (SecurityStack)
- Memory resource already exists (content_gen_mem)

Usage:
    python scripts/configure_memory_strategy.py
"""

import os
import sys
import json
import yaml
import boto3

# Load config
YAML_PATH = os.path.join(os.path.dirname(__file__), '..', '.bedrock_agentcore.yaml')
REGION = os.environ.get('AWS_REGION', 'eu-west-1')

# Custom extraction prompt for Strava content preferences
EXTRACTION_PROMPT = """\
You are analyzing feedback from a Strava activity content generation system.

The ASSISTANT message contains the AI-generated description for a running/cycling activity.
The USER message contains the version after the user manually edited it on Strava.

Your task: identify the user's content preferences by comparing what was generated vs what the user changed.

Focus on extracting these preference categories:
- LENGTH: Does the user prefer shorter or longer descriptions?
- EXPRESSIONS: Which phrases did the user replace? What style do they prefer?
- EMOJIS: Which emojis were removed or added?
- STRUCTURE: How did the user reorganize the content?
- TONE: Did the user soften, intensify, or change the tone?
- TECHNICAL_DETAIL: Does the user want more or fewer technical metrics?

Only extract significant changes (not typos). Each preference should be actionable for future content generation.
"""

# Custom consolidation prompt
CONSOLIDATION_PROMPT = """\
You are consolidating user preferences for a Strava activity content generation system.

When evaluating new preferences against existing ones:
- If a new preference REINFORCES an existing one (same direction), UPDATE with increased confidence
- If a new preference CONTRADICTS an existing one, consider frequency:
  - If the new pattern has appeared more recently and consistently, UPDATE to reflect the change
  - If it's a one-off deviation, SKIP (the user might have had a specific reason for that edit)
- If a new preference is NOVEL (not seen before), ADD it

Preferences should be concise and actionable. Each preference should directly inform how to generate content.
"""

# P2.3: Use Haiku 4.5 for extraction/consolidation (~4x cheaper than Sonnet).
# The memory strategy prompts are simple classification tasks that don't need Sonnet.
# Override with MEMORY_STRATEGY_MODEL_ID env var if needed.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from config.llm_config import get_haiku_model_id  # noqa: E402

EXTRACTION_MODEL_ID = os.environ.get('MEMORY_STRATEGY_MODEL_ID') or get_haiku_model_id()


def main():
    # Load memory config from YAML
    with open(YAML_PATH, 'r') as f:
        config = yaml.safe_load(f)

    memory_id = config['agents']['content_gen']['memory']['memory_id']
    account_id = config['agents']['content_gen']['aws']['account']

    print(f"Memory ID: {memory_id}")
    print(f"Account ID: {account_id}")
    print(f"Region: {REGION}")

    # Get memory execution role ARN from CloudFormation exports
    cfn = boto3.client('cloudformation', region_name=REGION)
    try:
        exports = cfn.list_exports()
        role_arn = None
        for export in exports['Exports']:
            if export['Name'] == 'StravaAIBoost-MemoryExecutionRoleArn':
                role_arn = export['Value']
                break

        if not role_arn:
            print("ERROR: MemoryExecutionRoleArn not found in CloudFormation exports.")
            print("Deploy the Security stack first: cdk deploy StravaAIBoost-Security")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Could not get CloudFormation exports: {e}")
        sys.exit(1)

    print(f"Memory Execution Role: {role_arn}")

    # Update memory with UserPreferenceStrategy (idempotent)
    agentcore_cp = boto3.client('bedrock-agentcore-control', region_name=REGION)

    # Check if StravaContentPreferences already exists → modify, else add
    existing_id = None
    try:
        mem = agentcore_cp.get_memory(memoryId=memory_id)
        for s in mem.get('memory', {}).get('strategies', []):
            if s.get('name') == 'StravaContentPreferences':
                existing_id = s.get('strategyId') or s.get('id')
                break
    except Exception as e:
        print(f"Warning: could not read existing strategies: {e}")

    try:
        if existing_id:
            print(f"Strategy exists ({existing_id}) — updating modelId to {EXTRACTION_MODEL_ID}")
            strategies = {
                'modifyMemoryStrategies': [
                    {
                        'memoryStrategyId': existing_id,
                        'configuration': {
                            'extraction': {
                                'customExtractionConfiguration': {
                                    'userPreferenceExtractionOverride': {
                                        'appendToPrompt': EXTRACTION_PROMPT,
                                        'modelId': EXTRACTION_MODEL_ID
                                    }
                                }
                            },
                            'consolidation': {
                                'customConsolidationConfiguration': {
                                    'userPreferenceConsolidationOverride': {
                                        'appendToPrompt': CONSOLIDATION_PROMPT,
                                        'modelId': EXTRACTION_MODEL_ID
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        else:
            print(f"Creating StravaContentPreferences strategy with modelId {EXTRACTION_MODEL_ID}")
            strategies = {
                'addMemoryStrategies': [
                    {
                        'customMemoryStrategy': {
                            'name': 'StravaContentPreferences',
                            'namespaces': ['/strategy/StravaContentPreferences/actors/{actorId}/'],
                            'configuration': {
                                'userPreferenceOverride': {
                                    'extraction': {
                                        'appendToPrompt': EXTRACTION_PROMPT,
                                        'modelId': EXTRACTION_MODEL_ID
                                    },
                                    'consolidation': {
                                        'appendToPrompt': CONSOLIDATION_PROMPT,
                                        'modelId': EXTRACTION_MODEL_ID
                                    }
                                }
                            }
                        }
                    }
                ]
            }

        response = agentcore_cp.update_memory(
            memoryId=memory_id,
            memoryExecutionRoleArn=role_arn,
            memoryStrategies=strategies
        )
        print(f"\nMemory updated successfully!")
        print(f"Response: {json.dumps(response.get('ResponseMetadata', {}), indent=2)}")

    except agentcore_cp.exceptions.ResourceNotFoundException:
        print(f"\nERROR: Memory resource {memory_id} not found.")
        print("Create it first via: agentcore memory create")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
