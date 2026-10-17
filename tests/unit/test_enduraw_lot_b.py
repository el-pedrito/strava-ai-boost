"""Lot B: Enduraw heat cost parsing, numeric metrics, and SET/REMOVE persistence.

The persistence tests use moto because the SET-vs-REMOVE behaviour is a DynamoDB
update_item semantic (a reprocess with no report must clear a prior metric)."""
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from processing.workout_analysis import extract_enduraw_report, enduraw_numeric_metrics


def _report(lines):
    body = "\n".join(lines)
    return {
        'description': "Ma sortie\n\n📈 𝗠𝘆 𝗘𝗻𝗱𝘂𝗿𝗮𝘄 𝗥𝗲𝗽𝗼𝗿𝘁 📈\n𝗘𝗻𝗱𝘂𝗿𝗮𝘄 𝗥𝗲𝗽𝗼𝗿𝘁\n" + body + "\nTry it now"
    }


class TestHeatParsing:
    def test_heat_cost_parsed(self):
        d = extract_enduraw_report(_report([
            "Adjusted Pace: 𝟰:𝟭𝟱/km",
            'Heat (25°C) cost you 𝟬\'𝟬𝟵"/km',
        ]))
        assert d['metrics']['heat_temp'] == "25°C"
        assert d['metrics']['heat_cost'] == "0'09\"/km"

    def test_heat_absent_leaves_no_key(self):
        d = extract_enduraw_report(_report(["Adjusted Pace: 𝟰:𝟭𝟱/km"]))
        assert 'heat_cost' not in d['metrics']

    def test_real_report_heat_line_with_emoji_prefix(self):
        """Real report line: an emoji prefix and a float temperature."""
        d = extract_enduraw_report(_report([
            "Adjusted Pace: 𝟰:𝟬𝟱/km",
            '😀 Heat (18.8°C) cost you 𝟬\'𝟬𝟯"/km.',
        ]))
        assert d['metrics']['heat_temp'] == "18.8°C"
        assert d['metrics']['heat_cost'] == "0'03\"/km"
        m = enduraw_numeric_metrics(d, raw_pace_s=300)
        assert m['heat_cost_s'] == 3

    def test_real_report_heat_line_integer_temp(self):
        """Real report line: integer temperature, no emoji."""
        d = extract_enduraw_report(_report([
            "Adjusted Pace: 𝟰:𝟬𝟱/km",
            'Heat (20°C) cost you 𝟬\'𝟬𝟯"/km',
        ]))
        assert d['metrics']['heat_temp'] == "20°C"
        assert d['metrics']['heat_cost'] == "0'03\"/km"

    def test_all_three_costs_together(self):
        d = extract_enduraw_report(_report([
            "Adjusted Pace: 𝟰:𝟭𝟱/km",
            'Wind (18km/h) cost you 𝟬\'𝟬𝟲"/km',
            'Elevation (1.2% avg) cost you 𝟬\'𝟬𝟯"/km',
            'Heat (25°C) cost you 𝟬\'𝟬𝟵"/km',
        ]))
        assert d['metrics']['wind_cost'] == "0'06\"/km"
        assert d['metrics']['elevation_cost'] == "0'03\"/km"
        assert d['metrics']['heat_cost'] == "0'09\"/km"


class TestNumericMetrics:
    def test_numeric_metrics_full(self):
        d = extract_enduraw_report(_report([
            "Adjusted Pace: 𝟰:𝟭𝟱/km",
            'Wind (18km/h) cost you 𝟬\'𝟬𝟲"/km',
            'Heat (25°C) cost you 𝟬\'𝟬𝟵"/km',
        ]))
        m = enduraw_numeric_metrics(d, raw_pace_s=280)
        assert m['adjusted_pace_s'] == 255   # 4:15
        assert m['raw_pace_s'] == 280
        assert m['wind_cost_s'] == 6
        assert m['heat_cost_s'] == 9
        # No elevation LINE -> key absent (CONTRACT: null, not 0).
        assert 'elevation_cost_s' not in m

    def test_present_zero_cost_line_is_kept(self):
        d = extract_enduraw_report(_report([
            "Adjusted Pace: 𝟬:𝟭𝟵/km",
            'Heat (20°C) cost you 𝟬\'𝟬𝟬"/km',
        ]))
        m = enduraw_numeric_metrics(d, raw_pace_s=280)
        # a present line reading 0 is a real datum, kept as 0
        assert m['heat_cost_s'] == 0

    def test_none_when_no_report(self):
        assert enduraw_numeric_metrics(None) is None
        assert enduraw_numeric_metrics({'report_available': False}) is None


TABLE = "test-activities"


@pytest.fixture
def activities_table():
    with mock_aws():
        from processing import content_generator as cg
        ddb = boto3.resource("dynamodb", region_name="eu-west-1")
        ddb.create_table(
            TableName=cg.ACTIVITIES_TABLE,
            KeySchema=[{"AttributeName": "activity_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "activity_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        old = cg.dynamodb
        cg.dynamodb = ddb
        try:
            yield ddb.Table(cg.ACTIVITIES_TABLE), cg
        finally:
            cg.dynamodb = old


class TestPersistenceSetRemove:
    def _content(self):
        return {'title': 'T', 'description': 'D', 'confidence': 0.9,
                'style_elements': [], 'modules_used': [], 'patterns_detected': [],
                'analysis_type': 'x'}

    def test_set_metrics_when_present(self, activities_table):
        table, cg = activities_table
        table.put_item(Item={'activity_id': '1'})
        cg.store_generated_content('1', self._content(),
                                   {'raw_pace_s': 280, 'adjusted_pace_s': 271,
                                    'heat_cost_s': 9, 'wind_cost_s': 6, 'elevation_cost_s': 0})
        item = table.get_item(Key={'activity_id': '1'})['Item']
        assert item['enduraw_metrics']['adjusted_pace_s'] == Decimal('271')
        assert item['enduraw_metrics']['heat_cost_s'] == Decimal('9')

    def test_remove_metrics_when_absent(self, activities_table):
        table, cg = activities_table
        table.put_item(Item={'activity_id': '1',
                             'enduraw_metrics': {'adjusted_pace_s': Decimal('271')}})
        cg.store_generated_content('1', self._content(), None)
        item = table.get_item(Key={'activity_id': '1'})['Item']
        assert 'enduraw_metrics' not in item  # reprocess w/o report clears stale metric
        assert item['enhanced_title'] == 'T'
