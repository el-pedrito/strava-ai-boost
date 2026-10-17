"""Campus paces in the sync (docs/design/campus-paces.md section A).

Structured pace fields per step, ``estimated_paces`` per session, and the zone write on
the owner's user-config item behind ``CAMPUS_ZONES_ENABLED`` (default off). The zone
write runs against moto so the UpdateItem / ConditionExpression semantics are DynamoDB's.
"""

import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import boto3
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from webhooks import campus_coach_sync as sync  # noqa: E402
from shared.pace_zones import CAMPUS_ZONE_SLUGS  # noqa: E402

OWNER = "owner-1"
REGION = "eu-west-1"


def _estimated_list():
    """Synthetic week.estimatedPaces: every mapped slug plus two extra ones."""
    out = [{"slug": slug, "value": 300.0 + i * 10.25, "dvalue": 9.96, "abstract": False}
           for i, slug in enumerate(CAMPUS_ZONE_SLUGS.values())]
    out.append({"slug": "10km", "value": 251.0, "dvalue": 5.0})
    out.append({"slug": "ef", "value": 999.0, "dvalue": 1.0})  # duplicate: ignored
    return out


def _week(monday_ms, paces=None):
    return {
        "access": "allowed",
        "weekDate": monday_ms,
        "context": {},
        "estimatedPaces": _estimated_list() if paces is None else paces,
        "sessions": [{
            "displayName": "Footing", "sport": "road", "stats": {},
            "exercisesBlocks": [{"blockType": "work", "repeat": 1, "exercises": [{
                "exerciseType": "work",
                "durations": [{"value": 40, "timeUnit": "minutes"}],
                "pace": {"name": "EF", "value": 348.8, "kind": "range", "zoneKind": "ef",
                         "abstract": False, "slug": "ef"},
            }]}],
        }],
    }


class _Env:
    """moto tables + patched module handles for one handler run."""

    def __init__(self, owner_item=True):
        self.owner_item = owner_item

    def __enter__(self):
        self._mock = mock_aws()
        self._mock.start()
        ddb = boto3.resource("dynamodb", region_name=REGION)
        self.config = ddb.create_table(
            TableName=sync.USER_CONFIG_TABLE, BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}])
        self.sessions = ddb.create_table(
            TableName=sync.COACHING_SESSIONS_TABLE, BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "session_date", "KeyType": "HASH"},
                       {"AttributeName": "session_id", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "session_date", "AttributeType": "S"},
                                  {"AttributeName": "session_id", "AttributeType": "S"}])
        if self.owner_item:
            self.config.put_item(Item={
                "user_id": OWNER,
                "user_preferences": {"max_hr": 190, "pace_zones": {"ef": {"min": "5:40", "max": "6:10"}}},
                "modules_config": {"campus_coach": {"enabled": True}},
            })
        self._patches = [
            patch.object(sync, "dynamodb", ddb),
            patch.object(sync, "_get_credentials", return_value={"username": "u", "password": "p"}),
            patch.object(sync, "_login", return_value="tok"),
            patch.object(sync, "_sync_athlete_context"),
            patch.object(sync, "_is_module_enabled", return_value=True),
        ]
        self.metrics = MagicMock()
        self._patches.append(patch.object(sync, "metrics", self.metrics))
        for p in self._patches:
            p.start()
        return self

    def run(self, weeks, env, event=None):
        with patch.object(sync, "_fetch_plan", return_value=weeks), patch.dict(os.environ, env):
            return sync.handler(event or {}, None)

    def owner(self):
        return self.config.get_item(Key={"user_id": OWNER}).get("Item")

    def metric_names(self):
        return [c.kwargs["name"] for c in self.metrics.add_metric.call_args_list]

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        self._mock.stop()


def _current_monday_ms():
    return int(sync._monday_of_iso_week(datetime.now(timezone.utc)).timestamp() * 1000)


ON = {"CAMPUS_ZONES_ENABLED": "true", "DEFAULT_USER_ID": OWNER}


class TestPaceFields:
    def test_structured_fields_next_to_the_unchanged_string(self):
        entry = sync._build_exercise_entry({
            "exerciseType": "work", "durations": [{"value": 9, "timeUnit": "minutes"}],
            "pace": {"name": "Semi Marathon", "value": 268, "kind": "single-value",
                     "zoneKind": "half-marathon", "slug": "half-marathon"},
        }, "work")
        assert entry["pace"] == "Semi Marathon (4:28/km)"
        assert (entry["pace_kind"], entry["pace_slug"], entry["pace_zone"]) == (
            "single-value", "half-marathon", "half-marathon")
        assert entry["pace_value_s"] == 268

    def test_fractional_value_is_truncated_like_the_string(self):
        fields = sync._pace_fields({"name": "EF", "value": 348.8, "kind": "range"})
        assert fields["pace_value_s"] == 348
        assert isinstance(fields["pace_value_s"], int)

    def test_abstract_placeholder_has_no_value(self):
        fields = sync._pace_fields({"name": "Lent", "value": 1000, "kind": "abstract"})
        assert fields == {"pace_kind": "abstract"}

    def test_bad_types_are_left_out(self):
        assert sync._pace_fields({"value": "x", "kind": 3, "slug": "", "zoneKind": None}) == {}
        assert sync._pace_fields({"value": float("nan")}) == {}

    def test_legacy_pace_without_structure_is_unchanged(self):
        entry = sync._build_exercise_entry({"exerciseType": "work", "pace": {"name": "EF"}}, "work")
        assert entry == {"type": "work", "duration": "", "pace": "EF"}


