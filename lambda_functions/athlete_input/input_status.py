"""Return the athlete-input state for one activity.

The API Gateway route is Cognito-protected. This handler additionally authorizes
against the activity row's ``user_id`` because the table contains personal data.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from shared.logger import get_logger, inject_correlation_id
from shared.responses import (
    CORS_HEADERS_READ,
    create_error_response,
    create_success_response,
)

logger = get_logger("input_status")

dynamodb = boto3.resource("dynamodb")

_RESPONSE_HEADERS = {**CORS_HEADERS_READ, "Cache-Control": "no-store"}
_ACTIVITY_ID = re.compile(r"^[0-9]+$")
_VALID_STATES = {"awaiting", "submitted", "closed"}


def _table() -> Any:
    # Read at call time (invariant 8), like input_wait: importing needs no environment.
    return dynamodb.Table(os.environ["ACTIVITIES_TABLE"])


def _activity_id(event: dict[str, Any]) -> str:
    value = (event.get("pathParameters") or {}).get("activityId")
    return value if isinstance(value, str) and _ACTIVITY_ID.fullmatch(value) else ""


def _claim_user_id(event: dict[str, Any]) -> str:
    try:
        claims = (event.get("requestContext") or {}).get("authorizer", {}).get("claims", {})
        value = claims.get("custom:strava_id", "")
        return value if isinstance(value, str) else ""
    except (AttributeError, TypeError):
        return ""


def _deadline_is_past(value: Any) -> bool:
    """Return True for expired or malformed deadlines, closing the window safely."""
    if not isinstance(value, str) or not value:
        return True
    try:
        deadline = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        return deadline.astimezone(UTC) <= datetime.now(UTC)
    except ValueError:
        return True


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle ``GET /activities/{activityId}/feedback``."""
    inject_correlation_id(logger, event)

    activity_id = _activity_id(event)
    if not activity_id:
        return create_error_response(400, "Invalid activityId", cors_headers=_RESPONSE_HEADERS)

    claim_user_id = _claim_user_id(event)
    if not claim_user_id:
        return create_error_response(403, "Forbidden", cors_headers=_RESPONSE_HEADERS)

    try:
        response = _table().get_item(
            Key={"activity_id": activity_id},
            ConsistentRead=True,
        )
    except ClientError as exc:
        logger.error(
            "Failed to read athlete-input status",
            extra={"activity_id": activity_id, "error_code": exc.response.get("Error", {}).get("Code")},
        )
        return create_error_response(500, "Internal server error", cors_headers=_RESPONSE_HEADERS)

    item = response.get("Item") or {}
    if not item.get("user_id"):
        # No owner yet (row written by the processor before input_wait or the
        # fetcher ran, or no row at all): no window can exist, and "none" leaks
        # nothing about the activity.
        return create_success_response({"state": "none"}, cors_headers=_RESPONSE_HEADERS)
    if str(item.get("user_id", "")) != claim_user_id:
        logger.warning("Athlete-input status denied", extra={"activity_id": activity_id})
        return create_error_response(403, "Forbidden", cors_headers=_RESPONSE_HEADERS)

    state = item.get("athlete_input_state")
    if state not in _VALID_STATES:
        state = "none"

    deadline = item.get("input_deadline_at")
    if state == "awaiting" and _deadline_is_past(deadline):
        state = "closed"

    payload: dict[str, Any] = {"state": state}
    if state == "awaiting" and isinstance(deadline, str):
        payload["deadline_at"] = deadline
    return create_success_response(payload, cors_headers=_RESPONSE_HEADERS)
