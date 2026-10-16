"""Business metric "artefact produced" (reliability plan, lot 1).

WHY this exists: after a model switch, voice debrief, weekly synthesis and weekly audio
recap produced nothing for days while every Lambda ``Errors`` metric sat at ~0. The
handlers swallowed the failure (batchItemFailures, ``{"statusCode": 500}``). Each
producer now emits ``<Artefact>Produced{outcome=ok|empty|failed|degraded}``, and the
weekly ones RAISE on failure.

Three layers of checks:
1. the EMF blob each module writes has exactly the shape the CloudWatch alarms select
   on (namespace, metric name, dimension set ``{outcome}``);
2. each handler path emits the right outcome (and synthesis/recap raise);
3. an anti-drift source check that the six producers keep emitting their metric on the
   failure path, and that nothing adds a ``service`` dimension behind the alarms' back.
"""

import ast
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from processing import coach_generator, content_generator, strava_updater  # noqa: E402
from processing import voice_debrief_generator as voice  # noqa: E402
from support import weekly_audio_recap as recap  # noqa: E402
from support import weekly_synthesis as synthesis  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# module, file, metric name -- the contract with stacks/webhook_processing_stack.py
PRODUCERS = [
    (content_generator, "lambda_functions/processing/content_generator.py", "ContentProduced"),
    (coach_generator, "lambda_functions/processing/coach_generator.py", "CoachProduced"),
    (voice, "lambda_functions/processing/voice_debrief_generator.py", "VoiceDebriefProduced"),
    (synthesis, "lambda_functions/support/weekly_synthesis.py", "WeeklySynthesisProduced"),
    (recap, "lambda_functions/support/weekly_audio_recap.py", "WeeklyRecapProduced"),
    (strava_updater, "lambda_functions/processing/strava_updater.py", "ActivityPublished"),
]


def _emf_blobs(captured: str) -> list:
    """Every EMF blob (JSON line carrying an ``_aws`` key) printed on stdout."""
    blobs = []
    for line in captured.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "_aws" in data:
            blobs.append(data)
    return blobs


# ---------------------------------------------------------------------------
# 1. EMF shape
# ---------------------------------------------------------------------------
class TestEmfShape:
    # One test looping over the producers rather than pytest parametrisation: test_docs_sync
    # counts one collected test per def in tests/unit.
    def test_outcome_metric_shape(self, capsys, monkeypatch):
        monkeypatch.delenv("POWERTOOLS_SERVICE_NAME", raising=False)
        for module, path, metric_name in PRODUCERS:
            module._record_outcome("failed")
            blobs = _emf_blobs(capsys.readouterr().out)
            assert len(blobs) == 1, (path, blobs)
            blob = blobs[0]
            directive = blob["_aws"]["CloudWatchMetrics"][0]
            assert directive["Namespace"] == "StravaAIBoost", path
            assert [m["Name"] for m in directive["Metrics"]] == [metric_name], path
            # Exactly {outcome}: the alarms select on this dimension set and nothing else.
            assert directive["Dimensions"] == [["outcome"]], path
            assert blob["outcome"] == "failed", path
            assert blob[metric_name] in (1.0, [1.0]), path

    def test_emission_failure_never_raises(self):
        with patch.object(content_generator, "single_metric", side_effect=RuntimeError("boom")):
            content_generator._record_outcome("ok")  # must not raise


