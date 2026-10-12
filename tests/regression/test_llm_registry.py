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

# Matches Bedrock model ids, both dated/versioned ones
# (global.anthropic.claude-haiku-4-5-20251001-v1:0) and the newer version-less
# Anthropic ids (global.anthropic.claude-sonnet-5). Without the second branch
# the guard would be blind to a stale version-less literal.
MODEL_ID_RE = re.compile(
    r"\b(?:global\.|us\.|eu\.|apac\.)?(?:"
    r"(?:anthropic|amazon|meta|mistral|cohere)\.[a-z0-9][a-z0-9.-]*-v\d+(?::\d+)?"
    r"|anthropic\.claude-[a-z0-9][a-z0-9.-]*[a-z0-9]"
    r")\b"
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


# ---------------------------------------------------------------------------
# Model contract (MODEL_PROFILES): lot 2 of docs/design/reliability-plan-2026-10.md
# ---------------------------------------------------------------------------
PROFILE_KEYS = {"thinking_off", "accepts_temperature", "default_max_tokens"}

# A `temperature` request knob: dict key with a non-string value
# ("temperature": 0.2 / "temperature": TEMP) or a keyword argument
# (temperature=0.2). The prompt JSON schemas legitimately name a weather
# "temperature" field whose value is a string, and weather code reads
# .get('temperature'): neither matches.
TEMPERATURE_KNOB_RE = re.compile(
    r"""["']temperature["']\s*:\s*(?!["'\s])|\btemperature\s*=(?!=)"""
)
TEMPERATURE_SCAN_DIRS = ["lambda_functions", "src"]


def _code_lines(text: str):
    """Yield (lineno, line) of non-comment lines."""
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        yield lineno, line


class TestModelProfiles:
    def test_profile_mirror_matches_registry(self):
        """The Lambda copy of MODEL_PROFILES must be identical to the registry."""
        assert _mirror().MODEL_PROFILES == _registry().MODEL_PROFILES

    def test_every_default_model_has_a_profile(self):
        """Switching a DEFAULT_* id to a model without a profile must fail here."""
        registry, mirror = _registry(), _mirror()
        for module in (registry, mirror):
            for model_id in (module.DEFAULT_SONNET_MODEL_ID, module.DEFAULT_HAIKU_MODEL_ID):
                assert model_id in module.MODEL_PROFILES, (
                    f"{module.__name__}: {model_id} has no MODEL_PROFILES entry"
                )

    def test_profiles_are_complete_and_typed(self):
        for model_id, profile in _registry().MODEL_PROFILES.items():
            assert set(profile) == PROFILE_KEYS, model_id
            assert isinstance(profile["accepts_temperature"], bool), model_id
            assert isinstance(profile["default_max_tokens"], int), model_id
            assert profile["default_max_tokens"] >= 4096, model_id
            thinking = profile["thinking_off"]
            assert set(thinking) == {"thinking"}, model_id
            assert thinking["thinking"].get("type"), model_id

    def test_no_thinking_reads_the_profile(self):
        mirror = _mirror()
        for model_id, profile in mirror.MODEL_PROFILES.items():
            assert mirror.no_thinking(model_id) == profile["thinking_off"]
        # A copy: a caller mutating the result must not corrupt the profile.
        sonnet = mirror.DEFAULT_SONNET_MODEL_ID
        mirror.no_thinking(sonnet)["thinking"]["type"] = "tampered"
        assert mirror.no_thinking(sonnet) == mirror.MODEL_PROFILES[sonnet]["thinking_off"]

    def test_no_thinking_refuses_unknown_models(self):
        """No substring guessing: an unknown model is an explicit error."""
        mirror = _mirror()
        for model_id in ("anthropic.claude-v2", "global.anthropic.claude-sonnet-9", ""):
            try:
                mirror.no_thinking(model_id)
            except KeyError as exc:
                assert "MODEL_PROFILES" in str(exc)
            else:
                raise AssertionError(f"no_thinking({model_id!r}) should raise")

    def test_temperature_knob_regex(self):
        """Self-test of the guard below, so it cannot silently go blind."""
        hits = [
            'inferenceConfig={"maxTokens": 10, "temperature": 0.2}',
            "inferenceConfig={'temperature': TEMP}",
            "BedrockModel(model_id=MODEL_ID, temperature=0.3)",
        ]
        misses = [
            '"temperature": "number (celsius)",',
            "Temp {fetched_weather.get('temperature')}°C",
            "if temperature == 3:",
        ]
        assert all(TEMPERATURE_KNOB_RE.search(s) for s in hits)
        assert not any(TEMPERATURE_KNOB_RE.search(s) for s in misses)

    def test_no_temperature_sent_to_models_that_reject_it(self):
        """No prod code may send `temperature` to a model whose profile rejects it.

        Code paths pick their model from env overrides, so a call site cannot be
        tied to one model statically: as soon as one registry model rejects
        temperature, any temperature knob in prod code is an offender.
        """
        profiles = _registry().MODEL_PROFILES
        rejecting = sorted(m for m, p in profiles.items() if not p["accepts_temperature"])
        if not rejecting:
            return
        offenders = []
        for scan_dir in TEMPERATURE_SCAN_DIRS:
            for path in (REPO_ROOT / scan_dir).rglob("*"):
                if path.suffix not in {".py", ".json"} or not path.is_file():
                    continue
                if "__pycache__" in path.parts or "fixtures" in path.parts:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for lineno, line in _code_lines(text):
                    if TEMPERATURE_KNOB_RE.search(line):
                        offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
        assert not offenders, (
            f"`temperature` sent while {rejecting} reject it (accepts_temperature=False):\n"
            + "\n".join(offenders)
        )
