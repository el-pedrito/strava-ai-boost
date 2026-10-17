"""HRV from Intervals.icu: Apple Watch only gives SDNN, sent by HealthFit to `hrvSDNN`."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from processing.activity_fetcher import (  # noqa: E402
    _compute_wellness_trends,
    _wellness_hrv,
    _wellness_hrv_kind,
)


def test_sdnn_used_when_rmssd_missing():
    w = {'hrv': None, 'hrvSDNN': 48.0, 'restingHR': 45}
    assert _wellness_hrv(w) == 48.0
    assert _wellness_hrv_kind(w) == 'sdnn'


def test_rmssd_wins_when_present():
    w = {'hrv': 62.0, 'hrvSDNN': 48.0}
    assert _wellness_hrv(w) == 62.0
    assert _wellness_hrv_kind(w) == 'rmssd'


def test_no_hrv_at_all():
    assert _wellness_hrv({'restingHR': 45}) is None
    assert _wellness_hrv_kind({'restingHR': 45}) is None


def test_trends_include_sdnn_series():
    history = [{'id': f'2026-10-{d:02d}', 'hrvSDNN': 40.0 + d} for d in range(1, 17)]
    trends = _compute_wellness_trends(history, '2026-10-16')
    assert trends['hrv']['current'] == 56.0
    assert trends['hrv']['data_points'] == 16
