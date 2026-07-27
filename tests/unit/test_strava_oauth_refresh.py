"""Tests for the Strava token refresh path.

This path had zero coverage while being critical: if it breaks, every activity
enhancement fails with a Strava 403 and messages land in the DLQ. The token
exchange now lives in a single place (`shared/strava_oauth.py`) and both
callers (`activity_fetcher`, `feedback_analyzer`) delegate to it.
"""

import json
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from shared.strava_oauth import STRAVA_TOKEN_URL, refresh_access_token


def _response(status_code=200, payload=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload if payload is not None else {}
    resp.text = json.dumps(payload or {})
    return resp


class TestSharedRefreshHelper:
    def test_returns_tokens_and_stamps_aware_metadata(self):
        session = MagicMock()
        session.post.return_value = _response(
            200, {'access_token': 'new-access', 'refresh_token': 'new-refresh', 'expires_at': 123}
        )

        result = refresh_access_token('old-refresh', 'cid', 'csecret', http_session=session)

        assert result['access_token'] == 'new-access'
        # Metadata must be timezone-aware ISO (activity_fetcher used to write a
        # naive datetime.utcnow(), producing a different format per caller).
        for field in ('obtained_at', 'last_refreshed'):
            parsed = datetime.fromisoformat(result[field])
            assert parsed.tzinfo is not None, f"{field} must be timezone-aware"

    def test_posts_expected_grant_to_strava(self):
        session = MagicMock()
        session.post.return_value = _response(200, {'access_token': 'a'})

        refresh_access_token('the-refresh', 'the-id', 'the-secret', http_session=session)

        url, kwargs = session.post.call_args[0][0], session.post.call_args[1]
        assert url == STRAVA_TOKEN_URL
        assert kwargs['data'] == {
            'client_id': 'the-id',
            'client_secret': 'the-secret',
            'grant_type': 'refresh_token',
            'refresh_token': 'the-refresh',
        }
        assert kwargs['timeout'] == 30

    def test_returns_none_on_non_200(self):
        session = MagicMock()
        session.post.return_value = _response(401, {'message': 'Authorization Error'})

        assert refresh_access_token('r', 'c', 's', http_session=session) is None

    def test_returns_none_when_access_token_missing(self):
        session = MagicMock()
        session.post.return_value = _response(200, {'refresh_token': 'only-refresh'})

        assert refresh_access_token('r', 'c', 's', http_session=session) is None


class TestActivityFetcherDelegates:
    """activity_fetcher resolves credentials itself, then delegates."""

    def test_delegates_to_shared_helper(self):
        from processing import activity_fetcher

        with patch.object(activity_fetcher, 'secretsmanager') as sm, \
                patch.object(activity_fetcher, 'shared_refresh_access_token') as shared, \
                patch.object(activity_fetcher, '_get_http_session') as sess:
            sm.get_secret_value.return_value = {
                'SecretString': json.dumps({'client_id': '42', 'client_secret': 'shh'})
            }
            shared.return_value = {'access_token': 'fresh'}

            result = activity_fetcher.refresh_access_token('old-refresh')

            assert result == {'access_token': 'fresh'}
            shared.assert_called_once()
            args, kwargs = shared.call_args
            assert args[0] == 'old-refresh'
            assert kwargs['http_session'] is sess.return_value

    def test_returns_none_without_credentials(self):
        from processing import activity_fetcher

        with patch.object(activity_fetcher, 'secretsmanager') as sm, \
                patch.object(activity_fetcher, 'shared_refresh_access_token') as shared:
            sm.get_secret_value.return_value = {'SecretString': json.dumps({})}

            assert activity_fetcher.refresh_access_token('r') is None
            shared.assert_not_called()


class TestFeedbackAnalyzerDelegates:
    def test_delegates_to_shared_helper(self):
        from support import feedback_analyzer

        with patch.object(feedback_analyzer, '_get_secretsmanager') as get_sm, \
                patch.object(feedback_analyzer, 'shared_refresh_access_token') as shared, \
                patch.object(feedback_analyzer, '_get_http_session') as sess:
            get_sm.return_value.get_secret_value.return_value = {
                'SecretString': json.dumps({'client_id': '42', 'client_secret': 'shh'})
            }
            shared.return_value = {'access_token': 'fresh'}

            result = feedback_analyzer.refresh_access_token('old-refresh')

            assert result == {'access_token': 'fresh'}
            args, kwargs = shared.call_args
            assert args[0] == 'old-refresh'
            assert kwargs['http_session'] is sess.return_value

    def test_returns_none_without_credentials(self):
        from support import feedback_analyzer

        with patch.object(feedback_analyzer, '_get_secretsmanager') as get_sm, \
                patch.object(feedback_analyzer, 'shared_refresh_access_token') as shared:
            get_sm.return_value.get_secret_value.return_value = {
                'SecretString': json.dumps({})
            }

            assert feedback_analyzer.refresh_access_token('r') is None
            shared.assert_not_called()


class TestOAuthStatusUsesRefreshToken:
    """An expired access token with a stored refresh token is still connected."""

    @pytest.fixture
    def config_api(self):
        from api import configuration_api
        return configuration_api

    def _status(self, config_api, tokens):
        with patch.object(config_api, 'secretsmanager') as sm:
            sm.get_secret_value.return_value = {'SecretString': json.dumps(tokens)}
            resp = config_api.get_oauth_status()
        return json.loads(resp['body'])

    def test_expired_with_refresh_token_reports_connected(self, config_api):
        body = self._status(config_api, {
            'access_token': 'a',
            'refresh_token': 'r',
            'expires_at': 1,  # long past
        })
        assert body['connected'] is True
        assert body['status'] == 'expired_refreshable'
        assert 'reconnect' not in body['message'].lower()

    def test_expired_without_refresh_token_asks_to_reconnect(self, config_api):
        body = self._status(config_api, {
            'access_token': 'a',
            'refresh_token': '',
            'expires_at': 1,
        })
        assert body['connected'] is False
        assert body['status'] == 'expired'
        assert 'reconnect' in body['message'].lower()
