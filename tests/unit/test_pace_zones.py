"""Tests for shared/pace_zones.py and its coach_chat mirror (docs/design/campus-paces.md B).

One reader rule for every consumer: Campus zones first (``campus`` / ``campus_stale``),
then the legacy manual zones (``manual_legacy``), else ``none``. The coach_chat runtime
carries a local copy (its bundle cannot import ``lambda_functions/shared/``); the parity
class below fails as soon as the two disagree.
"""

import importlib.util
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared import pace_zones as pz  # noqa: E402

_MIRROR_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "src", "coach_chat", "pace_zones.py"
)
_spec = importlib.util.spec_from_file_location("coach_chat_pace_zones_mirror", _MIRROR_PATH)
mirror = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mirror)

# Saturday of ISO week 2026-W42.
NOW = datetime(2026, 10, 17, 8, 0, tzinfo=timezone.utc)
CAMPUS = {"ef": {"min": "5:36", "max": "6:02", "slug": "ef",
                 "value_s": Decimal("348.8"), "dvalue_s": Decimal("13.0")}}
MANUAL = {"ef": {"min": "5:40", "max": "6:10"}}


def _estimated():
    """A complete synthetic estimated_paces map (one entry per mapped slug)."""
    base = 300.0
    return {slug: {"value": Decimal(str(base + i * 10)), "dvalue": Decimal("10.0")}
            for i, slug in enumerate(pz.CAMPUS_ZONE_SLUGS.values())}


