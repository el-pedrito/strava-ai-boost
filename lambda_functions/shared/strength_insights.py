"""Pure strength-insight aggregation for the Coach page.

Builds ``trends.strength_insights`` from the normalised ``strength_history``
entries. No I/O, no DynamoDB, no clock except an injectable "today" so tests are
deterministic. ``dashboard_api`` only wires this in, inside its own guard.

Payload contract (PLAN-v4 §3 + PLAN-v5):

    {
      counting_rule: str,
      weeks: [{week: "YYYY-Www", partial: bool,
               groups: {<group>: {logged: num, campus_plan: num}},   # all 10 keys
               explosivite: {logged, campus_plan},
               autre: {logged, campus_plan}}],
      push_pull: [{week, push, pull, ratio|null}],      # logged sets only, last 4 weeks
      records: [...],                                   # see _build_records
      unmapped_exercises: [{exercise, reason}],
      mixed_exercises: [{exercise, note_key}],
    }

Set counting (PLAN-v2 F1 / PLAN-v4 §6):
- a set counts when it has ``reps > 0`` or ``duration_s > 0``;
- the count is the number of valid ``sets_detail`` rows;
- a flat ``sets`` fallback is used ONLY when there is no usable detail AND the
  flat row itself has ``reps > 0`` or a duration.
Credit: ``group_weights`` (primary 1.0, secondary 0.5). Campus-plan sets land in
the ``campus_plan`` segment; everything else in ``logged``.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .numeric import to_finite_float
from .strength_exercises import canonicalize_exercise_name
from .strength_muscles import (
    AUTRE,
    EXPLOSIVITE,
    MUSCLE_GROUPS,
    PULL,
    PUSH,
    lookup_exercise,
    mixed_exercises as MIXED_EXERCISES,
)

WINDOW_WEEKS = 8
PUSH_PULL_WEEKS = 4

COUNTING_RULE_KEY = 'coach.strength.insights.countingRule'

CAMPUS_PLAN = 'campus_plan'
LOGGED = 'logged'

# Bodyweight exercises keep a distinct record shape (reps / weighted-reps), never
# a top-weight. Keyed by canonical name.
BODYWEIGHT_RECORD_NAMES = frozenset({'Tractions', 'Dips', 'Pompes'})

# Per-side notation tokens, same set as content_generator.py:1048-1050. One match
# anywhere in a session's description taints every exercise in that session.
PER_SIDE_RE = re.compile(
    r'/c\b|/cote|/côté|par\s+cote|par\s+côté|each\s+side|/side',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Week helpers
# ---------------------------------------------------------------------------

def _week_label(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _window_weeks(today: date, n: int = WINDOW_WEEKS) -> List[str]:
    """``n`` consecutive ISO week labels ending at ``today``'s week."""
    labels: List[str] = []
    cursor = today
    for _ in range(n):
        labels.append(_week_label(cursor))
        cursor = cursor - timedelta(weeks=1)
    labels.reverse()
    return labels


def _entry_date(entry: Dict[str, Any]) -> Optional[date]:
    raw = entry.get('date')
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Set counting
# ---------------------------------------------------------------------------

def _row_counts(row: Dict[str, Any]) -> bool:
    """A sets_detail row counts when it has reps > 0 or duration_s > 0."""
    reps = to_finite_float(row.get('reps'))
    if reps is not None and reps > 0:
        return True
    duration = to_finite_float(row.get('duration_s'))
    return duration is not None and duration > 0


def _set_count(parsed_set: Dict[str, Any]) -> int:
    """Number of counted sets for one parsed_set.

    Uses the valid ``sets_detail`` rows; falls back to the flat ``sets`` only
    when detail is absent/empty AND the flat row itself is countable (reps > 0 or
    a duration).
    """
    detail = parsed_set.get('sets_detail')
    if isinstance(detail, list) and detail:
        counted = sum(1 for row in detail if isinstance(row, dict) and _row_counts(row))
        if counted:
            return counted
        # Detail present but nothing countable -> no silent flat fallback.
        return 0
    # Flat fallback.
    flat_reps = to_finite_float(parsed_set.get('reps'))
    flat_duration = to_finite_float(parsed_set.get('duration_s'))
    countable = (flat_reps is not None and flat_reps > 0) or (
        flat_duration is not None and flat_duration > 0
    )
    if not countable:
        return 0
    sets = to_finite_float(parsed_set.get('sets'))
    if sets is None or sets <= 0:
        return 0
    return int(sets)


