"""A3: Campus home aggregates in the wellness table (goal tri-state, predictions,
week stats). The sync's existing session behaviour is covered by
test_campus_coach_sync.py and must stay byte-identical."""
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("COACHING_SESSIONS_TABLE", "test-coaching-sessions")
os.environ.setdefault("WELLNESS_TABLE", "test-wellness")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from webhooks import campus_coach_sync as ccs

NOW = datetime(2026, 10, 17, 5, 0, tzinfo=timezone.utc)


class TestGoalTriState:
    def test_none_means_no_write(self):
        assert ccs._goal_item(None, NOW) is None

    def test_empty_list_is_inactive(self):
        item = ccs._goal_item([], NOW)
        assert item == {'sk': 'campus#goal', 'active': False, 'synced_at': NOW.isoformat()}

    def test_goal_present_is_active_card(self):
        goals = [{
            'name': 'SEMI-MARATHON', 'goalType': 'half-marathon',
            'competitionDate': 1763164800000, 'sessionsPerWeek': 4,
            'weekIndex': 11, 'durationInWeeks': 15, 'cycleTheme': 'Force_A21',
            'stats': {'trainingsDoneCount': 48, 'trainingsCount': 81},
        }]
        item = ccs._goal_item(goals, NOW)
        assert item['active'] is True
        assert item['name'] == 'SEMI-MARATHON'
        assert item['type'] == 'half-marathon'
        assert item['week_index'] == 11
        assert item['weeks_total'] == 15
        assert item['trainings_done'] == 48
        assert item['trainings_total'] == 81


class TestCompetitivePaces:
    def test_parses_competitive_slugs_only(self):
        estimated = [
            {'slug': '10km', 'value': 245.7, 'dvalue': 3.2, 'competitive': True},
            {'slug': 'ef', 'value': 330.0, 'competitive': False},
            {'slug': 'half-marathon', 'value': 273.0, 'dvalue': 7.0, 'competitive': True},
        ]
        out = ccs._campus_competitive_paces(estimated)
        assert set(out) == {'10km', 'half-marathon'}
        assert out['10km']['pace_s'] == 246
        # time_s = value * distance_km
        assert out['10km']['time_s'] == round(245.7 * 10.0)
        lo, hi = out['10km']['range_s']
        assert lo == round((245.7 - 3.2) * 10.0)
        assert hi == round((245.7 + 3.2) * 10.0)

    def test_first_slug_wins_and_junk_ignored(self):
        estimated = [
            {'slug': 'half', 'value': 270.0, 'competitive': True},
            {'slug': 'half-marathon', 'value': 999.0, 'competitive': True},
            {'slug': '5km', 'value': 0, 'competitive': True},       # <=0 ignored
            {'slug': '5km', 'value': 'x', 'competitive': True},     # junk ignored
        ]
        out = ccs._campus_competitive_paces(estimated)
        # both 'half' and 'half-marathon' map to half-marathon; first wins
        assert out['half-marathon']['pace_s'] == 270
        assert '5km' not in out


class TestWeekStat:
    def test_week_stat_item(self):
        week = {'weekDate': 1760918400000, 'stats': {
            'expectedDistance': 39200, 'realDistance': 13200,
            'expectedDuration': 12600, 'realDuration': 4100,
        }}
        item = ccs._week_stat_item(week, NOW)
        assert item['sk'].startswith('campus#week#')
        assert item['expected_distance_km'] == 39.2
        assert item['real_distance_km'] == 13.2
        assert item['expected_duration_s'] == 12600
        assert item['real_duration_s'] == 4100


class TestStoreHomeCampus:
    def _week(self, ms, competitive=True):
        return {'weekDate': ms, 'access': 'allowed',
                'estimatedPaces': [{'slug': '10km', 'value': 245.0, 'dvalue': 2.0,
                                    'competitive': competitive}],
                'stats': {'expectedDistance': 39200, 'realDistance': 13200}}

    def test_no_owner_writes_nothing(self):
        with patch.object(ccs, "CAMPUS_OWNER_STRAVA_ID", ""), \
             patch.object(ccs, "dynamodb") as mock_ddb:
            ccs._store_home_campus([], [self._week(1)], NOW,
                                   datetime(2026, 10, 17, tzinfo=timezone.utc))
            mock_ddb.Table.assert_not_called()

    def test_writes_goal_week_and_current_prediction(self):
        monday = datetime(2026, 10, 12, tzinfo=timezone.utc)
        current_ms = int(monday.timestamp() * 1000)
        other_ms = int(datetime(2026, 10, 5, tzinfo=timezone.utc).timestamp() * 1000)
        weeks = [self._week(current_ms), self._week(other_ms)]
        table = MagicMock()
        with patch.object(ccs, "CAMPUS_OWNER_STRAVA_ID", "42"), \
             patch.object(ccs, "dynamodb") as mock_ddb:
            mock_ddb.Table.return_value = table
            ccs._store_home_campus([], weeks, NOW, monday)
        sks = [c.kwargs['Item']['sk'] for c in table.put_item.call_args_list]
        assert 'campus#goal' in sks
        assert any(sk.startswith('campus#week#') for sk in sks)
        # prediction only for the current ISO week
        pred_sks = [sk for sk in sks if sk.startswith('campus#pred#')]
        assert len(pred_sks) == 1
        for c in table.put_item.call_args_list:
            assert c.kwargs['Item']['user_id'] == "42"

    def test_goal_none_skips_goal_write_keeps_others(self):
        monday = datetime(2026, 10, 12, tzinfo=timezone.utc)
        weeks = [self._week(int(monday.timestamp() * 1000))]
        table = MagicMock()
        with patch.object(ccs, "CAMPUS_OWNER_STRAVA_ID", "42"), \
             patch.object(ccs, "dynamodb") as mock_ddb:
            mock_ddb.Table.return_value = table
            ccs._store_home_campus(None, weeks, NOW, monday)
        sks = [c.kwargs['Item']['sk'] for c in table.put_item.call_args_list]
        assert 'campus#goal' not in sks  # None -> keep previous goal item
        assert any(sk.startswith('campus#week#') for sk in sks)


class TestSyncAthleteContextReturn:
    def test_returns_list_on_200(self):
        table = MagicMock()
        goal_resp = MagicMock(status_code=200)
        goal_resp.json.return_value = [{'name': 'X'}]
        other = MagicMock(status_code=200)
        other.json.return_value = {}
        with patch.object(ccs.requests, "get", side_effect=[goal_resp, other, other]):
            result = ccs._sync_athlete_context("tok", table, "42")
        assert result == [{'name': 'X'}]

    def test_returns_none_on_non_200(self):
        table = MagicMock()
        goal_resp = MagicMock(status_code=500)
        other = MagicMock(status_code=200)
        other.json.return_value = {}
        with patch.object(ccs.requests, "get", side_effect=[goal_resp, other, other]):
            result = ccs._sync_athlete_context("tok", table, "42")
        assert result is None
