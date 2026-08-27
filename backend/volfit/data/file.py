"""FileProvider — option chains served from a loaded SNAPSHOT FILE (wave 3, A2).

A ``volfit-snapshot/1`` bundle (volfit.api.snapshot_files) embeds, per
ticker, the normalized ChainSnapshot exactly as it was fetched (the
export_inputs quote table + schema-v7 metadata). Opening one registers this
provider as the data source ``file`` and switches the app to it: every fetch
then serves the embedded chains at the embedded as-of, no network. Several
files can be loaded — their tickers UNION, and for a (ticker, expiry) both
carry, the LAST loaded file wins. The provider is live-only (the embedded
stamp is the only moment it can serve) and always reports green.

Index-root discovery (volfit.data.roots): a bundle files an index under the
root its exporting universe used (``SPXW``). ``resolve_alias`` / ``search_
symbols`` map a typed parent or sibling root (``SPX``) onto that bundle
ticker, and ``roots`` reports each bundle ticker's parent root (the file's
optional per-ticker ``root``, else the registry) — so "SPX" finds the file's
SPXW node instead of nothing.
"""

from __future__ import annotations

from datetime import date, datetime

from volfit.data.provider import AsOf, OptionChainProvider, SymbolMatch
from volfit.data.roots import aliases, is_index_root, normalize_root, parent_root
from volfit.data.types import ChainSnapshot, ExpirySettlement, OptionQuote

SOURCE_ID = "file"


def chain_from_doc(ticker: str, spot: float, timestamp: str, doc: dict) -> ChainSnapshot:
    """Inverse of ``volfit.api.export_inputs.export_chain`` (+ spot / stamp)."""
    cols = list(doc.get("quoteColumns") or [])
    idx = {c: i for i, c in enumerate(cols)}

    def col(row: list, name: str):
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else None

    quotes: list[OptionQuote] = []
    for row in doc.get("quotes") or []:
        ts = col(row, "timestamp")
        quotes.append(
            OptionQuote(
                ticker=ticker,
                expiry=date.fromisoformat(str(col(row, "expiry"))),
                strike=float(col(row, "strike")),
                call_put=str(col(row, "callPut")),
                bid=_opt_float(col(row, "bid")),
                ask=_opt_float(col(row, "ask")),
                last=_opt_float(col(row, "last")),
                volume=_opt_int(col(row, "volume")),
                open_interest=_opt_int(col(row, "openInterest")),
                timestamp=datetime.fromisoformat(ts) if isinstance(ts, str) else None,
            )
        )
    settlement = None
    if doc.get("settlement"):
        settlement = {
            date.fromisoformat(iso): ExpirySettlement(
                style=str(s["style"]),
                last_trade=datetime.fromisoformat(s["lastTrade"]),
                settle=datetime.fromisoformat(s["settle"]),
            )
            for iso, s in doc["settlement"].items()
        }
    return ChainSnapshot(
        ticker=ticker,
        spot=float(spot),
        timestamp=datetime.fromisoformat(timestamp),
        quotes=quotes,
        exercise_style=str(doc.get("exerciseStyle") or "european"),
        zero_carry=bool(doc.get("zeroCarry", False)),
        tick_size=_opt_float(doc.get("tickSize")),
        settlement=settlement,
    )


def _opt_float(v) -> float | None:
    return None if v is None else float(v)


def _opt_int(v) -> int | None:
    return None if v is None else int(v)


