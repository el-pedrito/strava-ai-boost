"""Canonical strength exercise names shared by ingestion and Coach aggregation."""

import re
import unicodedata
from typing import Dict, Iterable, Tuple


CANONICAL_STRENGTH_EXERCISES: Tuple[str, ...] = (
    'Tractions',
    'Développé couché',
    'Développé couché haltères',
    'Développé incliné',
    'Développé incliné haltères',
    'Développé décliné',
    'Développé militaire',
    'Développé militaire haltères',
    'Développé militaire assis',
    'Développé machine',
    'Presse épaules',
    'Dips',
    'Pompes',
    'Face pull',
    'Élévations latérales',
    'Élévations latérales haltères assis',
    'Pull-over',
    'Tirage vertical machine',
    'Tirage vertical prise neutre',
    'Tirage vertical neutre serré',
    'Tirage horizontal',
    'Tirage horizontal machine',
    'Tirage horizontal unilatéral machine',
    'Curl barre',
    'Curl biceps',
    'Curl biceps rotation',
    'Curl marteau',
    'Curl biceps à la corde',
    'Triceps à la corde',
    'Écartés pectoraux à la poulie',
    'Squat',
    'Fentes',
    'Presse à cuisses',
    'Leg curl',
    'Leg extension',
    'Hip thrust',
    'Soulevé de terre',
    'Mollets',
    'Gainage',
    'Crunch',
)


def _normalization_key(value: str) -> str:
    """Return an accent-, punctuation-, and case-insensitive lookup key."""
    normalized = unicodedata.normalize('NFKD', value.casefold())
    normalized = ''.join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.replace('œ', 'oe').replace('æ', 'ae')
    normalized = re.sub(r"[^a-z0-9]+", ' ', normalized)
    return ' '.join(normalized.split())


def _aliases(canonical: str, values: Iterable[str]) -> Tuple[str, Tuple[str, ...]]:
    return canonical, tuple(values)


_ALIAS_GROUPS = (
    _aliases('Face pull', ('Facepull', 'Face pulls')),
    _aliases('Élévations latérales', (
        'Élévation latérale', 'Elevation laterale', 'Elevations laterales',
    )),
    _aliases('Élévations latérales haltères assis', (
        'Élévation latérale haltères assis', 'Elevations laterales halteres assis',
    )),
    _aliases('Pull-over', ('Pullover', 'Pull over')),
    _aliases('Développé couché', (
        'DC', 'DC barre', 'Développé couché barre',
    )),
    _aliases('Développé couché haltères', (
        'DC halt', 'DC haltere', 'DC halteres', 'Développé couché halt',
        'Développé couché haltère',
    )),
    _aliases('Développé incliné haltères', (
        'Développé incliné halt', 'Développé incliné haltère',
    )),
    _aliases('Développé militaire haltères', (
        'Développé militaire halt', 'Développé militaire haltère',
    )),
    _aliases('Écartés pectoraux à la poulie', (
        'Écart pec', 'Écart pec poulie', 'Écart pectoral poulie',
        'Écart pectoraux poulie', 'Écartement pectoraux poulie',
        'Écartés pectoraux poulie', 'Écartés pectoraux à la poulie',
    )),
    _aliases('Triceps à la corde', (
        'Triceps corde', 'Extension triceps à la corde',
        'Triceps à la corde poulie haute',
    )),
    _aliases('Curl biceps à la corde', (
        'Biceps corde', 'Biceps à la corde', 'Curl biceps corde',
    )),
    _aliases('Curl barre', ('Biceps barre',)),
    _aliases('Curl marteau', ('Curl marteau biceps',)),
    _aliases('Tirage horizontal machine', ('Low row', 'Rowing machine')),
)

_ALIAS_TO_CANONICAL: Dict[str, str] = {
    _normalization_key(name): name for name in CANONICAL_STRENGTH_EXERCISES
}
for _canonical, _values in _ALIAS_GROUPS:
    for _value in _values:
        _ALIAS_TO_CANONICAL[_normalization_key(_value)] = _canonical


def canonicalize_exercise_name(name: str) -> str:
    """Return a stable canonical name for known aliases; preserve unknown names."""
    cleaned = ' '.join(str(name).strip().split())
    if not cleaned:
        return ''
    return _ALIAS_TO_CANONICAL.get(_normalization_key(cleaned), cleaned)


# ---------------------------------------------------------------------------
# Bodyweight and unilateral exercise tables (consumed by strength_volume.py).
#
# WHY these live here: the extraction prompt records ``weight_kg = null`` both
# for "loaded with the athlete's own body" and for "load unknown". A null alone
# cannot tell those apart, so the tonnage module needs an *explicit*, auditable
# source of truth to decide which nulls resolve to body weight. Keeping the
# table next to the canonical vocabulary means the exercise name it is keyed on
# is guaranteed to be the same canonical string the aggregator sees.
# ---------------------------------------------------------------------------

# Maps a canonical exercise name -> fraction of the athlete's body weight moved
# per repetition. This is the ONLY authorized way to turn a null ``weight_kg``
# into a real load; any exercise absent from this table with a null weight is
# treated as "load unknown" and is excluded from the tonnage (and signalled),
# never silently valued at zero.
#
# Coefficients are the ATHLETE'S explicit decision ("les tractions, les dips,
# les pompes, va partir sur mon poids du corps"):
#   Tractions 1.0, Dips 1.0, Pompes 1.0.
#
# Documented reservation on Pompes (push-ups): the real load moved in a push-up
# is only ~65% of body weight, so at 1.0 a push-up session is overstated by
# ~35% and its tonnage is NOT comparable to a pull-up session. This is a
# deliberate choice, not an oversight; making push-ups comparable is a
# one-line change here (``'Pompes': 0.65``).
BODYWEIGHT_EXERCISES: Dict[str, float] = {
    'Tractions': 1.0,
    'Dips': 1.0,
    'Pompes': 1.0,
}

# Maps a canonical exercise name -> number of sides performed. A unilateral
# exercise noted "4x10 @30kg" means 4 sets PER SIDE, so sets, reps and volume
# are all expanded by this factor together (see strength_volume.py). Expanding
# the set count -- rather than applying a factor to the volume alone -- keeps
# ``sets x reps x load`` equal to the displayed volume, so the doubling stays
# verifiable instead of hidden.
#
# Athlete's decision: count BOTH sides. Of the 40 canonical exercises only
# 'Tirage horizontal unilatéral machine' is unambiguously unilateral. 'Curl
# marteau' and 'Fentes' are ambiguous (alternating vs simultaneous; lunges
# alternate by nature) and are deliberately LEFT OUT -- doubling them by mistake
# would be a silent over-estimation. They join the table only on the athlete's
# confirmation. Convention reservation: this assumes "per side" notation; if the
# athlete ever logs the two-side total directly, the doubling would overstate --
# single point of change here.
UNILATERAL_EXERCISES: Dict[str, int] = {
    'Tirage horizontal unilatéral machine': 2,
}
