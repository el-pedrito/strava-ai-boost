"""GET /plan/workouts (dashboard_api branch + api/plan_workouts.py).

Plan: docs/design/apple-watch-workouts.md section C. One def per case (AGENTS.md).
"""

import base64
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from aws_lambda_powertools.metrics import MetricUnit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from api import plan_workouts  # noqa: E402
from api.dashboard_api import handler  # noqa: E402

OWNER = "424242"
# Far in the future, so the week filter never depends on the date the suite runs.
FUTURE_WEEK_MS = Decimal(int(datetime(2099, 1, 5, tzinfo=timezone.utc).timestamp() * 1000))


def _ms(year, month, day):
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp() * 1000)


def _week_ms(offset):
    """``week_date`` of the week ``offset`` weeks after FUTURE_WEEK_MS."""
    return FUTURE_WEEK_MS + Decimal(offset * 7 * 24 * 3600 * 1000)


def _row(session_id="1_0", week_iso="2099-W02", index=0, week_ms=FUTURE_WEEK_MS, **extra):
    row = {
        "session_date": f"week-{week_iso}",
        "session_id": session_id,
        "week_date": week_ms,
        "week_date_iso": week_iso,
        "training_index": Decimal(index),
        "title": "Blocs allure semi",
        "sport": "road",
        "training_type": "Intensity",
        "expected_duration_min": Decimal(64),
        "is_future": True,
        "provider_status": "todo",
        "intervals": [
            {"type": "warm-up", "duration": "15 min", "pace": "EF (5:57/km)"},
            {"type": "block", "repeat": Decimal(4), "exercises": [
                {"type": "work", "duration": "9 min", "pace": "Semi Marathon (4:28/km)"},
                {"type": "recovery", "duration": "2 min", "pace": "Lent (11:14/km)"},
            ]},
            {"type": "cool-down", "duration": "5 min", "pace": "EF (5:57/km)"},
        ],
    }
    row.update(extra)
    return row


def _event(claim=OWNER, method="GET", path="/plan/workouts", query=None):
    claims = {} if claim is None else {"custom:strava_id": claim}
    return {
        "httpMethod": method,
        "path": path,
        "queryStringParameters": query,
        "requestContext": {"authorizer": {"claims": claims}},
    }


@pytest.fixture
def owner_env(monkeypatch):
    monkeypatch.setenv("CAMPUS_OWNER_STRAVA_ID", OWNER)


@pytest.fixture
def table():
    mock_table = MagicMock()
    mock_table.scan.return_value = {"Items": [_row()]}
    with patch("api.dashboard_api.dynamodb") as mock_dynamo:
        mock_dynamo.Table.return_value = mock_table
        yield mock_table


def _body(response):
    return json.loads(response["body"])


def _assert_no_store(response):
    assert response["headers"]["Cache-Control"] == "no-store"
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"


@pytest.fixture
def plan_logs(caplog):
    """Every record of the dashboard_api logger.

    The Powertools logger does not propagate to the root logger, so caplog's handler
    is attached to it directly.
    """
    std_logger = logging.getLogger("dashboard_api")
    std_logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG, logger="dashboard_api")
    try:
        yield caplog
    finally:
        std_logger.removeHandler(caplog.handler)


def _all_log_text(caplog):
    # Formatted text (with any traceback) plus every record attribute (Powertools extras).
    return caplog.text + "\n".join(repr(vars(record)) for record in caplog.records)


class TestOwnerGate:
    def test_missing_claim_is_403(self, owner_env, table):
        response = handler(_event(claim=None), None)
        assert response["statusCode"] == 403
        _assert_no_store(response)
        table.scan.assert_not_called()

    def test_empty_claim_is_403(self, owner_env, table):
        response = handler(_event(claim=""), None)
        assert response["statusCode"] == 403
        table.scan.assert_not_called()

    def test_wrong_owner_is_403(self, owner_env, table):
        response = handler(_event(claim="999"), None)
        assert response["statusCode"] == 403
        _assert_no_store(response)
        table.scan.assert_not_called()

    def test_env_unset_is_403_even_with_a_claim(self, monkeypatch, table):
        monkeypatch.delenv("CAMPUS_OWNER_STRAVA_ID", raising=False)
        response = handler(_event(claim=OWNER), None)
        assert response["statusCode"] == 403
        _assert_no_store(response)
        table.scan.assert_not_called()

    def test_env_empty_is_403_with_empty_claim(self, monkeypatch, table):
        monkeypatch.setenv("CAMPUS_OWNER_STRAVA_ID", "")
        response = handler(_event(claim=""), None)
        assert response["statusCode"] == 403

    def test_default_user_id_is_not_a_fallback(self, owner_env, table):
        # DEFAULT_USER_ID may equal the owner: a request without the claim stays 403.
        with patch("api.dashboard_api.DEFAULT_USER_ID", OWNER):
            response = handler(_event(claim=None), None)
        assert response["statusCode"] == 403