class FileProvider(OptionChainProvider):
    """Embedded chains of one or more loaded snapshot files (see module doc)."""

    def __init__(self) -> None:
        self._chains: dict[str, ChainSnapshot] = {}
        self._names: list[str] = []
        self._as_of: datetime | None = None
        self._roots: dict[str, str] = {}  # bundle ticker -> parent index root

    # ----------------------------------------------------------- loading
    def load(
        self,
        name: str,
        chains: dict[str, ChainSnapshot],
        as_of: datetime | None,
        roots: dict[str, str] | None = None,
    ) -> None:
        """Merge a file's chains in: per ticker, quotes of expiries this file
        carries REPLACE the previously loaded ones (last-loaded wins per node);
        expiries only the older file had are kept. ``roots`` = the bundle's
        per-ticker parent root where it stamped one (else the registry's)."""
        for ticker, snap in chains.items():
            self._roots[ticker] = normalize_root((roots or {}).get(ticker) or parent_root(ticker))
            prev = self._chains.get(ticker)
            if prev is None:
                self._chains[ticker] = snap
                continue
            mine = set(snap.expiries())
            kept = [q for q in prev.quotes if q.expiry not in mine]
            settlement = dict(prev.settlement or {})
            settlement.update(snap.settlement or {})
            self._chains[ticker] = ChainSnapshot(
                ticker=ticker, spot=snap.spot, timestamp=snap.timestamp,
                quotes=kept + list(snap.quotes), exercise_style=snap.exercise_style,
                zero_carry=snap.zero_carry, tick_size=snap.tick_size,
                settlement=settlement or None,
            )
        if name not in self._names:
            self._names.append(name)
        self._as_of = as_of

    @property
    def names(self) -> list[str]:
        return list(self._names)

    @property
    def as_of(self) -> datetime | None:
        return self._as_of

    @property
    def label(self) -> str:
        """Selector label: ``File · <name>`` (several: ``File · a + b``)."""
        return "File · " + (" + ".join(self._names) if self._names else "none")

    # -------------------------------------------------------- index roots
    def roots(self) -> dict[str, str]:
        """Bundle ticker → parent index root (a non-index ticker maps to itself)."""
        return dict(self._roots)

    def _alias_set(self, ticker: str) -> set[str]:
        """Every symbol that should find ``ticker``: itself, its index family
        (volfit.data.roots) and the family of the root the file stamped."""
        names = set(aliases(ticker))
        root = self._roots.get(ticker)
        if root:
            names.update(aliases(root))
        return names

    def resolve_alias(self, symbol: str) -> str | None:
        """The bundle ticker ``symbol`` names — directly, or through the index-
        root registry (``"SPX"`` → a stored ``"SPXW"``). None when no bundle
        ticker matches; an exact bundle ticker always wins over an alias."""
        s = normalize_root(symbol)
        if not s:
            return None
        if s in self._chains:
            return s
        for ticker in self._chains:
            if s in self._alias_set(ticker):
                return ticker
        return None

    def search_symbols(self, query: str, limit: int = 10) -> list[SymbolMatch]:
        """Bundle tickers whose alias set matches the query prefix (or whose
        own symbol contains it), labelled ``SPXW · file (SPX weeklies)``. No
        free-text echo: the file cannot serve a symbol it does not carry."""
        q = normalize_root(query)
        if not q:
            return []
        out: list[SymbolMatch] = []
        for ticker in self._chains:
            hit = q in ticker or any(a.startswith(q) for a in self._alias_set(ticker))
            if not hit:
                continue
            root = self._roots.get(ticker, ticker)
            family = f" ({root} weeklies)" if root != ticker else ""
            out.append(SymbolMatch(
                symbol=ticker, name=f"{ticker} · file{family}",
                type="INDEX" if is_index_root(ticker) else "", exchange=SOURCE_ID,
            ))
        return out[:limit]

    # ---------------------------------------------------------- provider
    def list_tickers(self) -> list[str]:
        return list(self._chains)

    def available_expiries(self, ticker: str) -> list[date]:
        snap = self._chains.get(ticker)
        return snap.expiries() if snap is not None else []

    def fetch_chain(
        self, ticker: str, expiries: list[date] | None = None, as_of: AsOf | None = None
    ) -> ChainSnapshot:
        """The embedded chain (``as_of`` ignored: the file has one moment);
        ``expiries`` narrows it to the selection like every provider."""
        snap = self._chains[ticker]
        if not expiries:
            return snap
        want = set(expiries)
        return ChainSnapshot(
            ticker=snap.ticker, spot=snap.spot, timestamp=snap.timestamp,
            quotes=[q for q in snap.quotes if q.expiry in want],
            exercise_style=snap.exercise_style, zero_carry=snap.zero_carry,
            tick_size=snap.tick_size, settlement=snap.settlement,
        )

    def spot(self, ticker: str, expiries: list[date] | None = None) -> float:
        return float(self._chains[ticker].spot)

    def feed_status(self) -> tuple[str, str]:
        stamp = self._as_of.strftime("%Y-%m-%d %H:%M") if self._as_of else "no file"
        return ("green", f"snapshot file · {stamp} · fetch re-serves the embedded chains")
