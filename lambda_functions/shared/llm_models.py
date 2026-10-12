"""Bedrock model ID fallbacks for Lambda runtimes.

MIRROR of src/config/llm_config.py (the single source of truth) — this copy
exists only because lambda_functions/ is bundled without src/. The sync test
tests/regression/test_llm_registry.py fails if the two files diverge.

Lambdas resolve their model as: env var (set by CDK from the central
registry) -> these fallbacks. Always go through resolve_*() below; never
hardcode a model ID in a Lambda.
"""

import copy
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


# MIRROR of MODEL_PROFILES in src/config/llm_config.py (see the rationale
# there). Keep the two dicts identical: the sync test compares them.
#
# Claude 5.5 models think by default and the reasoning counts against maxTokens.
# On short structured tasks (voice script, weekly JSON, set extraction) the whole
# budget went to an empty reasoning block and no text came back (2026-10-09..11).
# The "off" value differs per model (Haiku 5.5: "disabled"; Sonnet 5.5:
# "between_tools", verified 2026-10-12), hence a per-model profile rather than
# guessing from the model name.
MODEL_PROFILES = {
    # Keyed by LITERAL ids on purpose: pointing a DEFAULT_* constant at a new
    # model must leave it without a profile until one is written (and smoked).
    "global.anthropic.claude-sonnet-5-5": {
        "thinking_off": {"thinking": {"type": "between_tools"}},
        "accepts_temperature": False,
        "default_max_tokens": 32000,
    },
    "global.anthropic.claude-haiku-5-5": {
        "thinking_off": {"thinking": {"type": "disabled"}},
        "accepts_temperature": False,
        "default_max_tokens": 8192,
    },
}


def model_profile(model_id: str) -> dict:
    """Contract of `model_id`. Raises KeyError for a model without a profile."""
    try:
        return MODEL_PROFILES[model_id]
    except KeyError:
        raise KeyError(
            f"No model profile for {model_id!r}: add it to MODEL_PROFILES in "
            "src/config/llm_config.py and lambda_functions/shared/llm_models.py"
        ) from None


# Pass the result as Converse `additionalModelRequestFields`, or merge it into
# an InvokeModel body. Returns a fresh copy: callers may mutate it.
def no_thinking(model_id: str) -> dict:
    """Request fields that turn reasoning off for `model_id`."""
    return copy.deepcopy(model_profile(model_id)["thinking_off"])


def text_from_converse(response: dict) -> str:
    """Join the text blocks of a Converse response, ignoring reasoning blocks."""
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    return "".join(block.get("text", "") for block in blocks if "text" in block)
