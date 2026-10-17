"""cdk-nag (AwsSolutions) suppressions, applied from app.py when ``-c nag=true``.

Only findings that are INTENTIONAL for this single-user personal project are
suppressed here, each with a one-line justification. Anything that is a real gap
(access logging, SSL-only queue/topic policies, broad name-prefix grants...) is
deliberately left unsuppressed so it stays visible in CI until it is fixed in the
stack itself.

Two kinds of suppressions:

- app-wide patterns (``_GLOBAL``), keyed by the exact ``appliesTo`` finding, so
  they only ever cover CDK-generated or service-imposed wildcards and survive
  construct renames;
- resource-specific ones (``_BY_PATH``), keyed by stack name and construct path.
  A path that no longer exists is skipped (not an error) so a refactor of a stack
  never breaks synth here; the finding simply reappears in CI if it is real.
"""

from typing import Dict, List

import aws_cdk as cdk
from cdk_nag import NagPackSuppression, NagSuppressions, RegexAppliesTo


def _rx(pattern: str) -> RegexAppliesTo:
    """Wrap a JS regex body as a cdk-nag ``appliesTo`` matcher."""
    return RegexAppliesTo(regex=f"/{pattern}/")


_LAMBDA_BASIC = "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
_APIGW_LOGS = (
    "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/"
    "AmazonAPIGatewayPushToCloudWatchLogs"
)

# Applied to every stack: wildcards CDK generates or the service imposes.
_GLOBAL: List[NagPackSuppression] = [
    NagPackSuppression(
        id="AwsSolutions-IAM4",
        reason="AWSLambdaBasicExecutionRole only grants CloudWatch Logs writes to the function's own log group.",
        applies_to=[_LAMBDA_BASIC],
    ),
    NagPackSuppression(
        id="AwsSolutions-IAM4",
        reason="API Gateway account-level CloudWatch role created by CDK (cloudWatchRole), logs push only.",
        applies_to=[_APIGW_LOGS],
    ),
    NagPackSuppression(
        id="AwsSolutions-IAM5",
        reason="CDK grantInvoke adds '<fn>:*' to cover the function's own versions and aliases.",
        applies_to=[_rx(r"^Resource::<[A-Za-z0-9]+\.Arn>:\*$")],
    ),
    NagPackSuppression(
        id="AwsSolutions-IAM5",
        reason="CDK table grants include the table's own GSIs ('<table>/index/*') used by the queries.",
        applies_to=[_rx(r"^Resource::<[A-Za-z0-9]+\.Arn>/index/\*$")],
    ),
    NagPackSuppression(
        id="AwsSolutions-IAM5",
        reason="DynamoDB stream ARN suffix is a timestamp unknown at synth; scoped to the activities table.",
        applies_to=[_rx(r"^Resource::<[A-Za-z0-9]+\.Arn>/stream/\*$")],
    ),
    NagPackSuppression(
        id="AwsSolutions-IAM5",
        reason="Execution names are generated at runtime; scoped to the single activity state machine.",
        applies_to=[
            _rx(r"^Resource::<ActivityProcessingWorkflow[A-Za-z0-9]+>:\*$"),
            # Same scope written by name from Core (cannot import Content's ARN).
            _rx(
                r"^Resource::arn:aws:states:<AWS::Region>:<AWS::AccountId>:"
                r"execution:StravaAIBoost-ActivityProcessing:\*$"
            ),
        ],
    ),
    NagPackSuppression(
        id="AwsSolutions-IAM5",
        reason="Object-level S3 access needs a key wildcard; scoped to the project's own audio bucket/prefix.",
        applies_to=[
            _rx(r"^Resource::<AudioDebriefsBucket[A-Za-z0-9]+\.Arn>/(recaps/)?\*$"),
            _rx(r"^Resource::arn:aws:s3:::strava-ai-boost-audio-debriefs-<AWS::AccountId>/recaps/\*$"),
        ],
    ),
    NagPackSuppression(
        id="AwsSolutions-IAM5",
        reason="Secrets Manager appends a random 6-char suffix to every secret ARN; scoped to the one named project secret.",
        applies_to=[_rx(
            r"^Resource::arn:aws:secretsmanager:<AWS::Region>:<AWS::AccountId>:"
            r"secret:strava-ai-boost-[a-z-]+-credentials-\*$"
        )],
    ),
    NagPackSuppression(
        id="AwsSolutions-IAM5",
        reason="Cross-region inference profiles route a pinned model to any region, so the model ARN needs region '*'.",
        applies_to=[_rx(r"^Resource::arn:aws:bedrock:\*::foundation-model/[A-Za-z0-9.:-]+$")],
    ),
    NagPackSuppression(
        id="AwsSolutions-IAM5",
        reason="AgentCore runtimes/memories are created by the AgentCore toolkit outside CDK; scoped to account+region.",
        applies_to=[_rx(
                r"^Resource::arn:aws:bedrock-agentcore:(<AWS::Region>|[a-z0-9-]+):"
                r"(<AWS::AccountId>|[0-9]{12}):(runtime|memory)/\*$"
            )],
    ),
    NagPackSuppression(
        id="AwsSolutions-L1",
        reason="Python 3.12 is the project's pinned runtime (Lambda layer and test suite are built for it).",
    ),
]

