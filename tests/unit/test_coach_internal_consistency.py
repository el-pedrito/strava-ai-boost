"""Tests for the internal-consistency checks on generated coaching text.

Every fixture below is a verbatim sentence pair the deployed pipeline produced on
2026-08-14, 15 and 16. They are the specification.

Why a separate check from ``verify_weekly_claims``
--------------------------------------------------
Those six production errors need NO computed figure to be caught: the text
contradicts itself. "5 fractions courtes" sits in the same feedback as "2 blocs de
sprints (35-25-15sec)", and 2 x 3 is 6. Catching them therefore does not depend on
any of the fact-building work, which is why this lands first.

Unlike a contradicted figure, a self-contradiction does not tell us WHICH of the two
statements is wrong. So these problems trigger a regeneration and are never used to
strip a sentence: removing the correct half of a contradiction would be worse than
leaving both.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from processing.coach_output_check import (  # noqa: E402
    find_internal_contradictions,
    verify_weekly_claims,
)


class TestIntervalCountAgainstBlockStructure:
    """16/08: the coach announced 5 short efforts and 2 blocks of three."""

    def test_five_efforts_contradicts_two_blocks_of_three(self):
        fb = {
            "strava_block": (
                "8,5km d'endurance de force en 54min (6:26/km) avec 5 fractions "
                "courtes (15-35sec) a intensite elevee."
            ),
            "detailed_analysis": (
                "Structure Campus Coach : 20min echauffement + 2 blocs de sprints "
                "(35-25-15sec) avec recup active 3min, puis 10min retour au calme."
            ),
        }
        problems = find_internal_contradictions(fb)
        assert any("effort count" in p for p in problems), problems

    def test_six_efforts_agrees_with_two_blocks_of_three(self):
        """The corrected wording must NOT be flagged."""
        fb = {
            "strava_block": "8,5km avec 6 fractions courtes (15-35sec).",
            "detailed_analysis": "Structure : 2 blocs de sprints (35-25-15sec).",
        }
        assert find_internal_contradictions(fb) == []


class TestSessionOrdinalAgainstPreviousSessionType:
    """14/08: '2e Upper en une journee apres la PPG' cannot both be true."""

    def test_second_upper_after_a_ppg_is_contradictory(self):
        fb = {
            "detailed_analysis": (
                "2e Upper en une journee apres la PPG : decision tactique mais le "
                "systeme nerveux paye."
            )
        }
        problems = find_internal_contradictions(fb)
        assert any("session ordinal" in p for p in problems), problems

    def test_second_session_of_the_day_after_a_ppg_is_fine(self):
        """The same feedback said it correctly elsewhere; that wording must pass."""
        fb = {
            "detailed_analysis": (
                "Contexte lourd : 2e seance du jour apres la PPG Campus (44min a 119bpm)."
            )
        }
        assert find_internal_contradictions(fb) == []


class TestCountAgainstItsOwnEnumeration:
    """14/08: '2 muscu, 1 PPG' then 'tes 2 muscu (PPG Campus + cet Upper)'."""

    def test_ppg_counted_apart_then_inside_the_muscu_count(self):
        fb = {
            "strava_block": (
                "Cette semaine : 2 courses (12,6 km), 2 muscu, 1 PPG, soit 5 seances au total."
            ),
            "detailed_analysis": "Tu as boucle tes 2 muscu de la semaine (PPG Campus + cet Upper).",
        }
        problems = find_internal_contradictions(fb)
        assert any("taxonomy" in p for p in problems), problems

    def test_muscu_enumeration_without_ppg_is_fine(self):
        fb = {
            "strava_block": "Cette semaine : 2 courses, 2 muscu, 1 PPG, soit 5 seances au total.",
            "detailed_analysis": "Tu as boucle tes 2 muscu de la semaine (Upper A + Upper B).",
        }
        assert find_internal_contradictions(fb) == []


class TestRelativeDayAgainstExplicitDate:
    """14/08: 'Upper B hier (11/08)' names a date three days earlier."""

    def test_hier_with_a_date_three_days_back(self):
        fb = {"detailed_analysis": "Tu as fait Upper B hier (11/08), aujourd'hui PPG (14/08)."}
        problems = find_internal_contradictions(fb, activity_date="2026-08-14")
        assert any("relative day" in p for p in problems), problems

    def test_hier_with_the_actual_previous_day(self):
        fb = {"detailed_analysis": "Tu as fait Upper B hier (13/08)."}
        assert find_internal_contradictions(fb, activity_date="2026-08-14") == []

    def test_no_reference_date_means_no_claim(self):
        """Without the activity date the check must stay silent, never guess."""
        fb = {"detailed_analysis": "Tu as fait Upper B hier (11/08)."}
        assert find_internal_contradictions(fb) == []


class TestRestAdviceAgainstEndOfWeek:
    """15/08 (Saturday): 48h of rest AND finish the week are incompatible."""

    def test_48h_rest_cannot_fit_before_the_week_ends(self):
        fb = {
            "recommendation_next": (
                "Prends 48h de recup apres cette sortie longue, puis termine la semaine "
                "avec l'Endurance de Force."
            )
        }
        problems = find_internal_contradictions(fb, activity_date="2026-08-15")
        assert any("rest window" in p for p in problems), problems

    def test_48h_rest_early_in_the_week_is_fine(self):
        fb = {
            "recommendation_next": (
                "Prends 48h de recup, puis termine la semaine avec l'Endurance de Force."
            )
        }
        assert find_internal_contradictions(fb, activity_date="2026-08-11") == []


class TestTotalSessionsRemainsCoveredByTheFigureVerifier:
    """14/08: 'soit 4 seances au total' on a 5-session week.

    No new code: the existing figure verifier already compares the stated total to
    ``done_this_week.total``. This locks that in, so the regression would show here
    rather than in production.
    """

    def test_stated_total_below_the_computed_one_is_caught(self):
        overview = {
            "done_this_week": {"runs": 2, "run_km": 12.6, "strength": 3, "muscu": 2, "total": 5},
            "campus_remaining": {"count": 2},
            "own_strength_program": {"remaining": 2},
            "counts_incomplete": False,
        }
        fb = {"strava_block": "Cette semaine : 2 courses (12,6 km), 2 muscu, soit 4 seances au total."}
        problems = verify_weekly_claims(fb, overview, None)
        assert any("total sessions" in p for p in problems), problems


class TestNeverRaises:
    def test_empty_and_malformed_inputs(self):
        assert find_internal_contradictions(None) == []
        assert find_internal_contradictions({}) == []
        assert find_internal_contradictions({"strava_block": None}) == []
        assert find_internal_contradictions("not a dict") == []
