"""Lot C — deterministic morning brief, built by WellnessSync after each pass.

No LLM, no notification. Writes one `brief#YYYY-MM-DD` row (overwritten each
pass, cost nil). Contents:
  - a traffic light (green/orange/red/unknown) from HRV, resting HR, sleep, form,
  - every signal visible with its as_of date and baseline (missing ones listed),
  - the next unfinished Campus session (effective_status; no per-session date),
  - Open-Meteo forecast for 07:00 and 18:00 Paris (5 s timeout; coordinates from
    the CDK context `brief_location` "lat,lon" rounded to 0.1 deg; absent -> no
    weather), with a CC-BY attribution string.

Thresholds are written here and unit-tested.
"""

import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import requests
from boto3.dynamodb.conditions import Key

from shared.campus_status import STATUS_DONE, STATUS_SKIP, effective_status
from shared.logger import get_logger

logger = get_logger("morning-brief")

COACHING_SESSIONS_TABLE = os.environ.get('COACHING_SESSIONS_TABLE', 'strava-ai-boost-campus-coaching-sessions')
BRIEF_LOCATION = os.environ.get('BRIEF_LOCATION', '')  # "lat,lon"

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_TIMEOUT_S = 5
WEATHER_ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
WEATHER_SLOTS = ("07:00", "18:00")

BASELINE_DAYS = 60
SLEEP_BASELINE_DAYS = 7
STALE_AFTER_DAYS = 1  # a signal older than J-1 (Paris) is "non dispo"

# Light thresholds (deviation from baseline). Written here and tested.
HRV_WARN_DROP = 0.08    # -8%
HRV_BAD_DROP = 0.15     # -15%
RHR_WARN_RISE = 3.0     # +3 bpm
RHR_BAD_RISE = 6.0      # +6 bpm
SLEEP_WARN_DROP_S = 3600    # -1 h
SLEEP_BAD_DROP_S = 7200     # -2 h
FORM_WARN = -15.0
FORM_BAD = -25.0


