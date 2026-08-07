"""Unit tests for the HR zone reduction used to stop the content agent from
inventing a zone number (root cause of the 'zone 1' bug on a real Zone 2 run)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from processing.activity_fetcher import compute_hr_zone


# Real Strava distribution_buckets for activity 19644900213 (a Zone 2 run):
# 2351s spent in 125-155 bpm, avg HR 141. Strava's own zones say Zone 2, while
# the content agent had narrated "zone 1".
REAL_Z2_BUCKETS = [
    {"min": 0, "max": 124, "time": 64.0},
    {"min": 125, "max": 155, "time": 2351.0},
    {"min": 156, "max": 170, "time": 0.0},
    {"min": 171, "max": 185, "time": 0.0},
    {"min": 186, "max": -1, "time": 0.0},
]


class TestComputeHrZone:
    def test_real_activity_is_zone_2(self):
        result = compute_hr_zone(REAL_Z2_BUCKETS)
        assert result is not None
        assert result["zone"] == 2
        assert "Zone 2" in result["label"]
        assert result["dominant_pct"] == 97.3
        assert result["range_bpm"] == [125, 155]

    def test_dominant_zone_is_by_time_not_first_nonzero(self):
        buckets = [
            {"min": 0, "max": 124, "time": 100.0},
            {"min": 125, "max": 155, "time": 50.0},
            {"min": 156, "max": 170, "time": 900.0},  # dominant
            {"min": 171, "max": 185, "time": 20.0},
        ]
        result = compute_hr_zone(buckets)
        assert result["zone"] == 3

    def test_none_input(self):
        assert compute_hr_zone(None) is None

    def test_empty_input(self):
        assert compute_hr_zone([]) is None

    def test_all_zero_time_returns_none(self):
        buckets = [{"min": 0, "max": 124, "time": 0.0}, {"min": 125, "max": 155, "time": 0.0}]
        assert compute_hr_zone(buckets) is None

    def test_malformed_bucket_returns_none(self):
        assert compute_hr_zone(["not-a-dict"]) is None

    def test_missing_time_treated_as_zero(self):
        buckets = [{"min": 0, "max": 124}, {"min": 125, "max": 155, "time": 10.0}]
        result = compute_hr_zone(buckets)
        assert result["zone"] == 2
