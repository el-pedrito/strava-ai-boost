"""Input wait Lambda (StravaAIBoost-InputWait): open the athlete-input window.

Invoked by the ``WaitForAthleteInput`` state (``waitForTaskToken``, 1 h timeout) with
``{activity_id, user_id, task_token}``. It opens the window on the activity row,
asks the athlete for their feeling through a push notification, and returns. The
execution then waits until the input API calls ``SendTaskSuccess`` with the stored
token, or until the 1 h task timeout, caught by the state machine (D4).

Fail open (D5, D8): when nobody can be asked (push disabled, no device reached,
any error) the window is closed again and the execution is released at once with
``SendTaskSuccess``. A replayed invocation on an already opened or closed window
releases at once too (D3: one input per activity).

The event carries the task token, a secret that lets anyone resume the execution:
the event is never logged, nor the token. Only ids and outcomes are.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from aws_lambda_powertools.metrics import single_metric
from botocore.exceptions import ClientError

from shared.logger import METRICS_NAMESPACE, MetricUnit, get_logger
from shared.push_notify import notify_input_request

logger = get_logger("input_wait")

REGION = os.environ.get("AWS_REGION", "us-east-1")
_dynamodb: Any = boto3.resource("dynamodb", region_name=REGION)
_stepfunctions: Any = boto3.client("stepfunctions", region_name=REGION)

# Same as the WaitForAthleteInput task timeout (content_generation_stack.py).
INPUT_WINDOW = timedelta(hours=1)
NOTIFICATION_TITLE = "Nouvelle séance"
NOTIFICATION_BODY = "Ton ressenti ?"
_ACTIVITY_ID_RE = re.compile(r"^[0-9]{1,20}$")
# Step Functions task tokens are at most 2048 characters (API reference, SendTaskSuccess).
MAX_TOKEN_LENGTH = 2048

STATE_AWAITING = "awaiting"
STATE_CLOSED = "closed"


def _push_enabled() -> bool:
    return os.environ.get("PUSH_ENABLED", "").lower() in ("1", "true", "yes")


def _table() -> Any:
    # Read at call time (invariant 8): importing this module needs no environment.
    return _dynamodb.Table(os.environ["ACTIVITIES_TABLE"])


def _record(outcome: str) -> None:
    """Emit ``InputWait{outcome}`` (EMF), never raising."""
    try:
        with single_metric(
            name="InputWait", unit=MetricUnit.Count, value=1, namespace=METRICS_NAMESPACE
        ) as metric:
            metric.add_dimension(name="outcome", value=outcome)
    except Exception as exc:  # noqa: BLE001 - a metric must never break the wait
        logger.warning(f"Could not emit InputWait{{outcome={outcome}}}: {exc}")


def _release(task_token: str, activity_id: str) -> None:
    """Resume the execution now. A failure leaves the 1 h task timeout as the backstop."""
    try:
        _stepfunctions.send_task_success(taskToken=task_token, output="{}")
    except Exception as exc:  # noqa: BLE001 - the task timeout still releases the run
        # The exception text never carries the token (it is a request parameter).
        logger.warning(f"input_wait could not release activity={activity_id}: {type(exc).__name__}")


def _open_window(activity_id: str, user_id: str, task_token: str, now: datetime) -> bool:
    """Open the window once. False when it was already opened or closed (replay)."""
    deadline = (now + INPUT_WINDOW).isoformat(timespec="seconds")
    try:
        _table().update_item(
            Key={"activity_id": activity_id},
            UpdateExpression=(
                "SET athlete_input_state = :awaiting, input_task_token = :t, "
                "input_deadline_at = :d, user_id = :u"
            ),
            ConditionExpression="attribute_not_exists(athlete_input_state)",
            ExpressionAttributeValues={
                ":awaiting": STATE_AWAITING,
                ":t": task_token,
                ":d": deadline,
                ":u": user_id,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def _close_window(activity_id: str) -> None:
    """Close a window nobody will answer, so GET says ``closed`` without waiting."""
    try:
        _table().update_item(
            Key={"activity_id": activity_id},
            UpdateExpression="SET athlete_input_state = :closed REMOVE input_task_token",
            ConditionExpression="athlete_input_state = :awaiting",
            ExpressionAttributeValues={":closed": STATE_CLOSED, ":awaiting": STATE_AWAITING},
        )
    except Exception as exc:  # noqa: BLE001 - the fetcher closes it anyway
        logger.warning(f"input_wait could not close activity={activity_id}: {type(exc).__name__}")


# No @metrics.log_metrics: every metric here goes through single_metric, which
# flushes itself. No log_event: the event carries the task token.
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    event = event if isinstance(event, dict) else {}
    task_token = event.get("task_token")
    activity_id = str(event.get("activity_id") or "").strip()
    user_id = str(event.get("user_id") or "").strip()

    if not isinstance(task_token, str) or not task_token or len(task_token) > MAX_TOKEN_LENGTH:
        # Nothing to release: the task timeout (1 h) resumes the execution.
        logger.error(f"input_wait: missing or invalid task token activity={activity_id}")
        _record("error")
        return {"outcome": "error"}

    if not _ACTIVITY_ID_RE.match(activity_id) or not user_id:
        logger.error("input_wait: invalid activity_id or user_id, releasing")
        _release(task_token, activity_id)
        _record("error")
        return {"outcome": "error"}

    try:
        opened = _open_window(activity_id, user_id, task_token, datetime.now(UTC))
    except Exception as exc:  # noqa: BLE001 - fail open (D8)
        logger.error(f"input_wait: open failed activity={activity_id}: {type(exc).__name__}")
        _release(task_token, activity_id)
        _record("error")
        return {"outcome": "error"}

    if not opened:
        # Window already opened or closed (replayed invocation): one input per activity.
        logger.info(f"input_wait: window already used activity={activity_id}, releasing")
        _release(task_token, activity_id)
        _record("replay")
        return {"outcome": "replay"}

    outcome = "no_push"
    if _push_enabled():
        try:
            sent = notify_input_request(
                user_id=user_id,
                activity_id=activity_id,
                title=NOTIFICATION_TITLE,
                body=NOTIFICATION_BODY,
                url=f"/activities/{activity_id}/feedback",
            )
        except Exception as exc:  # noqa: BLE001 - notify_input_request never raises; belt and braces
            logger.error(f"input_wait: notify failed activity={activity_id}: {type(exc).__name__}")
            sent = 0
            outcome = "error"
        if sent > 0:
            logger.info(f"input_wait: waiting activity={activity_id} devices={sent}")
            _record("waiting")
            return {"outcome": "waiting"}

    # Nobody was asked: close the window and let the run go on now (D5).
    logger.info(f"input_wait: {outcome} activity={activity_id}, releasing")
    _close_window(activity_id)
    _release(task_token, activity_id)
    _record(outcome)
    return {"outcome": outcome}
