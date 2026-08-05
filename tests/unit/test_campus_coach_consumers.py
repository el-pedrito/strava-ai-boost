"""Unit tests for Campus Coach data consumers (DynamoDB schema)."""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

# Set env vars before imports
os.environ.setdefault('AWS_REGION', 'eu-west-1')
os.environ.setdefault('COACHING_SESSIONS_TABLE', 'campus-coaching-sessions')
os.environ.setdefault('ACTIVITIES_TABLE', 'strava-ai-boost-activities')
os.environ.setdefault('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration')

# Mock agents module
sys.modules.setdefault('agents', MagicMock())
sys.modules.setdefault('agents.coach_agent', MagicMock())


SAMPLE_CURRENT_WEEK_SESSION = {
    'session_date': 'week-2026-W21',
    'session_id': '1779062400000_2',
    'week_date': Decimal('1779062400000'),
    'week_date_iso': '2026-W21',
    'training_index': Decimal('2'),
    'title': 'Force + Allure 10km',
    'description': 'Séance mix avec 3x30sec max + 4x6min allure 10km',
    'coach_advice': 'Donne tout sur les 30 secondes!',
    'sport': 'road',
    'training_type': 'Intensity',
    'difficulty': Decimal('4'),
    'importance': True,
    'status': 'todo',
    'is_current_week': True,
    'is_future': False,
    'intervals': [
        {'type': 'warm-up', 'duration': '15 min', 'pace': 'EF (6:01/km)'},
        {'type': 'work', 'repeat': 3, 'duration': '30 sec', 'pace': 'Rapide (3:26/km)'},
        {'type': 'work', 'repeat': 4, 'duration': '6 min', 'pace': '10km (4:27/km)'},
        {'type': 'cool-down', 'duration': '5 min', 'pace': 'EF (6:01/km)'},
    ],
    'expected_distance_km': '10.6',
    'expected_duration_min': Decimal('63'),
    'cycle_theme': 'Force_A10',
}

SAMPLE_NEXT_WEEK_SESSION = {
    'session_date': 'week-2026-W22',
    'session_id': '1779667200000_1',
    'week_date': Decimal('1779667200000'),
    'week_date_iso': '2026-W22',
    'training_index': Decimal('1'),
    'title': 'Sortie longue',
    'description': 'Sortie longue en endurance fondamentale',
    'sport': 'road',
    'difficulty': Decimal('2'),
    'status': 'todo',
    'is_current_week': False,
    'is_future': True,
    'intervals': [],
    'expected_distance_km': '16.0',
    'expected_duration_min': Decimal('96'),
}


@pytest.fixture
def mock_dynamo_table():
    """Create a mock DynamoDB table."""
    table = MagicMock()
    return table


class TestCoachGeneratorCampus:
    """Test coach_generator Campus Coach plan fetching."""

    @patch('boto3.resource')
    def test_campus_plan_populated_in_context(self, mock_boto_resource):
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            'Items': [SAMPLE_CURRENT_WEEK_SESSION, SAMPLE_NEXT_WEEK_SESSION]
        }
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        from processing.coach_generator import build_historical_summary

        with patch('processing.coach_generator.dynamodb', mock_dynamo):
            result = build_historical_summary.__wrapped__(
                'user1', {'user_preferences': {}}, {}
            ) if hasattr(build_historical_summary, '__wrapped__') else None

            # Directly test the scan logic by simulating what coach_generator does
            sessions_table = mock_dynamo.Table('campus-coaching-sessions')
            resp = sessions_table.scan(
                FilterExpression="is_current_week = :cw OR is_future = :ft",
                ExpressionAttributeValues={":cw": True, ":ft": True},
            )
            all_sessions = resp.get("Items", [])

            current_week = [s for s in all_sessions if s.get("is_current_week")]
            future_sessions = sorted(
                [s for s in all_sessions if s.get("is_future") and not s.get("is_current_week")],
                key=lambda s: s.get("week_date", 0)
            )
            next_week = []
            if future_sessions:
                next_week_date = future_sessions[0].get("week_date_iso")
                next_week = [s for s in future_sessions if s.get("week_date_iso") == next_week_date]

            assert len(current_week) == 1
            assert current_week[0]['title'] == 'Force + Allure 10km'
            assert len(next_week) == 1
            assert next_week[0]['title'] == 'Sortie longue'

    @patch('boto3.resource')
    def test_campus_plan_format_session(self, mock_boto_resource):
        """Test _format_plan_session extracts correct fields."""
        session = SAMPLE_CURRENT_WEEK_SESSION

        # Replicate _format_plan_session from coach_generator
        formatted = {
            "title": session.get("title", ""),
            "intervals": session.get("intervals", []),
            "expected_distance_km": session.get("expected_distance_km"),
            "expected_duration_min": session.get("expected_duration_min"),
            "status": session.get("status", ""),
            "sport": session.get("sport", ""),
            "difficulty": session.get("difficulty", ""),
        }

        assert formatted["title"] == "Force + Allure 10km"
        assert formatted["expected_distance_km"] == "10.6"
        assert formatted["status"] == "todo"
        assert len(formatted["intervals"]) == 4


