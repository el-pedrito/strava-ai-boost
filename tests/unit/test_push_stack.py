"""Offline CDK assertions for the Push stack (StravaAIBoost-Push).

With a fake account/region and no AWS calls:
  * the subscriptions table exists with the (user_id, endpoint_hash) key schema and
    PITR enabled;
  * the VAPID secret exists under the strava-ai-boost-* convention and is RETAINed;
  * both Lambdas (PushApi, PushSend) exist on the expected handlers;
  * least privilege: a GetSecretValue statement exists (PushSend signs with the
    private key) and no push role carries a bare Resource: "*";
  * grant_notify adds a lambda:InvokeFunction permission;
  * synth fails without a VAPID subject or with an unbuilt push layer;
  * PushApi has no Secrets Manager access and only ssm:GetParameter on the exact
    application-server-key parameter.
"""

import os
import sys
import tempfile

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from stacks.core_infrastructure_stack import CoreInfrastructureStack  # noqa: E402
from stacks.push_stack import (  # noqa: E402
    PUSH_SUBSCRIPTIONS_TABLE_NAME,
    VAPID_SECRET_NAME,
    PushStack,
)

FAKE_ENV = cdk.Environment(account="123456789012", region="us-east-1")
CONTEXT = {"vapid_subject": "mailto:ops@example.com"}


def _layer_dir(built: bool = True) -> str:
    """A throwaway push-layer folder, built (pywebpush present) or not."""
    root = tempfile.mkdtemp(prefix="push-layer-")
    for name in ("requirements.txt", "build_layer.sh"):
        with open(os.path.join(root, name), "w") as fh:
            fh.write("pywebpush==2.5.0\n" if name == "requirements.txt" else "#!/bin/bash\n")
    if built:
        os.makedirs(os.path.join(root, "python", "pywebpush"))
        with open(os.path.join(root, "python", "pywebpush", "__init__.py"), "w") as fh:
            fh.write("")
    return root


BUILT_LAYER = _layer_dir()


def _synth(context=CONTEXT, layer_dir=BUILT_LAYER, suffix=""):
    app = cdk.App(context=context)
    core = CoreInfrastructureStack(app, f"TestCorePush{suffix}", env=FAKE_ENV)
    push = PushStack(app, f"TestPush{suffix}", core_stack=core, layer_dir=layer_dir, env=FAKE_ENV)
    return assertions.Template.from_stack(push), push


def test_subscriptions_table_key_schema_and_pitr():
    template, _ = _synth()
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": PUSH_SUBSCRIPTIONS_TABLE_NAME,
            "KeySchema": [
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "endpoint_hash", "KeyType": "RANGE"},
            ],
            "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
        },
    )


def test_vapid_secret_named_by_convention_and_retained():
    template, _ = _synth()
    template.has_resource_properties(
        "AWS::SecretsManager::Secret",
        {"Name": VAPID_SECRET_NAME},
    )
    template.has_resource(
        "AWS::SecretsManager::Secret",
        {"DeletionPolicy": "Retain"},
    )


def test_both_push_lambdas_present_on_expected_handlers():
    template, _ = _synth()
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"FunctionName": "StravaAIBoost-PushApi", "Handler": "push.push_api.handler"},
    )
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"FunctionName": "StravaAIBoost-PushSend", "Handler": "push.push_send.handler"},
    )


def test_push_send_can_read_vapid_secret():
    template, _ = _synth()
    policies = template.find_resources("AWS::IAM::Policy")
    actions = []
    for pol in policies.values():
        for stmt in pol["Properties"]["PolicyDocument"]["Statement"]:
            act = stmt.get("Action")
            actions.extend(act if isinstance(act, list) else [act])
    assert any(a and "secretsmanager:GetSecretValue" in a for a in actions), (
        "PushSend must be granted secretsmanager:GetSecretValue on the VAPID secret"
    )


def test_no_bare_wildcard_resource_on_push_roles():
    template, _ = _synth()
    policies = template.find_resources("AWS::IAM::Policy")
    for name, pol in policies.items():
        # The CDK LogRetention custom-resource role needs logs:* on "*"; it is not
        # one of our push Lambda roles.
        if name.startswith("LogRetention"):
            continue
        for stmt in pol["Properties"]["PolicyDocument"]["Statement"]:
            if stmt.get("Effect") != "Allow":
                continue
            resource = stmt.get("Resource")
            items = resource if isinstance(resource, list) else [resource]
            assert "*" not in items, f"Policy {name} grants a bare Resource: '*'"


