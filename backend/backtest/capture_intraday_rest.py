"""Light intraday 0DTE capture over the Massive REST quotes API (R2 item 10).

The flat-file route (``capture_intraday``) is the campaign gold standard, but
one day of ``quotes_v1`` is ~111 GB (measured 2026-07-10) — hours of fragile
streaming per (ticker, day) on this link, and four probe attempts died
mid-stream. The REST historical-quotes endpoint serves the SAME SIP NBBO per
contract: ``GET /v3/quotes/{occ}?timestamp.lte=T&order=desc&limit=1`` is
exactly the flat-file reduction ("the last quote at-or-before the instant"),
so a 13-instant SPY day costs tens of thousands of tiny requests (minutes)
instead of 111 GB. Fixture schema, expiry ladder, instants and VolStore
persistence are shared with ``capture_intraday``, so
``validate_intraday_clock`` and the app's captured replay work unchanged —
a REST-captured day is skipped by (and interchangeable with) the flat-file
campaign.

Scope guard: contracts are discovered inside a moneyness window around the
day's close — dailies +/-10% (0-7 DTE SPY does not move 10% intraday), term
anchors +/-25% — the prep screens drop worthless wings anyway.

Sibling: ``rest_quotes.RestQuotesClient`` is the daily capture's REST source
(one 15:45 instant, DTE >= 7, whole board). This module exists for what that
one lacks: many sub-day instants per day, a day-bounded ``timestamp.gte``
(a contract not quoted TODAY must be absent, not carry yesterday's NBBO —
the flat-file day-scan semantics), strike windowing, and per-instant
checkpoint/resume.

Run (needs VOLFIT_MASSIVE_KEY — dot-source restart.local.ps1 first):

    python -m backtest.capture_intraday_rest --start 2026-07-10 --end 2026-07-10 \
        --tickers SPY --db backtest/results/intraday.sqlite
"""

from __future__ import annotations

import argparse
import json
import os
import time as _time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from volfit.data.expiry_time import is_trading_day
from volfit.data.types import OptionQuote

from backtest.capture_intraday import (
    DEFAULT_TIMES,
    FIXTURE_DIR,
    MAX_DAILY_DTE,
    TERM_ANCHOR_MAX_DTE,
    UNIVERSE_0DTE,
    _parse_times,
    _persist_db,
    select_expiries,
    session_instants,
)
from backtest.quotes_store import _parity_spot, _pos_or_none, _to_ns

ET = ZoneInfo("America/New_York")
DEFAULT_HOST = "https://api.massive.com"

#: Moneyness windows for contract discovery (fraction of the day's close).
DAILY_WINDOW = 0.10
ANCHOR_WINDOW = 0.25

#: Concurrent quote requests. The paid tiers are not request-limited; 429s
#: are still honored with backoff below.
DEFAULT_WORKERS = 12

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
        except httpx.HTTPError as exc:
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


def day_close(client: httpx.Client, ticker: str, day: date) -> float:
    """The day's official close from the daily aggregate (window anchor)."""
    data = _get(client, f"/v2/aggs/ticker/{ticker}/range/1/day/{day}/{day}", None)
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"no daily aggregate for {ticker} {day} (holiday? bad day?)")
    return float(results[0]["c"])


