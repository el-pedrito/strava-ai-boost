"""Pure tonnage computation for WeightTraining sessions.

WHY this module exists: the Coach LLM used to state strength figures it invented
(sets, reps, tonnage), and every figure left to the model was wrong in
production. The validated principle is that every number must be computed in
code and handed to the model. This module is that computation for a single
strength session: total sets, total reps, and lifted volume = Σ(reps × load).

Design invariants (all from docs/design/coach-figures-integrity.md §8):

- ``sets_detail`` is AUTHORITATIVE. The flat ``sets/reps/weight_kg`` schema
  cannot represent "10x80 8x90 8x90" and under-reported one real session's
  tonnage by 33%. When ``sets_detail`` is present, each entry is one set
  actually performed with its own reps and its own load. When it is missing
  (older rows), it is reconstructed from the flat fields.
- A missing figure is NEVER silently absorbed. Under-reporting without saying so
  would be the same class of lie this project set out to fix, so any exercise
  whose volume cannot be fully computed sets ``volume_kg_incomplete`` and is
  named in ``excluded_exercises``.
- ``body_weight_kg_used`` is always returned. The athlete's body weight drifts,
  and without recording which value was used, comparing two sessions' tonnage
  months apart becomes wrong with no way to detect it. There is NEVER a default
  body weight: an arbitrary 70 kg would produce a plausible, false number.
"""

from typing import Any, Dict, List, Optional

from shared.strength_exercises import (
    BODYWEIGHT_EXERCISES,
    UNILATERAL_EXERCISES,
    canonicalize_exercise_name,
)


def _reconstruct_sets_detail(
    sets: Optional[int],
    reps: Optional[int],
    weight_kg: Optional[float],
) -> List[Dict[str, Any]]:
    """Rebuild a per-set list from the flat schema for older rows.

    WHY: rows written before ``sets_detail`` existed carry only aggregate
    ``sets/reps/weight_kg``. Expanding them into one uniform entry per set lets
    the rest of the computation treat old and new rows identically instead of
    branching on schema shape at every step.
    """
    try:
        set_count = int(sets) if sets is not None else 0
    except (TypeError, ValueError):
        set_count = 0
    if set_count <= 0:
        return []
    return [{'reps': reps, 'weight_kg': weight_kg} for _ in range(set_count)]


def _coerce_optional_number(value: Any) -> Optional[float]:
    """Return ``value`` as a float, or ``None`` if it is absent/unparseable.

    WHY: a null reps or null load must stay null (it drives an explicit
    exclusion), so a failed conversion must not collapse to 0 and fabricate a
    figure.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_set_load(
    canonical: str,
    per_set_weight: Optional[float],
    body_weight_kg: Optional[float],
) -> Optional[float]:
    """Resolve the load lifted for one set, or ``None`` if it cannot be known.

    WHY the split: ``weight_kg = null`` is ambiguous. Only exercises listed in
    ``BODYWEIGHT_EXERCISES`` may resolve a null to body weight; every other null
    is an unknown load and must be reported as excluded, never valued at zero.
    Weighted variants ("tractions +10kg") add the extra plate on top of body
    weight, so a bodyweight exercise that carries a ``weight_kg`` sums the two.
    """
    coefficient = BODYWEIGHT_EXERCISES.get(canonical)
    if coefficient is not None:
        # Bodyweight movement: needs the athlete's body weight to be valued.
        if body_weight_kg is None:
            return None
        added_load = per_set_weight if per_set_weight is not None else 0.0
        return body_weight_kg * coefficient + added_load
    # Non-bodyweight movement: a null load is unknown, not zero.
    return per_set_weight


def compute_session_volume(
    parsed_sets: Optional[List[Dict[str, Any]]],
    body_weight_kg: Optional[float],
) -> Dict[str, Any]:
    """Compute code-authoritative strength figures for one session.

    Args:
        parsed_sets: list of ``{exercise, sets, reps, weight_kg, sets_detail}``
            as produced by the strength extractor. ``sets_detail`` (a list of
            ``{reps, weight_kg}``, one per real set) is authoritative when
            present; otherwise the flat fields are used.
        body_weight_kg: the athlete's body weight for this session, or ``None``.
            NEVER defaulted: bodyweight movements are simply marked incomplete
            when it is absent rather than valued with a fabricated weight.

    Returns:
        ``{total_sets, total_reps, volume_kg, body_weight_kg_used,
        per_exercise, volume_kg_incomplete, excluded_exercises}``. The identity
        ``total_sets == Σ per_exercise.sets`` (and likewise reps and volume)
        always holds, so the aggregate can be audited against its breakdown.
    """
    total_sets = 0
    total_reps = 0
    volume_kg = 0.0
    volume_incomplete = False
    per_exercise: List[Dict[str, Any]] = []
    excluded_exercises: List[str] = []

    for entry in parsed_sets or []:
        canonical = canonicalize_exercise_name(entry.get('exercise', ''))
        sides = UNILATERAL_EXERCISES.get(canonical, 1)
        is_unilateral = sides > 1

        sets_detail = entry.get('sets_detail')
        if not sets_detail:
            sets_detail = _reconstruct_sets_detail(
                entry.get('sets'),
                entry.get('reps'),
                entry.get('weight_kg'),
            )

        exercise_sets = 0
        exercise_reps = 0
        exercise_volume = 0.0
        exercise_incomplete = False

        for raw_set in sets_detail:
            reps = _coerce_optional_number(raw_set.get('reps'))
            if reps is None:
                # reps null -> the whole series is excluded and signalled; it
                # contributes to no count, only to the incomplete flag.
                exercise_incomplete = True
                continue

            exercise_sets += 1
            exercise_reps += int(reps)

            load = _resolve_set_load(
                canonical,
                _coerce_optional_number(raw_set.get('weight_kg')),
                body_weight_kg,
            )
            if load is None:
                # Load unknown: reps still count, but this set's tonnage is
                # excluded rather than guessed.
                exercise_incomplete = True
                continue
            exercise_volume += int(reps) * load

        # Expand both sides together so sets x reps x load still equals volume.
        exercise_sets *= sides
        exercise_reps *= sides
        exercise_volume *= sides

        if exercise_incomplete:
            volume_incomplete = True
            if canonical and canonical not in excluded_exercises:
                excluded_exercises.append(canonical)

        per_exercise.append({
            'exercise': canonical,
            'sets': exercise_sets,
            'reps': exercise_reps,
            'volume_kg': round(exercise_volume, 2),
            'unilateral': is_unilateral,
            'volume_incomplete': exercise_incomplete,
        })

        total_sets += exercise_sets
        total_reps += exercise_reps
        volume_kg += exercise_volume

    return {
        'total_sets': total_sets,
        'total_reps': total_reps,
        'volume_kg': round(volume_kg, 2),
        'body_weight_kg_used': body_weight_kg,
        'per_exercise': per_exercise,
        'volume_kg_incomplete': volume_incomplete,
        'excluded_exercises': excluded_exercises,
    }
