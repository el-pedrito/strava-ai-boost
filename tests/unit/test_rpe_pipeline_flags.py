"""RPE athlete input: processor flag, updater notification skip, error-handler cleanup.

docs/design/rpe-athlete-input.md §2, §10 and "Jeton et stream DynamoDB":
- the processor always writes a boolean ``wait_for_input`` = module flag AND a
  Strava ``create`` (read from the nested ``webhook_data``); flag off, update,
  late dictation or malformed config -> False;
- ``fetch_user_configuration`` returns the ``athlete_input`` module;
- the "activity enriched" push is skipped when the row went through the input
  window; flag off keeps today's push;
- the Step Functions error handler closes an open window and drops the token,
  without error when there is none.
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

from processing import strava_updater as su  # noqa: E402
from support import stepfunctions_error_handler as eh  # noqa: E402
from webhooks import activity_processor as ap  # noqa: E402

TABLE = "test-activities"


def _config(enabled):
    return {"modules_config": {"athlete_input": {"enabled": enabled}}}


def _body(aspect_type="create", **extra):
    body = {"activity_id": "777", "user_id": "42", "event_time": 42,
            "webhook_data": {"aspect_type": aspect_type, "object_id": 777}}
    body.update(extra)
    return body


# --------------------------------------------------------------------------- processor


def test_wait_when_flag_on_and_create():
    assert ap.should_wait_for_input(_config(True), _body()) is True


def test_no_wait_on_update():
    assert ap.should_wait_for_input(_config(True), _body("update")) is False


def test_no_wait_when_flag_off():
    assert ap.should_wait_for_input(_config(False), _body()) is False


def test_no_wait_without_module():
    assert ap.should_wait_for_input({"modules_config": {}}, _body()) is False


def test_no_wait_on_truthy_non_bool_flag():
    assert ap.should_wait_for_input(_config("true"), _body()) is False


def test_no_wait_on_late_dictation():
    body = _body(late_dictation={"text": "ajout"})
    assert ap.should_wait_for_input(_config(True), body) is False


def test_top_level_aspect_type_is_not_read():
    """The Strava payload is nested: a top-level aspect_type must not count."""
    body = {"activity_id": "777", "aspect_type": "create", "webhook_data": {}}
    assert ap.should_wait_for_input(_config(True), body) is False


def test_workflow_input_always_has_boolean_wait_for_input():
    sfn = MagicMock()
    sfn.start_execution.return_value = {"executionArn": "arn:exec"}
    with patch.object(ap, "stepfunctions", sfn), patch.object(ap, "update_activity_execution_arn"):
        ap.start_step_functions_workflow("777", "42", _body())
        ap.start_step_functions_workflow("777", "42", _body(), wait_for_input=True)
    first = json.loads(sfn.start_execution.call_args_list[0].kwargs["input"])
    second = json.loads(sfn.start_execution.call_args_list[1].kwargs["input"])
    assert first["wait_for_input"] is False
    assert second["wait_for_input"] is True


def test_process_record_passes_wait_for_input():
    record = {"body": json.dumps(_body())}
    with patch.object(ap, "should_skip_processing", return_value=False), \
         patch.object(ap, "fetch_user_configuration", return_value={
             "modules_config": {"enduraw": {"enabled": False}, "athlete_input": {"enabled": True}}}), \
         patch.object(ap, "update_activity_status"), \
         patch.object(ap, "start_step_functions_workflow", return_value="arn:exec") as start:
        ap.process_activity_record(record)
    assert start.call_args.kwargs["wait_for_input"] is True


def test_fetch_user_configuration_returns_athlete_input_module():
    table = MagicMock()
    table.get_item.return_value = {"Item": {"user_id": "42", "modules_config": {
        "athlete_input": {"enabled": True}}}}
    with patch.object(ap.dynamodb, "Table", return_value=table):
        config = ap.fetch_user_configuration("42")
    assert config["modules_config"]["athlete_input"] == {"enabled": True}


def test_fetch_user_configuration_defaults_athlete_input_off():
    table = MagicMock()
    table.get_item.return_value = {"Item": {"user_id": "42", "modules_config": {}}}
    with patch.object(ap.dynamodb, "Table", return_value=table):
        config = ap.fetch_user_configuration("42")
    assert config["modules_config"]["athlete_input"] == {"enabled": False}


def test_fetch_user_configuration_missing_user_defaults_off():
    table = MagicMock()
    table.get_item.return_value = {}
    with patch.object(ap.dynamodb, "Table", return_value=table):
        config = ap.fetch_user_configuration("42")
    assert config["modules_config"]["athlete_input"] == {"enabled": False}


# --------------------------------------------------------------------------- updater


class _Table:
    def __init__(self, item):
        self.item = item
        self.updates = []

    def get_item(self, **_kw):
        return {"Item": self.item}

    def update_item(self, **kw):
        self.updates.append(kw)
        return {}


def test_enriched_push_skipped_after_input_window(monkeypatch):
    monkeypatch.setenv("PUSH_ENABLED", "true")
    table = _Table({"user_id": "42", "enhanced_title": "Seuil", "athlete_input_state": "closed"})
    monkeypatch.setattr(su.dynamodb, "Table", lambda _n: table)
    with patch("shared.push_notify.notify_activity_enriched") as notify:
        su._maybe_push_completed("777", "42")
    notify.assert_not_called()
    assert table.updates == []  # push_sent_at not even claimed


def test_enriched_push_unchanged_without_input_window(monkeypatch):
    monkeypatch.setenv("PUSH_ENABLED", "true")
    table = _Table({"user_id": "42", "enhanced_title": "Seuil"})
    monkeypatch.setattr(su.dynamodb, "Table", lambda _n: table)
    with patch("shared.push_notify.notify_activity_enriched", return_value=True) as notify:
        su._maybe_push_completed("777", "42")
    notify.assert_called_once()


# --------------------------------------------------------------------------- error handler


@pytest.fixture
def ddb_table(monkeypatch):
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="eu-west-1")
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "activity_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "activity_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setattr(eh, "dynamodb", ddb)
        monkeypatch.setattr(eh, "ACTIVITIES_TABLE", TABLE)
        yield ddb.Table(TABLE)


def test_error_handler_closes_awaiting_window(ddb_table):
    ddb_table.put_item(Item={"activity_id": "777", "athlete_input_state": "awaiting", "input_task_token": "tok"})
    assert eh.close_athlete_input_window("777") is True
    row = ddb_table.get_item(Key={"activity_id": "777"})["Item"]
    assert row["athlete_input_state"] == "closed"
    assert "input_task_token" not in row


def test_error_handler_without_window_is_a_no_op(ddb_table):
    ddb_table.put_item(Item={"activity_id": "777", "processing_status": "processing"})
    assert eh.close_athlete_input_window("777") is False
    row = ddb_table.get_item(Key={"activity_id": "777"})["Item"]
    assert "athlete_input_state" not in row


def test_error_handler_missing_row_not_created(ddb_table):
    assert eh.close_athlete_input_window("777") is False
    assert "Item" not in ddb_table.get_item(Key={"activity_id": "777"})


def test_error_handler_closes_on_aborted_execution(ddb_table, monkeypatch):
    ddb_table.put_item(Item={"activity_id": "777", "athlete_input_state": "awaiting", "input_task_token": "tok"})
    monkeypatch.setattr(eh, "get_execution_details", lambda _arn: {})
    monkeypatch.setattr(eh, "send_to_dlq", lambda *a, **k: None)
    event = {"detail": {"executionArn": "arn:exec", "status": "ABORTED", "name": "activity-777-v42"}}

    result = eh.handler(event, None)

    assert result["statusCode"] == 200
    row = ddb_table.get_item(Key={"activity_id": "777"})["Item"]
    assert row["athlete_input_state"] == "closed"
    assert "input_task_token" not in row


def test_error_handler_close_never_raises(monkeypatch):
    broken = MagicMock()
    broken.Table.return_value.update_item.side_effect = RuntimeError("ddb down")
    monkeypatch.setattr(eh, "dynamodb", broken)
    assert eh.close_athlete_input_window("777") is False
