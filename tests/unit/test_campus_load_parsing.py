"""Tests for how the athlete's own load notation is parsed.

Reason this exists: from August to October 2026, 5 of his 6 Campus strength texts lost
the split squat load. "Split squat 2 kettlebells 16kg" was read as the term "s" (digits
broke the term, then str.replace("kettlebell") left the plural "s"), and "Split squat
avec 2 ketle de 24kg" as the term "de". Both then matched by SUBSTRING every plan
exercise containing that fragment ("de" is in "Extension de Mollet"), and the doubling
was lost with the family name.

His wording changes a little every time, so the real texts below are VERBATIM from the
original_description field in DynamoDB (activity id in the name), never paraphrased.

Athlete conventions, authoritative:
  - "fente(s)" and "split squat" are one family, done with two kettlebells, so the load
    he writes doubles (confirmed 2026-08-17), and "2 ketle de 24kg" = 48 kg (2026-10-13);
    a written "2" confirms the doubling, it never makes it x4;
  - "Split quat" is his typo for split squat (confirmed 2026-10-13).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared.campus_structure import (  # noqa: E402
    _load_for,
    compute_ppg_volume,
    extract_athlete_loads,
    resolve_exercise_loads,
)

SPLIT_SQUAT_PLAN_NAME = "Split Squat avec charge additionnelle"

# activity 19655889544, 2026-08-08
TEXT_0808 = (
    "Renfo course a pied Campus, pour mollet kettlebell 12kg, split squat 2 kettlebells "
    "de 20kg et swing kettlebell 24kg, pour se remettre en jambes avec la reprise du renfo."
)

# activity 19741778657, 2026-08-14
TEXT_1408 = (
    "Partie 1 du jour\n\nRenfo course campus\nMollet ketle 12kg\nFentes ketle 20kg\n"
    "Swing ketle 24kg"
)

# activity 20340697093, 2026-09-26
TEXT_2609 = (
    "Renfo course à pied campus\n\n26/09\nRoutine elastiques etirements\nSplit squat avec "
    "2 ketle de 24kg \nSwing avec ketle de 24kg\nMollets avec 12kg"
)

# activity 20431235182, 2026-10-03
TEXT_0310 = (
    "On enchaîne avec le renforcement course à pied, juste après le upper deuxième séance "
    "du jour en mode circuit\n\n03/10\nRenfo course campus\nSur split squat 2 ketle de 16kg "
    "on adapte par rapport à la semaine dernière pour pas avoir trop de courbatures qui "
    "viennent perturber la prépa\nMollet ketle de 12kg"
)

# activity 20524818169, 2026-10-10
TEXT_1010 = (
    "10/07\nRenfo campus course a pied la veille du 20km de paris on gere l’effort\n"
    "Split quat avec 2 ketle de 16kg\nEt mollets à la fin avec 12kg"
)

# activity 16923383374, 2026-01-03
TEXT_0301 = (
    "Renfo course a pied campus\nFinish fin de seance curl biceps rotation 16kg par bras "
    "20rep et extension triceps"
)


class TestRealTexts:
    def test_text_0808(self):
        assert extract_athlete_loads(TEXT_0808) == {"mollet": 12.0, "split squat": 40.0, "swing": 24.0}

    def test_text_1408(self):
        assert extract_athlete_loads(TEXT_1408) == {"mollet": 12.0, "split squat": 40.0, "swing": 24.0}

    def test_text_2609(self):
        assert extract_athlete_loads(TEXT_2609) == {"split squat": 48.0, "swing": 24.0, "mollet": 12.0}

    def test_text_0310(self):
        assert extract_athlete_loads(TEXT_0310) == {"split squat": 32.0, "mollet": 12.0}

    def test_text_1010(self):
        assert extract_athlete_loads(TEXT_1010) == {"split squat": 32.0, "mollet": 12.0}

    def test_text_0301(self):
        # Not a family: kept as his own words, never doubled ("par bras" stays as written).
        assert extract_athlete_loads(TEXT_0301) == {"finish fin seance curl biceps rotation": 16.0}

    def test_the_original_bug_string(self):
        assert extract_athlete_loads("Split squat 2 kettlebells 16kg") == {"split squat": 32.0}


class TestNoFragmentCanBecomeAKey:
    def test_a_stray_fragment_key_matches_nothing(self):
        # The exact shapes the old parser produced.
        assert _load_for("Extension de Mollet", {"de": 16.0}) is None
        assert _load_for("Squat goblet", {"s": 16.0}) is None

    def test_a_filler_only_clause_yields_nothing(self):
        assert extract_athlete_loads("avec de 20kg") == {}

    def test_a_short_unknown_term_abstains_without_touching_its_neighbour(self):
        assert extract_athlete_loads("Swing 24kg, rdl 40kg") == {"swing": 24.0}

    def test_et_inside_a_word_is_not_a_boundary(self):
        assert extract_athlete_loads("Bretelles 10kg") == {"bretelles": 10.0}


class TestDoubling:
    def test_split_squat_doubles_once(self):
        cases = [
            ("Fentes ketle 20kg", 40.0),
            ("Fentes à 20kg", 40.0),
            ("split squat deux ketle de 16kg", 32.0),  # x2 once, never x4
            ("split-squat 20kg", 40.0),
            ("Fentes 12,5kg", 25.0),  # decimal comma survives the clause split
        ]
        for text, expected in cases:
            assert extract_athlete_loads(text) == {"split squat": expected}, text

    def test_an_ordinary_squat_is_not_a_split_squat(self):
        cases = [
            ("Squat 60kg", "squat", 60.0),
            ("Back squat 85kg", "back squat", 85.0),
            ("Goblet squat 20kg", "goblet squat", 20.0),
        ]
        for text, key, load in cases:
            assert extract_athlete_loads(text) == {key: load}, text

    def test_per_side_notation_is_kept_as_written(self):
        assert extract_athlete_loads("Press epaules 35kg/cote") == {"press epaules": 35.0}

    def test_equal_values_are_compared_raw_before_doubling(self):
        assert extract_athlete_loads("Split squat 2 ketle de 20kg et 20kg") == {
            "split squat": 40.0
        }


class TestAmbiguityAbstains:
    def test_nothing_is_guessed(self):
        cases = [
            "DC 85-87,5kg",
            "DI 80→85kg",
            "2x22kg",
            "Swing 16kg puis 24kg",
            "Swing 16kg, 24kg",
            "Split squat 2 ketle de 20kg et 24kg",
        ]
        for text in cases:
            assert extract_athlete_loads(text) == {}, text

    def test_distinct_clauses_both_resolve(self):
        assert extract_athlete_loads("Swing 16kg puis Mollet 12kg") == {
            "swing": 16.0,
            "mollet": 12.0,
        }

    def test_a_family_without_value_is_dropped(self):
        assert extract_athlete_loads("Mollet et swing 24kg") == {"swing": 24.0}

    def test_a_value_alone_continues_the_family_just_before(self):
        assert extract_athlete_loads("Mollet\n12kg") == {"mollet": 12.0}


class TestLookup:
    def test_a_non_family_key_never_takes_a_family_exercise(self):
        loads = extract_athlete_loads("Squat 60kg\nFentes ketle 20kg")
        assert _load_for(SPLIT_SQUAT_PLAN_NAME, loads) == 40.0

    def test_legacy_and_canonical_keys_both_resolve(self):
        for key in ("fente", "fentes", "split squat"):
            assert _load_for(SPLIT_SQUAT_PLAN_NAME, {key: 40.0}) == 40.0, key


W42_RENFORCEMENT = {
    "intervals": [
        {
            "type": "block",
            "repeat": 4,
            "exercises": [
                {"type": "work", "name": SPLIT_SQUAT_PLAN_NAME, "reps": 8},
                {"type": "work", "name": "Extension de Mollet", "reps": 15},
                {"type": "work", "name": "Gainage Frontal", "duration": 30},
            ],
        },
    ],
}


class TestEndToEndOnTheLatestText:
    TEXT = TEXT_1010

    def test_rows_carry_the_right_loads(self):
        rows = {r["exercise"]: r for r in resolve_exercise_loads(W42_RENFORCEMENT, self.TEXT)}
        assert rows[SPLIT_SQUAT_PLAN_NAME]["load_kg"] == 32.0
        assert rows["Extension de Mollet"]["load_kg"] == 12.0
        assert rows["Gainage Frontal"]["bodyweight"] is True

    def test_volume(self):
        volume = compute_ppg_volume(W42_RENFORCEMENT, extract_athlete_loads(self.TEXT))
        # 4 x 8 x 32 + 4 x 15 x 12
        assert volume["volume_kg"] == 1744.0
