"""Guard the AgentCore memory id resolution used at CDK synth time.

WHY: .env.agentcore does not carry BEDROCK_AGENTCORE_MEMORY_ID, so
.bedrock_agentcore.yaml is its only source. load_agentcore_memory_id() used to wrap the
whole yaml fallback in ``except Exception: pass``, so a synth environment without PyYAML
returned '' with no error -- and ``cdk deploy`` then blanked the variable on every Lambda
consuming it, silently disabling AgentCore memory in production.

That was reproduced, not imagined: PyYAML was a transitive dependency requirements.txt
never declared, so a deploy venv built to spec (aws-cdk-lib + constructs only) produced
the empty id, and ``cdk diff`` showed FeedbackAnalyzer and WeeklyAudioRecap losing
``content_gen_mem-hnupsb8Lxz``.

The contract these tests pin: '' means "AgentCore is not configured", and is only ever
returned when there is no yaml at all. A yaml that exists but cannot be read must raise,
because shipping '' is indistinguishable from a real value to CloudFormation.
"""

import builtins
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from stacks import env_loader  # noqa: E402


def test_real_repo_resolves_a_non_empty_memory_id():
    """The committed .bedrock_agentcore.yaml must yield the live memory id.

    If this returns '', a deploy from this checkout would blank the variable.
    """
    if not (REPO_ROOT / ".bedrock_agentcore.yaml").exists():
        pytest.skip("no .bedrock_agentcore.yaml in this checkout")
    assert env_loader.load_agentcore_memory_id().startswith("content_gen_mem-")


def test_missing_yaml_returns_empty(monkeypatch, tmp_path):
    """No yaml at all = AgentCore not set up yet. Empty is the honest answer."""
    monkeypatch.setattr(env_loader, "_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(env_loader, "_ENV_FILE", str(tmp_path / ".env.agentcore"))
    assert env_loader.load_agentcore_memory_id() == ""


def test_unimportable_yaml_raises_instead_of_blanking(monkeypatch, tmp_path):
    """The regression: PyYAML absent must fail the synth, not return ''."""
    (tmp_path / ".bedrock_agentcore.yaml").write_text(
        "agents:\n  content_gen:\n    memory:\n      memory_id: content_gen_mem-abc\n"
    )
    monkeypatch.setattr(env_loader, "_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(env_loader, "_ENV_FILE", str(tmp_path / ".env.agentcore"))

    real_import = builtins.__import__

    def _no_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_yaml)
    monkeypatch.delitem(sys.modules, "yaml", raising=False)

    with pytest.raises(RuntimeError, match="PyYAML"):
        env_loader.load_agentcore_memory_id()


def test_unparseable_yaml_raises_instead_of_blanking(monkeypatch, tmp_path):
    (tmp_path / ".bedrock_agentcore.yaml").write_text("agents: [unclosed\n")
    monkeypatch.setattr(env_loader, "_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(env_loader, "_ENV_FILE", str(tmp_path / ".env.agentcore"))
    with pytest.raises(RuntimeError, match="could not read"):
        env_loader.load_agentcore_memory_id()


def test_yaml_without_the_key_returns_empty(monkeypatch, tmp_path):
    """A readable yaml that simply has no id is a legitimate empty, not a failure."""
    (tmp_path / ".bedrock_agentcore.yaml").write_text("agents:\n  content_gen: {}\n")
    monkeypatch.setattr(env_loader, "_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(env_loader, "_ENV_FILE", str(tmp_path / ".env.agentcore"))
    assert env_loader.load_agentcore_memory_id() == ""


def test_null_memory_id_is_treated_as_empty(monkeypatch, tmp_path):
    """The real yaml carries `memory_id: null` for one agent; None must not leak out."""
    (tmp_path / ".bedrock_agentcore.yaml").write_text(
        "agents:\n  content_gen:\n    memory:\n      memory_id: null\n"
    )
    monkeypatch.setattr(env_loader, "_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(env_loader, "_ENV_FILE", str(tmp_path / ".env.agentcore"))
    assert env_loader.load_agentcore_memory_id() == ""


def test_env_file_wins_over_yaml(monkeypatch, tmp_path):
    (tmp_path / ".env.agentcore").write_text("BEDROCK_AGENTCORE_MEMORY_ID=from-env\n")
    (tmp_path / ".bedrock_agentcore.yaml").write_text(
        "agents:\n  content_gen:\n    memory:\n      memory_id: from-yaml\n"
    )
    monkeypatch.setattr(env_loader, "_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(env_loader, "_ENV_FILE", str(tmp_path / ".env.agentcore"))
    assert env_loader.load_agentcore_memory_id() == "from-env"


def test_pyyaml_is_declared_in_requirements():
    """It is needed at synth time, so it cannot stay a transitive dependency."""
    assert "PyYAML" in (REPO_ROOT / "requirements.txt").read_text()