def discover_contracts(
    client: httpx.Client, ticker: str, day: date, close: float,
    daily_window: float = DAILY_WINDOW, anchor_window: float = ANCHOR_WINDOW,
) -> dict[str, tuple[date, float, str]]:
    """OCC ticker -> (expiry, strike, C/P) for the day's board, windowed.

    Two spans: the daily ladder (DTE <= MAX_DAILY_DTE, tight window) and the
    term-anchor span (wider window). Both ``expired`` flags are queried — the
    dailies have expired by capture time, the anchors may still be live —
    and deduped by OCC ticker.
    """
    spans = (
        (day, day + timedelta(days=MAX_DAILY_DTE), daily_window),
        (day + timedelta(days=MAX_DAILY_DTE + 1),
         day + timedelta(days=TERM_ANCHOR_MAX_DTE), anchor_window),
    )
    out: dict[str, tuple[date, float, str]] = {}
    for lo, hi, window in spans:
        for expired in ("true", "false"):
            params = {
                "underlying_ticker": ticker,
                "as_of": day.isoformat(),
                "expired": expired,
                "expiration_date.gte": lo.isoformat(),
                "expiration_date.lte": hi.isoformat(),
                "strike_price.gte": close * (1.0 - window),
                "strike_price.lte": close * (1.0 + window),
                "limit": 1000,
            }
            for row in _paged(client, "/v3/reference/options/contracts", params):
                cp = "C" if row["contract_type"] == "call" else "P"
                out[row["ticker"]] = (
                    date.fromisoformat(row["expiration_date"]),
                    float(row["strike_price"]),
                    cp,
                )
    return out


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


def _spot(quotes: list[dict], ts: datetime, ticker: str) -> float | None:
    """Parity spot from the snapshot's own quotes (same rule as the flat files)."""
    objs = [
        OptionQuote(
            ticker=ticker, expiry=date.fromisoformat(q["expiry"]), strike=q["strike"],
            call_put=q["cp"], bid=q["bid"], ask=q["ask"], last=None, volume=None,
            open_interest=q["size"], timestamp=ts,
        )
        for q in quotes
    ]
    return _parity_spot(objs)


def capture_day_rest(
    client: httpx.Client,
    ticker: str,
    day: date,
    times: tuple[time, ...] = DEFAULT_TIMES,
    workers: int = DEFAULT_WORKERS,
    daily_window: float = DAILY_WINDOW,
    anchor_window: float = ANCHOR_WINDOW,
) -> dict | None:
    """One (asset, day)'s intraday snapshots via REST — the fixture document.

    Progress is checkpointed per instant into ``<fixture>.part.json`` so an
    interrupted day resumes at the next instant, not from scratch.
    """
    instants = session_instants(day, times)
    if not instants:
        return None
    close = day_close(client, ticker, day)
    contracts = discover_contracts(client, ticker, day, close,
                                   daily_window, anchor_window)
    keep = set(select_expiries({c[0] for c in contracts.values()}, day))
    kept = sorted(
        (occ, exp, strike, cp)
        for occ, (exp, strike, cp) in contracts.items() if exp in keep
    )
    if not kept:
        return None
    print(f"{ticker} {day}: close={close:.2f}, {len(kept)} contracts, "
          f"{len(keep)} expiries, {len(instants)} instants")

    os.makedirs(FIXTURE_DIR, exist_ok=True)
    part_path = os.path.join(FIXTURE_DIR, f"{ticker}_{day.isoformat()}.part.json")
    part: dict[str, dict | None] = {}
    if os.path.exists(part_path):
        with open(part_path, encoding="utf-8") as fh:
            part = json.load(fh)

    gte_ns = _to_ns(
        datetime.combine(day, time(0, 0), tzinfo=ET).astimezone(ZoneInfo("UTC"))
        .replace(tzinfo=None)
    )
    for ts in instants:
        key = ts.isoformat()
        if key in part:
            continue
        t0 = _time.perf_counter()
        lte_ns = _to_ns(ts)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            nbbos = list(ex.map(lambda c: nbbo_at(client, c[0], gte_ns, lte_ns), kept))
        quotes = [
            {"expiry": exp.isoformat(), "strike": float(strike), "cp": cp,
             "bid": n["bid"], "ask": n["ask"], "size": n["size"]}
            for (occ, exp, strike, cp), n in zip(kept, nbbos) if n is not None
        ]
        spot = _spot(quotes, ts, ticker) if quotes else None
        part[key] = None if spot is None else {"ts": key, "spot": float(spot), "quotes": quotes}
        with open(part_path, "w", encoding="utf-8") as fh:
            json.dump(part, fh)
        print(f"  {key}: {len(quotes)} quotes"
              + ("" if spot is None else f", spot={spot:.2f}")
              + f"  ({_time.perf_counter() - t0:.0f}s)")

    snapshots = [part[ts.isoformat()] for ts in sorted(instants)
                 if part.get(ts.isoformat()) is not None]
    if os.path.exists(part_path):
        os.remove(part_path)
    if not snapshots:
        return None
    return {
        "asset": ticker,
        "day": day.isoformat(),
        "exercise_style": "american",
        "source": "rest",
        "expiries": sorted(e.isoformat() for e in keep),
        "snapshots": snapshots,
    }


