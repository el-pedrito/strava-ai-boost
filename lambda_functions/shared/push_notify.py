"""Inter-Lambda "send the push" client -- with NO environment read at import time.

StravaUpdater triggers the notification by invoking StravaAIBoost-PushSend
asynchronously through this helper. Per invariant 8 (a module imported for a pure
function must not require anything from its environment at load time), this module
reads no ``os.environ[...]`` at import: the push target function name is read lazily,
with a safe default, so importing it from StravaUpdater can never raise ``KeyError``.

Best-effort: every error is logged and swallowed -- a missed notification must never
fail the Strava update.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3

from shared.logger import get_logger

logger = get_logger("push_notify")

REGION = os.environ.get("AWS_REGION", "us-east-1")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def notify_activity_enriched(
    user_id: str,
    activity_id: str,
    title: str,
    body: str,
) -> None:
    """Trigger the "activity enriched" notification via an async PushSend invocation.

    Sent at the ``completed`` step of the pipeline, gated by ``PUSH_ENABLED`` and
    deduplicated by the caller. Best-effort: any error is logged, never raised.
    """
    function_name = os.environ.get("PUSH_SEND_FUNCTION", "StravaAIBoost-PushSend")
    payload = {
        "user_id": user_id,
        "activity_id": activity_id,
        "title": title,
        "body": body,
    }
    body_payload = {k: v for k, v in payload.items() if v is not None}
    try:
        boto3.client("lambda", region_name=REGION).invoke(
            FunctionName=function_name,
            InvocationType="Event",  # asynchronous
            Payload=_json_bytes(body_payload),
        )
        logger.info(f"notify_activity_enriched dispatched user={user_id} activity={activity_id}")
    except Exception as exc:  # noqa: BLE001 - best-effort, never propagate
        logger.warning(f"notify_activity_enriched failed (non-blocking): {exc}")
