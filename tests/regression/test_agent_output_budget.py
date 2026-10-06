"""Anti-drift: every agent model must carry an explicit output budget.

Strands sends no maxTokens when the model is passed as a bare model-id string,
so the provider default applies. On Sonnet 5 that default truncated the
content_gen output on rich sessions (intervals, strength, Campus match) and the
agent died with "unrecoverable state due to max_tokens limit".
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT_FILES = [
    ROOT / "src" / "agents" / "content_agent.py",
    ROOT / "src" / "agents" / "coach_agent.py",
    ROOT / "src" / "coach_chat" / "coach_chat_agent.py",
]


def test_no_agent_built_from_bare_model_id() -> None:
    """Agent(model=MODEL_ID, ...) would drop max_tokens; wrap it in BedrockModel."""
    for path in AGENT_FILES:
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"Agent\(\s*model\s*=\s*MODEL_ID", source), path.name


def test_budgets_are_large_enough() -> None:
    """Budgets must fit a <thinking> block plus the JSON on the richest session."""
    content = (AGENT_FILES[0]).read_text(encoding="utf-8")
    coach = (AGENT_FILES[1]).read_text(encoding="utf-8")
    assert 'max_tokens=CONTENT_MAX_TOKENS' in content
    assert int(re.search(r'CONTENT_MAX_TOKENS", "(\d+)"', content).group(1)) >= 8192
    assert int(re.search(r'COACH_MAX_TOKENS", "(\d+)"', coach).group(1)) >= 4096
    assert '"maxTokens": 1500' not in coach
    chat = (AGENT_FILES[2]).read_text(encoding="utf-8")
    assert "model = MODEL_ID" not in chat
    assert chat.count("max_tokens=CHAT_MAX_TOKENS") == 2
