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
) -> bool:
    """Trigger the "activity enriched" notification via an async PushSend invocation.

    Sent at the ``completed`` step of the pipeline, gated by ``PUSH_ENABLED`` and
    deduplicated by the caller. Best-effort: any error is logged, never raised.
    Returns True when the invocation was accepted, so the caller can release its
    dedup marker on failure.
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
        return True
    except Exception as exc:  # noqa: BLE001 - best-effort, never propagate
        logger.warning(f"notify_activity_enriched failed (non-blocking): {exc}")
        return False


# The "how did it feel?" request is sent synchronously: input_wait must know whether a
# device got it (D5: nobody notified -> the run goes on at once). PushSend times out at
# 90 s, so the read timeout sits just above it. total_max_attempts=1 is what prevents a
# read timeout from re-invoking PushSend, which would notify the devices twice.
INPUT_REQUEST_TTL_SECONDS = 3600  # the window lasts 1 h; a later delivery is useless
_input_request_client: Any = None


def _sync_lambda_client() -> Any:
    global _input_request_client
    if _input_request_client is None:
        from botocore.config import Config

        _input_request_client = boto3.client(
            "lambda",
            region_name=REGION,
            config=Config(
                read_timeout=95,
                connect_timeout=5,
                retries={"total_max_attempts": 1},
            ),
        )
    return _input_request_client


class PushRequestError(Exception):
    """The input request could not be handed to PushSend, or its answer is unusable.

    Distinct from a genuine ``sent == 0`` (nobody subscribed, every device gone):
    the caller still fails open, but records ``push_error`` instead of
    ``no_push`` so a broken push path is alarmed rather than counted as normal.
    The message carries no secret (never the payload).
    """


def notify_input_request(
    user_id: str,
    activity_id: str,
    title: str,
    body: str,
    url: str,
) -> int:
    """Ask the athlete for their session feeling; return how many devices got it.

    RequestResponse invocation of PushSend with ``url``, ``tag="input-<id>"`` and
    ``ttl=3600``. Returns PushSend's ``sent`` (0 when nobody was reached). Raises
    ``PushRequestError`` on an invocation error, a function error or a malformed
    answer, so the caller can tell a broken push path from an empty one. Raises
    nothing else.
    """
    function_name = os.environ.get("PUSH_SEND_FUNCTION", "StravaAIBoost-PushSend")
    payload = {
        "user_id": user_id,
        "activity_id": activity_id,
        "title": title,
        "body": body,
        "url": url,
        "tag": f"input-{activity_id}",
        "ttl": INPUT_REQUEST_TTL_SECONDS,
    }
    try:
        response = _sync_lambda_client().invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=_json_bytes(payload),
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed failure
        logger.warning(f"notify_input_request: invoke failed activity={activity_id}: {type(exc).__name__}")
        raise PushRequestError(f"invoke failed: {type(exc).__name__}") from None
    if response.get("FunctionError"):
        logger.warning(f"notify_input_request: PushSend failed activity={activity_id}")
        raise PushRequestError("PushSend function error")
    try:
        result = json.loads(response["Payload"].read() or b"{}")
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed failure
        raise PushRequestError(f"unreadable PushSend answer: {type(exc).__name__}") from None
    sent = result.get("sent") if isinstance(result, dict) else None
    if isinstance(sent, bool) or not isinstance(sent, int) or sent < 0:
        logger.warning(f"notify_input_request: malformed PushSend answer activity={activity_id}")
        raise PushRequestError("malformed PushSend answer")
    logger.info(f"notify_input_request user={user_id} activity={activity_id} sent={sent}")
    return sent
