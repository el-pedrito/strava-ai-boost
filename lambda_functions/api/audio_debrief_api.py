"""
Audio Debrief API Lambda

GET /activities/{activityId}/audio-url

Returns a 1h presigned S3 URL for the activity's voice debrief MP3, plus
duration and generated-at timestamps. Returns 404 if the activity has no
audio debrief yet, 403 if the activity does not belong to the caller, and
400 if the path parameter is missing.

Authentication: API Gateway Cognito authorizer is the source of truth — the
caller's user_id is read from the JWT claims (cognito:username or sub).
The Lambda also accepts ?user_id= for service-to-service invocations
(e.g. presigning from a backend script).
"""

import os
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

from shared.logger import get_logger, inject_correlation_id
from shared.responses import (
    CORS_HEADERS_READ as CORS_HEADERS,
    create_error_response,
    create_success_response,
)

logger = get_logger("audio-debrief-api")

REGION = os.environ.get("AWS_REGION", "us-east-1")
ACTIVITIES_TABLE = os.environ.get("ACTIVITIES_TABLE", "strava-ai-boost-activities")
AUDIO_BUCKET = os.environ.get("AUDIO_DEBRIEF_BUCKET", "")
PRESIGNED_TTL = int(os.environ.get("PRESIGNED_URL_TTL_SECONDS", "3600"))
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
# SigV4 client signs presigned URLs with the Lambda execution role
s3 = boto3.client("s3", region_name=REGION)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    inject_correlation_id(logger, event)

    if not AUDIO_BUCKET:
        return create_error_response(500, "Audio bucket not configured", cors_headers=CORS_HEADERS)

    try:
        activity_id = _extract_activity_id(event)
        if not activity_id:
            return create_error_response(
                400, "Missing path parameter 'activityId'", cors_headers=CORS_HEADERS
            )

        caller_user_id = _extract_caller_user_id(event)

        item = _load_activity_item(activity_id)
        if not item:
            return create_error_response(404, "Activity not found", cors_headers=CORS_HEADERS)

        # Ownership check (skipped if no caller could be resolved — single-user demo)
        owner_id = item.get("user_id")
        if caller_user_id and owner_id and str(owner_id) != str(caller_user_id):
            logger.warning(
                f"User {caller_user_id} requested audio for activity {activity_id} owned by {owner_id}"
            )
            return create_error_response(403, "Forbidden", cors_headers=CORS_HEADERS)

        s3_key = item.get("audio_debrief_s3_key") or _key_from_url(item.get("audio_debrief_url"))
        if not s3_key:
            return create_error_response(
                404, "Audio debrief not available for this activity", cors_headers=CORS_HEADERS
            )

        # Verify the object actually exists before signing
        if not _object_exists(s3_key):
            return create_error_response(
                404, "Audio debrief file not found in storage", cors_headers=CORS_HEADERS
            )

        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": AUDIO_BUCKET, "Key": s3_key},
            ExpiresIn=PRESIGNED_TTL,
            HttpMethod="GET",
        )

        return create_success_response(
            {
                "audio_url": url,
                "duration_sec": _to_int(item.get("audio_debrief_duration_sec")),
                "generated_at": item.get("audio_debrief_generated_at"),
                "language": item.get("audio_debrief_language"),
                "voice": item.get("audio_debrief_voice"),
                "expires_in_sec": PRESIGNED_TTL,
            },
            cors_headers=CORS_HEADERS,
        )

    except ClientError as exc:
        logger.error(f"AWS error: {exc}")
        return create_error_response(500, "Storage error", cors_headers=CORS_HEADERS)
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"Unexpected error: {exc}")
        return create_error_response(500, "Internal error", cors_headers=CORS_HEADERS)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _extract_activity_id(event: Dict[str, Any]) -> Optional[str]:
    path_params = event.get("pathParameters") or {}
    activity_id = path_params.get("activityId") or path_params.get("activity_id")
    if activity_id:
        return str(activity_id)
    qs = event.get("queryStringParameters") or {}
    return qs.get("activity_id") or None


def _extract_caller_user_id(event: Dict[str, Any]) -> Optional[str]:
    """Return the calling user_id from Cognito JWT claims, query, or env default."""
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("claims", {})
    )
    if claims:
        for key in ("custom:strava_id", "cognito:username", "sub"):
            value = claims.get(key)
            if value:
                return str(value)

    qs = event.get("queryStringParameters") or {}
    if qs.get("user_id"):
        return str(qs["user_id"])

    if DEFAULT_USER_ID:
        return DEFAULT_USER_ID
    return None


def _load_activity_item(activity_id: str) -> Optional[Dict[str, Any]]:
    table = dynamodb.Table(ACTIVITIES_TABLE)
    response = table.get_item(
        Key={"activity_id": activity_id},
        ProjectionExpression=(
            "user_id, audio_debrief_url, audio_debrief_s3_key, "
            "audio_debrief_generated_at, audio_debrief_duration_sec, "
            "audio_debrief_language, audio_debrief_voice"
        ),
    )
    return response.get("Item")


def _key_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    prefix = f"s3://{AUDIO_BUCKET}/"
    if url.startswith(prefix):
        return url[len(prefix):]
    return None


def _object_exists(key: str) -> bool:
    try:
        s3.head_object(Bucket=AUDIO_BUCKET, Key=key)
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

