"""REST per-contract NBBO capture — the fast alternative to the flat-file firehose.

The `quotes_v1` flat file is the OPRA firehose (~4.8 h/day to stream). With the
Massive/Polygon REST API (Options Advanced: no rate limit, historical quotes),
the same 15:45-ET chain is reconstructed in ~minutes/day:

  1. enumerate the day's contracts — `/v3/reference/options/contracts`
     (`as_of=date`, expiration window, paginated; plain ticker for indices so
     SPX -> O:SPX/O:SPXW etc.);
  2. fetch each contract's NBBO at-or-before the instant CONCURRENTLY —
     `/v3/quotes/{O:..}?timestamp.lte=&order=desc&limit=1` (measured ~110/s).

Returns the same `ChainSnapshot` the flat-file path does, so capture + the whole
compute pipeline are unchanged. Probed 2026-06-24: historical NBBO confirmed, no
429s, ~110 quotes/s sustained.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone

from volfit.data.types import US_OPTION_TICK, ChainSnapshot, OptionQuote

from backtest.quotes_store import _parity_spot, _pos_or_none

DEFAULT_BASE_URL = "https://api.polygon.io"
#: Below this length the configured key is a stub/placeholder (the real key is 32).
_MIN_KEY_LEN = 16


@dataclass(frozen=True)
class _Contract:
    occ_ticker: str  # O:...
    strike: float
    call_put: str  # 'C' | 'P'
    expiry: date


class RestQuotesClient:
    """Concurrent historical-NBBO chain reconstruction over the REST API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        concurrency: int = 40,
        min_dte: int = 7,
        max_dte: int = 400,
        retries: int = 3,
    ) -> None:
        key = (api_key or "").strip()
        if len(key) < _MIN_KEY_LEN:
            raise ValueError(
                f"VOLFIT_MASSIVE_KEY looks like a stub (len {len(key)}); set the real "
                "Massive/Polygon REST key (it is shadowed by a stale 4-char env var — "
                "clear it or force-set it in restart.local.ps1)."
            )
        self._key = key
        self.base_url = base_url.rstrip("/")
        self.concurrency = concurrency
        self.min_dte = min_dte
        self.max_dte = max_dte
        self.retries = retries
        self._headers = {"Authorization": f"Bearer {key}"}

    # ---------------------------------------------------------- public (sync)
    def enumerate_contracts(
        self, option_roots: list[str], as_of: date
    ) -> dict[date, list[_Contract]]:
        """Contracts grouped by expiry for the roots, as they existed on ``as_of``
        (DTE in [min_dte, max_dte]). One reference walk; cheap (no quotes)."""
        return asyncio.run(self._enumerate(option_roots, as_of))

    def fetch_nbbo(
        self,
        ticker: str,
        contracts_by_expiry: dict[date, list[_Contract]],
        ts: datetime,
        exercise_style: str,
    ) -> ChainSnapshot | None:
        """Concurrent NBBO at-or-before ``ts`` for every given contract; assembled
        into a ChainSnapshot (spot from put-call parity). None if nothing two-sided."""
        return asyncio.run(self._fetch_nbbo(ticker, contracts_by_expiry, ts, exercise_style))

    # ------------------------------------------------------------- async core
    async def _enumerate(
        self, option_roots: list[str], as_of: date
    ) -> dict[date, list[_Contract]]:
        import httpx

        lo = as_of.toordinal() + self.min_dte
        hi = as_of.toordinal() + self.max_dte
        lo_iso, hi_iso = date.fromordinal(lo).isoformat(), date.fromordinal(hi).isoformat()
        out: dict[date, list[_Contract]] = {}
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0) as client:
            for root in option_roots:
                url = f"{self.base_url}/v3/reference/options/contracts"
                params: dict | None = {
                    "underlying_ticker": root, "as_of": as_of.isoformat(),
                    "expiration_date.gte": lo_iso, "expiration_date.lte": hi_iso,
                    "limit": 1000,
                }
                while url:
                    body = await self._get(client, url, params)
                    for c in body.get("results") or []:
                        try:
                            exp = date.fromisoformat(c["expiration_date"])
                            cp = "C" if c["contract_type"] == "call" else "P"
                            out.setdefault(exp, []).append(
                                _Contract(c["ticker"], float(c["strike_price"]), cp, exp)
                            )
                        except (KeyError, ValueError):
                            continue
                    url = body.get("next_url") or ""
                    params = None  # next_url already carries the cursor
        return out

    async def _fetch_nbbo(
        self,
        ticker: str,
        contracts_by_expiry: dict[date, list[_Contract]],
        ts: datetime,
        exercise_style: str,
    ) -> ChainSnapshot | None:
        import httpx

        contracts = [c for cs in contracts_by_expiry.values() for c in cs]
        if not contracts:
            return None
        target_ns = _to_ns(ts)
        sem = asyncio.Semaphore(self.concurrency)
        limits = httpx.Limits(max_connections=self.concurrency + 10)
        async with httpx.AsyncClient(headers=self._headers, timeout=30.0, limits=limits) as client:
            async def one(c: _Contract) -> OptionQuote | None:
                async with sem:
                    body = await self._get(
                        client, f"{self.base_url}/v3/quotes/{c.occ_ticker}",
                        {"timestamp.lte": target_ns, "order": "desc", "limit": 1},
                    )
                res = body.get("results") or []
                if not res:
                    return None
                q = res[0]
                bid, ask = _pos_or_none(q.get("bid_price")), _pos_or_none(q.get("ask_price"))
                if bid is None and ask is None:
                    return None
                return OptionQuote(
                    ticker=ticker.upper(), expiry=c.expiry, strike=c.strike,
                    call_put=c.call_put, bid=bid, ask=ask, last=None, volume=None,
                    open_interest=_int_or_none(q.get("ask_size")), timestamp=ts,
                )

            quotes = [q for q in await asyncio.gather(*[one(c) for c in contracts]) if q]
        if not quotes:
            return None
        spot = _parity_spot(quotes)
        if spot is None:
            return None
        return ChainSnapshot(
            ticker=ticker.upper(), spot=spot, timestamp=ts, quotes=quotes,
            exercise_style=exercise_style,
            # Real NBBO — stamp the tick so the OTM tick-noise screen engages
            # (the live providers all do; None silently disables it).
            tick_size=US_OPTION_TICK,
        )

    async def _get(self, client, url: str, params: dict | None) -> dict:
        """GET with a small retry/backoff for transient 429/5xx/timeout."""
        import httpx

        for attempt in range(self.retries):
            try:
                r = await client.get(url, params=params)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("transient", request=r.request, response=r)
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, httpx.TimeoutException):
                if attempt == self.retries - 1:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))
        return {}


def _to_ns(ts: datetime) -> int:
    return int(ts.replace(tzinfo=timezone.utc).timestamp() * 1_000_000_000)


def _int_or_none(v) -> int | None:
    return None if v is None else int(v)
