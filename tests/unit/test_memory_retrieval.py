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
    @patch.object(coach_agent, "boto3")
    def test_prefix_namespace_user_filter_and_dynamic_query(self, mock_boto3):
        client = MagicMock()
        client.retrieve_memory_records.return_value = {
            "memoryRecordSummaries": [
                {"content": {"text": "mine"}, "namespaces": ["/strategies/S-1/actors/user42/"]},
                {"content": {"text": "other"}, "namespaces": ["/strategies/S-1/actors/other/"]},
            ]
        }
        mock_boto3.client.return_value = client

        result = coach_agent.retrieve_coaching_observations(
            "mem-1", "user42", {"sport_type": "WeightTraining"}
        )

        assert result == ["mine"]
        kwargs = client.retrieve_memory_records.call_args.kwargs
        assert kwargs["namespace"] == "/strategies/"
        assert "musculation" in kwargs["searchCriteria"]["searchQuery"]

    @patch.object(coach_agent, "boto3")
    def test_caps_at_five(self, mock_boto3):
        client = MagicMock()
        client.retrieve_memory_records.return_value = {
            "memoryRecordSummaries": [
                {"content": {"text": f"obs{i}"}, "namespaces": ["/strategies/S/actors/user42/"]}
                for i in range(8)
            ]
        }
        mock_boto3.client.return_value = client
        assert len(coach_agent.retrieve_coaching_observations("mem-1", "user42")) == 5

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


class TestCoachChatObservationsTool:
    """coach_chat 5th tool: long-term observations retrieval (impl)."""

    def _import_impl(self):
        sys.path.insert(0, os.path.join(REPO_ROOT, 'src', 'coach_chat'))
        import coach_chat_agent
        return coach_chat_agent

    def test_filters_to_user_and_caps_results(self):
        mod = self._import_impl()
        with patch.object(mod, "boto3") as mock_boto3, \
             patch.object(mod, "MEMORY_ID", "mem-1"):
            client = MagicMock()
            client.retrieve_memory_records.return_value = {
                "memoryRecordSummaries": [
                    {"content": {"text": f"obs{i}"}, "namespaces": ["/strategies/S/actors/user42/"]}
                    for i in range(8)
                ] + [
                    {"content": {"text": "other"}, "namespaces": ["/strategies/S/actors/other/"]}
                ]
            }
            mock_boto3.client.return_value = client

            result = mod._get_coach_observations_impl("user42", "progression muscu")

            assert len(result) == 5  # capped
            assert all(r.startswith("obs") for r in result)
            kwargs = client.retrieve_memory_records.call_args.kwargs
            assert kwargs["namespace"] == "/strategies/"
            assert kwargs["searchCriteria"]["searchQuery"] == "progression muscu"

    def test_empty_topic_uses_default_query(self):
        mod = self._import_impl()
        with patch.object(mod, "boto3") as mock_boto3, \
             patch.object(mod, "MEMORY_ID", "mem-1"):
            client = MagicMock()
            client.retrieve_memory_records.return_value = {"memoryRecordSummaries": []}
            mock_boto3.client.return_value = client

            mod._get_coach_observations_impl("user42", "  ")

            q = client.retrieve_memory_records.call_args.kwargs["searchCriteria"]["searchQuery"]
            assert "coaching observations" in q

    def test_no_memory_id_returns_empty(self):
        mod = self._import_impl()
        with patch.object(mod, "MEMORY_ID", ""):
            assert mod._get_coach_observations_impl("user42", "x") == []

    def test_error_returns_empty(self):
        mod = self._import_impl()
        with patch.object(mod, "boto3") as mock_boto3, \
             patch.object(mod, "MEMORY_ID", "mem-1"):
            mock_boto3.client.side_effect = Exception("boom")
            assert mod._get_coach_observations_impl("user42", "x") == []
