import json
import logging
import math
from datetime import datetime, UTC
from decimal import Decimal
from typing import Any, Dict

logger = logging.getLogger(__name__)

CORS_HEADERS_READ = {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
    'Access-Control-Max-Age': '86400',
}

CORS_HEADERS_WRITE = {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
    'Access-Control-Max-Age': '86400',
}


def decimal_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _sanitize_non_finite(value: Any) -> Any:
    """Return a copy of ``value`` with every non-finite number mapped to ``None``.

    Recurses through ``dict``, ``list`` and ``tuple``. A ``float`` or ``Decimal``
    that is ``NaN`` or ``±inf`` becomes ``None``; finite ``float``/``Decimal`` and
    every other type are returned unchanged, so the existing ``decimal_default``
    behaviour (``Decimal`` -> ``float``) is preserved for finite values. Booleans
    pass through untouched.

    DynamoDB cannot store ``NaN``/``inf``, so a non-finite value only appears as a
    computed result; this pass stops it reaching the body before
    ``json.dumps(..., allow_nan=False)`` would raise. The input is never mutated.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, dict):
        return {key: _sanitize_non_finite(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_sanitize_non_finite(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_non_finite(item) for item in value)
    return value


def create_success_response(
    data: Dict[str, Any],
    status_code: int = 200,
    cors_headers: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    # Sanitize non-finite float/Decimal values to None, then forbid NaN so a
    # missed value fails closed (ValueError -> 500) rather than producing a body
    # that JSON.parse rejects in the browser.
    payload = _sanitize_non_finite(
        {**data, 'timestamp': datetime.now(UTC).isoformat()}
    )
    return {
        'statusCode': status_code,
        'headers': (cors_headers or CORS_HEADERS_READ).copy(),
        'body': json.dumps(
            payload,
            default=decimal_default,
            ensure_ascii=False,
            allow_nan=False,
        ),
    }


def create_error_response(
    status_code: int,
    message: str,
    cors_headers: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    return {
        'statusCode': status_code,
        'headers': (cors_headers or CORS_HEADERS_READ).copy(),
        'body': json.dumps({
            'error': message,
            'timestamp': datetime.now(UTC).isoformat(),
        }),
    }
