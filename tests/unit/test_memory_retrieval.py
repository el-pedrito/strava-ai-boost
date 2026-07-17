"""Unit tests for the AgentCore Memory retrieval fixes (A4).

See docs/design/memory-improvements.md.
"""

import json
import os
import sys

import pytest
from unittest.mock import patch, MagicMock

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.join(REPO_ROOT, 'lambda_functions'))
sys.path.insert(0, os.path.join(REPO_ROOT, 'src', 'agents'))

import coach_agent  # noqa: E402  (src/agents, uses embedded_prompts sibling import)
from support.weekly_audio_recap import _retrieve_memory_observations  # noqa: E402


class TestBuildObservationQuery:
    """Session-type-aware semantic query construction (pure)."""

    def test_no_activity_returns_base(self):
        q = coach_agent._build_observation_query(None)
        assert "coaching observations" in q

    def test_weight_training(self):
        q = coach_agent._build_observation_query({"sport_type": "WeightTraining"})
        assert "musculation" in q and "charges" in q

    def test_run_intervals(self):
        q = coach_agent._build_observation_query(
            {"sport_type": "Run", "workout_classification": {"type": "intervals"}}
        )
        assert "fractionné" in q

    def test_run_long(self):
        q = coach_agent._build_observation_query(
            {"sport_type": "Run", "workout_classification": {"type": "long_run"}}
        )
        assert "sortie longue" in q

    def test_run_default(self):
        q = coach_agent._build_observation_query({"sport_type": "Run"})
        assert "course à pied" in q

    def test_ride(self):
        q = coach_agent._build_observation_query({"type": "Ride"})
        assert "vélo" in q


class TestRetrieveCoachingObservations:
    def setup_method(self):
        coach_agent._SEMANTIC_STRATEGY_ID = None  # reset the discovery cache

    @patch.object(coach_agent, "boto3")
    def test_uses_discovered_strategy_namespace(self, mock_boto3):
        control = MagicMock()
        control.get_memory.return_value = {
            "memory": {"strategies": [{"type": "SEMANTIC", "strategyId": "Comp-abc123"}]}
        }
        data_plane = MagicMock()
        data_plane.retrieve_memory_records.return_value = {
            "memoryRecordSummaries": [{"content": {"text": "obs1"}}]
        }
        mock_boto3.client.side_effect = lambda svc, **kw: (
            control if svc == "bedrock-agentcore-control" else data_plane
        )

        result = coach_agent.retrieve_coaching_observations(
            "mem-1", "user42", {"sport_type": "WeightTraining"}
        )

        assert result == ["obs1"]
        kwargs = data_plane.retrieve_memory_records.call_args.kwargs
        assert kwargs["namespace"] == "/strategies/Comp-abc123/actors/user42/"
        assert "musculation" in kwargs["searchCriteria"]["searchQuery"]

    @patch.object(coach_agent, "boto3")
    def test_falls_back_to_prefix_when_discovery_fails(self, mock_boto3):
        control = MagicMock()
        control.get_memory.side_effect = Exception("denied")
        data_plane = MagicMock()
        data_plane.retrieve_memory_records.return_value = {"memoryRecordSummaries": []}
        mock_boto3.client.side_effect = lambda svc, **kw: (
            control if svc == "bedrock-agentcore-control" else data_plane
        )

        result = coach_agent.retrieve_coaching_observations("mem-1", "user42")

        assert result == []
        assert data_plane.retrieve_memory_records.call_args.kwargs["namespace"] == "/strategies/"

    @patch.object(coach_agent, "boto3")
    def test_returns_empty_on_error(self, mock_boto3):
        mock_boto3.client.side_effect = Exception("boom")
        assert coach_agent.retrieve_coaching_observations("mem-1", "u") == []


class TestWeeklyRecapMemoryRead:
    @patch("support.weekly_audio_recap.boto3")
    @patch("support.weekly_audio_recap.MEMORY_ID", "mem-1")
    def test_filters_records_to_the_user(self, mock_boto3):
        client = MagicMock()
        client.retrieve_memory_records.return_value = {
            "memoryRecordSummaries": [
                {"content": {"text": "mine"}, "namespaces": ["/strategies/S-1/actors/user42/"]},
                {"content": {"text": "other"}, "namespaces": ["/strategies/S-1/actors/other/"]},
            ]
        }
        mock_boto3.client.return_value = client

        result = _retrieve_memory_observations("user42")

        assert "mine" in result and "other" not in result
        kwargs = client.retrieve_memory_records.call_args.kwargs
        assert kwargs["namespace"] == "/strategies/"
        assert "searchQuery" in kwargs["searchCriteria"]

    @patch("support.weekly_audio_recap.boto3")
    @patch("support.weekly_audio_recap.MEMORY_ID", "mem-1")
    def test_returns_empty_string_on_error(self, mock_boto3):
        mock_boto3.client.side_effect = Exception("boom")
        assert _retrieve_memory_observations("user42") == ""
