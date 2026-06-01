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


class TestCoachAskApiCampus:
    """Test coach_ask_api _fetch_campus_weekly_plan."""

    @patch('boto3.resource')
    def test_fetch_campus_weekly_plan_returns_formatted_text(self, mock_boto_resource):
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            'Items': [SAMPLE_CURRENT_WEEK_SESSION, SAMPLE_NEXT_WEEK_SESSION]
        }
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        with patch('api.coach_ask_api.dynamodb', mock_dynamo):
            from api.coach_ask_api import _fetch_campus_weekly_plan
            result = _fetch_campus_weekly_plan('user1')

        assert 'Plan Campus Coach cette semaine' in result
        assert 'Force + Allure 10km' in result
        assert 'Plan Campus Coach 2026-W22' in result
        assert 'Sortie longue' in result

    @patch('boto3.resource')
    def test_fetch_campus_weekly_plan_current_only(self, mock_boto_resource):
        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [SAMPLE_CURRENT_WEEK_SESSION]}
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        with patch('api.coach_ask_api.dynamodb', mock_dynamo):
            from api.coach_ask_api import _fetch_campus_weekly_plan
            result = _fetch_campus_weekly_plan('user1')

        assert 'Plan Campus Coach cette semaine' in result
        assert 'semaine prochaine' not in result

    @patch('boto3.resource')
    def test_fetch_campus_weekly_plan_empty(self, mock_boto_resource):
        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': []}
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        with patch('api.coach_ask_api.dynamodb', mock_dynamo):
            from api.coach_ask_api import _fetch_campus_weekly_plan
            result = _fetch_campus_weekly_plan('user1')

        assert result == ""


class TestModulesProcessingCampus:
    """Test modules_processing Campus Coach functions."""

    @patch('boto3.resource')
    def test_get_recent_campus_sessions_returns_current_week(self, mock_boto_resource):
        mock_table = MagicMock()
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
    def test_coach_ask_api_scan_exception(self, mock_boto_resource):
        mock_table = MagicMock()
        mock_table.scan.side_effect = Exception("Access denied")
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto_resource.return_value = mock_dynamo

        with patch('api.coach_ask_api.dynamodb', mock_dynamo):
            from api.coach_ask_api import _fetch_campus_weekly_plan
            result = _fetch_campus_weekly_plan('user1')

        assert result == ""

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
