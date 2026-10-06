"""Push stack -- StravaAIBoost-Push.

Opt-in Web Push notifications v1: a single neutral "activity enriched" message sent
after a Strava activity the user triggered has been updated (strictly opt-in, no
proactive nagging -- see BACKLOG.md).

Owns:
- The DynamoDB table ``strava-ai-boost-push-subscriptions`` (PK ``user_id``,
  SK ``endpoint_hash``): one item per browser subscription. Low-value data
  (recreated by a simple re-subscribe), but PITR + AWS-managed encryption for
  consistency with the other tables of this repo.
- The Secrets Manager secret ``strava-ai-boost-vapid-keys`` (``strava-ai-boost-*``
  convention): the VAPID key pair, seeded out of CDK by
  ``scripts/bootstrap_vapid.py``. The signing key is never in the code nor in an
  environment variable -- only ``PushSend`` can read this secret.
- The browser half of the pair (W3C ``applicationServerKey``) is served by
  ``PushApi`` at ``GET /push/application-server-key``, behind Cognito, from the SSM
  SecureString ``/strava-ai-boost/push/vapid-application-server-key``. The bootstrap
  script writes it (CloudFormation cannot create a SecureString); its integrity
  matters, so nothing in this stack can write it.
- ``StravaAIBoost-PushApi``: Lambda serving /push/* (routes wired in the API stack).
- ``StravaAIBoost-PushSend``: send + 410 cleanup Lambda, invoked asynchronously by
  StravaUpdater via ``shared.push_notify``.

Least privilege: each Lambda has its own role. ``PushApi`` reads/writes ITS table and
gets ``ssm:GetParameter`` on that one parameter only (no GetParameters, no
GetParameterHistory, no Secrets Manager). Decryption needs no ``kms:Decrypt`` grant:
the AWS managed key ``aws/ssm`` allows it for account principals calling through SSM.
``PushSend`` reads/writes ITS table (410 cleanup) and reads the VAPID secret (to
sign). ``grant_notify`` adds a single explicit ``lambda:InvokeFunction`` on the exact
PushSend ARN (not ``grant_invoke``, which also adds the ``:*`` alias/version ARN).
"""

from __future__ import annotations

import os

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

from .core_infrastructure_stack import CoreInfrastructureStack
from .layer_hash import compute_layer_asset_hash

PUSH_SUBSCRIPTIONS_TABLE_NAME = "strava-ai-boost-push-subscriptions"
VAPID_SECRET_NAME = "strava-ai-boost-vapid-keys"
# Browser half of the VAPID pair (W3C applicationServerKey), SSM SecureString written
# by scripts/bootstrap_vapid.py. PushApi reads this and nothing else.
VAPID_APP_SERVER_KEY_PARAM = "/strava-ai-boost/push/vapid-application-server-key"
PUSH_LAYER_DIR = os.path.join(os.path.dirname(__file__), "..", "lambda_layer_push")


def require_vapid_subject(value: str) -> str:
    """Fail synth on a missing or malformed VAPID subject (RFC 8292 ``sub``).

    Push services reject a JWT with an empty ``sub``; an empty value would deploy
    fine and silently never deliver anything.
    """
    subject = (value or "").strip()
    if not subject.startswith(("mailto:", "https://")) or subject in ("mailto:", "https://"):
        raise ValueError(
            "push_enabled requires a VAPID subject: deploy with "
            "--context vapid_subject=mailto:you@example.com (or https://...)."
        )
    return subject


def require_built_layer(layer_dir: str) -> None:
    """Fail synth when the push layer was not built (pywebpush missing).

    Without this check an empty folder ships as the layer and PushSend answers 200
    with sent=0 forever, because pywebpush is imported lazily.
    """
    if not os.path.isfile(os.path.join(layer_dir, "python", "pywebpush", "__init__.py")):
        raise ValueError(
            "The Web Push layer is not built: run ./lambda_layer_push/build_layer.sh "
            "before cdk synth/deploy with push_enabled=true."
        )