class TestParseEstimatedPaces:
    def test_decimal_one_digit(self):
        out = sync._parse_estimated_paces([{"slug": "ef", "value": 348.84, "dvalue": 12.96}])
        assert out == {"ef": {"value": Decimal("348.8"), "dvalue": Decimal("13.0")}}

    def test_duplicate_first_wins_with_metric(self):
        with patch.object(sync, "metrics") as m:
            out = sync._parse_estimated_paces([{"slug": "ef", "value": 340, "dvalue": 10},
                                               {"slug": "ef", "value": 999, "dvalue": 1}])
        assert out["ef"]["value"] == Decimal("340")
        assert m.add_metric.call_args.kwargs["name"] == "CampusEstimatedPaceDuplicate"

    def test_strict_first_wins_even_when_the_first_is_invalid(self):
        """The first entry for a slug decides; a valid later duplicate never stands in."""
        with patch.object(sync, "metrics") as m:
            out = sync._parse_estimated_paces([{"slug": "ef", "value": "x", "dvalue": 10},
                                               {"slug": "ef", "value": 340, "dvalue": 10},
                                               {"slug": "vma", "value": 230, "dvalue": 5}])
        assert "ef" not in out
        assert out["vma"]["value"] == Decimal("230")
        names = [c.kwargs["name"] for c in m.add_metric.call_args_list]
        assert names == ["CampusEstimatedPaceDuplicate"]

    def test_dvalue_zero_parses_but_zone_write_skips(self):
        """dvalue 0 is a stored provider value; the zone map refuses it (spec A)."""
        assert sync._parse_estimated_paces([{"slug": "ef", "value": 300, "dvalue": 0}]) == {
            "ef": {"value": Decimal("300"), "dvalue": Decimal("0")}}
        paces = [dict(p, dvalue=0.0) if p["slug"] == "ef" else p for p in _estimated_list()]
        with _Env() as env:
            out = env.run([_week(_current_monday_ms(), paces)], ON)
            assert out["zones_written"] is False
            assert "campus_pace_zones" not in env.owner()
            assert "CampusZonesSkipped" in env.metric_names()

    def test_invalid_entries_are_ignored(self):
        bad = [{"slug": "a", "value": 0, "dvalue": 1}, {"slug": "b", "value": -3, "dvalue": 1},
               {"slug": "c", "value": float("inf"), "dvalue": 1}, {"slug": "d", "value": 300, "dvalue": -1},
               {"slug": "e", "value": "x", "dvalue": 1}, {"value": 300, "dvalue": 1}, "junk"]
        assert sync._parse_estimated_paces(bad) == {}
        assert sync._parse_estimated_paces(None) == {}


class TestZoneWrite:
    def test_switch_off_by_default_writes_no_zone(self):
        with _Env() as env:
            out = env.run([_week(_current_monday_ms())], {"DEFAULT_USER_ID": OWNER})
            assert out["statusCode"] == 200 and out["zones_written"] is False
            assert "campus_pace_zones" not in env.owner()
            # The raw provider fields are stored either way.
            row = env.sessions.scan()["Items"][0]
            assert row["estimated_paces"]["ef"] == {"value": Decimal("310.2"), "dvalue": Decimal("10.0")}
            assert row["intervals"][0]["pace_kind"] == "range"

    def test_only_exact_true_turns_it_on(self):
        for value in ("True", "1", "yes", "false", ""):
            with _Env() as env:
                env.run([_week(_current_monday_ms())], {"CAMPUS_ZONES_ENABLED": value,
                                                         "DEFAULT_USER_ID": OWNER})
                assert "campus_pace_zones" not in env.owner(), value

    def test_switch_on_writes_top_level_on_the_owner_only(self):
        with _Env() as env:
            out = env.run([_week(_current_monday_ms())], ON, event={"user_id": "someone-else"})
            item = env.owner()
            assert out["zones_written"] is True
            assert set(item["campus_pace_zones"]) == set(CAMPUS_ZONE_SLUGS)
            assert item["campus_pace_zones"]["ef"]["slug"] == "ef"
            assert item["campus_pace_zones_week"] == sync._to_iso_week(_current_monday_ms())
            assert item["campus_pace_zones_synced_at"]
            # Nothing inside user_preferences is touched; no row for the event user.
            assert item["user_preferences"] == {"max_hr": 190, "pace_zones": {"ef": {"min": "5:40", "max": "6:10"}}}
            assert "Item" not in env.config.get_item(Key={"user_id": "someone-else"})
            assert "CampusZonesWritten" in env.metric_names()

    def test_incomplete_paces_write_nothing(self):
        paces = [p for p in _estimated_list() if p["slug"] != "vma"]
        with _Env() as env:
            out = env.run([_week(_current_monday_ms(), paces)], ON)
            assert out["zones_written"] is False
            assert "campus_pace_zones" not in env.owner()
            assert "CampusZonesSkipped" in env.metric_names()

    def test_absent_owner_item_is_never_created(self):
        with _Env(owner_item=False) as env:
            out = env.run([_week(_current_monday_ms())], ON)
            assert out["statusCode"] == 200 and out["zones_written"] is False
            assert env.owner() is None
            assert "CampusZonesSkipped" in env.metric_names()

    def test_empty_owner_id_writes_nothing(self):
        with _Env() as env:
            out = env.run([_week(_current_monday_ms())], {"CAMPUS_ZONES_ENABLED": "true",
                                                           "DEFAULT_USER_ID": ""})
            assert out["zones_written"] is False
            assert "campus_pace_zones" not in env.owner()

    def test_only_the_current_week_is_written(self):
        future = _current_monday_ms() + 7 * 24 * 3600 * 1000
        with _Env() as env:
            out = env.run([_week(future)], ON)
            assert out["zones_written"] is False
            assert "campus_pace_zones" not in env.owner()
