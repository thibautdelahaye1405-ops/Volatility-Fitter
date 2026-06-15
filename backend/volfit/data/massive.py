"""Massive (formerly Polygon.io) option-chain provider (ROADMAP Phase 3).

Design intent: `MassiveProvider` implements the `OptionChainProvider` contract
(volfit.data.provider) on top of the Massive REST API, so the rest of the stack
runs unchanged on Massive data. Massive rebranded from Polygon.io on
2025-10-30; the base host is ``api.massive.com`` and the paths are the familiar
``/v3/...`` Polygon routes, authenticated with a Bearer token.

Endpoints used:
- ``GET /v3/reference/options/contracts`` — enumerate listed contracts (cheap,
  paginated) for ``available_expiries``;
- ``GET /v3/snapshot/options/{underlying}`` — the option-chain snapshot
  (``last_quote`` bid/ask, ``day`` OHLCV, ``open_interest``, ``greeks``,
  ``implied_volatility``, ``details`` strike/expiry/type/exercise-style,
  ``underlying_asset.price``), paginated for ``fetch_chain`` and ``iv_surface``;
- ``GET /v3/reference/tickers`` — symbol search;
- ``GET /v2/snapshot/.../stocks/tickers/{T}`` — underlying spot fallback.

Entitlement note: NBBO quotes (``last_quote``) and the stock snapshot require a
paid options tier. On a plan without them the snapshot still returns greeks/IV
(see ``iv_surface``) but ``last_quote``/spot are absent and the dedicated quote
and stock endpoints answer ``NOT_AUTHORIZED`` — which ``fetch_chain`` surfaces
as a clear, actionable ``RuntimeError`` (the provider is otherwise built to the
full bid/ask + spot spec and lights up automatically once the plan is upgraded).

Robustness / conventions:
- ``httpx`` is imported lazily; tests inject ``http_get`` and stay offline.
- Missing/zero price fields map to ``None`` (volfit.data.types convention).
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Iterator, Sequence

from volfit.core.black import black_call
from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.provider import AsOf, OptionChainProvider, SymbolMatch
from volfit.data.types import ChainSnapshot, OptionQuote

#: Default REST host (api.polygon.io still works for legacy keys).
DEFAULT_BASE_URL = "https://api.massive.com"

#: Snapshot page size cap (Massive limits to 250).
_SNAPSHOT_LIMIT = 250


def _iso_date(value) -> date | None:
    """Parse an ISO 'YYYY-MM-DD' (possibly with a time suffix) to date."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class MassiveProvider(OptionChainProvider):
    """Live option chains for a watchlist via the Massive REST API.

    Parameters
    ----------
    tickers   : the watchlist; `list_tickers` returns exactly this list.
    api_key   : Massive API key (sent as ``Authorization: Bearer``).
    base_url  : REST host (default ``https://api.massive.com``).
    max_days  : drop expiries further out than this (and already-expired).
    http_get  : ``(url, params) -> dict`` performing one GET and returning the
                parsed JSON body; defaults to an httpx call carrying the Bearer
                header, injectable for offline tests.
    """

    def __init__(
        self,
        tickers: Sequence[str],
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        max_days: int = 730,
        http_get: Callable[[str, dict | None], dict] | None = None,
        iv_fallback: bool = True,
        ws_url: str | None = None,
        flat_store=None,
    ) -> None:
        self._tickers = [t.strip().upper() for t in tickers]
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_days = max_days
        self._http_get = http_get
        #: Optional explicit real-time WS cluster override (env
        #: VOLFIT_MASSIVE_WS_URL via serve.py). When unset the cluster is derived
        #: from the REST host, with the delayed cluster as an auto-fallback —
        #: see ``_ws_urls``.
        self._ws_url_override = ws_url
        #: When the live NBBO quotes are gated (base tier) but the snapshot still
        #: carries Massive's per-contract implied vol, synthesize zero-spread
        #: quotes from those IVs so the surface is still fittable. See
        #: ``_chain_from_iv``. Off => raise the usual entitlement error instead.
        self.iv_fallback = iv_fallback
        #: Optional real-time NBBO book (volfit.data.massive_ws). When streaming,
        #: ``fetch_chain(live)`` reads bid/ask from it instead of a REST snapshot
        #: poll. Started/stopped via ``start_streaming``/``stop_streaming``.
        self._live_book = None
        self._ws = None
        #: Optional flat-file history store (volfit.data.flatfiles, ROADMAP Tier
        #: 2). When present + credentialed it serves the official daily Close
        #: (day aggregates) for ANY recent trading day and reconstructs a chain at
        #: a past INTRADAY instant (minute aggregates) — so the as-of past-day
        #: moments work without the per-contract REST historical-quote path.
        self.flat_store = flat_store
        #: Cache of the listed contracts per (ticker, frozenset(expiries)) so the
        #: WS read path (``_chain_from_book``) and the scheduler's per-tick
        #: resubscribe diff (``option_tickers``) don't re-paginate the contracts
        #: reference every call. The listing is static intra-session for a fixed
        #: (ticker, expiry set); cleared on ``refresh_contracts`` if a fresh pull
        #: is wanted (e.g. a brand-new listing appears mid-session).
        self._contracts_cache: dict[tuple[str, frozenset | None], list[dict]] = {}

    def list_tickers(self) -> list[str]:
        return list(self._tickers)

    def feed_status(self) -> tuple[str, str]:
        """Cheap liveness probe (two single-page GETs, never full pagination):
        red without a key / when the contracts reference is unauthorized or
        unreachable; amber when the snapshot endpoint is authorized (a typically
        delayed tier) or only the reference works (quotes gated)."""
        if not self.api_key:
            return ("red", "no API key")
        tickers = self.list_tickers()
        if not tickers:
            return ("red", "no tickers configured")
        symbol = tickers[0].upper()
        try:
            ref = self._get(
                f"{self.base_url}/v3/reference/options/contracts",
                {"underlying_ticker": symbol, "limit": 1},
            )
        except Exception:
            return ("red", "unreachable")
        if ref.get("status") == "NOT_AUTHORIZED":
            return ("red", ref.get("message", "not entitled"))
        if not ref.get("results"):
            return ("red", "no contracts")
        try:
            snap = self._get(
                f"{self.base_url}/v3/snapshot/options/{symbol}", {"limit": 1}
            )
        except Exception:
            return ("amber", "reference only")
        if snap.get("status") == "NOT_AUTHORIZED":
            return ("amber", "reference only (quotes gated)")
        return ("amber", "delayed feed")

    # -- HTTP plumbing -------------------------------------------------------

    def _get(self, url: str, params: dict | None = None) -> dict:
        """One GET returning parsed JSON (does not raise on NOT_AUTHORIZED)."""
        if self._http_get is not None:
            return self._http_get(url, params)
        import httpx

        response = httpx.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=15.0,
        )
        return response.json()

    @staticmethod
    def _raise_if_unauthorized(body: dict) -> None:
        """Turn a NOT_AUTHORIZED body into an actionable RuntimeError."""
        if body.get("status") == "NOT_AUTHORIZED":
            message = body.get("message", "not entitled to this Massive data")
            raise RuntimeError(f"Massive: {message}")

    def _paginate(self, path: str, params: dict) -> Iterator[dict]:
        """Yield ``results`` across pages, following ``next_url`` (Bearer auth)."""
        url: str | None = f"{self.base_url}{path}"
        page_params: dict | None = params
        while url:
            body = self._get(url, page_params)
            self._raise_if_unauthorized(body)
            yield from body.get("results", []) or []
            url = body.get("next_url")
            page_params = None  # next_url already carries the cursor + filters

    # -- expiries ------------------------------------------------------------

    def available_expiries(self, ticker: str) -> list[date]:
        """All listed (unexpired) expiries inside (0, max_days] via the contracts
        reference endpoint (cheap; entitled on all tiers)."""
        today = date.today()
        expiries: set[date] = set()
        params = {
            "underlying_ticker": ticker.upper(),
            "expired": "false",
            "order": "asc",
            "sort": "expiration_date",
            "limit": 1000,
        }
        for contract in self._paginate("/v3/reference/options/contracts", params):
            expiry = _iso_date(contract.get("expiration_date"))
            if expiry is not None and 0 < (expiry - today).days <= self.max_days:
                expiries.add(expiry)
        return sorted(expiries)

    # -- chain ---------------------------------------------------------------

    def _snapshot_results(
        self, ticker: str, expiries: list[date] | None
    ) -> list[dict]:
        """Raw snapshot ``results`` for the selected expiries (or the horizon)."""
        path = f"/v3/snapshot/options/{ticker.upper()}"
        if expiries:
            out: list[dict] = []
            for expiry in sorted(expiries):
                out.extend(
                    self._paginate(
                        path,
                        {"expiration_date": expiry.isoformat(), "limit": _SNAPSHOT_LIMIT},
                    )
                )
            return out
        end = date.fromordinal(date.today().toordinal() + self.max_days)
        return list(
            self._paginate(
                path, {"expiration_date.lte": end.isoformat(), "limit": _SNAPSHOT_LIMIT}
            )
        )

    def historical_modes(self) -> set[str]:
        """Live + Previous Close (the snapshot's day close). With a flat-file
        history store, also per-day **EOD** (the official daily-aggregate close for
        any recent trading day)."""
        modes = {"live", "prev_close"}
        if self._flat_ready():
            modes.add("eod")
        return modes

    def available_history(self, ticker: str) -> list[date]:
        """Recent trading days the flat-file store can serve an EOD close for
        (newest last). Approximated as the last ~20 weekdays up to yesterday —
        today's file isn't published until after the close, and a non-trading day
        simply yields no bars (an empty chain) when fetched. Empty without a store."""
        if not self._flat_ready():
            return []
        out: list[date] = []
        day = date.today() - timedelta(days=1)
        while len(out) < 20:
            if day.weekday() < 5:
                out.append(day)
            day -= timedelta(days=1)
        return list(reversed(out))

    def _flat_ready(self) -> bool:
        return bool(self.flat_store is not None and self.flat_store.available())

    def intraday_capable(self) -> bool:
        """Massive/Polygon can reconstruct a chain at a past INSTANT from the
        per-contract historical NBBO quotes (``/v3/quotes``), so the as-of "latest"
        / "before close" moments work even with no captured snapshot. Needs a key."""
        return bool(self.api_key)

    # -- real-time streaming (WebSocket live book) ---------------------------

    def option_tickers(self, ticker: str, expiries: list[date] | None) -> list[str]:
        """The Polygon option tickers (``O:…``) for a ticker's selected expiries —
        what to subscribe to on the WebSocket."""
        return [c["ticker"] for c in self._intraday_contracts(ticker, expiries)]

    def _ws_url(self) -> str:
        """Real-time options-cluster WS endpoint derived from the REST host."""
        host = self.base_url.split("://")[-1].rstrip("/").replace("api.", "socket.")
        return f"wss://{host}/options"

    def _ws_urls(self) -> list[str]:
        """Candidate WS clusters, tried in order by the live-book client.

        Primary = the explicit override (``VOLFIT_MASSIVE_WS_URL``) or the
        real-time cluster derived from the REST host. The **delayed** cluster
        (``wss://delayed.polygon.io/options``) is appended as an auto-fallback:
        a delayed-tier key connects + auths on the real-time cluster but is served
        no quotes there, so the client advances to the delayed cluster (verified
        2026-06-15 to stream live SPY NBBO on this plan)."""
        primary = self._ws_url_override or self._ws_url()
        candidates = [primary]
        for fallback in ("wss://delayed.polygon.io/options",):
            if fallback not in candidates:
                candidates.append(fallback)
        return candidates

    def start_streaming(self, contracts: list[str]) -> None:
        """Open the WebSocket and stream NBBO for ``contracts`` into a live book;
        ``fetch_chain(live)`` then serves from it. Replaces any current stream."""
        from volfit.data.massive_ws import LiveBook, MassiveWebSocket

        self.stop_streaming()
        self._live_book = LiveBook()
        self._ws = MassiveWebSocket(
            self.api_key, list(contracts), self._live_book, urls=self._ws_urls()
        )
        self._ws.start()

    def stop_streaming(self) -> None:
        """Tear down the WebSocket and drop the live book (back to REST live)."""
        if self._ws is not None:
            self._ws.stop()
            self._ws = None
        self._live_book = None

    def is_streaming(self) -> bool:
        return self._ws is not None and self._ws.is_running()

    def streaming_contracts(self) -> set[str]:
        """The contract set currently subscribed on the WS (empty if not streaming)
        — lets the scheduler detect a universe change and resubscribe."""
        return set(self._ws.contracts) if self._ws is not None else set()

    def _spot_from_quotes(self, quotes: list[OptionQuote]) -> float | None:
        """Parity forward (spot proxy) from already-built two-sided quotes."""
        by_exp: dict[date, dict[float, dict[str, float]]] = {}
        for q in quotes:
            if q.bid is None or q.ask is None or q.ask < q.bid:
                continue
            by_exp.setdefault(q.expiry, {}).setdefault(q.strike, {})[q.call_put] = 0.5 * (q.bid + q.ask)
        return _parity_forward(by_exp)

    def _chain_from_book(
        self, ticker: str, expiries: list[date] | None
    ) -> ChainSnapshot | None:
        """Build the live chain from the streamed NBBO book for the selected
        contracts. None until enough two-sided quotes are booked to imply a
        forward (so the caller can REST-fetch the first frame)."""
        contracts = self._intraday_contracts(ticker, expiries)
        if not contracts:
            return None
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        quotes: list[OptionQuote] = []
        styles: list[str] = []
        for c in contracts:
            tick = self._live_book.quote(c["ticker"]) if self._live_book else None
            quotes.append(
                OptionQuote(
                    ticker=ticker.upper(),
                    expiry=c["expiry"],
                    strike=c["strike"],
                    call_put=c["call_put"],
                    bid=tick.bid if tick else None,
                    ask=tick.ask if tick else None,
                    last=None,
                    volume=None,
                    open_interest=None,
                    timestamp=timestamp,
                )
            )
            if c["style"] in ("american", "european"):
                styles.append(c["style"])
        spot = self._spot_from_quotes(quotes)
        if spot is None:
            return None
        return ChainSnapshot(
            ticker=ticker.upper(), spot=spot, timestamp=timestamp,
            quotes=quotes, exercise_style=_resolve_style(styles),
        )

    def fetch_chain(
        self,
        ticker: str,
        expiries: list[date] | None = None,
        as_of: AsOf | None = None,
    ) -> ChainSnapshot:
        """Fetch the chain snapshot for the selected expiries (or the horizon).

        ``as_of.mode == "prev_close"`` prices each contract at the session close
        (``day.close``, quoted as a zero-spread bid=ask=close so the mid fitter
        works); live uses the NBBO ``last_quote``. The spot comes from the option
        snapshot's ``underlying_asset.price``, else put-call parity on the chain
        (options-only); the STOCKS-snapshot fallback (a separate plan) is the last
        resort and only it can raise ``RuntimeError`` for entitlement.
        """
        # Flat-file history (Tier 2): the official daily Close for any recent
        # trading day, and a past INTRADAY instant — both reconstructed from the
        # aggregate flat files rather than the heavy per-contract REST quotes.
        if as_of is not None and as_of.mode == "eod" and as_of.on is not None and self._flat_ready():
            flat = self._fetch_flat(ticker, expiries, datetime.combine(as_of.on, time(23, 59, 59)), "day")
            if flat is None:
                raise RuntimeError(f"Massive: no flat-file data for {as_of.on.isoformat()}")
            return flat
        if as_of is not None and as_of.mode == "intraday" and as_of.ts is not None:
            if as_of.ts.date() < date.today() and self._flat_ready():
                flat = self._fetch_flat(ticker, expiries, as_of.ts, "minute")
                if flat is not None:
                    return flat  # else fall back to the per-contract REST quotes
            return self._fetch_intraday(ticker, expiries, as_of.ts)
        # Live + streaming: serve from the real-time WS book (no REST poll). Falls
        # through to a REST snapshot if the book hasn't warmed enough to imply a
        # forward yet (the first fetch after streaming starts).
        if (as_of is None or as_of.mode == "live") and self._live_book is not None:
            chain = self._chain_from_book(ticker, expiries)
            if chain is not None:
                return chain
        prev_close = as_of is not None and as_of.mode == "prev_close"
        results = self._snapshot_results(ticker, expiries)
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        quotes: list[OptionQuote] = []
        styles: list[str] = []
        spot: float | None = None
        for result in results:
            details = result.get("details") or {}
            strike = price_or_none(details.get("strike_price"))
            expiry = _iso_date(details.get("expiration_date"))
            call_put = {"call": "C", "put": "P"}.get(details.get("contract_type"))
            if strike is None or expiry is None or call_put is None:
                continue
            last_quote = result.get("last_quote") or {}
            day = result.get("day") or {}
            close = price_or_none(day.get("close")) or price_or_none(
                day.get("previous_close")
            )
            if prev_close:
                bid = ask = close  # zero-spread close so mid-fitting uses it
            else:
                bid = price_or_none(last_quote.get("bid"))
                ask = price_or_none(last_quote.get("ask"))
            quotes.append(
                OptionQuote(
                    ticker=ticker.upper(),
                    expiry=expiry,
                    strike=strike,
                    call_put=call_put,
                    bid=bid,
                    ask=ask,
                    last=close,
                    volume=int_or_none(day.get("volume")),
                    open_interest=int_or_none(result.get("open_interest")),
                    timestamp=timestamp,
                )
            )
            style = str(details.get("exercise_style", "")).strip().lower()
            if style in ("american", "european"):
                styles.append(style)
            if spot is None:
                spot = price_or_none((result.get("underlying_asset") or {}).get("price"))

        # Live NBBO gated on the base tier -> no two-sided quotes. If Massive still
        # returned its per-contract IV in the snapshot, synthesize the chain from
        # those IVs so the surface is fittable without the paid quote add-on.
        two_sided = sum(1 for q in quotes if q.bid is not None and q.ask is not None)
        if not prev_close and two_sided == 0 and self.iv_fallback:
            iv_chain = self._chain_from_iv(ticker, results, spot)
            if iv_chain is not None and iv_chain.quotes:
                return iv_chain

        if spot is None:
            spot = self._spot_from_parity(results)  # options-only: chain's own forward
        if spot is None:
            spot = self._spot(ticker)  # last resort: STOCKS snapshot (separate plan)
        return ChainSnapshot(
            ticker=ticker.upper(),
            spot=spot,
            timestamp=timestamp,
            quotes=quotes,
            exercise_style=_resolve_style(styles),
        )

    def _chain_from_iv(
        self, ticker: str, results: list[dict], spot: float | None
    ) -> ChainSnapshot | None:
        """Synthesize a zero-spread, European chain from Massive's per-contract
        implied vols (the base-tier fallback when NBBO quotes are gated).

        Each contract is priced from its IV with Black at forward = spot, DF = 1,
        and quoted bid = ask = price; the fitter re-inverts those prices and so
        recovers exactly Massive's IV smile (exact at zero carry; a tiny shift
        otherwise). Marked European so the pipeline does not de-Americanize a
        price that is already a clean Black value. None if no spot/IVs to use.
        """
        if spot is None or spot <= 0.0:
            return None
        today = date.today()
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        quotes: list[OptionQuote] = []
        for result in results:
            details = result.get("details") or {}
            strike = price_or_none(details.get("strike_price"))
            expiry = _iso_date(details.get("expiration_date"))
            call_put = {"call": "C", "put": "P"}.get(details.get("contract_type"))
            iv = result.get("implied_volatility")
            if strike is None or expiry is None or call_put is None or iv is None:
                continue
            t = (expiry - today).days / 365.0
            price = _price_from_iv(spot, strike, call_put, float(iv), t)
            if price is None or price <= 0.0:
                continue
            day = result.get("day") or {}
            quotes.append(
                OptionQuote(
                    ticker=ticker.upper(),
                    expiry=expiry,
                    strike=strike,
                    call_put=call_put,
                    bid=price,
                    ask=price,  # zero spread: the IV is the "mid"
                    last=price_or_none(day.get("close")),
                    volume=int_or_none(day.get("volume")),
                    open_interest=int_or_none(result.get("open_interest")),
                    timestamp=timestamp,
                )
            )
        if not quotes:
            return None
        return ChainSnapshot(
            ticker=ticker.upper(), spot=spot, timestamp=timestamp,
            quotes=quotes, exercise_style="european",
        )

    def _spot_from_parity(self, results: list[dict]) -> float | None:
        """Forward of the nearest expiry from put-call parity (a spot proxy when
        the option snapshot carries no ``underlying_asset.price``), so an
        OPTIONS-only plan works without the separate STOCKS-snapshot entitlement."""
        by_exp: dict[date, dict[float, dict[str, float]]] = {}
        for result in results:
            details = result.get("details") or {}
            expiry = _iso_date(details.get("expiration_date"))
            strike = price_or_none(details.get("strike_price"))
            call_put = {"call": "C", "put": "P"}.get(details.get("contract_type"))
            if expiry is None or strike is None or call_put is None:
                continue
            lq = result.get("last_quote") or {}
            bid, ask = price_or_none(lq.get("bid")), price_or_none(lq.get("ask"))
            if bid is None or ask is None or ask < bid:
                continue
            by_exp.setdefault(expiry, {}).setdefault(strike, {})[call_put] = 0.5 * (bid + ask)
        return _parity_forward(by_exp)

    def _spot(self, ticker: str) -> float:
        """Underlying last price via the STOCKS snapshot — a SEPARATE product from
        options, so an options-only plan (even 'Advanced') is not entitled to it.
        Only reached when the option snapshot has no underlying price AND parity
        gives no forward; ``fetch_chain`` prefers both of those."""
        url = (
            f"{self.base_url}/v2/snapshot/locale/us/markets/stocks/tickers/"
            f"{ticker.upper()}"
        )
        body = self._get(url)
        self._raise_if_unauthorized(body)
        snapshot = body.get("ticker") or body.get("results") or {}
        last_trade = snapshot.get("lastTrade") or {}
        spot = price_or_none(last_trade.get("p"))
        if spot is None:
            day = snapshot.get("day") or {}
            spot = price_or_none(day.get("c"))
        if spot is None:
            raise RuntimeError(
                f"Massive: no underlying spot for {ticker!r}; upgrade the plan "
                "for the stock snapshot, or use Bloomberg/Yahoo for spot."
            )
        return spot

    def _fetch_flat(
        self, ticker: str, expiries: list[date] | None, ts: datetime, frequency: str
    ):
        """Reconstruct the chain from the flat-file store (day/minute aggregates),
        co-caching the whole watchlist from the same daily file. None on no data."""
        return self.flat_store.chain_at(
            ticker, expiries, ts, underlyings=self.list_tickers(), frequency=frequency
        )

    # -- intraday replay (historical NBBO at an instant) ---------------------

    def _intraday_contracts(
        self, ticker: str, expiries: list[date] | None
    ) -> list[dict]:
        """Listed contracts (option ticker + strike/expiry/type/style) for the
        selected expiries, from the reference endpoint — the keys to query each
        contract's historical quote by. Cached per (ticker, expiry set) so the
        live book read / resubscribe diff don't re-paginate every call."""
        key = (ticker.upper(), frozenset(expiries) if expiries else None)
        cached = self._contracts_cache.get(key)
        if cached is not None:
            return cached
        wanted = set(expiries) if expiries else None
        out: list[dict] = []
        params = {
            "underlying_ticker": ticker.upper(),
            "expired": "false",
            "order": "asc",
            "sort": "expiration_date",
            "limit": 1000,
        }
        for c in self._paginate("/v3/reference/options/contracts", params):
            expiry = _iso_date(c.get("expiration_date"))
            opt_ticker = c.get("ticker")
            call_put = {"call": "C", "put": "P"}.get(c.get("contract_type"))
            strike = price_or_none(c.get("strike_price"))
            if expiry is None or opt_ticker is None or call_put is None or strike is None:
                continue
            if wanted is not None and expiry not in wanted:
                continue
            out.append(
                {"ticker": opt_ticker, "expiry": expiry, "strike": strike,
                 "call_put": call_put, "style": str(c.get("exercise_style", "")).lower()}
            )
        self._contracts_cache[key] = out
        return out

    def refresh_contracts(self) -> None:
        """Drop the cached contract listings (force a fresh reference pull)."""
        self._contracts_cache.clear()

    def _quote_le(self, option_ticker: str, ns: int) -> dict:
        """The most recent NBBO quote at-or-before ``ns`` (nanoseconds) for one
        contract; ``{}`` if none exists then."""
        body = self._get(
            f"{self.base_url}/v3/quotes/{option_ticker}",
            {"timestamp.lte": ns, "order": "desc", "sort": "timestamp", "limit": 1},
        )
        self._raise_if_unauthorized(body)
        results = body.get("results") or []
        return results[0] if results else {}

    def _fetch_intraday(
        self, ticker: str, expiries: list[date] | None, ts: datetime
    ) -> ChainSnapshot:
        """Reconstruct the chain at instant ``ts`` from per-contract historical
        NBBO quotes (Polygon ``/v3/quotes``; one request per selected contract)."""
        ns = int(ts.replace(tzinfo=timezone.utc).timestamp() * 1_000_000_000)
        contracts = self._intraday_contracts(ticker, expiries)
        quotes: list[OptionQuote] = []
        styles: list[str] = []
        for c in contracts:
            q = self._quote_le(c["ticker"], ns)
            quotes.append(
                OptionQuote(
                    ticker=ticker.upper(),
                    expiry=c["expiry"],
                    strike=c["strike"],
                    call_put=c["call_put"],
                    bid=price_or_none(q.get("bid_price")),
                    ask=price_or_none(q.get("ask_price")),
                    last=None,
                    volume=None,
                    open_interest=None,
                    timestamp=ts,
                )
            )
            if c["style"] in ("american", "european"):
                styles.append(c["style"])
        return ChainSnapshot(
            ticker=ticker.upper(),
            spot=self._spot_at(ticker, ns),
            timestamp=ts,
            quotes=quotes,
            exercise_style=_resolve_style(styles),
        )

    def _spot_at(self, ticker: str, ns: int) -> float:
        """Underlying mid at-or-before ``ns`` from the stock NBBO quotes feed."""
        body = self._get(
            f"{self.base_url}/v3/quotes/{ticker.upper()}",
            {"timestamp.lte": ns, "order": "desc", "sort": "timestamp", "limit": 1},
        )
        self._raise_if_unauthorized(body)
        results = body.get("results") or []
        if results:
            bid = price_or_none(results[0].get("bid_price"))
            ask = price_or_none(results[0].get("ask_price"))
            if bid is not None and ask is not None:
                return (bid + ask) / 2.0
            if bid is not None or ask is not None:
                return float(bid if bid is not None else ask)
        raise RuntimeError(
            f"Massive: no historical underlying quote for {ticker!r} at the requested instant"
        )

    # -- IV overlay (entitled without quotes; see Phase C) -------------------

    def iv_surface(self, ticker: str, expiries: list[date] | None = None) -> list[dict]:
        """Massive's precomputed IV/greeks per contract (read-only overlay).

        Returns one dict per contract: ``expiry``/``strike``/``callPut``/``iv``/
        ``delta``/``gamma``/``theta``/``vega``/``openInterest``/``dayClose``.
        Distinct from `fetch_chain`: this needs no quote entitlement, so it
        works on the base options tier.
        """
        rows: list[dict] = []
        for result in self._snapshot_results(ticker, expiries):
            details = result.get("details") or {}
            expiry = _iso_date(details.get("expiration_date"))
            call_put = {"call": "C", "put": "P"}.get(details.get("contract_type"))
            iv = result.get("implied_volatility")
            if expiry is None or call_put is None or iv is None:
                continue
            greeks = result.get("greeks") or {}
            day = result.get("day") or {}
            rows.append(
                {
                    "expiry": expiry.isoformat(),
                    "strike": price_or_none(details.get("strike_price")),
                    "callPut": call_put,
                    "iv": float(iv),
                    "delta": greeks.get("delta"),
                    "gamma": greeks.get("gamma"),
                    "theta": greeks.get("theta"),
                    "vega": greeks.get("vega"),
                    "openInterest": int_or_none(result.get("open_interest")),
                    "dayClose": price_or_none(day.get("close")),
                }
            )
        return rows

    # -- symbol search -------------------------------------------------------

    def search_symbols(self, query: str, limit: int = 10) -> list[SymbolMatch]:
        """Massive ticker reference search; falls back to the base echo search."""
        q = query.strip()
        if not q:
            return []
        try:
            body = self._get(
                f"{self.base_url}/v3/reference/tickers",
                {"search": q, "market": "stocks", "active": "true", "limit": limit},
            )
            if body.get("status") == "NOT_AUTHORIZED":
                return super().search_symbols(query, limit)
            results = body.get("results", []) or []
        except Exception:
            return super().search_symbols(query, limit)
        out: list[SymbolMatch] = []
        for item in results:
            symbol = item.get("ticker")
            if not symbol:
                continue
            out.append(
                SymbolMatch(
                    symbol=symbol,
                    name=item.get("name", ""),
                    type=item.get("type", ""),
                    exchange=item.get("primary_exchange", ""),
                )
            )
        return out[:limit]


