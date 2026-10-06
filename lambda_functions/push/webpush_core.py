"""Web Push v1 core -- VAPID key handling and encrypted send (shared by the push Lambdas).

Opt-in, event-driven notifications: a single neutral message is sent only after an
activity the user triggered has been enriched (see BACKLOG.md "Pas de notifications
proactives"). No health data, metric or figure is ever placed in a notification --
only a title, a short body and the target activity route.

VAPID keys
----------
The VAPID key pair (P-256 curve) lives in Secrets Manager under
``strava-ai-boost-vapid-keys`` (same ``strava-ai-boost-*`` convention as the other
secrets of this repo), as a JSON object in raw base64url. Only PushSend can read
that secret; the signing key never leaves it and is neither in the code nor in an
environment variable.

The browser needs the other half of the pair, the *application server key* (W3C
Push API ``applicationServerKey``): it lets the browser bind a subscription to this
server, and cannot sign anything. It is copied to the SSM SecureString parameter
``/strava-ai-boost/push/vapid-application-server-key`` (encrypted with ``aws/ssm``),
which PushApi alone reads to serve ``GET /push/application-server-key`` behind
Cognito. Integrity is what matters for this value: a substituted key would bind new
subscriptions to someone else, so only the bootstrap script, run by an operator,
writes it.

Sending
-------
``pywebpush`` handles the aes128gcm encryption and the VAPID ``Authorization`` header.
An expired endpoint returns 404/410: the caller must then delete the subscription
(410 cleanup, covered by the moto tests).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

import boto3

from shared.logger import get_logger

logger = get_logger("push_core")

REGION = os.environ.get("AWS_REGION", "us-east-1")
VAPID_SECRET_NAME = os.environ.get("VAPID_SECRET", "strava-ai-boost-vapid-keys")
# Application server key only (the browser half of the VAPID pair), readable by
# PushApi without any access to the Secrets Manager secret. SecureString, written by
# scripts/bootstrap_vapid.py.
VAPID_APP_SERVER_KEY_PARAM = os.environ.get(
    "VAPID_APP_SERVER_KEY_PARAM", "/strava-ai-boost/push/vapid-application-server-key"
)


class PushExpired(Exception):
    """The push endpoint no longer exists (404/410): delete the subscription."""


@lru_cache(maxsize=1)
def _secrets_client() -> Any:
    return boto3.client("secretsmanager", region_name=REGION)


@lru_cache(maxsize=1)
def _ssm_client() -> Any:
    return boto3.client("ssm", region_name=REGION)


def vapid_subject() -> str:
    """VAPID contact subject (RFC 8292 ``sub``), read at call time.

    Push services reject a JWT whose ``sub`` is empty, so a missing or malformed
    value fails loudly here instead of producing notifications that never arrive.
    """
    subject = os.environ.get("VAPID_SUBJECT", "").strip()
    if not subject.startswith(("mailto:", "https://")) or subject in ("mailto:", "https://"):
        raise ValueError("VAPID_SUBJECT must be a mailto: or https: URI")
    return subject


@lru_cache(maxsize=1)
def _load_vapid() -> dict[str, str]:
    """Load the VAPID pair from Secrets Manager (cached per container)."""
    resp = _secrets_client().get_secret_value(SecretId=VAPID_SECRET_NAME)
    data = json.loads(resp["SecretString"])
    if "public_key" not in data or "private_key" not in data:
        # Field names follow the VAPID / py-vapid convention; this JSON never leaves
        # the secret, which only PushSend can read.
        raise ValueError("VAPID secret is incomplete")
    return data


@lru_cache(maxsize=1)
def get_application_server_key() -> str:
    """VAPID application server key (base64url), served to the browser.

    Read from its own SecureString parameter (decrypted by SSM with ``aws/ssm``) so
    the caller never needs the Secrets Manager secret that holds the signing key.
    """
    resp = _ssm_client().get_parameter(Name=VAPID_APP_SERVER_KEY_PARAM, WithDecryption=True)
    value = (resp.get("Parameter") or {}).get("Value", "").strip()
    if not value:
        raise ValueError("VAPID application server key parameter is empty")
    return value


def send_push(subscription: dict[str, Any], payload: dict[str, Any]) -> None:
    """Send an encrypted notification to one Web Push subscription.

    ``subscription`` is the browser PushSubscription object
    (``{"endpoint", "keys": {"p256dh", "auth"}}``). ``payload`` is the JSON read by
    the service worker. Raises :class:`PushExpired` on 404/410 (dead endpoint).
    """
    # Lazy import: the dependency lives in the Lambda layer. Importing it lazily keeps
    # modules that import this one indirectly from requiring pywebpush at load time.
    from pywebpush import WebPushException, webpush

    vapid = _load_vapid()
    subject = vapid_subject()
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=vapid["private_key"],
            vapid_claims={"sub": subject},
        )
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            raise PushExpired(str(exc)) from exc
        raise
