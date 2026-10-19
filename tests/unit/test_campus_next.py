"""One next-session rule for /home/summary and /plan/workouts (shared.campus_next).

The two endpoints used to choose differently: Plan dropped rows without intervals
before picking, so a first open session with ``intervals: []`` was "today" on Home
and absent from Plan, which highlighted the following one. These tests feed the
SAME rows to both builders and require the same session. Invented data only.
"""
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from api import home_summary as hs  # noqa: E402
from api import plan_workouts  # noqa: E402
from shared import campus_next  # noqa: E402

# Saturday 17 Oct 2026, 08:00 Paris: ISO week 2026-W42.
NOW = datetime(2026, 10, 17, 6, 0, tzinfo=timezone.utc)
WEEK = '2026-W42'
NEXT_WEEK = '2026-W43'
WEEK_MS = plan_workouts.current_week_start_ms(NOW)
NEXT_WEEK_MS = WEEK_MS + 7 * 24 * 3600 * 1000

_INTERVALS = [
    {'type': 'warm-up', 'duration': '15 min', 'pace': 'EF (6:00/km)'},
    {'type': 'work', 'duration': '20 min', 'pace': 'Seuil (4:50/km)'},
    {'type': 'cool-down', 'duration': '10 min', 'pace': 'EF (6:00/km)'},
]


def _row(index, week=WEEK, week_ms=WEEK_MS, current=True, **extra):
    row = {
        'session_date': f'week-{week}', 'session_id': f'9_{index}' if week == WEEK else f'10_{index}',
        'week_date_iso': week, 'week_date': Decimal(week_ms), 'training_index': Decimal(index),
        'title': f'Séance {index}', 'training_type': 'Endurance', 'sport': 'road',
        'expected_duration_min': Decimal(45), 'is_current_week': current, 'is_future': not current,
        'provider_status': 'todo', 'intervals': _INTERVALS,
    }
    row.update(extra)
    return row


def _home_next_id(rows):
    week_rows = [r for r in rows if r['session_date'] == f'week-{WEEK}']
    table = MagicMock()
    table.query.return_value = {'Items': week_rows}
    table.scan.return_value = {'Items': [r for r in rows if r.get('is_current_week')]}
    _, nxt = hs._build_week_sessions(table, NOW)
    return nxt['session_id'] if nxt else None


def _plan_payload(rows):
    table = MagicMock()
    table.scan.return_value = {'Items': list(rows)}
    payload, _ = plan_workouts.build_plan_workouts(table, NOW)
    return payload


class TestHomeAndPlanAgree:
    def test_first_open_session_without_intervals_is_next_on_both(self):
        rows = [
            _row(0, local_status='done'),
            _row(1, intervals=[]),
            _row(2),
            _row(0, week=NEXT_WEEK, week_ms=NEXT_WEEK_MS, current=False),
        ]
        payload = _plan_payload(rows)
        assert _home_next_id(rows) == '9_1'
        assert payload['next_session_id'] == '9_1'
        # Plan still lists only sessions it can describe; the old rule picked 9_2.
        assert [w['session_id'] for w in payload['workouts']] == ['9_2', '10_0']

    def test_skipped_and_done_sessions_are_passed_over_on_both(self):
        rows = [
            _row(0, local_status='skip'),
            _row(1, matched_activity_id='123'),
            _row(2),
        ]
        assert _home_next_id(rows) == '9_2'
        assert _plan_payload(rows)['next_session_id'] == '9_2'

    def test_week_with_nothing_open_has_no_next_on_both(self):
        rows = [
            _row(0, local_status='done'),
            _row(0, week=NEXT_WEEK, week_ms=NEXT_WEEK_MS, current=False),
        ]
        assert _home_next_id(rows) is None
        assert _plan_payload(rows)['next_session_id'] is None

    def test_campus_order_wins_over_row_order(self):
        rows = [_row(3), _row(1), _row(2)]
        assert _home_next_id(rows) == '9_1'
        assert _plan_payload(rows)['next_session_id'] == '9_1'


class TestCurrentWeekRows:
    def test_future_week_is_never_the_current_one(self):
        rows = [_row(0, week=NEXT_WEEK, week_ms=NEXT_WEEK_MS, current=False)]
        assert campus_next.next_open_session(rows, hs.paris_date(NOW)) is None

    def test_flagged_week_is_the_fallback_when_the_paris_week_is_missing(self):
        stale = _row(0, week='2026-W41', week_ms=WEEK_MS - 7 * 24 * 3600 * 1000)
        assert campus_next.next_open_session([stale], hs.paris_date(NOW)) is stale

    def test_athlete_context_row_is_ignored(self):
        rows = [{'session_date': 'athlete-context', 'session_id': '1', 'is_current_week': True}]
        assert campus_next.current_week_rows(rows, hs.paris_date(NOW)) == []

    def test_partition_label_uses_the_paris_date(self):
        # Sunday 18 Oct 2026 23:30 UTC is Monday 19 Oct in Paris (CEST, +2): W43.
        late = datetime(2026, 10, 18, 23, 30, tzinfo=timezone.utc)
        assert campus_next.week_partition(hs.paris_date(late)) == 'week-2026-W43'
