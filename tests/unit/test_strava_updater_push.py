"""Tests for the opt-in push trigger in strava_updater (_maybe_push_completed).

The push fires at the `completed` step, once per activity:
- nothing when PUSH_ENABLED is off;
- a single notification: dedup via a conditional UpdateItem on `push_sent_at`,
  released again when the dispatch to PushSend fails;
- only when Strava was actually updated (not on `no_update_needed`);
- body = the enhanced title only (never the description, which can quote HR/pace),
  with a neutral fallback;
- never raises (best-effort), so a failure never fails the Strava update.
"""

import os
import sys
from unittest.mock import patch

from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

os.environ.setdefault("ACTIVITIES_TABLE", "test-activities")
os.environ.setdefault("STRAVA_OAUTH_SECRET", "test-oauth-secret")

from processing import strava_updater as su  # noqa: E402

_COND_FAILED = ClientError(
    {"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}}, "UpdateItem"
)


class FakeTable:
    """Configurable item + conditional UpdateItem on push_sent_at."""

    def __init__(self, item, already_sent=False):
        self._item = dict(item)
        self._already_sent = already_sent
        self.updates = []

    def get_item(self, **_kw):
        return {"Item": self._item}

    def update_item(self, **kw):
        self.updates.append(kw)
        cond = kw.get("ConditionExpression")
        if cond is not None and self._already_sent:
            raise _COND_FAILED
        return {}


def _patch_table(monkeypatch, table):
    monkeypatch.setattr(su.dynamodb, "Table", lambda _n: table)


def test_no_push_when_disabled(monkeypatch):
    monkeypatch.delenv("PUSH_ENABLED", raising=False)
    calls = []
    with patch("shared.push_notify.notify_activity_enriched", side_effect=lambda **k: calls.append(k)):
        su._maybe_push_completed("act1", "u1")
    assert calls == []


def test_push_fires_once(monkeypatch):
    monkeypatch.setenv("PUSH_ENABLED", "true")
    table = FakeTable({"user_id": "u1", "enhanced_title": "Sortie longue au bord de l'eau"})
    _patch_table(monkeypatch, table)
    calls = []
    with patch("shared.push_notify.notify_activity_enriched", side_effect=lambda **k: calls.append(k)):
        su._maybe_push_completed("act1", "u1")
    assert len(calls) == 1
    assert calls[0]["activity_id"] == "act1"
    assert calls[0]["body"] == "Sortie longue au bord de l'eau"
    # push_sent_at set conditionally
    assert any(u.get("ConditionExpression") is not None for u in table.updates)


def test_push_deduped_when_already_sent(monkeypatch):
    monkeypatch.setenv("PUSH_ENABLED", "true")
    table = FakeTable({"user_id": "u1", "enhanced_title": "x"}, already_sent=True)
    _patch_table(monkeypatch, table)
    calls = []
    with patch("shared.push_notify.notify_activity_enriched", side_effect=lambda **k: calls.append(k)):
        su._maybe_push_completed("act1", "u1")
    assert calls == []  # condition failed -> no notification


def test_marker_is_released_when_dispatch_fails(monkeypatch):
    """A transient invoke failure must not lose the notification for good."""
    monkeypatch.setenv("PUSH_ENABLED", "true")
    table = FakeTable({"user_id": "u1", "enhanced_title": "x"})
    _patch_table(monkeypatch, table)
    with patch("shared.push_notify.notify_activity_enriched", return_value=False):
        su._maybe_push_completed("act1", "u1")
    set_marker, release = table.updates
    assert set_marker["UpdateExpression"].startswith("SET push_sent_at")
    assert release["UpdateExpression"] == "REMOVE push_sent_at"


def test_marker_is_kept_when_dispatch_succeeds(monkeypatch):
    monkeypatch.setenv("PUSH_ENABLED", "true")
    table = FakeTable({"user_id": "u1", "enhanced_title": "x"})
    _patch_table(monkeypatch, table)
    with patch("shared.push_notify.notify_activity_enriched", return_value=True):
        su._maybe_push_completed("act1", "u1")
    assert [u["UpdateExpression"] for u in table.updates] == ["SET push_sent_at = :now"]


def test_no_push_when_strava_had_nothing_to_update(monkeypatch):
    """The handler only notifies when Strava was actually updated."""
    monkeypatch.setattr(su, "get_access_token", lambda _u: "tkn")
    monkeypatch.setattr(su, "update_strava_activity", lambda *_a: {"status": "no_update_needed"})
    monkeypatch.setattr(su, "update_activity_status", lambda *_a, **_k: None)
    calls = []
    monkeypatch.setattr(su, "_maybe_push_completed", lambda *a: calls.append(a))
    su.handler({"activity_id": "act1", "user_id": "u1", "enhanced_content": {"title": "t"}}, None)
    assert calls == []

    monkeypatch.setattr(su, "update_strava_activity", lambda *_a: {"status": "success"})
    su.handler({"activity_id": "act1", "user_id": "u1", "enhanced_content": {"title": "t"}}, None)
    assert calls == [("act1", "u1")]


def test_body_never_quotes_the_description(monkeypatch):
    """The description can quote heart rate or pace; a notification may show on a
    locked screen, so only the title (or a neutral sentence) is sent."""
    monkeypatch.setenv("PUSH_ENABLED", "true")
    table = FakeTable({"user_id": "u1", "enhanced_description": "FC moy 152 bpm, 5:12/km"})
    _patch_table(monkeypatch, table)
    calls = []
    with patch("shared.push_notify.notify_activity_enriched", side_effect=lambda **k: calls.append(k)):
        su._maybe_push_completed("act1", "u1")
    assert calls[0]["body"] == "Ta description enrichie est en ligne."
    assert "bpm" not in calls[0]["body"]


def test_never_raises(monkeypatch):
    monkeypatch.setenv("PUSH_ENABLED", "true")

    def boom(_n):
        raise RuntimeError("dynamo down")

    monkeypatch.setattr(su.dynamodb, "Table", boom)
    su._maybe_push_completed("act1", "u1")  # must swallow the error
