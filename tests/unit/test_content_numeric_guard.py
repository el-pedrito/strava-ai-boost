"""Full-chain tests for the lap-pace and strength-load checks of the content guard.

Every test goes build_content_facts -> verify_content on the sentence as the content
agent would publish it, never on the regex alone: a guard that never fires passes every
negative test (AGENTS.md, Hard-Won Gotchas).

The cases are the two families the athlete corrected by hand between August and
October 2026: a block pace no lap carries (4:41 for a 4:33 lap) and a strength load
swapped between exercises (12 kg put on the split squat he did with 2 x 16 kg).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from processing.content_guard import (  # noqa: E402
    apply_content_guard,
    build_content_facts,
    verify_content,
)


def _speed(pace: str) -> float:
    """m/s giving exactly this mm:ss pace (pace truncated, so aim mid-second)."""
    minutes, seconds = pace.split(":")
    return 1000.0 / (int(minutes) * 60 + int(seconds) + 0.4)


# Warm-up, three blocks at 4:33 / 4:34 / 4:37, recoveries, cool-down.
RUN_LAPS = [
    {"lap_index": 1, "distance": 2000, "moving_time": 660, "average_speed": _speed("5:30"), "max_speed": 5.2},
    {"lap_index": 2, "distance": 2000, "moving_time": 546, "average_speed": _speed("4:33"), "max_speed": 5.2},
    {"lap_index": 3, "distance": 400, "moving_time": 180, "average_speed": _speed("7:30")},
    {"lap_index": 4, "distance": 2000, "moving_time": 548, "average_speed": _speed("4:34")},
    {"lap_index": 5, "distance": 400, "moving_time": 180, "average_speed": _speed("7:30")},
    {"lap_index": 6, "distance": 2000, "moving_time": 554, "average_speed": _speed("4:37")},
    {"lap_index": 7, "distance": 1500, "moving_time": 500, "average_speed": _speed("5:33")},
]
RUN_ACTIVITY = {
    "type": "Run",
    "moving_time": 3168,
    "start_date_local": "2026-09-10T18:30:00Z",
    "description": "3x2km",
}


def _run_problems(description: str):
    facts = build_content_facts(RUN_ACTIVITY, RUN_LAPS, [])
    return verify_content({"title": "Seuil 3x2km", "description": description}, facts)


class TestLapPaces:
    def test_correct_block_paces_pass(self):
        assert _run_problems(
            "Trois blocs de 2 km tenus en 4:33, 4:34 puis 4:37/km, avec 400 m de récup trottée."
        ) == []

    def test_wrong_block_pace_fails(self):
        problems = _run_problems("Le deuxième bloc est sorti à 4:41/km, un peu au-dessus.")
        assert len(problems) == 1
        assert "4:41/km ne correspond à aucun lap" in problems[0]
        assert "4:33" in problems[0]  # the real lap paces are listed for the retry

    def test_wrong_pace_inside_block_list_fails(self):
        problems = _run_problems("Blocs en 4:33, 4:41 puis 4:37/km.")
        assert len(problems) == 1 and "4:41" in problems[0]

    def test_target_pace_not_flagged(self):
        assert _run_problems(
            "Allure cible 4:35/km sur les blocs, tenue sans forcer."
        ) == []

    def test_enduraw_adjusted_pace_not_flagged(self):
        assert _run_problems(
            "Enduraw donne une allure ajustée de 5:16/km sur les fractions malgré la chaleur."
        ) == []

    def test_best_effort_not_flagged(self):
        assert _run_problems("Record personnel au passage sur le premier bloc : 1K en 4:32.") == []
        assert _run_problems("Sur le bloc 1, 1K en 4:20/km au meilleur passage.") == []

    def test_whole_activity_average_not_flagged(self):
        assert _run_problems("Les blocs s'enchaînent, 4:58/km de moyenne sur la sortie.") == []

    def test_zone_range_not_flagged(self):
        assert _run_problems("Récup entre les blocs en zone EF, 5:20-5:50/km.") == []

    def test_pace_without_lap_word_not_flagged(self):
        assert _run_problems("Belle soirée à 4:50/km le long du canal.") == []

    def test_impossible_seconds_always_flagged(self):
        problems = _run_problems("Allure cible 4:75/km.")
        assert any("4:75/km invalide" in p for p in problems)

    def test_no_laps_no_verdict(self):
        facts = build_content_facts(RUN_ACTIVITY, None, [])
        assert verify_content({"description": "Bloc à 4:41/km."}, facts) == []

    def test_strip_removes_only_the_wrong_sentence(self):
        content = {
            "title": "Seuil 3x2km",
            "description": "Échauffement tranquille. Le deuxième bloc est sorti à 4:41/km. Bonne séance.",
        }
        out, problems, removed = apply_content_guard(content, RUN_ACTIVITY, RUN_LAPS, [], None)
        assert problems and removed == ["Le deuxième bloc est sorti à 4:41/km."]
        assert out["description"] == "Échauffement tranquille. Bonne séance."

    def test_regeneration_fixes_it(self):
        bad = {"title": "Seuil", "description": "Bloc 2 à 4:41/km."}
        good = {"title": "Seuil", "description": "Bloc 2 à 4:34/km."}
        seen = []

        def regenerate(problems):
            seen.append(problems)
            return good

        out, problems, removed = apply_content_guard(bad, RUN_ACTIVITY, RUN_LAPS, [], regenerate)
        assert out == good and problems == [] and removed == []
        assert "4:41" in seen[0][0]


# --- Strength loads ------------------------------------------------------------

CAMPUS_MODULES = [
    {
        "name": "campus_coach",
        "matched_session": {
            "title": "Renforcement",
            "expected_duration_min": 30,
            "intervals": [
                {
                    "type": "block",
                    "repeat": 4,
                    "exercises": [
                        {"type": "work", "name": "Split Squat avec charge additionnelle", "reps": 8},
                        {"type": "work", "name": "Extension de Mollet", "reps": 12},
                        {"type": "work", "name": "Gainage frontal", "duration": 30},
                    ],
                },
            ],
        },
    }
]
STRENGTH_ACTIVITY = {
    "type": "WeightTraining",
    "moving_time": 1900,
    "start_date_local": "2026-09-20T18:00:00Z",
    "original_description": "Renfo campus. Split squat 2 kettlebells 16kg, mollet 12kg.",
}


def _strength_problems(description: str, activity=STRENGTH_ACTIVITY, modules=CAMPUS_MODULES):
    facts = build_content_facts(activity, None, modules)
    return verify_content({"title": "Renfo Campus", "description": description}, facts)


class TestStrengthLoads:
    def test_swapped_load_fails(self):
        problems = _strength_problems(
            "Split squat avec 2 kettlebells de 12 kg et extensions de mollet à 16 kg."
        )
        assert len(problems) == 2
        assert any("12 kg attribuée à fente" in p for p in problems)
        assert any("16 kg attribuée à mollet" in p for p in problems)

    def test_correct_loads_pass(self):
        assert _strength_problems(
            "Split squat avec 2 kettlebells de 16 kg et extensions de mollet à 12 kg."
        ) == []

    def test_total_moved_with_dual_implement_passes(self):
        # 2 x 16 kg is 32 kg moved: the other correct reading.
        assert _strength_problems("Split squat à 32 kg au total des deux kettlebells.") == []

    def test_per_side_load_passes(self):
        activity = {
            "type": "WeightTraining",
            "moving_time": 3300,
            "start_date_local": "2026-09-22T12:00:00Z",
            "original_description": "Upper A. Développé couché haltères 4x8 40/c, tractions 4x8.",
        }
        assert _strength_problems(
            "Développé couché haltères en 4x8 à 40 kg par côté, propre.", activity, []
        ) == []
        assert _strength_problems(
            "Développé couché haltères : 80 kg déplacés par série.", activity, []
        ) == []
        problems = _strength_problems("Développé couché haltères à 35 kg par côté.", activity, [])
        assert len(problems) == 1 and "35 kg" in problems[0]

    def test_own_program_loads_from_description(self):
        activity = {
            "type": "WeightTraining",
            "moving_time": 3300,
            "start_date_local": "2026-07-15T12:15:00Z",
            "description": "Upper A. Développé couché 4x8 @70kg, développé militaire 3x10 @35kg.",
        }
        assert _strength_problems(
            "Développé couché 4x8 à 70 kg, développé militaire à 35 kg.", activity, []
        ) == []
        problems = _strength_problems("Développé militaire à 70 kg.", activity, [])
        assert len(problems) == 1

    def test_volume_and_previous_session_not_flagged(self):
        assert _strength_problems(
            "Split squat : 1024 kg de volume total. Mollet à 10 kg la semaine dernière."
        ) == []

    def test_not_a_strength_activity_no_check(self):
        facts = build_content_facts(dict(STRENGTH_ACTIVITY, type="Run"), None, CAMPUS_MODULES)
        assert verify_content({"description": "Split squat à 12 kg."}, facts) == []

    def test_strip_removes_swapped_sentence(self):
        content = {
            "title": "Renfo Campus",
            "description": "Séance complète. Split squat avec 2 kettlebells de 12 kg. Gainage solide.",
        }
        out, problems, removed = apply_content_guard(
            content, STRENGTH_ACTIVITY, None, CAMPUS_MODULES, None
        )
        assert problems and removed == ["Split squat avec 2 kettlebells de 12 kg."]
        assert "12 kg" not in out["description"]
