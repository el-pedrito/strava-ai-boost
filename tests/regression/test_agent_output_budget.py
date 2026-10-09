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
    # 8192 was exhausted by the reasoning alone on 2026-10-08 (15-lap intervals).
    assert int(re.search(r'CONTENT_MAX_TOKENS", "(\d+)"', content).group(1)) >= 32000
    assert int(re.search(r'COACH_MAX_TOKENS", "(\d+)"', coach).group(1)) >= 8192
    assert '"maxTokens": 1500' not in coach
    chat = (AGENT_FILES[2]).read_text(encoding="utf-8")
    assert "model = MODEL_ID" not in chat
    assert chat.count("max_tokens=CHAT_MAX_TOKENS") == 2


def test_content_generator_timeouts_fit_a_generation() -> None:
    """A larger budget means a longer call: the chain around it must keep up.

    On 2026-10-08 botocore's default 60s read_timeout fired mid-generation and
    retried, launching a duplicate agent call; the pair blew the Lambda's 120s.
    The client must wait longer than one generation, never retry on its own, and
    the Lambda must fit the generation plus the handler's one correction retry.
    """
    generator = (ROOT / "lambda_functions" / "processing" / "content_generator.py").read_text(encoding="utf-8")
    read_timeout = int(re.search(r"read_timeout=(\d+)", generator).group(1))
    assert read_timeout >= 240
    assert '"total_max_attempts": 1' in generator
    assert generator.count("config=AGENTCORE_CLIENT_CONFIG") == 2

    stack = (ROOT / "stacks" / "content_generation_stack.py").read_text(encoding="utf-8")
    block = stack.split('"ContentGenerator"', 1)[1].split("lambda_.Function(", 1)[0]
    minutes = int(re.search(r"timeout=Duration\.minutes\((\d+)\)", block).group(1))
    assert minutes * 60 >= 2 * read_timeout


def test_no_temperature_sent_to_claude_5_5() -> None:
    """Claude 5.5 models reject `temperature` ("deprecated for this model").

    One leftover inferenceConfig would turn that call into a ValidationException.
    """
    roots = [ROOT / "lambda_functions", ROOT / "src", ROOT / "tests" / "regression" / "evaluators_managed"]
    # A numeric value only: the prompt JSON schemas legitimately name a
    # "temperature" field (weather, in celsius).
    pattern = re.compile(r"""["']temperature["']\s*:\s*-?\d""")
    offenders = [
        str(p.relative_to(ROOT))
        for root in roots
        for p in root.rglob("*")
        if p.suffix in (".py", ".json") and "fixtures" not in p.parts
        and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