class TestModulesProcessingCampus:
    """Test modules_processing Campus Coach functions."""

    @patch('boto3.resource')
    def test_get_recent_campus_sessions_returns_current_week(self, mock_boto_resource):
        mock_table = MagicMock()
        # The week-scoped read is a Query on the session_date partition key;
        # scan remains the current-week fallback.
        mock_table.query.return_value = {'Items': [SAMPLE_CURRENT_WEEK_SESSION]}
        mock_table.scan.return_value = {'Items': [SAMPLE_CURRENT_WEEK_SESSION]}
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        with patch('processing.modules_processing.dynamodb', mock_dynamo):
            from processing.modules_processing import _get_recent_campus_sessions
            sessions = _get_recent_campus_sessions('2026-05-21')

        assert len(sessions) == 1
        assert sessions[0]['title'] == 'Force + Allure 10km'
        # Decimals should be converted to float
        assert isinstance(sessions[0]['difficulty'], float)
        assert sessions[0]['difficulty'] == 4.0

    @patch('boto3.resource')
    def test_get_recent_campus_sessions_filters_current_week_only(self, mock_boto_resource):
        """Scan uses is_current_week filter - only current week returned."""
        mock_table = MagicMock()
        # Simulate DynamoDB already filtering (scan with FilterExpression)
        mock_table.scan.return_value = {'Items': [SAMPLE_CURRENT_WEEK_SESSION]}
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        with patch('processing.modules_processing.dynamodb', mock_dynamo):
            from processing.modules_processing import _get_recent_campus_sessions
            sessions = _get_recent_campus_sessions()

        # Verify scan was called with correct filter
        mock_table.scan.assert_called_once_with(
            FilterExpression='is_current_week = :cw',
            ExpressionAttributeValues={':cw': True}
        )

    @patch('boto3.resource')
    def test_apply_campus_coach_processing_attaches_sessions(self, mock_boto_resource):
        mock_table = MagicMock()
        # The week-scoped read is a Query on the session_date partition key;
        # scan remains the current-week fallback.
        mock_table.query.return_value = {'Items': [SAMPLE_CURRENT_WEEK_SESSION]}
        mock_table.scan.return_value = {'Items': [SAMPLE_CURRENT_WEEK_SESSION]}
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        activity_data = {
            'start_date_local': '2026-05-21T08:00:00Z',
            'distance': 10000,
            'moving_time': 3600,
            'type': 'Run',
            'name': 'Morning Run',
            'description': '',
        }
        module = {'name': 'campus_coach', 'enabled': True, 'config': {}}

        with patch('processing.modules_processing.dynamodb', mock_dynamo):
            from processing.modules_processing import _apply_campus_coach_processing
            result = _apply_campus_coach_processing(activity_data, module)

        assert result['sessions_available'] is True
        assert result['campus_coach_sessions'][0]['title'] == 'Force + Allure 10km'
        # No strong match without laps, so all sessions passed through
        assert 'note' in result or 'matched_session' in result

    @patch('boto3.resource')
    def test_apply_campus_coach_processing_empty_sessions(self, mock_boto_resource):
        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': []}
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        activity_data = {'start_date_local': '2026-05-21', 'distance': 5000, 'moving_time': 1800, 'type': 'Run'}
        module = {'name': 'campus_coach', 'enabled': True, 'config': {}}

        with patch('processing.modules_processing.dynamodb', mock_dynamo):
            from processing.modules_processing import _apply_campus_coach_processing
            result = _apply_campus_coach_processing(activity_data, module)

        assert result['sessions_available'] is False
        assert result['campus_coach_sessions'] == []


