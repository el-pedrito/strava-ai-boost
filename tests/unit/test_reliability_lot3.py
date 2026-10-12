"""Reliability plan, lot 3: idempotence, replay, retries.

- TransientAgentError: content/coach generators RAISE it on a transient AgentCore
  failure (502/503/504, throttling, timeout) so the Step Functions Retry applies,
  and keep answering a 500 payload for everything else.
- Deterministic execution names + ExecutionAlreadyExists treated as success.
- Late dictation (BACKLOG P1): the 4 `update` cases.
- strava_updater: local 429 backoff, then a typed error for Step Functions.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

os.environ.setdefault(
    "STEP_FUNCTIONS_ARN",
    "arn:aws:states:eu-west-1:000000000000:stateMachine:StravaAIBoost-ActivityProcessing",
)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from processing import coach_generator, content_generator, strava_updater  # noqa: E402
from webhooks import activity_processor as ap  # noqa: E402


def _client_error(code: str, status: int, op: str = "InvokeAgentRuntime") -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": code},
         "ResponseMetadata": {"HTTPStatusCode": status}},
        op,
    )


# ---------------------------------------------------------------------------
# 1. TransientAgentError mapping
# ---------------------------------------------------------------------------
GENERATORS = (content_generator, coach_generator)
TRANSIENT_ERRORS = (
    _client_error("RuntimeClientError", 502),
    _client_error("ServiceUnavailableException", 503),
    _client_error("RuntimeClientError", 504),
    _client_error("ThrottlingException", 429),
    _client_error("ThrottlingException", 400),
    ReadTimeoutError(endpoint_url="https://x"),
)
PERMANENT_ERRORS = (
    _client_error("ValidationException", 400),
    _client_error("AccessDeniedException", 403),
    _client_error("InternalServerException", 500),
    ValueError("Empty response from AgentCore agent"),
)


class TestTransientClassification:
    def test_class_name_is_what_step_functions_matches(self):
        for module in GENERATORS:
            assert module.TransientAgentError.__name__ == "TransientAgentError"

    def test_transient(self):
        for module in GENERATORS:
            for exc in TRANSIENT_ERRORS:
                assert module._is_transient_agent_error(exc), (module.__name__, exc)

    def test_not_transient(self):
        for module in GENERATORS:
            for exc in PERMANENT_ERRORS:
                assert not module._is_transient_agent_error(exc), (module.__name__, exc)


class TestContentGeneratorTransient:
    def _generate(self, side_effect):
        client = MagicMock()
        client.invoke_agent_runtime.side_effect = side_effect
        with patch.object(content_generator.boto3, "client", return_value=client), \
             patch.object(content_generator, "_get_campus_context", return_value=None):
            return content_generator.generate_enhanced_content(
                {"type": "Run", "sport_type": "Run", "name": "Run"}, "u1", []
            )

    def test_502_on_invoke_raises_transient(self):
        with pytest.raises(content_generator.TransientAgentError):
            self._generate(_client_error("RuntimeClientError", 502))

    def test_non_transient_is_not_wrapped(self):
        with pytest.raises(ClientError):
            self._generate(_client_error("ValidationException", 400))

    @pytest.fixture
    def pipeline(self):
        with patch.object(content_generator, "retrieve_activity_data_from_dynamodb",
                          return_value={"activity_data": {"sport_type": "Run"}}), \
             patch.object(content_generator, "get_user_configuration", return_value={}), \
             patch.object(content_generator, "get_active_modules", return_value=[]), \
             patch.object(content_generator, "build_user_profile_from_config", return_value=None), \
             patch.object(content_generator, "extract_enduraw_report", return_value=None), \
             patch.object(content_generator, "apply_module_processing", return_value=[]), \
             patch.object(content_generator, "generate_enhanced_content") as gen, \
             patch.object(content_generator, "store_generated_content"), \
             patch.object(content_generator, "_record_outcome") as rec:
            yield {"gen": gen, "rec": rec}

    def test_handler_raises_transient_after_failed_outcome(self, pipeline):
        pipeline["gen"].side_effect = content_generator.TransientAgentError("502")
        with pytest.raises(content_generator.TransientAgentError):
            content_generator.handler({"activity_id": "a1", "user_id": "u1"}, None)
        pipeline["rec"].assert_called_once_with("failed")

    def test_handler_keeps_500_payload_for_other_errors(self, pipeline):
        pipeline["gen"].side_effect = ValueError("bad json")
        result = content_generator.handler({"activity_id": "a1", "user_id": "u1"}, None)
        assert result["statusCode"] == 500
        pipeline["rec"].assert_called_once_with("failed")


class TestCoachGeneratorTransient:
    def test_503_on_invoke_raises_transient(self):
        client = MagicMock()
        client.invoke_agent_runtime.side_effect = _client_error("ServiceUnavailableException", 503)
        with patch.object(coach_generator.boto3, "client", return_value=client), \
             patch.object(coach_generator, "COACH_AGENT_ARN", "arn:test"):
            with pytest.raises(coach_generator.TransientAgentError):
                coach_generator._invoke_coach_agent({"start_date": "2026-10-12T08:00:00Z"}, {}, None)

    def test_non_transient_is_not_wrapped(self):
        client = MagicMock()
        client.invoke_agent_runtime.side_effect = _client_error("AccessDeniedException", 403)
        with patch.object(coach_generator.boto3, "client", return_value=client), \
             patch.object(coach_generator, "COACH_AGENT_ARN", "arn:test"):
            with pytest.raises(ClientError):
                coach_generator._invoke_coach_agent({"start_date": "2026-10-12T08:00:00Z"}, {}, None)

    @pytest.fixture
    def pipeline(self):
        table = MagicMock()
        table.get_item.return_value = {"Item": {}}
        table.scan.return_value = {"Items": []}
        ddb = MagicMock()
        ddb.Table.return_value = table
        with patch.object(coach_generator, "dynamodb", ddb), \
             patch.object(coach_generator, "retrieve_activity_data",
                          return_value={"start_date": "2026-10-12T08:00:00Z"}), \
             patch.object(coach_generator, "build_historical_summary", return_value={}), \
             patch.object(coach_generator, "extract_and_store_prs"), \
             patch.object(coach_generator, "build_week_overview", return_value={}), \
             patch.object(coach_generator, "_invoke_coach_agent") as invoke, \
             patch.object(coach_generator, "_record_outcome") as rec:
            yield {"invoke": invoke, "rec": rec}

    def test_handler_raises_transient_after_failed_outcome(self, pipeline):
        pipeline["invoke"].side_effect = coach_generator.TransientAgentError("503")
        with pytest.raises(coach_generator.TransientAgentError):
            coach_generator.handler({"activity_id": "a1", "user_id": "u1", "user_config": {}}, None)
        pipeline["rec"].assert_called_once_with("failed")


# ---------------------------------------------------------------------------
# 2. Execution naming + ExecutionAlreadyExists
# ---------------------------------------------------------------------------
class TestExecutionName:
    def test_create_uses_event_time(self):
        body = {"event_time": 1791483462, "webhook_data": {"aspect_type": "create"}}
        assert ap.build_execution_name("20506094549", body) == "activity-20506094549-v1791483462"

    def test_falls_back_to_webhook_event_time(self):
        body = {"webhook_data": {"aspect_type": "update", "event_time": 1791490000}}
        assert ap.build_execution_name("1", body) == "activity-1-v1791490000"

    def test_float_event_time_is_rendered_as_int(self):
        assert ap.build_execution_name("1", {"event_time": 1791483462.0}) == "activity-1-v1791483462"

    def test_sanitized_and_bounded(self):
        name = ap.build_execution_name("12 3", {"event_time": "2026-10-12T08:00:00.123+00:00" * 4})
        assert len(name) <= 80
        assert all(c.isalnum() or c in "-_" for c in name)

    def test_same_message_same_name(self):
        body = {"event_time": 42}
        assert ap.build_execution_name("7", body) == ap.build_execution_name("7", dict(body))


class TestStartExecution:
    def test_started(self):
        sfn = MagicMock()
        sfn.start_execution.return_value = {"executionArn": "arn:exec"}
        with patch.object(ap, "stepfunctions", sfn), \
             patch.object(ap, "update_activity_execution_arn") as upd:
            arn = ap.start_step_functions_workflow("7", "u1", {"event_time": 42})
        assert arn == "arn:exec"
        assert sfn.start_execution.call_args.kwargs["name"] == "activity-7-v42"
        upd.assert_called_once_with("7", "arn:exec")

    def test_execution_already_exists_is_success(self):
        sfn = MagicMock()
        sfn.start_execution.side_effect = _client_error("ExecutionAlreadyExists", 400, "StartExecution")
        sfn.describe_execution.return_value = {"status": "RUNNING"}
        with patch.object(ap, "stepfunctions", sfn), \
             patch.object(ap, "update_activity_status") as status:
            arn = ap.start_step_functions_workflow("7", "u1", {"event_time": 42})
        assert arn.endswith(":execution:StravaAIBoost-ActivityProcessing:activity-7-v42")
        status.assert_not_called()  # still running: 'processing' is right

    def test_already_exists_and_succeeded_restores_completed(self):
        sfn = MagicMock()
        sfn.start_execution.side_effect = _client_error("ExecutionAlreadyExists", 400, "StartExecution")
        sfn.describe_execution.return_value = {"status": "SUCCEEDED"}
        with patch.object(ap, "stepfunctions", sfn), \
             patch.object(ap, "update_activity_status") as status:
            ap.start_step_functions_workflow("7", "u1", {"event_time": 42})
        status.assert_called_once_with("7", "completed")

    def test_other_errors_still_raise(self):
        sfn = MagicMock()
        sfn.start_execution.side_effect = _client_error("StateMachineDoesNotExist", 400, "StartExecution")
        with patch.object(ap, "stepfunctions", sfn):
            with pytest.raises(ClientError):
                ap.start_step_functions_workflow("7", "u1", {"event_time": 42})


# ---------------------------------------------------------------------------
# 3. Late dictation: the 4 `update` cases
# ---------------------------------------------------------------------------
ENDURAW = "Enduraw Report: allure moyenne 4:12/km, FC 152."
GENERATED = (
    "Seuil du jour, 3x10 min bien tenus.\n\n"
    "Les blocs se sont enchaînés proprement, la FC reste sous contrôle.\n\n"
    "Strava AI Boost Coach : bonne régularité.\n\n"
    "@Generated by Strava AI Boost"
)
DICTATION = "Jambes lourdes au début, ça s'est débloqué au deuxième bloc, vent de face au retour."


def _completed(**extra):
    item = {
        "activity_id": "99",
        "processing_status": "completed",
        "original_description": ENDURAW,
        "enhanced_description": GENERATED,
    }
    item.update(extra)
    return item


class TestDecideLateDictation:
    def test_dictation_added_reprocesses(self):
        current = f"{GENERATED}\n\n{DICTATION}"
        decision = ap.decide_late_dictation(_completed(), current)
        assert decision["action"] == ap.REPROCESS
        assert decision["new_text"] == DICTATION
        assert decision["merged_original"] == f"{ENDURAW}\n\n{DICTATION}"

    def test_dictation_prepended_reprocesses(self):
        decision = ap.decide_late_dictation(_completed(), f"{DICTATION}\n\n{GENERATED}")
        assert decision["action"] == ap.REPROCESS

    def test_manual_edit_of_generated_text_skips(self):
        current = GENERATED.replace("3x10 min bien tenus", "3x10 min plutôt bien tenus")
        decision = ap.decide_late_dictation(_completed(), current)
        assert decision == {**decision, "action": ap.SKIP, "reason": "manual_edit"}

    def test_manual_edit_recorded_by_analyzer_skips(self):
        item = _completed(final_description=GENERATED.replace("FC", "fréquence cardiaque"))
        decision = ap.decide_late_dictation(item, f"{GENERATED}\n\n{DICTATION}")
        assert (decision["action"], decision["reason"]) == (ap.SKIP, "manual_edit_recorded")

    def test_generated_text_replaced_skips(self):
        decision = ap.decide_late_dictation(_completed(), DICTATION)
        assert (decision["action"], decision["reason"]) == (ap.SKIP, "generated_text_replaced")

    def test_our_own_update_skips(self):
        # The update webhook fired by UpdateStrava itself (whitespace may differ).
        decision = ap.decide_late_dictation(_completed(), GENERATED.replace("\n\n", "\n\n\n"))
        assert (decision["action"], decision["reason"]) == (ap.SKIP, "own_write")

    def test_nothing_new_skips(self):
        # Only the athlete's original text re-appears next to ours.
        decision = ap.decide_late_dictation(_completed(), f"{ENDURAW}\n\n{GENERATED}")
        assert (decision["action"], decision["reason"]) == (ap.SKIP, "nothing_new")

    def test_merge_cap_is_a_hard_loop_guard(self):
        item = _completed(late_merge_count=ap.MAX_LATE_MERGES)
        decision = ap.decide_late_dictation(item, f"{GENERATED}\n\n{DICTATION}")
        assert (decision["action"], decision["reason"]) == (ap.SKIP, "merge_cap_reached")

    def test_already_merged_dictation_is_not_new(self):
        # After the reprocess: original holds the dictation, ours restates it.
        item = _completed(original_description=f"{ENDURAW}\n\n{DICTATION}",
                          enhanced_description=GENERATED, late_merge_count=1)
        decision = ap.decide_late_dictation(item, f"{GENERATED}\n\n{DICTATION}")
        assert decision["action"] == ap.SKIP


class TestLateDictationFlow:
    """process_activity_record end to end for an `update` of a completed activity."""

    def _record(self, event_time=1791500000):
        body = {
            "activity_id": "99", "user_id": "u1", "event_time": event_time,
            "webhook_data": {"aspect_type": "update", "object_id": 99, "event_time": event_time},
        }
        return {"messageId": "m1", "body": json.dumps(body)}

    @pytest.fixture
    def env(self):
        table = MagicMock()
        table.get_item.return_value = {"Item": _completed()}
        ddb = MagicMock()
        ddb.Table.return_value = table
        sfn = MagicMock()
        sfn.start_execution.return_value = {"executionArn": "arn:exec"}
        with patch.object(ap, "dynamodb", ddb), \
             patch.object(ap, "stepfunctions", sfn), \
             patch.object(ap, "sqs") as sqs, \
             patch.object(ap, "fetch_user_configuration",
                          return_value={"modules_config": {"enduraw": {"enabled": True}}}), \
             patch.object(ap, "fetch_strava_description") as fetch:
            yield {"table": table, "sfn": sfn, "sqs": sqs, "fetch": fetch}

    def test_dictation_added_starts_reprocess(self, env):
        env["fetch"].return_value = f"{GENERATED}\n\n{DICTATION}"
        ap.process_activity_record(self._record())
        merge = env["table"].update_item.call_args_list[0].kwargs
        assert merge["ConditionExpression"] == "processing_status = :completed"
        assert merge["ExpressionAttributeValues"][":merged"] == f"{ENDURAW}\n\n{DICTATION}"
        assert merge["ExpressionAttributeValues"][":count"] == 1
        env["sqs"].send_message.assert_not_called()  # no second Enduraw wait
        start = env["sfn"].start_execution.call_args.kwargs
        assert start["name"] == "activity-99-v1791500000"
        assert json.loads(start["input"])["webhook_data"]["late_dictation"]["new_text"] == DICTATION

    def _assert_untouched(self, env, current):
        env["fetch"].return_value = current
        ap.process_activity_record(self._record())
        env["table"].update_item.assert_not_called()
        env["sfn"].start_execution.assert_not_called()

    def test_our_own_update_never_touches_the_activity(self, env):
        self._assert_untouched(env, GENERATED)

    def test_manual_edit_never_touches_the_activity(self, env):
        self._assert_untouched(env, GENERATED.replace("bien tenus", "très bien tenus"))

    def test_nothing_new_never_touches_the_activity(self, env):
        self._assert_untouched(env, f"{ENDURAW}\n\n{GENERATED}")

    def test_strava_read_failure_skips_without_failing_the_activity(self, env):
        env["fetch"].side_effect = ValueError("Stored Strava access token expired")
        ap.process_activity_record(self._record())
        env["table"].update_item.assert_not_called()
        env["sfn"].start_execution.assert_not_called()

    def test_lost_merge_race_skips(self, env):
        env["fetch"].return_value = f"{GENERATED}\n\n{DICTATION}"
        env["table"].update_item.side_effect = _client_error(
            "ConditionalCheckFailedException", 400, "UpdateItem")
        ap.process_activity_record(self._record())
        env["sfn"].start_execution.assert_not_called()
        assert env["table"].update_item.call_count == 1  # never flipped to 'failed'

    def test_create_of_completed_activity_still_skips(self, env):
        body = json.loads(self._record()["body"])
        body["webhook_data"]["aspect_type"] = "create"
        ap.process_activity_record({"messageId": "m1", "body": json.dumps(body)})
        env["fetch"].assert_not_called()
        env["sfn"].start_execution.assert_not_called()


# ---------------------------------------------------------------------------
# 4. strava_updater 429 backoff
# ---------------------------------------------------------------------------
def _response(status, retry_after=None):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = {"Retry-After": retry_after} if retry_after is not None else {}
    resp.json.return_value = {"name": "T", "type": "Run"}
    resp.raise_for_status.return_value = None
    return resp


class TestStravaRateLimit:
    CONTENT = {"title": "T", "description": "D"}

    def test_retries_then_succeeds_honouring_capped_retry_after(self):
        responses = [_response(429, "120"), _response(429), _response(200)]
        with patch.object(strava_updater.requests, "put", side_effect=responses) as put, \
             patch.object(strava_updater.time, "sleep") as sleep:
            result = strava_updater.update_strava_activity("1", "tok", self.CONTENT)
        assert result["status"] == "success"
        assert put.call_count == 3
        assert [c.args[0] for c in sleep.call_args_list] == [30, 4]  # capped, then 2*2^1

    def test_three_429_raise_typed_error(self):
        with patch.object(strava_updater.requests, "put", return_value=_response(429)), \
             patch.object(strava_updater.time, "sleep") as sleep:
            with pytest.raises(strava_updater.StravaRateLimitError):
                strava_updater.update_strava_activity("1", "tok", self.CONTENT)
        assert sleep.call_count == 2

    def test_handler_raises_for_step_functions_retry(self):
        event = {"activity_id": "1", "user_id": "u1", "enhanced_content": self.CONTENT}
        with patch.object(strava_updater, "get_access_token", return_value="tok"), \
             patch.object(strava_updater.requests, "put", return_value=_response(429)), \
             patch.object(strava_updater.time, "sleep"), \
             patch.object(strava_updater, "update_activity_status") as status, \
             patch.object(strava_updater, "_record_outcome") as rec:
            with pytest.raises(strava_updater.StravaRateLimitError):
                strava_updater.handler(event, None)
        rec.assert_called_once_with("failed")
        status.assert_not_called()  # a retry is coming, do not mark 'failed'

    def test_invalid_retry_after_falls_back_to_exponential(self):
        assert strava_updater._retry_after_seconds(_response(429, "soon"), 0) == 2
