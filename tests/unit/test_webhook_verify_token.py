"""verify_token fail-closed logic (reliability plan lot 7, BACKLOG "verify_token").

Contract: the token lives in the Strava APP secret. While `webhook_verify_token`
is absent the subscription GET stays open (the live subscription must keep
validating until configure_strava_webhook.sh has written the random token); as
soon as the key exists, only that exact token passes and every error rejects.
WEBHOOK_VERIFY_TOKEN_REQUIRED closes the absent case too (final rollout step).
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from webhooks import webhook_handler  # noqa: E402
from webhooks.webhook_handler import handle_webhook_verification, validate_verify_token  # noqa: E402

TOKEN = "a" * 64


def _client(secret=None, error_code=None, exc=None):
    client = MagicMock()
    if error_code:
        client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": error_code, "Message": "x"}}, "GetSecretValue"
        )
    elif exc:
        client.get_secret_value.side_effect = exc
    else:
        client.get_secret_value.return_value = {
            "SecretString": secret if isinstance(secret, str) else json.dumps(secret)
        }
    return client


@pytest.fixture
def secrets():
    """Patch the Secrets Manager client; yields a setter taking _client kwargs."""
    with patch.object(webhook_handler, "get_secretsmanager_client") as getter:
        def use(**kwargs):
            client = _client(**kwargs)
            getter.return_value = client
            return client
        yield use


@pytest.fixture(autouse=True)
def not_required():
    with patch.object(webhook_handler, "WEBHOOK_VERIFY_TOKEN_REQUIRED", False):
        yield


class TestTokenConfigured:
    """Key present: fail closed."""

    def test_exact_token_accepted(self, secrets):
        client = secrets(secret={"client_id": "1", "webhook_verify_token": TOKEN})
        assert validate_verify_token(TOKEN) is True
        client.get_secret_value.assert_called_once_with(SecretId=webhook_handler.STRAVA_APP_SECRET)

    def test_reads_app_secret_not_oauth_secret(self, secrets):
        client = secrets(secret={"webhook_verify_token": TOKEN})
        validate_verify_token(TOKEN)
        secret_id = client.get_secret_value.call_args.kwargs["SecretId"]
        assert secret_id == webhook_handler.STRAVA_APP_SECRET
        assert secret_id != webhook_handler.STRAVA_OAUTH_SECRET

    def test_other_token_rejected(self, secrets):
        secrets(secret={"webhook_verify_token": TOKEN})
        for received in ("wrong", TOKEN[:-1], TOKEN + "x", TOKEN.upper()):
            assert validate_verify_token(received) is False, received

    def test_missing_received_token_rejected(self, secrets):
        secrets(secret={"webhook_verify_token": TOKEN})
        for received in (None, ""):
            assert validate_verify_token(received) is False

    def test_present_but_empty_or_garbled_key_rejects(self, secrets):
        """The owner wrote the key: an empty/garbled value must not reopen the GET."""
        for stored in ("", None, 123, ["x"]):
            secrets(secret={"webhook_verify_token": stored})
            assert validate_verify_token("anything") is False, stored


class TestTokenAbsent:
    """Key or secret absent: open (live subscription keeps working) unless required."""

    def test_key_absent_allows(self, secrets):
        secrets(secret={"client_id": "1", "client_secret": "2"})
        assert validate_verify_token("whatever") is True

    def test_secret_not_found_allows(self, secrets):
        secrets(error_code="ResourceNotFoundException")
        assert validate_verify_token("whatever") is True

    def test_key_absent_rejects_when_required(self, secrets):
        secrets(secret={"client_id": "1"})
        with patch.object(webhook_handler, "WEBHOOK_VERIFY_TOKEN_REQUIRED", True):
            assert validate_verify_token("whatever") is False

    def test_secret_not_found_rejects_when_required(self, secrets):
        secrets(error_code="ResourceNotFoundException")
        with patch.object(webhook_handler, "WEBHOOK_VERIFY_TOKEN_REQUIRED", True):
            assert validate_verify_token("whatever") is False

    def test_required_still_accepts_the_right_token(self, secrets):
        secrets(secret={"webhook_verify_token": TOKEN})
        with patch.object(webhook_handler, "WEBHOOK_VERIFY_TOKEN_REQUIRED", True):
            assert validate_verify_token(TOKEN) is True


class TestErrorsRejects:
    """An unknown condition never opens the GET."""

    def test_client_errors_reject(self, secrets):
        for code in ("AccessDeniedException", "InternalServiceError", "ThrottlingException"):
            secrets(error_code=code)
            assert validate_verify_token(TOKEN) is False, code

    def test_unexpected_exception_rejects(self, secrets):
        secrets(exc=RuntimeError("network"))
        assert validate_verify_token(TOKEN) is False

    def test_malformed_secret_rejects(self, secrets):
        for raw in ("not json", "[1, 2]", '"a string"'):
            secrets(secret=raw)
            assert validate_verify_token(TOKEN) is False, raw


class TestVerificationEndpoint:
    def test_challenge_echoed_with_right_token(self, secrets):
        secrets(secret={"webhook_verify_token": TOKEN})
        event = {"queryStringParameters": {
            "hub.mode": "subscribe", "hub.challenge": "c1", "hub.verify_token": TOKEN}}
        resp = handle_webhook_verification(event)
        assert resp["statusCode"] == 200
        assert json.loads(resp["body"]) == {"hub.challenge": "c1"}

    def test_wrong_token_403_and_not_logged(self, secrets):
        secrets(secret={"webhook_verify_token": TOKEN})
        event = {"queryStringParameters": {
            "hub.mode": "subscribe", "hub.challenge": "c1", "hub.verify_token": "leaky-value"}}
        with patch.object(webhook_handler.logger, "warning") as warn:
            resp = handle_webhook_verification(event)
        assert resp["statusCode"] == 403
        logged = " ".join(str(a) for call in warn.call_args_list for a in call.args)
        assert "leaky-value" not in logged
