"""Exercise -> muscle-group map for the Coach strength insights.

Pure data + lookup. No I/O, no DynamoDB. The aggregation in
``strength_insights.py`` turns one logged set into fractional "sets per muscle
group" through :func:`lookup_exercise`.

Design decisions (all traced to the reviewed plan)
--------------------------------------------------
- The lookup key is ``_normalization_key(canonicalize_exercise_name(name))`` from
  ``strength_exercises.py``, so case/accent variants and known aliases all resolve
  to one entry.
- Credit per set is expressed directly as ``group_weights`` (primary = 1.0,
  secondary = 0.5). Expressing weights rather than two lists keeps the honest
  split of mixed machine lifts representable.
- ``pattern`` is one of ``push|pull|legs|core|other`` and drives the push/pull
  balance (never derived from muscle totals).
- ``e1rm`` is ``True`` only for compound, plate/barbell lifts where an Epley
  estimate is meaningful and the stored load is comparable. Isolation, cable,
  bodyweight, unilateral, hold, conditioning and dumbbell lifts are ``False``.
- ``explosivite`` is a conditioning bucket shown as its own bar, not a muscle.
- ``autre`` collects unmapped movements, surfaced so gaps stay visible.
- A ``Développé machine`` row mixes a chest press and a shoulder press in stored
  history (pre-existing parser bug, out of this read-only scope); it is split
  pecs/delts/triceps at 0.5 each, flagged ``mixed`` and kept out of e1RM/records.

Muscle groups (10, FR labels): pectoraux, dos, epaules, biceps, triceps,
quadriceps, ischios, fessiers, mollets, abdos. Plus non-muscle buckets
``explosivite`` and ``autre``.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple

from .strength_exercises import (
    CANONICAL_STRENGTH_EXERCISES,
    canonicalize_exercise_name,
    _normalization_key,
)

# The ten real muscle groups, plus the two non-muscle buckets.
MUSCLE_GROUPS: tuple = (
    'pectoraux', 'dos', 'epaules', 'biceps', 'triceps',
    'quadriceps', 'ischios', 'fessiers', 'mollets', 'abdos',
)
EXPLOSIVITE = 'explosivite'
AUTRE = 'autre'

PUSH = 'push'
PULL = 'pull'
LEGS = 'legs'
CORE = 'core'
OTHER = 'other'


class MuscleMapping(NamedTuple):
    """Resolved mapping for one exercise.

    ``group_weights`` maps a muscle group (or ``explosivite``) to its fractional
    set credit. ``explosivite`` moves may also credit real groups at 0.5 (e.g. a
    kettlebell swing credits fessiers/ischios 0.5 while showing on the
    explosivite bar).
    """
    group_weights: Dict[str, float]
    pattern: str
    e1rm: bool
    explosivite: bool = False
    autre: bool = False
    # Reason surfaced in ``unmapped_exercises`` when ``autre`` is True.
    autre_reason: str = 'unknown'
    mixed: bool = False


def _m(primary, secondary=(), *, pattern, e1rm, explosivite=False):
    """Build group_weights from primary (1.0) and secondary (0.5) lists."""
    weights: Dict[str, float] = {}
    for g in primary:
        weights[g] = 1.0
    for g in secondary:
        weights.setdefault(g, 0.5)
    return MuscleMapping(
        group_weights=weights,
        pattern=pattern,
        e1rm=e1rm,
        explosivite=explosivite,
    )


# Final e1RM set (PLAN-v4 §2): compound plate/barbell lifts only. Dumbbell presses
# are excluded because "/c"/per-side notation and dumbbell loads are not comparable.
_E1RM_NAMES = frozenset({
    'Développé couché',
    'Développé incliné',
    'Développé décliné',
    'Développé militaire',
    'Presse épaules',
    'Tirage vertical machine',
    'Tirage vertical prise neutre',
    'Tirage vertical neutre serré',
    'Tirage horizontal',
    'Tirage horizontal machine',
    'Squat',
    'Presse à cuisses',
    'Hip thrust',
    'Soulevé de terre',
})

# Mixed exercises: a single stored name conflates two movements. Excluded from
# e1RM and from the records board; the chart keeps the series with a note.
# The value is an i18n note key for the frontend.
mixed_exercises: Dict[str, str] = {
    'Développé machine': 'mixed_chest_shoulder_machine',
    # Follow-up (separate, not this change): ask the athlete whether "dm machine"
    # is actually Presse épaules; if so add the alias + prompt mapping and
    # re-extract history. Until then the series is non-comparable.
}


def _entry(name: str) -> MuscleMapping:
    """Build the mapping for a canonical name, applying e1RM/mixed rules."""
    base = _RAW_MAP[name]
    e1rm = (name in _E1RM_NAMES) and not base.mixed
    return base._replace(e1rm=e1rm)


# Raw per-exercise definitions (before the e1RM/mixed gate is applied by _entry).
# pattern/explosivite/mixed are authoritative here; e1rm is recomputed in _entry.
_RAW_MAP: Dict[str, MuscleMapping] = {
    # --- Pulls ---
    'Tractions': _m(['dos'], ['biceps'], pattern=PULL, e1rm=False),
    'Face pull': _m(['epaules'], ['dos'], pattern=PULL, e1rm=False),
    'Pull-over': _m(['dos'], ['pectoraux'], pattern=PULL, e1rm=False),
    'Tirage vertical machine': _m(['dos'], ['biceps'], pattern=PULL, e1rm=True),
    'Tirage vertical prise neutre': _m(['dos'], ['biceps'], pattern=PULL, e1rm=True),
    'Tirage vertical neutre serré': _m(['dos'], ['biceps'], pattern=PULL, e1rm=True),
    'Tirage horizontal': _m(['dos'], ['biceps', 'epaules'], pattern=PULL, e1rm=True),
    'Tirage horizontal machine': _m(['dos'], ['biceps', 'epaules'], pattern=PULL, e1rm=True),
    'Tirage horizontal unilatéral machine': _m(['dos'], ['biceps', 'epaules'], pattern=PULL, e1rm=False),
    'Curl barre': _m(['biceps'], pattern=PULL, e1rm=False),
    'Curl biceps': _m(['biceps'], pattern=PULL, e1rm=False),
    'Curl biceps rotation': _m(['biceps'], pattern=PULL, e1rm=False),
    'Curl marteau': _m(['biceps'], pattern=PULL, e1rm=False),
    'Curl biceps à la corde': _m(['biceps'], pattern=PULL, e1rm=False),
    # --- Pushes ---
    'Développé couché': _m(['pectoraux'], ['triceps', 'epaules'], pattern=PUSH, e1rm=True),
    'Développé couché haltères': _m(['pectoraux'], ['triceps', 'epaules'], pattern=PUSH, e1rm=False),
    'Développé incliné': _m(['pectoraux'], ['triceps', 'epaules'], pattern=PUSH, e1rm=True),
    'Développé incliné haltères': _m(['pectoraux'], ['triceps', 'epaules'], pattern=PUSH, e1rm=False),
    'Développé décliné': _m(['pectoraux'], ['triceps', 'epaules'], pattern=PUSH, e1rm=True),
    'Développé militaire': _m(['epaules'], ['triceps'], pattern=PUSH, e1rm=True),
    'Développé militaire haltères': _m(['epaules'], ['triceps'], pattern=PUSH, e1rm=False),
    'Développé militaire assis': _m(['epaules'], ['triceps'], pattern=PUSH, e1rm=False),
    'Développé machine': MuscleMapping(
        group_weights={'pectoraux': 0.5, 'epaules': 0.5, 'triceps': 0.5},
        pattern=PUSH, e1rm=False, mixed=True,
    ),
    'Presse épaules': _m(['epaules'], ['triceps'], pattern=PUSH, e1rm=True),
    'Dips': _m(['pectoraux', 'triceps'], ['epaules'], pattern=PUSH, e1rm=False),
    'Pompes': _m(['pectoraux'], ['triceps', 'epaules'], pattern=PUSH, e1rm=False),
    'Élévations latérales': _m(['epaules'], pattern=OTHER, e1rm=False),
    'Élévations latérales haltères assis': _m(['epaules'], pattern=OTHER, e1rm=False),
    'Triceps à la corde': _m(['triceps'], pattern=PUSH, e1rm=False),
    'Écartés pectoraux à la poulie': _m(['pectoraux'], pattern=PUSH, e1rm=False),
    # --- Legs ---
    'Squat': _m(['quadriceps'], ['fessiers'], pattern=LEGS, e1rm=True),
    'Fentes': _m(['quadriceps', 'fessiers'], ['ischios'], pattern=LEGS, e1rm=False),
    'Presse à cuisses': _m(['quadriceps'], ['fessiers'], pattern=LEGS, e1rm=True),
    'Leg curl': _m(['ischios'], pattern=LEGS, e1rm=False),
    'Leg extension': _m(['quadriceps'], pattern=LEGS, e1rm=False),
    'Hip thrust': _m(['fessiers'], ['ischios'], pattern=LEGS, e1rm=True),
    'Soulevé de terre': _m(['ischios', 'fessiers'], ['dos', 'quadriceps'], pattern=LEGS, e1rm=True),
    'Mollets': _m(['mollets'], pattern=LEGS, e1rm=False),
    # --- Core / holds ---
    'Gainage': _m(['abdos'], pattern=CORE, e1rm=False),
    'Crunch': _m(['abdos'], pattern=CORE, e1rm=False),
    # --- Campus / extra names (resolved via canonicalisation or stems) ---
    'Mollet statique': _m(['mollets'], pattern=LEGS, e1rm=False),
    'Gainage frontal': _m(['abdos'], pattern=CORE, e1rm=False),
    'Gainage latéral': _m(['abdos'], pattern=CORE, e1rm=False),
    'Gainage ventral': _m(['abdos'], pattern=CORE, e1rm=False),
    'Soulevé de terre jambe tendue': _m(['ischios', 'fessiers'], pattern=LEGS, e1rm=False),
    'Montée sur banc': _m(['quadriceps', 'fessiers'], pattern=LEGS, e1rm=False),
    'Pont fessier unilatéral': _m(['fessiers'], ['ischios'], pattern=LEGS, e1rm=False),
    'Chaise': _m(['quadriceps'], pattern=LEGS, e1rm=False),
    # Conditioning / ballistic -> explosivite bar; swings also credit the hip
    # extensors at 0.5 (shown in the tooltip).
    'Saut groupé': MuscleMapping(group_weights={}, pattern=OTHER, e1rm=False, explosivite=True),
    'Bond sur place': MuscleMapping(group_weights={}, pattern=OTHER, e1rm=False, explosivite=True),
    'Swing avec charge': MuscleMapping(
        group_weights={'fessiers': 0.5, 'ischios': 0.5}, pattern=OTHER, e1rm=False, explosivite=True,
    ),
    'Swing ketle': MuscleMapping(
        group_weights={'fessiers': 0.5, 'ischios': 0.5}, pattern=OTHER, e1rm=False, explosivite=True,
    ),
    # Flexion tibiale -> no muscle group in our ten; tibialis is "autre".
    'Flexion tibiale': MuscleMapping(
        group_weights={}, pattern=LEGS, e1rm=False, autre=True, autre_reason='unknown',
    ),
    # Flexion de genou: ambiguous (knee flexion could be hamstrings) -> listed as
    # to_confirm until the athlete confirms (PLAN-v3 §4).
    'Flexion de genou': MuscleMapping(
        group_weights={}, pattern=LEGS, e1rm=False, autre=True, autre_reason='to_confirm',
    ),
}


# Build the resolved map keyed by the normalisation key.
EXERCISE_MUSCLES: Dict[str, MuscleMapping] = {}
_NAME_BY_KEY: Dict[str, str] = {}
for _name in _RAW_MAP:
    _key = _normalization_key(canonicalize_exercise_name(_name))
    EXERCISE_MUSCLES[_key] = _entry(_name)
    _NAME_BY_KEY[_key] = _name


# Stem fallback for future Campus names (PLAN-v3 §4, PLAN-v4 §6). Matched by
# containment on the normalised key, longest stem first; exact key wins first.
# "mollet" is kept for hold names such as "Mollet statique" (rep-based calf moves
# are already renamed to "Mollets" by ppg_history_sets, so this is for holds).
_STEM_FALLBACKS: tuple = (
    ('pont fessier', 'Pont fessier unilatéral'),
    ('gainage', 'Gainage'),
    ('fente', 'Fentes'),
    ('mollet', 'Mollets'),
)
# Longest stem first so "pont fessier" beats a bare "fessier"-like match.
_STEM_FALLBACKS = tuple(sorted(_STEM_FALLBACKS, key=lambda s: len(s[0]), reverse=True))


_UNKNOWN = MuscleMapping(
    group_weights={}, pattern=OTHER, e1rm=False, autre=True, autre_reason='unknown',
)


def lookup_exercise(name: str) -> MuscleMapping:
    """Resolve a (possibly raw) exercise name to its :class:`MuscleMapping`.

    Resolution order:
    1. exact normalised key (after canonicalisation);
    2. longest matching stem fallback;
    3. ``autre`` (unknown), so an unmapped name is surfaced, never silently zero.
    """
    canonical = canonicalize_exercise_name(name)
    key = _normalization_key(canonical)
    if key in EXERCISE_MUSCLES:
        return EXERCISE_MUSCLES[key]
    for stem, target in _STEM_FALLBACKS:
        if stem in key:
            return EXERCISE_MUSCLES[_normalization_key(canonicalize_exercise_name(target))]
    return _UNKNOWN


def canonical_display_name(name: str) -> str:
    """Canonical display name for a raw exercise name (for records/notes)."""
    return canonicalize_exercise_name(name)


# ---------------------------------------------------------------------------
# Coverage guard data (consumed by the unit tests).
# ---------------------------------------------------------------------------

def all_canonical_names() -> List[str]:
    """Every canonical strength name that must resolve to a non-unknown entry."""
    return list(CANONICAL_STRENGTH_EXERCISES)
