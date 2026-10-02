"""Unit tests for the Web Push lambdas: PushApi + PushSend.

moto-backed end-to-end over the real boto3 path on the (user_id, endpoint_hash) table:
- POST /push/subscribe stores an item; a re-subscribe with the same endpoint
  overwrites (single row);
- POST with a missing key is rejected 400;
- a request without a Cognito identity claim is rejected 401;
- DELETE /push/subscribe removes the user's subscription(s);
- GET /push/vapid-public-key returns only the public key;
- PushSend sends to each subscription and DELETES an endpoint returning 410
  (PushExpired), leaving the healthy ones; one failing sub never blocks the others.
Skipped when moto is not installed.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from typing import Any

import pytest

os.environ.setdefault("PUSH_SUBSCRIPTIONS_TABLE", "test-push-subscriptions")
os.environ.setdefault("VAPID_SECRET", "test-vapid")
os.environ.setdefault("DEFAULT_USER_ID", "12345678")
# The session-autouse conftest sets AWS_REGION=eu-west-1; the push modules read
# AWS_REGION at import, so pin both to the test region (override, not setdefault).
os.environ["AWS_REGION"] = "us-east-1"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

pytest.importorskip("moto")
from boto3.dynamodb.conditions import Key  # noqa: E402
from moto import mock_aws  # noqa: E402

USER = "12345678"
TABLE = "test-push-subscriptions"
REGION = "us-east-1"


@pytest.fixture(autouse=True)
def _pin_region(monkeypatch):
    monkeypatch.setenv("AWS_REGION", REGION)
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


def _create_table(boto3):
    ddb = boto3.resource("dynamodb", region_name=REGION)
    ddb.create_table(
        TableName=TABLE,
        KeySchema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "endpoint_hash", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "endpoint_hash", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return ddb.Table(TABLE)


def _reload_api():
    import push.push_api as api
    import push.webpush_core as core

    importlib.reload(core)
    importlib.reload(api)
    return api


def _reload_send():
    import push.push_send as send
    import push.webpush_core as core

    importlib.reload(core)
    importlib.reload(send)
    return send


def _sub_event(method: str, body: dict[str, Any] | None, with_identity: bool = True) -> dict[str, Any]:
    ctx = {"authorizer": {"claims": {"custom:strava_id": USER}}} if with_identity else {}
    return {
        "httpMethod": method,
        "path": "/push/subscribe",
        "body": json.dumps(body) if body is not None else None,
        "requestContext": ctx,
    }


def _subscription(endpoint: str) -> dict[str, Any]:
    return {"endpoint": endpoint, "keys": {"p256dh": "BPk...pub", "auth": "aUtH=="}}


@mock_aws
def test_subscribe_then_resubscribe_is_single_row():
    import boto3

    api = _reload_api()
    table = _create_table(boto3)

    r1 = api.handler(_sub_event("POST", _subscription("https://push.example/ep-A")), None)
    assert r1["statusCode"] == 200
    r2 = api.handler(_sub_event("POST", _subscription("https://push.example/ep-A")), None)
    assert r2["statusCode"] == 200

    items = table.query(KeyConditionExpression=Key("user_id").eq(USER))["Items"]
    assert len(items) == 1
    assert items[0]["endpoint"] == "https://push.example/ep-A"


@mock_aws
def test_subscribe_validation_rejects_missing_keys():
    import boto3

    api = _reload_api()
    _create_table(boto3)
    resp = api.handler(_sub_event("POST", {"endpoint": "https://x/ep"}), None)
    assert resp["statusCode"] == 400


@mock_aws
def test_subscribe_without_identity_is_401():
    import boto3

    api = _reload_api()
    _create_table(boto3)
    resp = api.handler(
        _sub_event("POST", _subscription("https://push.example/ep-A"), with_identity=False),
        None,
    )
    assert resp["statusCode"] == 401


@mock_aws
def test_unsubscribe_removes_all_for_user():
    import boto3

    api = _reload_api()
    table = _create_table(boto3)
    api.handler(_sub_event("POST", _subscription("https://push.example/ep-A")), None)
    api.handler(_sub_event("POST", _subscription("https://push.example/ep-B")), None)

    resp = api.handler(_sub_event("DELETE", None), None)
    assert resp["statusCode"] == 200
    items = table.query(KeyConditionExpression=Key("user_id").eq(USER))["Items"]
    assert items == []


@mock_aws
def test_send_delivers_and_cleans_expired_endpoint(monkeypatch):
    import boto3
    import push.webpush_core as core

    api = _reload_api()
    send = _reload_send()
    table = _create_table(boto3)

    api.handler(_sub_event("POST", _subscription("https://push.example/ep-A")), None)
    api.handler(_sub_event("POST", _subscription("https://push.example/ep-B")), None)

    def fake_send_push(subscription, payload):
        assert payload["url"].startswith("/")  # SW URL contract
        if subscription["endpoint"].endswith("ep-B"):
            raise core.PushExpired("410 Gone")

    monkeypatch.setattr(send, "send_push", fake_send_push)

    result = send.handler(
        {"user_id": USER, "activity_id": "act1", "title": "Activité enrichie", "body": "Bravo."},
        None,
    )
    assert result["statusCode"] == 200
    assert result["sent"] == 1
    assert result["cleaned"] == 1

    items = table.query(KeyConditionExpression=Key("user_id").eq(USER))["Items"]
    endpoints = {i["endpoint"] for i in items}
    assert endpoints == {"https://push.example/ep-A"}  # ep-B cleaned


@mock_aws
def test_send_one_failing_sub_does_not_block_others(monkeypatch):
    import boto3

    api = _reload_api()
    send = _reload_send()
    _create_table(boto3)

    api.handler(_sub_event("POST", _subscription("https://push.example/ep-A")), None)
    api.handler(_sub_event("POST", _subscription("https://push.example/ep-B")), None)

    def flaky(subscription, payload):
        if subscription["endpoint"].endswith("ep-A"):
            raise RuntimeError("transient")

    monkeypatch.setattr(send, "send_push", flaky)
    result = send.handler({"user_id": USER, "activity_id": "act1"}, None)
    assert result["statusCode"] == 200
    assert result["sent"] == 1  # ep-B still delivered


@mock_aws
def test_send_default_url_is_activity_route(monkeypatch):
    import boto3

    api = _reload_api()
    send = _reload_send()
    _create_table(boto3)
    api.handler(_sub_event("POST", _subscription("https://push.example/ep-A")), None)

    captured = {}

    def capture(subscription, payload):
        captured.update(payload)

    monkeypatch.setattr(send, "send_push", capture)
    send.handler({"user_id": USER, "activity_id": "act42"}, None)
    assert captured["url"] == "/activities/act42"


@mock_aws
def test_send_no_subscriptions_is_noop():
    import boto3

    send = _reload_send()
    _create_table(boto3)
    result = send.handler({"user_id": USER, "activity_id": "act1"}, None)
    assert result["statusCode"] == 200
    assert result["sent"] == 0


@mock_aws
def test_vapid_public_key_returns_only_public():
    import boto3

    _create_table(boto3)
    sm = boto3.client("secretsmanager", region_name=REGION)
    sm.create_secret(
        Name="test-vapid",
        SecretString=json.dumps({"public_key": "PUBLIC_KEY_B64", "private_key": "PRIVATE_KEY_B64"}),
    )
    api = _reload_api()

    event = {"httpMethod": "GET", "path": "/push/vapid-public-key", "requestContext": {}}
    resp = api.handler(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["public_key"] == "PUBLIC_KEY_B64"
    assert "private_key" not in resp["body"]
