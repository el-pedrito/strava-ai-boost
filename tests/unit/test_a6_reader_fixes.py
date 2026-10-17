"""A6 reader bug fixes (dashboard_api + coach_chat).

- ramp_rate is computed over COMPLETED weeks, not the in-progress week.
- interval/EF pace trends are dated by the activity's local date (start_date_local),
  not created_at (which resets on reprocess); EF HR comes from activity_data_json.
- activity detail exposes average_heartrate, max_heartrate, total_elevation_gain.
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from api.dashboard_api import get_coach_summary, get_activity_history, _activity_local_day


def _week_monday(now, weeks_ago):
    monday = (now - timedelta(days=now.weekday())).date()
    return monday - timedelta(weeks=weeks_ago)


def _run(day, km, moving_s, laps=None, adj_json=None):
    item = {
        'activity_id': f'r-{day}-{km}',
        'activity_type': 'Run',
        'distance': Decimal(str(km * 1000)),
        'moving_time': moving_s,
        'start_date': f'{day}T07:00:00Z',
        'created_at': '2000-01-01T00:00:00',  # deliberately stale: must be ignored
        'activity_data_json': json.dumps({'start_date_local': f'{day}T08:00:00',
                                           **(adj_json or {})}),
    }
    if laps is not None:
        item['laps_json'] = json.dumps(laps)
    return item


class TestRampRateCompletedWeeks:
    @patch('api.dashboard_api.dynamodb')
    def test_ramp_rate_uses_completed_weeks_not_in_progress(self, mock_ddb):
        now = datetime.now(tz=timezone.utc)
        wk_cur = _week_monday(now, 0).isoformat()      # in-progress week
        wk_prev = _week_monday(now, 1).isoformat()     # last completed
        wk_prev2 = _week_monday(now, 2).isoformat()    # previous completed
        # completed weeks: 10km -> 20km  => +100%. In-progress week only 1km so
        # the naive (current vs previous) calc would give a wrong, negative ramp.
        activities = [
            _run(wk_prev2, 10, 3600),
            _run(wk_prev, 20, 7200),
            _run(wk_cur, 1, 360),
        ]
        act_table = MagicMock()
        config_table = MagicMock()
        config_table.get_item.return_value = {'Item': {}}
        sessions_table = MagicMock()
        sessions_table.scan.return_value = {'Items': []}

        def table(name):
            if 'activities' in name:
                return act_table
            if 'coaching-sessions' in name:
                return sessions_table
            return config_table
        mock_ddb.Table.side_effect = table
        act_table.query.return_value = {'Items': activities}

        result = get_coach_summary('42')
        assert result['trends']['ramp_rate'] == 100.0
        assert result['volume_change_completed_weeks_pct'] == 100.0


class TestTrendDatingAndHr:
    @patch('api.dashboard_api.dynamodb')
    def test_ef_trend_dated_by_local_date_and_hr_from_json(self, mock_ddb):
        now = datetime.now(tz=timezone.utc)
        wk = _week_monday(now, 1).isoformat()
        # An EF session: >=2 laps, mostly slow, HR only in activity_data_json.
        laps = [
            {'average_speed': 3.0, 'distance': 2000, 'moving_time': 667},
            {'average_speed': 3.0, 'distance': 2000, 'moving_time': 667},
            {'average_speed': 3.0, 'distance': 2000, 'moving_time': 667},
        ]
        a = _run(wk, 6, 2001, laps=laps, adj_json={'average_heartrate': 142})
        act_table = MagicMock()
        config_table = MagicMock()
        config_table.get_item.return_value = {'Item': {}}
        sessions_table = MagicMock()
        sessions_table.scan.return_value = {'Items': []}

        def table(name):
            if 'activities' in name:
                return act_table
            if 'coaching-sessions' in name:
                return sessions_table
            return config_table
        mock_ddb.Table.side_effect = table
        act_table.query.return_value = {'Items': [a]}

        result = get_coach_summary('42')
        ef = result['trends']['ef_paces']
        assert ef, "expected one EF trend point"
        assert ef[0]['date'] == f'{wk}'  # local date, not the 2000 created_at
        assert ef[0]['hr'] == 142


class TestActivityLocalDayHelper:
    def test_prefers_start_date_local_over_created_at(self):
        item = {'created_at': '2000-01-01T00:00:00',
                'activity_data_json': json.dumps({'start_date_local': '2026-10-11T08:00:00'})}
        assert _activity_local_day(item) == '2026-10-11'


class TestActivityDetailFields:
    @patch('api.dashboard_api.dynamodb')
    def test_detail_returns_hr_and_elevation(self, mock_ddb):
        item = {
            'activity_id': '999',
            'activity_type': 'Run',
            'total_elevation_gain': Decimal('123.4'),
            'activity_data_json': json.dumps({
                'average_heartrate': 150.0,
                'max_heartrate': 178.0,
            }),
        }
        table = MagicMock()
        table.get_item.return_value = {'Item': item}
        mock_ddb.Table.return_value = table

        result = get_activity_history({'activity_id': '999'}, '42')
        act = result['activities'][0]
        assert act['average_heartrate'] == 150.0
        assert act['max_heartrate'] == 178.0
        assert act['total_elevation_gain'] == 123.4

