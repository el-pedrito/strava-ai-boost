"""Unit tests for shared.wellness helpers (HRV kind + activity-window reader)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from shared.wellness import (
    wellness_hrv,
    wellness_hrv_kind,
    in_activity_window,
    _activity_local_date,
)


class TestWellnessHrv:
    def test_rmssd_present_wins(self):
        assert wellness_hrv({"hrv": 42.0, "hrvSDNN": 60.0}) == 42.0
        assert wellness_hrv_kind({"hrv": 42.0, "hrvSDNN": 60.0}) == "rmssd"

    def test_sdnn_fallback(self):
        assert wellness_hrv({"hrvSDNN": 60.0}) == 60.0
        assert wellness_hrv_kind({"hrvSDNN": 60.0}) == "sdnn"

    def test_none_when_absent(self):
        assert wellness_hrv({}) is None
        assert wellness_hrv_kind({}) is None


class TestActivityLocalDate:
    def test_top_level_start_date_local(self):
        assert _activity_local_date({"start_date_local": "2026-10-11T07:00:00"}) == "2026-10-11"

    def test_from_activity_data_json_string(self):
        item = {"activity_data_json": json.dumps({"start_date_local": "2026-10-11T07:00:00"})}
        assert _activity_local_date(item) == "2026-10-11"

    def test_falls_back_to_start_date(self):
        assert _activity_local_date({"start_date": "2026-10-11T07:00:00Z"}) == "2026-10-11"

    def test_created_at_is_ignored(self):
        # created_at is reset on reprocess; it must never be used as the date.
        assert _activity_local_date({"created_at": "2026-10-11T07:00:00"}) == ""


class TestInActivityWindow:
    def test_inside_window(self):
        item = {"start_date_local": "2026-10-11T07:00:00"}
        assert in_activity_window(item, "2026-10-01", "2026-10-31") is True

    def test_before_window(self):
        item = {"start_date_local": "2026-09-30T07:00:00"}
        assert in_activity_window(item, "2026-10-01", "2026-10-31") is False

    def test_after_window(self):
        item = {"start_date_local": "2026-11-01T07:00:00"}
        assert in_activity_window(item, "2026-10-01", "2026-10-31") is False

    def test_unbounded_since(self):
        item = {"start_date_local": "2020-01-01T07:00:00"}
        assert in_activity_window(item, "", "2026-10-31") is True

    def test_no_date_excluded(self):
        assert in_activity_window({"created_at": "2026-10-11"}, "2026-10-01", "2026-10-31") is False
