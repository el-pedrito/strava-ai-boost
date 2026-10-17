"""A4: GET /home/summary — auth (403), no-store, no module cache, and the
builder's health/race/plan/sessions/predictions assembly."""
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from api import dashboard_api
from api import home_summary as hs

OWNER = "424242"
NOW = datetime(2026, 10, 17, 6, 0, tzinfo=timezone.utc)


def _event(strava_id):
    return {
        'path': '/home/summary',
        'httpMethod': 'GET',
        'requestContext': {'authorizer': {'claims': {'custom:strava_id': strava_id}}},
    }


class TestHomeSummaryAuth:
    def test_wrong_claim_is_403_and_no_store(self):
        with patch.dict(os.environ, {'CAMPUS_OWNER_STRAVA_ID': OWNER}, clear=False):
            resp = dashboard_api.get_home_summary_response(_event("999"))
        assert resp['statusCode'] == 403
        assert resp['headers']['Cache-Control'] == 'no-store'
        assert json.loads(resp['body'])['error'] == 'Forbidden'

    def test_empty_owner_denies_everyone(self):
        with patch.dict(os.environ, {'CAMPUS_OWNER_STRAVA_ID': ''}, clear=False):
            resp = dashboard_api.get_home_summary_response(_event(""))
        assert resp['statusCode'] == 403

    def test_owner_path_is_no_store_and_bypasses_cache(self):
        # Snapshot the shared module cache: the home route must not ADD to it
        # (other dashboard tests may have populated it, so assert "no new keys").
        before = set(dashboard_api._cache)
        with patch.dict(os.environ, {'CAMPUS_OWNER_STRAVA_ID': OWNER}, clear=False), \
             patch.object(dashboard_api, 'dynamodb') as mock_ddb, \
             patch.object(dashboard_api.home_summary, 'build_home_summary',
                          return_value={'ok': True, 'health': {}, 'week_sessions': [], 'brief': None}) as b:
            mock_ddb.Table.return_value = MagicMock()
            resp = dashboard_api.get_home_summary_response(_event(OWNER))
        assert resp['statusCode'] == 200
        assert resp['headers']['Cache-Control'] == 'no-store'
        assert b.called
        assert set(dashboard_api._cache) == before  # route added nothing to _cache

    def test_handler_routes_home_before_validate(self):
        with patch.dict(os.environ, {'CAMPUS_OWNER_STRAVA_ID': OWNER}, clear=False), \
             patch.object(dashboard_api, 'get_home_summary_response',
                          return_value={'statusCode': 200, 'headers': {}, 'body': '{}'}) as r:
            dashboard_api.handler(_event(OWNER), None)
        assert r.called


def _wellness_table_with(days=None, items=None):
    """Fake wellness table: query returns day/pred rows by key condition shape,
    get_item returns from an sk->item map."""
    days = days or []
    items = items or {}

    table = MagicMock()

    def _query(**kwargs):
        # crude: return day rows for a between() on day#, pred rows for begins_with campus#pred#
        expr = str(kwargs.get('KeyConditionExpression'))
        if 'campus#pred#' in expr:
            return {'Items': [v for k, v in items.items() if k.startswith('campus#pred#')]}
        return {'Items': days}

    def _get_item(Key):
        return {'Item': items[Key['sk']]} if Key['sk'] in items else {}

    table.query.side_effect = _query
    table.get_item.side_effect = _get_item
    return table


class TestBuildHealth:
    def test_hrv_baseline_same_kind_and_delta(self):
        days = [
            {'sk': 'day#2026-10-10', 'hrv': Decimal('40'), 'hrv_kind': 'rmssd'},
            {'sk': 'day#2026-10-15', 'hrv': Decimal('60'), 'hrv_kind': 'sdnn'},
            {'sk': 'day#2026-10-16', 'hrv': Decimal('56'), 'hrv_kind': 'sdnn'},
        ]
        today = datetime(2026, 10, 17, tzinfo=timezone.utc).date()
        health = hs._build_health(days, today)
        assert health['hrv']['kind'] == 'sdnn'
        # baseline excludes the latest point and the rmssd day -> baseline = 60
        assert health['hrv']['baseline_60d'] == 60.0
        assert health['hrv']['value'] == 56
        assert health['hrv']['delta'] == -4.0

    def test_stale_flag_on_old_signal(self):
        days = [{'sk': 'day#2026-10-10', 'restingHR': Decimal('48')}]
        today = datetime(2026, 10, 17, tzinfo=timezone.utc).date()
        health = hs._build_health(days, today)
        assert health['resting_hr']['stale'] is True
        assert health['resting_hr']['as_of'] == '2026-10-10'


