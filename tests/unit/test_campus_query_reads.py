"""Unit tests for the Scan -> Query conversions on the Campus Coach sessions table.

The coaching-sessions table has ``session_date`` as its partition key, with the
values written by the sync as ``week-YYYY-Www`` plus one special
``athlete-context`` partition. Reads that target a single, known partition are
Queries, not Scans: a Query reads exactly one partition instead of scanning the
whole table and filtering, which is cheaper and cannot pick up a stale row from
another week.

These tests lock in the conversion in
``content_generator._get_campus_context`` (athlete-context -> Query) and assert
that the current-week cycle-theme read, which is keyed on the ``is_current_week``
flag (a plain attribute, not the partition key), stays a Scan.
"""

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

os.environ.setdefault("AWS_REGION", "eu-west-1")
os.environ.setdefault("COACHING_SESSIONS_TABLE", "test-coaching-sessions")
os.environ.setdefault("ACTIVITIES_TABLE", "test-activities")
os.environ.setdefault("USER_CONFIG_TABLE", "test-user-config")

from processing.content_generator import _get_campus_context


ATHLETE_CONTEXT_ROW = {
    "session_date": "athlete-context",
    "session_id": "ctx",
    "goal": {"type": "semi", "trainings_done": 3, "trainings_total": 12},
    "assiduity": "high",
}

CURRENT_WEEK_ROW = {
    "session_date": "week-2026-W32",
    "session_id": "1_0",
    "is_current_week": True,
    "cycle_theme": "Force_A10",
    "cycle_description": "Bloc force",
}


class TestGetCampusContextQuery:
    """content_generator._get_campus_context: athlete-context via Query."""

    def _mock_dynamo(self, query_items, scan_items):
        table = MagicMock()
        table.query.return_value = {"Items": list(query_items)}
        table.scan.return_value = {"Items": list(scan_items)}
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        return dynamo, table

    def test_athlete_context_read_uses_query_on_partition_key(self):
        dynamo, table = self._mock_dynamo([ATHLETE_CONTEXT_ROW], [CURRENT_WEEK_ROW])

        with patch("processing.content_generator.dynamodb", dynamo):
            result = _get_campus_context()

        # athlete-context is read with a Query keyed on the partition key,
        # never a Scan filtered on session_date.
        table.query.assert_called_once_with(
            KeyConditionExpression="session_date = :sd",
            ExpressionAttributeValues={":sd": "athlete-context"},
        )
        # The only Scan left is the current-week cycle-theme lookup (flag-based).
        table.scan.assert_called_once_with(
            FilterExpression="is_current_week = :cw",
            ExpressionAttributeValues={":cw": True},
            Limit=1,
        )

        assert result is not None
        assert result["goal"] == {"type": "semi", "trainings_done": 3, "trainings_total": 12}
        assert result["assiduity"] == "high"
        assert result["cycle_theme"] == "Force_A10"
        assert result["cycle_description"] == "Bloc force"

    def test_returns_none_when_athlete_context_partition_empty(self):
        dynamo, table = self._mock_dynamo([], [CURRENT_WEEK_ROW])

        with patch("processing.content_generator.dynamodb", dynamo):
            result = _get_campus_context()

        # Empty athlete-context partition -> None, and the current-week Scan is
        # never reached (same early-return behaviour as before the conversion).
        assert result is None
        table.query.assert_called_once()
        table.scan.assert_not_called()

    def test_missing_current_week_theme_degrades_to_empty_strings(self):
        dynamo, table = self._mock_dynamo([ATHLETE_CONTEXT_ROW], [])

        with patch("processing.content_generator.dynamodb", dynamo):
            result = _get_campus_context()

        assert result is not None
        assert result["cycle_theme"] == ""
        assert result["cycle_description"] == ""

    def test_query_failure_degrades_to_none(self):
        table = MagicMock()
        table.query.side_effect = Exception("AccessDenied")
        dynamo = MagicMock()
        dynamo.Table.return_value = table

        with patch("processing.content_generator.dynamodb", dynamo):
            result = _get_campus_context()

        assert result is None
