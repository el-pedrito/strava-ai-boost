"""Offline CDK assertions for the Push stack (StravaAIBoost-Push).

With a fake account/region and no AWS calls:
  * the subscriptions table exists with the (user_id, endpoint_hash) key schema and
    PITR enabled;
  * the VAPID secret exists under the strava-ai-boost-* convention and is RETAINed;
  * both Lambdas (PushApi, PushSend) exist on the expected handlers;
  * least privilege: a GetSecretValue statement exists (PushSend signs with the
    private key) and no push role carries a bare Resource: "*";
  * grant_notify adds a lambda:InvokeFunction permission.
"""

import os
import sys

import aws_cdk as cdk
from aws_cdk import assertions

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from stacks.core_infrastructure_stack import CoreInfrastructureStack  # noqa: E402
from stacks.push_stack import (  # noqa: E402
    PUSH_SUBSCRIPTIONS_TABLE_NAME,
    VAPID_SECRET_NAME,
    PushStack,
)

FAKE_ENV = cdk.Environment(account="123456789012", region="us-east-1")


def _synth():
    app = cdk.App()
    core = CoreInfrastructureStack(app, "TestCorePush", env=FAKE_ENV)
    push = PushStack(app, "TestPush", core_stack=core, env=FAKE_ENV)
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


def test_grant_notify_adds_invoke_permission():
    app = cdk.App()
    core = CoreInfrastructureStack(app, "TestCorePush2", env=FAKE_ENV)
    push = PushStack(app, "TestPush2", core_stack=core, env=FAKE_ENV)
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
