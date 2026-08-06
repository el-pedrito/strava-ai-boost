"""Tests for the coach output verifier.

Every "lie" fixture below is a verbatim sentence the deployed coach produced. They
are the specification: the verifier exists to catch these shapes, and a change that
stops catching one of them is a regression.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from processing.coach_output_check import (  # noqa: E402
    split_sentences,
    strip_false_claims,
    verify_weekly_claims,
)


def _overview(runs=1, run_km=6.4, strength=1, remaining=4, incomplete=False):
    return {
        "week": "2026-W32",
        "label": "Cette semaine (03/08-09/08)",
        "done_this_week": {
            "runs": runs,
            "run_km": run_km,
            "strength": strength,
            "other": 0,
            "total": runs + strength,
        },
        "campus_remaining": {"count": remaining, "running_count": remaining - 1},
        "own_strength_program": {"planned_per_week": 3, "done_this_week": 1, "remaining": 2},
        "counts_incomplete": incomplete,
    }


def _session(total_sets=25, total_reps=238, volume_kg=15370.0, incomplete=False):
    return {
        "total_sets": total_sets,
        "total_reps": total_reps,
        "volume_kg": volume_kg,
        "body_weight_kg_used": 92.0,
        "volume_kg_incomplete": incomplete,
    }


class TestRealProductionLiesAreCaught:
    """The five figures the deployed coach actually got wrong."""

    def test_rep_total_fabricated(self):
        """'320 reps' on a session of 238, with an invented fun fact."""
        fb = {"detailed_analysis": "Fun fact : 320 reps au total aujourd'hui."}
        problems = verify_weekly_claims(fb, _overview(), _session())
        assert problems, "the 320 vs 238 mismatch must be caught"
        assert "total reps" in problems[0]

    def test_strength_session_count_inflated(self):
        """'2 seances muscu' on a week holding one."""
        fb = {"strava_block": "Cette semaine : 1 run (6,4km) + 2 seances muscu."}
        problems = verify_weekly_claims(fb, _overview(strength=1), None)
        assert any("strength sessions" in p for p in problems), problems

    def test_rolling_window_volume_presented_as_the_week(self):
        """'35km cette semaine' when the ISO week held 6.4km."""
        fb = {"strava_block": "Tu totalises 35km cette semaine, belle charge."}
        problems = verify_weekly_claims(fb, _overview(run_km=6.4), None)
        assert any("kilometres" in p for p in problems), problems

    def test_remaining_sessions_understated(self):
        """'il reste 2 seances' when 4 were to do."""
        fb = {"recommendation_next": "Il te reste 2 seances Campus a placer."}
        problems = verify_weekly_claims(fb, _overview(remaining=4), None)
        assert any("remaining" in p for p in problems), problems

    def test_set_count_inflated(self):
        """26 sets claimed on a 25-set session (the trailing xN bug)."""
        fb = {"detailed_analysis": "26 series au total sur cette seance."}
        problems = verify_weekly_claims(fb, _overview(), _session(total_sets=25))
        assert any("total sets" in p for p in problems), problems


class TestCorrectStatementsPass:
    """A verifier that flags correct text is worse than none: it would strip good
    sentences and train the reader to ignore the warnings."""

    def test_exact_figures_pass(self):
        fb = {
            "strava_block": "Cette semaine : 1 course (6,4km) + 1 seance muscu.",
            "detailed_analysis": "25 series, 238 reps, 15370 kg soulevés au total.",
            "recommendation_next": "Il te reste 4 seances Campus.",
        }
        assert verify_weekly_claims(fb, _overview(), _session()) == []

    def test_rounded_kilometres_tolerated(self):
        fb = {"strava_block": "6,5km cette semaine."}
        assert verify_weekly_claims(fb, _overview(run_km=6.42), None) == []

    def test_past_week_figures_are_not_compared_to_this_week(self):
        """weekly_breakdown legitimately reports other weeks."""
        fb = {"detailed_analysis": "La semaine derniere : 4 courses (26.5km), 2 muscu."}
        assert verify_weekly_claims(fb, _overview(runs=1, run_km=6.4), None) == []

    def test_incomplete_counts_disable_weekly_checks(self):
        """When the code itself flagged its counts as incomplete, it cannot arbitrate."""
        fb = {"strava_block": "3 courses cette semaine."}
        assert verify_weekly_claims(fb, _overview(runs=1, incomplete=True), None) == []

    def test_partial_tonnage_is_not_compared(self):
        """A partial tonnage legitimately differs from any stated figure."""
        fb = {"detailed_analysis": "environ 9000 kg soulevés."}
        assert verify_weekly_claims(fb, _overview(), _session(incomplete=True)) == []

    def test_no_figures_no_problems(self):
        fb = {"strava_block": "Belle seance, les sensations reviennent."}
        assert verify_weekly_claims(fb, _overview(), _session()) == []


class TestRobustness:
    """The verifier must never be the reason a coach feedback fails to publish."""

    def test_missing_inputs_are_tolerated(self):
        assert verify_weekly_claims(None, None, None) == []
        assert verify_weekly_claims({}, {}, {}) == []
        assert verify_weekly_claims({"strava_block": None}, _overview(), None) == []

    def test_non_dict_feedback_tolerated(self):
        assert verify_weekly_claims("not a dict", _overview(), None) == []

    def test_unparseable_truth_is_skipped(self):
        fb = {"strava_block": "3 courses cette semaine."}
        ov = _overview()
        ov["done_this_week"]["runs"] = "many"
        assert verify_weekly_claims(fb, ov, None) == []

    def test_sentence_splitting_keeps_newline_fragments_apart(self):
        parts = split_sentences("Premiere phrase.\nDeuxieme ligne. Troisieme !")
        assert len(parts) == 3, parts


class TestStripFalseClaims:
    """Last resort after a failed regeneration."""

    def test_only_the_offending_sentence_is_removed(self):
        fb = {
            "strava_block": (
                "Belle seance upper. Fun fact : 320 reps au total. "
                "Low row qui grimpe a 90kg, belle progression."
            )
        }
        cleaned, removed = strip_false_claims(fb, _overview(), _session())
        assert len(removed) == 1, removed
        assert "320 reps" in removed[0]
        assert "Belle seance upper." in cleaned["strava_block"]
        assert "belle progression" in cleaned["strava_block"]
        assert "320" not in cleaned["strava_block"]

    def test_clean_feedback_is_untouched(self):
        fb = {"strava_block": "238 reps au total, 25 series."}
        cleaned, removed = strip_false_claims(fb, _overview(), _session())
        assert removed == []
        assert cleaned["strava_block"] == "238 reps au total, 25 series."

    def test_all_checked_fields_are_cleaned(self):
        fb = {
            "strava_block": "320 reps au total.",
            "detailed_analysis": "Il te reste 2 seances.",
            "recommendation_next": "Repose-toi 48h.",
        }
        cleaned, removed = strip_false_claims(fb, _overview(), _session())
        assert len(removed) == 2, removed
        assert cleaned["strava_block"] == ""
        assert cleaned["recommendation_next"] == "Repose-toi 48h."


class TestRemainingVersusDone:
    """"il reste 2 muscu" counts sessions TO DO, not sessions done.

    The first version compared any "N muscu" against done_this_week.strength and
    stripped this correct sentence from a live coach output:
    "Il reste 4 seances Campus (3 courses dont 1 PPG) + 2 muscu perso".
    """

    def test_remaining_own_strength_is_not_compared_to_done(self):
        fb = {"recommendation_next": "Il reste 4 seances Campus + 2 muscu perso."}
        assert verify_weekly_claims(fb, _overview(strength=1, remaining=4), None) == []

    def test_wrong_remaining_own_strength_is_still_caught(self):
        fb = {"recommendation_next": "Il te reste 5 seances muscu perso a faire."}
        problems = verify_weekly_claims(fb, _overview(), None)
        assert any("remaining own strength" in p for p in problems), problems

    def test_done_claim_still_checked_when_no_remaining_marker(self):
        fb = {"strava_block": "Cette semaine : 2 seances muscu."}
        problems = verify_weekly_claims(fb, _overview(strength=1), None)
        assert any("strength sessions this week" in p for p in problems), problems


class TestAdvisorySentencesAreNotClaims:
    """Advice carrying a number claims nothing about the week.

    "evite 2 seances muscu consecutives" was stripped from a live output by the
    first version, removing useful coaching for no gain.
    """

    def test_advice_is_not_verified(self):
        fb = {"recommendation_next": "Alterne course et muscu, évite 2 séances muscu consécutives."}
        assert verify_weekly_claims(fb, _overview(strength=1), None) == []

    def test_factual_claim_in_the_same_field_is_still_verified(self):
        fb = {"recommendation_next": "Cette semaine : 2 séances muscu. Évite 2 muscu consécutives."}
        problems = verify_weekly_claims(fb, _overview(strength=1), None)
        assert len(problems) == 1, problems
        assert "strength sessions this week" in problems[0]



class TestWeekScopedByAnySynonym:
    """The week gate must not be defeated by rephrasing.

    Regression fixtures from activity 19616443561 (2026-08-05), the first activity
    processed after the verifier shipped. The coach double-counted the current
    session -- it took the weekly totals, which already include it, and added it
    again -- producing "3 runs" and "21,8km" against a real 2 runs / 14,08km.

    The verifier caught it in the sentence phrased "Cette semaine : ..." and stripped
    it, then PUBLISHED the identical error one sentence earlier because that one
    scoped the week as "Contexte hebdo". The gate was a four-literal allowlist, so
    any synonym walked around it and the athlete read a figure the code had already
    rejected.
    """

    def _week(self):
        """The real computed figures for 2026-W32: 2 runs, 14.08 km, 1 strength."""
        return _overview(runs=2, run_km=14.08, strength=1, remaining=3)

    def test_hebdo_scoped_run_count_is_caught(self):
        """VERBATIM published sentence: 'Contexte hebdo' scopes the week too."""
        fb = {
            "detailed_analysis": (
                "Contexte hebdo : 2 EF (14,1km) + Upper A (DC machine 110kg) "
                "+ cette seance = 3 runs + 1 muscu, frequence coherente."
            )
        }
        problems = verify_weekly_claims(fb, self._week(), None)
        assert problems, "'3 runs' contradicts the computed 2 and must be caught"
        assert any("run count" in p for p in problems)

    def test_correct_kilometres_in_the_same_sentence_still_pass(self):
        """Catching the run count must not also strip the correct 14,1km beside it.

        The verbatim sentence carries both a wrong figure (3 runs) and a correct one
        (14,1km, inside KM_TOLERANCE of the computed 14,08). Only the run count may be
        reported: a fix that also flagged the kilometres would be inventing a mismatch.
        """
        fb = {
            "detailed_analysis": (
                "Contexte hebdo : 2 EF (14,1km) + Upper A (DC machine 110kg) "
                "+ cette seance = 3 runs + 1 muscu, frequence coherente."
            )
        }
        problems = verify_weekly_claims(fb, self._week(), None)
        assert len(problems) == 1, f"expected only the run count to be flagged, got {problems}"
        assert "run count" in problems[0]
        assert not any("kilometres" in p for p in problems)

    def test_speed_is_not_read_as_a_weekly_distance(self):
        """VERBATIM published sentence: '17-18km/h' is a speed, not 18 km.

        The regex matched the 18 because \\b fires on the slash. Comparing it to the
        weekly 14,08 would strip the primary description of the workout.
        """
        fb = {
            "detailed_analysis": (
                "Cette semaine tu as fait 5x30sec rapides (138-150m par fraction, "
                "soit ~17-18km/h) sur la seance Campus."
            )
        }
        assert verify_weekly_claims(fb, self._week(), None) == []

    def test_current_activity_distance_is_not_a_weekly_claim(self):
        """The coach states this session's own distance constantly.

        Without a week marker it must stay unchecked, otherwise every activity's own
        distance gets compared to the weekly total.
        """
        fb = {"detailed_analysis": "Ta sortie de 7,7 km ce soir etait solide."}
        assert verify_weekly_claims(fb, self._week(), None) == []

    def test_other_period_claims_are_not_compared_to_the_week(self):
        """A monthly count is not a weekly count.

        This is why the run count keeps its gate instead of being checked
        unconditionally: 'le mois dernier' is not a week and must not be compared.
        """
        fb = {"detailed_analysis": "Le mois dernier tu avais boucle 12 courses."}
        assert verify_weekly_claims(fb, self._week(), None) == []

    def test_past_week_still_wins_over_the_broadened_marker(self):
        """'la semaine derniere' contains 'semaine' but must remain excluded."""
        fb = {"detailed_analysis": "La semaine derniere : 4 courses (26,5km), 2 muscu."}
        assert verify_weekly_claims(fb, self._week(), None) == []



class TestWeekGateRejectsNonCurrentWeekSentences:
    """Sentences that mention a week but claim nothing about THIS week's totals.

    Each case here was a measured false positive when the gate was briefly widened to a
    bare `semaine|hebdo` stem match. They are pinned because stripping a correct
    sentence is the failure this module holds to be worse than a missed check: it
    removes real coaching and teaches the athlete to ignore the warnings.

    The computed week is 2 runs / 14,08km / 1 strength throughout, so any figure below
    that differs would be flagged if the sentence were wrongly treated as a claim.
    """

    def _week(self):
        return _overview(runs=2, run_km=14.08, strength=1, remaining=3)

    def _assert_not_flagged(self, sentence):
        for field in ("detailed_analysis", "recommendation_next", "strava_block"):
            assert verify_weekly_claims({field: sentence}, self._week(), None) == [], (
                f"{field}: wrongly treated as a current-week claim: {sentence!r}"
            )

    def test_next_week_plan_is_not_a_current_week_claim(self):
        """recommendation_next is a CHECKED_FIELD, so next-week prose is unavoidable."""
        self._assert_not_flagged("La semaine prochaine tu as 4 courses au programme.")

    def test_weekly_average_is_not_a_current_week_claim(self):
        self._assert_not_flagged("Ta moyenne hebdomadaire tourne autour de 3 courses.")

    def test_habitual_weekly_load_is_not_a_current_week_claim(self):
        self._assert_not_flagged("Ta charge hebdo habituelle est de 35km.")

    def test_typical_week_is_not_a_current_week_claim(self):
        self._assert_not_flagged("Une semaine type chez toi : 4 courses pour 30km.")

    def test_weekday_habit_is_not_a_current_week_claim(self):
        self._assert_not_flagged("En semaine tu cales 3 courses avant le travail.")

    def test_numbered_week_is_not_a_current_week_claim(self):
        self._assert_not_flagged("Semaine 32 : 4 courses pour 26,5km.")

    def test_dated_week_is_not_a_current_week_claim(self):
        self._assert_not_flagged("La semaine du 27/07 tu avais boucle 4 courses.")

    def test_a_week_ago_is_not_a_current_week_claim(self):
        """_PAST_WEEK_MARKERS enumerates 'il y a 2/3/4 semaines' but not 'une'."""
        self._assert_not_flagged("Il y a une semaine tu enchainais 4 courses.")

    def test_frequency_phrasings_are_not_current_week_claims(self):
        for sentence in (
            "Tu tournes a 4 courses par semaine depuis mars.",
            "Ton volume est monte a 35km/semaine.",
            "Chaque semaine tu places 4 courses.",
            "Tu es a la semaine a 3 courses.",
            "Sur une semaine tu boucles 4 courses.",
        ):
            self._assert_not_flagged(sentence)

    def test_part_of_week_is_not_a_whole_week_claim(self):
        self._assert_not_flagged("En fin de semaine tu as pose 1 course de plus.")

    def test_multi_week_window_is_not_a_current_week_claim(self):
        """The plural must defeat the 'volume hebdo' shape too."""
        self._assert_not_flagged("Sur ces 3 semaines, ton volume hebdo etait de 30km.")

    def test_remaining_runs_are_not_compared_to_runs_done(self):
        """'il te reste 3 courses' counts sessions TO DO, not sessions completed."""
        self._assert_not_flagged("Il te reste 3 courses cette semaine pour boucler le plan.")


class TestWeekGateStillCatchesRealClaims:
    """The narrowing above must not cost the checks the verifier exists for."""

    def _week(self):
        return _overview(runs=2, run_km=14.08, strength=1, remaining=3)

    def test_recognised_hebdo_shapes_are_checked(self):
        """Each shape the allowlist covers must still catch a wrong run count."""
        for sentence in (
            "Contexte hebdo : 2 EF + cette seance = 3 runs.",
            "Bilan hebdo : 3 courses au compteur.",
            "Recap hebdo : 3 courses.",
            "Volume hebdo : 3 courses cumulees.",
            "Hebdo : 3 courses.",
        ):
            problems = verify_weekly_claims({"detailed_analysis": sentence}, self._week(), None)
            assert problems, f"wrong run count not caught in: {sentence!r}"
            assert any("run count" in p for p in problems)

    def test_original_literal_markers_still_work(self):
        """The four phrasings that predate this change must keep being checked."""
        for sentence in (
            "Cette semaine : 3 courses.",
            "Sur la semaine tu es a 3 courses.",
            "Ta semaine : 3 courses.",
            "Sur la semaine en cours, 3 courses.",
        ):
            problems = verify_weekly_claims({"detailed_analysis": sentence}, self._week(), None)
            assert problems, f"wrong run count not caught in: {sentence!r}"


class TestKilometreUnitGuard:
    """`_KM` must read distances and ignore speeds, without over-rejecting."""

    def _week(self):
        return _overview(runs=2, run_km=14.08, strength=1, remaining=3)

    def test_speeds_are_never_read_as_distances(self):
        for speed in ("~17-18km/h", "18 km/h", "18KM/H", "18km·h"):
            fb = {"detailed_analysis": f"Cette semaine tu as tourne a {speed} sur les fractions."}
            assert verify_weekly_claims(fb, self._week(), None) == [], f"{speed!r} read as a distance"

    def test_a_slash_used_as_a_separator_still_reads_as_a_distance(self):
        """The guard is scoped to a following 'h' so a km lie phrased with '/' is caught."""
        fb = {"detailed_analysis": "Cette semaine : 21,8km / 3 sorties."}
        problems = verify_weekly_claims(fb, self._week(), None)
        assert any("kilometres" in p for p in problems), "21,8km vs 14,08 must still be caught"

    def test_plain_distances_are_still_matched(self):
        for text in ("35km", "26,5km", "7.7 km", "12,5km."):
            fb = {"detailed_analysis": f"Cette semaine tu totalises {text}"}
            assert verify_weekly_claims(fb, self._week(), None), f"{text!r} not read as a distance"
