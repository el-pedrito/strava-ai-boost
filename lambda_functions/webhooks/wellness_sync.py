"""WellnessSync Lambda — daily health signals from Intervals.icu into the
wellness table, plus the deterministic morning brief (Lot C).

Scheduled by EventBridge Scheduler (Europe/Paris 06:30, 09:30, 11:00, 15:00).
HRV-SDNN syncs after 09:00, so the later passes catch it.

Each pass:
  - fail closed if the intervals.icu module config cannot be read or is disabled,
  - GET /athlete/0/wellness?oldest=J-N&newest=J (local Paris dates),
  - write one `day#YYYY-MM-DD` row per day PRESENT in the response, as an
    update_item that SETs the fields present and REMOVEs the fields absent from
    that day (no phantom carry-over), only for the days present,
  - rebuild `brief#YYYY-MM-DD` for today (Lot C).

Manual backfill: event {"backfill_days": N}, N clamped to 730, in 90-day slices.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import boto3
import requests

from shared.logger import get_logger, metrics, MetricUnit
from shared.wellness import paris_date, wellness_hrv, wellness_hrv_kind

logger = get_logger("wellness-sync")

REGION = os.environ.get('AWS_REGION', 'eu-west-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
secretsmanager = boto3.client('secretsmanager', region_name=REGION)

WELLNESS_TABLE = os.environ['WELLNESS_TABLE']
USER_CONFIG_TABLE = os.environ['USER_CONFIG_TABLE']
COACHING_SESSIONS_TABLE = os.environ.get('COACHING_SESSIONS_TABLE', 'strava-ai-boost-campus-coaching-sessions')
INTERVALS_ICU_SECRET = os.environ.get('INTERVALS_ICU_SECRET', 'strava-ai-boost-intervals-icu-credentials')
CAMPUS_OWNER_STRAVA_ID = os.environ.get('CAMPUS_OWNER_STRAVA_ID', '')
BRIEF_LOCATION = os.environ.get('BRIEF_LOCATION', '')  # "lat,lon" from CDK context

INTERVALS_BASE_URL = "https://intervals.icu/api/v1/athlete/0"
BACKFILL_MAX_DAYS = 730
BACKFILL_SLICE_DAYS = 90
DEFAULT_LOOKBACK_DAYS = 3

# Numeric wellness fields we persist. Everything else from the API is ignored.
_NUMERIC_FIELDS = [
    'restingHR', 'sleepSecs', 'sleepScore', 'avgSleepingHR', 'readiness',
    'respiration', 'spO2', 'weight', 'ctl', 'atl', 'rampRate', 'vo2max', 'steps',
]
# String/categorical fields.
_STRING_FIELDS = ['sleepQuality']
# All day-row attributes WellnessSync owns (used to compute REMOVE set).
_DAY_ATTRS = _NUMERIC_FIELDS + _STRING_FIELDS + ['hrv', 'hrvSDNN', 'hrv_kind']


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Decimal(str(x)) for finite numbers; None for None / non-finite / junk."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float('inf'), float('-inf')):  # NaN / inf
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _module_config(user_id: str) -> Optional[Dict[str, Any]]:
    """Read the user's intervals_icu module config. Returns None (fail closed)
    when the row/config cannot be read, so a transient DynamoDB error never
    silently writes against the wrong assumption."""
    if not user_id:
        return None
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        resp = table.get_item(Key={'user_id': user_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not read module config for {user_id}: {exc}")
        metrics.add_metric(name="WellnessSyncFailed", unit=MetricUnit.Count, value=1)
        return None
    item = resp.get('Item') or {}
    return (item.get('modules_config') or {}).get('intervals_icu') or {}


def _get_api_key() -> Optional[str]:
    try:
        resp = secretsmanager.get_secret_value(SecretId=INTERVALS_ICU_SECRET)
        return json.loads(resp['SecretString']).get('api_key') or None
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not read intervals.icu secret: {exc}")
        return None


def _fetch_wellness_range(api_key: str, oldest: str, newest: str) -> List[Dict[str, Any]]:
    resp = requests.get(
        f"{INTERVALS_BASE_URL}/wellness",
        params={"oldest": oldest, "newest": newest},
        auth=("API_KEY", api_key),
        timeout=15,
    )
    if resp.status_code != 200:
        logger.warning(f"intervals.icu wellness range returned {resp.status_code}")
        return []
    data = resp.json()
    return data if isinstance(data, list) else []


def _day_values(w: Dict[str, Any]) -> Dict[str, Any]:
    """Build the attribute->Decimal/str map for one API day row.

    HRV is normalized (rMSSD first else SDNN) into `hrv` + `hrv_kind`; the raw
    `hrvSDNN` is also kept so a reader can see the source. Absent/non-finite
    values are simply omitted here (the caller turns omissions into REMOVEs)."""
    values: Dict[str, Any] = {}
    for key in _NUMERIC_FIELDS:
        d = _to_decimal(w.get(key))
        if d is not None:
            values[key] = d
    for key in _STRING_FIELDS:
        v = w.get(key)
        if v is not None and v != '':
            values[key] = str(v)
    hrv = _to_decimal(wellness_hrv(w))
    if hrv is not None:
        values['hrv'] = hrv
        kind = wellness_hrv_kind(w)
        if kind:
            values['hrv_kind'] = kind
    sdnn = _to_decimal(w.get('hrvSDNN'))
    if sdnn is not None:
        values['hrvSDNN'] = sdnn
    return values


def _upsert_day(table: Any, user_id: str, day: str, values: Dict[str, Any]) -> None:
    """SET the present fields, REMOVE the owned fields that are absent for this
    day, in a single update_item. `synced_at` is always set. Only called for a
    day actually present in the API response."""
    set_parts = ["synced_at = :synced_at"]
    names: Dict[str, str] = {}
    attr_values: Dict[str, Any] = {":synced_at": datetime.now(timezone.utc).isoformat()}

    for i, (key, val) in enumerate(values.items()):
        ph_name = f"#f{i}"
        ph_val = f":v{i}"
        names[ph_name] = key
        attr_values[ph_val] = val
        set_parts.append(f"{ph_name} = {ph_val}")

    remove_keys = [k for k in _DAY_ATTRS if k not in values]
    remove_parts = []
    for j, key in enumerate(remove_keys):
        ph_name = f"#r{j}"
        names[ph_name] = key
        remove_parts.append(ph_name)

    expr = "SET " + ", ".join(set_parts)
    if remove_parts:
        expr += " REMOVE " + ", ".join(remove_parts)

    table.update_item(
        Key={'user_id': user_id, 'sk': f"day#{day}"},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=attr_values,
    )


def _sync_window(table: Any, user_id: str, api_key: str, oldest: str, newest: str) -> int:
    """Fetch [oldest, newest] and upsert every day PRESENT in the response.
    Returns the number of day rows written."""
    rows = _fetch_wellness_range(api_key, oldest, newest)
    written = 0
    for w in rows:
        day = w.get('id')  # intervals.icu wellness row id is the YYYY-MM-DD date
        if not day:
            continue
        _upsert_day(table, user_id, str(day)[:10], _day_values(w))
        written += 1
    return written


def _backfill(table: Any, user_id: str, api_key: str, today, days: int) -> int:
    """Backfill `days` (clamped to BACKFILL_MAX_DAYS) in 90-day slices."""
    days = max(1, min(int(days), BACKFILL_MAX_DAYS))
    total = 0
    end = today
    remaining = days
    while remaining > 0:
        span = min(BACKFILL_SLICE_DAYS, remaining)
        start = end - timedelta(days=span - 1)
        total += _sync_window(table, user_id, api_key,
                              start.isoformat(), end.isoformat())
        end = start - timedelta(days=1)
        remaining -= span
    return total


@metrics.log_metrics
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    event = event or {}
    user_id = CAMPUS_OWNER_STRAVA_ID or os.environ.get('DEFAULT_USER_ID', '')

    # Fail closed: no owner, or config unreadable, or module disabled -> no writes.
    if not user_id:
        logger.warning("WellnessSync: no CAMPUS_OWNER_STRAVA_ID; nothing to do")
        return {'statusCode': 200, 'message': 'no owner configured'}

    config = _module_config(user_id)
    if config is None:
        logger.warning("WellnessSync: module config unreadable; failing closed")
        return {'statusCode': 200, 'message': 'config unreadable, skipped'}
    if not config.get('enabled', False):
        logger.info("WellnessSync: intervals.icu module disabled; skipping")
        return {'statusCode': 200, 'message': 'module disabled'}

    api_key = _get_api_key()
    if not api_key:
        logger.warning("WellnessSync: no intervals.icu API key; skipping")
        metrics.add_metric(name="WellnessSyncFailed", unit=MetricUnit.Count, value=1)
        return {'statusCode': 200, 'message': 'no api key'}

    table = dynamodb.Table(WELLNESS_TABLE)
    now = datetime.now(timezone.utc)
    today = paris_date(now)

    try:
        backfill_days = event.get('backfill_days')
        if backfill_days:
            written = _backfill(table, user_id, api_key, today, backfill_days)
        else:
            oldest = (today - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()
            written = _sync_window(table, user_id, api_key, oldest, today.isoformat())
    except requests.exceptions.RequestException as exc:
        logger.warning(f"WellnessSync network error: {exc}")
        metrics.add_metric(name="WellnessSyncFailed", unit=MetricUnit.Count, value=1)
        return {'statusCode': 200, 'message': 'network error', 'days_written': 0}
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"WellnessSync failed: {exc}")
        metrics.add_metric(name="WellnessSyncFailed", unit=MetricUnit.Count, value=1)
        return {'statusCode': 500, 'error': 'sync failed'}

    metrics.add_metric(name="WellnessDaysWritten", unit=MetricUnit.Count, value=written)

    # Lot C: rebuild today's morning brief from the data just synced.
    brief_built = False
    try:
        from webhooks.morning_brief import build_and_store_brief
        build_and_store_brief(table, user_id, today, now)
        brief_built = True
    except Exception as exc:  # noqa: BLE001 - brief is best-effort, never blocks the sync
        logger.warning(f"Morning brief build failed (non-fatal): {exc}")

    logger.info("WellnessSync complete", extra={'days_written': written, 'brief_built': brief_built})
    return {'statusCode': 200, 'days_written': written, 'brief_built': brief_built}
