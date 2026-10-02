"""Web Push v1 core -- VAPID key handling and encrypted send (shared by the push Lambdas).

Opt-in, event-driven notifications: a single neutral message is sent only after an
activity the user triggered has been enriched (see BACKLOG.md "Pas de notifications
proactives"). No health data, metric or figure is ever placed in a notification --
only a title, a short body and the target activity route.

VAPID keys
----------
The VAPID key pair (P-256 curve) lives in Secrets Manager under
``strava-ai-boost-vapid-keys`` (same ``strava-ai-boost-*`` convention as the other
secrets of this repo). The secret holds a JSON ``{"public_key", "private_key"}`` in
raw base64url (65 bytes for the public key, 32 for the private one). The private key
never leaves Secrets Manager: it is neither in the code nor in an environment
variable. The public key is served as-is by ``GET /push/vapid-public-key`` for the
browser subscription step.

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
# VAPID contact subject (RFC 8292 `sub`). Overridable via env/CDK context; no
# hardcoded personal email -- an empty default degrades to a mailto with no address.
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:")


class PushExpired(Exception):
    """The push endpoint no longer exists (404/410): delete the subscription."""


@lru_cache(maxsize=1)
def _secrets_client() -> Any:
    return boto3.client("secretsmanager", region_name=REGION)


@lru_cache(maxsize=1)
def _load_vapid() -> dict[str, str]:
    """Load the VAPID pair from Secrets Manager (cached per container)."""
    resp = _secrets_client().get_secret_value(SecretId=VAPID_SECRET_NAME)
    data = json.loads(resp["SecretString"])
    if "public_key" not in data or "private_key" not in data:
        raise ValueError("VAPID secret must contain public_key and private_key")
    return data


def get_public_key() -> str:
    """VAPID public key (base64url), exposed to the browser for subscription."""
    return _load_vapid()["public_key"]


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
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=vapid["private_key"],
            vapid_claims={"sub": VAPID_SUBJECT},
        )
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            raise PushExpired(str(exc)) from exc
        raise
