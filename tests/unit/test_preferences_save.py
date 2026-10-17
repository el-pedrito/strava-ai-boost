"""Preferences save and Campus zones read (docs/design/campus-paces.md section D, API).

The POST must not replace the whole ``user_preferences`` map: that wiped
``strength_history``, ``pace_zones`` and ``personal_records``. These tests run on moto
so the child-path SET/REMOVE and the ConditionExpression semantics are DynamoDB's,
not a MagicMock's.
"""

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import patch

import boto3
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from api import user_preferences_api as api  # noqa: E402
from shared.iso_week import iso_week_label  # noqa: E402

USER = 'athlete1'
REGION = 'eu-west-1'
ZONES_A = {'ef': {'min': '5:40', 'max': '6:10'}, 'tempo': {'min': '4:40', 'max': '4:50'}}
ZONES_B = {'ef': {'min': '3:00', 'max': '3:10'}}
HISTORY = {'entries': [{'date': '2026-10-01', 'volume_kg': Decimal('4200')}]}
RECORDS = [{'distance': '10K', 'time': '42:00', 'date': '2026-03-01', 'event': 'x'}]


def _post(payload: Dict[str, Any]) -> Dict[str, Any]:
    body = {'user_id': USER, **payload}
    return api.update_user_preferences({'httpMethod': 'POST', 'path': '/preferences', 'body': json.dumps(body)})


def _get() -> Dict[str, Any]:
    response = api.get_user_preferences(
        {'httpMethod': 'GET', 'path': '/preferences', 'queryStringParameters': {'user_id': USER}})
    assert response['statusCode'] == 200
    return json.loads(response['body'])['preferences']


