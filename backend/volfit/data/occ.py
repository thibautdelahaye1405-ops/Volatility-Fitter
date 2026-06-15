"""OCC / OPRA option-symbol parsing (Polygon/Massive ``O:`` tickers).

The flat-file aggregates (Tier 2 history) identify each contract only by its
option ticker — e.g. ``O:SPY260616C00500000`` — and carry no separate strike /
expiry / type columns. That symbol fully encodes them, so the chain is
reconstructed by PARSING it (no contract-reference lookup needed):

    O:  SPY      260616     C        00500000
    │   │        │          │        └ strike × 1000, 8 digits  → 500.0
    │   │        │          └ option type  C | P
    │   │        └ expiry YYMMDD (UTC)                          → 2026-06-16
    │   └ underlying root (variable length)                     → "SPY"
    └ literal prefix

The root is whatever precedes the fixed 15-char ``YYMMDD C/P + 8-digit strike``
tail, so it handles multi-character roots (``SPXW``) without a table. This module
is pure and format-independent (fully offline-testable).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: Length of the fixed tail: 6 (date) + 1 (type) + 8 (strike).
_TAIL = 15
#: Strike is quoted in thousandths of a currency unit (OCC convention).
_STRIKE_SCALE = 1000.0


@dataclass(frozen=True)
class OccOption:
    """The components of a parsed option symbol."""

    underlying: str
    expiry: date
    call_put: str  # 'C' or 'P'
    strike: float


def parse_option_symbol(symbol: str) -> OccOption:
    """Parse an ``O:`` option ticker into its components.

    Raises ``ValueError`` on anything that is not a well-formed option symbol
    (wrong prefix, short body, non-numeric date/strike, bad type letter)."""
    if not symbol or not symbol.startswith("O:"):
        raise ValueError(f"not an option symbol: {symbol!r}")
    body = symbol[2:]
    if len(body) <= _TAIL:
        raise ValueError(f"option symbol too short: {symbol!r}")
    root, tail = body[:-_TAIL], body[-_TAIL:]
    yymmdd, cp, strike_digits = tail[:6], tail[6], tail[7:]
    if not root:
        raise ValueError(f"missing underlying root: {symbol!r}")
    if cp not in ("C", "P"):
        raise ValueError(f"bad option type {cp!r} in {symbol!r}")
    if not (yymmdd.isdigit() and strike_digits.isdigit()):
        raise ValueError(f"non-numeric date/strike in {symbol!r}")
    try:
        expiry = date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))
    except ValueError as exc:
        raise ValueError(f"bad expiry in {symbol!r}: {exc}") from None
    return OccOption(
        underlying=root,
        expiry=expiry,
        call_put=cp,
        strike=int(strike_digits) / _STRIKE_SCALE,
    )


def format_option_symbol(underlying: str, expiry: date, call_put: str, strike: float) -> str:
    """Build an ``O:`` option ticker from components (inverse of the parse).

    The strike is rounded to the nearest thousandth (OCC granularity)."""
    if call_put not in ("C", "P"):
        raise ValueError(f"call_put must be 'C' or 'P', got {call_put!r}")
    strike_digits = f"{round(strike * _STRIKE_SCALE):08d}"
    return f"O:{underlying.upper()}{expiry:%y%m%d}{call_put}{strike_digits}"


def underlying_of(symbol: str) -> str | None:
    """The underlying root of an option symbol, or None if it doesn't parse —
    a cheap filter for "is this contract on one of my watchlist names?"."""
    try:
        return parse_option_symbol(symbol).underlying
    except ValueError:
        return None
