"""Finite numeric coercion shared by the Coach strength aggregation.

Why this exists
---------------
Strength figures come back from DynamoDB as ``Decimal`` and, for rows written
before the typed pipeline, sometimes as strings (``"82,5"`` with a French comma).
A single coercion that accepts both, rejects booleans, and refuses any non-finite
result (``NaN``/``inf``) is the only authorised way to turn a stored value into a
Python ``float`` for the muscle, e1RM and record computations.

It is a *new* module and deliberately does NOT replace ``strength_progress._to_float``
(which the running coach reads): touching that function is out of scope for the
read-only Coach work.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


def to_finite_float(raw: Any) -> Optional[float]:
    """Return a finite ``float`` for a stored numeric value, else ``None``.

    Accepts ``int``, ``float``, ``Decimal`` and ``str`` (including a French
    decimal comma). Rejects:

    - ``bool`` (``True``/``False`` are never a load or a rep count);
    - ``None`` and anything unparseable;
    - any value whose float form is ``NaN`` or ``±inf``.

    The non-finite guard matters because DynamoDB cannot store ``NaN``/``inf``,
    so a non-finite value can only appear as the result of a Python computation
    that must not reach the JSON body.
    """
    if raw is None:
        return None
    # bool is a subclass of int; a boolean is never a measurement.
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, Decimal):
        try:
            value = float(raw)
        except (ValueError, OverflowError, InvalidOperation):
            return None
    elif isinstance(raw, str):
        text = raw.strip().replace(',', '.')
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(value):
        return None
    return value
