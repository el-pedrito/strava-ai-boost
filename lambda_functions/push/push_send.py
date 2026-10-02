"""Push send Lambda (StravaAIBoost-PushSend).

Invoked asynchronously after a Strava activity has been successfully updated, to send
the single opt-in v1 notification ("your enriched description is live"). The click
opens the activity route that exists in the frontend (``/activities/:id``).

Expected event (direct, asynchronous invocation):
    { "user_id": "...", "activity_id": "...",
      "title": "...", "body": "...", "url"?: "/...", "tag"?: "..." }

For each of the user's subscriptions the encrypted notification is sent; an expired
endpoint (404/410) is deleted from the table (410 cleanup). One failing subscription
never blocks the others. No health data or metric is placed in the payload.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from push.webpush_core import PushExpired, send_push
from shared.logger import get_logger, inject_correlation_id

logger = get_logger("push_send")

REGION = os.environ.get("AWS_REGION", "us-east-1")

_dynamodb: Any = boto3.resource("dynamodb", region_name=REGION)

# Neutral user-facing defaults, in the app's language (French, like the coach output).
DEFAULT_TITLE = "Activité enrichie"
DEFAULT_BODY = "Ta description enrichie est en ligne."


def _table() -> Any:
    # Read at call time, not at import: this module must stay importable in a runtime
    # that does not define PUSH_SUBSCRIPTIONS_TABLE (invariant 8).
    return _dynamodb.Table(os.environ["PUSH_SUBSCRIPTIONS_TABLE"])


def _resolve_url(activity_id: str, explicit_url: str | None) -> str:
    """URL opened on click. An explicit ``url`` in the event wins; otherwise the
    activity route that exists in frontend/src/App.tsx (``/activities/:id``)."""
    if explicit_url:
        return explicit_url
    return f"/activities/{activity_id}"


def _subscriptions(user_id: str) -> list[dict[str, Any]]:
    resp = _table().query(KeyConditionExpression=Key("user_id").eq(user_id))
    return resp.get("Items", [])


def _delete(user_id: str, endpoint_hash: str) -> None:
    try:
        _table().delete_item(Key={"user_id": user_id, "endpoint_hash": endpoint_hash})
        logger.info(f"push_cleanup user={user_id} endpoint_hash={endpoint_hash[:12]} reason=410")
    except ClientError as exc:
        logger.warning(f"Failed to delete expired subscription: {exc}")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    inject_correlation_id(logger, event)

    user_id = (event.get("user_id") or "").strip()
    activity_id = (event.get("activity_id") or "").strip()
    url = (event.get("url") or "").strip()
    # activity_id is optional as soon as an explicit url is provided.
    if not user_id or (not activity_id and not url):
        logger.warning("push_send skipped: missing user_id, or both activity_id and url")
        return {"statusCode": 400, "sent": 0}

    title = event.get("title") or DEFAULT_TITLE
    body = event.get("body") or DEFAULT_BODY
    tag = event.get("tag") or (f"activity-{activity_id}" if activity_id else "strava-ai-boost")
    payload = {
        "title": title,
        "body": body,
        # The service worker opens this URL on click. Must start with '/'.
        "url": _resolve_url(activity_id, url or None),
        "tag": tag,
    }

    subs = _subscriptions(user_id)
    if not subs:
        logger.info(f"push_send user={user_id} activity={activity_id} subscriptions=0")
        return {"statusCode": 200, "sent": 0}

    sent = 0
    cleaned = 0
    for sub in subs:
        subscription_info = {
            "endpoint": sub["endpoint"],
            "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
        }
        try:
            send_push(subscription_info, payload)
            sent += 1
        except PushExpired:
            _delete(user_id, sub["endpoint_hash"])
            cleaned += 1
        except Exception as exc:  # noqa: BLE001 - one failing sub never blocks the others
            logger.warning(f"push_send error user={user_id}: {exc}")

    logger.info(f"push_send user={user_id} activity={activity_id} sent={sent} cleaned={cleaned}")
    return {"statusCode": 200, "sent": sent, "cleaned": cleaned}
