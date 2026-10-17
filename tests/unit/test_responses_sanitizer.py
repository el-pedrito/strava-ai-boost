"""Unit tests for the responses.py non-finite sanitizer and allow_nan guard."""

import os
import sys
import json
from decimal import Decimal
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared import responses  # noqa: E402
from shared.responses import create_success_response, _sanitize_non_finite  # noqa: E402


class _FixedDatetime:
    @classmethod
    def now(cls, tz=None):
        import datetime as _dt
        return _dt.datetime(2026, 1, 1, 0, 0, 0, tzinfo=_dt.UTC)


class TestSanitizeNonFinite:
    def test_nan_float_to_none(self):
        assert _sanitize_non_finite(float('nan')) is None

    def test_inf_float_to_none(self):
        assert _sanitize_non_finite(float('inf')) is None
        assert _sanitize_non_finite(float('-inf')) is None

    def test_finite_float_preserved(self):
        assert _sanitize_non_finite(82.5) == 82.5

    def test_decimal_nan_to_none(self):
        assert _sanitize_non_finite(Decimal('NaN')) is None

    def test_decimal_inf_to_none(self):
        assert _sanitize_non_finite(Decimal('Infinity')) is None

    def test_finite_decimal_preserved_as_decimal(self):
        # Finite Decimals are preserved; decimal_default turns them to float at dump.
        out = _sanitize_non_finite(Decimal('5'))
        assert out == Decimal('5')

    def test_bool_preserved(self):
        assert _sanitize_non_finite(True) is True
        assert _sanitize_non_finite(False) is False

    def test_recurses_dict_list_tuple(self):
        data = {
            'a': [1.0, float('nan'), {'b': float('inf')}],
            'c': (Decimal('NaN'), 3),
        }
        out = _sanitize_non_finite(data)
        assert out == {'a': [1.0, None, {'b': None}], 'c': (None, 3)}

    def test_input_not_mutated(self):
        nested = {'x': float('nan')}
        data = {'nested': nested, 'vals': [float('inf')]}
        _sanitize_non_finite(data)
        import math
        assert math.isnan(data['nested']['x'])
        assert math.isinf(data['vals'][0])


class TestCreateSuccessResponse:
    def test_byte_identical_for_finite_payload(self):
        """A finite payload serializes exactly as the old helper did (same
        default + ensure_ascii), only now with allow_nan=False."""
        payload = {
            'trends': {'weekly_volume_km': [1.5, 2.0], 'ratio': None},
            'name': 'Développé couché',
            'count': 3,
            'dec': Decimal('82.5'),
        }
        with patch.object(responses, 'datetime', _FixedDatetime):
            resp = create_success_response(payload)
        expected = json.dumps(
            {**payload, 'timestamp': '2026-01-01T00:00:00+00:00'},
            default=responses.decimal_default,
            ensure_ascii=False,
        )
        assert resp['body'] == expected
        # And it round-trips with a strict parser.
        parsed = json.loads(resp['body'])
        assert parsed['dec'] == 82.5
        assert parsed['name'] == 'Développé couché'

    def test_nan_sanitized_to_null(self):
        payload = {'value': float('nan'), 'ok': 1.0}
        with patch.object(responses, 'datetime', _FixedDatetime):
            resp = create_success_response(payload)
        parsed = json.loads(resp['body'])
        assert parsed['value'] is None
        assert parsed['ok'] == 1.0

    def test_nested_inf_and_decimal_sanitized(self):
        payload = {'trends': {'a': [float('inf'), Decimal('NaN'), Decimal('5')]}}
        with patch.object(responses, 'datetime', _FixedDatetime):
            resp = create_success_response(payload)
        parsed = json.loads(resp['body'])
        assert parsed['trends']['a'] == [None, None, 5.0]

    def test_strict_parse_rejects_no_nan_tokens(self):
        """The body never contains a bare NaN/Infinity token (allow_nan=False)."""
        payload = {'value': float('nan'), 'inf': float('inf')}
        with patch.object(responses, 'datetime', _FixedDatetime):
            resp = create_success_response(payload)
        assert 'NaN' not in resp['body']
        assert 'Infinity' not in resp['body']