class TestRouting:
    def test_post_is_not_routed(self, owner_env, table):
        response = handler(_event(method="POST"), None)
        assert response["statusCode"] == 404
        table.scan.assert_not_called()

    def test_sub_path_is_not_routed(self, owner_env, table):
        response = handler(_event(path="/plan/workouts/extra"), None)
        assert response["statusCode"] == 404

    def test_bad_query_param_does_not_hit_the_dashboard_validator(self, owner_env, table):
        # The route takes no parameter and is dispatched before validate_request, so a
        # junk ?limit= cannot produce a 400 without no-store.
        response = handler(_event(query={"limit": "abc"}), None)
        assert response["statusCode"] == 200
        _assert_no_store(response)
        assert _body(response)["count"] == 1

    def test_bad_query_param_from_non_owner_is_403_no_store(self, owner_env, table):
        response = handler(_event(claim="999", query={"limit": "abc"}), None)
        assert response["statusCode"] == 403
        _assert_no_store(response)


class TestOwnerResponse:
    def test_200_envelope_and_item(self, owner_env, table):
        response = handler(_event(), None)
        assert response["statusCode"] == 200
        _assert_no_store(response)
        body = _body(response)
        assert set(body) == {"workouts", "count", "truncated", "timestamp"}
        assert body["count"] == 1
        assert body["truncated"] is False
        item = body["workouts"][0]
        assert item["session_id"] == "1_0"
        assert item["week_iso"] == "2099-W02"
        assert item["training_index"] == 0
        assert item["title"] == "Blocs allure semi"
        assert item["training_type"] == "Intensity"
        assert item["sport"] == "road"
        assert item["duration_min"] == 64
        assert item["encodable"] is True
        assert item["reason_code"] is None
        assert item["summary"].startswith("WU 15'")
        assert item["filename"].endswith(".workout")
        data = base64.b64decode(item["workout_b64"])
        assert 0 < len(data) <= 8192

    def test_scan_filters_current_or_future(self, owner_env, table):
        handler(_event(), None)
        kwargs = table.scan.call_args.kwargs
        assert kwargs["FilterExpression"] == "is_current_week = :t OR is_future = :t"
        assert kwargs["ExpressionAttributeValues"] == {":t": True}

    def test_non_encodable_item_has_reason_and_no_bytes(self, owner_env, table):
        table.scan.return_value = {"Items": [_row(sport="swim")]}
        item = _body(handler(_event(), None))["workouts"][0]
        assert item["encodable"] is False
        assert item["reason_code"] == "unsupported_sport"
        assert "workout_b64" not in item
        assert item["summary"] is None

    def test_missing_duration_is_null(self, owner_env, table):
        row = _row()
        del row["expected_duration_min"]
        table.scan.return_value = {"Items": [row]}
        assert _body(handler(_event(), None))["workouts"][0]["duration_min"] is None

    def test_does_not_use_module_cache(self, owner_env, table):
        handler(_event(), None)
        handler(_event(), None)
        assert table.scan.call_count == 2


class TestPagination:
    def test_two_pages_are_merged(self, owner_env, table):
        table.scan.side_effect = [
            {"Items": [_row("1_0", index=0)], "LastEvaluatedKey": {"session_id": "1_0"}},
            {"Items": [_row("1_1", index=1)]},
        ]
        body = _body(handler(_event(), None))
        assert [w["session_id"] for w in body["workouts"]] == ["1_0", "1_1"]
        assert table.scan.call_count == 2
        assert "ExclusiveStartKey" not in table.scan.call_args_list[0].kwargs
        assert table.scan.call_args_list[1].kwargs["ExclusiveStartKey"] == {"session_id": "1_0"}


