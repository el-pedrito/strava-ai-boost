"""Tests for session tonnage when the sets come from the Campus plan.

Reason this exists: on 2026-10-13 an audit of the 87 stored strength sessions found the
arithmetic right (87/87) but the INPUT wrong for every Campus renfo: his text gives only
loads ("Split quat avec 2 ketle de 16kg"), the sets and reps live in the Campus plan, so
the LLM extraction stored 0 sets and 0 kg, once even flagged complete.

Athlete rules, authoritative (2026-10-13):
  - for a Campus renfo the sets and reps come from the plan; outside the plan he writes
    everything;
  - the plan's split squat reps are PER LEG ("4 reps" = 4 per leg, 8 in total);
  - he never logs an upper session and a Campus renfo in the same Strava activity.
"""

import copy
import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))
os.environ.setdefault("COACHING_SESSIONS_TABLE", "campus-coaching-sessions")

from processing import modules_processing as mp  # noqa: E402
from shared.campus_structure import (  # noqa: E402
    compute_ppg_volume,
    extract_athlete_loads,
    ppg_history_sets,
)
from shared.strength_exercises import canonicalize_exercise_name  # noqa: E402
from shared.strength_progress import build_exercise_comparisons  # noqa: E402
from shared.strength_volume import compute_session_volume  # noqa: E402

# The real W41 PPG plan, read back from DynamoDB (legacy flat rounds + one block).
with open(os.path.join(os.path.dirname(__file__), "fixtures", "campus_ppg_w41.json")) as fh:
    W41_PPG = json.load(fh)

# Activity 20524818169, verbatim.
TEXT_1010 = (
    "10/07\nRenfo campus course a pied la veille du 20km de paris on gere l’effort\n"
    "Split quat avec 2 ketle de 16kg\nEt mollets à la fin avec 12kg"
)

W33_RENFORCEMENT = {
    "title": "Renforcement",
    "intervals": [
        {
            "type": "block",
            "repeat": 4,
            "exercises": [
                {"type": "work", "name": "Split Squat avec charge additionnelle", "reps": 8},
                {"type": "work", "name": "Gainage Frontal", "duration": "30 sec"},
                {"type": "work", "name": "Extension de Mollet", "reps": 12},
            ],
        },
        {
            "type": "block",
            "repeat": 4,
            "exercises": [
                {"type": "work", "name": "Swing avec charge", "reps": 8},
                {"type": "work", "name": "Gainage Latéral", "duration": "30 sec"},
                {"type": "work", "name": "Mollet statique", "duration": "40 sec"},
            ],
        },
    ],
}
W33_LOADS = {"mollet": 12.0, "split squat": 40.0, "swing": 24.0}


def _by_name(rows):
    return {row["exercise"]: row for row in rows}


def _history_volume(session, loads):
    return compute_session_volume(ppg_history_sets(session, loads), body_weight_kg=92)


class TestPlanSets:
    def test_the_1010_session_rebuilt_from_the_plan(self):
        rows = _by_name(ppg_history_sets(W41_PPG, extract_athlete_loads(TEXT_1010)))
        fentes = rows["Fentes"]
        assert fentes["sides"] == 2
        assert [s["reps"] for s in fentes["sets_detail"]] == [3, 3, 4, 4, 4]
        assert {s["weight_kg"] for s in fentes["sets_detail"]} == {32.0}
        assert [s["reps"] for s in rows["Mollets"]["sets_detail"]] == [12, 12, 12]
        assert rows["Mollets"]["weight_kg"] == 12.0
        assert rows["Swing avec charge"]["weight_kg"] is None
        assert rows["Bond sur place"]["sides"] == 1

    def test_the_1010_totals(self):
        volume = _history_volume(W41_PPG, extract_athlete_loads(TEXT_1010))
        assert volume["total_sets"] == 26
        assert volume["total_reps"] == 162
        assert volume["volume_kg"] == 1584.0
        assert volume["volume_kg_incomplete"] is True
        rows = _by_name(volume["per_exercise"])
        assert (rows["Fentes"]["sets"], rows["Fentes"]["reps"]) == (10, 36)
        assert rows["Fentes"]["volume_kg"] == 1152.0
        assert rows["Mollets"]["volume_kg"] == 432.0
        assert rows["Swing avec charge"]["volume_kg"] is None, "unknown, never 0 kg"

    def test_holds_keep_their_plan_name_and_count_as_sets(self):
        volume = _history_volume(W33_RENFORCEMENT, W33_LOADS)
        rows = _by_name(volume["per_exercise"])
        assert rows["Gainage Frontal"]["sets"] == 4
        assert rows["Gainage Frontal"]["volume_incomplete"] is False, "bodyweight hold"
        assert rows["Mollet statique"]["volume_incomplete"] is True, "loaded hold"
        assert rows["Mollet statique"]["volume_kg"] is None
        assert "Mollets" not in volume["excluded_exercises"]
        assert "Mollet statique" in volume["excluded_exercises"]

    def test_no_loads_invents_nothing(self):
        volume = _history_volume(W41_PPG, {})
        assert volume["volume_kg"] == 0.0
        assert volume["volume_kg_incomplete"] is True
        assert all(row["volume_kg"] is None for row in volume["per_exercise"])


