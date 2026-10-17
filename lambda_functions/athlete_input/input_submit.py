"""Store one athlete feedback submission and resume its Step Functions task."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

import boto3
from aws_lambda_powertools.metrics import MetricUnit, single_metric
from botocore.config import Config
from botocore.exceptions import ClientError

from shared.logger import METRICS_NAMESPACE, get_logger, inject_correlation_id
from shared.responses import (
    CORS_HEADERS_WRITE,
    create_error_response,
    create_success_response,
)

logger = get_logger("input_submit")

dynamodb = boto3.resource("dynamodb")
# Bounded callback (one 2 s connect + 4 s read attempt, no retry): the input is
# already durable when SendTaskSuccess runs, so a stalled call must fall into the
# 202 path well inside the Lambda timeout (15 s, at least twice this budget)
# instead of being killed with an integration error. The fetcher stays the backstop.
STEPFUNCTIONS_CLIENT_CONFIG = Config(
    connect_timeout=2,
    read_timeout=4,
    retries={"total_max_attempts": 1},
)
stepfunctions = boto3.client("stepfunctions", config=STEPFUNCTIONS_CLIENT_CONFIG)

_RESPONSE_HEADERS = {**CORS_HEADERS_WRITE, "Cache-Control": "no-store"}
_ACTIVITY_ID = re.compile(r"^[0-9]+$")
_ALLOWED_FIELDS = {"rpe", "summary"}
_LATE_CALLBACK_CODES = {"TaskTimedOut", "InvalidToken", "TaskDoesNotExist"}


def _record_outcome(outcome: str) -> None:
    """Emit one dimension-exact ``InputSubmit{outcome}`` metric."""
    try:
        with single_metric(
            name="InputSubmit",
            unit=MetricUnit.Count,
            value=1,
            namespace=METRICS_NAMESPACE,
        ) as metric:
            metric.add_dimension(name="outcome", value=outcome)
    except Exception as exc:  # noqa: BLE001 - telemetry must not change the API result
        logger.warning(
            "Could not emit InputSubmit outcome",
            extra={"outcome": outcome, "error_type": type(exc).__name__},
        )


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


_ZWJ = "\u200d"  # zero-width joiner: emoji sequences need it
_EXCESS_NEWLINES = re.compile(r"\n{3,}")


def _keep_character(character: str) -> bool:
    if character == "\n" or character == _ZWJ:
        return True
    # Cc: control characters. Cf: invisible format characters (bidi overrides
    # such as U+202E, zero-width space U+200B, word joiner U+2060...), a cheap
    # way to hide text from a human reader of the published post.
    return unicodedata.category(character) not in ("Cc", "Cf")


def _clean_summary(value: str) -> str:
    """Drop control and format characters, keep paragraphs (at most one blank line)."""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = "".join(character for character in value if _keep_character(character))
    return _EXCESS_NEWLINES.sub("\n\n", cleaned)


def _validated_body(event: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        body = json.loads(event.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return None, "Invalid JSON body"
    if not isinstance(body, dict):
        return None, "Body must be a JSON object"
    if set(body) - _ALLOWED_FIELDS:
        return None, "Unknown fields are not allowed"

    rpe = body.get("rpe")
    if type(rpe) is not int or not 1 <= rpe <= 10:
        return None, "rpe must be an integer from 1 to 10"

    raw_summary = body.get("summary", "")
    if not isinstance(raw_summary, str):
        return None, "summary must be a string"
    summary = _clean_summary(raw_summary)
    if len(summary) > 2000:
        return None, "summary must be at most 2000 characters"
    return {"rpe": rpe, "summary": summary}, None


def _is_conditional_failure(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle ``POST /activities/{activityId}/feedback``."""
    inject_correlation_id(logger, event)

    activity_id = _activity_id(event)
    if not activity_id:
        return create_error_response(400, "Invalid activityId", cors_headers=_RESPONSE_HEADERS)

    submission, validation_error = _validated_body(event)
    if validation_error:
        return create_error_response(400, validation_error, cors_headers=_RESPONSE_HEADERS)
    assert submission is not None

    claim_user_id = _claim_user_id(event)
    if not claim_user_id:
        return create_error_response(403, "Forbidden", cors_headers=_RESPONSE_HEADERS)

    table = _table()
    try:
        item = table.get_item(
            Key={"activity_id": activity_id},
            ConsistentRead=True,
        ).get("Item") or {}
    except ClientError as exc:
        logger.error(
            "Failed to authorize athlete-input submission",
            extra={"activity_id": activity_id, "error_code": exc.response.get("Error", {}).get("Code")},
        )
        return create_error_response(500, "Internal server error", cors_headers=_RESPONSE_HEADERS)

    if str(item.get("user_id", "")) != claim_user_id:
        logger.warning("Athlete-input submission denied", extra={"activity_id": activity_id})
        return create_error_response(403, "Forbidden", cors_headers=_RESPONSE_HEADERS)

    athlete_input = {
        "rpe": submission["rpe"],
        "summary": submission["summary"],
        "submitted_at": datetime.now(UTC).isoformat(),
    }
    try:
        response = table.update_item(
            Key={"activity_id": activity_id},
            UpdateExpression=(
                "SET athlete_input = :input, athlete_input_state = :submitted "
                "REMOVE input_task_token"
            ),
            ConditionExpression="athlete_input_state = :awaiting AND user_id = :user_id",
            ExpressionAttributeValues={
                ":input": athlete_input,
                ":submitted": "submitted",
                ":awaiting": "awaiting",
                ":user_id": claim_user_id,
            },
            ReturnValues="ALL_OLD",
        )
    except ClientError as exc:
        if _is_conditional_failure(exc):
            _record_outcome("409")
            return create_error_response(409, "Feedback window is closed", cors_headers=_RESPONSE_HEADERS)
        logger.error(
            "Failed to store athlete-input submission",
            extra={"activity_id": activity_id, "error_code": exc.response.get("Error", {}).get("Code")},
        )
        return create_error_response(500, "Internal server error", cors_headers=_RESPONSE_HEADERS)

    # The old image contains the task token. Keep it in this local variable only;
    # never include it in logs, metrics, or the API response.
    task_token = (response.get("Attributes") or {}).get("input_task_token")
    try:
        if not isinstance(task_token, str) or not task_token:
            raise ValueError("missing task token")
        stepfunctions.send_task_success(taskToken=task_token, output="{}")
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "Unknown")
        outcome = "late" if error_code in _LATE_CALLBACK_CODES else "callback_error"
        _record_outcome(outcome)
        logger.error(
            "Athlete-input callback failed after storage",
            extra={"activity_id": activity_id, "error_code": error_code, "outcome": outcome},
        )
    except Exception as exc:  # noqa: BLE001 - the durable write remains successful
        _record_outcome("callback_error")
        logger.error(
            "Athlete-input callback failed after storage",
            extra={"activity_id": activity_id, "error_type": type(exc).__name__, "outcome": "callback_error"},
        )
    else:
        _record_outcome("ok")

    return create_success_response(
        {"status": "accepted"},
        status_code=202,
        cors_headers=_RESPONSE_HEADERS,
    )