class TestBuildRaceAndPlan:
    def _goal(self):
        return {
            'sk': 'campus#goal', 'active': True, 'name': 'SEMI', 'type': 'half-marathon',
            'competition_date': '1794700800000',  # 2026-11-15 00:00 UTC
            'target_duration_s': Decimal('5759'),
            'target_distance_km': Decimal('21.095'),
            'weeks_total': Decimal('15'),
            'cycle_theme': 'Force_A21', 'trainings_done': Decimal('48'),
            'trainings_total': Decimal('81'), 'sessions_per_week': Decimal('4'),
            'weekly_volume_low': Decimal('26'), 'weekly_volume_high': Decimal('38'),
        }

    def test_race_days_left_and_prediction(self):
        today = datetime(2026, 10, 17, tzinfo=timezone.utc).date()
        pred = {'source_week': '2026-W42',
                'half-marathon': {'pace_s': Decimal('273'), 'time_s': Decimal('5857'),
                                  'range_s': [Decimal('5714'), Decimal('6001')]}}
        race = hs._build_race(self._goal(), pred, today)
        assert race['active'] is True
        assert race['type'] == 'half-marathon'
        assert race['days_left'] == 29  # 2026-11-15 minus 2026-10-17
        assert race['target_pace_s'] == round(5759 / 21.095)
        assert race['predicted_time_s'] == 5857
        assert race['predicted_range_s'] == [5714, 6001]
        assert race['prediction_week'] == '2026-W42'

    def test_inactive_goal_is_active_false_with_nulls(self):
        race = hs._build_race({'sk': 'campus#goal', 'active': False}, None,
                              datetime(2026, 10, 17, tzinfo=timezone.utc).date())
        assert race['active'] is False
        for k in ('name', 'type', 'date', 'days_left', 'target_time_s',
                  'target_pace_s', 'predicted_time_s', 'predicted_range_s',
                  'prediction_week'):
            assert race[k] is None, k

    def test_none_goal_is_none(self):
        assert hs._build_race(None, None,
                              datetime(2026, 10, 17, tzinfo=timezone.utc).date()) is None

    def test_plan_reads_week_index_from_week_stat(self):
        week_stat = {'expected_distance_km': Decimal('39.2'),
                     'real_distance_km': Decimal('13.2'),
                     'week_index': Decimal('11'), 'weeks_total': Decimal('15'),
                     'cycle_theme': 'Force_A21'}
        plan = hs._build_plan(self._goal(), week_stat)
        assert plan['week_index'] == 11
        assert plan['weeks_total'] == 15
        assert plan['cycle_theme'] == 'Force_A21'
        assert plan['week_km_expected'] == 39.2
        assert plan['week_km_real'] == 13.2
        assert plan['sessions_per_week'] == 4

    def test_plan_nulls_when_no_week_stat(self):
        plan = hs._build_plan(self._goal(), None)
        assert plan['week_index'] is None
        assert plan['weeks_total'] == 15
        assert plan['week_km_expected'] is None
        assert plan['week_km_real'] is None


class TestWeekSessions:
    def test_sessions_ordered_with_effective_status_and_next(self):
        sessions = [
            {'session_date': 'week-2026-W42', 'training_index': 0, 'title': 'EF',
             'training_type': 'Endurance', 'expected_duration_min': 45,
             'is_current_week': True, 'local_status': 'done'},
            {'session_date': 'week-2026-W42', 'training_index': 1, 'title': 'Allure',
             'training_type': 'Intensity', 'expected_duration_min': 64,
             'is_current_week': True},
        ]
        table = MagicMock()
        table.query.return_value = {'Items': sessions}
        now = datetime(2026, 10, 17, tzinfo=timezone.utc)
        week, nxt = hs._build_week_sessions(table, now)
        assert [w['order'] for w in week] == [1, 2]
        assert week[0]['status'] == 'done'
        assert nxt['title'] == 'Allure'
        assert 'status' not in nxt  # next_session has no status field