class TestOneTonnagePerSession:
    """The coach's computed_volume and the stored history must say the same thing."""

    def test_parity_on_the_real_w41_plan(self):
        loads = extract_athlete_loads(TEXT_1010)
        plan = compute_ppg_volume(W41_PPG, loads)
        history = _history_volume(W41_PPG, loads)
        for key in ("total_sets", "total_reps", "volume_kg", "volume_kg_incomplete"):
            assert plan[key] == history[key], key

    def test_parity_on_w33_with_holds(self):
        plan = compute_ppg_volume(W33_RENFORCEMENT, W33_LOADS)
        history = _history_volume(W33_RENFORCEMENT, W33_LOADS)
        for key in ("total_sets", "total_reps", "volume_kg", "volume_kg_incomplete"):
            assert plan[key] == history[key], key
        assert plan["volume_kg"] == 3904.0


class TestSessionVolumeRules:
    def test_explicit_sides_doubles_once(self):
        volume = compute_session_volume(
            [{"exercise": "Fentes", "sides": 2, "sets_detail": [{"reps": 4, "weight_kg": 32}]}],
            body_weight_kg=92,
        )
        assert (volume["total_sets"], volume["total_reps"], volume["volume_kg"]) == (2, 8, 256.0)

    def test_explicit_sides_one_overrides_the_unilateral_table(self):
        item = {
            "exercise": "Tirage horizontal unilatéral machine",
            "sets_detail": [{"reps": 10, "weight_kg": 30}],
        }
        assert compute_session_volume([item], 92)["volume_kg"] == 600.0
        assert compute_session_volume([dict(item, sides=1)], 92)["volume_kg"] == 300.0

    def test_invalid_sides_is_ignored(self):
        for bad in (0, -1, "2", 1.5, None):
            item = {"exercise": "Fentes", "sides": bad, "sets_detail": [{"reps": 4, "weight_kg": 10}]}
            assert compute_session_volume([item], 92)["volume_kg"] == 40.0, bad

    def test_listed_exercise_with_nothing_countable_is_incomplete(self):
        """The 10/10 entry stored 0 sets and still said complete."""
        volume = compute_session_volume(
            [{"exercise": "Fentes", "sets_detail": []}, {"exercise": "Mollets", "sets_detail": []}],
            body_weight_kg=92,
        )
        assert volume["volume_kg_incomplete"] is True
        assert volume["excluded_exercises"] == ["Fentes", "Mollets"]


class TestTrackStrengthHistory:
    def _run(self, matched_session):
        from processing import content_generator as cg

        table = MagicMock()
        table.get_item.return_value = {"Item": {}}
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        activity = {
            "description": TEXT_1010,
            "original_description": TEXT_1010,
            "start_date_local": "2026-10-10T08:00:00Z",
            "moving_time": 1920,
        }
        with patch.object(cg, "dynamodb", dynamo), patch.object(
            cg, "_extract_strength_sets", return_value=[]
        ) as extract:
            cg._track_strength_history("u1", "20524818169", activity, matched_session=matched_session)
        entry = table.update_item.call_args.kwargs["ExpressionAttributeValues"][":entry"][0]
        return entry, extract

    def test_a_campus_renfo_uses_the_plan_and_skips_the_llm(self):
        entry, extract = self._run(copy.deepcopy(W41_PPG))
        extract.assert_not_called()
        assert entry["sets_source"] == "campus_plan"
        assert float(entry["volume_kg"]) == 1584.0
        assert int(entry["total_sets"]) == 26

    def test_outside_the_plan_his_text_is_read(self):
        entry, extract = self._run(None)
        extract.assert_called_once()
        assert entry["sets_source"] == "athlete_text"
        assert entry["incomplete_reason"] == "nothing_extracted"


