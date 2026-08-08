"""Unit tests for the renfo/rando/rendo vocabulary normalizer.

The content agent narrated a WeightTraining as 'session rendo juste avant' (a
garble of 'renfo'). 'rendo' is always a typo; 'rando' is a real word so it is
only rewritten for strength sessions.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from processing.content_generator import _normalize_strength_vocab


class TestNormalizeStrengthVocab:
    def test_rendo_always_fixed(self):
        assert _normalize_strength_vocab("la session rendo juste avant", False) == "la session renfo juste avant"
        assert _normalize_strength_vocab("la session rendo juste avant", True) == "la session renfo juste avant"

    def test_rando_fixed_only_for_strength(self):
        assert _normalize_strength_vocab("ma rando du jour", True) == "ma renfo du jour"
        assert _normalize_strength_vocab("belle rando en montagne", False) == "belle rando en montagne"

    def test_randonnee_variants_for_strength(self):
        assert _normalize_strength_vocab("grosse randonnee aujourd'hui", True) == "grosse renfo aujourd'hui"
        assert _normalize_strength_vocab("grosse randonnée aujourd'hui", True) == "grosse renfo aujourd'hui"

    def test_word_boundary_spares_rendormir(self):
        assert _normalize_strength_vocab("je vais me rendormir apres", True) == "je vais me rendormir apres"

    def test_empty_and_none_safe(self):
        assert _normalize_strength_vocab("", True) == ""
        assert _normalize_strength_vocab(None, True) is None

    def test_case_insensitive(self):
        assert _normalize_strength_vocab("Rendo du soir", False) == "renfo du soir"
