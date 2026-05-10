"""Unit tests for assembly_lambda"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from processing.assembly_lambda import handler


@pytest.fixture
def content_result():
    return {
        "statusCode": 200,
        "activity_id": "act123",
        "user_id": "user1",
        "enhanced_content": {
            "title": "Great Run",
            "description": "Nice morning run\n\n💡 Fun fact: running is great!",
        },
    }


@pytest.fixture
def coach_result():
    return {
        "statusCode": 200,
        "activity_id": "act123",
        "coach_feedback": {
            "strava_block": "Good pace improvement this week!",
            "detailed_analysis": {"key_metrics": "5:30/km"},
        },
    }


class TestAssemblyHandler:

    def test_merge_with_coach_and_fun_fact(self, content_result, coach_result):
        event = [content_result, coach_result]
        result = handler(event, None)

        desc = result["enhanced_content"]["description"]
        assert "📊 Coach" in desc
        assert "Good pace improvement" in desc
        # Coach block should be before fun fact
        coach_pos = desc.index("📊 Coach")
        fact_pos = desc.index("💡")
        assert coach_pos < fact_pos

    def test_merge_with_coach_no_fun_fact(self, content_result, coach_result):
        content_result["enhanced_content"]["description"] = "Nice morning run"
        event = [content_result, coach_result]
        result = handler(event, None)

        desc = result["enhanced_content"]["description"]
        assert desc.endswith("Good pace improvement this week!")
        assert "📊 Coach" in desc

    def test_merge_coach_failure(self, content_result):
        coach_result = {"statusCode": 500, "error": "failed"}
        event = [content_result, coach_result]
        result = handler(event, None)

        assert result["enhanced_content"]["description"] == content_result["enhanced_content"]["description"]

    def test_merge_empty_coach_block(self, content_result):
        coach_result = {
            "statusCode": 200,
            "coach_feedback": {"strava_block": "", "detailed_analysis": {}},
        }
        event = [content_result, coach_result]
        result = handler(event, None)

        assert "📊 Coach" not in result["enhanced_content"]["description"]

    def test_merge_preserves_all_content_fields(self, content_result, coach_result):
        event = [content_result, coach_result]
        result = handler(event, None)

        assert result["activity_id"] == "act123"
        assert result["user_id"] == "user1"
        assert result["statusCode"] == 200
        assert result["enhanced_content"]["title"] == "Great Run"