def _resolve_style(styles: list[str]) -> str:
    """Majority exercise style across a chain (default american for equities)."""
    if not styles:
        return "american"
    return "european" if styles.count("european") > styles.count("american") else "american"


def _parity_forward(by_exp: dict[date, dict[float, dict[str, float]]]) -> float | None:
    """Nearest-expiry forward from put-call parity ``C(K) − P(K) = D·(F − K)``.

    ``by_exp`` maps expiry -> strike -> {"C": call_mid, "P": put_mid}. Regresses
    the paired strikes of the front expiry with ≥3 pairs; None otherwise."""
    import numpy as np

    for expiry in sorted(by_exp):
        pairs = [(k, v["C"], v["P"]) for k, v in by_exp[expiry].items() if "C" in v and "P" in v]
        if len(pairs) < 3:
            continue
        strikes = np.array([p[0] for p in pairs])
        y = np.array([p[1] - p[2] for p in pairs])
        (a, b), *_ = np.linalg.lstsq(np.column_stack([np.ones_like(strikes), strikes]), y, rcond=None)
        discount = -float(b)
        if discount > 0.0:
            return float(a) / discount
    return None


def _price_from_iv(
    spot: float, strike: float, call_put: str, iv: float, t: float
) -> float | None:
    """Black price of one option from its implied vol, at forward = spot, DF = 1.

    Uses the normalized forward call ``black_call(k, w)`` (k = ln(K/F), w = σ²T):
    call = F·B(k,w); the put follows by parity (put = call − (F − K)). Returns
    None for a degenerate input (non-positive vol/time/strike)."""
    if iv <= 0.0 or t <= 0.0 or strike <= 0.0 or spot <= 0.0:
        return None
    k = math.log(strike / spot)
    w = iv * iv * t
    call = spot * float(black_call(k, w))
    price = call if call_put == "C" else call - (spot - strike)
    return price if price > 0.0 else None
