"""Unit tests for dashboard_api Lambda"""

import json
import os
import sys
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from api.dashboard_api import (
    handler,
    validate_request,
    get_activity_type_breakdown,
    get_cached_or_compute,
    _cache,
    _cache_ttl,
    _build_strength_progression,
    _detect_health_anomalies,
    _resolve_coach_user_id,
    _extract_recovery,
    _bucket_weekly_trends,
    _completed_week_volume_change,
    _format_sleep,
    get_coach_summary,
)


class TestValidateRequest:
    """Test request validation"""

    def test_valid_get_request(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {}}
        assert validate_request(event) is None

    def test_valid_options_request(self):
        event = {'httpMethod': 'OPTIONS'}
        assert validate_request(event) is None

    def test_post_not_allowed(self):
        event = {'httpMethod': 'PUT'}
        result = validate_request(event)
        assert 'not allowed' in result

    def test_valid_days_param(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'days': '30'}}
        assert validate_request(event) is None

    def test_days_too_large(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'days': '500'}}
        result = validate_request(event)
        assert 'between 1 and 365' in result

    def test_days_zero(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'days': '0'}}
        result = validate_request(event)
        assert 'between 1 and 365' in result

    def test_days_not_integer(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'days': 'abc'}}
        result = validate_request(event)
        assert 'valid integer' in result

    def test_valid_limit(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'limit': '50'}}
        assert validate_request(event) is None

    def test_limit_too_large(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'limit': '200'}}
        result = validate_request(event)
        assert 'between 1 and 100' in result

    def test_limit_not_integer(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'limit': 'abc'}}
        result = validate_request(event)
        assert 'valid integer' in result

    def test_valid_offset(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'offset': '10'}}
        assert validate_request(event) is None

    def test_negative_offset(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': {'offset': '-1'}}
        result = validate_request(event)
        assert 'non-negative' in result

    def test_null_query_params(self):
        event = {'httpMethod': 'GET', 'queryStringParameters': None}
        assert validate_request(event) is None


class TestHandlerRouting:
    """Test handler routes to correct endpoint"""

    def test_options_returns_200(self):
        event = {'httpMethod': 'OPTIONS', 'path': '/dashboard/stats'}
        response = handler(event, None)
        assert response['statusCode'] == 200

    @patch('api.dashboard_api.get_dashboard_stats')
    def test_stats_route(self, mock_stats):
        mock_stats.return_value = {'total': 10}
        event = {
            'httpMethod': 'GET',
            'path': '/dashboard/stats',
            'queryStringParameters': {},
        }
        response = handler(event, None)
        assert response['statusCode'] == 200
        mock_stats.assert_called_once()

    @patch('api.dashboard_api.get_activity_history')
    def test_activities_route(self, mock_history):
        mock_history.return_value = {'activities': []}
        event = {
            'httpMethod': 'GET',
            'path': '/dashboard/activities',
            'queryStringParameters': {},
        }
        response = handler(event, None)
        assert response['statusCode'] == 200

    @patch('api.dashboard_api.get_system_stats')
    def test_system_route(self, mock_system):
        mock_system.return_value = {'queue_depth': 0}
        event = {
            'httpMethod': 'GET',
            'path': '/dashboard/system',
            'queryStringParameters': {},
        }
        response = handler(event, None)
        assert response['statusCode'] == 200

    def test_unknown_route_returns_404(self):
        event = {
            'httpMethod': 'GET',
            'path': '/dashboard/unknown',
            'queryStringParameters': {},
        }
        response = handler(event, None)
        assert response['statusCode'] == 404

    def test_invalid_method_returns_400(self):
        event = {
            'httpMethod': 'DELETE',
            'path': '/dashboard/stats',
            'queryStringParameters': {},
        }
        response = handler(event, None)
        assert response['statusCode'] == 400


class TestGetActivityTypeBreakdown:
    """Test activity type aggregation"""

    def test_single_type(self):
        activities = [
            {'activity_type': 'Run'},
            {'activity_type': 'Run'},
            {'activity_type': 'Run'},
        ]
        result = get_activity_type_breakdown(activities)
        assert result == {'Run': 3}

    def test_multiple_types(self):
        activities = [
            {'activity_type': 'Run'},
            {'activity_type': 'Ride'},
            {'activity_type': 'Run'},
            {'activity_type': 'Swim'},
        ]
        result = get_activity_type_breakdown(activities)
        assert result == {'Run': 2, 'Ride': 1, 'Swim': 1}

    def test_missing_type_defaults_unknown(self):
        activities = [{'other_field': 'value'}]
        result = get_activity_type_breakdown(activities)
        assert result == {'Unknown': 1}

    def test_empty_list(self):
        assert get_activity_type_breakdown([]) == {}


class TestCache:
    """Test caching mechanism"""

    def setup_method(self):
        _cache.clear()
        _cache_ttl.clear()

    def test_cache_miss_computes(self):
        counter = {'calls': 0}

        def compute():
            counter['calls'] += 1
            return 42

        result = get_cached_or_compute('test_key', compute)
        assert result == 42
        assert counter['calls'] == 1

    def test_cache_hit_reuses(self):
        counter = {'calls': 0}

        def compute():
            counter['calls'] += 1
            return 42

        get_cached_or_compute('test_key', compute)
        result = get_cached_or_compute('test_key', compute)
        assert result == 42
        assert counter['calls'] == 1  # Only called once


class TestBuildStrengthProgression:
    """Test per-exercise strength progression aggregation."""

    def test_empty(self):
        assert _build_strength_progression([]) == []

    def test_entries_without_parsed_sets_ignored(self):
        entries = [{'date': '2026-07-01', 'description': 'DC 4x8'}]
        assert _build_strength_progression(entries) == []

    def test_aggregates_per_exercise_sorted_by_sessions(self):
        entries = [
            {'date': '2026-07-01', 'parsed_sets': [
                {'exercise': 'Développé couché', 'sets': 4, 'reps': 8, 'weight_kg': 80},
                {'exercise': 'Tractions', 'sets': 4, 'reps': 10, 'weight_kg': None},
            ]},
            {'date': '2026-07-08', 'parsed_sets': [
                {'exercise': 'Développé couché', 'sets': 4, 'reps': 8, 'weight_kg': 82.5},
            ]},
        ]
        result = _build_strength_progression(entries)
        # DC has 2 sessions, Tractions 1 → DC first
        assert result[0]['exercise'] == 'Développé couché'
        assert result[0]['sessions'] == 2
        assert result[0]['points'][0] == {'date': '2026-07-01', 'top_weight_kg': 80.0, 'volume_kg': 2560.0}
        assert result[0]['points'][1]['top_weight_kg'] == 82.5
        # Bodyweight exercise → weight/volume None
        tractions = next(e for e in result if e['exercise'] == 'Tractions')
        assert tractions['points'][0]['top_weight_kg'] is None
        assert tractions['points'][0]['volume_kg'] is None

    def test_real_face_pull_aliases_merge_into_thirteen_sessions(self):
        labels = ['Face pull'] * 7 + ['Facepull'] * 6
        entries = [
            {
                'date': f'2026-07-{index + 1:02d}',
                'parsed_sets': [{
                    'exercise': label,
                    'sets': 4,
                    'reps': 12,
                    'weight_kg': 20,
                }],
            }
            for index, label in enumerate(labels)
        ]

        result = _build_strength_progression(entries)

        assert len(result) == 1
        assert result[0]['exercise'] == 'Face pull'
        assert result[0]['sessions'] == 13
        assert len(result[0]['points']) == 13

    def test_normalizes_real_aliases_but_keeps_dumbbell_bench_separate(self):
        entries = [
            {'date': '2026-07-01', 'parsed_sets': [
                {'exercise': 'Développé couché', 'sets': 4, 'reps': 8, 'weight_kg': 80},
                {'exercise': 'Écart pec', 'sets': 3, 'reps': 12, 'weight_kg': 15},
            ]},
            {'date': '2026-07-02', 'parsed_sets': [
                {'exercise': 'Développé couché barre', 'sets': 4, 'reps': 8, 'weight_kg': 82.5},
                {'exercise': 'Écartement pectoraux poulie', 'sets': 3, 'reps': 12, 'weight_kg': 16},
            ]},
            {'date': '2026-07-03', 'parsed_sets': [
                {'exercise': 'Développé couché halt', 'sets': 4, 'reps': 8, 'weight_kg': 24},
            ]},
            {'date': '2026-07-04', 'parsed_sets': [
                {'exercise': 'Développé couché haltères', 'sets': 4, 'reps': 8, 'weight_kg': 26},
            ]},
        ]

        by_name = {item['exercise']: item for item in _build_strength_progression(entries)}

        assert by_name['Développé couché']['sessions'] == 2
        assert by_name['Développé couché haltères']['sessions'] == 2
        assert by_name['Écartés pectoraux à la poulie']['sessions'] == 2

    def test_same_day_merges_max_weight_and_summed_volume(self):
        entries = [
            {'date': '2026-07-01', 'parsed_sets': [
                {'exercise': 'Squat', 'sets': 3, 'reps': 5, 'weight_kg': 100},
            ]},
            {'date': '2026-07-01', 'parsed_sets': [
                {'exercise': 'Squat', 'sets': 2, 'reps': 3, 'weight_kg': 110},
            ]},
        ]
        result = _build_strength_progression(entries)
        assert len(result) == 1
        pts = result[0]['points']
        assert len(pts) == 1  # merged into one day
        assert pts[0]['top_weight_kg'] == 110.0
        assert pts[0]['volume_kg'] == 3 * 5 * 100 + 2 * 3 * 110


class TestDetectHealthAnomalies:
    """Test deterministic health-anomaly rules."""

    def test_none_and_empty(self):
        assert _detect_health_anomalies(None) == []
        assert _detect_health_anomalies({}) == []

    def test_no_anomaly_when_stable(self):
        recovery = {
            'resting_hr_delta_7d': 1, 'form': -5,
            'sleep_delta_7d_min': -10, 'vo2max_delta_7d': 0.2,
        }
        assert _detect_health_anomalies(recovery) == []

    def test_resting_hr_up_warning(self):
        result = _detect_health_anomalies({'resting_hr_delta_7d': 6})
        assert len(result) == 1
        assert result[0]['id'] == 'resting_hr_up'
        assert result[0]['severity'] == 'warning'

    def test_form_low_warning(self):
        result = _detect_health_anomalies({'form': -25})
        assert any(a['id'] == 'form_low' and a['severity'] == 'warning' for a in result)

    def test_sleep_and_vo2max_info(self):
        result = _detect_health_anomalies({'sleep_delta_7d_min': -60, 'vo2max_delta_7d': -1.5})
        ids = {a['id'] for a in result}
        assert ids == {'sleep_down', 'vo2max_down'}
        assert all(a['severity'] == 'info' for a in result)

    def test_multiple_anomalies(self):
        recovery = {'resting_hr_delta_7d': 8, 'form': -30, 'sleep_delta_7d_min': -50}
        result = _detect_health_anomalies(recovery)
        assert {a['id'] for a in result} == {'resting_hr_up', 'form_low', 'sleep_down'}

    def test_missing_fields_no_false_positive(self):
        # Only form present and fine → no anomaly, no crash on missing keys.
        assert _detect_health_anomalies({'form': 3}) == []


# --- Phase 0 — Coach Intelligence V2 correctness/security (tasks 0.1-0.4) ---


class TestResolveCoachUserId:
    """0.1 — Coach user id is resolved from the authenticated Cognito claim and
    fails closed when absent (R1)."""

    def _event(self, strava_id=None):
        claims = {}
        if strava_id is not None:
            claims['custom:strava_id'] = strava_id
        return {'requestContext': {'authorizer': {'claims': claims}}}

    def test_authenticated_id_wins(self):
        assert _resolve_coach_user_id(self._event('12345')) == '12345'

    def test_authenticated_id_not_overridden_by_default(self):
        # Even with the dev fallback enabled, a real claim is never overridden.
        with patch('api.dashboard_api.COACH_ALLOW_DEFAULT_USER', True), \
             patch('api.dashboard_api.DEFAULT_USER_ID', '999'):
            assert _resolve_coach_user_id(self._event('12345')) == '12345'

    def test_empty_claim_fails_closed(self):
        with patch('api.dashboard_api.COACH_ALLOW_DEFAULT_USER', False):
            assert _resolve_coach_user_id(self._event('')) is None

    def test_missing_claims_fails_closed(self):
        with patch('api.dashboard_api.COACH_ALLOW_DEFAULT_USER', False):
            assert _resolve_coach_user_id({'requestContext': {}}) is None

    def test_dev_fallback_only_when_explicitly_enabled(self):
        with patch('api.dashboard_api.COACH_ALLOW_DEFAULT_USER', True), \
             patch('api.dashboard_api.DEFAULT_USER_ID', '777'):
            assert _resolve_coach_user_id(self._event('')) == '777'

    def test_dev_fallback_ignored_when_default_empty(self):
        with patch('api.dashboard_api.COACH_ALLOW_DEFAULT_USER', True), \
             patch('api.dashboard_api.DEFAULT_USER_ID', ''):
            assert _resolve_coach_user_id(self._event('')) is None


class TestCoachSummaryHandlerAuth:
    """0.1 — /coach/summary fails closed on missing identity and never scans on
    the authenticated path (R1.2, R1.4)."""

    def test_missing_claim_returns_403(self):
        event = {
            'httpMethod': 'GET',
            'path': '/coach/summary',
            'queryStringParameters': {},
            'requestContext': {'authorizer': {'claims': {}}},
        }
        with patch('api.dashboard_api.COACH_ALLOW_DEFAULT_USER', False):
            response = handler(event, None)
        assert response['statusCode'] == 403

    def test_no_authorizer_returns_403(self):
        event = {
            'httpMethod': 'GET',
            'path': '/coach/summary',
            'queryStringParameters': {},
        }
        with patch('api.dashboard_api.COACH_ALLOW_DEFAULT_USER', False):
            response = handler(event, None)
        assert response['statusCode'] == 403

    @patch('api.dashboard_api.dynamodb')
    def test_authenticated_path_queries_gsi_never_scans(self, mock_dynamo):
        activities_table = MagicMock()
        activities_table.query.return_value = {'Items': []}
        config_table = MagicMock()
        config_table.get_item.return_value = {'Item': {}}
        sessions_table = MagicMock()
        sessions_table.scan.return_value = {'Items': []}

        mock_dynamo.Table.side_effect = lambda name: {
            'test-activities': activities_table,
            'test-user-config': config_table,
            'test-coaching-sessions': sessions_table,
        }.get(name, MagicMock())

        event = {
            'httpMethod': 'GET',
            'path': '/coach/summary',
            'queryStringParameters': {},
            'requestContext': {'authorizer': {'claims': {'custom:strava_id': '42'}}},
        }
        response = handler(event, None)
        assert response['statusCode'] == 200

        # Activities are queried via the GSI, never scanned (R1.4).
        activities_table.query.assert_called()
        activities_table.scan.assert_not_called()
        call_kwargs = activities_table.query.call_args.kwargs
        assert call_kwargs.get('IndexName') == 'UserActivitiesIndex'
        assert call_kwargs['ExpressionAttributeValues'][':uid'] == '42'


class TestBucketWeeklyTrends:
    """0.4 — date-based 12-week WeeklyTrend objects (R2)."""

    def test_produces_twelve_chronological_monday_buckets(self):
        now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)  # Sunday
        trends = _bucket_weekly_trends([], now, num_weeks=12)
        assert len(trends) == 12
        starts = [datetime.fromisoformat(t['week_start']) for t in trends]
        # Chronological, exactly 7 days apart, all Mondays.
        for earlier, later in zip(starts, starts[1:]):
            assert (later - earlier).days == 7
        assert all(s.weekday() == 0 for s in starts)

    def test_last_bucket_is_current_incomplete_week(self):
        now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)  # Sunday 2026-07-26
        trends = _bucket_weekly_trends([], now)
        assert trends[-1]['complete'] is False
        assert all(t['complete'] for t in trends[:-1])
        assert trends[-1]['week_start'] == '2026-07-20'
        assert trends[-1]['week_end'] == '2026-07-26'

    def test_midweek_now_buckets_current_week(self):
        now = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)  # Wednesday
        acts = [{
            'activity_type': 'Run', 'distance': 10000, 'moving_time': 3000,
            'start_date': '2026-07-21T06:00:00Z',  # Tuesday, same week
        }]
        trends = _bucket_weekly_trends(acts, now)
        cur = trends[-1]
        assert cur['week_start'] == '2026-07-20'
        assert cur['complete'] is False
        assert cur['runs'] == 1
        assert cur['run_km'] == 10.0
        assert cur['run_duration_sec'] == 3000

    def test_sunday_activity_stays_in_same_week(self):
        now = datetime(2026, 7, 26, 20, 0, tzinfo=timezone.utc)  # Sunday
        acts = [{
            'activity_type': 'Run', 'distance': 5000, 'moving_time': 1500,
            'start_date': '2026-07-26T18:00:00Z',  # Sunday = week_end
        }]
        trends = _bucket_weekly_trends(acts, now)
        assert trends[-1]['week_start'] == '2026-07-20'
        assert trends[-1]['runs'] == 1

    def test_iso_year_boundary_week_53(self):
        # 2020-12-28 is the Monday of ISO week 53 2020; 2021-01-04 is Monday of
        # ISO week 1 2021. Monday-date bucketing keeps them distinct/adjacent.
        now = datetime(2021, 1, 6, 12, 0, tzinfo=timezone.utc)  # Wed of 2021-W01
        acts = [
            {'activity_type': 'Run', 'distance': 8000, 'moving_time': 2400,
             'start_date': '2020-12-30T07:00:00Z'},  # week of 2020-12-28
            {'activity_type': 'Run', 'distance': 6000, 'moving_time': 1800,
             'start_date': '2021-01-05T07:00:00Z'},  # current week 2021-01-04
        ]
        trends = _bucket_weekly_trends(acts, now)
        by_start = {t['week_start']: t for t in trends}
        assert by_start['2020-12-28']['runs'] == 1
        assert by_start['2020-12-28']['run_km'] == 8.0
        assert by_start['2020-12-28']['complete'] is True
        assert by_start['2021-01-04']['runs'] == 1
        assert by_start['2021-01-04']['complete'] is False

    def test_strength_and_other_classification(self):
        now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
        acts = [
            {'activity_type': 'WeightTraining', 'start_date': '2026-07-21T06:00:00Z'},
            {'activity_type': 'Ride', 'distance': 20000, 'start_date': '2026-07-22T06:00:00Z'},
        ]
        cur = _bucket_weekly_trends(acts, now)[-1]
        assert cur['strength_sessions'] == 1
        assert cur['other_sessions'] == 1
        assert cur['runs'] == 0
        assert cur['run_km'] == 0.0

    def test_zero_volume_weeks_are_zero_not_missing(self):
        now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
        trends = _bucket_weekly_trends([], now)
        assert len(trends) == 12
        assert all(t['run_km'] == 0.0 and t['runs'] == 0 for t in trends)

    def test_activities_outside_window_ignored(self):
        now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
        acts = [{'activity_type': 'Run', 'distance': 9999000,
                 'start_date': '2020-01-01T00:00:00Z'}]
        trends = _bucket_weekly_trends(acts, now)
        assert all(t['runs'] == 0 for t in trends)

    def test_sparse_history_only_fills_matching_weeks(self):
        now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
        acts = [{'activity_type': 'Run', 'distance': 12000, 'moving_time': 3600,
                 'start_date': '2026-06-15T06:00:00Z'}]  # week of 2026-06-15
        trends = _bucket_weekly_trends(acts, now)
        populated = [t for t in trends if t['runs'] > 0]
        assert len(populated) == 1
        assert populated[0]['week_start'] == '2026-06-15'
        assert populated[0]['run_km'] == 12.0