class _Env:
    """A moto user-config table patched into the API module."""

    def __init__(self, item=None):
        self.item = item

    def __enter__(self):
        self._mock = mock_aws()
        self._mock.start()
        self.ddb = boto3.resource('dynamodb', region_name=REGION)
        self.table = self.ddb.create_table(
            TableName=api.USER_CONFIG_TABLE, BillingMode='PAY_PER_REQUEST',
            KeySchema=[{'AttributeName': 'user_id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'user_id', 'AttributeType': 'S'}])
        if self.item is not None:
            self.table.put_item(Item=self.item)
        self._patch = patch.object(api, 'dynamodb', self.ddb)
        self._patch.start()
        return self

    def stored(self) -> Dict[str, Any]:
        return self.table.get_item(Key={'user_id': USER}).get('Item', {})

    def __exit__(self, *exc):
        self._patch.stop()
        self._mock.stop()


def _full_item() -> Dict[str, Any]:
    return {
        'user_id': USER,
        'modules_config': {'campus_coach': {'enabled': True}},
        'campus_pace_zones': {'ef': {'min': '5:36', 'max': '6:02', 'slug': 'ef'}},
        'campus_pace_zones_week': '2026-W42',
        'user_preferences': {
            'content_tone': 'casual & friendly',
            'pace_zones': ZONES_A,
            'strength_history': HISTORY,
            'personal_records': RECORDS,
            'max_hr': 190,
            'height_cm': Decimal('180'),
            'written_by_someone_else': 'keep me',
        },
    }


class TestPreferencesSavePreservesUnownedKeys:
    """Map present: child-path update, nothing outside the API keys is touched."""

    def test_hostile_pace_zones_ignored_history_and_zones_kept(self) -> None:
        with _Env(_full_item()) as env:
            response = _post({'content_tone': 'humorous & fun', 'pace_zones': ZONES_B})
            assert response['statusCode'] == 200
            prefs = env.stored()['user_preferences']
            assert prefs['pace_zones'] == ZONES_A
            assert prefs['strength_history'] == HISTORY
            assert prefs['written_by_someone_else'] == 'keep me'
            assert prefs['content_tone'] == 'humorous & fun'

    def test_absent_optional_keys_are_removed(self) -> None:
        with _Env(_full_item()) as env:
            _post({})
            prefs = env.stored()['user_preferences']
            assert 'max_hr' not in prefs
            assert 'height_cm' not in prefs

    def test_absent_personal_records_are_kept(self) -> None:
        with _Env(_full_item()) as env:
            _post({})
            assert env.stored()['user_preferences']['personal_records'] == RECORDS

    def test_sent_personal_records_replace_the_list(self) -> None:
        with _Env(_full_item()) as env:
            _post({'personal_records': [{'distance': '5K', 'time': '19:30'}]})
            records = env.stored()['user_preferences']['personal_records']
            assert [r['distance'] for r in records] == ['5K']

    def test_sent_max_hr_is_set(self) -> None:
        with _Env(_full_item()) as env:
            _post({'max_hr': 185})
            assert env.stored()['user_preferences']['max_hr'] == 185
    def test_athlete_profile_keeps_todays_behaviour(self) -> None:
        """Omitted -> stored as '' (SET, never REMOVE), sent -> stored as sent (review cr1)."""
        item = _full_item()
        item['user_preferences']['athlete_profile'] = 'marathon 2027'
        with _Env(item) as env:
            _post({})
            assert env.stored()['user_preferences']['athlete_profile'] == ''
            _post({'athlete_profile': 'semi sub 1h30'})
            assert env.stored()['user_preferences']['athlete_profile'] == 'semi sub 1h30'
        assert 'athlete_profile' not in api.OPTIONAL_REMOVABLE_KEYS


    def test_top_level_campus_attributes_untouched(self) -> None:
        with _Env(_full_item()) as env:
            _post({})
            item = env.stored()
            assert item['campus_pace_zones_week'] == '2026-W42'
            assert item['campus_pace_zones']['ef']['min'] == '5:36'
            assert item['modules_config'] == {'campus_coach': {'enabled': True}}
            assert 'updated_at' in item


class TestPreferencesSaveCreatesMissingMap:
    """Map or item absent: conditional create, then one child-path retry if raced."""

    def test_item_without_map_gets_full_map(self) -> None:
        with _Env({'user_id': USER, 'best_efforts_prs': {'5k': 'x'}}) as env:
            response = _post({'max_hr': 180})
            assert response['statusCode'] == 200
            item = env.stored()
            assert item['best_efforts_prs'] == {'5k': 'x'}
            assert item['user_preferences']['max_hr'] == 180
            assert item['user_preferences']['content_language'] == 'french'
            assert 'pace_zones' not in item['user_preferences']

    def test_absent_item_is_created(self) -> None:
        with _Env(None) as env:
            response = _post({'content_tone': 'humorous & fun', 'pace_zones': ZONES_B})
            assert response['statusCode'] == 200
            prefs = env.stored()['user_preferences']
            assert prefs['content_tone'] == 'humorous & fun'
            assert 'pace_zones' not in prefs

    def test_concurrent_creation_falls_back_to_child_path(self) -> None:
        with _Env({'user_id': USER}) as env:
            real_update = env.table.update_item
            calls = []

            def racing_update(**kwargs):
                calls.append(kwargs['ConditionExpression'])
                if kwargs['ConditionExpression'] == 'attribute_not_exists(#prefs)':
                    # Another writer creates the map just before our create lands.
                    env.table.put_item(Item={'user_id': USER, 'user_preferences': {'strength_history': HISTORY}})
                return real_update(**kwargs)

            table_proxy = type('T', (), {'update_item': staticmethod(racing_update)})()
            with patch.object(api.dynamodb, 'Table', return_value=table_proxy):
                response = _post({'max_hr': 182})
            assert response['statusCode'] == 200
            assert calls == ['attribute_exists(#prefs)', 'attribute_not_exists(#prefs)', 'attribute_exists(#prefs)']
            prefs = env.stored()['user_preferences']
            assert prefs['strength_history'] == HISTORY
            assert prefs['max_hr'] == 182


class TestPreferencesGetCampusZones:
    """GET exposes the Campus zones, their week, sync date and the effective source."""

    def test_campus_zones_current_week(self) -> None:
        item = _full_item()
        item['campus_pace_zones_week'] = iso_week_label(datetime.now(timezone.utc).isoformat())
        item['campus_pace_zones_synced_at'] = '2026-10-17T06:00:00+00:00'
        with _Env(item):
            prefs = _get()
            assert prefs['pace_zones_source'] == 'campus'
            assert prefs['campus_pace_zones']['ef']['max'] == '6:02'
            assert prefs['campus_pace_zones_week'] == item['campus_pace_zones_week']
            assert prefs['campus_pace_zones_synced_at'] == '2026-10-17T06:00:00+00:00'

    def test_old_week_is_stale(self) -> None:
        item = _full_item()
        item['campus_pace_zones_week'] = '2020-W01'
        with _Env(item):
            assert _get()['pace_zones_source'] == 'campus_stale'

    def test_legacy_manual_zones(self) -> None:
        item = _full_item()
        del item['campus_pace_zones']
        del item['campus_pace_zones_week']
        with _Env(item):
            prefs = _get()
            assert prefs['pace_zones_source'] == 'manual_legacy'
            assert prefs['campus_pace_zones'] is None
            assert prefs['pace_zones'] == ZONES_A

    def test_no_item_has_no_source(self) -> None:
        with _Env(None):
            prefs = _get()
            assert prefs['pace_zones_source'] == 'none'
            assert prefs['campus_pace_zones'] is None
            assert prefs['campus_pace_zones_week'] is None
            assert prefs['campus_pace_zones_synced_at'] is None
