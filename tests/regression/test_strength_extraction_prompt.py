"""Guardrails on the strength extraction prompt.

The 2026-08-14 Upperbody session was logged as ``dc 80x10 90 8-8-9`` and stored as
three sets (80x10, 90x8, 90x9): the middle 90x8 was lost, which corrupted every total
derived from it and fed the coach a session smaller than the real one.

The prompt specified the dash as a SUPERSET separator ('3x10-10 15-35' mapping to two
exercises) and never as successive sets, so '8-8-9' on a single exercise had no mapping.
It also showed 'x' only as reps x load ('10x80') while the athlete also writes load x
reps ('80x10').

These tests pin the rules down. They check the specification, not the model: a prompt
rule is necessary but not sufficient, which is why the figure verifier stays the
enforcement layer.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from processing.content_generator import _STRENGTH_EXTRACTION_SYSTEM_PROMPT as PROMPT  # noqa: E402


class TestDashSeriesRule:
    def test_the_failing_notation_is_specified_verbatim(self):
        assert "80x10 90 8-8-9" in PROMPT

    def test_repeated_values_must_not_be_collapsed(self):
        low = PROMPT.lower()
        assert "do not collapse repeated values" in low

    def test_the_single_exercise_case_is_distinguished_from_the_superset_case(self):
        low = PROMPT.lower()
        assert "dash series" in low
        assert "single exercise" in low

    def test_the_superset_rule_is_still_present(self):
        """The new rule must not have displaced the one that already worked."""
        assert "PAIRED notation" in PROMPT
        assert "3x10-10 15-35" in PROMPT


class TestXOrderRule:
    def test_both_orders_are_specified(self):
        assert "10x80" in PROMPT
        assert "80x10" in PROMPT

    def test_the_set_count_spelling_is_distinguished(self):
        assert "4x8" in PROMPT


class TestPreexistingRulesSurvive:
    """Rules earned from previous production failures must stay in place."""

    def test_per_side_loads(self):
        assert "PER SIDE" in PROMPT
        assert "4x8 55/c" in PROMPT

    def test_sets_detail_is_authoritative(self):
        assert "sets_detail is REQUIRED and is the authoritative field" in PROMPT


class TestPerSideFlagInExamples:
    """The model copies the examples. One without ``per_side`` teaches it to drop
    the flag, and an unflagged row then counts in no record."""

    def _example_objects(self):
        import json
        import re
        objects = []
        for raw in re.findall(r"-> (\[.*?\])(?:\n|$)", PROMPT):
            objects.extend(json.loads(raw))
        return objects

    def test_every_example_object_carries_per_side(self):
        objects = self._example_objects()
        assert len(objects) >= 7
        assert all(isinstance(o.get("per_side"), bool) for o in objects), [
            o["exercise"] for o in objects if not isinstance(o.get("per_side"), bool)
        ]

    def test_a_paired_line_with_one_per_side_lift_is_shown(self):
        flags = [o["per_side"] for o in self._example_objects()]
        assert "8/c-40" in PROMPT
        assert True in flags and False in flags

    def test_every_per_side_spelling_is_listed(self):
        for spelling in ("'/c'", "'/cote'", "'/côté'", "'par cote'", "'par côté'",
                         "'each side'", "'/side'"):
            assert spelling in PROMPT, spelling