# Every input shape the readers can meet. Each one is checked against both modules.
PARITY_CASES = (
    None,
    "not a dict",
    {},
    {"user_preferences": None},
    {"user_preferences": {"pace_zones": MANUAL}},
    {"user_preferences": {"pace_zones": {}}},
    {"user_preferences": {"pace_zones": "bad"}},
    {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": "2026-W42"},
    {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": "2026-W41"},
    {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": "2026-W40"},
    {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": "garbage"},
    {"campus_pace_zones": CAMPUS},
    {"campus_pace_zones": {}, "user_preferences": {"pace_zones": MANUAL}},
    {"campus_pace_zones": "bad", "user_preferences": {"pace_zones": MANUAL}},
    {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": "2026-W42",
     "user_preferences": {"pace_zones": MANUAL}},
)


class TestEffectivePaceZones:
    def test_campus_current_week_wins_over_manual(self):
        item = {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": "2026-W42",
                "user_preferences": {"pace_zones": MANUAL}}
        assert pz.effective_pace_zones(item, NOW) == (CAMPUS, pz.SOURCE_CAMPUS)

    def test_previous_week_is_still_fresh(self):
        item = {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": "2026-W41"}
        assert pz.effective_pace_zones(item, NOW)[1] == pz.SOURCE_CAMPUS

    def test_two_weeks_old_is_stale_but_still_used(self):
        item = {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": "2026-W40",
                "user_preferences": {"pace_zones": MANUAL}}
        assert pz.effective_pace_zones(item, NOW) == (CAMPUS, pz.SOURCE_CAMPUS_STALE)

    def test_unparseable_week_is_stale(self):
        item = {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": "W42"}
        assert pz.effective_pace_zones(item, NOW)[1] == pz.SOURCE_CAMPUS_STALE

    def test_manual_legacy_fallback(self):
        item = {"user_preferences": {"pace_zones": MANUAL}}
        assert pz.effective_pace_zones(item, NOW) == (MANUAL, pz.SOURCE_MANUAL_LEGACY)

    def test_empty_campus_map_counts_as_absent(self):
        item = {"campus_pace_zones": {}, "user_preferences": {"pace_zones": MANUAL}}
        assert pz.effective_pace_zones(item, NOW) == (MANUAL, pz.SOURCE_MANUAL_LEGACY)

    def test_nothing_is_none(self):
        assert pz.effective_pace_zones({}, NOW) == ({}, pz.SOURCE_NONE)
        assert pz.effective_pace_zones(None, NOW) == ({}, pz.SOURCE_NONE)

    def test_rollback_remove_returns_to_legacy(self):
        """REMOVE of the three top-level attributes is the whole rollback, no reader redeploy."""
        item = {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": "2026-W42",
                "campus_pace_zones_synced_at": "x", "user_preferences": {"pace_zones": MANUAL}}
        for key in ("campus_pace_zones", "campus_pace_zones_week", "campus_pace_zones_synced_at"):
            item.pop(key)
        assert pz.effective_pace_zones(item, NOW)[1] == pz.SOURCE_MANUAL_LEGACY
        assert mirror.effective_pace_zones(item, NOW)[1] == mirror.SOURCE_MANUAL_LEGACY


class TestMirrorParity:
    def test_every_case_agrees(self):
        for case in PARITY_CASES:
            assert mirror.effective_pace_zones(case, NOW) == pz.effective_pace_zones(case, NOW), case

    def test_source_labels_agree(self):
        for name in ("SOURCE_CAMPUS", "SOURCE_CAMPUS_STALE", "SOURCE_MANUAL_LEGACY", "SOURCE_NONE"):
            assert getattr(mirror, name) == getattr(pz, name), name

    def test_mirror_is_pure(self):
        """The mirror must stay importable in the coach_chat bundle: stdlib only."""
        with open(_MIRROR_PATH, encoding="utf-8") as fh:
            source = fh.read()
        assert "import boto3" not in source and "from shared" not in source


class TestFmtPace:
    def test_half_up_rounding(self):
        # 348.8 - 13.3 = 335.5 must read 5:36 (half-even round() would print 5:35).
        assert pz.fmt_pace(335.5) == "5:36"
        assert pz.fmt_pace(Decimal("348.8") + Decimal("13.0")) == "6:02"
        assert pz.fmt_pace(335.8) == "5:36"
        assert pz.fmt_pace(335.4) == "5:35"

    def test_invalid_is_empty(self):
        for bad in (None, 0, -5, "x", float("nan"), float("inf"), True):
            assert pz.fmt_pace(bad) == "", bad

    def test_minute_carry(self):
        assert pz.fmt_pace(359.6) == "6:00"


class TestBuildCampusZones:
    def test_complete_map_builds_every_zone(self):
        zones = pz.build_campus_zones(_estimated())
        assert set(zones) == set(pz.CAMPUS_ZONE_SLUGS)
        ef = zones["ef"]
        assert ef["slug"] == "ef"
        assert ef["min"] < ef["max"]  # min is the FAST bound

    def test_ef_example_from_the_spec(self):
        estimated = _estimated()
        estimated["ef"] = {"value": Decimal("348.8"), "dvalue": Decimal("13.0")}
        ef = pz.build_campus_zones(estimated)["ef"]
        # value -> value + 30 s, as the Campus app shows (349 -> "5:49 - 6:19").
        assert (ef["min"], ef["max"]) == ("5:49", "6:19")
        assert (ef["value_s"], ef["dvalue_s"]) == (Decimal("348.8"), Decimal("13.0"))

    def test_ef_range_matches_the_campus_app_screens(self):
        """EF 346 -> 5:46-6:16 and 349 -> 5:49-6:19 (6 Campus screens, 2026-10-17)."""
        for value, expected in ((Decimal("346"), ("5:46", "6:16")),
                                (Decimal("349"), ("5:49", "6:19")),
                                (Decimal("345.5"), ("5:46", "6:16"))):
            estimated = _estimated()
            estimated["ef"] = {"value": value, "dvalue": Decimal("13.0")}
            ef = pz.build_campus_zones(estimated)["ef"]
            assert (ef["min"], ef["max"]) == expected, value

    def test_single_value_slug_zone_is_one_pace(self):
        """Campus shows tempo as one pace ("5:15"): min == max, no invented width."""
        estimated = _estimated()
        estimated["tempo"] = {"value": Decimal("315"), "dvalue": Decimal("8.0")}
        tempo = pz.build_campus_zones(estimated)["tempo"]
        assert (tempo["min"], tempo["max"]) == ("5:15", "5:15")
        assert "tempo" not in pz.CAMPUS_RANGE_SLUGS

    def test_ef_zone_is_value_plus_30s(self):
        """Campus shows EF as "5:46 - 6:16": value, then +30 s."""
        estimated = _estimated()
        estimated["ef"] = {"value": Decimal("346"), "dvalue": Decimal("12.0")}
        ef = pz.build_campus_zones(estimated)["ef"]
        assert (ef["min"], ef["max"]) == ("5:46", "6:16")

    def test_zero_or_missing_dvalue_still_builds(self):
        """The spread is not used any more, so 0 or absent is fine."""
        for entry in ({"value": 346, "dvalue": 0}, {"value": 346, "dvalue": Decimal("0.0")},
                      {"value": 346}):
            estimated = _estimated()
            estimated["ef"] = entry
            assert pz.build_campus_zones(estimated)["ef"]["min"] == "5:46", entry

    def test_missing_slug_builds_nothing(self):
        estimated = _estimated()
        estimated.pop("vma")
        assert pz.build_campus_zones(estimated) is None

    def test_invalid_numbers_build_nothing(self):
        for bad in ({"value": "x", "dvalue": 1}, {"value": 10, "dvalue": 20},
                    {"value": float("nan"), "dvalue": 1}, {"value": 300, "dvalue": -1},
                    {"value": 119, "dvalue": 1}, {"value": 901, "dvalue": 1}, "bad"):
            estimated = _estimated()
            estimated["ef"] = bad
            assert pz.build_campus_zones(estimated) is None, bad

    def test_not_a_dict_builds_nothing(self):
        assert pz.build_campus_zones(None) is None
        assert pz.build_campus_zones([]) is None

    def test_campus_zones_feed_the_workout_classifier(self):
        """The classifier reads the Campus map as is (extra keys, Decimal values)."""
        sys.modules.setdefault("agents", MagicMock())
        from processing import workout_analysis as wa
        zones = pz.build_campus_zones(_estimated())
        for key, zone in zones.items():
            midpoint = (wa._parse_pace_mmss(zone["min"]) + wa._parse_pace_mmss(zone["max"])) / 2
            assert wa._classify_by_pace_zones(midpoint, {key: zone}) is not None, key


CAMPUS_ITEM = {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": "2026-W42",
               "user_preferences": {"pace_zones": MANUAL}}


class TestReaders:
    """Every Lambda reader goes through effective_pace_zones (Campus wins over manual)."""

    def test_content_generator_uses_campus_zones(self):
        from processing.content_generator import build_user_profile_from_config
        profile = build_user_profile_from_config(dict(CAMPUS_ITEM))
        assert profile["pace_zones"] == CAMPUS

    def test_content_generator_resolves_before_the_no_preferences_return(self):
        """Campus zones and no saved preferences: still a profile carrying the zones."""
        from processing.content_generator import build_user_profile_from_config
        item = {"campus_pace_zones": CAMPUS, "campus_pace_zones_week": "2026-W42"}
        profile = build_user_profile_from_config(item)
        assert profile is not None and profile["pace_zones"] == CAMPUS

    def test_content_generator_without_anything_is_none(self):
        from processing.content_generator import build_user_profile_from_config
        assert build_user_profile_from_config({}) is None

    def test_coach_generator_puts_effective_zones_in_user_config(self):
        sys.modules.setdefault("agents", MagicMock())
        from processing.coach_generator import with_effective_pace_zones
        event_copy = {"user_preferences": {"pace_zones": MANUAL, "max_hr": 190}}
        out = with_effective_pace_zones(event_copy, CAMPUS_ITEM)
        assert out["user_preferences"]["pace_zones"] == CAMPUS
        assert out["user_preferences"]["max_hr"] == 190
        # Inputs are never mutated.
        assert event_copy["user_preferences"]["pace_zones"] == MANUAL

    def test_coach_generator_keeps_manual_without_campus(self):
        sys.modules.setdefault("agents", MagicMock())
        from processing.coach_generator import with_effective_pace_zones
        out = with_effective_pace_zones({"user_preferences": {"pace_zones": MANUAL}}, {})
        assert out["user_preferences"]["pace_zones"] == MANUAL

    def test_weekly_audio_recap_prompt_carries_campus_zones(self):
        import json
        from unittest.mock import patch
        from support import weekly_audio_recap as war
        body = MagicMock()
        body.read.return_value = json.dumps({"content": [{"type": "text", "text": "ok"}]})
        with patch.object(war, "bedrock") as bedrock, \
                patch.object(war, "_retrieve_memory_observations", return_value=""), \
                patch.object(war, "_get_campus_goal_context", return_value=""), \
                patch.object(war, "no_thinking", return_value={}):
            bedrock.invoke_model.return_value = {"body": body}
            war._generate_script([], "", "fr", "2026-W42", user_config=dict(CAMPUS_ITEM))
        sent = json.loads(bedrock.invoke_model.call_args.kwargs["body"])
        user_msg = sent["messages"][0]["content"]
        assert "ef: 5:36-6:02/km" in user_msg
        assert "5:40-6:10" not in user_msg
