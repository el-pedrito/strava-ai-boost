"""CDK assertions for the business alarms (reliability plan, lot 1).

The Lambdas emit ``<Artefact>Produced{outcome=...}`` in namespace StravaAIBoost; these
alarms are the only thing that turns those datapoints into an email. A typo in a
metric name or dimension here would leave an alarm that can never fire, silently --
the exact failure mode this lot exists to remove. Synth only, no AWS call.
"""

import os
import sys

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from stacks.core_infrastructure_stack import CoreInfrastructureStack  # noqa: E402
from stacks.webhook_processing_stack import WebhookProcessingStack  # noqa: E402

SFN_ARN = "arn:aws:states:eu-west-1:123456789012:stateMachine:test"


@pytest.fixture(scope="module")
def alarms() -> dict:
    """Synthesized alarms of the webhook stack, keyed by AlarmName."""
    app = cdk.App()
    env = cdk.Environment(account="123456789012", region="eu-west-1")
    core = CoreInfrastructureStack(app, "TestCoreStack", env=env)
    stack = WebhookProcessingStack(
        app, "TestWebhookStack", core_stack=core, step_functions_arn=SFN_ARN, env=env
    )
    template = assertions.Template.from_stack(stack).to_json()
    return {
        res["Properties"]["AlarmName"]: res["Properties"]
        for res in template["Resources"].values()
        if res["Type"] == "AWS::CloudWatch::Alarm"
    }


def _metric_stats(props: dict) -> dict:
    """Math-alarm inputs: {id: (namespace, metric name, dimensions, period)}."""
    out = {}
    for m in props.get("Metrics", []):
        if "MetricStat" in m:
            stat = m["MetricStat"]
            metric = stat["Metric"]
            dims = {d["Name"]: d["Value"] for d in metric.get("Dimensions", [])}
            out[m["Id"]] = (metric["Namespace"], metric["MetricName"], dims, stat["Period"])
    return out


def _expression(props: dict) -> str:
    return next(m["Expression"] for m in props["Metrics"] if "Expression" in m)


def test_existing_alarms_kept(alarms):
    for name in ("strava-ai-boost-dlq-messages", "strava-ai-boost-old-messages",
                 "strava-ai-boost-lambda-errors"):
        assert name in alarms


def test_every_alarm_notifies_ops_topic(alarms):
    for name, props in alarms.items():
        assert props.get("AlarmActions"), f"{name} has no action"


def test_activity_not_published(alarms):
    props = alarms["strava-ai-boost-activity-not-published"]
    stats = _metric_stats(props)
    assert stats["published"] == ("StravaAIBoost", "ActivityPublished", {"outcome": "ok"}, 259200)
    assert stats["processed"] == (
        "StravaAIBoost", "ActivitiesProcessed", {"service": "strava-ai-boost"}, 259200
    )
    assert "FILL(published, 0) == 0" in _expression(props)
    assert props["ComparisonOperator"] == "GreaterThanOrEqualToThreshold"
    assert props["Threshold"] == 1
    assert props["TreatMissingData"] == "notBreaching"


# Loops instead of pytest parametrisation: test_docs_sync counts one collected test per def.
FAILED_ALARMS = [
    ("strava-ai-boost-content-failed", "ContentProduced", {"failed", "empty"}),
    ("strava-ai-boost-coach-failed", "CoachProduced", {"failed", "empty"}),
    ("strava-ai-boost-voice-debrief-failed", "VoiceDebriefProduced", {"failed", "empty"}),
    ("strava-ai-boost-weekly-synthesis-failed", "WeeklySynthesisProduced", {"failed"}),
    ("strava-ai-boost-weekly-recap-failed", "WeeklyRecapProduced", {"failed"}),
]
MISSING_ALARMS = [
    ("strava-ai-boost-weekly-synthesis-missing", "WeeklySynthesisProduced", {"ok", "empty"}),
    ("strava-ai-boost-weekly-recap-missing", "WeeklyRecapProduced", {"ok", "degraded", "empty"}),
]


def test_failed_alarms(alarms):
    for name, metric_name, outcomes in FAILED_ALARMS:
        props = alarms[name]
        stats = _metric_stats(props)
        assert {s[2]["outcome"] for s in stats.values()} == outcomes, name
        for namespace, metric, dims, period in stats.values():
            assert (namespace, metric, period) == ("StravaAIBoost", metric_name, 3600), name
            assert set(dims) == {"outcome"}, name
        assert props["ComparisonOperator"] == "GreaterThanOrEqualToThreshold", name
        assert props["Threshold"] == 1, name
        assert props["TreatMissingData"] == "notBreaching", name


def test_weekly_missing_alarms(alarms):
    for name, metric_name, outcomes in MISSING_ALARMS:
        props = alarms[name]
        stats = _metric_stats(props)
        assert {s[2]["outcome"] for s in stats.values()} == outcomes, name
        for namespace, metric, _dims, period in stats.values():
            # 7 days: the longest window an alarm may evaluate (Period x Evaluations).
            assert (namespace, metric, period) == ("StravaAIBoost", metric_name, 604800), name
        assert props["EvaluationPeriods"] == 1, name
        assert props["ComparisonOperator"] == "LessThanThreshold", name
        assert props["Threshold"] == 1, name
        assert props["TreatMissingData"] == "breaching", name


def test_voice_debrief_ratio(alarms):
    props = alarms["strava-ai-boost-voice-debrief-ratio"]
    stats = _metric_stats(props)
    assert stats["voice"][:3] == ("StravaAIBoost", "VoiceDebriefProduced", {"outcome": "ok"})
    assert stats["published"][:3] == ("StravaAIBoost", "ActivityPublished", {"outcome": "ok"})
    assert stats["voice"][3] == 86400
    assert props["ComparisonOperator"] == "LessThanThreshold"
    assert props["Threshold"] == 0.5


def test_step_functions_executions_failed(alarms):
    props = alarms["strava-ai-boost-sfn-executions-failed"]
    assert props["Namespace"] == "AWS/States"
    assert props["MetricName"] == "ExecutionsFailed"
    assert props["Dimensions"] == [{"Name": "StateMachineArn", "Value": SFN_ARN}]
    assert props["Threshold"] == 1
    assert props["TreatMissingData"] == "notBreaching"
