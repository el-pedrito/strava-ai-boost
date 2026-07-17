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
DEFAULT_SONNET_MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
DEFAULT_HAIKU_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"

SONNET_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", DEFAULT_SONNET_MODEL_ID)
HAIKU_MODEL_ID = os.getenv("BEDROCK_HAIKU_MODEL_ID", DEFAULT_HAIKU_MODEL_ID)

# All model IDs the project is allowed to reference (used by the sync test).
ALL_MODEL_IDS = [SONNET_MODEL_ID, HAIKU_MODEL_ID]
DEFAULT_MODEL_IDS = [DEFAULT_SONNET_MODEL_ID, DEFAULT_HAIKU_MODEL_ID]


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
