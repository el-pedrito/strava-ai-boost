#!/usr/bin/env python3
"""Seed the VAPID key pair (Web Push) into Secrets Manager.

Manual, rare step (see README § Web Push notifications): the CDK stack creates the
secret ``strava-ai-boost-vapid-keys`` empty; this script writes the
``{"public_key", "private_key"}`` pair into it as raw base64url (65 bytes / 32 bytes),
the format expected by ``lambda_functions/push/webpush_core.py`` and the browser
subscription step.

- Default: ``--dry-run`` (shows the secret state, generates nothing).
- ``--apply``: generates the pair and stores it. Refuses to overwrite an existing
  valid pair without ``--rotate`` (a rotation invalidates ALL subscriptions).
- The private key is never printed.

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
DEFAULT_REGION = "us-east-1"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_pair() -> dict[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private_raw = key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    assert len(public_raw) == 65 and len(private_raw) == 32
    return {"public_key": _b64url(public_raw), "private_key": _b64url(private_raw)}


def current_state(sm) -> str:
    """'valid' | 'placeholder' | 'missing' -- never returns the secret content."""
    try:
        value = sm.get_secret_value(SecretId=SECRET_NAME).get("SecretString") or ""
    except sm.exceptions.ResourceNotFoundException:
        return "missing"
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return "placeholder"
    if isinstance(data, dict) and data.get("public_key") and data.get("private_key"):
        return "valid"
    return "placeholder"


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
    state = current_state(sm)
    print(f"secret {SECRET_NAME}: {state}")

    if not args.apply:
        print("dry-run: nothing written. Re-run with --apply to seed the pair.")
        return 0
    if state == "missing":
        print("Secret does not exist: deploy the StravaAIBoost-Push stack first.", file=sys.stderr)
        return 2
    if state == "valid" and not args.rotate:
        print("A valid pair already exists; use --rotate to replace it (invalidates all subscriptions).")
        return 0

    pair = generate_pair()
    sm.put_secret_value(SecretId=SECRET_NAME, SecretString=json.dumps(pair))
    print(f"pair written. public_key={pair['public_key'][:12]}... (private key not shown)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