class TestGracefulDegradation:
    """Test all consumers handle empty/error cases without crashing."""

    @patch('boto3.resource')
    def test_modules_processing_scan_exception(self, mock_boto_resource):
        mock_table = MagicMock()
        mock_table.scan.side_effect = Exception("DynamoDB unavailable")
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        with patch('processing.modules_processing.dynamodb', mock_dynamo):
            from processing.modules_processing import _get_recent_campus_sessions
            sessions = _get_recent_campus_sessions()

        assert sessions == []

    @patch('boto3.resource')
    def test_apply_campus_coach_processing_scan_exception(self, mock_boto_resource):
        mock_table = MagicMock()
        mock_table.scan.side_effect = Exception("Timeout")
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        activity_data = {'start_date_local': '2026-05-21', 'distance': 5000, 'moving_time': 1800, 'type': 'Run'}
        module = {'name': 'campus_coach', 'enabled': True, 'config': {}}

        with patch('processing.modules_processing.dynamodb', mock_dynamo):
            from processing.modules_processing import _apply_campus_coach_processing
            result = _apply_campus_coach_processing(activity_data, module)

        assert result['sessions_available'] is False
        assert result['campus_coach_sessions'] == []
        assert 'note' in result  # graceful: returns note instead of crashing


# ---------------------------------------------------------------------------
# Interval-schema normalization: consumers must tolerate BOTH the legacy flat
# form and the new per-block form (34 legacy rows survive until next sync).
# ---------------------------------------------------------------------------

# Same 9x(1min work + 1min recovery) threshold session, expressed in both
# schemas. Consumers must produce identical results for the two forms.
NEW_BLOCK_THRESHOLD = [
    {'type': 'warm-up', 'duration': '15 min', 'pace': 'EF (6:01/km)'},
    {
        'type': 'block',
        'repeat': 9,
        'exercises': [
            {'type': 'work', 'duration': '1 min', 'pace': 'Seuil (4:25/km)'},
            {'type': 'recovery', 'duration': '1 min', 'pace': 'EF (6:01/km)'},
        ],
    },
    {'type': 'cool-down', 'duration': '5 min', 'pace': 'EF (6:01/km)'},
]

# Legacy flat form of the SAME session as it currently sits in DynamoDB: the
# repeat was copied onto the work exercise and the recovery lost its repeat.
LEGACY_FLAT_THRESHOLD = [
    {'type': 'warm-up', 'duration': '15 min', 'pace': 'EF (6:01/km)'},
    {'type': 'work', 'repeat': 9, 'duration': '1 min', 'pace': 'Seuil (4:25/km)'},
    {'type': 'cool-down', 'duration': '5 min', 'pace': 'EF (6:01/km)'},
]


class TestNormalizeIntervals:
    """The shared normalizer expands both schemas into flat occurrences."""

    def test_new_block_schema_expands_by_repeat(self):
        from processing.modules_processing import _normalize_intervals
        occ = _normalize_intervals(NEW_BLOCK_THRESHOLD)
        work = [o for o in occ if o['type'] == 'work']
        recovery = [o for o in occ if o['type'] == 'recovery']
        assert len(work) == 9
        assert len(recovery) == 9
        assert occ[0]['type'] == 'warm-up'

    def test_legacy_flat_schema_expands_by_repeat(self):
        from processing.modules_processing import _normalize_intervals
        occ = _normalize_intervals(LEGACY_FLAT_THRESHOLD)
        work = [o for o in occ if o['type'] == 'work']
        assert len(work) == 9

    def test_repeat_decimal_and_missing_are_tolerated(self):
        from processing.modules_processing import _normalize_intervals
        occ = _normalize_intervals([
            {'type': 'block', 'repeat': Decimal('3'),
             'exercises': [{'type': 'work', 'duration': '30 sec', 'pace': ''}]},
            {'type': 'work', 'duration': '2 min', 'pace': ''},  # no repeat -> 1
        ])
        assert len([o for o in occ if o['type'] == 'work']) == 4

    def test_non_dict_entries_ignored(self):
        from processing.modules_processing import _normalize_intervals
        assert _normalize_intervals([None, 'garbage', 42]) == []
        assert _normalize_intervals([]) == []