# ---------------------------------------------------------------------------
# 2. Handler paths
# ---------------------------------------------------------------------------
class TestContentGenerator:
    EVENT = {"activity_id": "a1", "user_id": "u1"}

    @pytest.fixture
    def pipeline(self):
        with patch.object(content_generator, "retrieve_activity_data_from_dynamodb",
                          return_value={"activity_data": {"sport_type": "Run"}}), \
             patch.object(content_generator, "get_user_configuration", return_value={}), \
             patch.object(content_generator, "get_active_modules", return_value=[]), \
             patch.object(content_generator, "build_user_profile_from_config", return_value=None), \
             patch.object(content_generator, "extract_enduraw_report", return_value=None), \
             patch.object(content_generator, "apply_module_processing", return_value=[]), \
             patch.object(content_generator, "generate_enhanced_content",
                          return_value={"title": "T", "description": "D"}) as gen, \
             patch.object(content_generator, "apply_content_guard",
                          side_effect=lambda content, *a: (content, [], [])) as guard, \
             patch.object(content_generator, "store_generated_content"), \
             patch.object(content_generator, "_record_outcome") as rec:
            yield {"gen": gen, "guard": guard, "rec": rec}

    def test_ok(self, pipeline):
        result = content_generator.handler(dict(self.EVENT), None)
        assert result["statusCode"] == 200
        pipeline["rec"].assert_called_once_with("ok")

    def test_empty_description(self, pipeline):
        pipeline["gen"].return_value = {"title": "T", "description": ""}
        content_generator.handler(dict(self.EVENT), None)
        pipeline["rec"].assert_called_once_with("empty")

    def test_failed(self, pipeline):
        pipeline["gen"].side_effect = ValueError("Empty response from AgentCore agent")
        result = content_generator.handler(dict(self.EVENT), None)
        assert result["statusCode"] == 500
        pipeline["rec"].assert_called_once_with("failed")

    def test_degraded_when_guard_fails(self, pipeline):
        pipeline["guard"].side_effect = RuntimeError("guard down")
        content_generator.handler(dict(self.EVENT), None)
        pipeline["rec"].assert_called_once_with("degraded")

    def test_degradation_does_not_leak_to_next_invocation(self, pipeline):
        pipeline["guard"].side_effect = RuntimeError("guard down")
        content_generator.handler(dict(self.EVENT), None)
        pipeline["guard"].side_effect = lambda content, *a: (content, [], [])
        pipeline["rec"].reset_mock()
        content_generator.handler(dict(self.EVENT), None)
        pipeline["rec"].assert_called_once_with("ok")

    def test_preview_never_emits(self, pipeline):
        content_generator.handler({**self.EVENT, "preview": True}, None)
        pipeline["gen"].side_effect = ValueError("boom")
        content_generator.handler({**self.EVENT, "preview": True}, None)
        pipeline["rec"].assert_not_called()

    def test_strength_extraction_failure_marks_degraded(self):
        content_generator._DEGRADATIONS.clear()
        runtime = MagicMock()
        runtime.converse.side_effect = RuntimeError("bedrock down")
        with patch.object(content_generator, "_get_bedrock_runtime", return_value=runtime):
            assert content_generator._extract_strength_sets("Squat 4x8 80kg, DC 3x10 60") == []
        assert content_generator._DEGRADATIONS == ["strength_extraction"]
        content_generator._DEGRADATIONS.clear()


class TestCoachGenerator:
    EVENT = {"activity_id": "a1", "user_id": "u1", "user_config": {}}

    @pytest.fixture
    def pipeline(self):
        table = MagicMock()
        table.get_item.return_value = {"Item": {}}
        table.scan.return_value = {"Items": []}
        ddb = MagicMock()
        ddb.Table.return_value = table
        with patch.object(coach_generator, "dynamodb", ddb), \
             patch.object(coach_generator, "retrieve_activity_data",
                          return_value={"start_date": "2026-10-12T08:00:00Z"}) as retrieve, \
             patch.object(coach_generator, "build_historical_summary", return_value={}), \
             patch.object(coach_generator, "extract_and_store_prs"), \
             patch.object(coach_generator, "build_week_overview", return_value={}), \
             patch.object(coach_generator, "_invoke_coach_agent",
                          return_value={"strava_block": "Bien."}) as invoke, \
             patch.object(coach_generator, "verify_weekly_claims", return_value=[]), \
             patch.object(coach_generator, "find_internal_contradictions", return_value=[]), \
             patch.object(coach_generator, "_inject_recap_line"), \
             patch.object(coach_generator, "store_coach_feedback"), \
             patch.object(coach_generator, "_record_outcome") as rec:
            yield {"ddb": ddb, "retrieve": retrieve, "invoke": invoke, "rec": rec}

    def test_ok(self, pipeline):
        result = coach_generator.handler(dict(self.EVENT), None)
        assert result["statusCode"] == 200
        pipeline["rec"].assert_called_once_with("ok")

    def test_empty_when_agent_returns_nothing(self, pipeline):
        pipeline["invoke"].return_value = None
        result = coach_generator.handler(dict(self.EVENT), None)
        assert result["coach_feedback"] is None
        pipeline["rec"].assert_called_once_with("empty")

    def test_failed(self, pipeline):
        pipeline["retrieve"].return_value = None
        result = coach_generator.handler(dict(self.EVENT), None)
        assert result["statusCode"] == 500
        pipeline["rec"].assert_called_once_with("failed")

    def test_degraded_when_context_reads_fail(self, pipeline):
        table = pipeline["ddb"].Table.return_value
        table.get_item.side_effect = RuntimeError("ddb down")
        table.scan.side_effect = RuntimeError("ddb down")
        coach_generator.handler(dict(self.EVENT), None)
        pipeline["rec"].assert_called_once_with("degraded")

    def test_coach_lambda_never_writes_agentcore_memory(self):
        # Decision 2026-10-16: the coach's own output must never reach the
        # shared memory (undated model text re-read as fact by the coach).
        import inspect
        source = inspect.getsource(coach_generator)
        assert "create_event" not in source
        assert "write_coaching_observation" not in source
        assert not hasattr(coach_generator, "MEMORY_ID")