def test_synth_refuses_a_missing_vapid_subject(monkeypatch):
    monkeypatch.delenv("VAPID_SUBJECT", raising=False)
    with pytest.raises(ValueError, match="vapid_subject"):
        _synth(context={}, suffix="NoSub")
    with pytest.raises(ValueError, match="vapid_subject"):
        _synth(context={"vapid_subject": "mailto:"}, suffix="EmptySub")


def test_synth_refuses_an_unbuilt_push_layer():
    with pytest.raises(ValueError, match="build_layer.sh"):
        _synth(layer_dir=_layer_dir(built=False), suffix="Unbuilt")


def _policy_actions_for(template, function_name):
    """IAM actions attached to the role of the Lambda named ``function_name``."""
    fns = template.find_resources("AWS::Lambda::Function", {"Properties": {"FunctionName": function_name}})
    role_ref = next(iter(fns.values()))["Properties"]["Role"]["Fn::GetAtt"][0]
    actions = []
    for pol in template.find_resources("AWS::IAM::Policy").values():
        if {"Ref": role_ref} not in pol["Properties"]["Roles"]:
            continue
        for stmt in pol["Properties"]["PolicyDocument"]["Statement"]:
            act = stmt.get("Action")
            actions.extend(act if isinstance(act, list) else [act])
    return actions, next(iter(fns.values()))["Properties"]


def test_push_api_has_no_access_to_the_vapid_secret():
    """PushApi reads one SSM parameter and nothing else; the secret is PushSend's."""
    template, _ = _synth()
    actions, props = _policy_actions_for(template, "StravaAIBoost-PushApi")
    assert not any(a.startswith("secretsmanager:") for a in actions)
    assert "VAPID_SECRET" not in props["Environment"]["Variables"]
    assert len(props["Layers"]) == 1  # no pywebpush layer on the API Lambda


def test_push_api_ssm_access_is_exactly_one_get_on_one_parameter():
    """Only ssm:GetParameter (no plural, no history, no write, no kms) on the exact
    ARN of the application server key SecureString."""
    template, _ = _synth()
    fns = template.find_resources(
        "AWS::Lambda::Function", {"Properties": {"FunctionName": "StravaAIBoost-PushApi"}}
    )
    role_ref = next(iter(fns.values()))["Properties"]["Role"]["Fn::GetAtt"][0]
    ssm_or_kms = []
    for pol in template.find_resources("AWS::IAM::Policy").values():
        if {"Ref": role_ref} not in pol["Properties"]["Roles"]:
            continue
        for stmt in pol["Properties"]["PolicyDocument"]["Statement"]:
            acts = stmt["Action"] if isinstance(stmt["Action"], list) else [stmt["Action"]]
            if any(a.startswith(("ssm:", "kms:")) for a in acts):
                ssm_or_kms.append((acts, stmt["Resource"]))
    assert len(ssm_or_kms) == 1
    acts, resource = ssm_or_kms[0]
    assert acts == ["ssm:GetParameter"]
    arn = "".join(p if isinstance(p, str) else "<ref>" for p in resource["Fn::Join"][1])
    assert arn.endswith(":parameter/strava-ai-boost/push/vapid-application-server-key")
    assert "parameter//" not in arn


def test_push_send_gets_the_vapid_subject():
    template, _ = _synth()
    _, props = _policy_actions_for(template, "StravaAIBoost-PushSend")
    assert props["Environment"]["Variables"]["VAPID_SUBJECT"] == "mailto:ops@example.com"


def test_grant_notify_adds_invoke_permission():
    app = cdk.App(context=CONTEXT)
    core = CoreInfrastructureStack(app, "TestCorePush2", env=FAKE_ENV)
    push = PushStack(app, "TestPush2", core_stack=core, layer_dir=BUILT_LAYER, env=FAKE_ENV)
    from typing import cast

    from aws_cdk import aws_iam as iam

    role = iam.Role(
        push,
        "Grantee",
        assumed_by=cast(iam.IPrincipal, iam.ServicePrincipal("lambda.amazonaws.com")),
    )
    push.grant_notify(role)
    template = assertions.Template.from_stack(push)
    template.has_resource_properties(
        "AWS::IAM::Policy",
        assertions.Match.object_like(
            {
                "PolicyDocument": {
                    "Statement": assertions.Match.array_with(
                        [assertions.Match.object_like({"Action": "lambda:InvokeFunction"})]
                    )
                }
            }
        ),
    )
