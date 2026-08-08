"""Unit tests for the shared Campus matcher and the coach's authoritative signal.

The content and coach branches run in parallel. The content branch marks a plan
session done as soon as it matches, so a coach branch that read the stored
completion marker would see the session as done or still to do depending on which
branch won the race. Both branches therefore call one deterministic matcher,
``match_campus_session``, which recomputes the match from laps.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

os.environ.setdefault('AWS_REGION', 'eu-west-1')
os.environ.setdefault('COACHING_SESSIONS_TABLE', 'campus-coaching-sessions')

from processing import modules_processing as mp  # noqa: E402


SEUIL_30_W31 = {
    'session_id': '1785110400000_2',
    'title': 'Seuil 30',
    'week_date_iso': '2026-W31',
    'sport': 'road',
    'status': 'todo',
    'provider_status': 'todo',
    'expected_duration_min': 38,
    'intervals': [
        {'type': 'warm-up', 'duration': '15 min', 'pace': 'EF (6:07/km)'},
        {'type': 'block', 'repeat': 9, 'exercises': [
            {'type': 'work', 'duration': '1 min', 'pace': 'Seuil 30 (4:26/km)'},
            {'type': 'recovery', 'duration': '1 min', 'pace': 'Lent (11:30/km)'},
        ]},
        {'type': 'cool-down', 'duration': '5 min', 'pace': 'EF (6:07/km)'},
    ],
}


def _interval_laps():
    """9x1min at ~4:25/km alternating with 1min recoveries, plus warm-up.

    ``average_speed`` (m/s) is what _analyze_lap_structure reads to derive pace.
    """
    laps = [{
        'distance': 2489.0, 'moving_time': 900.0,
        'average_speed': 2489.0 / 900.0, 'average_heartrate': 138.0,
    }]
    for _ in range(9):
        laps.append({
            'distance': 226.0, 'moving_time': 60.0,
            'average_speed': 226.0 / 60.0, 'average_heartrate': 160.0,
        })
        laps.append({
            'distance': 140.0, 'moving_time': 60.0,
            'average_speed': 140.0 / 60.0, 'average_heartrate': 159.0,
        })
    return laps


ACTIVITY = {
    'id': '19559992637',
    'start_date': '2026-08-01T17:39:17Z',
    'moving_time': 2345,
    'type': 'Run',
}


def _mock_dynamo(items):
    table = MagicMock()
    # Week-scoped read is a Query on the session_date partition key.
    table.query.return_value = {'Items': items}
    table.scan.return_value = {'Items': items}
    dynamo = MagicMock()
    dynamo.Table.return_value = table
    return table, dynamo


class TestSharedMatcher:
    def test_matches_the_session_of_the_activity_week(self):
        _, dynamo = _mock_dynamo([SEUIL_30_W31])
        with patch('processing.modules_processing.dynamodb', dynamo):
            result = mp.match_campus_session(
                ACTIVITY, laps=_interval_laps(), current_activity_id='19559992637'
            )
        assert result['matched_session']['title'] == 'Seuil 30'
        assert result['matched_session']['week_date_iso'] == '2026-W31'
        assert result['match_score'] >= mp.MATCH_THRESHOLD

    def test_returns_no_match_below_threshold(self):
        """A flat easy run must not be forced onto an interval session."""
        flat = [{'distance': 6000.0, 'moving_time': 2200.0,
                 'average_speed': 6000.0 / 2200.0, 'average_heartrate': 138.0}]
        _, dynamo = _mock_dynamo([SEUIL_30_W31])
        with patch('processing.modules_processing.dynamodb', dynamo):
            result = mp.match_campus_session(
                {**ACTIVITY, 'moving_time': 2200}, laps=flat,
                current_activity_id='19559992637',
            )
        assert result['matched_session'] is None
        assert result['sessions']

    def test_no_sessions_yields_empty_result(self):
        _, dynamo = _mock_dynamo([])
        with patch('processing.modules_processing.dynamodb', dynamo):
            result = mp.match_campus_session(ACTIVITY, laps=_interval_laps())
        assert result == {'sessions': [], 'matched_session': None, 'match_score': 0.0}

    def test_tolerates_missing_moving_time_and_type(self):
        _, dynamo = _mock_dynamo([SEUIL_30_W31])
        with patch('processing.modules_processing.dynamodb', dynamo):
            result = mp.match_campus_session(
                {'start_date': '2026-08-01T17:39:17Z'}, laps=_interval_laps()
            )
        assert 'match_score' in result


class TestRaceImmunity:
    """The session bound to the current activity stays matchable."""

    def test_session_already_marked_done_for_this_activity_is_kept(self):
        already_done = {
            **SEUIL_30_W31,
            'local_status': 'done',
            'matched_activity_id': '19559992637',
        }
        _, dynamo = _mock_dynamo([already_done])
        with patch('processing.modules_processing.dynamodb', dynamo):
            sessions = mp._get_recent_campus_sessions(
                '2026-08-01T17:39:17Z', current_activity_id='19559992637'
            )
        assert len(sessions) == 1, "content branch marking it done must not hide it"

    def test_session_done_for_a_different_activity_is_still_excluded(self):
        other = {
            **SEUIL_30_W31,
            'local_status': 'done',
            'matched_activity_id': '11111111',
        }
        _, dynamo = _mock_dynamo([other])
        with patch('processing.modules_processing.dynamodb', dynamo):
            sessions = mp._get_recent_campus_sessions(
                '2026-08-01T17:39:17Z', current_activity_id='19559992637'
            )
        assert sessions == []

    def test_match_is_identical_before_and_after_the_completion_marker(self):
        """Same inputs, same verdict, whichever branch ran first."""
        before = SEUIL_30_W31
        after = {
            **SEUIL_30_W31,
            'local_status': 'done',
            'matched_activity_id': '19559992637',
        }
        results = []
        for session in (before, after):
            _, dynamo = _mock_dynamo([session])
            with patch('processing.modules_processing.dynamodb', dynamo):
                results.append(mp.match_campus_session(
                    ACTIVITY, laps=_interval_laps(),
                    current_activity_id='19559992637',
                ))
        assert results[0]['matched_session']['title'] == \
            results[1]['matched_session']['title']
        assert results[0]['match_score'] == results[1]['match_score']

    def test_id_comparison_survives_int_vs_str(self):
        """Strava ids travel as int in payloads and str in DynamoDB."""
        done = {
            **SEUIL_30_W31,
            'local_status': 'done',
            'matched_activity_id': '19559992637',
        }
        _, dynamo = _mock_dynamo([done])
        with patch('processing.modules_processing.dynamodb', dynamo):
            sessions = mp._get_recent_campus_sessions(
                '2026-08-01T17:39:17Z', current_activity_id=19559992637
            )
        assert len(sessions) == 1


class TestContentBranchStillWorks:
    """_apply_campus_coach_processing must keep its published module contract."""
    def test_matched_session_and_score_exposed_to_content(self):
        _, dynamo = _mock_dynamo([SEUIL_30_W31])
        with patch('processing.modules_processing.dynamodb', dynamo):
            enhanced = mp._apply_campus_coach_processing(
                {**ACTIVITY, 'laps': _interval_laps()},
                {'name': 'campus_coach'},
                laps_data=_interval_laps(),
            )
        assert enhanced['matched_session']['title'] == 'Seuil 30'
        assert enhanced['match_score'] >= mp.MATCH_THRESHOLD
        assert enhanced['sessions_available'] is True
        assert enhanced['session_count'] == 1

    def test_falls_back_to_all_sessions_when_no_strong_match(self):
        flat = [{'distance': 6000.0, 'moving_time': 2200.0,
                 'average_speed': 6000.0 / 2200.0, 'average_heartrate': 138.0}]
        _, dynamo = _mock_dynamo([SEUIL_30_W31])
        with patch('processing.modules_processing.dynamodb', dynamo):
            enhanced = mp._apply_campus_coach_processing(
                {**ACTIVITY, 'moving_time': 2200}, {'name': 'campus_coach'},
                laps_data=flat,
            )
        assert 'matched_session' not in enhanced
        assert enhanced['session_count'] == 1
        assert 'No strong match' in enhanced['note']

    def test_no_sessions_marks_module_unavailable(self):
        _, dynamo = _mock_dynamo([])
        with patch('processing.modules_processing.dynamodb', dynamo):
            enhanced = mp._apply_campus_coach_processing(
                ACTIVITY, {'name': 'campus_coach'}, laps_data=_interval_laps()
            )
        assert enhanced['sessions_available'] is False
        assert enhanced['campus_coach_sessions'] == []


# --------------------------------------------------------------------------- #
# Coach branch: the authoritative signal reaches the agent payload
# --------------------------------------------------------------------------- #
os.environ.setdefault('ACTIVITIES_TABLE', 'strava-ai-boost-activities')
os.environ.setdefault('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration')
sys.modules.setdefault('agents', MagicMock())
sys.modules.setdefault('agents.coach_agent', MagicMock())

from processing import coach_generator as cg  # noqa: E402


class TestCoachReceivesAuthoritativeSignal:
    """Drive the real coach handler and capture what it sends to the agent."""

    def _run(self, plan_sessions, matcher_sessions, laps):
        captured = {}

        def _fake_invoke(activity_data, user_config, historical_summary):
            captured['hs'] = historical_summary
            return {'strava_block': 'ok'}

        coach_table = MagicMock()
        coach_table.get_item.return_value = {'Item': {}}
        # 1st scan: current/future plan. 2nd scan: athlete-context.
        coach_table.scan.side_effect = [{'Items': plan_sessions}, {'Items': []}]
        coach_dynamo = MagicMock()
        coach_dynamo.Table.return_value = coach_table

        match_table = MagicMock()
        match_table.query.return_value = {'Items': matcher_sessions}
        match_table.scan.return_value = {'Items': matcher_sessions}
        match_dynamo = MagicMock()
        match_dynamo.Table.return_value = match_table

        activity = {
            'start_date_local': '2026-08-01T17:39:17Z',
            'moving_time': 2345,
            'type': 'Run',
            '_laps': laps,
        }

        with patch.object(cg, 'dynamodb', coach_dynamo), \
                patch('processing.modules_processing.dynamodb', match_dynamo), \
                patch.object(cg, 'COACH_AGENT_ARN', 'arn:aws:bedrock-agentcore:eu-west-1:1:runtime/c'), \
                patch.object(cg, 'retrieve_activity_data', return_value=activity), \
                patch.object(cg, 'build_historical_summary', return_value={}), \
                patch.object(cg, 'extract_and_store_prs'), \
                patch.object(cg, 'store_coach_feedback'), \
                patch.object(cg, 'write_coaching_observation'), \
                patch.object(cg, '_invoke_coach_agent', side_effect=_fake_invoke):
            response = cg.handler(
                {'activity_id': '19559992637', 'user_id': 'u1', 'user_config': {}}, None
            )

        assert response['statusCode'] == 200
        return captured['hs']

    def test_matched_session_reaches_the_agent_payload(self):
        plan = {**SEUIL_30_W31, 'is_current_week': True, 'is_future': False}
        hs = self._run([plan], [SEUIL_30_W31], _interval_laps())

        signal = hs['campus_matched_session']
        assert signal is not None, "the coach must be told which session was closed"
        assert signal['title'] == 'Seuil 30'
        assert signal['week_date_iso'] == '2026-W31'
        assert signal['match_score'] >= mp.MATCH_THRESHOLD

    def test_signal_is_none_for_an_off_plan_activity(self):
        flat = [{
            'distance': 6000.0, 'moving_time': 2200.0,
            'average_speed': 6000.0 / 2200.0, 'average_heartrate': 138.0,
        }]
        plan = {**SEUIL_30_W31, 'is_current_week': True, 'is_future': False}
        hs = self._run([plan], [SEUIL_30_W31], flat)

        assert hs['campus_matched_session'] is None

    def test_signal_survives_the_content_branch_marking_it_done(self):
        """Race immunity end to end through the coach handler."""
        already_done = {
            **SEUIL_30_W31,
            'local_status': 'done',
            'matched_activity_id': '19559992637',
        }
        plan = {**already_done, 'is_current_week': True, 'is_future': False}
        hs = self._run([plan], [already_done], _interval_laps())

        assert hs['campus_matched_session']['title'] == 'Seuil 30'

    def test_matcher_failure_degrades_without_losing_the_plan(self):
        plan = {**SEUIL_30_W31, 'is_current_week': True, 'is_future': False}
        captured = {}

        def _fake_invoke(activity_data, user_config, historical_summary):
            captured['hs'] = historical_summary
            return {'strava_block': 'ok'}

        coach_table = MagicMock()
        coach_table.get_item.return_value = {'Item': {}}
        coach_table.scan.side_effect = [{'Items': [plan]}, {'Items': []}]
        coach_dynamo = MagicMock()
        coach_dynamo.Table.return_value = coach_table

        broken = MagicMock()
        broken.Table.side_effect = RuntimeError('DynamoDB unavailable')

        with patch.object(cg, 'dynamodb', coach_dynamo), \
                patch('processing.modules_processing.dynamodb', broken), \
                patch.object(cg, 'COACH_AGENT_ARN', 'arn:aws:bedrock-agentcore:eu-west-1:1:runtime/c'), \
                patch.object(cg, 'retrieve_activity_data',
                             return_value={'start_date_local': '2026-08-01T17:39:17Z',
                                           'moving_time': 2345, 'type': 'Run',
                                           '_laps': _interval_laps()}), \
                patch.object(cg, 'build_historical_summary', return_value={}), \
                patch.object(cg, 'extract_and_store_prs'), \
                patch.object(cg, 'store_coach_feedback'), \
                patch.object(cg, 'write_coaching_observation'), \
                patch.object(cg, '_invoke_coach_agent', side_effect=_fake_invoke):
            response = cg.handler(
                {'activity_id': '19559992637', 'user_id': 'u1', 'user_config': {}}, None
            )

        assert response['statusCode'] == 200
        hs = captured['hs']
        assert hs['campus_matched_session'] is None
        assert hs['campus_coach_plan']['sessions'], "plan context must survive"


class TestGymSessionDoesNotCloseCampusPpg:
    """A gym session must not silently close the Campus PPG session.

    The athlete follows his own strength program (`strength_program` in user
    preferences: Upper A, Upper B, Rappel, each 1x/semaine), which is distinct
    from the running-specific PPG the Campus plan prescribes. The scorer returned
    a hardcoded 0.8 for any WeightTraining against any 'Renforcement' session,
    above MATCH_THRESHOLD, so every gym session closed the planned PPG. That both
    hid a session still to do and made the coach report two strength sessions
    where there was one.
    """

    PPG = {
        'title': 'Renforcement',
        'week_date_iso': '2026-W32',
        'sport': 'ppg',
        'status': 'todo',
        'provider_status': 'todo',
        'expected_duration_min': 30,
        'intervals': [
            {'type': 'block', 'repeat': 2, 'exercises': [
                {'type': 'work', 'duration': '30 sec', 'pace': ''},
                {'type': 'recovery', 'duration': '1:00 min', 'pace': ''},
            ]},
        ],
    }

    def test_score_stays_below_match_threshold(self):
        score = mp._score_session_match(self.PPG, [], 48.0, 'weighttraining')
        assert score < mp.MATCH_THRESHOLD, (
            f"a gym session scored {score} against the Campus PPG and would "
            f"close it automatically"
        )

    def test_no_match_is_returned_for_a_gym_activity(self):
        _, dynamo = _mock_dynamo([self.PPG])
        activity = {
            'id': '19596127525',
            'start_date': '2026-08-04T10:28:28Z',
            'moving_time': 2880,
            'type': 'WeightTraining',
        }
        with patch('processing.modules_processing.dynamodb', dynamo):
            result = mp.match_campus_session(
                activity, laps=[], current_activity_id='19596127525'
            )
        assert result['matched_session'] is None, (
            "the Campus PPG session must stay open"
        )

    def test_ppg_is_still_offered_as_context(self):
        """Not matching must not mean hiding the session from the coach."""
        _, dynamo = _mock_dynamo([self.PPG])
        activity = {
            'id': 'a1', 'start_date': '2026-08-04T10:28:28Z',
            'moving_time': 2880, 'type': 'WeightTraining',
        }
        with patch('processing.modules_processing.dynamodb', dynamo):
            result = mp.match_campus_session(activity, laps=[])
        assert [s['title'] for s in result['sessions']] == ['Renforcement']

    def test_running_activity_never_matches_ppg(self):
        assert mp._score_session_match(self.PPG, [], 40.0, 'run') == 0.0

    def test_gym_activity_never_matches_a_running_session(self):
        running_session = {
            'title': 'Endurance Fondamentale',
            'week_date_iso': '2026-W32',
            'sport': 'road',
            'intervals': [{'type': 'work', 'duration': '40 min', 'pace': 'EF'}],
        }
        assert mp._score_session_match(
            running_session, [], 48.0, 'weighttraining'
        ) == 0.0


class TestCampusDeclarationDiscriminatesPpg:
    """"renfo campus" in the athlete's own text is what confirms the PPG match."""

    PPG = {
        'title': 'Renforcement',
        'week_date_iso': '2026-W32',
        'sport': 'ppg',
        'status': 'todo',
        'provider_status': 'todo',
        'expected_duration_min': 30,
        'intervals': [],
    }

    @staticmethod
    def _gym(name='Entraînement aux poids le midi', description='', **extra):
        return {
            'id': '19596127525',
            'start_date': '2026-08-04T10:28:28Z',
            'moving_time': 2880,
            'type': 'WeightTraining',
            'name': name,
            'description': description,
            **extra,
        }

    def _match(self, activity):
        _, dynamo = _mock_dynamo([self.PPG])
        with patch('processing.modules_processing.dynamodb', dynamo):
            return mp.match_campus_session(activity, laps=[])

    def test_own_program_session_does_not_close_the_ppg(self):
        """The real case: "Quick upper midi" with his own exercises."""
        activity = self._gym(description='Quick upper midi\n04/08\nTrac 10-10-10\nlow row mach 8x90')
        assert self._match(activity)['matched_session'] is None

    def test_declared_campus_session_matches(self):
        activity = self._gym(description='Renfo campus fait ce matin')
        result = self._match(activity)
        assert result['matched_session'] is not None
        assert result['matched_session']['title'] == 'Renforcement'
        assert result['match_score'] >= mp.MATCH_THRESHOLD

    def test_declaration_in_the_title_also_counts(self):
        activity = self._gym(name='Renfo Campus')
        assert self._match(activity)['matched_session'] is not None

    def test_detection_is_case_insensitive(self):
        assert mp._declares_campus_session({'name': 'RENFO CAMPUS'}) is True
        assert mp._declares_campus_session({'description': 'campus coach ppg'}) is True

    def test_original_fields_win_over_enhanced_ones(self):
        """Our own generated text says "Séance Campus Coach"; it must not confirm.

        Otherwise reprocessing an already-enhanced activity would let our output
        validate the match, a self-fulfilling loop.
        """
        activity = self._gym(
            name='Séance Campus Coach validée',
            description='Séance Campus Coach: renforcement du jour',
            original_name='Entraînement aux poids le midi',
            original_description='Quick upper midi, trac 10-10-10',
        )
        assert mp._declares_campus_session(activity) is False
        assert self._match(activity)['matched_session'] is None

    def test_falls_back_to_current_fields_when_no_original(self):
        activity = self._gym(description='renfo campus')
        assert mp._declares_campus_session(activity) is True

    def test_no_text_at_all_is_not_a_declaration(self):
        assert mp._declares_campus_session({}) is False
        assert mp._declares_campus_session({'name': None, 'description': None}) is False
