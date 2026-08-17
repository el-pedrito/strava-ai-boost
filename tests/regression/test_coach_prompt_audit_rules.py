"""Guardrails on the coach prompt rules earned from the 2026-08-14/15/16 audit.

Each rule below exists because a specific published sentence was wrong. These tests pin
the SPECIFICATION: a rule silently dropped during a prompt refactor would otherwise only
resurface as a wrong figure on Strava.

They deliberately check the prompt text, not the model. A prompt rule is necessary and
not sufficient, which is why ``coach_output_check`` enforces the same facts at output
time. Both layers are required: this project has three recorded cases where the fact was
present in the context and the model still ignored it.
"""

import os
from pathlib import Path

# Read as text rather than imported: the package name ``agents`` collides with another
# ``agents`` module once the full suite has run, and a guardrail on the specification does
# not need the module loaded. Same approach as test_coach_prompt_guardrails.py.
PROMPT = Path(
    os.path.join(os.path.dirname(__file__), "..", "..", "src", "agents", "embedded_prompts.py")
).read_text(encoding="utf-8")


class TestLapFactRules:
    """15/08: '3:16/km' came from max_speed 3.26 read as a decimal pace."""

    def test_lap_facts_is_named_as_the_sole_source_of_lap_paces(self):
        assert "_lap_facts" in PROMPT
        assert "pace_per_km" in PROMPT

    def test_max_speed_is_explicitly_forbidden(self):
        assert "max_speed" in PROMPT

    def test_the_effort_count_source_is_named(self):
        assert "work_reps.count" in PROMPT

    def test_the_recovery_mode_source_is_named(self):
        assert "recovery.mode" in PROMPT

    def test_the_published_errors_are_cited_so_the_rule_is_not_dropped_as_abstract(self):
        assert "3:16/km" in PROMPT
        assert "5 fractions courtes" in PROMPT


class TestProgressionRules:
    """14/08: a progression published as a regression, with an invented previous set."""

    def test_the_comparison_field_is_named(self):
        assert "exercise_comparisons" in PROMPT
        assert "classification" in PROMPT

    def test_decline_wording_is_forbidden_outside_a_regression(self):
        low = PROMPT.lower()
        assert "flancher" in low
        assert "regression" in low

    def test_the_invented_previous_session_is_cited(self):
        assert "4x8 @90kg" in PROMPT

    def test_incomparable_is_documented(self):
        assert "incomparable" in PROMPT


class TestCampusStructureRules:
    """14/08: a 2-block session flattened, and 'Bloc 1/2' invented from the athlete's text."""

    def test_the_structure_fields_are_named(self):
        assert "structure.work_exercises" in PROMPT
        assert "structure.blocks" in PROMPT

    def test_full_completion_forbids_announcing_a_remaining_block(self):
        assert "fully_completed" in PROMPT
        assert "Bloc 1/2" in PROMPT

    def test_the_planned_duration_scope_is_stated(self):
        assert "expected_duration_min" in PROMPT

    def test_the_computed_volume_and_its_partial_flag_are_named(self):
        assert "computed_volume" in PROMPT
        assert "volume_kg_incomplete" in PROMPT


class TestSessionOrdinalRule:
    """16/08: '5e seance de la semaine' on a seven-session week."""

    def test_the_counting_frame_must_be_named(self):
        assert "5e seance Campus" in PROMPT

    def test_campus_and_own_program_are_counted_separately(self):
        assert "own_strength_program" in PROMPT
        assert "campus_remaining" in PROMPT


class TestPreexistingRulesSurvive:
    """Rules earned before this audit must not be displaced by the new ones."""

    def test_strength_session_totals(self):
        assert "strength_session" in PROMPT
        assert "total_reps" in PROMPT

    def test_verification_errors_second_pass(self):
        assert "verification_errors" in PROMPT

    def test_activity_average_pace_rule(self):
        assert "avg_pace" in PROMPT