class TestVoiceDebrief:
    @staticmethod
    def _event(*seqs):
        return {"Records": [{"eventName": "MODIFY", "dynamodb": {"SequenceNumber": s}} for s in seqs]}

    def test_ok_and_skip(self):
        with patch.object(voice, "_process_record", side_effect=[True, False]), \
             patch.object(voice, "_record_outcome") as rec:
            result = voice.handler(self._event("1", "2"), None)
        assert result == {"batchItemFailures": []}
        rec.assert_called_once_with("ok")  # a skipped record emits nothing

    def test_failed_keeps_batch_item_failures(self):
        with patch.object(voice, "_process_record", side_effect=RuntimeError("polly down")), \
             patch.object(voice, "_record_outcome") as rec:
            result = voice.handler(self._event("7"), None)
        assert result == {"batchItemFailures": [{"itemIdentifier": "7"}]}
        rec.assert_called_once_with("failed")

    def test_empty_script(self):
        with patch.object(voice, "_process_record", side_effect=voice.EmptyOutput("empty")), \
             patch.object(voice, "_record_outcome") as rec:
            result = voice.handler(self._event("8"), None)
        assert result == {"batchItemFailures": [{"itemIdentifier": "8"}]}
        rec.assert_called_once_with("empty")

    def test_missing_bucket_is_failed(self):
        with patch.object(voice, "AUDIO_BUCKET", ""), \
             patch.object(voice, "_record_outcome") as rec:
            voice.handler(self._event("9"), None)
        rec.assert_called_once_with("failed")

    def test_empty_bedrock_script_raises_empty_output(self):
        """The incident path: the model answered nothing (thinking ate the budget)."""
        record = {
            "eventName": "MODIFY",
            "dynamodb": {"NewImage": {
                "activity_id": {"S": "a1"}, "user_id": {"S": "u1"},
                "processing_status": {"S": "completed"},
                "enhanced_description": {"S": "Sortie facile"},
            }},
        }
        with patch.object(voice, "_resolve_language", return_value="fr"), \
             patch.object(voice, "_load_activity_data", return_value={}), \
             patch.object(voice, "_generate_script", return_value=""):
            with pytest.raises(voice.EmptyOutput):
                voice._process_record(record)

    def test_ineligible_record_returns_false(self):
        assert voice._process_record({"eventName": "REMOVE"}) is False