class TestWeekBoundary:
    """Monday 00:00 UTC of the ISO week of TODAY IN PARIS, in CET and CEST."""

    def test_sunday_2330_paris_cet_is_previous_week(self):
        # 2026-01-11 is a Sunday; 23:30 CET = 22:30 UTC.
        now = datetime(2026, 1, 11, 22, 30, tzinfo=timezone.utc)
        assert plan_workouts.current_week_start_ms(now) == _ms(2026, 1, 5)

    def test_monday_0030_paris_cet_is_new_week(self):
        # 00:30 CET on Monday 2026-01-12 is still Sunday 23:30 in UTC.
        now = datetime(2026, 1, 11, 23, 30, tzinfo=timezone.utc)
        assert plan_workouts.current_week_start_ms(now) == _ms(2026, 1, 12)

    def test_sunday_2330_paris_cest_is_previous_week(self):
        # 2026-07-12 is a Sunday; 23:30 CEST = 21:30 UTC.
        now = datetime(2026, 7, 12, 21, 30, tzinfo=timezone.utc)
        assert plan_workouts.current_week_start_ms(now) == _ms(2026, 7, 6)

    def test_monday_0030_paris_cest_is_new_week(self):
        # 00:30 CEST on Monday 2026-07-13 is Sunday 22:30 UTC.
        now = datetime(2026, 7, 12, 22, 30, tzinfo=timezone.utc)
        assert plan_workouts.current_week_start_ms(now) == _ms(2026, 7, 13)

    def test_paris_date_matches_iana_over_two_years(self):
        zoneinfo = pytest.importorskip("zoneinfo")
        try:
            paris = zoneinfo.ZoneInfo("Europe/Paris")
        except zoneinfo.ZoneInfoNotFoundError:
            pytest.skip("no IANA database on this machine")
        from datetime import timedelta
        instant = datetime(2025, 1, 1, tzinfo=timezone.utc)
        while instant < datetime(2027, 1, 1, tzinfo=timezone.utc):
            assert plan_workouts.paris_date(instant) == instant.astimezone(paris).date(), instant
            instant += timedelta(minutes=30)

    def test_rows_of_previous_week_are_dropped(self):
        table = MagicMock()
        table.scan.return_value = {"Items": [
            _row("prev", week_iso="2026-W02", week_ms=Decimal(_ms(2026, 1, 5))),
            _row("cur", week_iso="2026-W03", week_ms=Decimal(_ms(2026, 1, 12))),
        ]}
        monday_0030_cet = datetime(2026, 1, 11, 23, 30, tzinfo=timezone.utc)
        payload, _ = plan_workouts.build_plan_workouts(table, monday_0030_cet)
        assert [w["session_id"] for w in payload["workouts"]] == ["cur"]

    def test_rows_of_current_week_are_kept_on_sunday_night(self):
        table = MagicMock()
        table.scan.return_value = {"Items": [
            _row("prev", week_iso="2026-W02", week_ms=Decimal(_ms(2026, 1, 5))),
        ]}
        sunday_2330_cet = datetime(2026, 1, 11, 22, 30, tzinfo=timezone.utc)
        payload, _ = plan_workouts.build_plan_workouts(table, sunday_2330_cet)
        assert [w["session_id"] for w in payload["workouts"]] == ["prev"]


class TestRowFilters:
    def _ids(self, table, rows):
        table.scan.return_value = {"Items": rows}
        return [w["session_id"] for w in _body(handler(_event(), None))["workouts"]]

    def test_done_is_dropped(self, owner_env, table):
        assert self._ids(table, [_row("a", local_status="done"), _row("b", index=1)]) == ["b"]

    def test_matched_activity_counts_as_done(self, owner_env, table):
        assert self._ids(table, [_row("a", matched_activity_id="123"), _row("b", index=1)]) == ["b"]

    def test_skip_is_dropped(self, owner_env, table):
        assert self._ids(table, [_row("a", local_status="skip"), _row("b", index=1)]) == ["b"]

    def test_todo_is_kept(self, owner_env, table):
        assert self._ids(table, [_row("a", provider_status="todo")]) == ["a"]

    def test_athlete_context_is_skipped(self, owner_env, table):
        context = {"session_date": "athlete-context", "session_id": OWNER, "is_future": True,
                   "week_date": FUTURE_WEEK_MS, "intervals": [{"type": "work"}]}
        assert self._ids(table, [context, _row("a")]) == ["a"]

    def test_rows_without_intervals_are_skipped(self, owner_env, table):
        no_key = _row("a")
        del no_key["intervals"]
        assert self._ids(table, [no_key, _row("b", intervals=[]), _row("c", index=2)]) == ["c"]

    def test_row_without_week_date_is_skipped(self, owner_env, table):
        row = _row("a")
        del row["week_date"]
        assert self._ids(table, [row, _row("b", index=1)]) == ["b"]

    def test_sort_week_then_numeric_index_then_session_id(self, owner_env, table):
        rows = [
            _row("w3", week_iso="2099-W03", index=0, week_ms=_week_ms(1)),
            _row("i10", index=10),
            _row("i2b", index=2),
            _row("i2a", index=2),
        ]
        assert self._ids(table, rows) == ["i2a", "i2b", "i10", "w3"]

    def test_sort_uses_numeric_week_date_not_the_iso_string(self, owner_env, table):
        # week_date_iso is optional: a missing one must not move the row to the front.
        later_without_iso = _row("later", index=0, week_ms=_week_ms(1))
        del later_without_iso["week_date_iso"]
        earlier = _row("earlier", week_iso="2099-W02", index=5)
        assert self._ids(table, [later_without_iso, earlier]) == ["earlier", "later"]


