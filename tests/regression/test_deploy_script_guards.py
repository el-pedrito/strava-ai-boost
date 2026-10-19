"""Guards in scripts/deploy.sh that keep a deploy from blanking live Lambda env vars.

Incident 19/10: a deploy run from a git worktree (no cdk.context.json, no
.env.agentcore) synthesised fine and blanked COACH_AGENT_ARN,
CONTENT_GENERATION_AGENT_ARN, CAMPUS_OWNER_STRAVA_ID... on 11 Lambdas.
"""
import json
import re
import subprocess
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / "scripts" / "deploy.sh"


def _preflight_block() -> str:
    text = DEPLOY.read_text()
    match = re.search(r"^# Config preflight.*?(?=^# Always verify AWS credentials)", text, re.S | re.M)
    assert match, "config preflight block missing from deploy.sh"
    return match.group(0)


def _run_preflight(cwd: Path) -> subprocess.CompletedProcess:
    script = (
        'print_error(){ echo "ERR $*"; }; print_status(){ echo "OK $*"; }\n'
        "FIRST_DEPLOYMENT=false\n" + _preflight_block()
    )
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


def _write_config(root: Path, owner: str = "123", coach_arn: str = "arn:coach") -> None:
    (root / "cdk.context.json").write_text(json.dumps({"default_user_id": owner}))
    (root / ".bedrock_agentcore.yaml").write_text("agents: {}\n")
    (root / ".env.agentcore").write_text(
        "CONTENT_GENERATION_AGENT_ARN=arn:content\n"
        f"COACH_AGENT_ARN={coach_arn}\n"
        "CAMPUS_COACH_AGENT_ARN=arn:campus\n"
    )


def test_synth_failure_aborts_the_deploy():
    text = DEPLOY.read_text()
    assert "continuing with deployment" not in text
    synth_else = re.search(r"if cdk synth .*?\n\s*else\n(.*?)\n\s*fi", text, re.S)
    assert synth_else and "exit 1" in synth_else.group(1)


def test_preflight_refuses_a_checkout_without_config(tmp_path):
    result = _run_preflight(tmp_path)
    assert result.returncode == 1
    for name in ("cdk.context.json", ".env.agentcore", ".bedrock_agentcore.yaml"):
        assert name in result.stdout


def test_preflight_refuses_empty_owner_or_agent_arn(tmp_path):
    _write_config(tmp_path, owner="", coach_arn="")
    result = _run_preflight(tmp_path)
    assert result.returncode == 1
    assert "default_user_id empty" in result.stdout
    assert "COACH_AGENT_ARN empty" in result.stdout


def test_preflight_passes_with_complete_config(tmp_path):
    _write_config(tmp_path)
    result = _run_preflight(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "preflight passed" in result.stdout
