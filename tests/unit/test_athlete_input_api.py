"""Unit tests for the Cognito-authenticated athlete feedback API."""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from athlete_input import input_status, input_submit  # noqa: E402


USER_ID = "424242"
ACTIVITY_ID = "123456789"
TASK_TOKEN = "opaque-task-token"


def _event(method="GET", body=None, activity_id=ACTIVITY_ID, user_id=USER_ID):
    claims = {} if user_id is None else {"custom:strava_id": user_id}
    event = {
        "httpMethod": method,
        "pathParameters": {"activityId": activity_id},
        "requestContext": {"authorizer": {"claims": claims}, "requestId": "request-1"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _client_error(code, operation):
    return ClientError({"Error": {"Code": code, "Message": "failure"}}, operation)


class TestInputStatus:
    def test_rejects_non_ascii_activity_id_before_read(self):
        with patch.object(input_status.dynamodb, "Table") as table:
            result = input_status.handler(_event(activity_id="１２３"), None)

        assert result["statusCode"] == 400
        table.assert_not_called()

    def test_missing_identity_is_forbidden(self):
        with patch.object(input_status.dynamodb, "Table") as table:
            result = input_status.handler(_event(user_id=None), None)

        assert result["statusCode"] == 403
        table.assert_not_called()

    def test_other_owner_is_forbidden(self):
        table = MagicMock()
        table.get_item.return_value = {"Item": {"user_id": "someone-else"}}
        with patch.object(input_status.dynamodb, "Table", return_value=table):
            result = input_status.handler(_event(), None)

        assert result["statusCode"] == 403
        assert TASK_TOKEN not in result["body"]

    def test_existing_activity_without_window_returns_none(self):
        table = MagicMock()
        table.get_item.return_value = {"Item": {"user_id": USER_ID}}
        with patch.object(input_status.dynamodb, "Table", return_value=table):
            result = input_status.handler(_event(), None)

        assert result["statusCode"] == 200
        assert json.loads(result["body"])["state"] == "none"
        table.get_item.assert_called_once_with(
            Key={"activity_id": ACTIVITY_ID}, ConsistentRead=True
        )

    def test_row_without_owner_yet_returns_none(self):
        """Processor wrote the row, input_wait/fetcher not yet: none, not 403."""
        table = MagicMock()
        table.get_item.return_value = {"Item": {"activity_id": ACTIVITY_ID, "processing_status": "processing"}}
        with patch.object(input_status.dynamodb, "Table", return_value=table):
            result = input_status.handler(_event(), None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["state"] == "none"
        assert "deadline_at" not in body

    def test_missing_row_returns_none(self):
        table = MagicMock()
        table.get_item.return_value = {}
        with patch.object(input_status.dynamodb, "Table", return_value=table):
            result = input_status.handler(_event(), None)

        assert result["statusCode"] == 200
        assert json.loads(result["body"])["state"] == "none"

    def test_table_name_is_read_at_call_time(self, monkeypatch):
        monkeypatch.setenv("ACTIVITIES_TABLE", "late-bound-activities")
        with patch.object(input_status.dynamodb, "Table") as table:
            table.return_value.get_item.return_value = {}
            input_status.handler(_event(), None)
        table.assert_called_once_with("late-bound-activities")

    def test_open_window_returns_deadline_without_token(self):
        deadline = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
        table = MagicMock()
        table.get_item.return_value = {"Item": {
            "user_id": USER_ID,
            "athlete_input_state": "awaiting",
            "input_deadline_at": deadline,
            "input_task_token": TASK_TOKEN,
        }}
        with patch.object(input_status.dynamodb, "Table", return_value=table):
            result = input_status.handler(_event(), None)

        body = json.loads(result["body"])
        assert body["state"] == "awaiting"
        assert body["deadline_at"] == deadline
        assert TASK_TOKEN not in result["body"]

    def test_expired_awaiting_window_returns_closed(self):
        deadline = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        table = MagicMock()
        table.get_item.return_value = {"Item": {
            "user_id": USER_ID,
            "athlete_input_state": "awaiting",
            "input_deadline_at": deadline,
        }}
        with patch.object(input_status.dynamodb, "Table", return_value=table):
            result = input_status.handler(_event(), None)

        body = json.loads(result["body"])
        assert body["state"] == "closed"
        assert "deadline_at" not in body

    def test_malformed_awaiting_deadline_fails_closed(self):
        table = MagicMock()
        table.get_item.return_value = {"Item": {
            "user_id": USER_ID,
            "athlete_input_state": "awaiting",
            "input_deadline_at": "not-a-date",
        }}
        with patch.object(input_status.dynamodb, "Table", return_value=table):
            result = input_status.handler(_event(), None)

        assert json.loads(result["body"])["state"] == "closed"

    def test_terminal_states_are_returned_without_deadline_or_token(self):
        for state in ("submitted", "closed"):
            table = MagicMock()
            table.get_item.return_value = {"Item": {
                "user_id": USER_ID,
                "athlete_input_state": state,
                "input_deadline_at": "2099-01-01T00:00:00+00:00",
                "input_task_token": TASK_TOKEN,
            }}
            with patch.object(input_status.dynamodb, "Table", return_value=table):
                result = input_status.handler(_event(), None)

            body = json.loads(result["body"])
            assert body["state"] == state
            assert "deadline_at" not in body
            assert TASK_TOKEN not in result["body"]

    def test_read_failure_returns_500(self):
        table = MagicMock()
        table.get_item.side_effect = _client_error("InternalServerError", "GetItem")
        with patch.object(input_status.dynamodb, "Table", return_value=table):
            result = input_status.handler(_event(), None)

        assert result["statusCode"] == 500


class TestInputSubmitValidation:
    def test_rejects_rpe_zero(self):
        result = input_submit.handler(_event("POST", {"rpe": 0}), None)
        assert result["statusCode"] == 400

    def test_rejects_rpe_eleven(self):
        result = input_submit.handler(_event("POST", {"rpe": 11}), None)
        assert result["statusCode"] == 400

    def test_rejects_boolean_rpe(self):
        result = input_submit.handler(_event("POST", {"rpe": True}), None)
        assert result["statusCode"] == 400

    def test_rejects_string_rpe(self):
        result = input_submit.handler(_event("POST", {"rpe": "7"}), None)
        assert result["statusCode"] == 400

    def test_rejects_unknown_field(self):
        result = input_submit.handler(_event("POST", {"rpe": 7, "extra": 1}), None)
        assert result["statusCode"] == 400

    def test_rejects_non_string_summary(self):
        result = input_submit.handler(_event("POST", {"rpe": 7, "summary": 123}), None)
        assert result["statusCode"] == 400

    def test_rejects_summary_over_2000_after_cleaning(self):
        result = input_submit.handler(
            _event("POST", {"rpe": 7, "summary": "\u0000" + "x" * 2001}), None
        )
        assert result["statusCode"] == 400

    def test_accepts_summary_at_2000_after_cleaning(self):
        event = _event("POST", {"rpe": 7, "summary": "\u0000" + "x" * 2000})

        submission, error = input_submit._validated_body(event)

        assert error is None
        assert submission == {"rpe": 7, "summary": "x" * 2000}

    def test_strips_format_characters_but_keeps_zwj(self):
        raw = "a\u202eb\u200bc\u2060d\ufeffe \U0001F468\u200d\U0001F469"
        assert input_submit._clean_summary(raw) == "abcde \U0001F468\u200d\U0001F469"

    def test_keeps_newlines_and_normalises_crlf(self):
        assert input_submit._clean_summary("un\r\ndeux\rtrois\nquatre") == "un\ndeux\ntrois\nquatre"

    def test_collapses_three_or_more_newlines_to_two(self):
        assert input_submit._clean_summary("a\n\n\n\nb\r\n\r\n\r\nc\n\nd") == "a\n\nb\n\nc\n\nd"

    def test_newline_runs_split_by_removed_characters_are_collapsed(self):
        assert input_submit._clean_summary("a\n\u200b\n\u0000\nb") == "a\n\nb"

    def test_strips_other_control_characters(self):
        assert input_submit._clean_summary("a\tb\u0007c\u0085d") == "abcd"

    def test_submit_table_name_is_read_at_call_time(self, monkeypatch):
        monkeypatch.setenv("ACTIVITIES_TABLE", "late-bound-activities")
        with patch.object(input_submit.dynamodb, "Table") as table:
            table.return_value.get_item.return_value = {}
            input_submit.handler(_event("POST", {"rpe": 7}), None)
        table.assert_called_once_with("late-bound-activities")

    def test_rejects_invalid_json(self):
        event = _event("POST", {"rpe": 7})
        event["body"] = "{"
        result = input_submit.handler(event, None)
        assert result["statusCode"] == 400

    def test_rejects_non_object_body(self):
        event = _event("POST", {"rpe": 7})
        event["body"] = "[]"
        result = input_submit.handler(event, None)
        assert result["statusCode"] == 400

    def test_rejects_invalid_activity_id(self):
        with patch.object(input_submit.dynamodb, "Table") as table:
            result = input_submit.handler(
                _event("POST", {"rpe": 7}, activity_id="123/feedback"), None
            )
        assert result["statusCode"] == 400
        table.assert_not_called()


class TestInputSubmit:
    def _owned_table(self):
        table = MagicMock()
        table.get_item.return_value = {"Item": {
            "activity_id": ACTIVITY_ID,
            "user_id": USER_ID,
            "athlete_input_state": "awaiting",
        }}
        table.update_item.return_value = {"Attributes": {
            "input_task_token": TASK_TOKEN,
            "athlete_input_state": "awaiting",
        }}
        return table

    def test_missing_identity_is_forbidden_without_read(self):
        with patch.object(input_submit.dynamodb, "Table") as dynamodb_table:
            result = input_submit.handler(
                _event("POST", {"rpe": 7}, user_id=None), None
            )

        assert result["statusCode"] == 403
        dynamodb_table.assert_not_called()

    def test_other_owner_is_forbidden_without_update(self):
        table = self._owned_table()
        table.get_item.return_value = {"Item": {"user_id": "someone-else"}}
        with patch.object(input_submit.dynamodb, "Table", return_value=table):
            result = input_submit.handler(_event("POST", {"rpe": 7}), None)

        assert result["statusCode"] == 403
        table.update_item.assert_not_called()

    def test_success_stores_cleaned_input_removes_token_and_resumes_task(self):
        table = self._owned_table()
        with (
            patch.object(input_submit.dynamodb, "Table", return_value=table),
            patch.object(input_submit.stepfunctions, "send_task_success") as callback,
            patch.object(input_submit, "_record_outcome") as metric,
        ):
            result = input_submit.handler(
                _event("POST", {"rpe": 8, "summary": "Dur\nmais bien\u0000"}), None
            )

        assert result["statusCode"] == 202
        assert TASK_TOKEN not in result["body"]
        callback.assert_called_once_with(taskToken=TASK_TOKEN, output="{}")
        metric.assert_called_once_with("ok")
        kwargs = table.update_item.call_args.kwargs
        assert kwargs["ReturnValues"] == "ALL_OLD"
        assert kwargs["ConditionExpression"] == (
            "athlete_input_state = :awaiting AND user_id = :user_id"
        )
        assert "REMOVE input_task_token" in kwargs["UpdateExpression"]
        stored = kwargs["ExpressionAttributeValues"][":input"]
        assert stored["rpe"] == 8
        assert stored["summary"] == "Dur\nmais bien"
        assert datetime.fromisoformat(stored["submitted_at"]).tzinfo is not None

    def test_empty_summary_is_stored_when_omitted(self):
        table = self._owned_table()
        with (
            patch.object(input_submit.dynamodb, "Table", return_value=table),
            patch.object(input_submit.stepfunctions, "send_task_success"),
            patch.object(input_submit, "_record_outcome"),
        ):
            result = input_submit.handler(_event("POST", {"rpe": 5}), None)

        assert result["statusCode"] == 202
        stored = table.update_item.call_args.kwargs["ExpressionAttributeValues"][":input"]
        assert stored["summary"] == ""

    def test_conditional_write_failure_returns_409(self):
        table = self._owned_table()
        table.update_item.side_effect = _client_error(
            "ConditionalCheckFailedException", "UpdateItem"
        )
        with (
            patch.object(input_submit.dynamodb, "Table", return_value=table),
            patch.object(input_submit.stepfunctions, "send_task_success") as callback,
            patch.object(input_submit, "_record_outcome") as metric,
        ):
            result = input_submit.handler(_event("POST", {"rpe": 5}), None)

        assert result["statusCode"] == 409
        callback.assert_not_called()
        metric.assert_called_once_with("409")

    def test_timed_out_callback_returns_202_and_records_late(self):
        table = self._owned_table()
        with (
            patch.object(input_submit.dynamodb, "Table", return_value=table),
            patch.object(
                input_submit.stepfunctions,
                "send_task_success",
                side_effect=_client_error("TaskTimedOut", "SendTaskSuccess"),
            ),
            patch.object(input_submit, "_record_outcome") as metric,
        ):
            result = input_submit.handler(_event("POST", {"rpe": 5}), None)

        assert result["statusCode"] == 202
        metric.assert_called_once_with("late")

    def test_other_callback_error_returns_202_and_records_callback_error(self):
        table = self._owned_table()
        with (
            patch.object(input_submit.dynamodb, "Table", return_value=table),
            patch.object(
                input_submit.stepfunctions,
                "send_task_success",
                side_effect=_client_error("AccessDeniedException", "SendTaskSuccess"),
            ),
            patch.object(input_submit, "_record_outcome") as metric,
            patch.object(input_submit.logger, "error") as error_log,
        ):
            result = input_submit.handler(_event("POST", {"rpe": 5}), None)

        assert result["statusCode"] == 202
        metric.assert_called_once_with("callback_error")
        assert TASK_TOKEN not in repr(error_log.call_args)

    def test_missing_old_token_returns_202_and_records_callback_error(self):
        table = self._owned_table()
        table.update_item.return_value = {"Attributes": {}}
        with (
            patch.object(input_submit.dynamodb, "Table", return_value=table),
            patch.object(input_submit.stepfunctions, "send_task_success") as callback,
            patch.object(input_submit, "_record_outcome") as metric,
        ):
            result = input_submit.handler(_event("POST", {"rpe": 5}), None)

        assert result["statusCode"] == 202
        callback.assert_not_called()
        metric.assert_called_once_with("callback_error")

    def test_get_item_failure_returns_500_without_update(self):
        table = self._owned_table()
        table.get_item.side_effect = _client_error("InternalServerError", "GetItem")
        with patch.object(input_submit.dynamodb, "Table", return_value=table):
            result = input_submit.handler(_event("POST", {"rpe": 5}), None)

        assert result["statusCode"] == 500
        table.update_item.assert_not_called()

    def test_nonconditional_write_failure_returns_500(self):
        table = self._owned_table()
        table.update_item.side_effect = _client_error("InternalServerError", "UpdateItem")
        with (
            patch.object(input_submit.dynamodb, "Table", return_value=table),
            patch.object(input_submit, "_record_outcome") as metric,
        ):
            result = input_submit.handler(_event("POST", {"rpe": 5}), None)

        assert result["statusCode"] == 500
        metric.assert_not_called()

    def test_handlers_never_log_full_event_or_task_token(self):
        root = Path(__file__).parents[2] / "lambda_functions" / "athlete_input"
        sources = "\n".join(path.read_text() for path in root.glob("input_*.py"))
        assert "logger.info(event" not in sources
        assert "logger.error(event" not in sources
        assert 'extra={"task_token"' not in sources
        assert '"input_task_token": task_token' not in sources


class TestInputSubmitMetric:
    def test_emf_has_exact_outcome_dimension(self, capsys, monkeypatch):
        monkeypatch.delenv("POWERTOOLS_SERVICE_NAME", raising=False)

        input_submit._record_outcome("ok")

        blobs = []
        for line in capsys.readouterr().out.splitlines():
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "_aws" in candidate:
                blobs.append(candidate)
        assert len(blobs) == 1
        blob = blobs[0]
        directive = blob["_aws"]["CloudWatchMetrics"][0]
        assert directive["Namespace"] == "StravaAIBoost"
        assert directive["Dimensions"] == [["outcome"]]
        assert [metric["Name"] for metric in directive["Metrics"]] == ["InputSubmit"]
        assert blob["outcome"] == "ok"
        assert blob["InputSubmit"] in (1.0, [1.0])

    def test_metric_emission_failure_does_not_change_api_behavior(self):
        with patch.object(input_submit, "single_metric", side_effect=RuntimeError("boom")):
            input_submit._record_outcome("callback_error")
