"""Strava sends "description": null when the athlete wrote none.

Activity 20683904387 (22/10): ``activity_data.get('description', default)`` kept
None, and the prompt log ``validated_description[:150]`` raised
"'NoneType' object is not subscriptable" before the model was ever called, so
no title or description reached Strava. The agent module needs the Strands and
AgentCore runtimes to import, so these checks read its source.
"""
import re
from pathlib import Path

AGENTS = Path(__file__).resolve().parents[2] / "src" / "agents"


def test_no_get_with_default_on_nullable_strava_text_fields():
    # .get(key, default) returns None for a present-but-null key; use `or default`.
    pattern = re.compile(r"\.get\(\s*['\"](name|description)['\"]\s*,")
    offenders = [
        f"{path.name}:{lineno}: {line.strip()}"
        for path in sorted(AGENTS.glob("*.py"))
        for lineno, line in enumerate(path.read_text().splitlines(), 1)
        if pattern.search(line)
    ]
    assert not offenders, "\n".join(offenders)


def test_content_agent_falls_back_on_null_title_and_description():
    text = (AGENTS / "content_agent.py").read_text()
    assert "activity_data.get('name') or 'Untitled'" in text
    assert "activity_data.get('description') or 'No description provided'" in text
    assert "validated_description[:" not in text
