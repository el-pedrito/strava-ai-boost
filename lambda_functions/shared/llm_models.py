"""Bedrock model ID fallbacks for Lambda runtimes.

MIRROR of src/config/llm_config.py (the single source of truth) — this copy
exists only because lambda_functions/ is bundled without src/. The sync test
tests/regression/test_llm_registry.py fails if the two files diverge.

Lambdas resolve their model as: env var (set by CDK from the central
registry) -> these fallbacks. Always go through resolve_*() below; never
hardcode a model ID in a Lambda.
"""

import os

# Keep in sync with src/config/llm_config.py DEFAULT_* constants.
DEFAULT_SONNET_MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
DEFAULT_HAIKU_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


def resolve_sonnet_model_id() -> str:
    """Main generation model: env override (CDK-injected) or registry default."""
    return os.environ.get("BEDROCK_MODEL_ID", DEFAULT_SONNET_MODEL_ID)


def resolve_haiku_model_id() -> str:
    """Cheap structured-task model: env override or registry default."""
    return os.environ.get("BEDROCK_HAIKU_MODEL_ID", DEFAULT_HAIKU_MODEL_ID)
