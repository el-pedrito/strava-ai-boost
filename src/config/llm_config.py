"""Central Bedrock model registry for Strava AI Boost.

SINGLE SOURCE OF TRUTH for every model ID in the project. To change a model,
edit the two constants below (or set the env vars) — CDK stacks, deploy
scripts, and managed evaluator configs all read from here. Lambda runtime
fallbacks live in lambda_functions/shared/llm_models.py (bundled separately)
and MUST mirror these values; the sync test in
tests/regression/test_llm_registry.py enforces it.

Roles:
- SONNET: main generation (content agent, coach agent, coach chat,
  weekly synthesis, weekly audio recap script).
- HAIKU: cheap structured/short tasks (voice debrief script, strength-set
  extraction, memory preference extraction, LLM-as-a-Judge evaluators).

The `global.` prefix is the cross-region inference profile — the deliberate
choice everywhere (do not reintroduce `us.` variants).
"""

import os

# ---------------------------------------------------------------------------
# The registry. Change models HERE. (Env vars override at deploy/run time.)
# ---------------------------------------------------------------------------
DEFAULT_SONNET_MODEL_ID = "global.anthropic.claude-sonnet-5-5"
DEFAULT_HAIKU_MODEL_ID = "global.anthropic.claude-haiku-5-5"

SONNET_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", DEFAULT_SONNET_MODEL_ID)
HAIKU_MODEL_ID = os.getenv("BEDROCK_HAIKU_MODEL_ID", DEFAULT_HAIKU_MODEL_ID)

# All model IDs the project is allowed to reference (used by the sync test).
ALL_MODEL_IDS = [SONNET_MODEL_ID, HAIKU_MODEL_ID]
DEFAULT_MODEL_IDS = [DEFAULT_SONNET_MODEL_ID, DEFAULT_HAIKU_MODEL_ID]

# ---------------------------------------------------------------------------
# Model contract: the request knobs that differ per model. Every model the
# project can call MUST have a profile here (enforced by
# tests/regression/test_llm_registry.py) and the live behaviour is checked by
# scripts/smoke_models.py. Mirrored in lambda_functions/shared/llm_models.py.
#
# - thinking_off: request fields that turn reasoning off (Converse
#   `additionalModelRequestFields`, or merged into an InvokeModel body).
#   Verified 2026-10-12 on Bedrock: Haiku 5.5 accepts {"type": "disabled"} and
#   rejects "between_tools"; Sonnet 5.5 rejects "disabled" and requires
#   {"type": "between_tools"} (no thinking before answering).
# - accepts_temperature: both 5.5 models reject `temperature`
#   ("deprecated for this model") -> a ValidationException.
# - default_max_tokens: budget for a call with reasoning ON. Claude 5.5 reasons
#   by default and the reasoning consumes maxTokens (600 -> empty text), so this
#   is the floor for any call that does not send thinking_off. Sonnet matches
#   the content agent budget (CONTENT_MAX_TOKENS), Haiku the coach/chat one.
# ---------------------------------------------------------------------------
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
            "src/config/llm_config.py (and its mirror lambda_functions/shared/llm_models.py), "
            "then run scripts/smoke_models.py"
        ) from None


def _foundation_model_id(model_id: str) -> str:
    """Strip the inference-profile prefix (global./us./eu.) for IAM ARNs."""
    for prefix in ("global.", "us.", "eu.", "apac."):
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


def iam_resources_for(model_id: str, region: str = "*", account: str = "*") -> list:
    """IAM resource ARNs required to invoke a model via its inference profile.

    Invoking a cross-region profile requires BOTH the inference-profile ARN
    and the underlying foundation-model ARN (any region).
    """
    return [
        f"arn:aws:bedrock:{region}:{account}:inference-profile/{model_id}",
        f"arn:aws:bedrock:*::foundation-model/{_foundation_model_id(model_id)}",
    ]


def all_iam_resources(region: str = "*", account: str = "*") -> list:
    """IAM resources for every registry model (for shared Lambda roles)."""
    resources: list = []
    for model_id in ALL_MODEL_IDS:
        for arn in iam_resources_for(model_id, region, account):
            if arn not in resources:
                resources.append(arn)
    return resources


# ---------------------------------------------------------------------------
# Backward-compatible helpers (existing stack imports).
# ---------------------------------------------------------------------------
def get_bedrock_model_id() -> str:
    """Main generation model ID (Sonnet)."""
    return SONNET_MODEL_ID


def get_haiku_model_id() -> str:
    """Cheap structured-task model ID (Haiku)."""
    return HAIKU_MODEL_ID