class TestWeeklySynthesis:
    @pytest.fixture
    def env(self):
        table = MagicMock()
        table.query.return_value = {"Items": [{"distance": 10000, "moving_time": 3000,
                                               "activity_type": "Run"}]}
        table.get_item.return_value = {"Item": {}}
        ddb = MagicMock()
        ddb.Table.return_value = table
        bedrock = MagicMock()
        with patch.object(synthesis, "DEFAULT_USER_ID", "u1"), \
             patch.object(synthesis, "dynamodb", ddb), \
             patch.object(synthesis.boto3, "client", return_value=bedrock), \
             patch.object(synthesis, "no_thinking", return_value={}), \
             patch.object(synthesis, "text_from_converse",
                          return_value='{"summary": "Belle semaine"}') as text, \
             patch.object(synthesis, "_record_outcome") as rec:
            yield {"table": table, "bedrock": bedrock, "text": text, "rec": rec}

    def test_ok(self, env):
        result = synthesis.handler({}, None)
        assert result["statusCode"] == 200
        env["rec"].assert_called_once_with("ok")

    def test_no_activity_is_empty_not_raised(self, env):
        env["table"].query.return_value = {"Items": []}
        result = synthesis.handler({}, None)
        assert result["statusCode"] == 200
        env["rec"].assert_called_once_with("empty")

    def test_bedrock_failure_emits_failed_and_raises(self, env):
        env["bedrock"].converse.side_effect = RuntimeError("model gone")
        with pytest.raises(RuntimeError, match="model gone"):
            synthesis.handler({}, None)
        env["rec"].assert_called_once_with("failed")

    def test_truncated_json_raises(self, env):
        env["text"].return_value = '{"summary": "cut mid'
        with pytest.raises(json.JSONDecodeError):
            synthesis.handler({}, None)
        env["rec"].assert_called_once_with("failed")

    def test_summary_missing_raises(self, env):
        env["text"].return_value = '{"highlight": "x"}'
        with pytest.raises(synthesis.GenerationFailed):
            synthesis.handler({}, None)
        env["rec"].assert_called_once_with("failed")

    def test_no_user_raises(self, env):
        with patch.object(synthesis, "DEFAULT_USER_ID", ""):
            with pytest.raises(synthesis.GenerationFailed):
                synthesis.handler({}, None)
        env["rec"].assert_called_once_with("failed")


class TestWeeklyAudioRecap:
    EVENT = {"user_id": "u1", "source": "aws.events"}

    @pytest.fixture
    def env(self):
        with patch.object(recap, "dynamodb", MagicMock()), \
             patch.object(recap, "_get_existing_recap", return_value=None) as existing, \
             patch.object(recap, "_fetch_week_activities", return_value=[{"distance": 1}]) as fetch, \
             patch.object(recap, "_get_user_config", return_value={}), \
             patch.object(recap, "_generate_script", return_value="Bonne semaine") as script, \
             patch.object(recap, "_synthesize_audio", return_value=(b"mp3", 120)) as audio, \
             patch.object(recap, "_upload_to_s3"), \
             patch.object(recap, "_record_outcome") as rec:
            yield {"existing": existing, "fetch": fetch, "script": script,
                   "audio": audio, "rec": rec}

    def test_ok(self, env):
        result = recap.handler(dict(self.EVENT), None)
        assert result["statusCode"] == 200
        env["rec"].assert_called_once_with("ok")

    def test_no_activity_is_empty(self, env):
        env["fetch"].return_value = []
        result = recap.handler(dict(self.EVENT), None)
        assert result["statusCode"] == 200
        env["rec"].assert_called_once_with("empty")

    def test_existing_recap_emits_exists(self, env):
        # The week is covered: counted so the "missing" alarm does not fire.
        env["existing"].return_value = {"week": "2026-W41"}
        recap.handler(dict(self.EVENT), None)
        env["rec"].assert_called_once_with("exists")

    def test_script_failure_emits_failed_and_raises(self, env):
        env["script"].return_value = None
        with pytest.raises(recap.GenerationFailed, match="Script"):
            recap.handler(dict(self.EVENT), None)
        env["rec"].assert_called_once_with("failed")

    def test_audio_failure_emits_failed_and_raises(self, env):
        env["audio"].return_value = (None, 0)
        with pytest.raises(recap.GenerationFailed, match="Audio"):
            recap.handler(dict(self.EVENT), None)
        env["rec"].assert_called_once_with("failed")

    def test_degraded_when_memory_read_failed(self, env):
        def _script(*_a, **_k):
            recap._mark_degraded("memory_read")
            return "Bonne semaine"
        env["script"].side_effect = _script
        recap.handler(dict(self.EVENT), None)
        env["rec"].assert_called_once_with("degraded")

    def test_memory_read_failure_marks_degraded(self):
        recap._DEGRADATIONS.clear()
        with patch.object(recap, "MEMORY_ID", "mem-1"), \
             patch.object(recap.boto3, "client", side_effect=RuntimeError("down")):
            assert recap._retrieve_memory_observations("u1") == ""
        assert recap._DEGRADATIONS == ["memory_read"]
        recap._DEGRADATIONS.clear()