class TestIsolationAndMetrics:
    def test_a_raising_mapper_marks_only_its_item_internal(self, owner_env, table):
        real = plan_workouts.campus_workout.map_session
        boom_row = _row("boom", index=0)

        def flaky(row, *args, **kwargs):
            if row["session_id"] == "boom":
                raise RuntimeError("unexpected")
            return real(row, *args, **kwargs)

        table.scan.return_value = {"Items": [boom_row, _row("ok", index=1)]}
        with patch.object(plan_workouts.campus_workout, "map_session", side_effect=flaky), \
                patch("api.dashboard_api.metrics.add_metric") as add_metric:
            response = handler(_event(), None)
        assert response["statusCode"] == 200
        boom, ok = _body(response)["workouts"]
        assert boom["encodable"] is False and boom["reason_code"] == "internal"
        assert "workout_b64" not in boom
        assert ok["encodable"] is True
        add_metric.assert_any_call(name="WorkoutMapFailed", unit=MetricUnit.Count, value=1)

    def test_mapper_counters_are_emitted(self, owner_env, table):
        row = _row(intervals=[{"type": "work", "duration": "45 min", "pace": "Inconnue (5:00/km)"}])
        table.scan.return_value = {"Items": [row]}
        with patch("api.dashboard_api.metrics.add_metric") as add_metric:
            handler(_event(), None)
        add_metric.assert_any_call(name="WorkoutUnknownPaceFamily", unit=MetricUnit.Count, value=1)

    def test_lone_surrogate_row_does_not_fail_its_neighbour(self, owner_env, table):
        # Real malformed text, no mock: an unpaired UTF-16 surrogate cannot be encoded
        # to UTF-8, which used to make the byte-ceiling serialization raise (500).
        bad = _row("bad\ud800", index=0, title="Blocs \udc80 semi",
                   training_type="Int\ud800", sport="road")
        bad["week_date_iso"] = "2099-W02\udfff"
        table.scan.return_value = {"Items": [bad, _row("ok", index=1)]}
        response = handler(_event(), None)
        assert response["statusCode"] == 200
        response["body"].encode("utf-8")
        first, second = _body(response)["workouts"]
        assert first["title"] == "Blocs ? semi"
        assert first["session_id"] == "bad?"
        assert first["week_iso"] == "2099-W02?"
        assert first["training_type"] == "Int?"
        assert second["session_id"] == "ok"
        assert second["encodable"] is True

    def test_lone_surrogate_payload_is_utf8_serializable(self):
        table = MagicMock()
        table.scan.return_value = {"Items": [_row("a", title="\ud83d"), _row("b", index=1)]}
        payload, _ = plan_workouts.build_plan_workouts(table, datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert payload["count"] == 2
        json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def test_non_bytes_mapper_payload_marks_only_its_item_internal(self, owner_env, table):
        # base64 of a non-bytes payload raises TypeError: inside the per-row boundary.
        real = plan_workouts.campus_workout.map_session

        def bad_bytes(row, *args, **kwargs):
            if row["session_id"] == "boom":
                return plan_workouts.campus_workout.MapResult(True, bytes="not bytes", summary="x")
            return real(row, *args, **kwargs)

        table.scan.return_value = {"Items": [_row("boom", index=0), _row("ok", index=1)]}
        with patch.object(plan_workouts.campus_workout, "map_session", side_effect=bad_bytes), \
                patch("api.dashboard_api.metrics.add_metric") as add_metric:
            response = handler(_event(), None)
        assert response["statusCode"] == 200
        boom, ok = _body(response)["workouts"]
        assert boom["encodable"] is False and boom["reason_code"] == "internal"
        assert boom["session_id"] == "boom"
        assert "workout_b64" not in boom
        assert ok["encodable"] is True
        add_metric.assert_any_call(name="WorkoutMapFailed", unit=MetricUnit.Count, value=1)

    def test_scan_error_is_500_with_no_store(self, owner_env, table):
        table.scan.side_effect = ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "x"}}, "Scan"
        )
        response = handler(_event(), None)
        assert response["statusCode"] == 500
        _assert_no_store(response)
        assert _body(response)["error"] == "Internal server error"


