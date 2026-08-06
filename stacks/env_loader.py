"""
Shared loader for .env.agentcore configuration.

Eliminates duplication across api_gateway_stack, content_generation_stack,
and feedback_loop_stack.
"""

import os
from typing import Dict, Optional, Set


_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..')
_ENV_FILE = os.path.join(_PROJECT_ROOT, '.env.agentcore')


def load_env_agentcore(keys: Optional[Set[str]] = None) -> Dict[str, str]:
    """
    Load variables from .env.agentcore file.

    Args:
        keys: If provided, only load these keys. Otherwise load all.

    Returns:
        Dictionary of loaded key-value pairs.
    """
    result: Dict[str, str] = {}

    if not os.path.exists(_ENV_FILE):
        return result

    with open(_ENV_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            if keys is None or key in keys:
                result[key] = value

    return result


def load_agentcore_agent_arns() -> Dict[str, str]:
    """Load agent ARNs for IAM scoping and Lambda environment."""
    return load_env_agentcore(keys={
        'CONTENT_GENERATION_AGENT_ARN',
    })


def load_agentcore_memory_id() -> str:
    """Load BEDROCK_AGENTCORE_MEMORY_ID, with .bedrock_agentcore.yaml fallback.

    Returns '' ONLY when AgentCore is genuinely not configured (no yaml on disk).
    Raises RuntimeError when the yaml exists but cannot be read.

    WHY it raises instead of returning '': .env.agentcore does not carry the memory id,
    so the yaml is its only source. The previous version wrapped the whole fallback in
    `except Exception: pass`, so a synth environment without PyYAML silently produced an
    empty id -- and `cdk deploy` then blanked BEDROCK_AGENTCORE_MEMORY_ID on every Lambda
    consuming it, disabling AgentCore memory in production with no error anywhere.

    This was not hypothetical: PyYAML is a transitive dependency that requirements.txt did
    not declare, so a deploy venv built to spec (aws-cdk-lib + constructs) reproduced it,
    and `cdk diff` showed FeedbackAnalyzer and WeeklyAudioRecap losing their memory id.
    Same principle as the rest of this project: a plausible wrong value is worse than a
    loud gap, so an unreadable-but-present config fails the synth rather than shipping ''.
    """
    env = load_env_agentcore(keys={'BEDROCK_AGENTCORE_MEMORY_ID'})
    memory_id = env.get('BEDROCK_AGENTCORE_MEMORY_ID', '')

    if memory_id:
        return memory_id

    yaml_path = os.path.join(_PROJECT_ROOT, '.bedrock_agentcore.yaml')
    if not os.path.exists(yaml_path):
        # AgentCore not set up yet (pre-bootstrap): an empty id is the honest answer.
        return ''

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on the synth environment
        raise RuntimeError(
            f"{yaml_path} holds the AgentCore memory id but PyYAML is not importable in "
            "this synth environment. Returning an empty id would blank "
            "BEDROCK_AGENTCORE_MEMORY_ID on every Lambda that consumes it and silently "
            "disable AgentCore memory. Install requirements.txt into the venv running cdk."
        ) from exc

    try:
        with open(yaml_path, 'r') as f:
            config = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError(
            f"could not read the AgentCore memory id from {yaml_path}: {exc}. Refusing to "
            "synth with an empty id, which would blank it on the deployed Lambdas."
        ) from exc

    return (
        ((config.get('agents') or {}).get('content_gen') or {}).get('memory') or {}
    ).get('memory_id') or ''
