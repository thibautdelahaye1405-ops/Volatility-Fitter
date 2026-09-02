"""Provider-agnostic symbol normalization for the universe store.

The universe keeps ONE ticker string per underlying, but the data sources name
the same underlying differently:

  * US equities / ETFs — Bloomberg decorates them with a "yellow key" ("AAPL US
    Equity"); Yahoo, Massive (Polygon/OPRA) and the exchange venues take the
    bare ticker ("AAPL");
  * cash indices — "SPX Index" (Bloomberg), "^SPX" (Yahoo), "_SPX" (the Cboe
    CDN file), "I:SPX" (Massive/Polygon), bare "SPX" (OCC root, the venues).

Storing the bare form keeps a universe entry PORTABLE: it resolves on every
source, each provider re-decorating it its own way when it fetches
(``BloombergProvider._security`` re-appends the yellow key / " Index",
``YahooProvider`` the "^", ``MassiveProvider`` the "I:", the Cboe adapter the
"_"). So a ticker never has to be re-added after a source switch; only names
no other source knows (a Eurex "SX5E INDEX", "SAP GY Equity") stay as typed —
those are left untouched and simply show as "not listed" on a venue that has
no such product (volfit.data.exchange records the reason per ticker).
"""

from __future__ import annotations

from volfit.data.roots import INDEX_ROOTS, normalize_root

#: Bloomberg yellow key of US-listed equities/ETFs (the only portable case).
_US_EQUITY_SUFFIX = " US EQUITY"
#: Massive/Polygon index prefix ("I:SPX").
_INDEX_PREFIX = "I:"


def portable_ticker(symbol: str) -> str:
    """Bare ticker for a US-listed equity/ETF or a known cash-index root (any
    of its provider spellings); the symbol unchanged otherwise."""
    s = symbol.strip()
    if s.upper().endswith(_US_EQUITY_SUFFIX):
        return s[: -len(_US_EQUITY_SUFFIX)].strip()
    bare = s.upper()
    if bare.startswith(_INDEX_PREFIX):
        bare = bare[len(_INDEX_PREFIX):]
    root = normalize_root(bare)
    if root in INDEX_ROOTS:
        return root
    return s
