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


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(activity_fetcher, "CLOSE_BACKOFF_SECONDS", (0, 0))


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
    broken.Table.return_value.get_item.side_effect = RuntimeError("ddb down")
    monkeypatch.setattr(activity_fetcher, "dynamodb", broken)
    assert activity_fetcher.close_athlete_input_window("777") == (None, None)


def _throttle_close(monkeypatch, table):
    """Real moto table, but the close UpdateItem is throttled."""
    from unittest.mock import MagicMock

    from botocore.exceptions import ClientError

    wrapped = MagicMock(wraps=table)
    wrapped.update_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow down"}},
        "UpdateItem",
    )
    resource = MagicMock()
    resource.Table.return_value = wrapped
    monkeypatch.setattr(activity_fetcher, "dynamodb", resource)
    return wrapped


def test_throttled_close_keeps_submitted_input(table, outcomes, monkeypatch):
    """A non-conditional error must not drop the RPE: consistent read fallback."""
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "submitted", "athlete_input": INPUT})
    wrapped = _throttle_close(monkeypatch, table)

    athlete_input, state = activity_fetcher.close_athlete_input_window("777")

    assert state == "closed"
    assert athlete_input["rpe"] == 7
    assert athlete_input["summary"] == "Jambes lourdes au début"
    assert wrapped.get_item.call_args.kwargs["ConsistentRead"] is True


def test_throttled_close_on_awaiting_window_still_reports_closed(table, outcomes, monkeypatch):
    """No input yet, but a window existed: closed, so no second "enriched" push."""
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "awaiting", "input_task_token": "tok"})
    _throttle_close(monkeypatch, table)

    assert activity_fetcher.close_athlete_input_window("777") == (None, "closed")


def test_throttled_close_without_window_stays_flag_off(table, outcomes, monkeypatch):
    table.put_item(Item={"activity_id": "777", "processing_status": "processing"})
    _throttle_close(monkeypatch, table)

    assert activity_fetcher.close_athlete_input_window("777") == (None, None)


def test_throttled_close_then_store_keeps_input_on_the_row(table, outcomes, monkeypatch):
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "submitted", "athlete_input": INPUT,
                         "input_task_token": "tok"})
    _throttle_close(monkeypatch, table)
    athlete_input, state = activity_fetcher.close_athlete_input_window("777")
    monkeypatch.setattr(activity_fetcher, "dynamodb", boto3.resource("dynamodb", region_name="eu-west-1"))

    activity_fetcher.store_activity_data(
        "777", _activity(), None, None, {"user_id": "42"},
        athlete_input=athlete_input, athlete_input_state=state,
    )

    row = table.get_item(Key={"activity_id": "777"})["Item"]
    assert row["athlete_input_state"] == "closed"
    assert row["athlete_input"]["rpe"] == 7
    assert "input_task_token" not in row


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


_THROTTLE = {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow down"}}


def _flaky_close(monkeypatch, table, failures):
    """Real moto table; the first ``failures`` close UpdateItems are throttled."""
    from unittest.mock import MagicMock

    from botocore.exceptions import ClientError

    calls = {"n": 0}
    real_update = table.update_item

    def update_item(**kwargs):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise ClientError(_THROTTLE, "UpdateItem")
        return real_update(**kwargs)

    wrapped = MagicMock(wraps=table)
    wrapped.update_item.side_effect = update_item
    resource = MagicMock()
    resource.Table.return_value = wrapped
    monkeypatch.setattr(activity_fetcher, "dynamodb", resource)
    return wrapped, calls


def test_close_is_retried_before_the_fallback(table, outcomes, monkeypatch):
    """Two throttles then success: a real conditional close, no guarded store needed."""
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "submitted", "athlete_input": INPUT,
                         "input_task_token": "tok"})
    wrapped, calls = _flaky_close(monkeypatch, table, failures=2)

    athlete_input, state, guard = activity_fetcher._close_window("777")

    assert calls["n"] == 3
    assert (state, guard) == ("closed", None)
    assert athlete_input["rpe"] == 7
    wrapped.get_item.assert_not_called()
    assert outcomes == ["submitted"]
    assert "input_task_token" not in table.get_item(Key={"activity_id": "777"})["Item"]


def test_close_retries_are_bounded(table, outcomes, monkeypatch):
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "awaiting", "input_task_token": "tok"})
    _wrapped, calls = _flaky_close(monkeypatch, table, failures=99)
    sleeps = []
    monkeypatch.setattr(activity_fetcher.time, "sleep", sleeps.append)

    athlete_input, state, guard = activity_fetcher._close_window("777")

    assert calls["n"] == activity_fetcher.CLOSE_ATTEMPTS == 3
    assert len(sleeps) == 2
    assert (athlete_input, state, guard) == (None, "closed", {"observed_state": "awaiting"})


