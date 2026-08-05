"""Unit tests for compute_session_volume — code-authoritative strength tonnage.

These tests pin the WP5 contract: figures are computed in code (never estimated
by the LLM), ``sets_detail`` is authoritative, and any figure that cannot be
computed is signalled rather than silently under-reported. No per-case fixture indirection is
used, per repo convention for tests/unit/.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared.strength_volume import compute_session_volume  # noqa: E402


def _assert_coherent(result: dict) -> None:
    """The aggregate must always equal the sum of its per-exercise breakdown.

    WHY: the whole point is auditable figures; if totals diverge from the
    breakdown the doubling or an exclusion has silently corrupted a number.
    """
    assert result['total_sets'] == sum(e['sets'] for e in result['per_exercise'])
    assert result['total_reps'] == sum(e['reps'] for e in result['per_exercise'])
    assert result['volume_kg'] == round(
        sum(e['volume_kg'] for e in result['per_exercise']), 2
    )


class TestRealSession:
    """The mandatory reference session (04/08, body weight 92 kg)."""

    def test_reference_session_totals(self) -> None:
        parsed_sets = [
            {'exercise': 'Tractions', 'sets': 3, 'reps': 10, 'weight_kg': None},
            {'exercise': 'Tirage vertical', 'sets_detail': [
                {'reps': 10, 'weight_kg': 75},
                {'reps': 10, 'weight_kg': 80},
                {'reps': 10, 'weight_kg': 80},
            ]},
            {'exercise': 'Tirage horizontal', 'sets_detail': [
                {'reps': 10, 'weight_kg': 80},
                {'reps': 8, 'weight_kg': 90},
                {'reps': 8, 'weight_kg': 90},
            ]},
            {'exercise': 'Développé machine', 'sets': 4, 'reps': 8, 'weight_kg': 110},
            {'exercise': 'Élévations latérales', 'sets': 3, 'reps': 10, 'weight_kg': 15},
            {'exercise': 'Face pull', 'sets': 3, 'reps': 10, 'weight_kg': 35},
            {'exercise': 'Triceps corde', 'sets': 3, 'reps': 10, 'weight_kg': 50},
            {'exercise': 'Curl biceps corde', 'sets': 3, 'reps': 10, 'weight_kg': 50},
        ]

        result = compute_session_volume(parsed_sets, body_weight_kg=92)

        assert result['total_sets'] == 25
        assert result['total_reps'] == 238
        assert result['volume_kg'] == 15370
        assert result['body_weight_kg_used'] == 92
        assert result['volume_kg_incomplete'] is False
        assert result['excluded_exercises'] == []
        _assert_coherent(result)


class TestFlatSchema:
    """Older rows carry only the flat sets/reps/weight schema."""

    def test_flat_4x10_at_80(self) -> None:
        result = compute_session_volume(
            [{'exercise': 'Développé machine', 'sets': 4, 'reps': 10, 'weight_kg': 80}],
            body_weight_kg=80,
        )
        assert result['total_sets'] == 4
        assert result['total_reps'] == 40
        assert result['volume_kg'] == 3200
        assert result['volume_kg_incomplete'] is False
        _assert_coherent(result)

    def test_sets_detail_takes_precedence_over_flat(self) -> None:
        # Flat fields would give 3x10x80 = 2400; sets_detail is authoritative.
        result = compute_session_volume(
            [{
                'exercise': 'Tirage horizontal',
                'sets': 3, 'reps': 10, 'weight_kg': 80,
                'sets_detail': [
                    {'reps': 10, 'weight_kg': 80},
                    {'reps': 8, 'weight_kg': 90},
                    {'reps': 8, 'weight_kg': 90},
                ],
            }],
            body_weight_kg=92,
        )
        assert result['total_reps'] == 26
        assert result['volume_kg'] == 2240
        _assert_coherent(result)


class TestBodyweight:
    """Bodyweight resolution and the weighted (lesté) case."""

    def test_pure_bodyweight_tractions(self) -> None:
        result = compute_session_volume(
            [{'exercise': 'Tractions', 'sets': 1, 'reps': 4, 'weight_kg': None}],
            body_weight_kg=92,
        )
        assert result['total_reps'] == 4
        assert result['volume_kg'] == 368  # 4 x 92
        assert result['volume_kg_incomplete'] is False
        _assert_coherent(result)

    def test_weighted_pullups_add_plate_to_bodyweight(self) -> None:
        # "tractions +10kg" -> (92 + 10) per rep.
        result = compute_session_volume(
            [{'exercise': 'Tractions', 'sets': 3, 'reps': 10, 'weight_kg': 10}],
            body_weight_kg=92,
        )
        assert result['volume_kg'] == 3060  # 3 x 10 x 102
        assert result['volume_kg_incomplete'] is False
        _assert_coherent(result)

    def test_bodyweight_without_body_weight_is_incomplete_not_crash(self) -> None:
        result = compute_session_volume(
            [{'exercise': 'Tractions', 'sets': 3, 'reps': 10, 'weight_kg': None}],
            body_weight_kg=None,
        )
        # reps are known and still counted; only the tonnage is unknown.
        assert result['total_sets'] == 3
        assert result['total_reps'] == 30
        assert result['volume_kg'] == 0
        assert result['volume_kg_incomplete'] is True
        assert 'Tractions' in result['excluded_exercises']
        assert result['body_weight_kg_used'] is None
        _assert_coherent(result)


class TestExclusions:
    """Missing figures must be signalled, never silently absorbed."""

    def test_reps_null_series_excluded(self) -> None:
        result = compute_session_volume(
            [{'exercise': 'Développé machine', 'sets_detail': [
                {'reps': 10, 'weight_kg': 80},
                {'reps': None, 'weight_kg': 80},
            ]}],
            body_weight_kg=80,
        )
        # The null-reps series contributes nothing at all.
        assert result['total_sets'] == 1
        assert result['total_reps'] == 10
        assert result['volume_kg'] == 800
        assert result['volume_kg_incomplete'] is True
        assert 'Développé machine' in result['excluded_exercises']
        _assert_coherent(result)

    def test_unknown_exercise_unknown_load_incomplete(self) -> None:
        result = compute_session_volume(
            [{'exercise': 'Mouvement inconnu', 'sets': 3, 'reps': 10, 'weight_kg': None}],
            body_weight_kg=92,
        )
        # Reps known and counted, but load unknown -> excluded from tonnage.
        assert result['total_reps'] == 30
        assert result['volume_kg'] == 0
        assert result['volume_kg_incomplete'] is True
        assert 'Mouvement inconnu' in result['excluded_exercises']
        _assert_coherent(result)


class TestUnilateral:
    """Unilateral exercises count both sides, coherently across all figures."""

    def test_unilateral_doubles_sets_reps_volume(self) -> None:
        result = compute_session_volume(
            [{
                'exercise': 'Tirage horizontal unilatéral machine',
                'sets': 4, 'reps': 10, 'weight_kg': 30,
            }],
            body_weight_kg=92,
        )
        assert result['total_sets'] == 8
        assert result['total_reps'] == 80
        assert result['volume_kg'] == 2400  # 8 x 10 x 30
        assert result['per_exercise'][0]['unilateral'] is True
        # sets x reps-per-set x load must still equal the displayed volume.
        assert result['per_exercise'][0]['sets'] * 10 * 30 == result['volume_kg']
        _assert_coherent(result)

    def test_bilateral_exercise_not_doubled(self) -> None:
        result = compute_session_volume(
            [{'exercise': 'Tirage horizontal', 'sets': 4, 'reps': 10, 'weight_kg': 30}],
            body_weight_kg=92,
        )
        assert result['total_sets'] == 4
        assert result['per_exercise'][0]['unilateral'] is False
        _assert_coherent(result)


class TestEdgeCases:
    """Empty / degenerate inputs must not crash and must not fabricate figures."""

    def test_empty_session(self) -> None:
        result = compute_session_volume([], body_weight_kg=92)
        assert result['total_sets'] == 0
        assert result['total_reps'] == 0
        assert result['volume_kg'] == 0
        assert result['volume_kg_incomplete'] is False
        assert result['excluded_exercises'] == []
        assert result['body_weight_kg_used'] == 92

    def test_none_parsed_sets(self) -> None:
        result = compute_session_volume(None, body_weight_kg=None)
        assert result['total_sets'] == 0
        assert result['volume_kg'] == 0
        assert result['body_weight_kg_used'] is None
