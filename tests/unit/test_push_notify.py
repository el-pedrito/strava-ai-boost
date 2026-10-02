"""Unit tests for the inter-Lambda push client (shared.push_notify).

Best-effort async invocation of StravaAIBoost-PushSend:
- dispatches an Event invocation with the expected payload;
- never raises when the invoke fails.
"""

import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared import push_notify  # noqa: E402


@patch("shared.push_notify.boto3")
def test_dispatches_async_invoke(mock_boto3: MagicMock, monkeypatch) -> None:
    monkeypatch.setenv("PUSH_SEND_FUNCTION", "StravaAIBoost-PushSend")
    client = MagicMock()
    mock_boto3.client.return_value = client

    push_notify.notify_activity_enriched(
        user_id="12345678", activity_id="act1", title="Activité enrichie", body="Bravo."
    )

    client.invoke.assert_called_once()
    kwargs = client.invoke.call_args.kwargs
    assert kwargs["FunctionName"] == "StravaAIBoost-PushSend"
    assert kwargs["InvocationType"] == "Event"


@patch("shared.push_notify.boto3")
def test_never_raises_on_invoke_error(mock_boto3: MagicMock) -> None:
    client = MagicMock()

    def _boom(*_a: Any, **_k: Any):
        raise RuntimeError("boom")

    client.invoke.side_effect = _boom
    mock_boto3.client.return_value = client

    # Must not raise.
    push_notify.notify_activity_enriched(
        user_id="12345678", activity_id="act1", title="T", body="B"
    )