class TestCompletedWeekVolumeChange:
    """0.4 — compare the two most recent completed weeks only (R2.5)."""

    def _wk(self, run_km, complete=True):
        return {'run_km': run_km, 'complete': complete}

    def test_none_when_fewer_than_two_completed(self):
        assert _completed_week_volume_change([]) is None
        assert _completed_week_volume_change([self._wk(10)]) is None
        # One completed week + the current incomplete week is still insufficient.
        assert _completed_week_volume_change([self._wk(10), self._wk(12, complete=False)]) is None

    def test_compares_last_two_completed_ignoring_current_week(self):
        trends = [self._wk(20), self._wk(30), self._wk(999, complete=False)]
        assert _completed_week_volume_change(trends) == 50.0

    def test_none_when_previous_week_zero(self):
        assert _completed_week_volume_change([self._wk(0), self._wk(15)]) is None

    def test_negative_change(self):
        assert _completed_week_volume_change([self._wk(40), self._wk(30)]) == -25.0


class TestExtractRecovery:
    """0.3 — recovery freshness + current vs 30-day sleep + zero deltas (R3)."""

    def _activity(self, trends=None, fitness=None, start_date='2026-07-26T08:00:00Z'):
        icu = {'fitness': fitness or {}, 'trends': trends or {}}
        return {
            'start_date': start_date,
            'created_at': start_date,
            'intervals_icu_json': json.dumps(icu),
        }

    def test_none_when_no_intervals_data(self):
        assert _extract_recovery([{'activity_id': 'x'}]) is None

    def test_current_vs_average_sleep_separated(self):
        now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
        act = self._activity(trends={
            'sleep_duration': {'current': 25200, 'avg_30d': 28800, 'delta_7d': -600},
        })
        rec = _extract_recovery([act], now)
        assert rec['sleep_current_sec'] == 25200.0
        assert rec['sleep_average_30d_sec'] == 28800.0
        assert rec['sleep_current_display'] == _format_sleep(25200)
        assert rec['sleep_average_30d_display'] == _format_sleep(28800)
        # Legacy field keeps the 30-day average for frontend compatibility.
        assert rec['sleep_display'] == _format_sleep(28800)

    def test_zero_deltas_preserved_not_nulled(self):
        now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
        act = self._activity(trends={
            'vo2max': {'current': 55, 'delta_7d': 0},
            'resting_hr': {'delta_7d': 0},
            'sleep_duration': {'current': 0, 'avg_30d': 0, 'delta_7d': 0},
        })
        rec = _extract_recovery([act], now)
        assert rec['vo2max_delta_7d'] == 0.0
        assert rec['resting_hr_delta_7d'] == 0.0
        assert rec['sleep_delta_7d_sec'] == 0.0
        assert rec['sleep_delta_7d_min'] == 0
        assert rec['sleep_current_sec'] == 0.0

    def test_freshness_fields_present_and_fresh(self):
        now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
        act = self._activity(
            start_date='2026-07-26T08:00:00Z',
            fitness={'form': -5, 'ctl': 40, 'atl': 45},
        )
        rec = _extract_recovery([act], now)
        assert rec['source'] == 'intervals_icu'
        assert rec['as_of'] == '2026-07-26'
        assert rec['fetched_at'] == '2026-07-26T08:00:00Z'
        assert rec['stale'] is False
        assert rec['form'] == -5.0

    def test_stale_when_older_than_threshold(self):
        now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
        act = self._activity(start_date='2026-07-20T08:00:00Z')  # ~6 days old
        rec = _extract_recovery([act], now, stale_threshold_hours=36)
        assert rec['stale'] is True

    def test_invalid_measurement_date_is_stale(self):
        now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
        rec = _extract_recovery([
            self._activity(start_date='not-a-date', fitness={'form': -30}),
        ], now)
        assert rec['as_of'] is None
        assert rec['stale'] is True
        assert _detect_health_anomalies(rec) == []

    def test_missing_fields_return_none_without_crash(self):
        now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
        rec = _extract_recovery([self._activity(trends={}, fitness={})], now)
        assert rec['form'] is None
        assert rec['vo2max'] is None
        assert rec['sleep_current_sec'] is None
        assert rec['sleep_average_30d_sec'] is None


