"""Unit tests: every number the coach states comes from code, not its arithmetic.

Companion to test_coach_weekly_figures.py. The established pattern, verified on
four production cases, is that any figure left to the model was wrong and any
figure moved into code was right. These cover the non-weekly numbers audited
afterwards: the volume-ramp percentage, the activity's average pace and %FCmax,
and personal-record status.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

os.environ.setdefault('AWS_REGION', 'eu-west-1')
os.environ.setdefault('COACHING_SESSIONS_TABLE', 'campus-coaching-sessions')
os.environ.setdefault('ACTIVITIES_TABLE', 'strava-ai-boost-activities')
os.environ.setdefault('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration')
sys.modules.setdefault('agents', MagicMock())
sys.modules.setdefault('agents.coach_agent', MagicMock())

from processing import coach_generator as cg  # noqa: E402


class TestVolumeRampIsCodeComputed:
    """The ramp-rate percentage is computed in code, never by the model.

    In production the coach summed a rolling 7-day window and derived a bogus
    "+32%" alert. The percentage is now a code figure between two COMPLETE ISO
    weeks; the partial current week is excluded upstream.
    """

    def test_ramp_between_two_weeks(self):
        ramp = cg._compute_volume_ramp({'2026-W30': 30.0, '2026-W31': 36.0})
        assert ramp['from_week'] == '2026-W30'
        assert ramp['to_week'] == '2026-W31'
        assert ramp['from_km'] == 30.0 and ramp['to_km'] == 36.0
        assert ramp['delta_pct'] == 20.0
        assert ramp['exceeds_10pct'] is True

    def test_within_10pct_is_not_flagged(self):
        ramp = cg._compute_volume_ramp({'2026-W30': 40.0, '2026-W31': 42.0})
        assert ramp['delta_pct'] == 5.0
        assert ramp['exceeds_10pct'] is False

    def test_uses_the_two_most_recent_weeks(self):
        ramp = cg._compute_volume_ramp(
            {'2026-W29': 10.0, '2026-W30': 30.0, '2026-W31': 33.0}
        )
        assert ramp['from_week'] == '2026-W30'
        assert ramp['to_week'] == '2026-W31'

    def test_single_week_yields_nothing(self):
        assert cg._compute_volume_ramp({'2026-W31': 30.0}) is None

    def test_empty_yields_nothing(self):
        assert cg._compute_volume_ramp({}) is None

    def test_zero_baseline_is_not_divided(self):
        assert cg._compute_volume_ramp({'2026-W30': 0.0, '2026-W31': 20.0}) is None


class TestActivityMetricsAreProvided:
    """Pace and %FCmax are formatted in code so the model never recomputes them."""

    def test_avg_pace_is_formatted_in_code(self):
        # 2.8 m/s -> 1000/2.8 = 357.1s = 5:57/km
        metrics = cg._compute_coach_metrics([], {'average_speed': 2.8})
        assert metrics['avg_pace'] == '5:57/km'

    def test_pace_seconds_never_exceed_59(self):
        # The bug class this guards: naive formatting produced "4:87/km".
        metrics = cg._compute_coach_metrics([], {'average_speed': 3.35})
        secs = metrics['avg_pace'].split('/km')[0].split(':')[1]
        assert 0 <= int(secs) <= 59

    def test_pct_fcmax_is_computed_when_reference_available(self):
        metrics = cg._compute_coach_metrics(
            [],
            {'average_speed': 2.8, 'average_heartrate': 152,
             'max_heartrate': 178, '_max_hr_ref': 190},
        )
        assert metrics['avg_hr_pct_max'] == 80.0
        assert metrics['max_hr_pct_max'] == 93.7
        assert metrics['fcmax_reference'] == 190

    def test_ef_pace_at_hr_reuses_the_same_pace(self):
        metrics = cg._compute_coach_metrics(
            [], {'average_speed': 2.8, 'average_heartrate': 150}
        )
        assert metrics['avg_pace'] == '5:57/km'
        assert metrics['ef_pace_at_hr'] == '5:57/km @ 150bpm'

    def test_no_pace_without_speed(self):
        assert 'avg_pace' not in cg._compute_coach_metrics([], {})


class TestPrStatusFromStrava:
    """PR status comes from Strava's pr_rank, surfaced by code, not inferred."""

    def _run_handler(self, activity_data):
        captured = {}

        def _fake_invoke(activity, user_config, historical_summary):
            captured['hs'] = historical_summary
            return {'strava_block': 'ok'}

        coach_table = MagicMock()
        coach_table.get_item.return_value = {'Item': {}}
        coach_table.query.return_value = {'Items': []}
        coach_table.scan.return_value = {'Items': []}
        coach_dynamo = MagicMock()
        coach_dynamo.Table.return_value = coach_table

        with patch.object(cg, 'dynamodb', coach_dynamo), \
                patch.object(cg, 'match_campus_session',
                             return_value={'matched_session': None, 'match_score': 0.0}), \
                patch.object(cg, 'COACH_AGENT_ARN',
                             'arn:aws:bedrock-agentcore:eu-west-1:1:runtime/c'), \
                patch.object(cg, 'retrieve_activity_data', return_value=activity_data), \
                patch.object(cg, 'build_historical_summary', return_value={}), \
                patch.object(cg, 'extract_and_store_prs'), \
                patch.object(cg, 'store_coach_feedback'), \
                patch.object(cg, 'write_coaching_observation'), \
                patch.object(cg, '_invoke_coach_agent', side_effect=_fake_invoke):
            resp = cg.handler(
                {'activity_id': '9', 'user_id': 'u1', 'user_config': {}}, None
            )
        assert resp['statusCode'] == 200
        return captured['hs']

    def test_prs_set_are_listed_from_pr_rank(self):
        activity = {
            'start_date_local': '2026-08-03T17:21:26Z', 'type': 'Run',
            'best_efforts': [
                {'name': '5k', 'pr_rank': 1},
                {'name': '10k', 'pr_rank': 2},
                {'name': '1k', 'pr_rank': None},
            ],
        }
        hs = self._run_handler(activity)
        assert hs['prs_set_this_activity'] == ['5k'], (
            "only pr_rank==1 efforts are records of the day"
        )

    def test_no_pr_field_when_none_set(self):
        activity = {
            'start_date_local': '2026-08-03T17:21:26Z', 'type': 'Run',
            'best_efforts': [{'name': '5k', 'pr_rank': 2}],
        }
        hs = self._run_handler(activity)
        assert 'prs_set_this_activity' not in hs
