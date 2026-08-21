"""Exchange-published DELAYED option chains with real bid/ask — one adapter per venue.

Why a new source: Yahoo only yields a usable mid; the EXCHANGES themselves publish
delayed (typically 15-min) quote snapshots of their own books with the full
bid/ask, sizes, volume and open interest — free, unmetered, no entitlement. The
first venue is Cboe (volfit.data.cboe: every US-listed equity/ETF option plus the
Cboe cash indices SPX/SPXW/XSP/VIX/RUT/…); the adapter seam below is what every
further exchange plugs into (Docs/exchange_delayed_sources.md keeps the
worldwide catalog and the feasibility notes).

Contract: an ``ExchangeAdapter`` turns ONE ticker into a ``RawChain`` (spot +
every listed contract, already in OptionQuote terms) with one HTTP round-trip,
optionally a lightweight spot read and a cheap reachability probe. The generic
``ExchangeChainProvider`` does everything else the app's provider contract needs
(volfit.data.provider): caches the raw chain per ticker for a short TTL (the
venue files refresh about once a minute and weigh several MB — the universe's
``available_expiries`` + ``fetch_chain`` + status must not re-download them),
filters the selected expiries, stamps the chain with the VENUE's publication
time (the honest data age — delayed means delayed), and reports an AMBER status
("~15-min delayed") while reachable. The HTTP layer is injectable
(``fetch_json``) so the whole thing is offline-testable.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Protocol, Sequence

from volfit.data.provider import AsOf, OptionChainProvider, SymbolMatch
from volfit.data.types import ChainSnapshot, OptionQuote

#: Browser-like headers: the venue CDNs serve plain JSON but some front doors
#: refuse requests without a UA.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) volfit/1.0",
    "Accept": "application/json, text/plain, */*",
}
#: Seconds a fetched raw chain is reused before re-downloading (venue refresh ~1 min).
DEFAULT_CACHE_SECONDS = 60.0
#: Seconds a reachability verdict is reused (the UI polls status every 30 s).
_STATUS_TTL = 60.0


@dataclass(frozen=True)
class RawChain:
    """One venue's whole chain for a ticker, in the app's quote terms."""

    ticker: str
    spot: float
    timestamp: datetime  # venue publication time, UTC-naive (types.py convention)
    quotes: list[OptionQuote] = field(default_factory=list)
    exercise_style: str = "american"  # "american" | "european"
    spot_bid: float | None = None
    spot_ask: float | None = None
    security_type: str = ""  # venue's own tag ("stock" / "index" / …), informational


class ExchangeAdapter(Protocol):
    """What a venue must provide (see volfit.data.cboe for the reference one)."""

    id: str  # source id ("cboe")
    label: str  # selector label ("Cboe")
    delay_minutes: int  # the venue's stated quote delay
    tick_size: float | None  # option price tick (None = unknown)

    def fetch_chain(self, ticker: str, fetch_json: Callable[[str], dict]) -> RawChain:
        """The whole chain for ``ticker`` (raises ValueError when unlisted)."""

    def fetch_spot(self, ticker: str, fetch_json: Callable[[str], dict]) -> float:
        """A lightweight underlying read (the real-time spot poll)."""

    def probe(self, tickers: Sequence[str], fetch_json: Callable[[str], dict]) -> bool:
        """Cheap reachability check (one small request)."""


class ExchangeChainProvider(OptionChainProvider):
    """Delayed option chains from one exchange adapter (OptionChainProvider).

    Parameters
    ----------
    tickers       : the watchlist; ``list_tickers`` returns exactly this list.
    adapter       : the venue adapter.
    max_days      : drop expiries further out than this (and already-expired).
    cache_seconds : raw-chain reuse window (see module doc).
    fetch_json    : ``url -> dict`` (injected by tests); defaults to a pooled
                    httpx client with browser-like headers.
    """

    def __init__(
        self,
        tickers: Sequence[str],
        adapter: ExchangeAdapter,
        max_days: int = 730,
        cache_seconds: float = DEFAULT_CACHE_SECONDS,
        fetch_json: Callable[[str], dict] | None = None,
    ) -> None:
        self._tickers = [t.strip().upper() for t in tickers]
        self.adapter = adapter
        self.max_days = max_days
        self.cache_seconds = cache_seconds
        #: ``fetch_json(url) -> dict``; the default also exposes ``.text(url)`` for
        #: venues that speak HTML / JSONP (tests inject an object with the same shape).
        self._fetch_json = fetch_json if fetch_json is not None else _HttpFetcher(self)
        self._client = None
        self._cache: dict[str, tuple[float, RawChain]] = {}
        self._lock = threading.Lock()
        self._status: tuple[float, tuple[str, str]] | None = None
        self._last_error: str | None = None

    # ---------------------------------------------------------------- http
    def _http(self):
        import httpx

        if self._client is None:
            headers = {**_HEADERS, **getattr(self.adapter, "headers", {})}  # venue extras
            self._client = httpx.Client(timeout=30.0, headers=headers, follow_redirects=True)
        return self._client

    def _default_fetch_json(self, url: str) -> dict:
        response = self._http().get(url)
        if response.status_code in (403, 404):  # the venue CDNs refuse unknown symbols this way
            raise ValueError(f"not found: {url}")
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            raise ValueError(f"not JSON: {url}") from None

    def _default_fetch_text(self, url: str) -> str:
        """Raw body for venues that speak HTML / JSONP (HKEX) — exposed to the
        adapter as ``fetch_json.text`` (see ``__init__``)."""
        response = self._http().get(url)
        if response.status_code in (403, 404):
            raise ValueError(f"not found: {url}")
        response.raise_for_status()
        return response.text

    # --------------------------------------------------------------- chain
    def _raw(self, ticker: str, max_age: float | None = None) -> RawChain:
        """The venue chain for ``ticker``, re-downloaded when older than
        ``max_age`` (default ``cache_seconds``)."""
        key = ticker.upper()
        ttl = self.cache_seconds if max_age is None else max_age
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None and now - hit[0] <= ttl:
                return hit[1]
        try:
            raw = self.adapter.fetch_chain(key, self._fetch_json)
        except Exception as exc:
            self._last_error = str(exc).strip().splitlines()[-1][:80] if str(exc) else "fetch failed"
            raise
        self._last_error = None
        with self._lock:
            self._cache[key] = (time.monotonic(), raw)
        return raw

    def list_tickers(self) -> list[str]:
        return list(self._tickers)

    def available_expiries(self, ticker: str) -> list[date]:
        """All listed expiries inside (0, max_days] (one cached download)."""
        today = date.today()
        raw = self._raw(ticker)
        return sorted({q.expiry for q in raw.quotes if 0 < (q.expiry - today).days <= self.max_days})

    def spot(self, ticker: str, expiries: list[date] | None = None) -> float:
        """Lightweight underlying read for the real-time spot poll (never the
        multi-MB chain file); falls back to the cached chain's spot."""
        try:
            return float(self.adapter.fetch_spot(ticker.upper(), self._fetch_json))
        except Exception:  # noqa: BLE001 — venue hiccup: the cached chain spot
            return float(self._raw(ticker).spot)

    def fetch_chain(
        self,
        ticker: str,
        expiries: list[date] | None = None,
        as_of: AsOf | None = None,
    ) -> ChainSnapshot:
        """The delayed chain for the selected expiries (the universe's selection)
        or the whole listed ladder within ``max_days``. Live-only (``as_of`` is
        ignored); stamped with the venue's publication time."""
        raw = self._raw(ticker)
        today = date.today()
        if expiries is None:
            wanted = {q.expiry for q in raw.quotes if 0 < (q.expiry - today).days <= self.max_days}
        else:
            wanted = set(expiries)
        quotes = [q for q in raw.quotes if q.expiry in wanted]
        if not quotes:
            raise ValueError(f"{self.adapter.label} lists no options for {ticker!r} in the requested expiries")
        from volfit.data.expiry_time import settlement_map

        return ChainSnapshot(
            ticker=ticker.upper(),
            spot=float(raw.spot),
            timestamp=raw.timestamp,
            quotes=quotes,
            exercise_style=raw.exercise_style,
            tick_size=self.adapter.tick_size,
            settlement=settlement_map({q.expiry for q in quotes}, root=ticker.upper()),
        )

    # -------------------------------------------------------------- status
    def feed_status(self) -> tuple[str, str]:
        """Amber while the venue answers (delayed by construction), red when it
        does not — one small request, cached for a minute (the UI polls every
        30 s). A recent fetch failure is surfaced as its reason."""
        tickers = self.list_tickers()
        if not tickers:
            return ("red", "no tickers configured")
        now = time.monotonic()
        if self._status is not None and now - self._status[0] <= _STATUS_TTL:
            return self._status[1]
        try:
            ok = self.adapter.probe(tickers, self._fetch_json)
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            verdict = ("red", f"{self.adapter.label} unreachable")
        elif self._last_error:
            verdict = ("red", f"{self.adapter.label}: {self._last_error}")
        else:  # an adapter may word its own amber text (Eurex: which tier it served)
            text = getattr(self.adapter, "status_text", None)
            verdict = ("amber", text() if callable(text) else f"{self.adapter.label} ~{self.adapter.delay_minutes}-min delayed")
        self._status = (now, verdict)
        return verdict

    def historical_modes(self) -> set[str]:
        return {"live"}

    def search_symbols(self, query: str, limit: int = 10) -> list[SymbolMatch]:
        """Venue search when the adapter has one, else the base substring/echo."""
        search = getattr(self.adapter, "search_symbols", None)
        if search is not None:
            try:
                hits = search(query, self._fetch_json, limit)
                if hits:
                    return hits[:limit]
            except Exception:  # noqa: BLE001 — degrade to the base search
                pass
        return super().search_symbols(query, limit)

    def invalidate(self, ticker: str | None = None) -> None:
        """Drop the cached chain(s) (tests / an explicit refresh)."""
        with self._lock:
            if ticker is None:
                self._cache.clear()
            else:
                self._cache.pop(ticker.upper(), None)


class _HttpFetcher:
    """The provider's default fetcher: ``fetcher(url) -> dict`` (JSON) plus
    ``fetcher.text(url) -> str`` for HTML / JSONP venues."""

    def __init__(self, provider: "ExchangeChainProvider") -> None:
        self._provider = provider

    def __call__(self, url: str) -> dict:
        return self._provider._default_fetch_json(url)

    def text(self, url: str) -> str:
        return self._provider._default_fetch_text(url)


def utc_naive(dt: datetime) -> datetime:
    """A tz-aware datetime -> UTC-naive (the wire convention)."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)