def _empty_segment() -> Dict[str, float]:
    return {LOGGED: 0.0, CAMPUS_PLAN: 0.0}


def _empty_week(week: str, partial: bool) -> Dict[str, Any]:
    groups = {g: _empty_segment() for g in MUSCLE_GROUPS}
    return {
        'week': week,
        'partial': partial,
        'groups': groups,
        EXPLOSIVITE: _empty_segment(),
        AUTRE: _empty_segment(),
    }


def _round1(value: float) -> float:
    return round(value + 0.0, 1)


# ---------------------------------------------------------------------------
# Weekly muscle sets + push/pull
# ---------------------------------------------------------------------------

def _build_weeks_and_push_pull(
    entries: List[Dict[str, Any]],
    today: date,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    labels = _window_weeks(today, WINDOW_WEEKS)
    current_week = labels[-1]
    index = {label: _empty_week(label, label == current_week) for label in labels}
    label_set = set(labels)

    # push/pull accumulators (logged only), keyed by week label.
    push_pull: Dict[str, Dict[str, float]] = {
        label: {PUSH: 0.0, PULL: 0.0} for label in labels
    }

    unmapped: Dict[str, str] = {}

    for entry in entries:
        d = _entry_date(entry)
        if d is None:
            continue
        label = _week_label(d)
        if label not in label_set:
            continue
        source = CAMPUS_PLAN if entry.get('sets_source') == CAMPUS_PLAN else LOGGED
        parsed = entry.get('parsed_sets')
        if not isinstance(parsed, list):
            continue
        week_bucket = index[label]
        for parsed_set in parsed:
            if not isinstance(parsed_set, dict):
                continue
            raw_name = parsed_set.get('exercise')
            if not raw_name:
                continue
            count = _set_count(parsed_set)
            if count <= 0:
                continue
            mapping = lookup_exercise(str(raw_name))
            # Muscle credit.
            if mapping.autre:
                week_bucket[AUTRE][source] += count
                unmapped[canonicalize_exercise_name(str(raw_name))] = mapping.autre_reason
            else:
                if mapping.explosivite:
                    week_bucket[EXPLOSIVITE][source] += count
                for group, weight in mapping.group_weights.items():
                    if group in week_bucket['groups']:
                        week_bucket['groups'][group][source] += count * weight
            # push/pull: logged sets only, one set = 1 for its pattern.
            if source == LOGGED and mapping.pattern in (PUSH, PULL):
                push_pull[label][mapping.pattern] += count

    # Round the accumulated weekly figures.
    weeks_out: List[Dict[str, Any]] = []
    for label in labels:
        wk = index[label]
        for group in wk['groups']:
            seg = wk['groups'][group]
            seg[LOGGED] = _round1(seg[LOGGED])
            seg[CAMPUS_PLAN] = _round1(seg[CAMPUS_PLAN])
        for key in (EXPLOSIVITE, AUTRE):
            wk[key][LOGGED] = _round1(wk[key][LOGGED])
            wk[key][CAMPUS_PLAN] = _round1(wk[key][CAMPUS_PLAN])
        weeks_out.append(wk)

    # push/pull on the last PUSH_PULL_WEEKS weeks of the window.
    push_pull_out: List[Dict[str, Any]] = []
    for label in labels[-PUSH_PULL_WEEKS:]:
        pp = push_pull[label]
        push = _round1(pp[PUSH])
        pull = _round1(pp[PULL])
        ratio = _round1(push / pull) if pull > 0 else None
        push_pull_out.append({'week': label, 'push': push, 'pull': pull, 'ratio': ratio})

    unmapped_out = [
        {'exercise': name, 'reason': reason}
        for name, reason in sorted(unmapped.items())
    ]
    return weeks_out, push_pull_out, unmapped_out


# ---------------------------------------------------------------------------
# e1RM
# ---------------------------------------------------------------------------

def _epley_1rm(load: float, reps: int) -> float:
    """Epley estimate, with reps == 1 -> load, rounded to 0.5 kg."""
    if reps == 1:
        estimate = load
    else:
        estimate = load * (1.0 + reps / 30.0)
    return round(estimate * 2.0) / 2.0


def _valid_reps(raw: Any) -> Optional[int]:
    """Integer reps in 1..10, else None (above 10 Epley is unreliable)."""
    reps = to_finite_float(raw)
    if reps is None or not reps.is_integer():
        return None
    reps_int = int(reps)
    if 1 <= reps_int <= 10:
        return reps_int
    return None


def _best_set_e1rm(sets_detail: List[Dict[str, Any]]) -> Optional[float]:
    """Best e1RM over a day's valid sets, or None."""
    best: Optional[float] = None
    for row in sets_detail:
        if not isinstance(row, dict):
            continue
        load = to_finite_float(row.get('weight_kg'))
        reps = _valid_reps(row.get('reps'))
        if load is None or load <= 0 or reps is None:
            continue
        value = _epley_1rm(load, reps)
        if best is None or value > best:
            best = value
    return best


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def _per_side_noted(entry: Dict[str, Any]) -> bool:
    description = entry.get('description')
    if not isinstance(description, str):
        return False
    return bool(PER_SIDE_RE.search(description))


def _per_exercise_incomplete(entry: Dict[str, Any]) -> Dict[str, bool]:
    """Map canonical exercise name -> volume_incomplete from the entry's per_exercise."""
    out: Dict[str, bool] = {}
    for row in entry.get('per_exercise') or []:
        if not isinstance(row, dict):
            continue
        name = canonicalize_exercise_name(str(row.get('exercise') or ''))
        if name:
            out[name] = bool(row.get('volume_incomplete'))
    return out


def _per_exercise_volume(entry: Dict[str, Any]) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for row in entry.get('per_exercise') or []:
        if not isinstance(row, dict):
            continue
        name = canonicalize_exercise_name(str(row.get('exercise') or ''))
        if name:
            out[name] = to_finite_float(row.get('volume_kg'))
    return out


def _max_load(sets_detail: List[Dict[str, Any]]) -> Optional[float]:
    best: Optional[float] = None
    for row in sets_detail:
        if not isinstance(row, dict):
            continue
        load = to_finite_float(row.get('weight_kg'))
        if load is None:
            continue
        if best is None or load > best:
            best = load
    return best


def _max_reps(sets_detail: List[Dict[str, Any]]) -> Optional[int]:
    best: Optional[int] = None
    for row in sets_detail:
        if not isinstance(row, dict):
            continue
        reps = to_finite_float(row.get('reps'))
        if reps is None or not reps.is_integer() or reps <= 0:
            continue
        reps_int = int(reps)
        if best is None or reps_int > best:
            best = reps_int
    return best


def _best_weighted_bw(sets_detail: List[Dict[str, Any]]) -> Optional[Tuple[int, float]]:
    """Best (reps, added_weight) over sets with an explicit positive load."""
    best: Optional[Tuple[int, float]] = None
    for row in sets_detail:
        if not isinstance(row, dict):
            continue
        load = to_finite_float(row.get('weight_kg'))
        reps = to_finite_float(row.get('reps'))
        if load is None or load <= 0 or reps is None or not reps.is_integer() or reps <= 0:
            continue
        candidate = (int(reps), load)
        # Order weighted records by load, then reps.
        if best is None or (load, int(reps)) > (best[1], best[0]):
            best = candidate
    return best


def _pick_earliest(candidates: List[Tuple[float, str]]) -> Optional[Tuple[float, str]]:
    """Max value; ties broken by the earliest date."""
    if not candidates:
        return None
    return sorted(candidates, key=lambda vd: (-vd[0], vd[1]))[0]


def _build_records(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One record row per canonical exercise with >= 2 sessions.

    Loaded lifts: best top weight, best e1RM (eligible, non-Campus, non-mixed,
    non-notation-mixed only), best session volume (volume_incomplete excluded).
    Bodyweight lifts: best reps, best weighted set. Ties earliest date.
    """
    by_exercise: Dict[str, Dict[str, Any]] = {}

    # Session-level notation taint: which exercises had any per-side-noted session
    # and any plain session.
    per_side_seen: Dict[str, bool] = {}
    plain_seen: Dict[str, bool] = {}

    for entry in entries:
        d = _entry_date(entry)
        if d is None:
            continue
        parsed = entry.get('parsed_sets')
        if not isinstance(parsed, list):
            continue
        session_per_side = _per_side_noted(entry)
        is_campus = entry.get('sets_source') == CAMPUS_PLAN
        incomplete_map = _per_exercise_incomplete(entry)
        volume_map = _per_exercise_volume(entry)
        date_str = d.isoformat()

        for parsed_set in parsed:
            if not isinstance(parsed_set, dict):
                continue
            raw_name = parsed_set.get('exercise')
            if not raw_name:
                continue
            name = canonicalize_exercise_name(str(raw_name))
            if not name:
                continue
            mapping = lookup_exercise(str(raw_name))
            if mapping.autre:
                # Unmapped: no record row (surfaced in unmapped_exercises instead).
                continue
            if session_per_side:
                per_side_seen[name] = True
            else:
                plain_seen[name] = True

            detail = parsed_set.get('sets_detail')
            detail = detail if isinstance(detail, list) else []

            rec = by_exercise.setdefault(name, {
                'name': name,
                'is_bodyweight': name in BODYWEIGHT_RECORD_NAMES,
                'is_mixed': name in MIXED_EXERCISES,
                'session_dates': set(),
                'top_weight': [],      # (value, date)
                'e1rm': [],            # (value, date)
                'volume': [],          # (value, date)
                'reps_bw': [],         # (reps, date)
                'weighted_bw': [],     # (reps, added, date)
                'last_date': date_str,
            })
            rec['session_dates'].add(date_str)
            rec['last_date'] = max(rec['last_date'], date_str)

            if rec['is_bodyweight']:
                best_reps = _max_reps(detail)
                if best_reps is not None:
                    rec['reps_bw'].append((best_reps, date_str))
                weighted = _best_weighted_bw(detail)
                if weighted is not None:
                    rec['weighted_bw'].append((weighted[0], weighted[1], date_str))
            else:
                top = _max_load(detail)
                if top is not None:
                    rec['top_weight'].append((top, date_str))
                # Best volume from the authoritative per_exercise figure.
                vol = volume_map.get(name)
                if vol is not None and not incomplete_map.get(name, False):
                    rec['volume'].append((vol, date_str))
                # e1RM only on eligible, non-Campus sessions.
                if mapping.e1rm and not is_campus:
                    best = _best_set_e1rm(detail)
                    if best is not None:
                        rec['e1rm'].append((best, date_str))

    records: List[Dict[str, Any]] = []
    for name, rec in by_exercise.items():
        if len(rec['session_dates']) < 2:
            continue
        notation_mixed = bool(per_side_seen.get(name) and plain_seen.get(name))
        is_mixed = rec['is_mixed']

        row: Dict[str, Any] = {
            'exercise': name,
            'last_date': rec['last_date'],
            'notation_mixed': notation_mixed,
        }

        if rec['is_bodyweight']:
            row['kind'] = 'bodyweight'
            row['load_label'] = None
            row['top_weight_kg'] = None
            row['top_weight_date'] = None
            row['e1rm_kg'] = None
            row['e1rm_date'] = None
            row['best_volume_kg'] = None
            row['best_volume_date'] = None
            best_reps = _pick_earliest([(float(r), d) for r, d in rec['reps_bw']])
            row['best_reps_bw'] = (
                {'reps': int(best_reps[0]), 'date': best_reps[1]} if best_reps else None
            )
            # weighted: max load then reps, ties earliest date.
            weighted = None
            if rec['weighted_bw']:
                weighted = sorted(
                    rec['weighted_bw'], key=lambda x: (-x[1], -x[0], x[2])
                )[0]
            row['best_weighted_bw'] = (
                {'reps': weighted[0], 'added_weight_kg': weighted[1], 'date': weighted[2]}
                if weighted else None
            )
        else:
            row['kind'] = 'loaded'
            row['load_label'] = 'total_noted'
            row['best_reps_bw'] = None
            row['best_weighted_bw'] = None

            top = _pick_earliest(rec['top_weight'])
            # Mixed and notation-mixed exercises get no top-weight record.
            if top and not is_mixed and not notation_mixed:
                row['top_weight_kg'] = _round1(top[0])
                row['top_weight_date'] = top[1]
            else:
                row['top_weight_kg'] = None
                row['top_weight_date'] = None

            e1rm = _pick_earliest(rec['e1rm'])
            if e1rm and not is_mixed and not notation_mixed:
                row['e1rm_kg'] = round(e1rm[0] * 2.0) / 2.0
                row['e1rm_date'] = e1rm[1]
            else:
                row['e1rm_kg'] = None
                row['e1rm_date'] = None

            vol = _pick_earliest(rec['volume'])
            # notation_mixed also excludes volume (same tainted load).
            if vol and not notation_mixed:
                row['best_volume_kg'] = _round1(vol[0])
                row['best_volume_date'] = vol[1]
            else:
                row['best_volume_kg'] = None
                row['best_volume_date'] = None

        records.append(row)

    # Sort by last session date, descending; cap at 15.
    records.sort(key=lambda r: r['last_date'], reverse=True)
    return records[:15]


# ---------------------------------------------------------------------------
# e1RM eligibility / mixed / notation flags for the progression series
# ---------------------------------------------------------------------------

def exercise_flags(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, bool]]:
    """Per canonical exercise: {e1rm_eligible, mixed, notation_mixed}.

    e1rm_eligible is True only when the map says e1rm AND the exercise is not
    mixed AND its sessions do not mix per-side and plain notation.
    """
    per_side_seen: Dict[str, bool] = {}
    plain_seen: Dict[str, bool] = {}
    seen: Dict[str, bool] = {}
    map_e1rm: Dict[str, bool] = {}
    is_mixed: Dict[str, bool] = {}

    for entry in entries:
        parsed = entry.get('parsed_sets')
        if not isinstance(parsed, list):
            continue
        session_per_side = _per_side_noted(entry)
        for parsed_set in parsed:
            if not isinstance(parsed_set, dict):
                continue
            raw_name = parsed_set.get('exercise')
            if not raw_name:
                continue
            name = canonicalize_exercise_name(str(raw_name))
            if not name:
                continue
            mapping = lookup_exercise(str(raw_name))
            seen[name] = True
            map_e1rm[name] = mapping.e1rm
            is_mixed[name] = name in MIXED_EXERCISES
            if session_per_side:
                per_side_seen[name] = True
            else:
                plain_seen[name] = True

    flags: Dict[str, Dict[str, bool]] = {}
    for name in seen:
        notation_mixed = bool(per_side_seen.get(name) and plain_seen.get(name))
        mixed = is_mixed.get(name, False)
        eligible = map_e1rm.get(name, False) and not mixed and not notation_mixed
        flags[name] = {
            'e1rm_eligible': eligible,
            'mixed': mixed,
            'notation_mixed': notation_mixed,
        }
    return flags


def per_day_e1rm(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Optional[float]]]:
    """Per canonical exercise -> {date -> best e1RM that day} for eligible lifts.

    Campus-plan sessions and non-eligible exercises contribute nothing.
    """
    flags = exercise_flags(entries)
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for entry in entries:
        d = _entry_date(entry)
        if d is None:
            continue
        if entry.get('sets_source') == CAMPUS_PLAN:
            continue
        parsed = entry.get('parsed_sets')
        if not isinstance(parsed, list):
            continue
        date_str = d.isoformat()
        for parsed_set in parsed:
            if not isinstance(parsed_set, dict):
                continue
            raw_name = parsed_set.get('exercise')
            if not raw_name:
                continue
            name = canonicalize_exercise_name(str(raw_name))
            if not name or not flags.get(name, {}).get('e1rm_eligible'):
                continue
            detail = parsed_set.get('sets_detail')
            detail = detail if isinstance(detail, list) else []
            best = _best_set_e1rm(detail)
            if best is None:
                continue
            day_map = out.setdefault(name, {})
            prev = day_map.get(date_str)
            day_map[date_str] = best if prev is None else max(prev, best)
    return out


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------

def build_strength_insights(
    entries: Optional[List[Dict[str, Any]]],
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Build the full ``strength_insights`` payload.

    Pure; raises nothing on malformed rows (they are skipped). ``today`` defaults
    to the current Europe/Paris date.
    """
    if today is None:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo('Europe/Paris')).date()

    safe_entries = [e for e in (entries or []) if isinstance(e, dict)]

    weeks, push_pull, unmapped = _build_weeks_and_push_pull(safe_entries, today)
    records = _build_records(safe_entries)

    mixed_out = [
        {'exercise': name, 'note_key': note}
        for name, note in sorted(MIXED_EXERCISES.items())
    ]

    return {
        'counting_rule': COUNTING_RULE_KEY,
        'weeks': weeks,
        'push_pull': push_pull,
        'records': records,
        'unmapped_exercises': unmapped,
        'mixed_exercises': mixed_out,
    }
