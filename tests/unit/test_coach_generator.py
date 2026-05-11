"""Unit tests for coach_generator Lambda"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

# Mock the agents.coach_agent module before it gets imported by the handler
mock_coach_agent = MagicMock()
sys.modules.setdefault('agents', MagicMock())
sys.modules.setdefault('agents.coach_agent', mock_coach_agent)

from processing.coach_generator import handler, build_historical_summary


@pytest.fixture
def activity_event():
    return {"activity_id": "act123", "user_id": "user1", "user_config": {"user_preferences": {}}}


@pytest.fixture
def activity_data():
    return {"name": "Morning Run", "type": "Run", "distance": 10000, "moving_time": 3600}


@pytest.fixture
def coach_feedback():
    return {
        "strava_block": "📊 Great session!",
        "detailed_analysis": {"key_metrics": "10km in 60min", "progress_note": "Improving"},
    }


class TestHandler:

    @patch('processing.coach_generator.write_coaching_observation')
    @patch('processing.coach_generator.store_coach_feedback')
    @patch('processing.coach_generator.build_historical_summary', return_value={"weeks": 4, "total_activities": 0})
    @patch('processing.coach_generator.retrieve_activity_data')
    @patch('processing.coach_generator._invoke_coach_agent')
    def test_handler_success(self, mock_invoke, mock_retrieve, mock_history, mock_store, mock_write,
                             activity_event, activity_data, coach_feedback):
        mock_retrieve.return_value = activity_data
        mock_invoke.return_value = coach_feedback

        response = handler(activity_event, None)

        assert response["statusCode"] == 200
        assert response["coach_feedback"] == coach_feedback
        mock_store.assert_called_once_with("act123", coach_feedback)

    @patch('processing.coach_generator.retrieve_activity_data', return_value=None)
    def test_handler_missing_activity(self, mock_retrieve, activity_event):
        response = handler(activity_event, None)

        assert response["statusCode"] == 500
        assert "not found" in response["error"]

    @patch('processing.coach_generator._invoke_coach_agent', return_value=None)
    @patch('processing.coach_generator.build_historical_summary', return_value={"weeks": 4, "total_activities": 0})
    @patch('processing.coach_generator.retrieve_activity_data')
    def test_handler_coach_agent_failure(self, mock_retrieve, mock_history, mock_invoke, activity_event, activity_data):
        mock_retrieve.return_value = activity_data

        response = handler(activity_event, None)

        assert response["statusCode"] == 200
        assert response["coach_feedback"] is None

    def test_handler_missing_event_fields(self):
        response = handler({"user_id": "user1"}, None)
        assert response["statusCode"] == 500
        assert "Missing required" in response["error"]

    @patch('processing.coach_generator.write_coaching_observation')
    @patch('processing.coach_generator.store_coach_feedback')
    @patch('processing.coach_generator._invoke_coach_agent')
    @patch('processing.coach_generator.build_historical_summary', return_value={"weeks": 4, "total_activities": 0})
    @patch('processing.coach_generator.retrieve_activity_data')
    @patch.dict(os.environ, {"MEMORY_ID": ""}, clear=False)
    def test_handler_no_memory_id(self, mock_retrieve, mock_history, mock_invoke, mock_store, mock_write,
                                  activity_event, activity_data, coach_feedback):
        mock_retrieve.return_value = activity_data
        mock_invoke.return_value = coach_feedback

        response = handler(activity_event, None)

        assert response["statusCode"] == 200


class TestBuildHistoricalSummary:

    @patch('processing.coach_generator.dynamodb')
    def test_build_historical_summary(self, mock_dynamodb):
        # Use fixed dates in 3 distinct ISO weeks to avoid flakiness
        from datetime import datetime, timezone, timedelta
        # Monday of current week, then -1w, -2w → guaranteed 3 ISO weeks
        monday = datetime(2026, 5, 11, 10, 0, 0, tzinfo=timezone.utc)
        week_dates = [monday, monday - timedelta(weeks=1), monday - timedelta(weeks=2)]
        items = []
        for i in range(10):
            dt = week_dates[i % 3] + timedelta(hours=i)
            items.append({
                "activity_id": f"act_{i}",
                "activity_data_json": json.dumps({
                    "distance": 8000,
                    "moving_time": 2400,
                    "average_speed": 3.33,
                    "start_date_local": dt.isoformat(),
                }),
                "created_at": dt.isoformat(),
            })

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": items}
        mock_dynamodb.Table.return_value = mock_table

        summary = build_historical_summary("user1", "current_act")

        assert summary["total_activities"] == 10
        assert summary["weeks"] == 4
        assert summary["total_distance_km"] == 80.0
        assert summary["weeks_active"] == 3
