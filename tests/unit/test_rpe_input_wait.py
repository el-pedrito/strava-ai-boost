"""RPE athlete input: the InputWait Lambda (docs/design/rpe-athlete-input.md §5).

moto-backed for the conditional writes (their semantics are the point), with
Step Functions and the push helper mocked:
- opens the window once (awaiting, token, deadline, user_id as a string);
- a device reached -> the execution keeps waiting (no SendTaskSuccess);
- push off, nobody reached, notify error -> window closed, token removed,
  execution released at once (D5);
- replay on an already used window -> released at once, row untouched (D3);
- the task token is never logged;
- an InputWait{outcome} metric per outcome.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from athlete_input import input_wait  # noqa: E402

TABLE = "test-activities"
TOKEN = "AQB8AAAAKgAAAAMAAAAAAAAAAc-secret-task-token"  # pragma: allowlist secret


@pytest.fixture
def env(monkeypatch):
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="eu-west-1")
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "activity_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "activity_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setenv("ACTIVITIES_TABLE", TABLE)
        monkeypatch.setattr(input_wait, "_dynamodb", ddb)
        sfn = MagicMock()
        monkeypatch.setattr(input_wait, "_stepfunctions", sfn)
        outcomes = []
        monkeypatch.setattr(input_wait, "_record", outcomes.append)
        notify = MagicMock(return_value=1)
        monkeypatch.setattr(input_wait, "notify_input_request", notify)
        monkeypatch.setenv("PUSH_ENABLED", "true")
        yield {"table": ddb.Table(TABLE), "sfn": sfn, "outcomes": outcomes, "notify": notify}


def _event(**overrides):
    event = {"activity_id": "777", "user_id": 42, "task_token": TOKEN}
    event.update(overrides)
    return event


def _row(env):
    return env["table"].get_item(Key={"activity_id": "777"}).get("Item")


def test_opens_window_and_waits_when_a_device_is_reached(env):
    result = input_wait.handler(_event(), None)

    assert result == {"outcome": "waiting"}
    row = _row(env)
    assert row["athlete_input_state"] == "awaiting"
    assert row["input_task_token"] == TOKEN
    assert row["user_id"] == "42"  # str, like the GSI key
    assert "created_at" not in row  # stays out of UserActivitiesIndex
    deadline = datetime.fromisoformat(row["input_deadline_at"])
    assert timedelta(minutes=59) < deadline - datetime.now(deadline.tzinfo) <= timedelta(hours=1)
    env["sfn"].send_task_success.assert_not_called()
    assert env["outcomes"] == ["waiting"]


def test_notification_carries_the_feedback_url_never_the_token(env):
    input_wait.handler(_event(), None)
    kwargs = env["notify"].call_args.kwargs
    assert kwargs["url"] == "/activities/777/feedback"
    assert kwargs["title"] == "Nouvelle séance"
    assert kwargs["body"] == "Ton ressenti ?"
    assert TOKEN not in repr(kwargs)


def test_nobody_reached_closes_and_releases(env):
    env["notify"].return_value = 0
    result = input_wait.handler(_event(), None)

    assert result == {"outcome": "no_push"}
    row = _row(env)
    assert row["athlete_input_state"] == "closed"
    assert "input_task_token" not in row
    env["sfn"].send_task_success.assert_called_once_with(taskToken=TOKEN, output="{}")
    assert env["outcomes"] == ["no_push"]


def test_push_disabled_closes_and_releases_without_notifying(env, monkeypatch):
    monkeypatch.delenv("PUSH_ENABLED")
    result = input_wait.handler(_event(), None)

    assert result == {"outcome": "no_push"}
    env["notify"].assert_not_called()
    assert _row(env)["athlete_input_state"] == "closed"
    env["sfn"].send_task_success.assert_called_once()


def test_notify_exception_closes_and_releases(env):
    env["notify"].side_effect = RuntimeError("boom")
    result = input_wait.handler(_event(), None)

    assert result == {"outcome": "error"}
    assert _row(env)["athlete_input_state"] == "closed"
    env["sfn"].send_task_success.assert_called_once()
    assert env["outcomes"] == ["error"]


def test_replay_on_used_window_releases_and_keeps_row(env):
    env["table"].put_item(Item={
        "activity_id": "777", "athlete_input_state": "submitted",
        "athlete_input": {"rpe": 7, "summary": "dur", "submitted_at": "2026-10-17T10:00:00+00:00"},
    })
    result = input_wait.handler(_event(), None)

    assert result == {"outcome": "replay"}
    row = _row(env)
    assert row["athlete_input_state"] == "submitted"
    assert "input_task_token" not in row
    env["notify"].assert_not_called()
    env["sfn"].send_task_success.assert_called_once()
    assert env["outcomes"] == ["replay"]


def test_missing_token_records_error_and_relies_on_task_timeout(env):
    result = input_wait.handler(_event(task_token=None), None)
    assert result == {"outcome": "error"}
    env["sfn"].send_task_success.assert_not_called()
    assert _row(env) is None


def test_invalid_activity_id_releases_without_writing(env):
    result = input_wait.handler(_event(activity_id="12; DROP"), None)
    assert result == {"outcome": "error"}
    env["sfn"].send_task_success.assert_called_once()
    assert env["table"].scan()["Items"] == []


def test_dynamodb_failure_fails_open(env, monkeypatch):
    broken = MagicMock()
    broken.Table.return_value.update_item.side_effect = RuntimeError("ddb down")
    monkeypatch.setattr(input_wait, "_dynamodb", broken)
    result = input_wait.handler(_event(), None)
    assert result == {"outcome": "error"}
    env["sfn"].send_task_success.assert_called_once()


def test_release_failure_never_raises(env):
    env["notify"].return_value = 0
    env["sfn"].send_task_success.side_effect = RuntimeError("TaskTimedOut")
    assert input_wait.handler(_event(), None) == {"outcome": "no_push"}


def test_token_never_logged(env, caplog):
    env["notify"].return_value = 0
    env["sfn"].send_task_success.side_effect = RuntimeError(f"bad token {TOKEN}")
    with caplog.at_level(logging.DEBUG):
        input_wait.handler(_event(), None)
        input_wait.handler(_event(), None)  # replay path
        input_wait.handler(_event(activity_id="x"), None)  # invalid path
    # Our own logger only: botocore's DEBUG wire logs are off in Lambda.
    ours = [r.getMessage() for r in caplog.records if r.name.startswith("input_wait")]
    assert ours, "expected input_wait log lines"
    assert all(TOKEN not in line for line in ours)


def test_record_emits_input_wait_metric(capsys):
    input_wait._record("waiting")
    out = capsys.readouterr().out
    assert '"InputWait"' in out
    assert '"outcome":"waiting"' in out.replace(" ", "")
