"""RPE athlete input: behaviour across slices, on one moto table.

docs/design/rpe-athlete-input.md §7 claims that DynamoDB serialises the submit
API and the fetcher close: submit first -> the fetcher reads the RPE; close
first -> the API answers 409. Each half is tested on its own elsewhere; here both
real handlers run against the same table, in both orders.

The flag-off chain is driven end to end as well: the processor writes
``wait_for_input=False``, the fetcher leaves no input field on the row, and the
updater sends today's "activity enriched" push.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))
os.environ.setdefault("STEP_FUNCTIONS_ARN", "arn:aws:states:eu-west-1:123456789012:stateMachine:StravaAIBoost-ActivityProcessing")
os.environ.setdefault("STRAVA_OAUTH_SECRET", "test-oauth-secret")

from athlete_input import input_submit  # noqa: E402
from processing import activity_fetcher  # noqa: E402
from processing import strava_updater  # noqa: E402
from webhooks import activity_processor  # noqa: E402

TABLE = "test-activities"
USER_ID = "42"
ACTIVITY_ID = "777"
TOKEN = "AQB8AAAAKgAAAAMAAAAAAAAAAc-cross-slice-token"  # pragma: allowlist secret


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
        monkeypatch.setenv("ACTIVITIES_TABLE", TABLE)
        for module in (input_submit, activity_fetcher, strava_updater, activity_processor):
            monkeypatch.setattr(module, "dynamodb", ddb)
        monkeypatch.setattr(activity_fetcher, "ACTIVITIES_TABLE", TABLE)
        monkeypatch.setattr(strava_updater, "ACTIVITIES_TABLE", TABLE)
        monkeypatch.setattr(activity_fetcher, "_record_input_wait", lambda _o: None)
        monkeypatch.setattr(input_submit, "_record_outcome", lambda _o: None)
        monkeypatch.setattr(input_submit, "stepfunctions", MagicMock())
        yield ddb.Table(TABLE)


def _open_window(table):
    """The row as input_wait leaves it once a device was reached."""
    table.put_item(Item={
        "activity_id": ACTIVITY_ID,
        "user_id": USER_ID,
        "athlete_input_state": "awaiting",
        "input_task_token": TOKEN,
        "input_deadline_at": "2099-01-01T00:00:00+00:00",
    })


def _submit(rpe=7, summary="Jambes lourdes"):
    return input_submit.handler({
        "httpMethod": "POST",
        "pathParameters": {"activityId": ACTIVITY_ID},
        "requestContext": {"authorizer": {"claims": {"custom:strava_id": USER_ID}}, "requestId": "r"},
        "body": json.dumps({"rpe": rpe, "summary": summary}),
    }, None)


def test_submit_then_close_the_fetcher_reads_the_rpe(table):
    _open_window(table)

    assert _submit()["statusCode"] == 202
    input_submit.stepfunctions.send_task_success.assert_called_once_with(taskToken=TOKEN, output="{}")

    athlete_input, state = activity_fetcher.close_athlete_input_window(ACTIVITY_ID)

    assert state == "closed"
    assert athlete_input["rpe"] == 7
    assert athlete_input["summary"] == "Jambes lourdes"
    row = table.get_item(Key={"activity_id": ACTIVITY_ID})["Item"]
    assert row["athlete_input_state"] == "closed"
    assert "input_task_token" not in row


def test_close_then_submit_the_api_answers_409(table):
    _open_window(table)

    athlete_input, state = activity_fetcher.close_athlete_input_window(ACTIVITY_ID)
    result = _submit()

    assert (athlete_input, state) == (None, "closed")
    assert result["statusCode"] == 409
    input_submit.stepfunctions.send_task_success.assert_not_called()
    row = table.get_item(Key={"activity_id": ACTIVITY_ID})["Item"]
    assert row["athlete_input_state"] == "closed"
    assert "athlete_input" not in row


def _strava_activity():
    return {
        "id": int(ACTIVITY_ID), "description": "Bonne sortie", "name": "Run", "type": "Run",
        "distance": 10000.0, "moving_time": 3000, "total_elevation_gain": 50.0,
        "start_date": "2026-10-17T07:00:00Z", "athlete": {"id": int(USER_ID)},
    }


def test_flag_off_chain_keeps_todays_path_and_enriched_push(table, monkeypatch):
    # 1. Processor, module off: the execution input carries wait_for_input=False.
    sfn = MagicMock()
    sfn.start_execution.return_value = {"executionArn": "arn:exec"}
    body = {"activity_id": ACTIVITY_ID, "user_id": USER_ID, "event_time": 42,
            "webhook_data": {"aspect_type": "create", "object_id": int(ACTIVITY_ID)}}
    with patch.object(activity_processor, "stepfunctions", sfn), \
         patch.object(activity_processor, "update_activity_execution_arn"), \
         patch.object(activity_processor, "should_skip_processing", return_value=False), \
         patch.object(activity_processor, "fetch_user_configuration", return_value={
             "modules_config": {"enduraw": {"enabled": False}, "athlete_input": {"enabled": False}}}):
        activity_processor.process_activity_record({"body": json.dumps(body)})
    execution_input = json.loads(sfn.start_execution.call_args.kwargs["input"])
    assert execution_input["wait_for_input"] is False

    # 2. Fetcher (the Choice skipped the wait): no input field on the stored row.
    stubs = {
        "get_access_token": "token",
        "fetch_activity_data": _strava_activity(),
        "fetch_laps_data": None,
        "fetch_activity_zones": None,
        "fetch_athlete_stats": None,
        "fetch_athlete_profile": None,
        "fetch_user_configuration": {"user_id": USER_ID, "modules_config": {}},
        "persist_body_weight_from_strava": None,
        "fetch_intervals_icu_data": None,
    }
    patches = [patch.object(activity_fetcher, name, return_value=value) for name, value in stubs.items()]
    for p in patches:
        p.start()
    try:
        result = activity_fetcher.handler(
            {"activity_id": execution_input["activity_id"], "user_id": execution_input["user_id"]}, None
        )
    finally:
        for p in patches:
            p.stop()
    assert result["statusCode"] == 200
    row = table.get_item(Key={"activity_id": ACTIVITY_ID})["Item"]
    for field in ("athlete_input_state", "athlete_input", "input_task_token", "input_deadline_at"):
        assert field not in row
    stored = json.loads(row["activity_data_json"])
    assert "athlete_rpe" not in stored
    assert "athlete_summary" not in stored

    # 3. Updater: today's "activity enriched" push is sent, once.
    table.update_item(
        Key={"activity_id": ACTIVITY_ID},
        UpdateExpression="SET enhanced_title = :t",
        ExpressionAttributeValues={":t": "Sortie enrichie"},
    )
    monkeypatch.setenv("PUSH_ENABLED", "true")
    with patch("shared.push_notify.notify_activity_enriched", return_value=True) as notify:
        strava_updater._maybe_push_completed(ACTIVITY_ID, USER_ID)
        strava_updater._maybe_push_completed(ACTIVITY_ID, USER_ID)
    notify.assert_called_once()
    assert notify.call_args.kwargs["body"] == "Sortie enrichie"
