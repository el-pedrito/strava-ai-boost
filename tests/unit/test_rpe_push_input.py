"""RPE athlete input: the synchronous push request (docs/design/rpe-athlete-input.md §4).

- ``notify_input_request`` invokes PushSend in RequestResponse with url, tag and
  ttl, on a dedicated client that never retries (a retried read timeout would
  notify the devices twice), and returns ``sent``; any error returns 0.
- PushSend accepts the optional ``tag`` and ``ttl`` fields; an invalid ttl falls
  back to the 24 h default; absent fields keep today's behaviour.
"""

from __future__ import annotations

import io
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))
os.environ.setdefault("PUSH_SUBSCRIPTIONS_TABLE", "test-push-subscriptions")
os.environ.setdefault("VAPID_SECRET", "test-vapid")

from shared import push_notify  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_client():
    push_notify._input_request_client = None
    yield
    push_notify._input_request_client = None


def _response(payload, function_error=None):
    resp = {"StatusCode": 200, "Payload": io.BytesIO(json.dumps(payload).encode())}
    if function_error:
        resp["FunctionError"] = function_error
    return resp


def _call():
    return push_notify.notify_input_request(
        user_id="42", activity_id="777", title="Nouvelle séance",
        body="Ton ressenti ?", url="/activities/777/feedback",
    )


@patch("shared.push_notify.boto3")
def test_request_response_with_url_tag_ttl(mock_boto3, monkeypatch):
    monkeypatch.setenv("PUSH_SEND_FUNCTION", "StravaAIBoost-PushSend")
    client = MagicMock()
    client.invoke.return_value = _response({"statusCode": 200, "sent": 2})
    mock_boto3.client.return_value = client

    assert _call() == 2

    kwargs = client.invoke.call_args.kwargs
    assert kwargs["FunctionName"] == "StravaAIBoost-PushSend"
    assert kwargs["InvocationType"] == "RequestResponse"
    payload = json.loads(kwargs["Payload"])
    assert payload["url"] == "/activities/777/feedback"
    assert payload["tag"] == "input-777"
    assert payload["ttl"] == 3600
    assert payload["user_id"] == "42"
    assert payload["activity_id"] == "777"


@patch("shared.push_notify.boto3")
def test_dedicated_client_never_retries(mock_boto3):
    client = MagicMock()
    client.invoke.return_value = _response({"sent": 1})
    mock_boto3.client.return_value = client
    _call()
    config = mock_boto3.client.call_args.kwargs["config"]
    assert config.read_timeout == 95
    assert config.connect_timeout == 5
    assert config.retries == {"total_max_attempts": 1}


@patch("shared.push_notify.boto3")
def test_read_timeout_invokes_push_send_once_and_returns_zero(mock_boto3):
    from botocore.exceptions import ReadTimeoutError

    client = MagicMock()
    client.invoke.side_effect = ReadTimeoutError(endpoint_url="https://lambda")
    mock_boto3.client.return_value = client
    assert _call() == 0
    assert client.invoke.call_count == 1


@patch("shared.push_notify.boto3")
def test_function_error_returns_zero(mock_boto3):
    client = MagicMock()
    client.invoke.return_value = _response({"errorMessage": "boom"}, function_error="Unhandled")
    mock_boto3.client.return_value = client
    assert _call() == 0


@patch("shared.push_notify.boto3")
def test_zero_sent_returns_zero(mock_boto3):
    client = MagicMock()
    client.invoke.return_value = _response({"statusCode": 200, "sent": 0})
    mock_boto3.client.return_value = client
    assert _call() == 0


@patch("shared.push_notify.boto3")
def test_malformed_sent_returns_zero(mock_boto3):
    client = MagicMock()
    client.invoke.return_value = _response({"sent": True})
    mock_boto3.client.return_value = client
    assert _call() == 0