class PushStack(Stack):
    """StravaAIBoost-Push: subscriptions table, VAPID secret, PushApi + PushSend."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        core_stack: CoreInfrastructureStack,
        layer_dir: str = PUSH_LAYER_DIR,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.core_stack = core_stack
        default_user_id = os.environ.get("DEFAULT_USER_ID", "") or (
            self.node.try_get_context("default_user_id") or ""
        )
        vapid_subject = require_vapid_subject(
            os.environ.get("VAPID_SUBJECT", "") or (self.node.try_get_context("vapid_subject") or "")
        )
        require_built_layer(layer_dir)

        # ---- Subscriptions table (PK user_id, SK endpoint_hash) -------------
        self.subscriptions_table = dynamodb.Table(
            self,
            "PushSubscriptionsTable",
            table_name=PUSH_SUBSCRIPTIONS_TABLE_NAME,
            partition_key=dynamodb.Attribute(
                name="user_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="endpoint_hash",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ---- VAPID secret (private key never in code/env) -------------------
        # Content ({"public_key","private_key"} base64url) seeded out of CDK by
        # scripts/bootstrap_vapid.py, like the other strava-ai-boost-* secrets.
        self.vapid_secret = secretsmanager.Secret(
            self,
            "VapidKeys",
            secret_name=VAPID_SECRET_NAME,
            description="VAPID key pair (P-256) for Web Push notifications",
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ---- Push-only layer (pywebpush) ------------------------------------
        # Owned by this stack and attached only to the push Lambdas, so adding or
        # bumping pywebpush never touches the shared layer exported by Core (which
        # cannot be replaced, see README "Known Issues"). Build it first with
        # lambda_layer_push/build_layer.sh; the hash follows its definition files.
        self.push_layer = lambda_.LayerVersion(
            self,
            "PushDependenciesLayer",
            layer_version_name="strava-ai-boost-push-dependencies",
            code=lambda_.Code.from_asset(
                layer_dir,
                asset_hash=compute_layer_asset_hash(layer_dir),
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Web Push dependencies (pywebpush) for the push Lambdas",
            removal_policy=RemovalPolicy.DESTROY,
        )

        common_code = lambda_.Code.from_asset(
            "lambda_functions",
            exclude=["**/__pycache__", "**/*.pyc"],
        )

        api_env = {
            "PUSH_SUBSCRIPTIONS_TABLE": self.subscriptions_table.table_name,
            "VAPID_APP_SERVER_KEY_PARAM": VAPID_APP_SERVER_KEY_PARAM,
            "DEFAULT_USER_ID": default_user_id,
        }
        send_env = {
            "PUSH_SUBSCRIPTIONS_TABLE": self.subscriptions_table.table_name,
            "VAPID_SECRET": self.vapid_secret.secret_name,
            "VAPID_SUBJECT": vapid_subject,
            "DEFAULT_USER_ID": default_user_id,
        }

        # ---- PushApi: /push/* (routes wired in the API stack) ---------------
        self.push_api_lambda = lambda_.Function(
            self,
            "PushApi",
            function_name="StravaAIBoost-PushApi",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="push.push_api.handler",
            code=common_code,
            # No push layer: PushApi never signs or encrypts anything.
            layers=[core_stack.dependencies_layer],
            timeout=Duration.seconds(30),
            memory_size=256,
            environment=api_env,
        )
        # Least privilege: RW its table + ssm:GetParameter on the one SecureString
        # holding the application server key. Nothing on the Secrets Manager secret,
        # no GetParameters / GetParameterHistory, no write. No kms:Decrypt either:
        # the AWS managed key aws/ssm already allows it through SSM for this account.
        self.subscriptions_table.grant_read_write_data(self.push_api_lambda)
        self.push_api_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:GetParameter"],
                resources=[
                    self.format_arn(
                        service="ssm",
                        resource="parameter",
                        # No leading slash: the ARN is ...:parameter/strava-ai-boost/...
                        resource_name=VAPID_APP_SERVER_KEY_PARAM.lstrip("/"),
                    )
                ],
            )
        )

        # ---- PushSend: send + 410 cleanup -----------------------------------
        self.push_send_lambda = lambda_.Function(
            self,
            "PushSend",
            function_name="StravaAIBoost-PushSend",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="push.push_send.handler",
            code=common_code,
            layers=[core_stack.dependencies_layer, self.push_layer],
            timeout=Duration.seconds(30),
            memory_size=256,
            environment=send_env,
        )
        # Least privilege: RW its table (410 cleanup) + READ the VAPID secret
        # (private key, to sign). Nothing else.
        self.subscriptions_table.grant_read_write_data(self.push_send_lambda)
        self.vapid_secret.grant_read(self.push_send_lambda)

    def grant_notify(self, grantee: iam.IGrantable) -> None:
        """Allow ``grantee`` (StravaUpdater) to invoke PushSend asynchronously.

        Explicit ``lambda:InvokeFunction`` on the exact function ARN -- not
        ``grant_invoke`` which also grants the ``<arn>:*`` alias/version ARN.
        """
        grantee.grant_principal.add_to_principal_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=[self.push_send_lambda.function_arn],
            )
        )
