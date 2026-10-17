"""Hardening of the Web Push feature (port review of PR #26).

* subscription endpoints are limited to the browser push services (no SSRF);
* the per-user subscription count is capped;
* ``send_push`` sets a TTL, a network timeout and an Urgency header, refuses a
  non-allowed endpoint before any network call, and keeps the payload under the
  push service size limit;
* PushSend skips rows that are not subscriptions;
* PushSend is not retried by Lambda async invoke (a retry would resend);
* the Push stack passes cdk-nag with the repo suppressions.
"""

import importlib
import json
import os
import sys
import types
from typing import Any

import aws_cdk as cdk
import pytest
from aws_cdk import assertions
from boto3.dynamodb.conditions import Key
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

TABLE = "test-push-subscriptions-hardening"
USER = "athlete-42"
APPLE = "https://web.push.apple.com/QGx-abc"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("PUSH_SUBSCRIPTIONS_TABLE", TABLE)
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:ops@example.com")


def _core():
    import push.webpush_core as core

    return importlib.reload(core)


def _create_table(boto3):
    ddb = boto3.resource("dynamodb", region_name="us-east-1")
    return ddb.create_table(
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


def _post(api, endpoint: str) -> dict[str, Any]:
    event = {
        "httpMethod": "POST",
        "path": "/push/subscribe",
        "body": json.dumps({"endpoint": endpoint, "keys": {"p256dh": "p", "auth": "a"}}),
        "requestContext": {"authorizer": {"claims": {"custom:strava_id": USER}}},
    }
    return api.handler(event, None)


# ---- endpoint allowlist ------------------------------------------------------


def test_allowlist_accepts_the_browser_push_services():
    core = _core()
    assert core.is_allowed_endpoint("https://web.push.apple.com/QGx")
    assert core.is_allowed_endpoint("https://fcm.googleapis.com/fcm/send/abc")
    assert core.is_allowed_endpoint("https://updates.push.services.mozilla.com/wpush/v2/x")
    assert core.is_allowed_endpoint("https://wns2-par02p.notify.windows.com/w/?token=x")
    assert core.is_allowed_endpoint("https://web.push.apple.com:443/QGx")


def test_allowlist_refuses_internal_and_lookalike_targets():
    core = _core()
    refused = [
        "http://web.push.apple.com/QGx",                   # not https
        "https://169.254.169.254/latest/meta-data/",       # instance metadata
        "https://127.0.0.1/x",
        "https://localhost/x",
        "https://web.push.apple.com.evil.example/x",       # suffix trick
        "https://evilpush.apple.com/x",                    # no dot before the suffix
        "https://fcm.googleapis.com.evil.example/x",
        "https://user:pw@web.push.apple.com/x",            # credentials  # pragma: allowlist secret
        "https://web.push.apple.com:8443/x",               # other port
        "https://web.push.apple.com/" + "a" * 1100,        # too long
        "",
        "not a url",
    ]
    for url in refused:
        assert not core.is_allowed_endpoint(url), url


@mock_aws
def test_subscribe_refuses_a_non_push_service_endpoint():
    import boto3
    import push.push_api as api_mod

    _core()
    api = importlib.reload(api_mod)
    table = _create_table(boto3)

    resp = _post(api, "https://169.254.169.254/latest/meta-data/")
    assert resp["statusCode"] == 400
    assert table.scan()["Items"] == []


@mock_aws
def test_subscribe_caps_the_number_of_devices():
    import boto3
    import push.push_api as api_mod

    _core()
    api = importlib.reload(api_mod)
    table = _create_table(boto3)

    for i in range(api.MAX_SUBSCRIPTIONS_PER_USER):
        assert _post(api, f"{APPLE}-{i}")["statusCode"] == 200
    assert _post(api, f"{APPLE}-extra")["statusCode"] == 409
    # Re-subscribing a known device still works at the cap.
    assert _post(api, f"{APPLE}-0")["statusCode"] == 200
    items = table.query(KeyConditionExpression=Key("user_id").eq(USER))["Items"]
    assert len(items) == api.MAX_SUBSCRIPTIONS_PER_USER


# ---- send_push ---------------------------------------------------------------


def _fake_pywebpush(monkeypatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class WebPushException(Exception):
        pass

    def webpush(**kwargs):
        calls.append(kwargs)
        return None

    module = types.ModuleType("pywebpush")
    module.WebPushException = WebPushException
    module.webpush = webpush
    monkeypatch.setitem(sys.modules, "pywebpush", module)
    return calls


def test_send_push_sets_ttl_timeout_and_urgency(monkeypatch):
    core = _core()
    calls = _fake_pywebpush(monkeypatch)
    monkeypatch.setattr(core, "_load_vapid", lambda: {"public_key": "pub", "private_key": "priv"})  # pragma: allowlist secret

    core.send_push({"endpoint": APPLE, "keys": {"p256dh": "p", "auth": "a"}}, {"title": "t", "body": "b"})

    assert len(calls) == 1
    assert calls[0]["ttl"] == core.PUSH_TTL_SECONDS > 0
    assert calls[0]["timeout"] == core.PUSH_HTTP_TIMEOUT_SECONDS
    assert calls[0]["headers"] == {"Urgency": "normal"}


def test_send_push_refuses_a_non_allowed_endpoint_before_any_call(monkeypatch):
    core = _core()
    calls = _fake_pywebpush(monkeypatch)
    loaded: list[bool] = []
    monkeypatch.setattr(core, "_load_vapid", lambda: loaded.append(True) or {})

    with pytest.raises(ValueError):
        core.send_push({"endpoint": "https://169.254.169.254/x", "keys": {}}, {"title": "t"})
    assert calls == []
    assert loaded == []  # the VAPID secret is not even read


def test_payload_is_shortened_under_the_size_limit():
    core = _core()
    payload = {"title": "Activité enrichie", "body": "é" * 5000, "url": "/activities/1", "tag": "x"}
    encoded = core.fit_payload(payload)
    data = json.loads(encoded)
    assert len(encoded.encode("utf-8")) <= core.MAX_PAYLOAD_BYTES
    assert data["url"] == "/activities/1" and data["tag"] == "x"
    assert data["title"] == "Activité enrichie"
    assert data["body"].endswith("…")


def test_small_payload_is_unchanged():
    core = _core()
    payload = {"title": "t", "body": "b", "url": "/", "tag": "x"}
    assert json.loads(core.fit_payload(payload)) == payload


# ---- PushSend robustness -----------------------------------------------------


@mock_aws
def test_send_skips_rows_that_are_not_subscriptions(monkeypatch):
    import boto3
    import push.push_send as send_mod

    _core()
    send = importlib.reload(send_mod)
    table = _create_table(boto3)
    table.put_item(Item={"user_id": USER, "endpoint_hash": "state", "note": "not a subscription"})
    table.put_item(
        Item={"user_id": USER, "endpoint_hash": "h1", "endpoint": APPLE, "p256dh": "p", "auth": "a"}
    )
    sent: list[str] = []
    monkeypatch.setattr(send, "send_push", lambda sub, payload: sent.append(sub["endpoint"]))

    result = send.handler({"user_id": USER, "activity_id": "a1"}, None)

    assert result["sent"] == 1
    assert sent == [APPLE]


# ---- infrastructure ----------------------------------------------------------


def _push_app(nag: bool = False):
    from stacks.core_infrastructure_stack import CoreInfrastructureStack
    from stacks.push_stack import PushStack
    from tests.unit.test_push_stack import BUILT_LAYER

    env = cdk.Environment(account="123456789012", region="us-east-1")
    app = cdk.App(context={"vapid_subject": "mailto:ops@example.com"})
    core = CoreInfrastructureStack(app, "StravaAIBoost-Core", env=env)
    push = PushStack(app, "StravaAIBoost-Push", core_stack=core, layer_dir=BUILT_LAYER, env=env)
    if nag:
        from cdk_nag import AwsSolutionsChecks

        from stacks.nag_suppressions import apply_nag_suppressions

        apply_nag_suppressions(app)
        cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))
    return app, push


def test_push_send_is_not_retried_by_async_invoke():
    _app, push = _push_app()
    template = assertions.Template.from_stack(push)
    configs = template.find_resources("AWS::Lambda::EventInvokeConfig")
    assert len(configs) == 1
    props = next(iter(configs.values()))["Properties"]
    assert props["MaximumRetryAttempts"] == 0
    assert props["MaximumEventAgeInSeconds"] == 6 * 3600


def test_push_stack_has_no_cdk_nag_error():
    _app, push = _push_app(nag=True)
    errors = assertions.Annotations.from_stack(push).find_error(
        "*", assertions.Match.string_like_regexp("AwsSolutions-.*")
    )
    assert errors == [], [e.entry.data for e in errors]
