"""Unit tests for streams_analysis module — pure functions"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from processing.streams_analysis import (
    _parse_pace_mmss,
    _classify_by_pace_zones,
    classify_workout_from_streams,
    detect_workout_phases,
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


class TestClassifyWorkoutFromStreams:
    """Test workout classification from block data"""

    def _make_blocks(self, paces):
        """Helper: create blocks from pace values"""
        return [{'pace_min_km': p, 'hr_bpm': 150} for p in paces]

    def test_too_few_blocks_returns_unknown(self):
        blocks = self._make_blocks([5.0, 5.1])
        result = classify_workout_from_streams(blocks)
        assert result['type'] == 'unknown'
        assert result['confidence'] == 0

    def test_steady_run(self):
        # Low variability = steady
        paces = [5.5, 5.6, 5.4, 5.5, 5.5, 5.6, 5.4, 5.5, 5.5, 5.4]
        blocks = self._make_blocks(paces)
        result = classify_workout_from_streams(blocks)
        assert result['type'] == 'steady'
        assert result['confidence'] > 0.5

    def test_intervals_detected(self):
        # Alternating fast/slow = intervals
        paces = [4.0, 6.5, 4.0, 6.5, 4.0, 6.5, 4.0, 6.5, 4.0, 6.5]
        blocks = self._make_blocks(paces)
        result = classify_workout_from_streams(blocks)
        assert result['type'] == 'intervals'

    def test_progression_detected(self):
        # Negative split: std > 0.40, first third avg > last third avg by > 0.5
        paces = [6.5, 6.4, 6.3, 5.7, 5.6, 5.5, 5.1, 5.0, 4.9, 4.8]
        blocks = self._make_blocks(paces)
        result = classify_workout_from_streams(blocks)
        assert result['type'] == 'progression'

    def test_steady_with_pace_zones(self):
        paces = [5.8, 5.9, 5.7, 5.8, 5.9, 5.7, 5.8, 5.9, 5.8, 5.7]
        blocks = self._make_blocks(paces)
        pace_zones = {'ef': {'min': '5:30', 'max': '6:20'}}
        result = classify_workout_from_streams(blocks, pace_zones=pace_zones)
        assert result['type'] == 'steady_easy_run'

    def test_stats_present(self):
        paces = [5.5, 5.6, 5.4, 5.5, 5.5, 5.6, 5.4, 5.5, 5.5, 5.4]
        blocks = self._make_blocks(paces)
        result = classify_workout_from_streams(blocks)
        assert 'stats' in result
        assert 'avg_pace' in result['stats']
        assert 'pace_std' in result['stats']
        assert 'blocks_analyzed' in result['stats']

    def test_outlier_filtering(self):
        # Mostly steady with a couple extreme outliers (warmup/cooldown)
        paces = [8.0, 5.5, 5.4, 5.5, 5.6, 5.5, 5.4, 5.5, 5.6, 9.0]
        blocks = self._make_blocks(paces)
        result = classify_workout_from_streams(blocks)
        # Outliers should be filtered, core is steady
        assert result['type'] in ('steady', 'fartlek')

    def test_zero_paces_excluded(self):
        paces = [0, 5.5, 5.4, 5.5, 0, 5.6, 5.5, 5.4, 5.5, 0]
        blocks = self._make_blocks(paces)
        result = classify_workout_from_streams(blocks)
        assert result['type'] != 'unknown'

    def test_empty_blocks(self):
        result = classify_workout_from_streams([])
        assert result['type'] == 'unknown'


class TestDetectWorkoutPhases:
    """Test workout phase detection"""

    def test_empty_returns_empty(self):
        assert detect_workout_phases(None) == []
        assert detect_workout_phases({}) == []
        assert detect_workout_phases({'blocks': []}) == []

    def test_single_phase_steady(self):
        blocks = [
            {'pace_min_km': 5.5, 'hr_bpm': 150, 'duration_s': 60},
            {'pace_min_km': 5.6, 'hr_bpm': 152, 'duration_s': 60},
            {'pace_min_km': 5.4, 'hr_bpm': 148, 'duration_s': 60},
            {'pace_min_km': 5.5, 'hr_bpm': 150, 'duration_s': 60},
        ]
        phases = detect_workout_phases({'blocks': blocks})
        # Steady pace → should be 1 phase
        assert len(phases) == 1
        assert phases[0]['blocks_count'] == 4

    def test_multiple_phases_intervals(self):
        blocks = []
        for _ in range(3):
            # Fast phase
            for _ in range(3):
                blocks.append({'pace_min_km': 4.0, 'hr_bpm': 170, 'duration_s': 30})
            # Slow phase
            for _ in range(3):
                blocks.append({'pace_min_km': 6.5, 'hr_bpm': 130, 'duration_s': 30})

        phases = detect_workout_phases({'blocks': blocks})
        # Should detect alternating fast/slow phases
        assert len(phases) >= 3

    def test_short_phases_filtered(self):
        # Phases < 0.5min are dropped from output
        blocks = [
            {'pace_min_km': 5.5, 'hr_bpm': 150, 'duration_s': 120},
            {'pace_min_km': 5.4, 'hr_bpm': 152, 'duration_s': 120},
            {'pace_min_km': 5.5, 'hr_bpm': 150, 'duration_s': 120},
            # Short burst that creates its own phase
            {'pace_min_km': 3.5, 'hr_bpm': 180, 'duration_s': 15},
            {'pace_min_km': 5.5, 'hr_bpm': 150, 'duration_s': 120},
        ]
        phases = detect_workout_phases({'blocks': blocks})
        # The 15s burst phase should be filtered out (< 0.5min)
        for phase in phases:
            assert phase['duration_min'] >= 0.5

    def test_phase_format(self):
        blocks = [
            {'pace_min_km': 5.5, 'hr_bpm': 150, 'duration_s': 120},
            {'pace_min_km': 5.4, 'hr_bpm': 152, 'duration_s': 120},
            {'pace_min_km': 5.6, 'hr_bpm': 148, 'duration_s': 120},
        ]
        phases = detect_workout_phases({'blocks': blocks})
        assert len(phases) >= 1
        phase = phases[0]
        assert 'duration_min' in phase
        assert 'avg_pace' in phase
        assert '/km' in phase['avg_pace']
        assert 'avg_hr' in phase
        assert 'blocks_count' in phase

    def test_invalid_paces_skipped(self):
        blocks = [
            {'pace_min_km': 0, 'hr_bpm': 0, 'duration_s': 60},
            {'pace_min_km': 20, 'hr_bpm': 0, 'duration_s': 60},  # > 15 = invalid
            {'pace_min_km': 5.5, 'hr_bpm': 150, 'duration_s': 120},
            {'pace_min_km': 5.4, 'hr_bpm': 152, 'duration_s': 120},
            {'pace_min_km': 5.5, 'hr_bpm': 150, 'duration_s': 120},
        ]
        phases = detect_workout_phases({'blocks': blocks})
        # Invalid blocks should be skipped
        assert len(phases) >= 1
