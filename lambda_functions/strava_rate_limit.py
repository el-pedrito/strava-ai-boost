"""
Strava API Rate Limit Manager

Centralized rate limiting for all Strava API calls.
Strava limits: 100 requests/15min, 1000 requests/day.

Uses atomic DynamoDB operations to prevent race conditions.
"""

import os
import logging
from typing import Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

UTC = timezone.utc

dynamodb = boto3.resource('dynamodb')
RATE_LIMITS_TABLE = os.environ.get('RATE_LIMITS_TABLE', 'strava-ai-boost-rate-limits')

# Strava API limits
SHORT_TERM_LIMIT = 100   # per 15 minutes
SHORT_TERM_WINDOW = 15   # minutes
DAILY_LIMIT = 1000       # per day

# Safety buffers
SHORT_TERM_BUFFER = 10   # reserve 10 calls
DAILY_BUFFER = 50        # reserve 50 calls


def check_and_consume(calls_needed: int = 1) -> Tuple[bool, Dict[str, Any]]:
    """
    Atomically check rate limits and consume quota if allowed.
    
    Returns:
        (is_allowed, rate_info) where rate_info contains current usage and limits
    """
    table = dynamodb.Table(RATE_LIMITS_TABLE)
    now = datetime.now(UTC)

    try:
        # Reset expired windows first (atomic)
        _reset_if_expired(table, 'short_term', timedelta(minutes=SHORT_TERM_WINDOW), now)
        _reset_if_expired(table, 'daily', timedelta(days=1), now)

        # Read current state
        short_usage = _get_usage(table, 'short_term')
        daily_usage = _get_usage(table, 'daily')

        short_remaining = SHORT_TERM_LIMIT - SHORT_TERM_BUFFER - short_usage
        daily_remaining = DAILY_LIMIT - DAILY_BUFFER - daily_usage

        rate_info = {
            'short_term': {'usage': short_usage, 'limit': SHORT_TERM_LIMIT, 'remaining': max(0, short_remaining)},
            'daily': {'usage': daily_usage, 'limit': DAILY_LIMIT, 'remaining': max(0, daily_remaining)},
        }

        if calls_needed > short_remaining or calls_needed > daily_remaining:
            logger.warning(f"Rate limit would be exceeded: need {calls_needed}, "
                           f"short={short_remaining}, daily={daily_remaining}")
            return False, rate_info

        # Atomically increment both counters
        _increment(table, 'short_term', calls_needed, now)
        _increment(table, 'daily', calls_needed, now)

        rate_info['short_term']['usage'] += calls_needed
        rate_info['short_term']['remaining'] = max(0, short_remaining - calls_needed)
        rate_info['daily']['usage'] += calls_needed
        rate_info['daily']['remaining'] = max(0, daily_remaining - calls_needed)

        return True, rate_info

    except Exception as e:
        logger.error(f"Rate limit check failed: {e}")
        return False, {'error': str(e)}


def record_usage(calls_made: int) -> None:
    """Record API calls that were made (for callers that check separately)."""
    table = dynamodb.Table(RATE_LIMITS_TABLE)
    now = datetime.now(UTC)
    try:
        _increment(table, 'short_term', calls_made, now)
        _increment(table, 'daily', calls_made, now)
        logger.info(f"Recorded {calls_made} Strava API calls")
    except Exception as e:
        logger.error(f"Failed to record usage: {e}")


def get_status() -> Dict[str, Any]:
    """Get current rate limit status without consuming quota."""
    table = dynamodb.Table(RATE_LIMITS_TABLE)
    now = datetime.now(UTC)

    try:
        _reset_if_expired(table, 'short_term', timedelta(minutes=SHORT_TERM_WINDOW), now)
        _reset_if_expired(table, 'daily', timedelta(days=1), now)

        short_usage = _get_usage(table, 'short_term')
        daily_usage = _get_usage(table, 'daily')

        short_item = _get_item(table, 'short_term')
        daily_item = _get_item(table, 'daily')

        return {
            'short_term': {
                'usage': short_usage,
                'limit': SHORT_TERM_LIMIT,
                'remaining': max(0, SHORT_TERM_LIMIT - SHORT_TERM_BUFFER - short_usage),
                'resets_at': short_item.get('reset_time', 'unknown'),
            },
            'daily': {
                'usage': daily_usage,
                'limit': DAILY_LIMIT,
                'remaining': max(0, DAILY_LIMIT - DAILY_BUFFER - daily_usage),
                'resets_at': daily_item.get('reset_time', 'unknown'),
            },
        }
    except Exception as e:
        logger.error(f"Failed to get rate limit status: {e}")
        return {'error': str(e)}


def seconds_until_available() -> int:
    """Calculate seconds to wait before quota is available again."""
    table = dynamodb.Table(RATE_LIMITS_TABLE)
    now = datetime.now(UTC)

    try:
        short_usage = _get_usage(table, 'short_term')
        daily_usage = _get_usage(table, 'daily')

        if daily_usage >= DAILY_LIMIT - DAILY_BUFFER:
            item = _get_item(table, 'daily')
            reset = datetime.fromisoformat(item.get('reset_time', now.isoformat()))
            return max(0, int((reset - now).total_seconds()))

        if short_usage >= SHORT_TERM_LIMIT - SHORT_TERM_BUFFER:
            item = _get_item(table, 'short_term')
            reset = datetime.fromisoformat(item.get('reset_time', now.isoformat()))
            return max(0, int((reset - now).total_seconds()))

        return 0
    except Exception:
        return SHORT_TERM_WINDOW * 60  # safe default


# --- Internal helpers ---

def _get_item(table, limit_type: str) -> Dict[str, Any]:
    try:
        resp = table.get_item(Key={'limit_type': limit_type})
        return resp.get('Item', {})
    except Exception:
        return {}


def _get_usage(table, limit_type: str) -> int:
    item = _get_item(table, limit_type)
    return int(item.get('current_usage', 0))


def _reset_if_expired(table, limit_type: str, window: timedelta, now: datetime) -> None:
    """Atomically reset counter only if reset_time has passed."""
    new_reset = (now + window).isoformat()
    try:
        table.update_item(
            Key={'limit_type': limit_type},
            UpdateExpression='SET current_usage = :zero, reset_time = :reset, updated_at = :now',
            ConditionExpression='attribute_not_exists(reset_time) OR reset_time < :now_str',
            ExpressionAttributeValues={
                ':zero': 0,
                ':reset': new_reset,
                ':now': now.isoformat(),
                ':now_str': now.isoformat(),
            }
        )
        logger.info(f"Reset {limit_type} rate limit counter, next reset: {new_reset}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            pass  # Not expired yet, expected
        else:
            raise


def _increment(table, limit_type: str, count: int, now: datetime) -> None:
    """Atomically increment usage counter."""
    table.update_item(
        Key={'limit_type': limit_type},
        UpdateExpression='ADD current_usage :inc SET last_request = :now',
        ExpressionAttributeValues={
            ':inc': count,
            ':now': now.isoformat(),
        }
    )
