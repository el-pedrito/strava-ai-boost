"""Real DynamoDB semantics (moto) for the home writes that a MagicMock cannot check.

- campus#* UpdateItem must not touch the sort key, and REMOVEs owned values that vanished.
- The morning brief is stored with UpdateItem (the role grants no PutItem).
- Early Monday, the Paris-week partition is kept even before the sync flags it current.
"""
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import boto3
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')

OWNER = '123'


def _wellness_table():
    ddb = boto3.resource('dynamodb', region_name='us-east-1')
    return ddb.create_table(
        TableName='strava-ai-boost-wellness',
        KeySchema=[{'AttributeName': 'user_id', 'KeyType': 'HASH'},
                   {'AttributeName': 'sk', 'KeyType': 'RANGE'}],
        AttributeDefinitions=[{'AttributeName': 'user_id', 'AttributeType': 'S'},
                              {'AttributeName': 'sk', 'AttributeType': 'S'}],
        BillingMode='PAY_PER_REQUEST',
    )


@mock_aws
def test_campus_item_update_succeeds_on_real_table():
    from webhooks.campus_coach_sync import _put_campus_item
    table = _wellness_table()
    _put_campus_item(table, OWNER, {'sk': 'campus#goal', 'active': True, 'name': 'SEMI',
                                    'target_duration_s': 5759})
    item = table.get_item(Key={'user_id': OWNER, 'sk': 'campus#goal'})['Item']
    assert item['name'] == 'SEMI'
    assert item['target_duration_s'] == Decimal('5759')


@mock_aws
def test_campus_item_removes_vanished_owned_value():
    from webhooks.campus_coach_sync import _put_campus_item
    table = _wellness_table()
    _put_campus_item(table, OWNER, {'sk': 'campus#goal', 'active': True, 'target_duration_s': 5759,
                                    'weekly_volume_low': 26})
    _put_campus_item(table, OWNER, {'sk': 'campus#goal', 'active': True})
    item = table.get_item(Key={'user_id': OWNER, 'sk': 'campus#goal'})['Item']
    assert 'target_duration_s' not in item
    assert 'weekly_volume_low' not in item
    assert item['active'] is True


@mock_aws
def test_brief_stored_with_update_item_only():
    import webhooks.morning_brief as mb
    table = _wellness_table()
    brief = {'sk': 'brief#2026-10-17', 'date': '2026-10-17', 'light': 'green',
             'built_at': '2026-10-17T05:00:00+00:00', 'signals': [], 'missing': ['hrv']}
    original = mb.build_brief
    mb.build_brief = lambda *a, **k: dict(brief)
    spy = MagicMock(wraps=table)
    try:
        mb.build_and_store_brief(spy, OWNER, None, datetime(2026, 10, 17, tzinfo=timezone.utc))
    finally:
        mb.build_brief = original
    assert spy.put_item.call_count == 0
    item = table.get_item(Key={'user_id': OWNER, 'sk': 'brief#2026-10-17'})['Item']
    assert item['date'] == '2026-10-17'
    assert item['missing'] == ['hrv']


def test_unflagged_paris_week_kept_early_monday():
    from api.home_summary import _build_week_sessions
    sessions = MagicMock()
    sessions.query.return_value = {'Items': [
        {'session_date': 'week-2026-W43', 'session_id': 'b', 'training_index': 2,
         'title': 'Allure', 'is_current_week': False},
        {'session_date': 'week-2026-W43', 'session_id': 'a', 'training_index': 1,
         'title': 'EF', 'is_current_week': False},
    ]}
    sessions.scan.return_value = {'Items': [
        {'session_date': 'week-2026-W42', 'session_id': 'z', 'training_index': 1,
         'title': 'Old week', 'is_current_week': True},
    ]}
    # Monday 19/10/2026 00:30 Paris = Sunday 22:30 UTC.
    week, _next = _build_week_sessions(sessions, datetime(2026, 10, 18, 22, 30, tzinfo=timezone.utc))
    assert [s['title'] for s in week] == ['EF', 'Allure']
    assert sessions.scan.call_count == 0
