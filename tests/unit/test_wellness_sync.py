"""A2: WellnessSync upsert semantics, Paris dates, backfill bounds, fail-closed.

DynamoDB SET/REMOVE semantics matter here, so the upsert tests use moto for a
real round-trip against the wellness table.
"""
import os
import sys
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("WELLNESS_TABLE", "test-wellness")
os.environ.setdefault("USER_CONFIG_TABLE", "test-user-config")
os.environ.setdefault("CAMPUS_OWNER_STRAVA_ID", "42")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from webhooks import wellness_sync as ws


OWNER = "42"


@pytest.fixture
def wellness_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="eu-west-1")
        ddb.create_table(
            TableName="test-wellness",
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        old = ws.dynamodb
        ws.dynamodb = ddb
        try:
            yield ddb.Table("test-wellness")
        finally:
            ws.dynamodb = old


class TestToDecimal:
    def test_finite_number(self):
        assert ws._to_decimal(42) == Decimal("42")
        assert ws._to_decimal("48.5") == Decimal("48.5")

    def test_non_finite_and_junk_are_none(self):
        assert ws._to_decimal(float("nan")) is None
        assert ws._to_decimal(float("inf")) is None
        assert ws._to_decimal("abc") is None
        assert ws._to_decimal(None) is None
        assert ws._to_decimal(True) is None  # bools are not metrics


class TestDayValues:
    def test_hrv_rmssd_first_with_kind(self):
        vals = ws._day_values({"hrv": 42.0, "hrvSDNN": 60.0, "restingHR": 48})
        assert vals["hrv"] == Decimal("42.0")
        assert vals["hrv_kind"] == "rmssd"
        assert vals["restingHR"] == Decimal("48")

    def test_hrv_sdnn_fallback(self):
        vals = ws._day_values({"hrvSDNN": 60.0})
        assert vals["hrv"] == Decimal("60.0")
        assert vals["hrv_kind"] == "sdnn"

    def test_absent_fields_omitted(self):
        vals = ws._day_values({"restingHR": 50, "weight": None, "ctl": float("nan")})
        assert "weight" not in vals
        assert "ctl" not in vals


class TestUpsertSetRemove:
    def test_set_present_remove_absent_only_for_present_day(self, wellness_table):
        # Seed a day with a weight; next sync returns no weight -> weight REMOVEd.
        ws._upsert_day(wellness_table, OWNER, "2026-10-16",
                       {"restingHR": Decimal("48"), "weight": Decimal("92")})
        item = wellness_table.get_item(Key={"user_id": OWNER, "sk": "day#2026-10-16"})["Item"]
        assert item["weight"] == Decimal("92")

        ws._upsert_day(wellness_table, OWNER, "2026-10-16",
                       {"restingHR": Decimal("47")})
        item = wellness_table.get_item(Key={"user_id": OWNER, "sk": "day#2026-10-16"})["Item"]
        assert item["restingHR"] == Decimal("47")
        assert "weight" not in item  # absent in the new response -> removed

    def test_untouched_day_is_not_modified(self, wellness_table):
        ws._upsert_day(wellness_table, OWNER, "2026-10-15", {"restingHR": Decimal("50")})
        ws._upsert_day(wellness_table, OWNER, "2026-10-16", {"restingHR": Decimal("48")})
        # Writing day 16 again must not touch day 15.
        ws._upsert_day(wellness_table, OWNER, "2026-10-16", {"restingHR": Decimal("49")})
        d15 = wellness_table.get_item(Key={"user_id": OWNER, "sk": "day#2026-10-15"})["Item"]
        assert d15["restingHR"] == Decimal("50")


class TestSyncWindowWritesPresentDays:
    def test_only_days_present_in_response_are_written(self, wellness_table):
        rows = [
            {"id": "2026-10-15", "restingHR": 50, "ctl": 10.0, "atl": 20.0},
            {"id": "2026-10-16", "restingHR": 48, "hrvSDNN": 60.0},
            {"id": None},  # ignored
        ]
        with patch.object(ws, "_fetch_wellness_range", return_value=rows):
            written = ws._sync_window(wellness_table, OWNER, "key", "2026-10-14", "2026-10-16")
        assert written == 2
        got = wellness_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("user_id").eq(OWNER),
        )["Items"]
        sks = sorted(i["sk"] for i in got)
        assert sks == ["day#2026-10-15", "day#2026-10-16"]


