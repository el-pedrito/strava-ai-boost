"""Web Push v1 core -- VAPID key handling and encrypted send (shared by the push Lambdas).

Opt-in, event-driven notifications: a single neutral message is sent only after an
activity the user triggered has been enriched (see BACKLOG.md "Pas de notifications
proactives"). A notification carries only a title, a short body and an internal
route. The body is the enriched activity title, already public on Strava; the
description, which can quote heart rate or pace, is never sent.

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


# How long the push service keeps an undelivered message (seconds). pywebpush
# defaults to 0, which makes a phone that is asleep or offline lose the
# notification: Apple tries once and stores nothing.
PUSH_TTL_SECONDS = 24 * 3600
# Network timeout for one push service call: (connect, read) seconds. Sends run
# one after the other, up to MAX_SUBSCRIPTIONS_PER_USER (10), so even ten slow
# endpoints (10 x 8 s) stay inside the PushSend timeout.
PUSH_HTTP_TIMEOUT_SECONDS = (3, 5)
# Longest url / tag we put in a payload (ours are short internal paths).
MAX_URL_LENGTH = 512
MAX_TAG_LENGTH = 64
# Push services reject encrypted payloads above 4096 bytes; keep the clear text
# well under that once aes128gcm padding and headers are added.
MAX_PAYLOAD_BYTES = 3000

# Hosts of the browser push services this app can receive from. A subscription
# endpoint is a URL the Lambda will POST to, so anything else is refused
# (otherwise an authenticated caller could make PushSend call any URL).
ALLOWED_PUSH_HOSTS = frozenset({"fcm.googleapis.com"})  # Chrome, Edge (Chromium)
ALLOWED_PUSH_DOMAIN_SUFFIXES = (
    ".push.apple.com",             # Safari / iOS Home Screen web apps (web.push.apple.com)
    ".push.services.mozilla.com",  # Firefox
    ".notify.windows.com",         # Edge legacy / Windows
)
MAX_ENDPOINT_LENGTH = 1024
MAX_KEY_LENGTH = 256


class PushExpired(Exception):
    """The push endpoint no longer exists (404/410): delete the subscription."""


def is_allowed_endpoint(endpoint: str) -> bool:
    """True when ``endpoint`` is an https URL on a known browser push service.

    No credentials, no explicit port other than 443, no control character, no IP
    literal: only :data:`ALLOWED_PUSH_HOSTS` and :data:`ALLOWED_PUSH_DOMAIN_SUFFIXES`.
    """
    from urllib.parse import urlsplit

    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > MAX_ENDPOINT_LENGTH:
        return False
    if any(ord(ch) < 0x21 or ord(ch) == 0x7F for ch in endpoint):
        # urlsplit silently strips tabs and newlines; refuse them instead.
        return False
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username or parts.password:
        return False
    if port not in (None, 443):
        return False
    host = (parts.hostname or "").lower()
    if not host:
        return False
    return host in ALLOWED_PUSH_HOSTS or host.endswith(ALLOWED_PUSH_DOMAIN_SUFFIXES)


def _encoded_size(data: dict[str, Any]) -> int:
    return len(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def fit_payload(payload: dict[str, Any]) -> str:
    """JSON-encode ``payload`` within :data:`MAX_PAYLOAD_BYTES`, always.

    ``url`` and ``tag`` longer than their caps fall back to safe defaults
    (the worker maps a missing url to '/'); then ``body`` and ``title`` are
    shortened. The result can never exceed the limit.
    """
    data = {k: v for k, v in payload.items() if k in ("title", "body", "url", "tag")}
    if len(str(data.get("url") or "")) > MAX_URL_LENGTH:
        data["url"] = "/"
    if len(str(data.get("tag") or "")) > MAX_TAG_LENGTH:
        data["tag"] = "strava-ai-boost"
    for field in ("body", "title"):
        text = str(data.get(field) or "")
        while _encoded_size(data) > MAX_PAYLOAD_BYTES and text:
            text = text[: max(0, len(text) - 40)].rstrip()
            data[field] = (text + "…") if text else ""
    return json.dumps(data, ensure_ascii=False)


def _no_redirect_session() -> Any:
    """A requests session that refuses redirects.

    The allowlist checks the endpoint we POST to; a redirect would send the
    request somewhere unchecked, so any 3xx raises instead of being followed.
    """
    import requests

    session = requests.Session()
    session.max_redirects = 0
    return session


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

    if not is_allowed_endpoint(subscription.get("endpoint", "")):
        # Checked again here, not only at subscribe time: a row written before the
        # allowlist existed, or by hand, must never turn into an outbound request.
        raise ValueError("push endpoint is not on an allowed push service")

    vapid = _load_vapid()
    subject = vapid_subject()
    try:
        webpush(
            subscription_info=subscription,
            data=fit_payload(payload),
            vapid_private_key=vapid["private_key"],
            vapid_claims={"sub": subject},
            ttl=PUSH_TTL_SECONDS,
            timeout=PUSH_HTTP_TIMEOUT_SECONDS,
            headers={"Urgency": "normal"},
            requests_session=_no_redirect_session(),
        )
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            raise PushExpired(str(exc)) from exc
        raise
