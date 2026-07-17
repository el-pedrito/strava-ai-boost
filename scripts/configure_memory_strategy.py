#!/usr/bin/env python3
"""
Configure the AgentCore Memory strategies (idempotent).

Manages the strategies on content_gen_mem:
1. StravaContentPreferences (CUSTOM/userPreference): extraction/consolidation of
   content preferences from feedback diffs. Ensures its namespace follows the
   unified '/strategies/{memoryStrategyId}/actors/{actorId}/' convention
   (was '/strategy/<name>/...' singular — see docs/design/memory-improvements.md
   piste 5) and migrates existing records to the new namespace.
2. CoachingEpisodes (EPISODIC): episodes per actor + periodic reflections
   (consolidated insights) — piste 1. Namespaces aligned on the unified
   '/strategies/' prefix so all prefix-based readers (coach, recap, chat tool)
   see episodes and reflections without code changes.

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

# Unified namespace convention for every strategy (see memory-improvements.md).
UNIFIED_NAMESPACE_TEMPLATE = '/strategies/{memoryStrategyId}/actors/{actorId}/'
LEGACY_PREFS_NAMESPACE_PREFIX = '/strategy/StravaContentPreferences/actors/'

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

    agentcore_cp = boto3.client('bedrock-agentcore-control', region_name=REGION)
    agentcore_dp = boto3.client('bedrock-agentcore', region_name=REGION)

    mem = agentcore_cp.get_memory(memoryId=memory_id).get('memory', {})
    strategies_by_name = {
        s.get('name'): s for s in mem.get('strategies', [])
    }

    _ensure_preferences_strategy(agentcore_cp, memory_id, role_arn, strategies_by_name)
    _migrate_legacy_preference_records(agentcore_dp, agentcore_cp, memory_id, strategies_by_name)
    _ensure_episodic_strategy(agentcore_cp, memory_id, role_arn, strategies_by_name)
    print("\nDone.")


def _strategy_id(strategy: dict) -> str:
    return strategy.get('strategyId') or strategy.get('memoryStrategyId') or strategy.get('id') or ''


def _ensure_preferences_strategy(cp, memory_id: str, role_arn: str, strategies_by_name: dict) -> None:
    """Create or update StravaContentPreferences with the unified namespace."""
    existing = strategies_by_name.get('StravaContentPreferences')
    try:
        if existing:
            sid = _strategy_id(existing)
            namespaces = existing.get('namespaces') or []
            needs_ns_fix = any(ns.startswith(LEGACY_PREFS_NAMESPACE_PREFIX) for ns in namespaces)
            modify = {
                'memoryStrategyId': sid,
                'configuration': {
                    'extraction': {'customExtractionConfiguration': {
                        'userPreferenceExtractionOverride': {
                            'appendToPrompt': EXTRACTION_PROMPT, 'modelId': EXTRACTION_MODEL_ID}}},
                    'consolidation': {'customConsolidationConfiguration': {
                        'userPreferenceConsolidationOverride': {
                            'appendToPrompt': CONSOLIDATION_PROMPT, 'modelId': EXTRACTION_MODEL_ID}}},
                },
            }
            if needs_ns_fix:
                modify['namespaceTemplates'] = [UNIFIED_NAMESPACE_TEMPLATE]
                print(f"StravaContentPreferences ({sid}): unifying namespace -> {UNIFIED_NAMESPACE_TEMPLATE}")
            else:
                print(f"StravaContentPreferences ({sid}): namespace already unified, refreshing prompts/model")
            cp.update_memory(memoryId=memory_id, memoryExecutionRoleArn=role_arn,
                             memoryStrategies={'modifyMemoryStrategies': [modify]})
        else:
            print("Creating StravaContentPreferences strategy (unified namespace)")
            cp.update_memory(memoryId=memory_id, memoryExecutionRoleArn=role_arn, memoryStrategies={
                'addMemoryStrategies': [{'customMemoryStrategy': {
                    'name': 'StravaContentPreferences',
                    'namespaceTemplates': [UNIFIED_NAMESPACE_TEMPLATE],
                    'configuration': {'userPreferenceOverride': {
                        'extraction': {'appendToPrompt': EXTRACTION_PROMPT, 'modelId': EXTRACTION_MODEL_ID},
                        'consolidation': {'appendToPrompt': CONSOLIDATION_PROMPT, 'modelId': EXTRACTION_MODEL_ID},
                    }},
                }}]})
        print("  preferences strategy OK")
    except Exception as e:
        print(f"ERROR (preferences strategy): {e}")
        sys.exit(1)


def _migrate_legacy_preference_records(dp, cp, memory_id: str, strategies_by_name: dict) -> None:
    """Copy records from the legacy '/strategy/...' namespace to the unified one.

    Copy-then-delete, verified: originals are only deleted after the copy of
    the SAME record succeeded. Idempotent via requestIdentifier=memoryRecordId.
    """
    existing = strategies_by_name.get('StravaContentPreferences')
    if not existing:
        return
    sid = _strategy_id(existing)
    new_ns_prefix = f"/strategies/{sid}/actors/"

    migrated = 0
    token = None
    while True:
        kwargs = {'memoryId': memory_id, 'namespace': LEGACY_PREFS_NAMESPACE_PREFIX, 'maxResults': 50}
        if token:
            kwargs['nextToken'] = token
        try:
            resp = dp.list_memory_records(**kwargs)
        except Exception as e:
            print(f"  migration: could not list legacy records ({e}) — skipping")
            return
        records = resp.get('memoryRecordSummaries', [])
        for rec in records:
            old_ns = (rec.get('namespaces') or [''])[0]
            actor = old_ns[len(LEGACY_PREFS_NAMESPACE_PREFIX):].strip('/')
            if not actor:
                continue
            new_ns = f"{new_ns_prefix}{actor}/"
            text = rec.get('content', {}).get('text', '')
            if not text:
                continue
            try:
                created = dp.batch_create_memory_records(memoryId=memory_id, records=[{
                    'requestIdentifier': rec['memoryRecordId'][:80],
                    'namespaces': [new_ns],
                    'content': {'text': text},
                    'timestamp': rec.get('createdAt'),
                    'memoryStrategyId': sid,
                }])
                if created.get('failedRecords'):
                    print(f"  migration: record {rec['memoryRecordId']} copy FAILED in-band "
                          f"({created['failedRecords'][0].get('errorMessage', '?')}) — original kept")
                    continue
                dp.delete_memory_record(memoryId=memory_id, memoryRecordId=rec['memoryRecordId'])
                migrated += 1
            except Exception as e:
                print(f"  migration: record {rec['memoryRecordId']} failed ({e}) — original kept")
        token = resp.get('nextToken')
        if not token:
            break
    print(f"  migrated {migrated} legacy preference record(s) -> {new_ns_prefix}...")


def _ensure_episodic_strategy(cp, memory_id: str, role_arn: str, strategies_by_name: dict) -> None:
    """Add the EPISODIC strategy (episodes + actor-level reflections)."""
    if 'CoachingEpisodes' in strategies_by_name:
        print(f"CoachingEpisodes: already exists ({_strategy_id(strategies_by_name['CoachingEpisodes'])})")
        return
    print("Creating CoachingEpisodes EPISODIC strategy (episodes + actor-level reflections)")
    try:
        cp.update_memory(memoryId=memory_id, memoryExecutionRoleArn=role_arn, memoryStrategies={
            'addMemoryStrategies': [{'episodicMemoryStrategy': {
                'name': 'CoachingEpisodes',
                'description': 'Per-session training episodes consolidated into periodic actor-level reflections (progression, patterns).',
                'namespaceTemplates': [UNIFIED_NAMESPACE_TEMPLATE],
                # Reflections at ACTOR level (not cross-actor: privacy note in AWS docs).
                'reflectionConfiguration': {'namespaceTemplates': [UNIFIED_NAMESPACE_TEMPLATE]},
            }}]})
        print("  episodic strategy created")
    except Exception as e:
        print(f"ERROR (episodic strategy): {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
