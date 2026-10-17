"""A0: late-dictation fields survive the fetcher's full put_item reprocess.

``store_activity_data`` deliberately rewrites the whole item on every reprocess
(the correct retreatment semantics: all per-run output is cleared). Three
late-dictation attributes must survive that rewrite, and only those three.
DynamoDB semantics matter here (put_item overwrites the item), so these use moto
for a real round-trip rather than a mock.
"""
import os
import sys

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from processing import activity_fetcher


TABLE = "test-activities"


@pytest.fixture
def ddb_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="eu-west-1")
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "activity_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "activity_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # Point the module's resource at moto.
        old = activity_fetcher.dynamodb
        activity_fetcher.dynamodb = ddb
        try:
            yield ddb.Table(TABLE)
        finally:
            activity_fetcher.dynamodb = old


def _activity(desc="Footing tranquille", name="Run"):
    return {
        "id": 111,
        "description": desc,
        "name": name,
        "type": "Run",
        "distance": 10000.0,
        "moving_time": 3000,
        "total_elevation_gain": 50.0,
        "start_date": "2026-01-01T07:00:00Z",
        "start_date_local": "2026-01-01T08:00:00",
        "athlete": {"id": 42},
    }


def test_late_dictation_fields_carried_across_reprocess(ddb_table):
    ddb_table.put_item(Item={
        "activity_id": "111",
        "late_dictation_text": "ajout dicté après coup",
        "late_dictation_at": "2026-01-01T09:00:00Z",
        "late_merge_count": 2,
        # per-run fields that MUST be cleared by the full put_item
        "enhanced_description": "old generated text",
        "coach_feedback": {"x": 1},
        "push_sent_at": "2026-01-01T08:30:00Z",
    })

    activity_fetcher.store_activity_data(
        "111", _activity(), None, None, {"user_id": "42"}, None, None
    )

    item = ddb_table.get_item(Key={"activity_id": "111"})["Item"]
    assert item["late_dictation_text"] == "ajout dicté après coup"
    assert item["late_dictation_at"] == "2026-01-01T09:00:00Z"
    assert item["late_merge_count"] == 2


def test_reprocess_clears_other_per_run_fields(ddb_table):
    ddb_table.put_item(Item={
        "activity_id": "111",
        "late_merge_count": 1,
        "enhanced_description": "old generated text",
        "coach_feedback": {"x": 1},
        "push_sent_at": "2026-01-01T08:30:00Z",
    })

    activity_fetcher.store_activity_data(
        "111", _activity(), None, None, {"user_id": "42"}, None, None
    )

    item = ddb_table.get_item(Key={"activity_id": "111"})["Item"]
    assert "enhanced_description" not in item
    assert "coach_feedback" not in item
    assert "push_sent_at" not in item


def test_no_prior_late_dictation_means_no_fields(ddb_table):
    ddb_table.put_item(Item={"activity_id": "111", "created_at": "old"})

    activity_fetcher.store_activity_data(
        "111", _activity(), None, None, {"user_id": "42"}, None, None
    )

    item = ddb_table.get_item(Key={"activity_id": "111"})["Item"]
    assert "late_dictation_text" not in item
    assert "late_merge_count" not in item


def test_get_item_failure_is_non_fatal_and_metered(ddb_table, monkeypatch):
    """A read failure must not crash the store; it warns + emits a metric and
    stores without carrying (current behaviour)."""
    from unittest.mock import MagicMock, patch

    broken = MagicMock()
    broken.get_item.side_effect = RuntimeError("ddb down")
    # put_item still works on the broken proxy (we only assert it is attempted).

    captured = {}

    def _fake_table(name):
        return broken

    with patch.object(activity_fetcher.dynamodb, "Table", side_effect=_fake_table), \
         patch.object(activity_fetcher.metrics, "add_metric",
                      side_effect=lambda **kw: captured.setdefault("metric", kw)):
        activity_fetcher.store_activity_data(
            "111", _activity(), None, None, {"user_id": "42"}, None, None
        )

    assert broken.get_item.called
    assert broken.put_item.called
    assert captured["metric"]["name"] == "LateDictationCarryFailed"
