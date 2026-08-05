"""Unit tests for the Campus Coach week-disambiguation fixes (Agent A: B1/B5/B6).

Covers, for the three files owned by Agent A:
  * coach_generator.py  — canonical status in the plan passed to the LLM (B1),
    ISO-week label on the current-week plan block + ISO-string activity_iso_week
    in the agent payload (B5), and the module-level `iso_week_label` helper.
  * coach_context.py    — canonical status in `format_campus_sessions` (B1) and
    the ISO-week label on the "cette semaine" header (B5).
  * coach_chat_agent.py — the local `_effective_status` mirror (B1), which must
    reproduce shared.campus_status.effective_status() precedence exactly.

The recurring assertion of interest: a session whose legacy `status` is stale
('todo') but whose `provider_status` is 'done' MUST be seen as done, and every
plan block handed to the model MUST carry its ISO week identity.
"""

import importlib.util
import json
import os
import re
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

# The coach handler imports agents.coach_agent lazily elsewhere; stub the package
# so importing the module never reaches for the (deploy-only) agent code.
sys.modules.setdefault("agents", MagicMock())
sys.modules.setdefault("agents.coach_agent", MagicMock())

import processing.coach_generator as cg  # noqa: E402
from shared.coach_context import fetch_campus_weekly_plan, format_campus_sessions  # noqa: E402


# --------------------------------------------------------------------------- #
# shared.iso_week.iso_week_label  (B5 helper)
# --------------------------------------------------------------------------- #
class TestIsoWeekLabel:
    def test_returns_zero_padded_iso_string(self):
        # 2026-01-01 is a Thursday -> ISO week 1 of 2026 -> zero-padded "W01".
        assert cg.iso_week_label("2026-01-01T00:00:00") == "2026-W01"

    def test_matches_iso_format_and_is_str(self):
        label = cg.iso_week_label("2026-08-06T10:00:00Z")
        assert isinstance(label, str)
        assert re.match(r"^\d{4}-W\d{2}$", label)

    def test_empty_or_unparseable_returns_empty(self):
        assert cg.iso_week_label("") == ""
        assert cg.iso_week_label(None) == ""
        assert cg.iso_week_label("not-a-date") == ""


# --------------------------------------------------------------------------- #
# coach_generator handler  (B1 + B5: campus_coach_plan built for the LLM)
# --------------------------------------------------------------------------- #
class TestCampusPlanForCoachAgent:
    """Drive the real handler and capture the historical_summary it sends."""

    def _run_handler_capturing_summary(self, session: dict) -> dict:
        captured: dict = {}

        def _fake_invoke(activity_data, user_config, historical_summary):
            captured["historical_summary"] = historical_summary
            return {"strava_block": "ok"}

        mock_table = MagicMock()
        # USER_CONFIG enrichment get_item -> no extra config.
        mock_table.get_item.return_value = {"Item": {}}
        # 1st scan: current/future sessions. 2nd scan: athlete-context (none).
        mock_table.scan.side_effect = [{"Items": [session]}, {"Items": []}]
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table

        event = {"activity_id": "act1", "user_id": "u1", "user_config": {}}

        with patch.object(cg, "dynamodb", mock_dynamo), \
                patch.object(cg, "COACH_AGENT_ARN", "arn:aws:bedrock-agentcore:eu-west-1:1:runtime/coach"), \
                patch.object(cg, "retrieve_activity_data", return_value={"start_date_local": "2026-08-06T10:00:00Z"}), \
                patch.object(cg, "build_historical_summary", return_value={}), \
                patch.object(cg, "extract_and_store_prs"), \
                patch.object(cg, "store_coach_feedback"), \
                patch.object(cg, "write_coaching_observation"), \
                patch.object(cg, "_invoke_coach_agent", side_effect=_fake_invoke):
            response = cg.handler(event, None)

        assert response["statusCode"] == 200
        return captured["historical_summary"]

    def test_stale_status_resolved_as_done_via_effective_status(self):
        # Legacy status is stale ('todo') but the provider says the session was
        # done: the coach must see it as done (B1).
        session = {
            "title": "Seuil 30",
            "week_date_iso": "2026-W32",
            "status": "todo",
            "provider_status": "done",
            "is_current_week": True,
            "is_future": False,
            "intervals": [],
            "expected_distance_km": "10.0",
            "expected_duration_min": 60,
            "sport": "road",
            "difficulty": 3,
        }
        hs = self._run_handler_capturing_summary(session)
        plan = hs["campus_coach_plan"]
        assert plan["sessions"][0]["status"] == "done"

    def test_current_week_plan_carries_iso_week_label(self):
        # The plan block handed to the LLM must be a dict carrying its ISO week,
        # and each session keeps its own week_date_iso (B5).
        session = {
            "title": "Seuil 30",
            "week_date_iso": "2026-W32",
            "status": "todo",
            "is_current_week": True,
            "is_future": False,
            "intervals": [],
            "expected_distance_km": "10.0",
            "expected_duration_min": 60,
        }
        hs = self._run_handler_capturing_summary(session)
        plan = hs["campus_coach_plan"]
        assert isinstance(plan, dict)
        assert plan["week"] == "2026-W32"
        assert plan["sessions"][0]["week_date_iso"] == "2026-W32"