class TestPredictions:
    def test_current_week_items_and_history(self):
        preds = [
            {'source_week': '2026-W42',
             'half-marathon': {'time_s': Decimal('5857'), 'pace_s': Decimal('273'),
                               'range_s': [Decimal('5714'), Decimal('6001')]},
             '10km': {'time_s': Decimal('2457'), 'pace_s': Decimal('246'),
                      'range_s': [Decimal('2420'), Decimal('2490')]}},
            {'source_week': '2026-W37',
             'half-marathon': {'time_s': Decimal('5950'), 'pace_s': Decimal('281'),
                               'range_s': [Decimal('5900'), Decimal('6000')]}},
        ]
        current, history = hs._build_predictions(preds, '2026-W42')
        assert current['week'] == '2026-W42'
        dists = {i['distance'] for i in current['items']}
        assert {'10km', 'half-marathon'} <= dists
        assert history == [{'week': '2026-W37', 'half_marathon_time_s': 5950}]

    def test_absent_current_week_is_none(self):
        preds = [{'source_week': '2026-W37', 'half-marathon': {'time_s': Decimal('5950')}}]
        current, history = hs._build_predictions(preds, '2026-W42')
        assert current is None


class TestEnduraw:
    def test_trend_window_and_fields(self):
        activities = [
            {'activity_id': '1', 'start_date_local': '2026-10-11T08:00:00',
             'enduraw_metrics': {'raw_pace_s': 280, 'adjusted_pace_s': 271,
                                 'heat_cost_s': 0, 'wind_cost_s': 4, 'elevation_cost_s': 3}},
            {'activity_id': 'old', 'start_date_local': '2020-01-01T08:00:00',
             'enduraw_metrics': {'raw_pace_s': 300, 'adjusted_pace_s': 300}},
            {'activity_id': 'none', 'start_date_local': '2026-10-12T08:00:00'},
        ]
        trend = hs._build_enduraw_trend(lambda: activities, '2026-07-20')
        ids = [t['activity_id'] for t in trend]
        assert ids == ['1']  # old is before window, none has no metrics
        assert trend[0]['adjusted_pace_s'] == 271
        assert trend[0]['wind_cost_s'] == 4
        assert trend[0]['heat_cost_s'] == 0  # a present 0 line is kept


class TestModules:
    def test_module_flags(self):
        cfg = {'modules_config': {'intervals_icu': {'enabled': True},
                                  'campus_coach': {'enabled': False}}}
        assert hs._build_modules(cfg) == {'intervals_icu': True, 'campus_coach': False}


class TestContractShape:
    """The /home/summary body carries the full CONTRACT shape with explicit nulls."""

    def _empty_build(self):
        wellness = _wellness_table_with(days=[], items={})
        sessions = MagicMock()
        sessions.query.return_value = {'Items': []}
        sessions.scan.return_value = {'Items': []}
        return hs.build_home_summary(wellness, sessions, {}, lambda: [], NOW, OWNER)

    def test_top_level_keys_present(self):
        body = self._empty_build()
        for key in ('generated_at', 'modules', 'brief', 'race', 'plan',
                    'week_sessions', 'next_session', 'health', 'health_series',
                    'predictions', 'predictions_history', 'enduraw_trend'):
            assert key in body, key
        assert body['brief'] is None
        assert body['race'] is None
        assert body['plan'] is None
        assert body['predictions'] is None
        assert body['next_session'] is None
        assert body['week_sessions'] == []
        for sig in ('resting_hr', 'hrv', 'sleep_s', 'sleep_score', 'ctl',
                    'atl', 'form', 'vo2max', 'weight'):
            assert sig in body['health'] and body['health'][sig] is None, sig