@patch("shared.push_notify.boto3")
def test_non_json_payload_returns_zero(mock_boto3):
    client = MagicMock()
    client.invoke.return_value = {"StatusCode": 200, "Payload": io.BytesIO(b"not json")}
    mock_boto3.client.return_value = client
    assert _call() == 0


@patch("shared.push_notify.boto3")
def test_async_enriched_helper_unchanged(mock_boto3):
    """The existing async helper keeps its Event invocation (flag-off behaviour)."""
    client = MagicMock()
    mock_boto3.client.return_value = client
    push_notify.notify_activity_enriched(user_id="42", activity_id="777", title="T", body="B")
    assert client.invoke.call_args.kwargs["InvocationType"] == "Event"


# --------------------------------------------------------------------------- PushSend


def _send_module():
    import push.push_send as send

    return send


def _sub():
    return {"endpoint": "https://web.push.apple.com/ep", "p256dh": "k", "auth": "a", "endpoint_hash": "h"}


def _run_send(monkeypatch, event):
    send = _send_module()
    calls = []

    def fake_send_push(subscription, payload, **kwargs):
        calls.append((payload, kwargs))

    monkeypatch.setattr(send, "_subscriptions", lambda _u: [_sub()])
    monkeypatch.setattr(send, "_record_delivery", lambda **_k: None)
    monkeypatch.setattr(send, "send_push", fake_send_push)
    result = send.handler(event, None)
    return result, calls


def test_push_send_passes_tag_url_and_ttl(monkeypatch):
    result, calls = _run_send(monkeypatch, {
        "user_id": "42", "activity_id": "777", "url": "/activities/777/feedback",
        "tag": "input-777", "ttl": 3600,
    })
    assert result["sent"] == 1
    payload, kwargs = calls[0]
    assert payload["url"] == "/activities/777/feedback"
    assert payload["tag"] == "input-777"
    assert kwargs == {"ttl": 3600}


def test_push_send_without_ttl_keeps_default(monkeypatch):
    _, calls = _run_send(monkeypatch, {"user_id": "42", "activity_id": "777"})
    payload, kwargs = calls[0]
    assert kwargs == {}
    assert payload["tag"] == "activity-777"


def test_push_send_ignores_out_of_range_ttl(monkeypatch):
    _, calls = _run_send(monkeypatch, {"user_id": "42", "activity_id": "777", "ttl": 10 ** 9})
    assert calls[0][1] == {}


def test_push_send_ignores_bool_or_text_ttl(monkeypatch):
    _, calls_bool = _run_send(monkeypatch, {"user_id": "42", "activity_id": "777", "ttl": True})
    _, calls_text = _run_send(monkeypatch, {"user_id": "42", "activity_id": "777", "ttl": "3600"})
    assert calls_bool[0][1] == {}
    assert calls_text[0][1] == {}


def _fake_webpush(monkeypatch):
    import push.webpush_core as core

    captured = {}
    fake_module = MagicMock()
    fake_module.WebPushException = type("WebPushException", (Exception,), {})
    fake_module.webpush = lambda **kwargs: captured.update(kwargs)
    monkeypatch.setitem(sys.modules, "pywebpush", fake_module)
    monkeypatch.setattr(core, "_load_vapid", lambda: {"private_key": "x"})
    monkeypatch.setattr(core, "vapid_subject", lambda: "mailto:a@b.c")
    monkeypatch.setattr(core, "_no_redirect_session", lambda: MagicMock())
    return core, captured


def test_send_push_forwards_ttl_to_webpush(monkeypatch):
    core, captured = _fake_webpush(monkeypatch)
    core.send_push({"endpoint": "https://web.push.apple.com/ep", "keys": {}}, {"title": "t"}, ttl=3600)
    assert captured["ttl"] == 3600


def test_send_push_default_ttl_is_unchanged(monkeypatch):
    core, captured = _fake_webpush(monkeypatch)
    core.send_push({"endpoint": "https://web.push.apple.com/ep", "keys": {}}, {"title": "t"})
    assert captured["ttl"] == core.PUSH_TTL_SECONDS
