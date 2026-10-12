"""Reliability plan, lot 3: the Step Functions tasks carry the transient Retry blocks."""

import json
import os
import sys

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from stacks.core_infrastructure_stack import CoreInfrastructureStack  # noqa: E402
from stacks.content_generation_stack import ContentGenerationStack  # noqa: E402

TRANSIENT = {
    "Lambda.ServiceException",
    "Lambda.TooManyRequestsException",
    "Sandbox.Timedout",
    "TransientAgentError",
}


def _render(definition) -> str:
    """Flatten the Fn::Join of DefinitionString, replacing tokens by a placeholder."""
    if isinstance(definition, str):
        return definition
    parts = definition["Fn::Join"][1]
    return "".join(p if isinstance(p, str) else "TOKEN" for p in parts)


@pytest.fixture(scope="module")
def states():
    app = cdk.App()
    env = cdk.Environment(account="123456789012", region="eu-west-1")
    core = CoreInfrastructureStack(app, "TestCoreStack", env=env)
    stack = ContentGenerationStack(app, "TestContentStack", core_stack=core, env=env)
    template = assertions.Template.from_stack(stack)
    machines = template.find_resources("AWS::StepFunctions::StateMachine")
    assert len(machines) == 1
    machine = next(iter(machines.values()))
    definition = json.loads(_render(machine["Properties"]["DefinitionString"]))
    flat = dict(definition["States"])
    for state in definition["States"].values():
        for branch in state.get("Branches", []):
            flat.update(branch["States"])
    return flat


def _transient_retrier(state):
    return next(r for r in state.get("Retry", []) if "TransientAgentError" in r["ErrorEquals"])


@pytest.mark.parametrize("task", ["GenerateContent", "GenerateCoach", "UpdateStrava"])
def test_task_retries_transient_errors(states, task):
    retrier = _transient_retrier(states[task])
    assert TRANSIENT <= set(retrier["ErrorEquals"])
    assert retrier["MaxAttempts"] == 2
    assert retrier["BackoffRate"] == 2
    assert retrier["IntervalSeconds"] == 10


def test_update_strava_also_retries_rate_limit(states):
    assert "StravaRateLimitError" in _transient_retrier(states["UpdateStrava"])["ErrorEquals"]


@pytest.mark.parametrize("task", ["GenerateContent", "GenerateCoach", "UpdateStrava"])
def test_one_retrier_per_error(states, task):
    seen = [e for r in states[task]["Retry"] for e in r["ErrorEquals"]]
    assert len(seen) == len(set(seen))


def test_coach_keeps_its_fallback_catch(states):
    catches = states["GenerateCoach"].get("Catch", [])
    assert any(c["Next"] == "CoachErrorFallback" for c in catches)
