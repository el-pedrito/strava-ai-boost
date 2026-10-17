"""CDK assertions for reliability plan lot 7 (pre-publication hardening). Synth only.

- no `foundation-model/*` (nor `inference-profile/*`) Bedrock wildcard in any IAM
  policy of the stacks that grant Bedrock access;
- the AgentCore memory execution role keeps the model its LIVE custom strategy runs
  with (Haiku 4.5), otherwise preference extraction breaks silently;
- DynamoDB tables and secrets of the Core stack are Retain + PITR;
- the webhook API stage is throttled;
- the daily Bedrock cost alarm exists and notifies the ops topic.
"""

import os
import sys

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from stacks.content_generation_stack import ContentGenerationStack  # noqa: E402
from stacks.core_infrastructure_stack import CoreInfrastructureStack  # noqa: E402
from stacks.feedback_loop_stack import FeedbackLoopStack  # noqa: E402
from stacks.security_stack import LIVE_MEMORY_STRATEGY_MODEL_ID, SecurityStack  # noqa: E402
from stacks.voice_debrief_stack import VoiceDebriefStack  # noqa: E402
from stacks.webhook_processing_stack import (  # noqa: E402
    BEDROCK_DAILY_TOKEN_THRESHOLD,
    WEBHOOK_THROTTLE_BURST_LIMIT,
    WEBHOOK_THROTTLE_RATE_LIMIT,
    WebhookProcessingStack,
)

SFN_ARN = "arn:aws:states:us-east-1:123456789012:stateMachine:test"


@pytest.fixture(scope="module")
def templates() -> dict:
    app = cdk.App()
    env = cdk.Environment(account="123456789012", region="us-east-1")
    core = CoreInfrastructureStack(app, "TestCore", env=env)
    security = SecurityStack(app, "TestSecurity", env=env)
    content = ContentGenerationStack(app, "TestContent", core_stack=core,
                                     security_stack=security, env=env)
    webhook = WebhookProcessingStack(app, "TestWebhook", core_stack=core,
                                     step_functions_arn=SFN_ARN, env=env)
    voice = VoiceDebriefStack(app, "TestVoice", core_stack=core, env=env)
    feedback = FeedbackLoopStack(
        app, "TestFeedback",
        activities_table=core.activities_table,
        strava_oauth_secret=core.strava_oauth_secret,
        strava_app_secret=core.strava_app_secret,
        dependencies_layer=core.dependencies_layer,
        env=env,
    )
    stacks = {"core": core, "security": security, "content": content,
              "webhook": webhook, "voice": voice, "feedback": feedback}
    return {k: assertions.Template.from_stack(s).to_json() for k, s in stacks.items()}


