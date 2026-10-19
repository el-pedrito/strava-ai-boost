"""Unit tests for shared.numeric.to_finite_float."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))


import math
from decimal import Decimal

from shared.numeric import to_finite_float  # noqa: E402


class TestToFiniteFloat:
    def test_int(self):
        assert to_finite_float(5) == 5.0

    def test_float(self):
        assert to_finite_float(82.5) == 82.5

    def test_decimal(self):
        assert to_finite_float(Decimal('82.5')) == 82.5

    def test_string_dot(self):
        assert to_finite_float('82.5') == 82.5

    def test_string_comma(self):
        assert to_finite_float('82,5') == 82.5

    def test_string_with_spaces(self):
        assert to_finite_float('  40 ') == 40.0

    def test_empty_string(self):
        assert to_finite_float('') is None

    def test_garbage_string(self):
        assert to_finite_float('abc') is None

    def test_none(self):
        assert to_finite_float(None) is None

    def test_bool_true_rejected(self):
        assert to_finite_float(True) is None

    def test_bool_false_rejected(self):
        assert to_finite_float(False) is None

    def test_float_nan_rejected(self):
        assert to_finite_float(float('nan')) is None

    def test_float_inf_rejected(self):
        assert to_finite_float(float('inf')) is None

    def test_float_neg_inf_rejected(self):
        assert to_finite_float(float('-inf')) is None

    def test_decimal_nan_rejected(self):
        assert to_finite_float(Decimal('NaN')) is None

    def test_decimal_inf_rejected(self):
        assert to_finite_float(Decimal('Infinity')) is None

    def test_string_nan_rejected(self):
        assert to_finite_float('nan') is None

    def test_string_inf_rejected(self):
        assert to_finite_float('inf') is None

    def test_unsupported_type(self):
        assert to_finite_float([1, 2]) is None

    def test_zero(self):
        assert to_finite_float(0) == 0.0

    def test_negative(self):
        assert to_finite_float(-10) == -10.0

    def test_finite_result_is_finite(self):
        value = to_finite_float('123.456')
        assert value is not None and math.isfinite(value)
