import json
import logging
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


def create_success_response(
    data: Dict[str, Any],
    status_code: int = 200,
    cors_headers: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    return {
        'statusCode': status_code,
        'headers': (cors_headers or CORS_HEADERS_READ).copy(),
        'body': json.dumps(
            {**data, 'timestamp': datetime.now(UTC).isoformat()},
            default=decimal_default,
            ensure_ascii=False,
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
