"""RPE athlete input: the synthesized state machine and the InputWait Lambda (§3, §5).

CDK assertions on the Content stack template:
- ShouldWaitForInput (Choice) is the start state, guarded by IsPresent so an
  execution without the field takes the old path;
- WaitForAthleteInput is a waitForTaskToken invoke with a 1 h timeout, result
  discarded, no retry, and one States.ALL catcher, both exits to TransformInput;
- TransformInput never references wait_for_input;
- the overall timeout is 120 min;
- InputWait: 120 s timeout, its own role with UpdateItem on the activities table
  and states:SendTaskSuccess only (no Failure, no Heartbeat).
"""

from __future__ import annotations

import json
import os
import sys

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from stacks.content_generation_stack import ContentGenerationStack  # noqa: E402
from stacks.core_infrastructure_stack import CoreInfrastructureStack  # noqa: E402


def _render(definition) -> str:
    if isinstance(definition, str):
        return definition
    parts = definition["Fn::Join"][1]
    return "".join(p if isinstance(p, str) else "TOKEN" for p in parts)


@pytest.fixture(scope="module")
def template() -> dict:
    app = cdk.App()
    env = cdk.Environment(account="123456789012", region="eu-west-1")
    core = CoreInfrastructureStack(app, "TestCoreRpe", env=env)
    stack = ContentGenerationStack(app, "TestContentRpe", core_stack=core, env=env)
    return assertions.Template.from_stack(stack).to_json()


@pytest.fixture(scope="module")
def asl(template) -> dict:
    machines = [r for r in template["Resources"].values() if r["Type"] == "AWS::StepFunctions::StateMachine"]
    assert len(machines) == 1
    return json.loads(_render(machines[0]["Properties"]["DefinitionString"]))


def test_choice_is_the_start_state(asl):
    assert asl["StartAt"] == "ShouldWaitForInput"
    assert asl["States"]["ShouldWaitForInput"]["Type"] == "Choice"


def test_choice_guards_with_is_present(asl):
    choice = asl["States"]["ShouldWaitForInput"]
    assert len(choice["Choices"]) == 1
    rule = choice["Choices"][0]
    assert rule["Next"] == "WaitForAthleteInput"
    assert {"Variable": "$.wait_for_input", "IsPresent": True} in rule["And"]
    assert {"Variable": "$.wait_for_input", "BooleanEquals": True} in rule["And"]
    assert choice["Default"] == "TransformInput"


def test_wait_task_is_a_one_hour_callback(asl):
    wait = asl["States"]["WaitForAthleteInput"]
    assert wait["Resource"].endswith(":states:::lambda:invoke.waitForTaskToken")
    assert wait["TimeoutSeconds"] == 3600
    assert wait["ResultPath"] is None
    assert wait["Parameters"]["Payload"] == {
        "activity_id.$": "$.activity_id",
        "user_id.$": "$.user_id",
        "task_token.$": "$$.Task.Token",
    }
    assert wait["Next"] == "TransformInput"


def test_wait_task_has_no_retry(asl):
    assert "Retry" not in asl["States"]["WaitForAthleteInput"]


def test_wait_task_has_a_single_states_all_catcher(asl):
    catches = asl["States"]["WaitForAthleteInput"]["Catch"]
    assert catches == [{
        "ErrorEquals": ["States.ALL"],
        "ResultPath": "$.input_wait_error",
        "Next": "TransformInput",
    }]


def test_transform_input_ignores_wait_for_input(asl):
    transform = asl["States"]["TransformInput"]
    assert "wait_for_input" not in json.dumps(transform)
    assert "input_wait_error" not in json.dumps(transform)
    assert transform["Next"] == "FetchActivityData"


def test_overall_timeout_is_120_minutes(asl):
    assert asl["TimeoutSeconds"] == 7200


def _input_wait_function(template) -> dict:
    return next(
        r for r in template["Resources"].values()
        if r["Type"] == "AWS::Lambda::Function"
        and r["Properties"].get("FunctionName") == "StravaAIBoost-InputWait"
    )


def test_input_wait_lambda(template):
    props = _input_wait_function(template)["Properties"]
    assert props["Handler"] == "athlete_input.input_wait.handler"
    assert props["Timeout"] == 120
    assert props["Runtime"] == "python3.12"
    assert "ACTIVITIES_TABLE" in props["Environment"]["Variables"]
    # Push wiring is added from app.py only when the Push stack exists.
    assert "PUSH_ENABLED" not in props["Environment"]["Variables"]


def test_input_wait_role_least_privilege(template):
    policies = [
        r for k, r in template["Resources"].items()
        if r["Type"] == "AWS::IAM::Policy" and k.startswith("InputWaitRole")
    ]
    assert len(policies) == 1
    statements = policies[0]["Properties"]["PolicyDocument"]["Statement"]
    actions = sorted(s["Action"] if isinstance(s["Action"], str) else ",".join(s["Action"]) for s in statements)
    assert actions == ["dynamodb:UpdateItem", "states:SendTaskSuccess"]
    for statement in statements:
        if statement["Action"] == "states:SendTaskSuccess":
            assert statement["Resource"] == "*"
        else:
            assert statement["Resource"] != "*"


def test_step_functions_role_can_invoke_input_wait(template):
    text = json.dumps([
        r for r in template["Resources"].values() if r["Type"] == "AWS::IAM::Policy"
    ])
    input_wait_id = next(
        k for k, r in template["Resources"].items()
        if r["Type"] == "AWS::Lambda::Function"
        and r["Properties"].get("FunctionName") == "StravaAIBoost-InputWait"
    )
    assert input_wait_id in text
