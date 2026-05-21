"""Unit tests for campus_coach_sync Lambda"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

os.environ.setdefault("COACHING_SESSIONS_TABLE", "test-coaching-sessions")
os.environ.setdefault("USER_CONFIG_TABLE", "test-user-config")
os.environ.setdefault("SECRET_ARN", "test-secret-arn")
os.environ.setdefault("AWS_REGION", "eu-west-1")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from webhooks.campus_coach_sync import (
    handler,
    _is_module_enabled,
    _login,
    _fetch_plan,
    _build_intervals,
    _format_pace,
    _find_pace,
    _monday_of_iso_week,
    _to_iso_week,
    _delete_stale_sessions,
)


class TestIsModuleEnabled:

    @patch('webhooks.campus_coach_sync.dynamodb')
    def test_is_module_enabled_true(self, mock_dynamodb):
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            'Item': {'modules_config': {'campus_coach': {'enabled': True}}}
        }
        assert _is_module_enabled('user1') is True

    @patch('webhooks.campus_coach_sync.dynamodb')
    def test_is_module_enabled_false(self, mock_dynamodb):
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            'Item': {'modules_config': {'campus_coach': {'enabled': False}}}
        }
        assert _is_module_enabled('user1') is False


class TestHandler:

    @patch('webhooks.campus_coach_sync._is_module_enabled', return_value=False)
    def test_handler_module_not_enabled(self, mock_enabled):
        result = handler({'user_id': 'user1'}, None)
        assert result == {'statusCode': 200, 'message': 'Module not enabled'}

    @patch('webhooks.campus_coach_sync._delete_stale_sessions', return_value=0)
    @patch('webhooks.campus_coach_sync.dynamodb')
    @patch('webhooks.campus_coach_sync._fetch_plan')
    @patch('webhooks.campus_coach_sync._login', return_value='fake-token')
    @patch('webhooks.campus_coach_sync._get_credentials', return_value={'username': 'u', 'password': 'p'})
    @patch('webhooks.campus_coach_sync._is_module_enabled', return_value=True)
    def test_handler_module_enabled_success(self, mock_enabled, mock_creds, mock_login, mock_fetch, mock_ddb, mock_delete):
        mock_table = MagicMock()
        mock_ddb.Table.return_value = mock_table

        now = datetime.now(timezone.utc)
        monday_ms = int(_monday_of_iso_week(now).timestamp() * 1000)
        mock_fetch.return_value = [{
            'access': 'allowed',
            'weekDate': monday_ms,
            'context': {},
            'estimatedPaces': [],
            'sessions': [{'displayName': 'Easy Run', 'sport': 'running', 'stats': {}}],
        }]

        result = handler({'user_id': 'user1'}, None)

        assert result['statusCode'] == 200
        assert result['sessions_stored'] == 1
        mock_table.put_item.assert_called_once()


class TestLogin:

    @patch('webhooks.campus_coach_sync.requests.post')
    def test_login_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.json.return_value = {'token': 'jwt123'}
        assert _login('user@test.com', 'pass') == 'jwt123'

    @patch('webhooks.campus_coach_sync.requests.post')
    def test_login_failure(self, mock_post):
        mock_post.return_value = MagicMock()
        mock_post.return_value.raise_for_status.side_effect = Exception("401 Unauthorized")
        with pytest.raises(Exception, match="401"):
            _login('user@test.com', 'wrong')


class TestFetchPlan:

    @patch('webhooks.campus_coach_sync.requests.get')
    def test_fetch_plan_success(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = [{'weekDate': 123, 'sessions': []}]
        result = _fetch_plan('token', 1000, 2000)
        assert result == [{'weekDate': 123, 'sessions': []}]
        mock_get.assert_called_once()


class TestBuildIntervals:

    def test_build_intervals_running_session(self):
        session = {
            'exercisesBlocks': [{
                'blockType': 'work',
                'repeat': 3,
                'exercises': [{
                    'exerciseType': 'work',
                    'durations': [{'value': 5, 'timeUnit': 'minutes'}],
                    'pace': {'name': '10km', 'value': 300},
                }],
            }]
        }
        result = _build_intervals(session, [])
        assert len(result) == 1
        assert result[0]['type'] == 'work'
        assert result[0]['duration'] == '5 min'
        assert result[0]['repeat'] == 3
        assert '5:00/km' in result[0]['pace']

    def test_build_intervals_empty(self):
        assert _build_intervals({}, []) == []
        assert _build_intervals({'exercisesBlocks': []}, []) == []


class TestFormatPace:

    def test_format_pace(self):
        assert _format_pace(300) == '5:00/km'
        assert _format_pace(270) == '4:30/km'
        assert _format_pace(None) is None
        assert _format_pace(0) is None


class TestFindPace:

    def test_find_pace(self):
        paces = [{'slug': '10km', 'value': 300}, {'slug': 'ef', 'value': 330}]
        assert _find_pace(paces, '10km') == 300
        assert _find_pace(paces, 'ef') == 330
        assert _find_pace(paces, 'missing') is None
        assert _find_pace([], 'x') is None
        assert _find_pace(None, 'x') is None


class TestDateUtils:

    def test_monday_of_iso_week(self):
        # Wednesday 2026-05-20 -> Monday 2026-05-18
        dt = datetime(2026, 5, 20, 12, 30, 0, tzinfo=timezone.utc)
        monday = _monday_of_iso_week(dt)
        assert monday.weekday() == 0
        assert monday.day == 18
        assert monday.hour == 0

    def test_to_iso_week(self):
        # 2026-05-18 is Monday of W21
        dt = datetime(2026, 5, 18, tzinfo=timezone.utc)
        ms = int(dt.timestamp() * 1000)
        assert _to_iso_week(ms) == '2026-W21'


class TestDeleteStaleSessions:

    def test_delete_stale_sessions(self):
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            'Items': [
                {'session_date': 'week-2026-W20', 'session_id': '123_0'},
                {'session_date': 'week-2026-W21', 'session_id': '456_0'},
            ]
        }
        mock_batch = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch)
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        current_ids = {'week-2026-W21#456_0'}
        deleted = _delete_stale_sessions(mock_table, current_ids)

        assert deleted == 1
        mock_batch.delete_item.assert_called_once_with(
            Key={'session_date': 'week-2026-W20', 'session_id': '123_0'}
        )
