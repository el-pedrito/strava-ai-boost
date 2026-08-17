"""Deterministic replay of the four audited activities against the new guards.

Every string below is VERBATIM from what the pipeline published on 2026-08-14, 15 and 16,
read back from DynamoDB (``coach_feedback`` and ``enhanced_description``). The facts
alongside are the ones the new modules compute from the same activities' ``laps_json``
and Campus plan.

The question this answers is the only one that matters: would the guards have caught the
18 errors? It is not a substitute for the live prompt regression, which replays synthetic
fixtures against the DEPLOYED runtime and therefore cannot judge an undeployed prompt. It
answers a narrower and more directly useful question, offline and for free.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from processing.coach_output_check import (  # noqa: E402
    find_internal_contradictions,
    verify_weekly_claims,
)

# --- Facts computed by the new modules from the real activities ---------------

LONG_RUN_FACTS = {
    "lap_facts": {
        "work_reps": {"count": 4, "durations_s": [299, 300, 300, 300]},
        "blocks": [{"repeat": 4, "pattern_s": [299]}],
        "recovery": {"count": 4, "mode": "active", "distances_m": [179, 200, 210, 229]},
    }
}
ENDURANCE_FORCE_FACTS = {
    "lap_facts": {
        "work_reps": {"count": 6, "durations_s": [34, 25, 15, 35, 25, 15]},
        "blocks": [{"repeat": 2, "pattern_s": [34, 25, 15]}],
        "recovery": {"count": 6, "mode": "active", "distances_m": [390, 417, 777, 408, 443, 755]},
    }
}
UPPERBODY_FACTS = {
    "exercise_comparisons": [
        {
            "exercise": "Développé couché",
            "classification": "progression",
            "delta_reps_at_top_load": 1,
            "current": {"top_load_kg": 90, "sets_at_top_load": 3, "reps_at_top_load": 25},
            "previous": {"top_load_kg": 90, "sets_at_top_load": 3, "reps_at_top_load": 24},
        }
    ]
}
RENFO_FACTS = {
    "campus": {
        "fully_completed": True,
        "structure": {"blocks": 2, "rounds": [4, 4]},
    }
}
# 2 runs (12.6 km), 2 own muscu, 1 Campus PPG: five sessions, and the PPG apart.
WEEK_OVERVIEW_14_08 = {
    "done_this_week": {"runs": 2, "run_km": 12.6, "strength": 3, "muscu": 2, "total": 5},
    "campus_remaining": {"count": 2},
    "own_strength_program": {"planned_per_week": 3, "done_this_week": 2, "remaining": 1},
    "counts_incomplete": False,
}


class TestLongRun1508:
    """Published: '4 fractions actives (5min a 3:16/km)' on fractions run at 5:24."""

    def test_the_passive_recovery_claim_is_caught(self):
        published = {
            "detailed_analysis": (
                "Les laps confirment le plan : 25min a 142bpm (Lap 1), puis 4 blocs de 5min a "
                "158-162bpm entrecoupes de recup passive (Laps 3-5-7-9)."
            )
        }
        problems = verify_weekly_claims(published, None, None, computed_facts=LONG_RUN_FACTS)
        assert any("recovery mode" in p for p in problems), problems

    def test_the_rest_window_contradiction_is_caught(self):
        published = {
            "recommendation_next": (
                "Prends 48h de recup apres cette sortie longue (aucune seance course ni muscu "
                "intensive). Quand tu te sens pret, termine la semaine avec l'Endurance de Force."
            )
        }
        problems = find_internal_contradictions(published, activity_date="2026-08-15")
        assert any("rest window" in p for p in problems), problems


class TestEnduranceForce1608:
    """Published: '5 fractions courtes' next to '2 blocs de sprints (35-25-15sec)'."""

    def test_the_effort_count_is_caught_against_the_laps(self):
        published = {
            "strava_block": (
                "8,5km d'endurance de force en 54min (6:26/km) avec 5 fractions courtes "
                "(15-35sec) a intensite elevee (pics a 161-165bpm, 89% FCmax)."
            )
        }
        problems = verify_weekly_claims(
            published, None, None, computed_facts=ENDURANCE_FORCE_FACTS
        )
        assert any("effort count" in p for p in problems), problems

    def test_the_self_contradiction_is_caught_without_any_fact(self):
        published = {
            "strava_block": "8,5km d'endurance de force avec 5 fractions courtes (15-35sec).",
            "detailed_analysis": (
                "Structure Campus Coach : 20min echauffement + 2 blocs de sprints (35-25-15sec) "
                "avec recup active 3min, puis 10min retour au calme."
            ),
        }
        problems = find_internal_contradictions(published)
        assert any("effort count" in p for p in problems), problems


class TestUpperbody1408:
    """Published: a regression on the bench press, which had progressed by one rep."""

    def test_the_inverted_direction_is_caught(self):
        published = {
            "detailed_analysis": (
                "Sur le developpe couche c'est une regression : tu as flanche sur la derniere "
                "serie par rapport a la seance du 11/08."
            )
        }
        problems = verify_weekly_claims(published, None, None, computed_facts=UPPERBODY_FACTS)
        assert any("progression direction" in p for p in problems), problems

    def test_the_session_type_contradiction_is_caught(self):
        published = {
            "detailed_analysis": (
                "2e Upper en une journee apres la PPG : decision tactique mais le systeme "
                "nerveux paye."
            )
        }
        problems = find_internal_contradictions(published)
        assert any("session ordinal" in p for p in problems), problems

    def test_the_taxonomy_contradiction_is_caught(self):
        published = {
            "strava_block": (
                "Cette semaine : 2 courses (12,6 km), 2 muscu, 1 PPG, soit 5 seances au total."
            ),
            "detailed_analysis": "Tu as boucle tes 2 muscu de la semaine (PPG Campus + cet Upper).",
        }
        problems = find_internal_contradictions(published)
        assert any("taxonomy" in p for p in problems), problems


class TestRenfoCampus1408:
    """Published: 'hier (11/08)' three days back, a total omitting the PPG, and 'Bloc 1/2'."""

    def test_the_relative_day_is_caught(self):
        published = {
            "detailed_analysis": (
                "Ton rythme muscu personnel s'ajuste bien : tu as fait Upper B hier (11/08), "
                "aujourd'hui PPG (14/08)."
            )
        }
        problems = find_internal_contradictions(published, activity_date="2026-08-14")
        assert any("relative day" in p for p in problems), problems

    def test_the_total_omitting_the_ppg_is_caught(self):
        published = {
            "strava_block": (
                "Cette semaine : 2 courses (12,6 km), 2 muscu, soit 4 seances au total."
            )
        }
        problems = verify_weekly_claims(published, WEEK_OVERVIEW_14_08, None)
        assert any("total sessions" in p for p in problems), problems

    def test_the_block_one_of_two_claim_is_caught(self):
        """From enhanced_description, the content agent's own output."""
        published = {"strava_block": "Seance Campus Coach : Renforcement (Bloc 1/2)."}
        problems = verify_weekly_claims(published, None, None, computed_facts=RENFO_FACTS)
        assert any("session completeness" in p for p in problems), problems

    def test_the_remaining_block_claim_is_caught(self):
        published = {
            "recommendation_next": (
                "Prochaine etape : le Bloc 2 avec gainage lateral et mollet statique."
            )
        }
        problems = verify_weekly_claims(published, None, None, computed_facts=RENFO_FACTS)
        assert any("session completeness" in p for p in problems), problems


class TestTheCorrectSentencesSurvive:
    """A guard that strips correct coaching is worse than no guard at all."""

    def test_the_correct_effort_count_passes(self):
        published = {"strava_block": "8,5km d'endurance de force avec 6 fractions courtes."}
        assert (
            verify_weekly_claims(published, None, None, computed_facts=ENDURANCE_FORCE_FACTS) == []
        )

    def test_the_correctly_phrased_second_session_passes(self):
        published = {
            "detailed_analysis": (
                "Contexte lourd : 2e seance du jour apres la PPG Campus (44min a 119bpm)."
            )
        }
        assert find_internal_contradictions(published) == []

    def test_the_real_weekly_total_passes(self):
        published = {
            "strava_block": (
                "Cette semaine : 2 courses (12,6 km), 2 muscu, 1 PPG, soit 5 seances au total."
            )
        }
        assert verify_weekly_claims(published, WEEK_OVERVIEW_14_08, None) == []

    def test_describing_the_completed_session_passes(self):
        published = {"strava_block": "Renforcement complete : 2 blocs de 4 tours, 6 exercices."}
        assert verify_weekly_claims(published, None, None, computed_facts=RENFO_FACTS) == []
