"""Shared market-field coercion helpers for the live providers.

Every provider (Yahoo, Bloomberg, Massive) faces the same two chores when
mapping a vendor field onto volfit.data.types conventions:

- prices: a value of ``0.0`` (or ``NaN``, or a non-numeric blank) means "no
  quote", which types.py represents as ``None`` — never ``0.0`` (a valid
  price); and
- counts (volume, open interest): ``NaN``/blank means "unknown" -> ``None``.

Vendors also disagree on the *type* they hand back: Yahoo gives floats,
Bloomberg's narwhals long-format frames give numeric *strings* ('496.17',
'1.0', '26'). Both helpers therefore accept anything and coerce via ``float``.
"""

from __future__ import annotations

import math


def price_or_none(value) -> float | None:
    """Coerce a vendor price to float; ``<= 0``, ``NaN`` or blank -> ``None``."""
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or x <= 0.0:
        return None
    return x


def int_or_none(value) -> int | None:
    """Coerce a vendor count (volume, OI) to int; ``NaN``/inf/blank -> ``None``.

    Bloomberg reports counts as float-like strings ('26', '1.0'), so the parse
    goes through ``float`` before truncating to ``int``.
    """
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return int(x)
