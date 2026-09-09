"""Friendly-name resolution for tickers spoken in a chat.

A desk says "EuroStoxx", "the SPX", "the Dax"; the app's sources each spell
these differently (Eurex: ``SX5E`` / ``OESX``; Bloomberg: ``SX5E Index``;
Cboe: ``SPX``; Yahoo: ``^SPX`` / ``^STOXX50E``). ``resolve`` maps a spoken
name to the app's canonical ticker plus the sources that actually list it, in
preference order, so ``set_universe`` can pin each ticker to a venue that
carries it (``volfit.api.state_sources`` per-ticker pins) — Yahoo has no
EuroStoxx options and Eurex has no SPX, so a mixed EU/US universe must be
split across sources.

Pure data + functions; no network. Unknown names pass through unchanged (the
app then reports "not listed" per source via ``UniverseResponse.errors``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Canonical ticker -> (spoken aliases, source preference). The canonical
#: spelling is the one the Eurex / Cboe adapters and ``portable_ticker`` accept.
_INDEX_TABLE: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "SX5E": (
        ("EUROSTOXX", "EURO STOXX", "EURO STOXX 50", "EUROSTOXX50", "EUROSTOXX 50",
         "STOXX50", "STOXX50E", "^STOXX50E", "ESTX50", "OESX", "SX5E INDEX", "ESTOXX"),
        ("bloomberg", "eurex"),
    ),
    "DAX": (
        ("DAX", "DAX40", "DAX 40", "^GDAXI", "GDAXI", "ODAX", "DAX INDEX"),
        ("bloomberg", "eurex"),
    ),
    "SXXP": (
        ("STOXX600", "STOXX 600", "EUROPE 600", "^STOXX", "OSTX", "SXXP INDEX"),
        ("bloomberg", "eurex"),
    ),
    "SPX": (
        ("SPX", "S&P", "S&P500", "S&P 500", "SP500", "^SPX", "^GSPC", "SPX INDEX", "SANDP"),
        ("bloomberg", "cboe", "massive", "yahoo"),
    ),
    "NDX": (
        ("NDX", "NASDAQ100", "NASDAQ 100", "^NDX", "NDX INDEX"),
        ("bloomberg", "cboe", "massive", "yahoo"),
    ),
    "RUT": (
        ("RUT", "RUSSELL", "RUSSELL 2000", "^RUT", "RUT INDEX"),
        ("bloomberg", "cboe", "massive", "yahoo"),
    ),
    "VIX": (("VIX", "^VIX", "VIX INDEX"), ("bloomberg", "cboe", "massive", "yahoo")),
}

#: US single names / ETFs are listed everywhere the US feeds reach.
_US_SOURCES = ("bloomberg", "cboe", "nasdaq", "massive", "yahoo")


@dataclass(frozen=True)
class Resolved:
    """One spoken name resolved: the app ticker + where to fetch it."""

    spoken: str
    ticker: str
    kind: str  # "index" | "equity"
    preferred_sources: tuple[str, ...] = field(default_factory=tuple)

    def pick_source(self, available: list[str]) -> str | None:
        """First preferred source among those registered (``None`` = default)."""
        for sid in self.preferred_sources:
            if sid in available:
                return sid
        return None


def _key(name: str) -> str:
    """Normalised lookup key: upper-case, hyphens as spaces, a leading article
    ("the S&P", "le Dax") dropped."""
    words = name.strip().upper().replace("-", " ").split()
    if len(words) > 1 and words[0] in ("THE", "LE", "LA", "DER", "DIE", "DAS"):
        words = words[1:]
    return " ".join(words)


_ALIAS_INDEX: dict[str, str] = {}
for _canon, (_aliases, _) in _INDEX_TABLE.items():
    _ALIAS_INDEX[_key(_canon)] = _canon
    for _a in _aliases:
        _ALIAS_INDEX[_key(_a)] = _canon


def resolve(name: str) -> Resolved:
    """Resolve one spoken name. Index roots get their venue preference; any
    other spelling is treated as a US-listed equity/ETF symbol (upper-cased,
    a Bloomberg " US Equity" suffix stripped)."""
    key = _key(name)
    canon = _ALIAS_INDEX.get(key) or _ALIAS_INDEX.get(key.replace(" INDEX", ""))
    if canon is not None:
        return Resolved(name, canon, "index", _INDEX_TABLE[canon][1])
    bare = key
    for suffix in (" US EQUITY", " EQUITY"):
        if bare.endswith(suffix):
            bare = bare[: -len(suffix)].strip()
    return Resolved(name, bare, "equity", _US_SOURCES)


def resolve_many(names: list[str]) -> list[Resolved]:
    """Resolve a list, de-duplicated on the canonical ticker, order kept."""
    seen: set[str] = set()
    out: list[Resolved] = []
    for n in names:
        r = resolve(n)
        if r.ticker in seen:
            continue
        seen.add(r.ticker)
        out.append(r)
    return out


def known_aliases() -> dict[str, list[str]]:
    """Canonical ticker -> spoken aliases (for the server instructions)."""
    return {canon: list(aliases) for canon, (aliases, _) in _INDEX_TABLE.items()}