def run(
    start: date, end: date, tickers=UNIVERSE_0DTE,
    times: tuple[time, ...] = DEFAULT_TIMES,
    db_path: str | None = None, force: bool = False,
    workers: int = DEFAULT_WORKERS,
    client: httpx.Client | None = None,
    daily_window: float = DAILY_WINDOW,
    anchor_window: float = ANCHOR_WINDOW,
) -> list[str]:
    """Capture the window via REST; returns fixture paths written (resumable)."""
    if client is None:
        api_key = os.environ.get("VOLFIT_MASSIVE_KEY", "")
        if not api_key:
            raise SystemExit("no Massive API key (dot-source restart.local.ps1)")
        client = httpx.Client(
            base_url=os.environ.get("VOLFIT_MASSIVE_HOST", DEFAULT_HOST),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(20.0, read=30.0),
            limits=httpx.Limits(max_connections=workers + 4),
        )
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    written: list[str] = []
    day = start
    while day <= end:
        if not is_trading_day(day):
            day += timedelta(days=1)
            continue
        for ticker in tickers:
            path = os.path.join(FIXTURE_DIR, f"{ticker}_{day.isoformat()}.json")
            if os.path.exists(path) and not force:
                print(f"{ticker} {day}: exists, skipped")
                continue
            t0 = _time.perf_counter()
            doc = None
            for attempt in (1, 2):
                try:
                    doc = capture_day_rest(client, ticker, day, times, workers,
                                           daily_window, anchor_window)
                    break
                except Exception as exc:  # noqa: BLE001 — outages happen; checkpoint kept
                    print(f"{ticker} {day}: attempt {attempt} failed: {exc}")
            if doc is None:
                print(f"{ticker} {day}: no usable quotes")
                continue
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=1)
            written.append(path)
            n_db = _persist_db(db_path, ticker, doc) if db_path else 0
            n_q = sum(len(s["quotes"]) for s in doc["snapshots"])
            print(
                f"{ticker} {day}: {len(doc['snapshots'])} snapshots, {n_q} quotes, "
                f"{len(doc['expiries'])} expiries"
                + (f", {n_db} -> {db_path}" if db_path else "")
                + f"  ({_time.perf_counter() - t0:.0f}s)"
            )
        day += timedelta(days=1)
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description="Intraday 0DTE capture via Massive REST.")
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--tickers", default=",".join(UNIVERSE_0DTE))
    ap.add_argument("--times", default=None,
                    help="comma-separated ET wall times (default 10:00..15:45)")
    ap.add_argument("--db", default=None,
                    help="also write snapshots into this VolStore (app replay)")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--daily-window", type=float, default=DAILY_WINDOW,
                    help="moneyness window for the daily ladder (frac of close)")
    ap.add_argument("--anchor-window", type=float, default=ANCHOR_WINDOW,
                    help="moneyness window for the term anchors (frac of close)")
    args = ap.parse_args()
    written = run(
        args.start, args.end,
        tickers=tuple(t.strip().upper() for t in args.tickers.split(",")),
        times=_parse_times(args.times),
        db_path=args.db, force=args.force, workers=args.workers,
        daily_window=args.daily_window, anchor_window=args.anchor_window,
    )
    print(f"wrote {len(written)} fixture file(s) under {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