class TestComparisonsIgnorePlanReps:
    def test_a_campus_plan_entry_is_never_the_previous_occurrence(self):
        history = [
            {
                "date": "2026-10-03",
                "sets_source": "campus_plan",
                "parsed_sets": [{"exercise": "Fentes", "sets_detail": [{"reps": 3, "weight_kg": 32}]}],
            }
        ]
        current = [{"exercise": "Fentes", "sets_detail": [{"reps": 4, "weight_kg": 32}]}]
        comparison = build_exercise_comparisons(current, history)[0]
        assert comparison["previous"] is None


def _ppg(session_id, reps=8, **extra):
    session = {
        "session_id": session_id,
        "title": "Renforcement",
        "sport": "ppg",
        "training_type": "PPG",
        "expected_duration_min": 30.0,
        "intervals": [{"type": "block", "repeat": 4.0, "exercises": [
            {"type": "work", "name": "Split Squat avec charge additionnelle", "reps": reps, "duration": ""},
        ]}],
    }
    session.update(extra)
    return session


def _match_with_scores(sessions, scores):
    with patch.object(mp, "_get_recent_campus_sessions", return_value=sessions), patch.object(
        mp, "_score_session_match", side_effect=lambda s, *a, **k: scores[s["session_id"]]
    ):
        return mp.match_campus_session({"type": "WeightTraining", "start_date": "2026-10-10"}, laps=[])


class TestMatcherTies:
    def test_identical_sessions_are_interchangeable(self):
        """Two identical footings must close one after the other, never block."""
        result = _match_with_scores([_ppg("b"), _ppg("a")], {"a": 0.8, "b": 0.8})
        assert result["matched_session"]["session_id"] == "a", "lowest session_id"
        assert result["match_ambiguous"] is False

    def test_different_plans_tied_are_ambiguous(self):
        result = _match_with_scores([_ppg("a", reps=8), _ppg("b", reps=10)], {"a": 0.8, "b": 0.8})
        assert result["matched_session"] is None
        assert result["match_ambiguous"] is True

    def test_a_later_unique_best_clears_an_earlier_tie(self):
        result = _match_with_scores(
            [_ppg("a", reps=8), _ppg("b", reps=10), _ppg("c", reps=12)],
            {"a": 0.6, "b": 0.6, "c": 0.9},
        )
        assert result["matched_session"]["session_id"] == "c"
        assert result["match_ambiguous"] is False

    def test_signature_ignores_what_may_differ_between_identical_sessions(self):
        base = _ppg("a")
        other = _ppg(
            "z",
            training_index=3.0, importance=False, coach_advice="x", description="y",
            is_current_week=True, is_future=False, synced_at="now", provider_status="done",
            session_date="week-2026-W41", matched_activity_id="123",
        )
        assert mp._session_signature(base) == mp._session_signature(other)

    def test_signature_normalizes_numbers_and_empty_fields(self):
        a = _ppg("a")
        b = _ppg("b")
        b["intervals"][0]["repeat"] = 4
        b["intervals"][0]["exercises"][0]["reps"] = 8.0
        del b["intervals"][0]["exercises"][0]["duration"]
        assert mp._session_signature(a) == mp._session_signature(b)

    def test_signature_sees_exercise_name_and_reps(self):
        assert mp._session_signature(_ppg("a", reps=8)) != mp._session_signature(_ppg("a", reps=10))


class TestExtractionFixes:
    def test_larry_scott_joins_the_curl_biceps_series(self):
        for name in ("Curl Larry Scott", "biceps larry scott", "biceps larry scott guide"):
            assert canonicalize_exercise_name(name) == "Curl biceps", name

    def test_the_lost_face_pull_set_is_taught_to_the_extractor(self):
        from processing.content_generator import _STRENGTH_EXTRACTION_SYSTEM_PROMPT

        assert "'Face pull 40 10 45 2x10'" in _STRENGTH_EXTRACTION_SYSTEM_PROMPT