class TestHealthAnomaliesStaleSuppression:
    """0.3 — freshness-dependent anomalies are suppressed on stale data (R3.6)."""

    def test_stale_suppresses_all_anomalies(self):
        recovery = {
            'resting_hr_delta_7d': 8, 'form': -30,
            'sleep_delta_7d_min': -60, 'stale': True,
        }
        assert _detect_health_anomalies(recovery) == []

    def test_fresh_still_fires(self):
        recovery = {'resting_hr_delta_7d': 8, 'form': -30, 'stale': False}
        ids = {a['id'] for a in _detect_health_anomalies(recovery)}
        assert 'resting_hr_up' in ids
        assert 'form_low' in ids


class TestCoachSummaryContract:
    """0.1/0.4 — additive V2 fields present, legacy fields preserved."""

    @patch('api.dashboard_api.dynamodb')
    def test_additive_fields_present_and_legacy_preserved(self, mock_dynamo):
        activities_table = MagicMock()
        activities_table.query.return_value = {'Items': []}
        config_table = MagicMock()
        config_table.get_item.return_value = {'Item': {}}
        sessions_table = MagicMock()
        sessions_table.scan.return_value = {'Items': []}
        mock_dynamo.Table.side_effect = lambda name: {
            'test-activities': activities_table,
            'test-user-config': config_table,
            'test-coaching-sessions': sessions_table,
        }.get(name, MagicMock())

        result = get_coach_summary('42')

        # Additive V2 correctness fields.
        assert result['schema_version'] == 1
        assert isinstance(result['weekly_trends'], list)
        assert len(result['weekly_trends']) == 12
        assert 'volume_change_completed_weeks_pct' in result

        # Legacy fields preserved for frontend compatibility.
        assert 'trends' in result
        assert 'weekly_volume_km' in result['trends']
        assert 'recovery' in result['trends']
        assert 'health_anomalies' in result['trends']
        assert 'current_week' in result
        assert 'recent_feedback' in result
        assert 'athlete_profile' in result


class TestCoachSummaryCampusCompliance:
    """Provider and local Campus completion states share canonical semantics."""

    @patch('api.dashboard_api.dynamodb')
    def test_provider_completed_session_counts_as_completed(self, mock_dynamo):
        activities_table = MagicMock()
        activities_table.query.return_value = {'Items': []}
        config_table = MagicMock()
        config_table.get_item.return_value = {'Item': {}}
        sessions_table = MagicMock()
        sessions_table.scan.return_value = {
            'Items': [{
                'session_date': 'week-2026-W30',
                'session_id': '1',
                'provider_status': 'completed',
                'is_current_week': True,
            }],
        }
        mock_dynamo.Table.side_effect = lambda name: {
            'test-activities': activities_table,
            'test-user-config': config_table,
            'test-coaching-sessions': sessions_table,
        }.get(name, MagicMock())

        result = get_coach_summary('42')

        assert result['trends']['compliance'] == {
            'planned': 1,
            'completed': 1,
            'percentage': 100,
        }
