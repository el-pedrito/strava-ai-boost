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