# --------------------------------------------------------------------------- #
# coach_generator._invoke_coach_agent  (B5: activity_iso_week is an ISO string)
# --------------------------------------------------------------------------- #
class TestActivityIsoWeekPayload:
    def test_activity_iso_week_is_iso_string_not_int(self):
        captured: dict = {}

        class _Client:
            def invoke_agent_runtime(self, **kwargs):
                captured["payload"] = kwargs["payload"]
                # Minimal well-formed envelope: parseable, no strava_block ->
                # _invoke_coach_agent returns None, which is fine here.
                return {"contentType": "application/json", "response": [b'{"response": "{}"}']}

        with patch.object(cg, "COACH_AGENT_ARN", "arn:aws:bedrock-agentcore:eu-west-1:1:runtime/coach"), \
                patch.object(cg.boto3, "client", lambda *a, **k: _Client()):
            cg._invoke_coach_agent({"start_date_local": "2026-08-06T10:00:00Z"}, {}, {})

        payload = json.loads(captured["payload"].decode("utf-8"))
        iso_week = payload["activity_iso_week"]
        assert isinstance(iso_week, str)
        assert re.match(r"^\d{4}-W\d{2}$", iso_week)
        assert iso_week == cg.iso_week_label("2026-08-06T10:00:00Z")


# --------------------------------------------------------------------------- #
# coach_context.format_campus_sessions  (B1) + fetch_campus_weekly_plan (B5)
# --------------------------------------------------------------------------- #
class TestCoachContextCampus:
    def test_format_campus_sessions_uses_effective_status(self):
        sessions = [
            {"title": "Seuil 30", "status": "todo", "provider_status": "done"},
        ]
        rendered = format_campus_sessions(sessions)
        assert "statut: done" in rendered

    def test_fetch_campus_weekly_plan_labels_current_week_iso(self):
        session = {
            "title": "Seuil 30",
            "week_date_iso": "2026-W32",
            "status": "todo",
            "is_current_week": True,
            "is_future": False,
            "expected_distance_km": "10.0",
        }
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": [session]}
        mock_table.query.return_value = {"Items": []}
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table

        with patch("shared.coach_context.dynamodb", mock_dynamo):
            plan_text = fetch_campus_weekly_plan("u1")

        assert "Plan Campus Coach cette semaine (2026-W32):" in plan_text


# --------------------------------------------------------------------------- #
# coach_chat_agent._effective_status  (B1 local mirror)
# --------------------------------------------------------------------------- #
def _stub_package(top: str, submodules: tuple = ()) -> None:
    """Stub a deploy-only package (and submodules) if it is absent from the venv.

    Robust to a prior test having already stubbed the package: ``find_spec`` on a
    MagicMock left in ``sys.modules`` raises ValueError, so we short-circuit when
    the name is already present (real import or an earlier stub) and swallow the
    lookup errors.
    """
    if top in sys.modules:
        return
    try:
        if importlib.util.find_spec(top) is not None:
            return
    except (ValueError, ModuleNotFoundError):
        pass
    for name in (top, *submodules):
        if name not in sys.modules:
            mod = MagicMock(name=name)
            mod.__path__ = []
            sys.modules[name] = mod


# The coach_chat runtime bundles only src/coach_chat/ (direct_code_deploy), so it
# cannot import shared.campus_status — hence a local mirror. Stub the heavy
# deploy-only deps (only if absent) so we can import the module and exercise that
# mirror; when the CI venv has the real packages, find_spec skips the stub.
_stub_package("ag_ui", ("ag_ui.core", "ag_ui.encoder"))
_stub_package("ag_ui_strands")
_stub_package("fastapi", ("fastapi.responses",))
_stub_package("uvicorn")
_stub_package("strands", ("strands.models",))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "coach_chat"))

import coach_chat_agent as cca  # noqa: E402


class TestCoachChatEffectiveStatus:
    def test_stale_status_but_provider_done_is_done(self):
        assert cca._effective_status({"status": "todo", "provider_status": "done"}) == "done"

    def test_local_status_takes_precedence(self):
        assert (
            cca._effective_status(
                {"local_status": "skip", "status": "done", "provider_status": "done"}
            )
            == "skip"
        )

    def test_legacy_status_is_no_longer_consulted(self):
        """The raw `status` field was retired: it held stale mixed values.

        Completion now lives in local_status / matched_activity_id / provider_status.
        A row whose only completion marker is the legacy field is migrated by
        scripts/migrate_campus_legacy_status.py before this code ships.
        """
        assert cca._effective_status({"status": "Fait"}) == "todo"

    def test_matched_activity_id_implies_done(self):
        assert cca._effective_status({"status": "todo", "matched_activity_id": "act9"}) == "done"

    def test_defaults_to_todo(self):
        assert cca._effective_status({}) == "todo"
        assert cca._effective_status({"status": "todo"}) == "todo"

    def test_matches_shared_effective_status(self):
        """Local mirror must agree with the canonical shared resolver."""
        from shared.campus_status import effective_status

        cases = [
            {"status": "todo", "provider_status": "done"},
            {"local_status": "skip", "status": "done"},
            {"status": "Fait"},
            {"matched_activity_id": "x", "status": "todo"},
            {"completed_at": "2026-08-06", "status": "todo"},
            {},
            {"status": "todo"},
        ]
        for case in cases:
            assert cca._effective_status(case) == effective_status(dict(case))
