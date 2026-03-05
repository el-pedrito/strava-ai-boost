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
        'CAMPUS_COACH_AGENT_ARN',
    })


def load_agentcore_memory_id() -> str:
    """Load BEDROCK_AGENTCORE_MEMORY_ID, with .bedrock_agentcore.yaml fallback."""
    env = load_env_agentcore(keys={'BEDROCK_AGENTCORE_MEMORY_ID'})
    memory_id = env.get('BEDROCK_AGENTCORE_MEMORY_ID', '')

    if memory_id:
        return memory_id

    # Fallback: try .bedrock_agentcore.yaml
    yaml_path = os.path.join(_PROJECT_ROOT, '.bedrock_agentcore.yaml')
    if os.path.exists(yaml_path):
        try:
            import yaml
            with open(yaml_path, 'r') as f:
                config = yaml.safe_load(f)
                memory_id = (
                    config.get('agents', {})
                    .get('content_gen', {})
                    .get('memory', {})
                    .get('memory_id', '')
                )
        except Exception:
            pass

    return memory_id
