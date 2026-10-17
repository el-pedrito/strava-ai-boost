"""A3: Campus home aggregates in the wellness table (goal tri-state, predictions,
week stats). The sync's existing session behaviour is covered by
test_campus_coach_sync.py and must stay byte-identical.

Fixtures copy the STRUCTURE and numbers of a captured smart-training payload
(real field paths: sessionCompetitionInfo.sessionCompetition.stats,
simulatedWeeklyVolume, weekStats, goalDuration, context.cycleTheme, coach.name).
No free text, no real ids."""
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


def _goal_payload():
    """Real goal/active[0] shape: name/targets under sessionCompetitionInfo,
    volume under simulatedWeeklyVolume, totals under stats."""
    return {
        '_id': 'fake-goal-id',
        'competitionDate': 1794700800000,   # 2026-11-15 00:00 UTC
        'durationInWeeks': 15,
        'goalType': 'half-marathon',
        'sessionsPerWeek': 4,
        'stats': {'trainingsCount': 81, 'trainingsDoneCount': 48,
                  'distanceTotal': 344.779, 'timeTotal': 125120},
        'simulatedWeeklyVolume': {'lowerBound': 26, 'upperBound': 38},
        'sessionCompetitionInfo': {
            'sessionCompetition': {
                'name': 'SEMI-MARATHON',
                'displayName': 'SEMI-MARATHON',
                'trainingType': 'Competition',
                'stats': {'expectedDistance': 21.095238095238095,  # already km
                          'expectedDuration': 5759},               # seconds
            }
        },
    }


def _week_payload(week_date_ms, index=11):
    """Real smart-training week shape: weekStats already in km, goalDuration,
    context, coach, estimatedPaces."""
    return {
        'weekDate': week_date_ms,
        'access': 'allowed',
        'goalDuration': {'durationInWeeks': 15, 'index': index},
        'context': {'cycleTheme': 'Force_A21'},
        'coach': {'name': 'Tristan'},
        'weekStats': {'expectedDistance': 39.19272015278587,   # km (do NOT /1000)
                      'realDistance': 13.214400000000001,       # km
                      'expectedDuration': 12462, 'realDuration': 6448},
        'estimatedPaces': [
            {'slug': '5km', 'value': 245.6818821886492, 'dvalue': 6.53, 'competitive': True},
            {'slug': '10km', 'value': 260.581706770561, 'dvalue': 6.44, 'competitive': True},
            {'slug': 'half-marathon', 'value': 277.6422220970489, 'dvalue': 6.81, 'competitive': True},
            {'slug': 'marathon', 'value': 314.0621064183594, 'dvalue': 7.75, 'competitive': True},
            {'slug': 'slow', 'value': 658.2665181488353, 'dvalue': 40, 'abstract': True, 'competitive': False},
        ],
    }


class TestGoalTriState:
    def test_none_means_no_write(self):
        assert ccs._goal_item(None, NOW) is None

    def test_empty_list_is_inactive(self):
        item = ccs._goal_item([], NOW)
        assert item == {'sk': 'campus#goal', 'active': False, 'synced_at': NOW.isoformat()}

    def test_goal_present_reads_real_paths(self):
        item = ccs._goal_item([_goal_payload()], NOW)
        assert item['active'] is True
        assert item['name'] == 'SEMI-MARATHON'
        assert item['type'] == 'half-marathon'
        assert item['competition_date'] == '1794700800000'
        assert item['sessions_per_week'] == 4
        assert item['weeks_total'] == 15
        assert item['trainings_done'] == 48
        assert item['trainings_total'] == 81
        assert item['target_duration_s'] == 5759
        # expectedDistance already in km (21.095...), NOT divided by 1000
        assert item['target_distance_km'] == pytest.approx(21.095, abs=0.01)
        assert item['weekly_volume_low'] == 26
        assert item['weekly_volume_high'] == 38
        # week_index is NOT on the goal card (reader copies the week's value)
        assert 'week_index' not in item

    def test_goal_type_normalised_to_prediction_slug(self):
        g = _goal_payload()
        g['goalType'] = 'HALF_MARATHON'
        item = ccs._goal_item([g], NOW)
        assert item['type'] == 'half-marathon'
        g['goalType'] = 'semi'
        assert ccs._goal_item([g], NOW)['type'] == 'half-marathon'


class TestCompetitivePaces:
    def test_parses_competitive_slugs_only(self):
        out = ccs._campus_competitive_paces(_week_payload(0)['estimatedPaces'])
        assert set(out) == {'5km', '10km', 'half-marathon', 'marathon'}
        # time_s = value * distance_km
        v = round(260.581706770561, 1)   # 260.6
        d = round(6.44, 1)                # 6.4
        assert out['10km']['pace_s'] == round(v)
        assert out['10km']['time_s'] == round(v * 10.0)
        lo, hi = out['10km']['range_s']
        assert lo == round((v - d) * 10.0)
        assert hi == round((v + d) * 10.0)

    def test_first_slug_wins_and_junk_ignored(self):
        estimated = [
            {'slug': 'half', 'value': 270.0, 'dvalue': 5.0, 'competitive': True},
            {'slug': 'half-marathon', 'value': 999.0, 'dvalue': 1.0, 'competitive': True},
            {'slug': '5km', 'value': 0, 'dvalue': 1.0, 'competitive': True},   # <=0 ignored
            {'slug': '5km', 'value': 'x', 'dvalue': 1.0, 'competitive': True}, # junk ignored
        ]
        out = ccs._campus_competitive_paces(estimated)
        # 'half' maps to half-marathon and is the first valid one
        assert out['half-marathon']['pace_s'] == 270
        assert '5km' not in out


