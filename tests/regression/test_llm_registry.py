"""Anti-drift guard for the central Bedrock model registry.

Every Bedrock model-ID literal in production code must belong to the central
registry (src/config/llm_config.py). The Lambda-side mirror
(lambda_functions/shared/llm_models.py) must stay identical to the registry.
If you change a model: edit the registry + mirror, and this test will point
at any file still referencing the old ID.
"""

import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories containing production code to scan.
SCAN_DIRS = ["lambda_functions", "src", "stacks", "scripts", "tests/regression/evaluators_managed"]
SCAN_SUFFIXES = {".py", ".sh", ".json", ".yaml", ".yml"}

# Matches Bedrock model ids like global.anthropic.claude-sonnet-4-5-20250929-v1:0
MODEL_ID_RE = re.compile(
    r"\b(?:global\.|us\.|eu\.|apac\.)?(?:anthropic|amazon|meta|mistral|cohere)\."
    r"[a-z0-9][a-z0-9.-]*-v\d+(?::\d+)?\b"
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _registry():
    return _load_module(REPO_ROOT / "src" / "config" / "llm_config.py", "central_llm_config")


def _mirror():
    return _load_module(
        REPO_ROOT / "lambda_functions" / "shared" / "llm_models.py", "lambda_llm_models"
    )


class TestLLMRegistry:
    def test_mirror_matches_registry(self):
        """The Lambda mirror must be byte-identical to the registry defaults."""
        registry, mirror = _registry(), _mirror()
        assert mirror.DEFAULT_SONNET_MODEL_ID == registry.DEFAULT_SONNET_MODEL_ID
        assert mirror.DEFAULT_HAIKU_MODEL_ID == registry.DEFAULT_HAIKU_MODEL_ID

    def test_registry_uses_global_inference_profiles(self):
        """Project convention: cross-region `global.` profiles only."""
        registry = _registry()
        for model_id in registry.DEFAULT_MODEL_IDS:
            assert model_id.startswith("global."), model_id

    def test_no_stray_model_ids_in_prod_code(self):
        """Every model-id literal in prod code must belong to the registry."""
        registry = _registry()
        allowed = set(registry.DEFAULT_MODEL_IDS)
        # Foundation-model variants (prefix stripped) appear legitimately in IAM docs.
        allowed |= {registry._foundation_model_id(m) for m in registry.DEFAULT_MODEL_IDS}

        offenders = []
        for scan_dir in SCAN_DIRS:
            base = REPO_ROOT / scan_dir
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.suffix not in SCAN_SUFFIXES or not path.is_file():
                    continue
                if "__pycache__" in path.parts or path.name.startswith("."):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for match in MODEL_ID_RE.finditer(text):
                    model_id = match.group(0)
                    if model_id not in allowed:
                        offenders.append(f"{path.relative_to(REPO_ROOT)}: {model_id}")

        assert not offenders, (
            "Model IDs outside the central registry (src/config/llm_config.py):\n"
            + "\n".join(sorted(set(offenders)))
        )