def _flatten(value) -> str:
    """Render an IAM resource (string or Fn::Join) as a plain string."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and "Fn::Join" in value:
        sep, parts = value["Fn::Join"]
        return sep.join(_flatten(p) for p in parts)
    return "TOKEN"


def _bedrock_statements(template: dict):
    for logical_id, res in template["Resources"].items():
        if res["Type"] not in ("AWS::IAM::Policy", "AWS::IAM::ManagedPolicy", "AWS::IAM::Role"):
            continue
        docs = []
        if "PolicyDocument" in res["Properties"]:
            docs.append(res["Properties"]["PolicyDocument"])
        docs += [p["PolicyDocument"] for p in res["Properties"].get("Policies", [])]
        for doc in docs:
            for stmt in doc["Statement"]:
                actions = stmt.get("Action", [])
                actions = actions if isinstance(actions, list) else [actions]
                if any(a.startswith("bedrock:") for a in actions):
                    resources = stmt["Resource"] if isinstance(stmt["Resource"], list) else [stmt["Resource"]]
                    yield logical_id, [_flatten(r) for r in resources]


def test_no_bedrock_model_wildcard_anywhere(templates):
    seen = 0
    for name, template in templates.items():
        for logical_id, resources in _bedrock_statements(template):
            seen += 1
            for arn in resources:
                assert arn != "*", f"{name}/{logical_id}: Resource *"
                assert not arn.endswith("foundation-model/*"), f"{name}/{logical_id}: {arn}"
                assert not arn.endswith("inference-profile/*"), f"{name}/{logical_id}: {arn}"
    assert seen >= 6, "expected the Bedrock statements of the 6 stacks to be inspected"


def test_memory_role_keeps_live_strategy_model(templates):
    resources = [arn for _, rs in _bedrock_statements(templates["security"]) for arn in rs]
    fm = LIVE_MEMORY_STRATEGY_MODEL_ID.split(".", 1)[1]
    assert any(arn.endswith(f"inference-profile/{LIVE_MEMORY_STRATEGY_MODEL_ID}") for arn in resources)
    assert f"arn:aws:bedrock:*::foundation-model/{fm}" in resources


def test_core_lambda_roles_use_registry_only(templates):
    from config.llm_config import all_iam_resources

    expected = {a.split(":", 5)[5] for a in all_iam_resources()}
    for logical_id, resources in _bedrock_statements(templates["core"]):
        assert {a.split(":", 5)[5] for a in resources} == expected, logical_id


def test_core_tables_retained_with_pitr(templates):
    tables = {k: r for k, r in templates["core"]["Resources"].items()
              if r["Type"] == "AWS::DynamoDB::Table"}
    # 4 tables since A1 added the wellness table (activities, user-config,
    # coaching-sessions, wellness) — all RETAIN + PITR.
    assert len(tables) == 4
    for logical_id, res in tables.items():
        assert res["DeletionPolicy"] == "Retain", logical_id
        assert res["UpdateReplacePolicy"] == "Retain", logical_id
        pitr = res["Properties"]["PointInTimeRecoverySpecification"]
        assert pitr["PointInTimeRecoveryEnabled"] is True, logical_id


def test_activities_ttl_disabled_history_kept(templates):
    """The activity history is never deleted by TTL (it used to expire after 1 year)."""
    tables = [r for r in templates["core"]["Resources"].values()
              if r["Type"] == "AWS::DynamoDB::Table"
              and r["Properties"].get("TableName") == "strava-ai-boost-activities"]
    assert len(tables) == 1
    ttl = tables[0]["Properties"]["TimeToLiveSpecification"]
    assert ttl["Enabled"] is False


def test_activity_fetcher_writes_no_ttl():
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "lambda_functions/processing/activity_fetcher.py"
    assert "item['expires_at']" not in src.read_text()


def test_core_secrets_retained(templates):
    secrets = {k: r for k, r in templates["core"]["Resources"].items()
               if r["Type"] == "AWS::SecretsManager::Secret"}
    assert len(secrets) == 4
    for logical_id, res in secrets.items():
        assert res["DeletionPolicy"] == "Retain", logical_id
        assert res["UpdateReplacePolicy"] == "Retain", logical_id


def test_webhook_stage_throttled(templates):
    stages = [r for r in templates["webhook"]["Resources"].values()
              if r["Type"] == "AWS::ApiGateway::Stage"]
    assert len(stages) == 1
    settings = stages[0]["Properties"]["MethodSettings"]
    star = next(s for s in settings if s["HttpMethod"] == "*" and s["ResourcePath"] == "/*")
    assert star["ThrottlingRateLimit"] == WEBHOOK_THROTTLE_RATE_LIMIT == 5
    assert star["ThrottlingBurstLimit"] == WEBHOOK_THROTTLE_BURST_LIMIT == 10


def test_webhook_handler_can_read_app_secret(templates):
    resources = templates["webhook"]["Resources"]
    handler = next(r for r in resources.values()
                   if r["Type"] == "AWS::Lambda::Function"
                   and r["Properties"].get("FunctionName") == "StravaAIBoost-WebhookHandler")
    assert "STRAVA_APP_SECRET" in handler["Properties"]["Environment"]["Variables"]


def test_bedrock_cost_alarm(templates):
    alarms = {r["Properties"]["AlarmName"]: r["Properties"]
              for r in templates["webhook"]["Resources"].values()
              if r["Type"] == "AWS::CloudWatch::Alarm"}
    props = alarms["strava-ai-boost-bedrock-daily-tokens"]
    assert props["Threshold"] == BEDROCK_DAILY_TOKEN_THRESHOLD
    assert props["ComparisonOperator"] == "GreaterThanThreshold"
    assert props["TreatMissingData"] == "notBreaching"
    assert props["EvaluationPeriods"] == 1
    assert props["AlarmActions"], "cost alarm must notify the ops topic"
    stats = {m["Id"]: m["MetricStat"] for m in props["Metrics"] if "MetricStat" in m}
    assert stats["input"]["Metric"]["MetricName"] == "InputTokenCount"
    assert stats["output"]["Metric"]["MetricName"] == "OutputTokenCount"
    for stat in stats.values():
        assert stat["Metric"]["Namespace"] == "AWS/Bedrock"
        assert stat["Period"] == 86400
        assert stat["Stat"] == "Sum"
    expr = next(m["Expression"] for m in props["Metrics"] if "Expression" in m)
    assert expr == "FILL(input, 0) + 5 * FILL(output, 0)"
