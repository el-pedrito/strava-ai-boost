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
        # Real per-week breakdown is now provided (string; may be empty if all
        # activities fall outside the rolling 4-week window relative to today).
        assert "weekly_breakdown" in summary
        assert isinstance(summary["weekly_breakdown"], str)

    @patch('processing.coach_generator.dynamodb')
    def test_string_numeric_fields_do_not_break_summary(self, mock_dynamodb):
        """Regression (live incident 2026-07-18): manual/indoor activities store
        distance/average_speed as strings — the summary crashed on int + str and
        the coach silently lost all historical context."""
        from datetime import datetime, timezone, timedelta
        monday = datetime(2026, 5, 11, 10, 0, 0, tzinfo=timezone.utc)
        items = [
            {
                "activity_id": "act_normal",
                "activity_data_json": json.dumps({
                    "distance": 8000,
                    "moving_time": 2400,
                    "average_speed": 3.33,
                    "average_heartrate": 150,
                    "start_date_local": monday.isoformat(),
                }),
                "created_at": monday.isoformat(),
            },
            {
                # Exact shape of live manual activity 19305772266
                "activity_id": "act_manual",
                "activity_data_json": json.dumps({
                    "distance": "5000.0",
                    "moving_time": 1886,
                    "average_speed": "2.651",
                    "average_heartrate": None,
                    "start_date_local": (monday - timedelta(days=1)).isoformat(),
                }),
                "created_at": (monday - timedelta(days=1)).isoformat(),
            },
        ]
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": items}
        mock_dynamodb.Table.return_value = mock_table

        summary = build_historical_summary("user1", "current_act")

        assert "error" not in summary
        assert summary["total_activities"] == 2
        assert summary["total_distance_km"] == 13.0  # 8km + 5km, string coerced
        # Per-activity detail is grouped by ISO week so no rolling window can be
        # assembled from it; flatten here only to assert the entry itself.
        flat = [
            a
            for entries in summary["recent_activities_by_week"].values()
            for a in entries
        ]
        manual = [a for a in flat if a["distance_km"] == 5.0]
        assert manual and manual[0]["pace"]  # pace computed from string speed

from processing.coach_generator import _compute_coach_metrics, extract_and_store_prs, _build_fitness_trend


class TestComputeCoachMetrics:

    def test_ef_calculation(self):
        laps = [{"average_heartrate": 143, "moving_time": 600}]
        activity_data = {"average_speed": 2.7, "average_heartrate": 143}
        metrics = _compute_coach_metrics(laps, activity_data)
        assert metrics["ef_pace_at_hr"] == "6:10/km @ 143bpm"

    def test_pct_fcmax(self):
        laps = [{"average_heartrate": 143, "moving_time": 600}]
        activity_data = {"average_speed": 3.0, "average_heartrate": 143, "_max_hr_ref": 192}
        metrics = _compute_coach_metrics(laps, activity_data)
        assert metrics["avg_hr_pct_max"] == pytest.approx(74.5, abs=0.1)

    def test_zone3_detection(self):
        laps = [{"average_heartrate": 155, "moving_time": 600}]
        activity_data = {
            "average_speed": 3.0,
            "average_heartrate": 155,
            "_athlete_zones": {
                "heart_rate": {
                    "zones": [
                        {"min": 0, "max": 120},
                        {"min": 120, "max": 150},
                        {"min": 150, "max": 165},
                        {"min": 165, "max": 180},
                        {"min": 180, "max": 220},
                    ]
                }
            },
        }
        metrics = _compute_coach_metrics(laps, activity_data)
        assert metrics["zone3_moderate_pct"] > 0

    def test_no_data(self):
        metrics = _compute_coach_metrics([], {})
        assert metrics == {}


class TestExtractAndStorePrs:

    @patch('processing.coach_generator.dynamodb')
    def test_extracts_pr_rank_1(self, mock_dynamodb):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {"best_efforts_prs": {}}}
        mock_dynamodb.Table.return_value = mock_table

        activity_data = {
            "best_efforts": [
                {"name": "1 mile", "pr_rank": 1, "elapsed_time": 360, "start_date": "2026-05-11T10:00:00Z", "distance": 1609}
            ]
        }
        extract_and_store_prs("user1", activity_data)
        mock_table.update_item.assert_called()

    @patch('processing.coach_generator.dynamodb')
    def test_skips_no_prs(self, mock_dynamodb):
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        extract_and_store_prs("user1", {"best_efforts": []})
        mock_table.update_item.assert_not_called()

    @patch('processing.coach_generator.dynamodb')
    def test_updates_only_if_faster(self, mock_dynamodb):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"best_efforts_prs": {"1 mile": {"elapsed_time": 300, "date": "2026-01-01"}}}
        }
        mock_dynamodb.Table.return_value = mock_table

        # New effort is slower (400s > 300s) → should NOT update
        activity_data = {
            "best_efforts": [
                {"name": "1 mile", "pr_rank": 1, "elapsed_time": 400, "start_date": "2026-05-11T10:00:00Z", "distance": 1609}
            ]
        }
        extract_and_store_prs("user1", activity_data)
        # update_item is not called for best_efforts_prs since existing is faster
        calls = mock_table.update_item.call_args_list
        pr_updates = [c for c in calls if "best_efforts_prs" in str(c)]
        assert len(pr_updates) == 0


class TestBuildFitnessTrend:

    def test_with_icu_data(self):
        activities = [
            {"start_date": "2026-05-01T10:00:00Z", "_intervals_icu": {"fitness": {"ctl": 40.0}}},
            {"start_date": "2026-05-08T10:00:00Z", "_intervals_icu": {"fitness": {"ctl": 45.0}}},
        ]
        result = _build_fitness_trend(activities)
        assert "fitness_trend" in result
        assert result["fitness_trend"]["ctl_delta"] == 5.0

    def test_without_icu(self):
        activities = [
            {"start_date": "2026-05-01T10:00:00Z"},
            {"start_date": "2026-05-08T10:00:00Z"},
        ]
        result = _build_fitness_trend(activities)
        assert result == {}