class TestStravaUpdater:
    EVENT = {"activity_id": "a1", "user_id": "u1",
             "enhanced_content": {"title": "T", "description": "D"}}

    @pytest.fixture
    def env(self):
        with patch.object(strava_updater, "get_access_token", return_value="tok"), \
             patch.object(strava_updater, "update_strava_activity",
                          return_value={"status": "success"}) as update, \
             patch.object(strava_updater, "update_activity_status"), \
             patch.object(strava_updater, "_record_outcome") as rec:
            yield {"update": update, "rec": rec}

    def test_ok(self, env):
        strava_updater.handler(dict(self.EVENT), None)
        env["rec"].assert_called_once_with("ok")

    def test_nothing_to_update_is_empty(self, env):
        env["update"].return_value = {"status": "no_update_needed"}
        strava_updater.handler(dict(self.EVENT), None)
        env["rec"].assert_called_once_with("empty")

    def test_no_content_is_empty(self, env):
        strava_updater.handler({**self.EVENT, "enhanced_content": {}}, None)
        env["rec"].assert_called_once_with("empty")

    def test_strava_error_is_failed(self, env):
        env["update"].side_effect = Exception("Strava API rate limit exceeded")
        result = strava_updater.handler(dict(self.EVENT), None)
        assert result["statusCode"] == 500
        env["rec"].assert_called_once_with("failed")


# ---------------------------------------------------------------------------
# 3. Anti-drift
# ---------------------------------------------------------------------------
def _calls_record_outcome(nodes, outcome: str) -> bool:
    for node in nodes:
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "_record_outcome"
                and sub.args
                and isinstance(sub.args[0], ast.Constant)
                and sub.args[0].value == outcome
            ):
                return True
    return False


class TestAntiDrift:
    def test_producers_emit_their_metric(self):
        for _module, path, metric_name in PRODUCERS:
            self._check_producer(path, metric_name)

    @staticmethod
    def _check_producer(path: str, metric_name: str) -> None:
        source = (REPO_ROOT / path).read_text()
        tree = ast.parse(source)
        assert f'"{metric_name}"' in source, f"{path} no longer names {metric_name}"
        assert "single_metric(" in source, f"{path} no longer emits through single_metric"

        handler = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "handler"
        )
        # The failure path of the handler must emit outcome=failed: that is the whole
        # point of the lot (a swallowed failure must make noise).
        except_bodies = [
            h for n in ast.walk(handler) if isinstance(n, ast.Try) for h in n.handlers
        ]
        assert _calls_record_outcome(except_bodies, "failed"), (
            f"{path}: handler has no except that emits outcome=failed"
        )
        # ...and a success path exists outside any except.
        except_nodes = {id(n) for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler)
                        for n in ast.walk(h)}
        success_calls = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "_record_outcome" and id(n) not in except_nodes
        ]
        assert success_calls, f"{path}: no _record_outcome call on the success path"
        assert any(isinstance(n, ast.Constant) and n.value == "ok" for n in ast.walk(tree))

    def test_weekly_producers_reraise(self):
        """Synthesis and recap must raise after emitting failed, so Lambda Errors counts it."""
        for path in ("lambda_functions/support/weekly_synthesis.py",
                     "lambda_functions/support/weekly_audio_recap.py"):
            self._check_reraise(path)

    @staticmethod
    def _check_reraise(path: str) -> None:
        tree = ast.parse((REPO_ROOT / path).read_text())
        handler = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "handler"
        )
        for node in ast.walk(handler):
            if isinstance(node, ast.ExceptHandler) and _calls_record_outcome([node], "failed"):
                assert any(isinstance(s, ast.Raise) for s in ast.walk(node)), (
                    f"{path}: except emits failed but does not re-raise"
                )
        assert '{"statusCode": 500' not in "".join(
            line for line in (REPO_ROOT / path).read_text().splitlines(True)
            if not line.lstrip().startswith("#")
        ), f"{path} answers a 500 payload again instead of raising"

    def test_no_service_dimension_injected(self):
        """POWERTOOLS_SERVICE_NAME adds a `service` dimension to single_metric blobs,
        which would silently detach every outcome alarm (they select on {outcome})."""
        for stack in (REPO_ROOT / "stacks").glob("*.py"):
            assert "POWERTOOLS_SERVICE_NAME" not in stack.read_text(), stack.name