class TestTruncation:
    def test_item_ceiling_keeps_nearest_weeks(self, owner_env, table):
        rows = [_row(f"far_{i:03d}", week_iso="2099-W09", index=i, week_ms=_week_ms(7)) for i in range(10)]
        rows += [_row(f"near_{i:03d}", index=i) for i in range(plan_workouts.MAX_ITEMS)]
        table.scan.return_value = {"Items": rows}
        body = _body(handler(_event(), None))
        assert body["count"] == plan_workouts.MAX_ITEMS
        assert body["truncated"] is True
        assert all(w["week_iso"] == "2099-W02" for w in body["workouts"])

    def test_exactly_at_ceiling_is_not_truncated(self, owner_env, table):
        table.scan.return_value = {"Items": [_row(f"{i:03d}", index=i) for i in range(plan_workouts.MAX_ITEMS)]}
        body = _body(handler(_event(), None))
        assert body["count"] == plan_workouts.MAX_ITEMS
        assert body["truncated"] is False

    def test_byte_ceiling(self, owner_env, table, monkeypatch):
        # One session per week, so the byte ceiling falls between weeks.
        table.scan.return_value = {"Items": [_row(f"{i}", week_ms=_week_ms(i)) for i in range(5)]}
        one = len(json.dumps(_body(handler(_event(), None))["workouts"][0], ensure_ascii=False).encode())
        monkeypatch.setattr(plan_workouts, "MAX_RESPONSE_BYTES", int(one * 2.5))
        body = _body(handler(_event(), None))
        assert body["count"] == 2
        assert body["truncated"] is True

    def test_item_ceiling_never_cuts_a_week(self, owner_env, table, monkeypatch):
        # 3 + 3 sessions with room for 4: the second week is dropped whole.
        monkeypatch.setattr(plan_workouts, "MAX_ITEMS", 4)
        rows = [_row(f"a{i}", index=i) for i in range(3)]
        rows += [_row(f"b{i}", week_iso="2099-W03", index=i, week_ms=_week_ms(1)) for i in range(3)]
        table.scan.return_value = {"Items": rows}
        body = _body(handler(_event(), None))
        assert [w["session_id"] for w in body["workouts"]] == ["a0", "a1", "a2"]
        assert body["truncated"] is True

    def test_byte_ceiling_never_cuts_a_week(self, owner_env, table, monkeypatch):
        rows = [_row("a0", index=0)]
        rows += [_row(f"b{i}", week_iso="2099-W03", index=i, week_ms=_week_ms(1)) for i in range(2)]
        table.scan.return_value = {"Items": rows}
        one = len(json.dumps(_body(handler(_event(), None))["workouts"][0], ensure_ascii=False).encode())
        # Room for two items, but the second week holds two: only the first week stays.
        monkeypatch.setattr(plan_workouts, "MAX_RESPONSE_BYTES", int(one * 2.5))
        body = _body(handler(_event(), None))
        assert [w["session_id"] for w in body["workouts"]] == ["a0"]
        assert body["truncated"] is True


class TestNoCampusTextInLogs:
    SECRET_TITLE = "Titre-prive-zq81"  # pragma: allowlist secret

    def test_mapper_error_quoting_the_title_is_not_logged(self, owner_env, table, plan_logs):
        def leaky(row, *args, **kwargs):
            raise RuntimeError(f"cannot map {row['title']}")

        table.scan.return_value = {"Items": [_row(title=self.SECRET_TITLE)]}
        with patch.object(plan_workouts.campus_workout, "map_session", side_effect=leaky):
            response = handler(_event(), None)
        assert response["statusCode"] == 200
        text = _all_log_text(plan_logs)
        # Non-vacuous: the capture really sees this branch's records.
        assert "Plan workouts listed" in text
        assert self.SECRET_TITLE not in text
        assert "cannot map" not in text

    def test_scan_error_message_is_not_logged(self, owner_env, table, plan_logs):
        table.scan.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": f"bad item {self.SECRET_TITLE}"}},
            "Scan",
        )
        response = handler(_event(), None)
        assert response["statusCode"] == 500
        _assert_no_store(response)
        text = _all_log_text(plan_logs)
        assert "Plan workouts failed" in text
        assert "ClientError" in text
        assert self.SECRET_TITLE not in text
        assert "ValidationException" not in text
