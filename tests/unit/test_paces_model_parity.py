"""Switches off -> no model-visible change (docs/design/campus-paces.md, review cr1).

The paces sync stores structured fields on every step (``pace_kind``, ``pace_slug``,
``pace_zone``, ``pace_value_s``) and ``estimated_paces`` on every session, whatever
the switches say. Those fields are for the Watch mapper only. These tests build the
REAL agent payload from a legacy row and from its structured twin and require the
two to be byte-identical, for the coach Lambda and the content Lambda.

They also pin the coach handler wiring of the effective pace zones (review S3):
removing ``with_effective_pace_zones`` from the handler must fail a test.
"""

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))
sys.modules.setdefault("agents", MagicMock())
sys.modules.setdefault("agents.coach_agent", MagicMock())

from processing import coach_generator as cg  # noqa: E402
from processing import content_generator as content  # noqa: E402
from shared.pace_zones import strip_structured_pace_fields  # noqa: E402

MANUAL = {"ef": {"min": "5:40", "max": "6:10"}}
CAMPUS = {"ef": {"min": "5:36", "max": "6:02", "slug": "ef",
                 "value_s": Decimal("355.4"), "dvalue_s": Decimal("12.4")}}


def _session(structured: bool) -> dict:
    """One synthetic plan row, in its legacy form or as the new sync writes it."""
    warmup = {"type": "warmup", "duration": "15min", "pace": "5:55/km"}
    work = {"type": "work", "duration": "3min", "pace": "4:20/km"}
    rec = {"type": "recovery", "duration": "1min"}
    if structured:
        warmup = {**warmup, "pace_kind": "range", "pace_slug": "ef", "pace_zone": "ef",
                  "pace_value_s": 355}
        work = {**work, "pace_kind": "single-value", "pace_slug": "seuil30",
                "pace_zone": "threshold", "pace_value_s": 260}
        rec = {**rec, "pace_kind": "abstract", "pace_slug": "slow"}
    row = {
        "session_date": "week-2026-W42",
        "session_id": "1760306400000_1",
        "title": "Seuil 5x3min",
        "sport": "running",
        "week_date_iso": "2026-W42",
        "is_current_week": True,
        "is_future": False,
        "expected_duration_min": Decimal("55"),
        "intervals": [warmup, {"type": "block", "repeat": 5, "exercises": [work, rec]}],
    }
    if structured:
        row["estimated_paces"] = {"ef": {"value": Decimal("355.4"), "dvalue": Decimal("12.4")}}
    return row


class TestStripHelper:
    def test_removes_every_structured_key_recursively(self):
        out = strip_structured_pace_fields(_session(True))
        assert out == _session(False)

    def test_does_not_mutate_input(self):
        row = _session(True)
        strip_structured_pace_fields(row)
        assert row["intervals"][0]["pace_kind"] == "range"
        assert "estimated_paces" in row

    def test_legacy_row_is_unchanged(self):
        assert strip_structured_pace_fields(_session(False)) == _session(False)

    def test_mirror_agrees(self):
        import importlib.util
        path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "coach_chat", "pace_zones.py")
        spec = importlib.util.spec_from_file_location("cc_pz_mirror_strip", path)
        mirror = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mirror)
        from shared import pace_zones as pz
        for case in (_session(True), _session(False), [_session(True)], None, "x", 3, {}):
            assert mirror.strip_structured_pace_fields(case) == pz.strip_structured_pace_fields(case)
        assert mirror.STRUCTURED_INTERVAL_KEYS == pz.STRUCTURED_INTERVAL_KEYS
        assert mirror.STRUCTURED_SESSION_KEYS == pz.STRUCTURED_SESSION_KEYS


# --------------------------------------------------------------------------- #
# Coach Lambda: real handler, real payload bytes.
# --------------------------------------------------------------------------- #
def _coach_payload(session: dict, uc_item: dict) -> dict:
    """Run the coach handler and return the JSON payload sent to the agent runtime."""
    sent = []

    client = MagicMock()

    def _invoke(**kwargs):
        sent.append(kwargs["payload"])
        return {"contentType": "application/json", "response": [b""]}

    client.invoke_agent_runtime.side_effect = _invoke

    sessions_table = MagicMock()

    def _scan(**kwargs):
        values = kwargs.get("ExpressionAttributeValues", {})
        if values.get(":sd") == "athlete-context":
            return {"Items": []}
        return {"Items": [dict(session)]}

    sessions_table.scan.side_effect = _scan
    config_table = MagicMock()
    config_table.get_item.return_value = {"Item": dict(uc_item)}
    resource = MagicMock()
    resource.Table.side_effect = lambda name: config_table if name == cg.USER_CONFIG_TABLE else sessions_table

    activity = {"name": "Seuil", "type": "Run", "distance": 10000, "moving_time": 3300,
                "start_date_local": "2026-10-14T18:00:00Z"}
    event = {"activity_id": "act1", "user_id": "u1",
             "user_config": {"user_preferences": {"pace_zones": MANUAL}}}
    with patch.object(cg, "COACH_AGENT_ARN", "arn:test"), \
            patch.object(cg, "boto3") as boto, \
            patch.object(cg, "dynamodb", resource), \
            patch.object(cg, "retrieve_activity_data", return_value=dict(activity)), \
            patch.object(cg, "build_historical_summary", return_value={"weeks": 4}), \
            patch.object(cg, "extract_and_store_prs"), \
            patch.object(cg, "match_campus_session",
                         side_effect=lambda *a, **k: {"matched_session": dict(session),
                                                      "match_score": 0.9, "sessions": [session]}):
        boto.client.return_value = client
        response = cg.handler(event, None)
    assert response["statusCode"] == 200, response
    assert len(sent) == 1
    return json.loads(sent[0])