class TestWeekStat:
    def test_week_stat_item_real_paths(self):
        item = ccs._week_stat_item(_week_payload(1760918400000), NOW)
        assert item['sk'].startswith('campus#week#')
        # weekStats already km -> rounded to 1 decimal, NOT divided by 1000
        assert item['expected_distance_km'] == 39.2
        assert item['real_distance_km'] == 13.2
        assert item['expected_duration_s'] == 12462
        assert item['real_duration_s'] == 6448
        assert item['week_index'] == 11
        assert item['weeks_total'] == 15
        assert item['cycle_theme'] == 'Force_A21'
        assert item['coach_name'] == 'Tristan'


class TestStoreHomeCampus:
    def test_no_owner_writes_nothing(self):
        with patch.object(ccs, "CAMPUS_OWNER_STRAVA_ID", ""), \
             patch.object(ccs, "dynamodb") as mock_ddb:
            ccs._store_home_campus([_goal_payload()], [_week_payload(1)], NOW,
                                   datetime(2026, 10, 17, tzinfo=timezone.utc))
            mock_ddb.Table.assert_not_called()

    def test_writes_goal_week_and_current_prediction_via_update_item(self):
        monday = datetime(2026, 10, 12, tzinfo=timezone.utc)
        current_ms = int(monday.timestamp() * 1000)
        other_ms = int(datetime(2026, 10, 5, tzinfo=timezone.utc).timestamp() * 1000)
        weeks = [_week_payload(current_ms), _week_payload(other_ms, index=10)]
        table = MagicMock()
        with patch.object(ccs, "CAMPUS_OWNER_STRAVA_ID", "42"), \
             patch.object(ccs, "dynamodb") as mock_ddb:
            mock_ddb.Table.return_value = table
            ccs._store_home_campus([_goal_payload()], weeks, NOW, monday)
        # writes go through update_item (SET), not put_item
        assert table.put_item.call_count == 0
        sks = [c.kwargs['Key']['sk'] for c in table.update_item.call_args_list]
        assert 'campus#goal' in sks
        assert any(sk.startswith('campus#week#') for sk in sks)
        pred_sks = [sk for sk in sks if sk.startswith('campus#pred#')]
        assert len(pred_sks) == 1  # only the current ISO week
        for c in table.update_item.call_args_list:
            assert c.kwargs['Key']['user_id'] == "42"
            assert c.kwargs['UpdateExpression'].startswith('SET ')

    def test_goal_none_skips_goal_write_keeps_others(self):
        monday = datetime(2026, 10, 12, tzinfo=timezone.utc)
        weeks = [_week_payload(int(monday.timestamp() * 1000))]
        table = MagicMock()
        with patch.object(ccs, "CAMPUS_OWNER_STRAVA_ID", "42"), \
             patch.object(ccs, "dynamodb") as mock_ddb:
            mock_ddb.Table.return_value = table
            ccs._store_home_campus(None, weeks, NOW, monday)
        sks = [c.kwargs['Key']['sk'] for c in table.update_item.call_args_list]
        assert 'campus#goal' not in sks  # None -> keep previous goal item
        assert any(sk.startswith('campus#week#') for sk in sks)


class TestSyncAthleteContextReturn:
    def test_returns_list_on_200(self):
        table = MagicMock()
        goal_resp = MagicMock(status_code=200)
        goal_resp.json.return_value = [_goal_payload()]
        other = MagicMock(status_code=200)
        other.json.return_value = {}
        with patch.object(ccs.requests, "get", side_effect=[goal_resp, other, other]):
            result = ccs._sync_athlete_context("tok", table, "42")
        assert isinstance(result, list) and result[0]['goalType'] == 'half-marathon'

    def test_returns_none_on_non_200(self):
        table = MagicMock()
        goal_resp = MagicMock(status_code=500)
        other = MagicMock(status_code=200)
        other.json.return_value = {}
        with patch.object(ccs.requests, "get", side_effect=[goal_resp, other, other]):
            result = ccs._sync_athlete_context("tok", table, "42")
        assert result is None

    def test_returns_none_on_non_list_200_body(self):
        """A 200 whose body is not a list -> None (keep the previous item)."""
        table = MagicMock()
        goal_resp = MagicMock(status_code=200)
        goal_resp.json.return_value = {"unexpected": "dict"}
        other = MagicMock(status_code=200)
        other.json.return_value = {}
        with patch.object(ccs.requests, "get", side_effect=[goal_resp, other, other]):
            result = ccs._sync_athlete_context("tok", table, "42")
        assert result is None
