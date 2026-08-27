"""HTTP primitives of the REST intraday capture (``capture_intraday_rest``).

Everything that talks to the Massive REST API lives here — the backoff GET,
cursor pagination, the day-close window anchor and the per-contract NBBO
reduction — split out for the 400-line policy. The capture logic (multi-root
discovery, expiry ladder, per-instant checkpointing, fixtures) stays in
``capture_intraday_rest``, which imports these names.
"""

from __future__ import annotations

import time as _time
from datetime import date

import httpx

from backtest.quotes_store import _pos_or_none

DEFAULT_HOST = "https://api.massive.com"

_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _get(client: httpx.Client, url: str, params: dict | None, max_tries: int = 9) -> dict:
    """One GET with backoff on 429/5xx/network errors; raises on other 4xx.

    The backoff must RIDE OUT a transient DNS/network outage — this link
    drops DNS for minutes at a time (the flat-file path learned the same
    lesson, commit 511f805; the REST campaign died live on 'getaddrinfo
    failed' with a ~30 s total budget). Waits 10, 20, 40, 80, 120, 120, ...
    seconds: ~10 minutes of outage survived per request."""
    wait = 10.0
    for attempt in range(1, max_tries + 1):
        try:
            resp = client.get(url, params=params)
        except httpx.HTTPError:
            if attempt == max_tries:
                raise
            _time.sleep(wait)
            wait = min(wait * 2.0, 120.0)
            continue
        if resp.status_code in _RETRY_STATUSES and attempt < max_tries:
            retry_after = resp.headers.get("Retry-After")
            _time.sleep(float(retry_after) if retry_after else wait)
            wait = min(wait * 2.0, 120.0)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"unreachable after {max_tries} tries: {url}")


def _paged(client: httpx.Client, path: str, params: dict):
    """Yield ``results`` rows across ``next_url`` pages (cursor keeps the query)."""
    url: str | None = path
    while url:
        data = _get(client, url, params)
        yield from data.get("results") or []
        url = data.get("next_url")
        params = None  # the cursor URL carries the whole query


def day_close(
    client: httpx.Client, ticker: str, day: date,
    candidates: tuple[str, ...] | None = None,
) -> float:
    """The day's official close from the daily aggregate (window anchor).

    ``candidates`` are the aggregate tickers to try in order (default just
    ``ticker``); an index capture passes ``("I:SPX", "SPX")`` since Massive
    keys index aggregates under the ``I:`` prefix."""
    for agg in candidates or (ticker,):
        data = _get(client, f"/v2/aggs/ticker/{agg}/range/1/day/{day}/{day}", None)
        results = data.get("results") or []
        if results:
            return float(results[0]["c"])
    raise RuntimeError(f"no daily aggregate for {ticker} {day} (holiday? bad day?)")


def nbbo_at(client: httpx.Client, occ: str, gte_ns: int, lte_ns: int) -> dict | None:
    """The contract's NBBO at-or-before the instant (within the day), or None."""
    data = _get(client, f"/v3/quotes/{occ}", {
        "timestamp.gte": gte_ns,
        "timestamp.lte": lte_ns,
        "order": "desc",
        "sort": "timestamp",
        "limit": 1,
    })
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    bid = _pos_or_none(r.get("bid_price"))
    ask = _pos_or_none(r.get("ask_price"))
    if bid is None and ask is None:
        return None
    size = r.get("ask_size")
    return {"bid": bid, "ask": ask, "size": None if size is None else int(size)}