class TestCoachPayload:
    def test_structured_twin_gives_identical_payload(self):
        legacy = _coach_payload(_session(False), {"user_preferences": {"pace_zones": MANUAL}})
        twin = _coach_payload(_session(True), {"user_preferences": {"pace_zones": MANUAL}})
        assert json.dumps(legacy, sort_keys=True) == json.dumps(twin, sort_keys=True)
        # Not trivially equal: the plan and the matched session are both there.
        summary = twin["historical_summary"]
        assert summary["campus_coach_plan"]["sessions"][0]["intervals"]
        assert summary["campus_matched_session"]["intervals"]
        text = json.dumps(twin)
        for key in ("pace_kind", "pace_slug", "pace_value_s", "estimated_paces"):
            assert key not in text, key

    def test_payload_carries_campus_zones_when_they_exist(self):
        """Handler wiring (review S3): Campus zones reach the agent payload."""
        week = datetime.now(timezone.utc).strftime("%G-W%V")
        uc_item = {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": week,
                   "user_preferences": {"pace_zones": MANUAL}}
        payload = _coach_payload(_session(False), uc_item)
        zones = payload["user_config"]["user_preferences"]["pace_zones"]
        assert zones["ef"]["min"] == "5:36" and zones["ef"]["max"] == "6:02"

    def test_payload_carries_legacy_zones_without_campus(self):
        payload = _coach_payload(_session(False), {"user_preferences": {"pace_zones": MANUAL}})
        assert payload["user_config"]["user_preferences"]["pace_zones"] == MANUAL


# --------------------------------------------------------------------------- #
# Content Lambda: generate_enhanced_content, real payload bytes.
# --------------------------------------------------------------------------- #
class _Sent(Exception):
    pass


def _content_payload(session: dict, matched: bool) -> dict:
    sent = []
    client = MagicMock()

    def _invoke(**kwargs):
        sent.append(kwargs["payload"])
        raise _Sent()

    client.invoke_agent_runtime.side_effect = _invoke
    module = {"name": "campus_coach", "enabled": True, "sessions_available": True,
              "campus_coach_sessions": [dict(session)]}
    if matched:
        module["matched_session"] = dict(session)
        module["match_score"] = 0.9
    activity = {"id": "act1", "name": "Seuil", "type": "Run", "distance": 10000,
                "moving_time": 3300, "start_date_local": "2026-10-14T18:00:00Z",
                "description": "bonnes sensations"}
    with patch.dict(os.environ, {"CONTENT_GENERATION_AGENT_ARN": "arn:test"}), \
            patch.object(content, "boto3") as boto, \
            patch.object(content, "_get_campus_context", return_value=None):
        boto.client.return_value = client
        try:
            content.generate_enhanced_content(activity, "u1", [module])
        except Exception:  # noqa: BLE001 - the fake runtime always raises after capture
            pass
    assert len(sent) == 1
    return json.loads(sent[0])


class TestContentPayload:
    def test_structured_twin_gives_identical_payload_matched(self):
        legacy = _content_payload(_session(False), matched=True)
        twin = _content_payload(_session(True), matched=True)
        assert json.dumps(legacy, sort_keys=True) == json.dumps(twin, sort_keys=True)
        assert twin["campus_coach_session"][0]["intervals"]
        assert twin["active_modules"][0]["matched_session"]["intervals"]
        text = json.dumps(twin)
        for key in ("pace_kind", "pace_slug", "pace_value_s", "estimated_paces"):
            assert key not in text, key

    def test_structured_twin_gives_identical_payload_context_only(self):
        legacy = _content_payload(_session(False), matched=False)
        twin = _content_payload(_session(True), matched=False)
        assert json.dumps(legacy, sort_keys=True) == json.dumps(twin, sort_keys=True)


# --------------------------------------------------------------------------- #
# Shared coach context (text plan block): reads explicit keys only.
# --------------------------------------------------------------------------- #
class TestCoachContextPlanText:
    def test_structured_twin_gives_identical_text(self):
        from shared.coach_context import format_campus_sessions
        legacy = format_campus_sessions([_session(False)])
        twin = format_campus_sessions([_session(True)])
        assert legacy == twin
        assert "4:20/km" in twin  # not trivially empty