def _f(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _read_days(table: Any, user_id: str, since: str, until: str) -> List[Dict[str, Any]]:
    """Day rows in [since, until] (inclusive), ascending by sk."""
    resp = table.query(
        KeyConditionExpression=Key('user_id').eq(user_id)
        & Key('sk').between(f"day#{since}", f"day#{until}"),
    )
    return resp.get('Items', [])


def _series(days: List[Dict[str, Any]], field: str) -> List[Tuple[str, float]]:
    out = []
    for d in days:
        v = _f(d.get(field))
        if v is not None:
            out.append((d['sk'][len('day#'):], v))
    out.sort(key=lambda x: x[0])
    return out


def _latest(series: List[Tuple[str, float]]) -> Optional[Tuple[str, float]]:
    return series[-1] if series else None


def _baseline(series: List[Tuple[str, float]], exclude_last: bool = True) -> Optional[float]:
    vals = [v for _, v in series]
    if exclude_last and len(vals) >= 2:
        vals = vals[:-1]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def _is_stale(as_of: Optional[str], today) -> bool:
    if not as_of:
        return True
    try:
        d = datetime.strptime(as_of, '%Y-%m-%d').date()
    except ValueError:
        return True
    return (today - d).days > STALE_AFTER_DAYS


def _hrv_series_same_kind(days: List[Dict[str, Any]]) -> List[Tuple[str, float]]:
    """HRV series restricted to the latest day's kind so SDNN and rMSSD are never
    mixed on one baseline."""
    kinded = [(d['sk'][len('day#'):], _f(d.get('hrv')), d.get('hrv_kind'))
              for d in days if _f(d.get('hrv')) is not None]
    kinded.sort(key=lambda x: x[0])
    if not kinded:
        return []
    latest_kind = kinded[-1][2]
    return [(day, v) for day, v, k in kinded if k == latest_kind]


def _signal(key: str, series: List[Tuple[str, float]], today,
            baseline_days: int) -> Optional[Dict[str, Any]]:
    """Build one brief signal {key,value,baseline,status,as_of} or None if absent.

    status: ok/warn/bad from the thresholds, or 'missing' when stale (excluded
    from the light by the caller)."""
    latest = _latest(series)
    if latest is None:
        return None
    as_of, value = latest
    window = [(d, v) for d, v in series
              if d >= (today - timedelta(days=baseline_days)).isoformat()]
    baseline = _baseline(window)
    stale = _is_stale(as_of, today)
    status = 'missing' if stale else _status_for(key, value, baseline)
    return {
        'key': key,
        'value': round(value, 1),
        'baseline': baseline,
        'status': status,
        'as_of': as_of,
    }


def _status_for(key: str, value: float, baseline: Optional[float]) -> str:
    # Form is absolute (CTL-ATL): it needs no baseline, so evaluate it first.
    if key == 'form':
        if value <= FORM_BAD:
            return 'bad'
        if value <= FORM_WARN:
            return 'warn'
        return 'ok'
    if baseline is None:
        return 'ok'
    if key == 'hrv':
        drop = (baseline - value) / baseline if baseline else 0
        if drop >= HRV_BAD_DROP:
            return 'bad'
        if drop >= HRV_WARN_DROP:
            return 'warn'
        return 'ok'
    if key == 'resting_hr':
        rise = value - baseline
        if rise >= RHR_BAD_RISE:
            return 'bad'
        if rise >= RHR_WARN_RISE:
            return 'warn'
        return 'ok'
    if key == 'sleep':
        drop = baseline - value
        if drop >= SLEEP_BAD_DROP_S:
            return 'bad'
        if drop >= SLEEP_WARN_DROP_S:
            return 'warn'
        return 'ok'
    return 'ok'


def _light(signals: List[Dict[str, Any]]) -> str:
    """green/orange/red from the non-stale signals; unknown if none are fresh."""
    fresh = [s for s in signals if s['status'] != 'missing']
    if not fresh:
        return 'unknown'
    statuses = {s['status'] for s in fresh}
    if 'bad' in statuses:
        return 'red'
    if 'warn' in statuses:
        return 'orange'
    return 'green'


def _next_campus_session(now: datetime) -> Optional[Dict[str, Any]]:
    """First not-done session of the current ISO week, in plan order. Campus has
    no per-session date, so this is the next unfinished item, not a dated one."""
    try:
        import boto3
        from shared.iso_week import iso_week_label
        ddb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'eu-west-1'))
        table = ddb.Table(COACHING_SESSIONS_TABLE)
        week_iso = iso_week_label(now.isoformat())
        resp = table.query(
            KeyConditionExpression=Key('session_date').eq(f"week-{week_iso}"),
        )
        sessions = resp.get('Items', [])
        sessions.sort(key=lambda s: int(s.get('training_index', 0) or 0))
        for s in sessions:
            st = effective_status(s)
            if st not in (STATUS_DONE, STATUS_SKIP):
                dur = s.get('expected_duration_min')
                return {
                    'title': s.get('title', ''),
                    'training_type': s.get('training_type', ''),
                    'duration_min': int(dur) if dur is not None else None,
                }
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"next Campus session lookup failed (non-fatal): {exc}")
    return None


def _coords() -> Optional[Tuple[float, float]]:
    """Parse BRIEF_LOCATION "lat,lon", rounded to 0.1 deg. None if absent/bad."""
    if not BRIEF_LOCATION:
        return None
    try:
        lat_s, lon_s = BRIEF_LOCATION.split(',')
        return round(float(lat_s), 1), round(float(lon_s), 1)
    except (ValueError, AttributeError):
        return None


