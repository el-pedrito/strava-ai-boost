"""Push subscription API (StravaAIBoost-PushApi).

Serves the Web Push subscription endpoints behind the Cognito authorizer, like the
other API Lambdas of this repo. User resolution follows the same convention as
dashboard_api / audio_debrief_api: the ``custom:strava_id`` Cognito claim identifies
the athlete (it maps to the Strava athlete id used as DynamoDB ``user_id``).

Routes (all Cognito-protected except the public key, which is public by design):
- GET    /push/vapid-public-key   -> {public_key} (no secret: this is the public key)
- POST   /push/subscribe          -> stores the browser subscription
- DELETE /push/subscribe          -> deletes the subscription(s)

Model (table ``strava-ai-boost-push-subscriptions``, PK user_id, SK endpoint_hash):
    { user_id, endpoint_hash, endpoint, p256dh, auth, created_at }
``endpoint_hash`` = sha256(endpoint): re-subscribing the same device overwrites its
row instead of duplicating it.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from push.webpush_core import get_public_key
from shared.logger import get_logger, inject_correlation_id
from shared.responses import (
    CORS_HEADERS_WRITE,
    create_error_response,
    create_success_response,
)

logger = get_logger("push_api")

REGION = os.environ.get("AWS_REGION", "us-east-1")

_dynamodb: Any = boto3.resource("dynamodb", region_name=REGION)


def _table() -> Any:
    # Read at call time, not at import: this keeps the module importable in a
    # runtime that does not define PUSH_SUBSCRIPTIONS_TABLE (invariant 8).
    return _dynamodb.Table(os.environ["PUSH_SUBSCRIPTIONS_TABLE"])


def _endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


def _get_user_id(event: dict[str, Any]) -> str:
    """Return the Strava athlete id from the Cognito ``custom:strava_id`` claim.

    Returns an empty string when no identity is present, which the handler turns
    into a 401 for the subscribe/unsubscribe routes.
    """
    try:
        claims = (event.get("requestContext") or {}).get("authorizer", {}).get("claims", {})
        return claims.get("custom:strava_id", "") or ""
    except (AttributeError, TypeError):
        return ""


def get_vapid_public_key(_event: dict[str, Any]) -> dict[str, Any]:
    try:
        return create_success_response({"public_key": get_public_key()})
    except (ClientError, ValueError, KeyError) as exc:
        logger.error(f"Failed to load VAPID public key: {exc}")
        return create_error_response(500, "VAPID key unavailable")


def subscribe(event: dict[str, Any], user_id: str) -> dict[str, Any]:
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return create_error_response(400, "Invalid JSON body", cors_headers=CORS_HEADERS_WRITE)
    if not isinstance(body, dict):
        return create_error_response(400, "Body must be a JSON object", cors_headers=CORS_HEADERS_WRITE)

    endpoint = (body.get("endpoint") or "").strip()
    keys = body.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip() if isinstance(keys, dict) else ""
    auth = (keys.get("auth") or "").strip() if isinstance(keys, dict) else ""
    if not endpoint or not p256dh or not auth:
        return create_error_response(
            400,
            "endpoint and keys.p256dh/auth are required",
            cors_headers=CORS_HEADERS_WRITE,
        )

    record = {
        "user_id": user_id,
        "endpoint_hash": _endpoint_hash(endpoint),
        "endpoint": endpoint,
        "p256dh": p256dh,
        "auth": auth,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        _table().put_item(Item=record)
    except ClientError as exc:
        logger.error(f"Failed to store subscription for {user_id}: {exc}")
        return create_error_response(500, "Failed to store subscription", cors_headers=CORS_HEADERS_WRITE)

    return create_success_response({"subscribed": True}, cors_headers=CORS_HEADERS_WRITE)


def unsubscribe(event: dict[str, Any], user_id: str) -> dict[str, Any]:
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        body = {}
    endpoint = (body.get("endpoint") or "").strip() if isinstance(body, dict) else ""

    try:
        table = _table()
        if endpoint:
            table.delete_item(Key={"user_id": user_id, "endpoint_hash": _endpoint_hash(endpoint)})
        else:
            # No endpoint provided: delete every subscription of this user.
            resp = table.query(KeyConditionExpression=Key("user_id").eq(user_id))
            for item in resp.get("Items", []):
                table.delete_item(Key={"user_id": user_id, "endpoint_hash": item["endpoint_hash"]})
    except ClientError as exc:
        logger.error(f"Failed to delete subscription for {user_id}: {exc}")
        return create_error_response(500, "Failed to delete subscription", cors_headers=CORS_HEADERS_WRITE)

    return create_success_response({"subscribed": False}, cors_headers=CORS_HEADERS_WRITE)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    inject_correlation_id(logger, event)
    method = event.get("httpMethod", "GET")
    path = event.get("path", "")

    if method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS_WRITE.copy(),
            "body": json.dumps({"status": "ok"}),
        }

    # Public key: no secret, no identity required (the Cognito authorizer may still
    # be attached at the API Gateway layer; we do not require it here).
    if path.endswith("/vapid-public-key") and method == "GET":
        return get_vapid_public_key(event)

    user_id = _get_user_id(event)
    if not user_id:
        return create_error_response(401, "Unauthenticated: missing identity claim")

    try:
        if path.endswith("/subscribe") and method == "POST":
            return subscribe(event, user_id)
        if path.endswith("/subscribe") and method == "DELETE":
            return unsubscribe(event, user_id)
        return create_error_response(404, "Endpoint not found")
    except (ClientError, ValueError, TypeError) as exc:
        logger.error(f"Push API error: {exc}", exc_info=True)
        return create_error_response(500, "Internal server error")
