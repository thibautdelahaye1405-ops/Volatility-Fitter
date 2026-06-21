"""Provider-agnostic symbol normalization for the universe store.

The universe keeps one ticker string per underlying, but the data sources name
the same underlying differently: Bloomberg decorates US equities with a "yellow
key" ("AAPL US Equity"), while Yahoo and Massive (Polygon/OPRA) take the bare
ticker ("AAPL"). Storing the bare ticker keeps a universe entry portable — it
resolves on every source, and Bloomberg re-appends its yellow key when fetching.

``portable_ticker`` strips the US-equity yellow key (case-insensitively, so it
works on both the title-case search result "AAPL US Equity" and the upper-cased
stored form "AAPL US EQUITY"). Non-US names ("SAP GY Equity") and indices
("SPX Index") are left untouched: those are Bloomberg-only here, so there is no
portability to gain by stripping them.
"""

from __future__ import annotations

#: Bloomberg yellow key of US-listed equities/ETFs (the only portable case).
_US_EQUITY_SUFFIX = " US EQUITY"


def portable_ticker(symbol: str) -> str:
    """Bare ticker for a US-listed equity/ETF; the symbol unchanged otherwise."""
    s = symbol.strip()
    if s.upper().endswith(_US_EQUITY_SUFFIX):
        return s[: -len(_US_EQUITY_SUFFIX)].strip()
    return s