def _weather(today) -> List[Dict[str, Any]]:
    """Open-Meteo forecast for the 07:00 and 18:00 Paris slots. 5 s timeout;
    any failure (or no coordinates) returns []."""
    coords = _coords()
    if coords is None:
        return []
    lat, lon = coords
    try:
        resp = requests.get(
            OPEN_METEO_URL,
            params={
                'latitude': lat, 'longitude': lon,
                'hourly': 'temperature_2m,wind_speed_10m,precipitation',
                'timezone': 'Europe/Paris',
                'start_date': today.isoformat(), 'end_date': today.isoformat(),
            },
            timeout=OPEN_METEO_TIMEOUT_S,
        )
        if resp.status_code != 200:
            return []
        hourly = resp.json().get('hourly', {})
        times = hourly.get('time', [])
        temps = hourly.get('temperature_2m', [])
        winds = hourly.get('wind_speed_10m', [])
        precs = hourly.get('precipitation', [])
        out = []
        for slot in WEATHER_SLOTS:
            target = f"{today.isoformat()}T{slot}"
            if target in times:
                i = times.index(target)
                out.append({
                    'slot': slot,
                    'temp_c': _f(temps[i]) if i < len(temps) else None,
                    'wind_kmh': _f(winds[i]) if i < len(winds) else None,
                    'precip_mm': _f(precs[i]) if i < len(precs) else None,
                })
        return out
    except requests.exceptions.RequestException as exc:
        logger.warning(f"Open-Meteo request failed (brief without weather): {exc}")
        return []


def _form_series(days: List[Dict[str, Any]]) -> List[Tuple[str, float]]:
    """Form = CTL - ATL per day (both must be present)."""
    out = []
    for d in days:
        ctl, atl = _f(d.get('ctl')), _f(d.get('atl'))
        if ctl is not None and atl is not None:
            out.append((d['sk'][len('day#'):], round(ctl - atl, 1)))
    out.sort(key=lambda x: x[0])
    return out


def build_brief(table: Any, user_id: str, today, now: datetime) -> Dict[str, Any]:
    """Reads the wellness day rows + Campus + weather and returns the brief dict.
    Separated from the write for testability."""
    since = (today - timedelta(days=BASELINE_DAYS)).isoformat()
    days = _read_days(table, user_id, since, today.isoformat())

    hrv_series = _hrv_series_same_kind(days)
    hrv_sig = _signal('hrv', hrv_series, today, BASELINE_DAYS)
    if hrv_sig is not None:
        latest_day = max((d for d in days if _f(d.get('hrv')) is not None),
                         key=lambda d: d['sk'], default=None)
        if latest_day is not None:
            hrv_sig['kind'] = latest_day.get('hrv_kind')

    signals: List[Dict[str, Any]] = []
    for sig in (
        hrv_sig,
        _signal('resting_hr', _series(days, 'restingHR'), today, BASELINE_DAYS),
        _signal('sleep', _series(days, 'sleepSecs'), today, SLEEP_BASELINE_DAYS),
        _signal('form', _form_series(days), today, BASELINE_DAYS),
    ):
        if sig is not None:
            signals.append(sig)

    present_keys = {s['key'] for s in signals}
    missing = [k for k in ('hrv', 'resting_hr', 'sleep', 'form') if k not in present_keys]
    # a stale signal is also "missing" from the light
    missing += [s['key'] for s in signals if s['status'] == 'missing' and s['key'] not in missing]

    weather = _weather(today)
    return {
        'sk': f"brief#{today.isoformat()}",
        'date': today.isoformat(),
        'built_at': now.isoformat(),
        'light': _light(signals),
        'signals': signals,
        'missing': missing,
        'next_session': _next_campus_session(now),
        'weather': weather,
        'weather_attribution': WEATHER_ATTRIBUTION if weather else None,
    }


def _to_dynamo(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo(v) for v in obj]
    return obj


def build_and_store_brief(table: Any, user_id: str, today, now: datetime) -> Dict[str, Any]:
    brief = build_brief(table, user_id, today, now)
    item = {'user_id': user_id, **_to_dynamo(brief)}
    table.put_item(Item=item)
    logger.info("Morning brief stored", extra={'date': brief['date'], 'light': brief['light']})
    return brief
