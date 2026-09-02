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

from volfit.data import progress
from volfit.data.expiry_time import default_settlement, session_close_utc
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
#: Wall-clock cap on ONE venue download (seconds) — see ``_default_fetch_json``.
DOWNLOAD_BUDGET_SECONDS = 120.0
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
    #: expiry -> the OCC root that lists it, for the settlement convention: a
    #: cash-index file mixes the AM-settled parent (SPX, 3rd Fridays) with its
    #: PM-settled weekly sibling (SPXW) — one root per DATE, the parent winning
    #: when both list it. Empty = every expiry settles per the ticker's root.
    roots: dict = field(default_factory=dict)
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
    today         : ``() -> date`` used by the expiry filter (injected by tests
                    so canned chains stay deterministic; production keeps the
                    wall clock).
    """

    def __init__(
        self,
        tickers: Sequence[str],
        adapter: ExchangeAdapter,
        max_days: int = 730,
        cache_seconds: float = DEFAULT_CACHE_SECONDS,
        fetch_json: Callable[[str], dict] | None = None,
        today: Callable[[], date] | None = None,
    ) -> None:
        self._tickers = [t.strip().upper() for t in tickers]
        self._today = today if today is not None else date.today
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
        #: Per-TICKER outcomes of the last fetch: a transport/parse error (the
        #: source is in trouble) vs "the venue lists no options for this symbol"
        #: (a fact about the ticker — never a source outage). One bad symbol in
        #: the universe (a Eurex name on Cboe) used to red-light the whole feed.
        self._errors: dict[str, str] = {}
        self._unlisted: dict[str, str] = {}

    # ---------------------------------------------------------------- http
    def _http(self):
        import httpx

        if self._client is None:
            headers = {**_HEADERS, **getattr(self.adapter, "headers", {})}  # venue extras
            self._client = httpx.Client(timeout=30.0, headers=headers, follow_redirects=True)
        return self._client

    def _default_fetch_json(self, url: str) -> dict:
        """Download a venue JSON document, STREAMED: bytes vs Content-Length go
        to volfit.data.progress (the status bar's gauge — a 13 MB Cboe index
        chain is a visible download, not a frozen bar) and a wall-clock budget
        (``DOWNLOAD_BUDGET_SECONDS``) caps a trickling transfer — httpx's
        ``timeout`` is per socket operation, so without it a slow CDN could
        hold a fetch (and the UI) for minutes."""
        import json
        import time as _time

        with self._http().stream("GET", url) as response:
            if response.status_code in (403, 404):  # the venue CDNs refuse unknown symbols this way
                raise ValueError(f"not found: {url}")
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            deadline = _time.monotonic() + DOWNLOAD_BUDGET_SECONDS
            chunks: list[bytes] = []
            for chunk in response.iter_bytes():
                chunks.append(chunk)
                # Raw (compressed) bytes, like Content-Length; a mocked transport
                # counts none, so fall back to the decoded bytes.
                got = response.num_bytes_downloaded or sum(len(c) for c in chunks)
                progress.report(got, total, progress.bytes_label(got, total))
                if _time.monotonic() > deadline:
                    raise TimeoutError(
                        f"{self.adapter.label} download exceeded {DOWNLOAD_BUDGET_SECONDS:.0f}s: {url}"
                    )
        try:
            return json.loads(b"".join(chunks))
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
            text = str(exc).strip()
            short = text.splitlines()[-1][:80] if text else "fetch failed"
            if "not found" in text or "lists no" in text:  # the venue has no listing for this symbol
                self._unlisted[key] = short  # the adapter's own wording ("Cboe lists no options for …")
                self._errors.pop(key, None)
            else:
                self._errors[key] = short
            raise
        self._errors.pop(key, None)
        self._unlisted.pop(key, None)
        with self._lock:
            self._cache[key] = (time.monotonic(), raw)
        return raw

    def ticker_error(self, ticker: str) -> str | None:
        """Why the last fetch of ``ticker`` yielded nothing (an unlisted symbol
        or a transport error), for the universe payload; None when fine."""
        key = ticker.upper()
        return self._unlisted.get(key) or self._errors.get(key)

    def _keep_expiry(self, expiry: date, today: date) -> bool:
        """Listed-ladder rule: inside ``max_days``, and TODAY's expiry only while
        its session is still open (a 0DTE is a live node until the close, dead
        after it)."""
        days = (expiry - today).days
        if days > self.max_days:
            return False
        if days > 0:
            return True
        return days == 0 and self._now() < session_close_utc(today)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def list_tickers(self) -> list[str]:
        return list(self._tickers)

    def available_expiries(self, ticker: str) -> list[date]:
        """All listed expiries inside (0, max_days] (one cached download)."""
        today = self._today()
        raw = self._raw(ticker)
        return sorted({q.expiry for q in raw.quotes if self._keep_expiry(q.expiry, today)})

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
        today = self._today()
        if expiries is None:
            wanted = {q.expiry for q in raw.quotes if self._keep_expiry(q.expiry, today)}
        else:
            wanted = set(expiries)
        quotes = [q for q in raw.quotes if q.expiry in wanted]
        if not quotes:
            raise ValueError(f"{self.adapter.label} lists no options for {ticker!r} in the requested expiries")
        return ChainSnapshot(
            ticker=ticker.upper(),
            spot=float(raw.spot),
            timestamp=raw.timestamp,
            quotes=quotes,
            exercise_style=raw.exercise_style,
            tick_size=self.adapter.tick_size,
            settlement={  # per expiry: the listing root's convention (SPX AM vs SPXW PM)
                e: default_settlement(e, raw.roots.get(e, ticker.upper()))
                for e in sorted({q.expiry for q in quotes})
            },
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
        elif self._errors:  # a real transport / parse failure on some ticker
            worst = next(iter(self._errors.values()))
            verdict = ("red", f"{self.adapter.label}: {worst}")
        else:  # an adapter may word its own amber text (Eurex: which tier it served)
            text = getattr(self.adapter, "status_text", None)
            detail = text() if callable(text) else f"{self.adapter.label} ~{self.adapter.delay_minutes}-min delayed"
            if self._unlisted:  # a fact about those symbols, not about the feed
                detail = f"{detail} · not listed: {', '.join(sorted(self._unlisted))}"
            verdict = ("amber", detail)
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
