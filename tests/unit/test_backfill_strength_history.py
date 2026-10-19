"""scripts/backfill_strength_history.py bumps last_updated on every write, so the
per-side re-read refuses a plan made before the list changed."""

import importlib
import os
import sys
from unittest.mock import MagicMock

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "lambda_functions"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

backfill = importlib.import_module("backfill_strength_history")


def _write_kwargs(monkeypatch, replace):
    table = MagicMock()
    table.get_item.return_value = {"Item": {"user_preferences": {}}}
    resource = MagicMock()
    resource.Table.return_value = table
    monkeypatch.setattr(backfill.boto3, "resource", lambda *a, **k: resource)
    monkeypatch.setattr(backfill, "_strength_activities", lambda *_a: [{
        "activity_id": "a1", "description": "dc 3x10 80", "start_date": "2026-10-13",
        "moving_time": 3600}])
    monkeypatch.setattr(backfill.time, "sleep", lambda _s: None)
    from processing import content_generator
    monkeypatch.setattr(content_generator, "_extract_strength_sets", lambda _d: [
        {"exercise": "Développé couché", "sets": 3, "reps": 10, "weight_kg": 80,
         "per_side": False, "sets_detail": [{"reps": 10, "weight_kg": 80}] * 3}])
    backfill.backfill("u1", "us-east-1", apply=True, replace=replace)
    return table.update_item.call_args_list[-1].kwargs


def test_append_bumps_last_updated(monkeypatch):
    kwargs = _write_kwargs(monkeypatch, replace=False)
    assert "strength_history.last_updated = :ts" in kwargs["UpdateExpression"]
    assert kwargs["ExpressionAttributeValues"][":ts"].startswith("20")


def test_replace_bumps_last_updated(monkeypatch):
    kwargs = _write_kwargs(monkeypatch, replace=True)
    assert "strength_history.last_updated = :ts" in kwargs["UpdateExpression"]
    assert kwargs["ExpressionAttributeValues"][":ts"].startswith("20")
