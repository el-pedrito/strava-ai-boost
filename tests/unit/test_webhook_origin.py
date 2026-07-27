"""Tests for webhook origin validation.

Strava does NOT sign webhook events (https://developers.strava.com/docs/webhooks/),
so the only usable signal is that the event body carries our own subscription id
and a known athlete. These tests pin the two properties that matter:

1. No regression: a legitimate Strava event is always processed.
2. The forged event that reached production on 2026-07-27 is dropped.

Validated against 339 real events (2026-03-26 -> 2026-07-27): 338/338 legitimate
events carried subscription_id=337159 and owner_id=138362426; the single
mismatch was the forged test.
"""

import importlib
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

REAL_SUBSCRIPTION = '337159'
REAL_ATHLETE = '138362426'


def _load(strict='true', subscription=REAL_SUBSCRIPTION, default_user=REAL_ATHLETE):
    """Reload the handler with a given environment (module-level config)."""
    os.environ['WEBHOOK_STRICT_ORIGIN'] = strict
    os.environ['STRAVA_SUBSCRIPTION_ID'] = subscription
    os.environ['DEFAULT_USER_ID'] = default_user
    from webhooks import webhook_handler
    return importlib.reload(webhook_handler)


def _event(subscription_id=REAL_SUBSCRIPTION, owner_id=REAL_ATHLETE, object_id=19469298323):
    return {
        'object_type': 'activity',
        'object_id': object_id,
        'aspect_type': 'create',
        'owner_id': int(owner_id),
        'subscription_id': int(subscription_id),
        'event_time': 1785166542,
    }


@pytest.fixture(autouse=True)
def _restore_env():
    saved = {k: os.environ.get(k) for k in
             ('WEBHOOK_STRICT_ORIGIN', 'STRAVA_SUBSCRIPTION_ID', 'DEFAULT_USER_ID')}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class TestNoRegressionOnLegitimateEvents:
    """The webhook is a hard dependency: legitimate events must always pass."""

    def test_real_strava_event_is_accepted(self):
        wh = _load()
        with patch.object(wh, 'is_known_athlete', return_value=True):
            assert wh.validate_webhook_origin(_event()) is True

    def test_accepted_when_subscription_id_not_configured(self):
        """Missing config must never block ingestion (fails open)."""
        wh = _load(subscription='')
        with patch.object(wh, 'is_known_athlete', return_value=True):
            assert wh.validate_webhook_origin(_event(subscription_id='999')) is True

    def test_accepted_when_athlete_lookup_fails(self):
        """A DynamoDB outage must not stop Strava ingestion."""
        wh = _load()
        with patch.object(wh, 'get_dynamodb_resource', side_effect=RuntimeError('ddb down')):
            assert wh.is_known_athlete(REAL_ATHLETE) is True

    def test_deauthorisation_event_from_known_athlete_accepted(self):
        wh = _load()
        evt = _event()
        evt.update({'object_type': 'athlete', 'aspect_type': 'update',
                    'updates': {'authorized': 'false'}})
        with patch.object(wh, 'is_known_athlete', return_value=True):
            assert wh.validate_webhook_origin(evt) is True


class TestForgedEventsAreDropped:
    def test_forged_subscription_id_is_dropped(self):
        """This is the exact event that reached production on 2026-07-27."""
        wh = _load()
        forged = _event(subscription_id='1', object_id=999999999)
        with patch.object(wh, 'is_known_athlete', return_value=True):
            assert wh.validate_webhook_origin(forged) is False

    def test_unknown_athlete_is_dropped(self):
        wh = _load()
        with patch.object(wh, 'is_known_athlete', return_value=False):
            assert wh.validate_webhook_origin(_event(owner_id='424242')) is False

    def test_kill_switch_restores_previous_behaviour(self):
        """Operators must be able to disable rejection without a code deploy."""
        wh = _load(strict='false')
        forged = _event(subscription_id='1')
        with patch.object(wh, 'is_known_athlete', return_value=True):
            assert wh.validate_webhook_origin(forged) is True


class TestHandlerAlwaysAcknowledges:
    """Strava retries non-200 three times then disables the subscription."""

    def test_dropped_event_still_returns_200_and_queues_nothing(self):
        wh = _load()
        sqs = MagicMock()
        with patch.object(wh, 'validate_webhook_origin', return_value=False), \
                patch.object(wh, 'get_sqs_client', return_value=sqs):
            resp = wh.handle_webhook_notification({
                'body': json.dumps(_event(subscription_id='1')),
                'headers': {},
            })
        assert resp['statusCode'] == 200
        assert json.loads(resp['body'])['status'] == 'ignored'
        sqs.send_message.assert_not_called()


class TestSignatureCheckStaysFailOpen:
    """Strava sends no signature; requiring one would break every event."""

    def test_missing_signature_header_is_allowed(self):
        wh = _load()
        assert wh.verify_webhook_signature('{}', {}) is True