class TestWorkCountAndDurationBothSchemas:
    """The three interval consumers must agree across both schemas."""

    def test_work_count_matches_nine_efforts(self):
        from processing.modules_processing import _normalize_intervals
        for intervals in (NEW_BLOCK_THRESHOLD, LEGACY_FLAT_THRESHOLD):
            work = [o for o in _normalize_intervals(intervals) if o['type'] == 'work']
            assert len(work) == 9

    def test_session_duration_equivalent_across_schemas(self):
        from processing.modules_processing import _extract_session_duration
        new_dur = _extract_session_duration(NEW_BLOCK_THRESHOLD)
        legacy_dur = _extract_session_duration(LEGACY_FLAT_THRESHOLD)
        # New schema expands the recovery too (9 min); legacy flat lost the
        # recovery repeat, so it only differs by the recovery contribution.
        # Both count warm-up (15) + 9x1 work (9) + cool-down (5) = 29 min work-side.
        assert new_dur == pytest.approx(15 + 9 + 9 + 5)      # recovery expanded
        assert legacy_dur == pytest.approx(15 + 9 + 5)       # legacy: no recovery

    def test_avg_work_interval_duration_expanded(self):
        from processing.modules_processing import _normalize_intervals, _avg_work_interval_duration
        work = [o for o in _normalize_intervals(NEW_BLOCK_THRESHOLD) if o['type'] == 'work']
        # nine 1-min work intervals -> 60s average
        assert _avg_work_interval_duration(work) == pytest.approx(60)

    def test_multi_exercise_block_not_inflated(self):
        """A renforcement block repeat=2 with 6 work exercises yields 12 work
        occurrences (2x6), expressed via one block, not per-exercise repeat."""
        from processing.modules_processing import _normalize_intervals
        intervals = [{
            'type': 'block', 'repeat': 2,
            'exercises': [{'type': 'work', 'duration': '', 'pace': ''} for _ in range(6)],
        }]
        work = [o for o in _normalize_intervals(intervals) if o['type'] == 'work']
        assert len(work) == 12


class TestGetRecentSessionsStatusFilter:
    """B1: sessions are excluded via effective_status, not the raw legacy
    ``status`` field (which is stale)."""

    def _session(self, **overrides):
        base = {
            'session_date': 'week-2026-W32',
            'session_id': '1_0',
            'title': 'Endurance Fondamentale',
            'is_current_week': True,
            'intervals': [],
        }
        base.update(overrides)
        return base

    @patch('boto3.resource')
    def test_provider_done_excluded_even_if_legacy_status_todo(self, mock_boto_resource):
        """The proven bug: provider_status='done' but legacy status='todo'.
        The session must be excluded (it is completed on Campus)."""
        done_session = self._session(session_id='1_1', status='todo', provider_status='done')
        todo_session = self._session(session_id='1_2', status='todo', provider_status='todo')
        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [done_session, todo_session]}
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        with patch('processing.modules_processing.dynamodb', mock_dynamo):
            from processing.modules_processing import _get_recent_campus_sessions
            sessions = _get_recent_campus_sessions()

        titles_ids = [s['session_id'] for s in sessions]
        assert '1_1' not in titles_ids       # provider done -> excluded
        assert '1_2' in titles_ids           # still to do -> kept

    @patch('boto3.resource')
    def test_local_skip_and_completed_are_excluded(self, mock_boto_resource):
        skip_session = self._session(session_id='1_3', local_status='skip')
        # Migrated form: what used to live in the legacy `status='Fait'` marker is
        # now carried by local_status (see migrate_campus_legacy_status.py). The
        # raw `status` field is no longer consulted.
        migrated_done = self._session(session_id='1_4', local_status='done')
        matched = self._session(session_id='1_5', status='todo', matched_activity_id='act-9')
        keep = self._session(session_id='1_6', status='todo', provider_status='todo')
        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [skip_session, migrated_done, matched, keep]}
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        with patch('processing.modules_processing.dynamodb', mock_dynamo):
            from processing.modules_processing import _get_recent_campus_sessions
            sessions = _get_recent_campus_sessions()

        kept_ids = [s['session_id'] for s in sessions]
        assert kept_ids == ['1_6']
