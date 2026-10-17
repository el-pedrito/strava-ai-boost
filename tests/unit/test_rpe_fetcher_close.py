"""RPE athlete input: the fetcher closes the window and is the sole arbiter (§7).

moto round-trips, because the conditional UpdateItem, ReturnValues ALL_NEW and
ReturnValuesOnConditionCheckFailure ALL_OLD semantics are what is under test:
- awaiting -> closed, token removed, InputWait{outcome=expired};
- submitted -> closed, the input is returned, InputWait{outcome=submitted};
- reprocess (already closed): no error, the RPE kept from ALL_OLD;
- flag off (no window): nothing written, item carries no athlete_input_state;
- the stored item uses the close result, even when get_item still says awaiting;
- athlete_rpe / athlete_summary land in activity_data, never in original_description.
"""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from processing import activity_fetcher  # noqa: E402

TABLE = "test-activities"
INPUT = {"rpe": Decimal(7), "summary": "Jambes lourdes au début", "submitted_at": "2026-10-17T10:00:00+00:00"}


@pytest.fixture
def table(monkeypatch):
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="eu-west-1")
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "activity_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "activity_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setattr(activity_fetcher, "dynamodb", ddb)
        monkeypatch.setattr(activity_fetcher, "ACTIVITIES_TABLE", TABLE)
        yield ddb.Table(TABLE)


@pytest.fixture
def outcomes(monkeypatch):
    seen = []
    monkeypatch.setattr(activity_fetcher, "_record_input_wait", seen.append)
    return seen


def _activity():
    return {
        "id": 777, "description": "Enduraw Report: 4:12/km", "name": "Run", "type": "Run",
        "distance": 10000.0, "moving_time": 3000, "total_elevation_gain": 50.0,
        "start_date": "2026-10-17T07:00:00Z", "athlete": {"id": 42},
    }


def test_awaiting_window_closes_as_expired(table, outcomes):
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "awaiting",
                         "input_task_token": "tok", "input_deadline_at": "2026-10-17T11:00:00+00:00"})

    athlete_input, state = activity_fetcher.close_athlete_input_window("777")

    assert (athlete_input, state) == (None, "closed")
    row = table.get_item(Key={"activity_id": "777"})["Item"]
    assert row["athlete_input_state"] == "closed"
    assert "input_task_token" not in row
    assert outcomes == ["expired"]


def test_submitted_window_closes_and_returns_input(table, outcomes):
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "submitted", "athlete_input": INPUT})

    athlete_input, state = activity_fetcher.close_athlete_input_window("777")

    assert state == "closed"
    assert athlete_input["rpe"] == 7
    assert athlete_input["summary"] == "Jambes lourdes au début"
    assert outcomes == ["submitted"]


def test_reprocess_keeps_rpe_from_all_old(table, outcomes):
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "closed", "athlete_input": INPUT})

    athlete_input, state = activity_fetcher.close_athlete_input_window("777")

    assert state == "closed"
    assert athlete_input["rpe"] == 7  # deserialised from the raw DynamoDB Item
    assert athlete_input["summary"] == "Jambes lourdes au début"
    assert outcomes == []  # not a new wait outcome


def test_flag_off_row_untouched(table, outcomes):
    table.put_item(Item={"activity_id": "777", "processing_status": "processing"})

    assert activity_fetcher.close_athlete_input_window("777") == (None, None)
    row = table.get_item(Key={"activity_id": "777"})["Item"]
    assert "athlete_input_state" not in row
    assert outcomes == []


def test_missing_row_is_not_created(table, outcomes):
    assert activity_fetcher.close_athlete_input_window("777") == (None, None)
    assert "Item" not in table.get_item(Key={"activity_id": "777"})


def test_unexpected_error_fails_open(monkeypatch, outcomes):
    from unittest.mock import MagicMock

    broken = MagicMock()
    broken.Table.return_value.update_item.side_effect = RuntimeError("ddb down")
    monkeypatch.setattr(activity_fetcher, "dynamodb", broken)
    assert activity_fetcher.close_athlete_input_window("777") == (None, None)


def test_apply_athlete_input_sets_both_keys():
    data = {"description": "Enduraw Report: 4:12/km"}
    activity_fetcher.apply_athlete_input(data, INPUT)
    assert data["athlete_rpe"] == 7
    assert isinstance(data["athlete_rpe"], int)
    assert data["athlete_summary"] == "Jambes lourdes au début"
    assert data["description"] == "Enduraw Report: 4:12/km"  # D9: never merged


def test_apply_athlete_input_drops_invalid_values():
    data = {}
    activity_fetcher.apply_athlete_input(data, {"rpe": Decimal(11), "summary": "   "})
    assert data == {}
    activity_fetcher.apply_athlete_input(data, {"rpe": True})
    assert data == {}
    activity_fetcher.apply_athlete_input(data, None)
    assert data == {}


def test_apply_athlete_input_summary_only():
    data = {}
    activity_fetcher.apply_athlete_input(data, {"summary": "Bonne séance"})
    assert data == {"athlete_summary": "Bonne séance"}


def test_store_uses_close_result_even_if_get_item_says_awaiting(table):
    """The non-consistent get_item can lag behind the close: it must not win."""
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "awaiting",
                         "input_task_token": "tok", "input_deadline_at": "2026-10-17T11:00:00+00:00"})

    activity_fetcher.store_activity_data(
        "777", _activity(), None, None, {"user_id": "42"},
        athlete_input=dict(INPUT), athlete_input_state="closed",
    )

    row = table.get_item(Key={"activity_id": "777"})["Item"]
    assert row["athlete_input_state"] == "closed"
    assert row["athlete_input"]["rpe"] == 7
    assert "input_task_token" not in row
    assert "input_deadline_at" not in row


def test_store_without_window_writes_no_input_fields(table):
    activity_fetcher.store_activity_data("777", _activity(), None, None, {"user_id": "42"})
    row = table.get_item(Key={"activity_id": "777"})["Item"]
    assert "athlete_input_state" not in row
    assert "athlete_input" not in row


def test_handler_wires_close_input_and_store(table, outcomes):
    """End to end in the handler: close first, keys in activity_data_json, item closed."""
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "submitted", "athlete_input": INPUT,
                         "input_deadline_at": "2026-10-17T11:00:00+00:00"})
    stubs = {
        "get_access_token": "token",
        "fetch_activity_data": _activity(),
        "fetch_laps_data": None,
        "fetch_activity_zones": None,
        "fetch_athlete_stats": None,
        "fetch_athlete_profile": None,
        "fetch_user_configuration": {"user_id": "42", "modules_config": {}},
        "persist_body_weight_from_strava": None,
        "fetch_intervals_icu_data": None,
    }
    patches = [patch.object(activity_fetcher, name, return_value=value) for name, value in stubs.items()]
    for p in patches:
        p.start()
    try:
        result = activity_fetcher.handler({"activity_id": "777", "user_id": "42"}, None)
    finally:
        for p in patches:
            p.stop()

    assert result["statusCode"] == 200
    row = table.get_item(Key={"activity_id": "777"})["Item"]
    assert row["athlete_input_state"] == "closed"
    assert "input_deadline_at" not in row
    stored = json.loads(row["activity_data_json"])
    assert stored["athlete_rpe"] == 7
    assert stored["athlete_summary"] == "Jambes lourdes au début"
    assert row["original_description"] == "Enduraw Report: 4:12/km"
    assert outcomes == ["submitted"]
