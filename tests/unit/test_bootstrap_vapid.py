"""scripts/bootstrap_vapid.py stores the VAPID pair safely (moto, no AWS).

- the application server key goes to SSM as a SecureString, tagged;
- the signing key is never written to SSM and never printed;
- an existing pair is not overwritten without --rotate, only re-synced to SSM.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

moto = pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402

REGION = "us-east-1"
SCRIPT = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "bootstrap_vapid.py")


def _load():
    spec = importlib.util.spec_from_file_location("bootstrap_vapid", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(mod, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["bootstrap_vapid.py", "--region", REGION, *args])
    return mod.main()


@mock_aws
def test_apply_stores_a_tagged_securestring_and_hides_the_signing_key(monkeypatch, capsys):
    import boto3

    mod = _load()
    sm = boto3.client("secretsmanager", region_name=REGION)
    ssm = boto3.client("ssm", region_name=REGION)
    # CDK creates the secret with a random placeholder value (Secret() default).
    sm.create_secret(Name=mod.SECRET_NAME, SecretString="cdk-generated-placeholder")

    assert _run(mod, monkeypatch, "--apply") == 0

    stored = json.loads(sm.get_secret_value(SecretId=mod.SECRET_NAME)["SecretString"])
    param = ssm.get_parameter(Name=mod.APP_SERVER_KEY_PARAM, WithDecryption=True)["Parameter"]
    assert param["Type"] == "SecureString"
    assert param["Value"] == stored["public_key"]
    assert stored["private_key"] not in param["Value"]

    tags = ssm.list_tags_for_resource(ResourceType="Parameter", ResourceId=mod.APP_SERVER_KEY_PARAM)
    assert {"Key": "Project", "Value": "strava-ai-boost"} in tags["TagList"]

    out = capsys.readouterr().out
    assert stored["private_key"] not in out
    assert stored["public_key"] not in out


@mock_aws
def test_existing_pair_is_kept_and_only_resynced(monkeypatch):
    import boto3

    mod = _load()
    sm = boto3.client("secretsmanager", region_name=REGION)
    ssm = boto3.client("ssm", region_name=REGION)
    pair = mod.generate_pair()
    sm.create_secret(Name=mod.SECRET_NAME, SecretString=json.dumps(pair))

    assert _run(mod, monkeypatch, "--apply") == 0

    assert json.loads(sm.get_secret_value(SecretId=mod.SECRET_NAME)["SecretString"]) == pair
    param = ssm.get_parameter(Name=mod.APP_SERVER_KEY_PARAM, WithDecryption=True)["Parameter"]
    assert param["Value"] == pair["public_key"]


@mock_aws
def test_dry_run_writes_nothing(monkeypatch):
    import boto3

    mod = _load()
    boto3.client("secretsmanager", region_name=REGION).create_secret(
        Name=mod.SECRET_NAME, SecretString="cdk-generated-placeholder"
    )
    assert _run(mod, monkeypatch) == 0
    names = [
        p["Name"]
        for p in boto3.client("ssm", region_name=REGION).describe_parameters()["Parameters"]
    ]
    assert mod.APP_SERVER_KEY_PARAM not in names
