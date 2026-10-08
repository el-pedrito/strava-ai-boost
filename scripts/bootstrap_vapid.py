#!/usr/bin/env python3
"""Seed the VAPID key pair (Web Push).

Manual, rare step run by an operator with their own credentials (see README § Web
Push notifications). The CDK stack creates the Secrets Manager secret
``strava-ai-boost-vapid-keys`` with a random placeholder value (the ``Secret()``
default), which this script reports as ``placeholder``; this script:

1. writes the VAPID pair into that secret (raw base64url, the format expected by
   ``lambda_functions/push/webpush_core.py``). Only PushSend can read it;
2. copies the browser half of the pair, the *application server key* (W3C Push API
   ``applicationServerKey``), to the SSM **SecureString** parameter
   ``/strava-ai-boost/push/vapid-application-server-key``, encrypted with the AWS
   managed key ``aws/ssm`` and tagged. PushApi reads only this parameter. Its
   integrity matters (a substituted key would bind new subscriptions to someone
   else), so only this operator script writes it. CloudFormation cannot create a
   SecureString, hence this step.

- Default: ``--dry-run`` (shows the state, generates and writes nothing).
- ``--apply``: generates the pair and stores both. Refuses to overwrite an existing
  valid pair without ``--rotate`` (a rotation invalidates ALL subscriptions); on an
  existing pair it only re-syncs the SecureString parameter.
- The signing key is never printed.

Usage:
    python scripts/bootstrap_vapid.py --dry-run --profile myprofile --region us-east-1
    python scripts/bootstrap_vapid.py --apply --profile myprofile
"""

from __future__ import annotations

import argparse
import base64
import json
import sys

import boto3
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

SECRET_NAME = "strava-ai-boost-vapid-keys"
APP_SERVER_KEY_PARAM = "/strava-ai-boost/push/vapid-application-server-key"
PARAM_TAGS = [
    {"Key": "Project", "Value": "strava-ai-boost"},
    {"Key": "Component", "Value": "web-push"},
]
DEFAULT_REGION = "us-east-1"
# Field names inside the secret follow the VAPID / py-vapid convention. This JSON
# never leaves Secrets Manager.
_SIGNING_FIELD = "private_key"
_APP_SERVER_FIELD = "public_key"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_pair() -> dict[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    signing_raw = key.private_numbers().private_value.to_bytes(32, "big")
    app_server_raw = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    assert len(app_server_raw) == 65 and len(signing_raw) == 32
    return {_APP_SERVER_FIELD: _b64url(app_server_raw), _SIGNING_FIELD: _b64url(signing_raw)}


def _read_pair(sm) -> dict | None:
    """Return the stored pair, or None when the secret is missing. Never printed."""
    try:
        value = sm.get_secret_value(SecretId=SECRET_NAME).get("SecretString") or ""
    except sm.exceptions.ResourceNotFoundException:
        return None
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def state_of(pair: dict | None) -> str:
    """'valid' | 'placeholder' | 'missing' -- never the secret content."""
    if pair is None:
        return "missing"
    if pair.get(_APP_SERVER_FIELD) and pair.get(_SIGNING_FIELD):
        return "valid"
    return "placeholder"


def publish_application_server_key(ssm, value: str) -> None:
    """Store the browser half of the pair as a SecureString (aws/ssm), tagged.

    Never the signing key. ``Overwrite`` keeps the parameter in sync after a
    rotation; tags cannot be passed together with ``Overwrite`` so they are applied
    separately.
    """
    ssm.put_parameter(
        Name=APP_SERVER_KEY_PARAM,
        Value=value,
        Type="SecureString",
        Overwrite=True,
        Tier="Standard",
        Description="VAPID application server key for Web Push (read by StravaAIBoost-PushApi)",
    )
    ssm.add_tags_to_resource(
        ResourceType="Parameter", ResourceId=APP_SERVER_KEY_PARAM, Tags=PARAM_TAGS
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--apply", action="store_true", help="generate and store the pair")
    ap.add_argument("--rotate", action="store_true", help="allow overwriting a valid pair")
    ap.add_argument("--dry-run", action="store_true", help="(default) show state, write nothing")
    ap.add_argument("--profile", default=None, help="AWS profile name")
    ap.add_argument("--region", default=DEFAULT_REGION, help=f"AWS region (default {DEFAULT_REGION})")
    args = ap.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    sm = session.client("secretsmanager")
    pair = _read_pair(sm)
    state = state_of(pair)
    print(f"secret {SECRET_NAME}: {state}")

    if not args.apply:
        print("dry-run: nothing written. Re-run with --apply to seed the pair.")
        return 0
    if state == "missing":
        print("Secret does not exist: deploy the StravaAIBoost-Push stack first.", file=sys.stderr)
        return 2
    ssm = session.client("ssm")
    if state == "valid" and not args.rotate:
        publish_application_server_key(ssm, pair[_APP_SERVER_FIELD])
        print(f"A valid pair already exists ({APP_SERVER_KEY_PARAM} re-synced); "
              "use --rotate to replace it (invalidates all subscriptions).")
        return 0

    pair = generate_pair()
    sm.put_secret_value(SecretId=SECRET_NAME, SecretString=json.dumps(pair))
    publish_application_server_key(ssm, pair[_APP_SERVER_FIELD])
    print(f"pair written; application server key stored in {APP_SERVER_KEY_PARAM} "
          "(SecureString). The signing key is not shown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