class TestEndToEndOnMoto:
    """build_home_summary against a real (moto) DynamoDB wellness table, including
    JSON serialisation of the Decimal values it reads back."""

    def test_build_and_serialise_decimals(self):
        from moto import mock_aws
        import boto3

        with mock_aws():
            ddb = boto3.resource('dynamodb', region_name='eu-west-1')
            table = ddb.create_table(
                TableName='strava-ai-boost-wellness', BillingMode='PAY_PER_REQUEST',
                KeySchema=[{'AttributeName': 'user_id', 'KeyType': 'HASH'},
                           {'AttributeName': 'sk', 'KeyType': 'RANGE'}],
                AttributeDefinitions=[{'AttributeName': 'user_id', 'AttributeType': 'S'},
                                      {'AttributeName': 'sk', 'AttributeType': 'S'}])
            table.put_item(Item={'user_id': OWNER, 'sk': 'day#2026-10-16',
                                 'restingHR': Decimal('45'), 'hrv': Decimal('48.0'),
                                 'hrv_kind': 'sdnn', 'ctl': Decimal('10.5'),
                                 'atl': Decimal('28.3')})
            table.put_item(Item={'user_id': OWNER, 'sk': 'campus#goal', 'active': True,
                                 'name': 'SEMI', 'type': 'half-marathon',
                                 'competition_date': '1794700800000',
                                 'target_duration_s': Decimal('5759'),
                                 'target_distance_km': Decimal('21.095'),
                                 'weeks_total': Decimal('15'),
                                 'trainings_done': Decimal('48'),
                                 'trainings_total': Decimal('81')})
            week_iso = hs._week_label(NOW)
            table.put_item(Item={'user_id': OWNER, 'sk': 'campus#week#' + week_iso,
                                 'week': week_iso, 'week_index': Decimal('11'),
                                 'weeks_total': Decimal('15'), 'cycle_theme': 'Force_A21',
                                 'expected_distance_km': Decimal('39.2'),
                                 'real_distance_km': Decimal('13.2')})
            table.put_item(Item={'user_id': OWNER, 'sk': 'campus#pred#' + week_iso,
                                 'source_week': week_iso,
                                 'half-marathon': {'time_s': Decimal('5857'),
                                                   'pace_s': Decimal('273'),
                                                   'range_s': [Decimal('5714'), Decimal('6001')]}})

            sessions = MagicMock()
            sessions.query.return_value = {'Items': []}
            sessions.scan.return_value = {'Items': []}

            body = hs.build_home_summary(table, sessions, {}, lambda: [], NOW, OWNER)

            dumped = json.dumps(body)
            assert isinstance(dumped, str)
            assert body['race']['active'] is True
            assert body['race']['target_pace_s'] == round(5759 / 21.095)
            assert body['race']['days_left'] == 29
            assert body['plan']['week_index'] == 11
            assert body['plan']['week_km_expected'] == 39.2
            assert body['health']['hrv']['value'] == 48.0
            assert body['health']['hrv']['kind'] == 'sdnn'
            assert body['predictions']['week'] == week_iso


class TestWeekLabelParisBoundary:
    """_week_label derives the ISO week from the Europe/Paris date, so a Sunday
    UTC late-night instant that is already Monday in Paris reads the new week."""

    def test_winter_sunday_night_utc_is_monday_paris(self):
        # 2026-01-18 is a Sunday. 23:30 UTC in winter (UTC+1) -> Mon 00:30 Paris.
        sun = datetime(2026, 1, 18, 23, 30, tzinfo=timezone.utc)
        mon = datetime(2026, 1, 19, 23, 30, tzinfo=timezone.utc)  # already Monday UTC
        assert hs._week_label(sun) == hs._week_label(mon)   # both the Monday week
        assert hs._week_label(sun) == '2026-W04'

    def test_winter_sunday_evening_still_sunday_paris(self):
        # 22:30 UTC winter -> 23:30 Paris Sunday, still the Sunday's week.
        sun_eve = datetime(2026, 1, 18, 22, 30, tzinfo=timezone.utc)
        assert hs._week_label(sun_eve) == '2026-W03'

    def test_summer_sunday_night_utc_is_monday_paris(self):
        # 2026-07-19 is a Sunday. 22:30 UTC in summer (UTC+2) -> Mon 00:30 Paris.
        sun = datetime(2026, 7, 19, 22, 30, tzinfo=timezone.utc)
        assert hs._week_label(sun) == '2026-W30'   # Monday 2026-07-20's week

    def test_summer_sunday_evening_still_sunday_paris(self):
        # 21:30 UTC summer -> 23:30 Paris Sunday, still the Sunday's week.
        sun_eve = datetime(2026, 7, 19, 21, 30, tzinfo=timezone.utc)
        assert hs._week_label(sun_eve) == '2026-W29'
