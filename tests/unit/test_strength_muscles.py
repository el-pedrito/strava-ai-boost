"""Unit tests for shared.strength_muscles: map coverage and resolution rules."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))


import json
from pathlib import Path

from shared.campus_structure import ppg_history_sets  # noqa: E402
from shared.strength_muscles import (  # noqa: E402
    AUTRE,
    EXPLOSIVITE,
    MUSCLE_GROUPS,
    lookup_exercise,
    all_canonical_names,
    mixed_exercises,
)

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


class TestCanonicalCoverage:
    def test_every_canonical_name_resolves(self):
        """Every canonical name maps to a real entry (or the one intentional
        to_confirm case), never a silent unknown."""
        unexpected = []
        for name in all_canonical_names():
            mapping = lookup_exercise(name)
            if mapping.autre:
                unexpected.append(name)
        assert unexpected == [], f"canonical names falling to autre: {unexpected}"

    def test_groups_are_valid(self):
        """Every group used is one of the ten muscles, explosivite excluded."""
        valid = set(MUSCLE_GROUPS)
        for name in all_canonical_names():
            mapping = lookup_exercise(name)
            for group in mapping.group_weights:
                assert group in valid, f"{name} uses invalid group {group}"

    def test_pattern_in_allowed_set(self):
        allowed = {'push', 'pull', 'legs', 'core', 'other'}
        for name in all_canonical_names():
            assert lookup_exercise(name).pattern in allowed


class TestWeightsAndFlags:
    def test_primary_secondary_weights(self):
        m = lookup_exercise('Développé couché')
        assert m.group_weights['pectoraux'] == 1.0
        assert m.group_weights['triceps'] == 0.5
        assert m.group_weights['epaules'] == 0.5

    def test_developpe_machine_split(self):
        m = lookup_exercise('Développé machine')
        assert m.group_weights == {'pectoraux': 0.5, 'epaules': 0.5, 'triceps': 0.5}
        assert m.mixed is True
        assert m.e1rm is False
        assert 'Développé machine' in mixed_exercises

    def test_e1rm_true_only_for_compound_barbell(self):
        for name in ['Développé couché', 'Squat', 'Soulevé de terre',
                     'Presse à cuisses', 'Hip thrust', 'Développé militaire']:
            assert lookup_exercise(name).e1rm is True, name

    def test_e1rm_false_for_dumbbells_and_isolation(self):
        for name in ['Développé couché haltères', 'Développé militaire haltères',
                     'Curl barre', 'Élévations latérales', 'Triceps à la corde',
                     'Tractions', 'Dips', 'Pompes']:
            assert lookup_exercise(name).e1rm is False, name

    def test_soulevé_de_terre_secondaries(self):
        m = lookup_exercise('Soulevé de terre')
        assert m.group_weights['ischios'] == 1.0
        assert m.group_weights['fessiers'] == 1.0
        assert m.group_weights['dos'] == 0.5
        assert m.group_weights['quadriceps'] == 0.5

    def test_swing_explosivite_and_hip_credit(self):
        m = lookup_exercise('Swing avec charge')
        assert m.explosivite is True
        assert m.group_weights == {'fessiers': 0.5, 'ischios': 0.5}

    def test_bond_sur_place_explosivite_only(self):
        m = lookup_exercise('Bond sur place')
        assert m.explosivite is True
        assert m.group_weights == {}

    def test_unilateral_tirage_not_e1rm(self):
        assert lookup_exercise('Tirage horizontal unilatéral machine').e1rm is False


class TestResolution:
    def test_case_and_accent_insensitive(self):
        a = lookup_exercise('Gainage latéral')
        b = lookup_exercise('Gainage Latéral')
        assert a == b
        assert a.group_weights == {'abdos': 1.0}

    def test_alias_resolves(self):
        # 'Facepull' -> 'Face pull'
        assert lookup_exercise('Facepull').pattern == 'pull'
        assert lookup_exercise('Facepull').group_weights == {'epaules': 1.0, 'dos': 0.5}

    def test_flexion_de_genou_hamstrings_and_posterior_chain(self):
        """Confirmed by the athlete: hamstrings, plus a posterior-chain hold."""
        m = lookup_exercise('Flexion de genou')
        assert m.autre is False
        assert m.group_weights == {'ischios': 1.0, 'fessiers': 0.5, 'dos': 0.5}
        assert m.pattern == 'legs'
        assert m.e1rm is False

    def test_athlete_shorthand_dc_dm_di(self):
        """dc = couché, dm = militaire (machine = presse épaules), di = incliné."""
        from shared.strength_exercises import canonicalize_exercise_name as c
        assert c('DC') == 'Développé couché'
        assert c('DM') == 'Développé militaire'
        assert c('DI') == 'Développé incliné'
        assert c('DM mach') == 'Presse épaules'
        assert c('dc machine convergente') == 'Développé couché machine'
        assert lookup_exercise('Développé couché machine').group_weights == {
            'pectoraux': 1.0, 'triceps': 0.5, 'epaules': 0.5,
        }
        assert lookup_exercise('Développé couché machine').mixed is False

    def test_flexion_tibiale_unknown(self):
        m = lookup_exercise('Flexion tibiale')
        assert m.autre is True
        assert m.autre_reason == 'unknown'

    def test_unknown_name_is_autre_unknown(self):
        m = lookup_exercise('Mouvement inexistant xyz')
        assert m.autre is True
        assert m.autre_reason == 'unknown'
        assert m.group_weights == {}

    def test_stem_fallback_pont_fessier(self):
        # A future Campus name beginning with "pont fessier".
        m = lookup_exercise('Pont fessier au sol')
        assert m.group_weights == {'fessiers': 1.0, 'ischios': 0.5}

    def test_stem_fallback_gainage(self):
        m = lookup_exercise('Gainage dynamique')
        assert m.group_weights == {'abdos': 1.0}

    def test_stem_fallback_mollet_hold(self):
        m = lookup_exercise('Mollet statique sur marche')
        assert m.group_weights == {'mollets': 1.0}

    def test_exact_key_wins_over_stem(self):
        # "Fentes" is an exact canonical key; the fente* stem must not override it.
        exact = lookup_exercise('Fentes')
        assert exact.group_weights == {'quadriceps': 1.0, 'fessiers': 1.0, 'ischios': 0.5}


class TestGate0Fixture:
    def test_gate0_names_all_resolve_as_planned(self):
        data = json.loads((FIXTURES / 'workout/gate0/ppg_renfo.json').read_text())
        sets = ppg_history_sets(data['session'])
        resolved = {s['exercise']: lookup_exercise(s['exercise']) for s in sets}

        # Flexion de genou -> hamstrings (confirmed).
        assert resolved['Flexion de genou'].group_weights['ischios'] == 1.0
        # Mollets / Fentes already renamed by ppg_history_sets.
        assert resolved['Mollets'].group_weights == {'mollets': 1.0}
        assert resolved['Fentes'].group_weights == {
            'quadriceps': 1.0, 'fessiers': 1.0, 'ischios': 0.5
        }
        # Explosivite.
        assert resolved['Saut groupé'].explosivite is True
        # Stiff-leg deadlift.
        assert resolved['Soulevé de terre jambe tendue'].group_weights == {
            'ischios': 1.0, 'fessiers': 1.0
        }
        # Gainage holds -> abdos (stem or exact).
        assert resolved['Gainage ventral'].group_weights == {'abdos': 1.0}
        assert resolved['Gainage latéral'].group_weights == {'abdos': 1.0}
        # Step-up and chair.
        assert resolved['Montée sur banc'].group_weights == {
            'quadriceps': 1.0, 'fessiers': 1.0
        }
        assert resolved['Chaise'].group_weights == {'quadriceps': 1.0}
        # Single-leg glute bridge via pont fessier stem.
        assert resolved['Pont fessier unilatéral'].group_weights == {
            'fessiers': 1.0, 'ischios': 0.5
        }
