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

from datetime import date, datetime, timezone
from typing import Callable, Iterator, Sequence

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
    ) -> None:
        self._tickers = [t.strip().upper() for t in tickers]
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_days = max_days
        self._http_get = http_get

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
        """Live + Previous Close (the snapshot's day close); no per-day EOD list
        (Polygon historical chains are per-contract daily bars — too heavy)."""
        return {"live", "prev_close"}

    def fetch_chain(
        self,
        ticker: str,
        expiries: list[date] | None = None,
        as_of: AsOf | None = None,
    ) -> ChainSnapshot:
        """Fetch the chain snapshot for the selected expiries (or the horizon).

        ``as_of.mode == "prev_close"`` prices each contract at the session close
        (``day.close``, quoted as a zero-spread bid=ask=close so the mid fitter
        works); live uses the NBBO ``last_quote``. Raises ``RuntimeError`` if the
        plan does not entitle the underlying spot.
        """
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

        if spot is None:
            spot = self._spot(ticker)  # stock snapshot fallback (may raise upgrade)
        return ChainSnapshot(
            ticker=ticker.upper(),
            spot=spot,
            timestamp=timestamp,
            quotes=quotes,
            exercise_style=_resolve_style(styles),
        )

    def _spot(self, ticker: str) -> float:
        """Underlying last price via the stocks snapshot (gated on lower tiers)."""
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
