"""Tests for the lap facts handed to the coach.

Fixtures are the real laps of the two audited runs, read from ``laps_json``.

What the deployed pipeline did with them:
  * it published "les 4 fractions actives (5min a 3:16/km)" when the real pace was 5:23
    to 5:26. 3:16 is the ``max_speed`` of lap 1 (3.26 m/s) read as a decimal minute
    count. Nothing else in the activity produces that value;
  * it called laps covering 179 to 229 m in two minutes "recup passive";
  * it announced "5 fractions courtes" on a session holding six efforts.

Hence the three rules pinned below: pace comes from ``average_speed`` alone and is
formatted in code, ``max_speed`` never reaches the model, and work versus recovery is
decided by relative contrast, never by an absolute ``pace_zone`` threshold. That last
point matters because the two sessions disagree: the 16/08 efforts sit in zones 5 and 6
while the 15/08 fractions sit in zone 2, below their own recoveries' neighbours.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared.lap_facts import build_lap_facts  # noqa: E402

# 2026-08-15 "Sortie Longue & Active": 25min warmup, 4x5min tempo, 2min recoveries.
LAPS_LONG_RUN = [
    {"lap_index": 1, "distance": 3859, "moving_time": 1499, "average_speed": 2.57, "max_speed": 3.26, "pace_zone": 1},
    {"lap_index": 2, "distance": 920, "moving_time": 299, "average_speed": 3.08, "max_speed": 3.92, "pace_zone": 2},
    {"lap_index": 3, "distance": 179, "moving_time": 120, "average_speed": 1.49, "max_speed": 3.80, "pace_zone": 1},
    {"lap_index": 4, "distance": 918, "moving_time": 300, "average_speed": 3.06, "max_speed": 3.84, "pace_zone": 2},
    {"lap_index": 5, "distance": 200, "moving_time": 119, "average_speed": 1.68, "max_speed": 3.48, "pace_zone": 1},
    {"lap_index": 6, "distance": 923, "moving_time": 300, "average_speed": 3.08, "max_speed": 3.80, "pace_zone": 2},
    {"lap_index": 7, "distance": 210, "moving_time": 120, "average_speed": 1.75, "max_speed": 3.18, "pace_zone": 1},
    {"lap_index": 8, "distance": 926, "moving_time": 300, "average_speed": 3.09, "max_speed": 3.67, "pace_zone": 2},
    {"lap_index": 9, "distance": 229, "moving_time": 119, "average_speed": 1.92, "max_speed": 3.50, "pace_zone": 1},
    {"lap_index": 10, "distance": 1903, "moving_time": 721, "average_speed": 2.64, "max_speed": 3.44, "pace_zone": 1},
    # 12 m in 4 s, and max_speed BELOW average_speed: physically impossible.
    {"lap_index": 11, "distance": 12, "moving_time": 4, "average_speed": 3.10, "max_speed": 2.56, "pace_zone": 2},
]

# 2026-08-16 "Endurance de Force": 20min warmup, 2 blocks of 35-25-15s, 10min cooldown.
LAPS_ENDURANCE_FORCE = [
    {"lap_index": 1, "distance": 3112, "moving_time": 1200, "average_speed": 2.59, "max_speed": 4.37, "pace_zone": 1},
    {"lap_index": 2, "distance": 142, "moving_time": 34, "average_speed": 4.19, "max_speed": 4.84, "pace_zone": 6},
    {"lap_index": 3, "distance": 390, "moving_time": 180, "average_speed": 2.17, "max_speed": 4.24, "pace_zone": 1},
    {"lap_index": 4, "distance": 101, "moving_time": 25, "average_speed": 4.04, "max_speed": 4.43, "pace_zone": 6},
    {"lap_index": 5, "distance": 417, "moving_time": 179, "average_speed": 2.33, "max_speed": 4.30, "pace_zone": 1},
    {"lap_index": 6, "distance": 59, "moving_time": 15, "average_speed": 3.95, "max_speed": 4.92, "pace_zone": 5},
    {"lap_index": 7, "distance": 777, "moving_time": 300, "average_speed": 2.59, "max_speed": 4.87, "pace_zone": 1},
    {"lap_index": 8, "distance": 149, "moving_time": 35, "average_speed": 4.26, "max_speed": 5.87, "pace_zone": 6},
    {"lap_index": 9, "distance": 408, "moving_time": 180, "average_speed": 2.27, "max_speed": 4.46, "pace_zone": 1},
    {"lap_index": 10, "distance": 105, "moving_time": 25, "average_speed": 4.22, "max_speed": 4.96, "pace_zone": 6},
    {"lap_index": 11, "distance": 443, "moving_time": 180, "average_speed": 2.46, "max_speed": 5.14, "pace_zone": 1},
    {"lap_index": 12, "distance": 61, "moving_time": 15, "average_speed": 4.09, "max_speed": 4.83, "pace_zone": 6},
    {"lap_index": 13, "distance": 755, "moving_time": 300, "average_speed": 2.52, "max_speed": 4.96, "pace_zone": 1},
    {"lap_index": 14, "distance": 1525, "moving_time": 600, "average_speed": 2.54, "max_speed": 3.20, "pace_zone": 1},
    {"lap_index": 15, "distance": 7, "moving_time": 5, "average_speed": 1.36, "max_speed": 2.76, "pace_zone": 1},
]


class TestPaceComesFromAverageSpeedOnly:
    def test_the_tempo_fractions_read_5_24_not_3_16(self):
        facts = build_lap_facts(LAPS_LONG_RUN)
        by_index = {lap["index"]: lap for lap in facts["laps"]}
        assert by_index[2]["pace_per_km"] == "5:24"
        assert by_index[4]["pace_per_km"] == "5:26"
        assert by_index[8]["pace_per_km"] == "5:23"

    def test_max_speed_never_appears_in_the_facts(self):
        """3:16 came from max_speed 3.26 read as a pace. The field must not travel."""
        facts = build_lap_facts(LAPS_LONG_RUN)
        assert "3:16" not in repr(facts)
        for lap in facts["laps"]:
            assert "max_speed" not in lap
            assert "max_pace" not in lap
        assert facts["quality"]["speed_fields_excluded"] is True

    def test_no_bare_speed_value_is_exposed(self):
        """A bare 3.26 reads as 3:16. Any speed must carry its unit in the key."""
        for lap in build_lap_facts(LAPS_LONG_RUN)["laps"]:
            for key in lap:
                assert "speed" not in key


class TestWorkAndRecoveryByRelativeContrast:
    def test_the_long_run_holds_four_work_fractions(self):
        facts = build_lap_facts(LAPS_LONG_RUN)
        assert facts["work_reps"]["count"] == 4
        assert [lap["index"] for lap in facts["laps"] if lap["role"] == "work"] == [2, 4, 6, 8]

    def test_the_endurance_force_holds_six_efforts_not_five(self):
        """The published feedback said five. pace_zone thresholds would also fail here."""
        facts = build_lap_facts(LAPS_ENDURANCE_FORCE)
        assert facts["work_reps"]["count"] == 6
        assert [lap["index"] for lap in facts["laps"] if lap["role"] == "work"] == [
            2, 4, 6, 8, 10, 12
        ]

    def test_zone_two_fractions_are_still_recognised_as_work(self):
        """The 15/08 fractions sit in pace_zone 2, so no absolute zone rule can work."""
        facts = build_lap_facts(LAPS_LONG_RUN)
        work = [lap for lap in facts["laps"] if lap["role"] == "work"]
        assert all(lap["pace_zone"] == 2 for lap in work)

    def test_warmup_and_cooldown_are_not_counted_as_efforts(self):
        facts = build_lap_facts(LAPS_ENDURANCE_FORCE)
        by_index = {lap["index"]: lap for lap in facts["laps"]}
        assert by_index[1]["role"] == "warmup"
        assert by_index[14]["role"] == "cooldown"


class TestRecoveryMode:
    def test_two_hundred_metres_in_two_minutes_is_active_not_passive(self):
        facts = build_lap_facts(LAPS_LONG_RUN)
        assert facts["recovery"]["mode"] == "active"
        assert facts["recovery"]["count"] == 4
        assert facts["recovery"]["distances_m"] == [179, 200, 210, 229]

    def test_recovery_paces_are_reported(self):
        facts = build_lap_facts(LAPS_LONG_RUN)
        assert facts["recovery"]["paces"][0] == "11:11"


class TestBlockStructure:
    def test_two_blocks_of_three_efforts_are_detected(self):
        facts = build_lap_facts(LAPS_ENDURANCE_FORCE)
        assert facts["blocks"] == [{"repeat": 2, "pattern_s": [34, 25, 15]}]

    def test_a_uniform_series_is_one_repeated_effort(self):
        facts = build_lap_facts(LAPS_LONG_RUN)
        assert facts["blocks"] == [{"repeat": 4, "pattern_s": [299]}]


class TestQualityGuards:
    def test_a_lap_whose_max_is_below_its_average_is_flagged(self):
        facts = build_lap_facts(LAPS_LONG_RUN)
        assert 11 in facts["quality"]["aberrant_laps"]

    def test_an_aberrant_lap_is_excluded_from_the_effort_count(self):
        """Lap 11 is 12 m in 4 s: fast on paper, not an effort."""
        facts = build_lap_facts(LAPS_LONG_RUN)
        assert 11 not in [lap["index"] for lap in facts["laps"] if lap["role"] == "work"]

    def test_never_raises_on_malformed_input(self):
        assert build_lap_facts(None)["work_reps"]["count"] == 0
        assert build_lap_facts([])["laps"] == []
        assert build_lap_facts([{"nonsense": 1}])["work_reps"]["count"] == 0
