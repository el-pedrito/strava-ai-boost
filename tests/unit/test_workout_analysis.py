"""Unit tests for workout_analysis module — pure functions"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from processing.workout_analysis import (
    _parse_pace_mmss,
    _classify_by_pace_zones,
    classify_workout_from_laps,
)


class TestParsePaceMmss:
    """Test pace string parsing"""

    def test_standard_pace(self):
        assert _parse_pace_mmss('5:30') == pytest.approx(5.5)

    def test_exact_minute(self):
        assert _parse_pace_mmss('6:00') == 6.0

    def test_sub_5(self):
        assert _parse_pace_mmss('4:45') == pytest.approx(4.75)

    def test_float_input(self):
        assert _parse_pace_mmss('5.5') == 5.5

    def test_invalid_returns_zero(self):
        assert _parse_pace_mmss('abc') == 0.0

    def test_none_returns_zero(self):
        assert _parse_pace_mmss(None) == 0.0

    def test_integer_string(self):
        assert _parse_pace_mmss('6') == 6.0


class TestClassifyByPaceZones:
    """Test pace zone matching"""

    @pytest.fixture
    def pace_zones(self):
        return {
            'recovery': {'min': '6:30', 'max': '7:30'},
            'ef': {'min': '5:30', 'max': '6:20'},
            'tempo': {'min': '4:30', 'max': '5:00'},
            'interval': {'min': '3:30', 'max': '4:15'},
        }

    def test_recovery_zone(self, pace_zones):
        result = _classify_by_pace_zones(7.0, pace_zones)
        assert result is not None
        assert result['type'] == 'recovery_run'

    def test_ef_zone(self, pace_zones):
        result = _classify_by_pace_zones(5.75, pace_zones)
        assert result is not None
        assert result['type'] == 'steady_easy_run'

    def test_tempo_zone(self, pace_zones):
        result = _classify_by_pace_zones(4.75, pace_zones)
        assert result is not None
        assert result['type'] == 'tempo'

    def test_interval_zone(self, pace_zones):
        result = _classify_by_pace_zones(3.9, pace_zones)
        assert result is not None
        assert result['type'] == 'intervals'

    def test_no_match_too_slow(self, pace_zones):
        result = _classify_by_pace_zones(9.0, pace_zones)
        assert result is None

    def test_no_match_too_fast(self, pace_zones):
        result = _classify_by_pace_zones(3.0, pace_zones)
        assert result is None

    def test_empty_zones(self):
        result = _classify_by_pace_zones(5.5, {})
        assert result is None

    def test_invalid_zone_format(self):
        result = _classify_by_pace_zones(5.5, {'ef': 'not-a-dict'})
        assert result is None


class TestClassifyByPointZones:
    """Campus single-value zones (min == max): nearest pace within 10 s/km."""

    @pytest.fixture
    def campus_zones(self):
        return {
            'ef': {'min': '5:46', 'max': '6:16'},
            'tempo': {'min': '5:15', 'max': '5:15'},
            'allure_semi': {'min': '4:35', 'max': '4:35'},
            'seuil_30': {'min': '4:11', 'max': '4:11'},
        }

    def test_exact_single_value_matches(self, campus_zones):
        assert _classify_by_pace_zones(5.25, campus_zones)['type'] == 'tempo'

    def test_within_10s_matches(self, campus_zones):
        # 5:23 /km is 8 s slower than tempo 5:15.
        assert _classify_by_pace_zones(5 + 23 / 60, campus_zones)['type'] == 'tempo'

    def test_exactly_10s_matches(self, campus_zones):
        # 5:25 /km is exactly 10 s from tempo 5:15.
        assert _classify_by_pace_zones(5 + 25 / 60, campus_zones)['type'] == 'tempo'

    def test_beyond_10s_does_not_match(self, campus_zones):
        # 4:55 /km is 20 s from both tempo and semi.
        assert _classify_by_pace_zones(4 + 55 / 60, campus_zones) is None

    def test_nearest_single_value_wins(self, campus_zones):
        # 4:38 /km: 3 s from semi 4:35, far from tempo.
        result = _classify_by_pace_zones(4 + 38 / 60, campus_zones)
        assert result['label'] == _classify_by_pace_zones(4 + 35 / 60, campus_zones)['label']
        assert result['type'] != 'tempo'

    def test_real_range_beats_a_near_single_value(self):
        zones = {'ef': {'min': '5:30', 'max': '6:00'}, 'tempo': {'min': '5:28', 'max': '5:28'}}
        # 5:31 is inside EF and 3 s from tempo: the range wins.
        assert _classify_by_pace_zones(5 + 31 / 60, zones)['type'] == 'steady_easy_run'

    def test_ef_range_still_matches(self, campus_zones):
        assert _classify_by_pace_zones(6.0, campus_zones)['type'] == 'steady_easy_run'


def _make_laps(paces_min_km):
    """Helper: create laps from pace values (min/km).
    Converts pace to average_speed (m/s) for the Strava lap format.
    """
    laps = []
    for i, pace in enumerate(paces_min_km):
        avg_speed = 1000 / (pace * 60) if pace > 0 else 0  # m/s
        laps.append({
            'lap_index': i + 1,
            'name': f'Lap {i + 1}',
            'distance': 1000,
            'moving_time': int(pace * 60),
            'elapsed_time': int(pace * 60),
            'average_speed': avg_speed,
            'max_speed': avg_speed * 1.1,
            'average_heartrate': 150,
            'max_heartrate': 165,
            'pace_zone': 3,
            'total_elevation_gain': 5,
        })
    return laps


class TestClassifyWorkoutFromLaps:
    """Test workout classification from laps data"""

    def test_too_few_laps_returns_unknown(self):
        laps = _make_laps([5.0])
        result = classify_workout_from_laps(laps)
        assert result['type'] == 'unknown'
        assert result['confidence'] == 0

    def test_empty_laps(self):
        result = classify_workout_from_laps([])
        assert result['type'] == 'unknown'

    def test_none_laps(self):
        result = classify_workout_from_laps(None)
        assert result['type'] == 'unknown'

    def test_steady_run(self):
        paces = [5.5, 5.6, 5.4, 5.5, 5.5, 5.6, 5.4, 5.5, 5.5, 5.4]
        laps = _make_laps(paces)
        result = classify_workout_from_laps(laps)
        assert result['type'] == 'steady'
        assert result['confidence'] > 0.5

    def test_intervals_detected(self):
        paces = [4.0, 6.5, 4.0, 6.5, 4.0, 6.5, 4.0, 6.5, 4.0, 6.5]
        laps = _make_laps(paces)
        result = classify_workout_from_laps(laps)
        assert result['type'] == 'intervals'

    def test_progression_detected(self):
        paces = [6.5, 6.4, 6.3, 5.7, 5.6, 5.5, 5.1, 5.0, 4.9, 4.8]
        laps = _make_laps(paces)
        result = classify_workout_from_laps(laps)
        assert result['type'] == 'progression'

    def test_steady_with_pace_zones(self):
        paces = [5.8, 5.9, 5.7, 5.8, 5.9, 5.7, 5.8, 5.9, 5.8, 5.7]
        laps = _make_laps(paces)
        pace_zones = {'ef': {'min': '5:30', 'max': '6:20'}}
        result = classify_workout_from_laps(laps, pace_zones=pace_zones)
        assert result['type'] == 'steady_easy_run'

    def test_stats_present(self):
        paces = [5.5, 5.6, 5.4, 5.5, 5.5, 5.6, 5.4, 5.5, 5.5, 5.4]
        laps = _make_laps(paces)
        result = classify_workout_from_laps(laps)
        assert 'stats' in result
        assert 'avg_pace' in result['stats']
        assert 'pace_std' in result['stats']
        assert 'laps_analyzed' in result['stats']
