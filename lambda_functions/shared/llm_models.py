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
DEFAULT_SONNET_MODEL_ID = "global.anthropic.claude-sonnet-5-5"
DEFAULT_HAIKU_MODEL_ID = "global.anthropic.claude-haiku-5-5"


def resolve_sonnet_model_id() -> str:
    """Main generation model: env override (CDK-injected) or registry default."""
    return os.environ.get("BEDROCK_MODEL_ID", DEFAULT_SONNET_MODEL_ID)


def resolve_haiku_model_id() -> str:
    """Cheap structured-task model: env override or registry default."""
    return os.environ.get("BEDROCK_HAIKU_MODEL_ID", DEFAULT_HAIKU_MODEL_ID)


# Claude 5.5 models think by default and the reasoning counts against maxTokens.
# On short structured tasks (voice script, weekly JSON, set extraction) the whole
# budget went to an empty reasoning block and no text came back (2026-10-09..11:
# "Bedrock returned an empty script", truncated weekly synthesis JSON).
#
# The "off" value differs per model (verified 2026-10-12 against Bedrock):
# Haiku 5.5 accepts {"type": "disabled"} and rejects "between_tools"; Sonnet 5.5
# rejects "disabled" and asks for {"type": "between_tools"} (no thinking before
# answering). Pass the result as Converse `additionalModelRequestFields`, or
# merge it into an InvokeModel body.
def no_thinking(model_id: str) -> dict:
    """Request fields that turn reasoning off for `model_id`."""
    if "sonnet" in model_id or "opus" in model_id:
        return {"thinking": {"type": "between_tools"}}
    return {"thinking": {"type": "disabled"}}


def text_from_converse(response: dict) -> str:
    """Join the text blocks of a Converse response, ignoring reasoning blocks."""
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    return "".join(block.get("text", "") for block in blocks if "text" in block)
