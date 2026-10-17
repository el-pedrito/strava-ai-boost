"""A4 — builder for GET /home/summary.

Pure-ish assembly of the home dashboard contract from the wellness table (health
day rows, morning brief, campus#* aggregates), the coaching-sessions table (this
week's plan), the user-config row (module flags), and the activities table
(enduraw_trend). The HTTP wrapper (auth, no-store, logging) lives in
dashboard_api.get_home_summary_response.

Contract: /tmp/home-review/CONTRACT.md. Durations in seconds, paces in s/km,
dates YYYY-MM-DD (Europe/Paris), timestamps ISO UTC. Any field may be null; a
value is never shown without its own as_of date.
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from boto3.dynamodb.conditions import Key

from shared.campus_status import STATUS_DONE, effective_status
from shared.iso_week import iso_week_label
from shared.wellness import activity_local_date, in_activity_window, paris_date

HEALTH_SERIES_DAYS = 90
HRV_BASELINE_DAYS = 60
RHR_BASELINE_DAYS = 60
SLEEP_BASELINE_DAYS = 7
STALE_AFTER_DAYS = 1
ENDURAW_TREND_WEEKS = 12


def _f(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _num(v: Any) -> Any:
    """Return a plain number (int if integral) for JSON; None passthrough."""
    f = _f(v)
    if f is None:
        return None
    return int(f) if f == int(f) else round(f, 2)


# ----------------------------------------------------------------- wellness I/O
def _read_days(table: Any, user_id: str, since: str, until: str) -> List[Dict[str, Any]]:
    resp = table.query(
        KeyConditionExpression=Key('user_id').eq(user_id)
        & Key('sk').between(f"day#{since}", f"day#{until}"),
    )
    return resp.get('Items', [])


def _read_item(table: Any, user_id: str, sk: str) -> Optional[Dict[str, Any]]:
    resp = table.get_item(Key={'user_id': user_id, 'sk': sk})
    return resp.get('Item')


def _read_prefix(table: Any, user_id: str, prefix: str) -> List[Dict[str, Any]]:
    resp = table.query(
        KeyConditionExpression=Key('user_id').eq(user_id)
        & Key('sk').begins_with(prefix),
    )
    return resp.get('Items', [])


# ----------------------------------------------------------------- health
def _day_of(item: Dict[str, Any]) -> str:
    return item['sk'][len('day#'):]


def _series(days: List[Dict[str, Any]], field: str) -> List[Tuple[str, float]]:
    out = [(_day_of(d), _f(d.get(field))) for d in days]
    out = [(d, v) for d, v in out if v is not None]
    out.sort(key=lambda x: x[0])
    return out


def _hrv_series_same_kind(days: List[Dict[str, Any]]) -> Tuple[List[Tuple[str, float]], Optional[str]]:
    kinded = [(_day_of(d), _f(d.get('hrv')), d.get('hrv_kind'))
              for d in days if _f(d.get('hrv')) is not None]
    kinded.sort(key=lambda x: x[0])
    if not kinded:
        return [], None
    latest_kind = kinded[-1][2]
    return [(d, v) for d, v, k in kinded if k == latest_kind], latest_kind


def _is_stale(as_of: str, today) -> bool:
    try:
        d = datetime.strptime(as_of, '%Y-%m-%d').date()
    except ValueError:
        return True
    return (today - d).days > STALE_AFTER_DAYS


def _baseline(series: List[Tuple[str, float]], today, days: int) -> Optional[float]:
    cutoff = (today - timedelta(days=days)).isoformat()
    vals = [v for d, v in series if d >= cutoff]
    if len(vals) >= 2:
        vals = vals[:-1]  # exclude the latest point from its own baseline
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)


def _health_signal(series: List[Tuple[str, float]], today, baseline_days: int,
                   baseline_key: str) -> Optional[Dict[str, Any]]:
    if not series:
        return None
    as_of, value = series[-1]
    baseline = _baseline(series, today, baseline_days)
    sig: Dict[str, Any] = {
        'value': _num(value),
        'as_of': as_of,
        'stale': _is_stale(as_of, today),
    }
    sig[baseline_key] = baseline
    sig['delta'] = round(value - baseline, 1) if baseline is not None else None
    return sig


def _simple_signal(series: List[Tuple[str, float]], today) -> Optional[Dict[str, Any]]:
    if not series:
        return None
    as_of, value = series[-1]
    return {'value': _num(value), 'as_of': as_of, 'stale': _is_stale(as_of, today)}


def _build_health(days: List[Dict[str, Any]], today) -> Dict[str, Any]:
    """Every contracted health signal is present as a key; a signal with no data
    is explicit ``null`` (never omitted, never a stale value without a date)."""
    health: Dict[str, Any] = {
        'resting_hr': None, 'hrv': None, 'sleep_s': None, 'sleep_score': None,
        'ctl': None, 'atl': None, 'form': None, 'vo2max': None, 'weight': None,
    }

    rhr = _health_signal(_series(days, 'restingHR'), today, RHR_BASELINE_DAYS, 'baseline_60d')
    if rhr:
        health['resting_hr'] = rhr

    hrv_series, kind = _hrv_series_same_kind(days)
    hrv = _health_signal(hrv_series, today, HRV_BASELINE_DAYS, 'baseline_60d')
    if hrv:
        hrv['kind'] = kind
        health['hrv'] = hrv

    sleep = _health_signal(_series(days, 'sleepSecs'), today, SLEEP_BASELINE_DAYS, 'baseline_7d')
    if sleep:
        health['sleep_s'] = sleep

    for key, field in (('sleep_score', 'sleepScore'), ('ctl', 'ctl'),
                       ('atl', 'atl'), ('vo2max', 'vo2max'), ('weight', 'weight')):
        sig = _simple_signal(_series(days, field), today)
        if sig:
            health[key] = sig

    # form = CTL - ATL (per the latest day having both).
    form_series = []
    for d in days:
        ctl, atl = _f(d.get('ctl')), _f(d.get('atl'))
        if ctl is not None and atl is not None:
            form_series.append((_day_of(d), round(ctl - atl, 1)))
    form_series.sort(key=lambda x: x[0])
    form = _simple_signal(form_series, today)
    if form:
        health['form'] = form

    return health


def _build_health_series(days: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for d in sorted(days, key=lambda x: x['sk']):
        day = _day_of(d)
        ctl, atl = _f(d.get('ctl')), _f(d.get('atl'))
        entry = {
            'date': day,
            'resting_hr': _num(d.get('restingHR')),
            'hrv': _num(d.get('hrv')),
            'hrv_kind': d.get('hrv_kind'),
            'sleep_s': _num(d.get('sleepSecs')),
            'ctl': _num(ctl),
            'atl': _num(atl),
            'form': round(ctl - atl, 1) if ctl is not None and atl is not None else None,
        }
        out.append(entry)
    return out


# ----------------------------------------------------------------- campus/race/plan
def _week_label(now: datetime) -> str:
    """ISO week of the Europe/Paris calendar date.

    Campus stores a week under its Monday 00:00 UTC ``weekDate``; the Paris
    Monday maps to that same stored week, so deriving the week from the Paris
    date (not the raw UTC instant) is what keeps the reader on the right week
    around local Monday midnight.
    """
    return iso_week_label(datetime.combine(paris_date(now), datetime.min.time()).isoformat())


def _build_modules(user_config: Dict[str, Any]) -> Dict[str, bool]:
    mc = (user_config or {}).get('modules_config', {}) or {}
    return {
        'intervals_icu': bool((mc.get('intervals_icu') or {}).get('enabled', False)),
        'campus_coach': bool((mc.get('campus_coach') or {}).get('enabled', False)),
    }


def _build_race(goal: Optional[Dict[str, Any]], current_pred: Optional[Dict[str, Any]],
                today) -> Optional[Dict[str, Any]]:
    """Full race object with explicit nulls (CONTRACT). None goal -> null;
    inactive goal -> {active: false, ...nulls}. ``target_pace_s`` is the TARGET
    pace (target_duration_s / target_distance_km), not the predicted pace."""
    if goal is None:
        return None
    race = {
        'active': bool(goal.get('active')),
        'name': None, 'type': None, 'date': None, 'days_left': None,
        'target_time_s': None, 'target_pace_s': None,
        'predicted_time_s': None, 'predicted_range_s': None, 'prediction_week': None,
    }
    if not goal.get('active'):
        return race

    comp_date_ms = goal.get('competition_date')
    if comp_date_ms:
        try:
            d = datetime.fromtimestamp(int(comp_date_ms) / 1000, tz=timezone.utc)
            race_day = paris_date(d)
            race['date'] = race_day.isoformat()
            race['days_left'] = (race_day - today).days
        except (ValueError, TypeError, OverflowError, OSError):
            pass
    race['name'] = goal.get('name') or None
    race['type'] = goal.get('type') or None
    target_time = _num(goal.get('target_duration_s'))
    race['target_time_s'] = target_time
    dist = _f(goal.get('target_distance_km'))
    if target_time is not None and dist and dist > 0:
        race['target_pace_s'] = round(float(target_time) / dist)

    if current_pred:
        pred = current_pred.get(goal.get('type', ''))
        if isinstance(pred, dict):
            race['predicted_time_s'] = _num(pred.get('time_s'))
            rng = pred.get('range_s')
            if isinstance(rng, list) and len(rng) == 2:
                race['predicted_range_s'] = [_num(rng[0]), _num(rng[1])]
            race['prediction_week'] = current_pred.get('source_week')
    return race


def _build_plan(goal: Optional[Dict[str, Any]], week_stat: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Full plan object with explicit nulls. ``week_index``/``weeks_total``/
    ``cycle_theme`` come from the current week's stored item (the single source);
    totals and volume come from the goal."""
    if not goal or not goal.get('active'):
        return None
    ws = week_stat or {}
    week_index = ws.get('week_index')
    weeks_total = ws.get('weeks_total')
    if weeks_total is None:
        weeks_total = goal.get('weeks_total')
    cycle_theme = ws.get('cycle_theme') or goal.get('cycle_theme')
    plan = {
        'week_index': _num(week_index),
        'weeks_total': _num(weeks_total),
        'cycle_theme': cycle_theme or None,
        'trainings_done': _num(goal.get('trainings_done')),
        'trainings_total': _num(goal.get('trainings_total')),
        'week_km_expected': _num(ws.get('expected_distance_km')),
        'week_km_real': _num(ws.get('real_distance_km')),
        'weekly_volume_low': _num(goal.get('weekly_volume_low')),
        'weekly_volume_high': _num(goal.get('weekly_volume_high')),
        'sessions_per_week': _num(goal.get('sessions_per_week')),
    }
    return plan