class TestBackfillBounds:
    def test_backfill_clamped_to_730_and_sliced_by_90(self, wellness_table):
        calls = []

        def fake_window(table, user_id, api_key, oldest, newest):
            calls.append((oldest, newest))
            return 0

        with patch.object(ws, "_sync_window", side_effect=fake_window):
            ws._backfill(wellness_table, OWNER, "key", date(2026, 10, 16), 10_000)
        # 730 clamped, 90-day slices -> ceil(730/90) = 9 slices.
        assert len(calls) == 9
        # Each slice spans at most 90 days.
        for oldest, newest in calls:
            o = date.fromisoformat(oldest)
            n = date.fromisoformat(newest)
            assert (n - o).days <= 89


class TestFailClosed:
    def _owner_cfg(self, enabled):
        return {"Item": {"user_id": OWNER, "modules_config": {"intervals_icu": {"enabled": enabled}}}}

    def test_module_disabled_writes_nothing(self):
        with patch.object(ws, "dynamodb") as mock_ddb:
            cfg_table = MagicMock()
            cfg_table.get_item.return_value = self._owner_cfg(False)
            mock_ddb.Table.return_value = cfg_table
            result = ws.handler({}, None)
        assert "disabled" in result["message"]
        # No write of any kind when the module is off (only the config GetItem).
        assert cfg_table.update_item.call_count == 0
        assert cfg_table.put_item.call_count == 0

    def test_config_unreadable_fails_closed(self):
        with patch.object(ws, "dynamodb") as mock_ddb:
            cfg_table = MagicMock()
            cfg_table.get_item.side_effect = RuntimeError("ddb down")
            mock_ddb.Table.return_value = cfg_table
            with patch.object(ws.metrics, "add_metric") as m:
                result = ws.handler({}, None)
        assert "unreadable" in result["message"]
        assert any(c.kwargs.get("name") == "WellnessSyncFailed" for c in m.call_args_list)

    def test_no_owner_does_nothing(self):
        with patch.object(ws, "CAMPUS_OWNER_STRAVA_ID", ""), \
             patch.dict(os.environ, {"DEFAULT_USER_ID": ""}, clear=False):
            result = ws.handler({}, None)
        assert result["message"] == "no owner configured"

    def test_default_user_id_is_not_a_fallback(self):
        """Owner only: a set DEFAULT_USER_ID must NOT be used when the owner is empty."""
        with patch.object(ws, "CAMPUS_OWNER_STRAVA_ID", ""), \
             patch.dict(os.environ, {"DEFAULT_USER_ID": "999"}, clear=False):
            result = ws.handler({}, None)
        assert result["message"] == "no owner configured"

    def test_intervals_non_200_fails_and_no_brief_rebuild(self):
        """A non-200 from intervals.icu -> WellnessSyncFailed metric, no brief
        rebuild from empty data."""
        with patch.object(ws, "dynamodb") as mock_ddb, \
             patch.object(ws, "_module_config", return_value={"enabled": True}), \
             patch.object(ws, "_get_api_key", return_value="key"), \
             patch.object(ws.metrics, "add_metric") as add_metric, \
             patch("webhooks.morning_brief.build_and_store_brief") as build_brief:
            mock_ddb.Table.return_value = MagicMock()
            resp = MagicMock(status_code=503)
            with patch.object(ws.requests, "get", return_value=resp):
                result = ws.handler({}, None)
        assert result["days_written"] == 0
        assert any(c.kwargs.get("name") == "WellnessSyncFailed" for c in add_metric.call_args_list)
        assert not build_brief.called  # no rebuild from empty data
