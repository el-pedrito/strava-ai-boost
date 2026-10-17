"""Lot C: deterministic morning brief — light thresholds, same-kind HRV baseline,
stale/missing signals, weather (mocked), next Campus session, coordinates."""
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("COACHING_SESSIONS_TABLE", "test-coaching-sessions")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from webhooks import morning_brief as mb


def _day(d, **fields):
    item = {"sk": f"day#{d}"}
    for k, v in fields.items():
        item[k] = Decimal(str(v)) if isinstance(v, (int, float)) else v
    return item


class TestStatusThresholds:
    def test_hrv_drop_warn_and_bad(self):
        assert mb._status_for("hrv", 100.0, 100.0) == "ok"
        assert mb._status_for("hrv", 91.0, 100.0) == "warn"   # -9%
        assert mb._status_for("hrv", 84.0, 100.0) == "bad"    # -16%

    def test_resting_hr_rise(self):
        assert mb._status_for("resting_hr", 48.0, 48.0) == "ok"
        assert mb._status_for("resting_hr", 52.0, 48.0) == "warn"   # +4
        assert mb._status_for("resting_hr", 55.0, 48.0) == "bad"    # +7

    def test_sleep_drop(self):
        base = 28000.0
        assert mb._status_for("sleep", 28000.0, base) == "ok"
        assert mb._status_for("sleep", base - 3700, base) == "warn"
        assert mb._status_for("sleep", base - 7300, base) == "bad"

    def test_form_negative(self):
        assert mb._status_for("form", -5.0, None) == "ok"
        assert mb._status_for("form", -16.0, None) == "warn"
        assert mb._status_for("form", -26.0, None) == "bad"


class TestLight:
    def test_red_when_any_bad(self):
        sigs = [{"status": "ok"}, {"status": "bad"}, {"status": "warn"}]
        assert mb._light(sigs) == "red"

    def test_orange_when_warn_no_bad(self):
        assert mb._light([{"status": "ok"}, {"status": "warn"}]) == "orange"

    def test_green_all_ok(self):
        assert mb._light([{"status": "ok"}, {"status": "ok"}]) == "green"

    def test_unknown_when_all_stale(self):
        assert mb._light([{"status": "missing"}]) == "unknown"
        assert mb._light([]) == "unknown"


class TestHrvSameKind:
    def test_baseline_uses_only_latest_kind(self):
        # latest day is sdnn; rmssd rows must be excluded from the series.
        days = [
            _day("2026-10-10", hrv=40.0, hrv_kind="rmssd"),
            _day("2026-10-14", hrv=60.0, hrv_kind="sdnn"),
            _day("2026-10-15", hrv=62.0, hrv_kind="sdnn"),
        ]
        series = mb._hrv_series_same_kind(days)
        assert [v for _, v in series] == [60.0, 62.0]


class TestStale:
    def test_signal_older_than_j_minus_1_is_missing(self):
        today = date(2026, 10, 17)
        series = [("2026-10-15", 48.0)]  # 2 days old -> stale
        sig = mb._signal("resting_hr", series, today, 60)
        assert sig["status"] == "missing"
        assert sig["as_of"] == "2026-10-15"

    def test_fresh_signal_not_missing(self):
        today = date(2026, 10, 17)
        series = [("2026-10-14", 48.0), ("2026-10-16", 48.0)]
        sig = mb._signal("resting_hr", series, today, 60)
        assert sig["status"] != "missing"


class TestCoords:
    def test_rounds_to_tenth(self):
        with patch.object(mb, "BRIEF_LOCATION", "48.8566,2.3522"):
            assert mb._coords() == (48.9, 2.4)

    def test_absent_is_none(self):
        with patch.object(mb, "BRIEF_LOCATION", ""):
            assert mb._coords() is None


class TestWeather:
    def test_no_coords_no_weather(self):
        with patch.object(mb, "BRIEF_LOCATION", ""):
            assert mb._weather(date(2026, 10, 17)) == []

    def test_two_slots_parsed(self):
        today = date(2026, 10, 17)
        payload = {
            "hourly": {
                "time": [f"{today}T07:00", f"{today}T18:00"],
                "temperature_2m": [6.0, 14.0],
                "wind_speed_10m": [20.0, 10.0],
                "precipitation": [0.0, 0.2],
            }
        }
        resp = MagicMock(status_code=200)
        resp.json.return_value = payload
        with patch.object(mb, "BRIEF_LOCATION", "48.8,2.3"), \
             patch.object(mb.requests, "get", return_value=resp):
            weather = mb._weather(today)
        assert [w["slot"] for w in weather] == ["07:00", "18:00"]
        assert weather[0]["temp_c"] == 6.0
        assert weather[1]["precip_mm"] == 0.2

    def test_timeout_returns_empty(self):
        import requests
        with patch.object(mb, "BRIEF_LOCATION", "48.8,2.3"), \
             patch.object(mb.requests, "get", side_effect=requests.exceptions.Timeout()):
            assert mb._weather(date(2026, 10, 17)) == []


class TestNextCampusSession:
    def test_first_not_done_in_order(self):
        sessions = [
            {"training_index": 0, "title": "EF", "training_type": "Endurance",
             "expected_duration_min": 45, "local_status": "done"},
            {"training_index": 1, "title": "Allure 21km", "training_type": "Intensity",
             "expected_duration_min": 64},
        ]
        table = MagicMock()
        table.query.return_value = {"Items": sessions}
        with patch("boto3.resource") as res:
            res.return_value.Table.return_value = table
            now = datetime(2026, 10, 17, 6, 30, tzinfo=timezone.utc)
            nxt = mb._next_campus_session(now)
        assert nxt["title"] == "Allure 21km"
        assert nxt["duration_min"] == 64


class TestBuildBrief:
    def test_build_brief_shape(self):
        today = date(2026, 10, 17)
        now = datetime(2026, 10, 17, 6, 30, tzinfo=timezone.utc)
        days = [
            _day("2026-10-16", restingHR=48, hrvSDNN=60.0, hrv=60.0, hrv_kind="sdnn",
                 sleepSecs=27000, ctl=10.0, atl=28.0),
            _day("2026-10-15", restingHR=47, hrvSDNN=61.0, hrv=61.0, hrv_kind="sdnn",
                 sleepSecs=28000, ctl=11.0, atl=27.0),
        ]
        table = MagicMock()
        table.query.return_value = {"Items": days}
        with patch.object(mb, "_weather", return_value=[]), \
             patch.object(mb, "_next_campus_session", return_value=None):
            brief = mb.build_brief(table, "42", today, now)
        assert brief["sk"] == "brief#2026-10-17"
        assert brief["date"] == "2026-10-17"
        assert brief["light"] in ("green", "orange", "red", "unknown")
        keys = {s["key"] for s in brief["signals"]}
        assert {"hrv", "resting_hr", "sleep", "form"} <= keys
        # hrv signal carries its kind
        hrv = next(s for s in brief["signals"] if s["key"] == "hrv")
        assert hrv["kind"] == "sdnn"

    def test_missing_lists_absent_signals(self):
        today = date(2026, 10, 17)
        now = datetime(2026, 10, 17, 6, 30, tzinfo=timezone.utc)
        days = [_day("2026-10-16", restingHR=48)]  # only resting hr present
        table = MagicMock()
        table.query.return_value = {"Items": days}
        with patch.object(mb, "_weather", return_value=[]), \
             patch.object(mb, "_next_campus_session", return_value=None):
            brief = mb.build_brief(table, "42", today, now)
        assert "hrv" in brief["missing"]
        assert "sleep" in brief["missing"]
        assert "form" in brief["missing"]