def test_fallback_without_window_guards_on_absent_state(table, outcomes, monkeypatch):
    table.put_item(Item={"activity_id": "777", "processing_status": "processing"})
    _flaky_close(monkeypatch, table, failures=99)

    assert activity_fetcher._close_window("777") == (None, None, {"observed_state": None})


def test_guarded_store_refuses_a_changed_state(table):
    """observed=awaiting but a submit made it submitted: no overwrite."""
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "submitted", "athlete_input": INPUT})

    with pytest.raises(activity_fetcher.InputStateChanged):
        activity_fetcher.store_activity_data(
            "777", _activity(), None, None, {"user_id": "42"},
            athlete_input=None, athlete_input_state="closed", input_guard={"observed_state": "awaiting"},
        )

    row = table.get_item(Key={"activity_id": "777"})["Item"]
    assert row["athlete_input_state"] == "submitted"
    assert row["athlete_input"]["rpe"] == 7


def test_guarded_store_on_absent_state_refuses_a_window(table):
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "awaiting", "input_task_token": "tok"})

    with pytest.raises(activity_fetcher.InputStateChanged):
        activity_fetcher.store_activity_data(
            "777", _activity(), None, None, {"user_id": "42"}, input_guard={"observed_state": None},
        )
    assert table.get_item(Key={"activity_id": "777"})["Item"]["input_task_token"] == "tok"


def test_guarded_store_writes_when_state_unchanged(table):
    table.put_item(Item={"activity_id": "777", "athlete_input_state": "awaiting", "input_task_token": "tok"})

    activity_fetcher.store_activity_data(
        "777", _activity(), None, None, {"user_id": "42"},
        athlete_input=None, athlete_input_state="closed", input_guard={"observed_state": "awaiting"},
    )

    row = table.get_item(Key={"activity_id": "777"})["Item"]
    assert row["athlete_input_state"] == "closed"
    assert "input_task_token" not in row


def _run_handler():
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
        return activity_fetcher.handler({"activity_id": "777", "user_id": "42"}, None)
    finally:
        for p in patches:
            p.stop()


def test_submit_between_fallback_read_and_store_is_kept(table, outcomes, monkeypatch):
    """The exact race: close throttled 3x, consistent read sees awaiting, the real
    submit API answers 202 before the store, then the store must not erase it."""
    import athlete_input.input_submit as input_submit
    from unittest.mock import MagicMock

    table.put_item(Item={"activity_id": "777", "user_id": "42", "athlete_input_state": "awaiting",
                         "input_task_token": "tok", "input_deadline_at": "2099-01-01T00:00:00+00:00"})
    monkeypatch.setenv("ACTIVITIES_TABLE", TABLE)
    monkeypatch.setattr(input_submit, "dynamodb", boto3.resource("dynamodb", region_name="eu-west-1"))
    monkeypatch.setattr(input_submit, "stepfunctions", MagicMock())
    monkeypatch.setattr(input_submit, "_record_outcome", lambda _o: None)
    wrapped, _calls = _flaky_close(monkeypatch, table, failures=3)
    real_get = table.get_item
    submits = []

    def get_item(**kwargs):
        result = real_get(**kwargs)
        if kwargs.get("ConsistentRead") and not submits:
            submits.append(input_submit.handler({
                "httpMethod": "POST",
                "pathParameters": {"activityId": "777"},
                "requestContext": {"authorizer": {"claims": {"custom:strava_id": "42"}}, "requestId": "r"},
                "body": json.dumps({"rpe": 8, "summary": "Dur sur la fin"}),
            }, None))
        return result

    wrapped.get_item.side_effect = get_item

    result = _run_handler()

    assert result["statusCode"] == 200
    assert submits[0]["statusCode"] == 202
    row = table.get_item(Key={"activity_id": "777"})["Item"]
    assert row["athlete_input_state"] == "closed"
    assert row["athlete_input"]["rpe"] == 8
    assert "input_task_token" not in row
    stored = json.loads(row["activity_data_json"])
    assert stored["athlete_rpe"] == 8
    assert stored["athlete_summary"] == "Dur sur la fin"
    assert outcomes == ["submitted"]  # the second, successful close


def test_fallback_store_without_race_closes_the_row(table, outcomes, monkeypatch):
    table.put_item(Item={"activity_id": "777", "user_id": "42", "athlete_input_state": "awaiting",
                         "input_task_token": "tok"})
    _flaky_close(monkeypatch, table, failures=99)

    assert _run_handler()["statusCode"] == 200

    row = table.get_item(Key={"activity_id": "777"})["Item"]
    assert row["athlete_input_state"] == "closed"
    assert "input_task_token" not in row
    assert "athlete_rpe" not in json.loads(row["activity_data_json"])