def _build_week_sessions(sessions_table: Any, now: datetime) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """This week's sessions in plan order with their effective_status, plus the
    next unfinished one. Current week is chosen by the is_current_week flag (as
    plan_workouts does), not a recomputed partition name. Campus has no per-session
    date, so there is no date field, only an order."""
    week_iso = _week_label(now)
    items = []
    resp = sessions_table.query(
        KeyConditionExpression=Key('session_date').eq(f"week-{week_iso}"),
    )
    items = resp.get('Items', [])
    if not items:
        # Fallback only when the Paris-week partition is empty. Early Monday the
        # partition exists but still carries is_current_week=False until the
        # 05:00 UTC sync: it is still this week, so it is kept (the plan, the
        # predictions and the brief use the same Paris week).
        scanned = sessions_table.scan(
            FilterExpression="is_current_week = :cw",
            ExpressionAttributeValues={":cw": True},
        ).get('Items', [])
        if scanned:
            items = scanned

    items = [s for s in items if s.get('session_date', '').startswith('week-')]
    items.sort(key=lambda s: int(s.get('training_index', 0) or 0))

    out = []
    next_session = None
    _STATUS_MAP = {'done': 'done', 'skip': 'missed', 'todo': 'todo'}
    for order, s in enumerate(items, 1):
        st = effective_status(s)
        dur = s.get('expected_duration_min')
        row = {
            'order': order,
            'title': s.get('title', ''),
            'training_type': s.get('training_type', ''),
            'status': _STATUS_MAP.get(st, 'todo'),
            'duration_min': int(dur) if dur is not None else None,
        }
        out.append(row)
        if next_session is None and st != STATUS_DONE and _STATUS_MAP.get(st) != 'missed':
            next_session = {k: row[k] for k in ('order', 'title', 'training_type', 'duration_min')}
    return out, next_session