# Service APIs that only accept Resource '*', keyed by stack -> construct paths.
_STAR_ONLY_REASON = (
    "These actions do not support resource-level permissions "
    "(logs delivery/resource policy, X-Ray config, Polly, dynamodb:ListStreams, "
    "states:SendTaskSuccess)."
)
_STAR_ONLY: Dict[str, List[str]] = {
    "StravaAIBoost-API": [
        "/StravaAIBoost-API/InputSubmit/ServiceRole/DefaultPolicy/Resource",
    ],
    "StravaAIBoost-Content": ["/StravaAIBoost-Content/StepFunctionsRole/DefaultPolicy/Resource"],
    "StravaAIBoost-Feedback": [
        # CDK singleton LogRetention provider id (a fixed hash, not a secret)
        "/StravaAIBoost-Feedback/LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8a/ServiceRole/DefaultPolicy/Resource",  # pragma: allowlist secret
    ],
    "StravaAIBoost-Webhook": [
        # CDK singleton LogRetention provider (WellnessSync log retention)
        "/StravaAIBoost-Webhook/LogRetentionaae0aa3c5b4d4f87b02d85b201efdd8a/ServiceRole/DefaultPolicy/Resource",  # pragma: allowlist secret
    ],
    "StravaAIBoost-Security": [
        "/StravaAIBoost-Security/LogsPolicyHandler/ServiceRole/DefaultPolicy/Resource",
        "/StravaAIBoost-Security/XRayConfigHandler/ServiceRole/DefaultPolicy/Resource",
    ],
    "StravaAIBoost-VoiceDebrief": [
        "/StravaAIBoost-VoiceDebrief/VoiceDebriefGeneratorRole/DefaultPolicy/Resource",
        "/StravaAIBoost-VoiceDebrief/WeeklyRecapRole/DefaultPolicy/Resource",
    ],
}

_THIRD_PARTY_SECRET = NagPackSuppression(
    id="AwsSolutions-SMG4",
    reason="Third-party credentials (Strava, Campus Coach, Intervals.icu) have no rotation API; OAuth tokens are refreshed by the app.",
)

_BY_PATH: Dict[str, Dict[str, List[NagPackSuppression]]] = {
    "StravaAIBoost-Webhook": {
        path: [
            NagPackSuppression(
                id="AwsSolutions-APIG4",
                reason="Strava calls the webhook without credentials; requests are checked by verify_token/HMAC in the handler.",
            ),
            NagPackSuppression(
                id="AwsSolutions-COG4",
                reason="Strava calls the webhook without credentials; a Cognito authorizer cannot apply to it.",
            ),
        ]
        for path in (
            "/StravaAIBoost-Webhook/StravaWebhookAPI/Default/webhook/GET/Resource",
            "/StravaAIBoost-Webhook/StravaWebhookAPI/Default/webhook/POST/Resource",
        )
    },
    "StravaAIBoost-Frontend": {
        "/StravaAIBoost-Frontend/Distribution/Resource": [
            NagPackSuppression(
                id="AwsSolutions-CFR4",
                reason="No custom domain: the default *.cloudfront.net certificate cannot pin a minimum TLS version.",
            ),
        ],
        "/StravaAIBoost-Frontend/UserPool/Resource": [
            NagPackSuppression(
                id="AwsSolutions-COG2",
                reason="Single admin-created user, self sign-up disabled; MFA left to the account owner.",
            ),
            NagPackSuppression(
                id="AwsSolutions-COG8",
                reason="Cognito Plus tier (advanced security) is not worth its cost for a single admin-created user.",
            ),
        ],
    },
    "StravaAIBoost-Core": {
        path: [_THIRD_PARTY_SECRET]
        for path in (
            "/StravaAIBoost-Core/StravaOAuthSecret/Resource",
            "/StravaAIBoost-Core/StravaAppSecret/Resource",
            "/StravaAIBoost-Core/CampusCoachSecret/Resource",
            "/StravaAIBoost-Core/IntervalsICUSecret/Resource",
        )
    },
    "StravaAIBoost-Push": {
        "/StravaAIBoost-Push/VapidKeys/Resource": [
            NagPackSuppression(
                id="AwsSolutions-SMG4",
                reason="VAPID keys are rotated by hand: a new pair invalidates every browser subscription, so there is no rotation Lambda.",
            ),
        ],
    },
}


def _suppress_path(stack: cdk.Stack, path: str, suppressions: List[NagPackSuppression]) -> None:
    """Suppress on one construct path, skipping paths a refactor has removed."""
    if stack.node.try_find_child(path.split("/", 2)[2].split("/", 1)[0]) is None:
        return
    try:
        NagSuppressions.add_resource_suppressions_by_path(stack, path, suppressions)
    except RuntimeError:
        # Path no longer exists (construct renamed): skip, the finding resurfaces in CI.
        return


def apply_nag_suppressions(app: cdk.App) -> None:
    """Attach the justified AwsSolutions suppressions to the app's stacks."""
    for stack in (c for c in app.node.children if isinstance(c, cdk.Stack)):
        NagSuppressions.add_stack_suppressions(stack, _GLOBAL)

        for path in _STAR_ONLY.get(stack.stack_name, []):
            _suppress_path(
                stack,
                path,
                [
                    NagPackSuppression(
                        id="AwsSolutions-IAM5",
                        reason=_STAR_ONLY_REASON,
                        applies_to=["Resource::*"],
                    )
                ],
            )

        for path, suppressions in _BY_PATH.get(stack.stack_name, {}).items():
            _suppress_path(stack, path, suppressions)
