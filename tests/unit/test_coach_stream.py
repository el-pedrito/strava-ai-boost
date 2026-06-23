"""Unit tests for the coach streaming app — AG-UI SSE event generation."""

import asyncio
import json
import os
import sys

import pytest  # noqa: F401  (fixtures use pytest)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))


def _collect(agen):
    """Drain an async generator into a list (sync wrapper for tests)."""

    async def _run():
        return [item async for item in agen]

    return asyncio.run(_run())


@pytest.fixture
def stream_module(monkeypatch):
    """Import coach_stream.app with context builders + bedrock mocked out."""
    from coach_stream import app as mod

    monkeypatch.setattr(mod, "build_user_context", lambda uid: ["Profil: test"])
    monkeypatch.setattr(mod, "retrieve_memory_observations", lambda uid: "")
    monkeypatch.setattr(mod, "write_chat_to_memory", lambda *a, **k: None)
    return mod


def _fake_bedrock(deltas):
    """A boto3-like client whose converse_stream yields the given text deltas."""

    class _Client:
        def converse_stream(self, **kwargs):
            stream = [
                {"contentBlockDelta": {"delta": {"text": d}}} for d in deltas
            ]
            return {"stream": stream}

    return _Client()


def test_event_stream_emits_agui_sequence(stream_module, monkeypatch):
    monkeypatch.setattr(
        stream_module.boto3, "client", lambda *a, **k: _fake_bedrock(["Salut", " champion"])
    )

    frames = _collect(
        stream_module._event_stream("Comment je progresse ?", "user1", "msg1")
    )
    events = [json.loads(f.removeprefix("data: ").strip()) for f in frames]
    types = [e["type"] for e in events]

    assert types[0] == "RUN_STARTED"
    assert "TEXT_MESSAGE_START" in types
    assert types[-1] == "RUN_FINISHED"
    deltas = [e["delta"] for e in events if e["type"] == "TEXT_MESSAGE_CONTENT"]
    assert "".join(deltas) == "Salut champion"


def test_event_stream_emits_run_error_on_failure(stream_module, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("bedrock down")

    monkeypatch.setattr(stream_module.boto3, "client", _boom)

    frames = _collect(stream_module._event_stream("q", "user1", "msg1"))
    events = [json.loads(f.removeprefix("data: ").strip()) for f in frames]
    types = [e["type"] for e in events]

    assert types[0] == "RUN_STARTED"
    assert types[-1] == "RUN_ERROR"


def test_sse_frame_format(stream_module):
    frame = stream_module._sse("TEXT_MESSAGE_CONTENT", {"delta": "héllo"})
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    parsed = json.loads(frame.removeprefix("data: ").strip())
    assert parsed == {"type": "TEXT_MESSAGE_CONTENT", "delta": "héllo"}