def _build_predictions(preds: List[Dict[str, Any]], current_week: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Current week's prediction (items list per CONTRACT) + a compact history of
    the half-marathon time for the other weeks. Absent current week -> None (never
    an old one presented as current)."""
    by_week = {p.get('source_week'): p for p in preds if p.get('source_week')}
    current = by_week.get(current_week)
    current_out = None
    if current:
        items = []
        for dist in ('5km', '10km', 'half-marathon', 'marathon'):
            d = current.get(dist)
            if isinstance(d, dict):
                rng = d.get('range_s')
                items.append({
                    'distance': dist,
                    'time_s': _num(d.get('time_s')),
                    'range_s': [_num(rng[0]), _num(rng[1])] if isinstance(rng, list) and len(rng) == 2 else None,
                    'pace_s': _num(d.get('pace_s')),
                })
        current_out = {'week': current_week, 'items': items}

    history = []
    for wk in sorted(by_week):
        if wk == current_week:
            continue
        half = by_week[wk].get('half-marathon')
        if isinstance(half, dict) and half.get('time_s') is not None:
            history.append({'week': wk, 'half_marathon_time_s': _num(half.get('time_s'))})
    return current_out, history


# ----------------------------------------------------------------- brief
def _build_brief(brief_item: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not brief_item:
        return None
    out = {
        'date': brief_item.get('date'),
        'built_at': brief_item.get('built_at'),
        'light': brief_item.get('light', 'unknown'),
        'signals': _plainify(brief_item.get('signals', [])),
        'missing': list(brief_item.get('missing', [])),
        'next_session': _plainify(brief_item.get('next_session')),
        'weather': _plainify(brief_item.get('weather', [])),
        'weather_attribution': brief_item.get('weather_attribution'),
    }
    return out


# ----------------------------------------------------------------- enduraw
def _build_enduraw_trend(activities_reader, since_date: str) -> List[Dict[str, Any]]:
    """12-week trend of {date, activity_id, raw_pace_s, adjusted_pace_s, *cost_s}
    from activities carrying enduraw_metrics, dated by activity local date."""
    out = []
    for item in activities_reader():
        metrics_blob = item.get('enduraw_metrics')
        if not metrics_blob:
            continue
        if not in_activity_window(item, since_date, ''):
            continue
        if isinstance(metrics_blob, str):
            try:
                metrics_blob = json.loads(metrics_blob)
            except (json.JSONDecodeError, TypeError):
                continue
        out.append({
            'date': activity_local_date(item),
            'activity_id': item.get('activity_id'),
            'raw_pace_s': _num(metrics_blob.get('raw_pace_s')),
            'adjusted_pace_s': _num(metrics_blob.get('adjusted_pace_s')),
            'heat_cost_s': _num(metrics_blob.get('heat_cost_s')),
            'wind_cost_s': _num(metrics_blob.get('wind_cost_s')),
            'elevation_cost_s': _num(metrics_blob.get('elevation_cost_s')),
        })
    out.sort(key=lambda x: x['date'] or '')
    return out


def _plainify(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: _plainify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_plainify(v) for v in obj]
    return obj


def build_home_summary(
    wellness_table: Any,
    sessions_table: Any,
    user_config: Dict[str, Any],
    activities_reader,
    now: datetime,
    user_id: str,
) -> Dict[str, Any]:
    today = paris_date(now)
    since = (today - timedelta(days=HEALTH_SERIES_DAYS)).isoformat()

    days = _read_days(wellness_table, user_id, since, today.isoformat())
    goal = _read_item(wellness_table, user_id, 'campus#goal')
    brief_item = _read_item(wellness_table, user_id, 'brief#' + today.isoformat())
    week_iso = _week_label(now)
    week_stat = _read_item(wellness_table, user_id, f'campus#week#{week_iso}')
    preds = _read_prefix(wellness_table, user_id, 'campus#pred#')
    current_pred = next((p for p in preds if p.get('source_week') == week_iso), None)

    week_sessions, next_session = _build_week_sessions(sessions_table, now)
    predictions, predictions_history = _build_predictions(preds, week_iso)

    enduraw_since = (today - timedelta(weeks=ENDURAW_TREND_WEEKS)).isoformat()

    return _plainify({
        'generated_at': now.astimezone(timezone.utc).isoformat(),
        'modules': _build_modules(user_config),
        'brief': _build_brief(brief_item),
        'race': _build_race(goal, current_pred, today),
        'plan': _build_plan(goal, week_stat),
        'week_sessions': week_sessions,
        'next_session': next_session,
        'health': _build_health(days, today),
        'health_series': _build_health_series(days),
        'predictions': predictions,
        'predictions_history': predictions_history,
        'enduraw_trend': _build_enduraw_trend(activities_reader, enduraw_since),
    })
