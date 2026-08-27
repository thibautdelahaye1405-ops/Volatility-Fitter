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

Multi-root discovery (V3.8 rider): an index needs several OCC roots — SPX is
``SPX`` (AM-settled monthlies) plus ``SPXW`` (PM-settled weeklies/EOM). The
roots come from ``backtest.roots`` (``--roots`` override, else the universe
registry, else the ticker itself — SPY/QQQ/IWM byte-identical). Each root is
queried on its own ``underlying_ticker``, the boards are unioned (deduped by
OCC symbol) and every contract keeps its root, so the settlement stamp is per
CONTRACT root: a Monday SPXW expiry is "pm" while the SPX monthly stays "am"
(the ROADMAP known issue of ``default_settlement(e, root="SPX")``). Same-date
collisions follow ``backtest.roots``' first-listed-root policy; multi-root
fixtures carry a ``meta`` block (``roots``, ``expiryRoots``, and
``rootCollisions`` only when some were dropped). Index closes come from the
``I:<ticker>`` aggregate, falling back to the bare ticker.

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
from volfit.data.occ import underlying_of
from volfit.data.types import OptionQuote

from backtest.capture_intraday import (
    DEFAULT_TIMES,
    FIXTURE_DIR,
    LADDERS,
    MAX_DAILY_DTE,
    TERM_ANCHOR_MAX_DTE,
    TERM_MAX_DTE,
    UNIVERSE_0DTE,
    _persist_db,
    add_grid_args,
    add_roots_arg,
    resolve_times,
    roots_override_from_args,
    session_instants,
)
from backtest.intraday_rest_http import (  # noqa: F401 — day_close/nbbo_at re-exported
    DEFAULT_HOST,
    _paged,
    day_close,
    nbbo_at,
)
from backtest.quotes_store import _parity_spot, _to_ns
from backtest.roots import exercise_style_for, resolve_expiry_roots, root_meta, roots_for

ET = ZoneInfo("America/New_York")

#: Moneyness windows for contract discovery (fraction of the day's close).
DAILY_WINDOW = 0.10
ANCHOR_WINDOW = 0.25

#: Concurrent quote requests. The paid tiers are not request-limited; 429s
#: are still honored with backoff (intraday_rest_http._get).
DEFAULT_WORKERS = 12


def discover_contracts(
    client: httpx.Client, ticker: str, day: date, close: float,
    daily_window: float = DAILY_WINDOW, anchor_window: float = ANCHOR_WINDOW,
    anchor_max_dte: int = TERM_ANCHOR_MAX_DTE,
    roots: tuple[str, ...] | None = None,
) -> dict[str, tuple[date, float, str, str]]:
    """OCC ticker -> (expiry, strike, C/P, root) for the day's board, windowed.

    Two spans: the daily ladder (DTE <= MAX_DAILY_DTE, tight window) and the
    term span (wider window, out to ``anchor_max_dte`` — the default covers
    the 0DTE anchors; ``--ladder term`` extends it to TERM_MAX_DTE). Both
    ``expired`` flags are queried — the dailies have expired by capture time,
    the anchors may still be live — and deduped by OCC ticker.

    ``roots`` (default ``(ticker,)``, the single-root query) are the OCC roots
    queried as ``underlying_ticker`` in turn; the union is returned and each
    contract carries its root (parsed from the OCC symbol, else the query
    root). Same-date collisions are NOT resolved here (see capture_day_rest).
    """
    spans = (
        (day, day + timedelta(days=MAX_DAILY_DTE), daily_window),
        (day + timedelta(days=MAX_DAILY_DTE + 1),
         day + timedelta(days=anchor_max_dte), anchor_window),
    )
    out: dict[str, tuple[date, float, str, str]] = {}
    for root in roots or (ticker,):
        for lo, hi, window in spans:
            for expired in ("true", "false"):
                params = {
                    "underlying_ticker": root,
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
                    parsed = underlying_of(row["ticker"])
                    # Tag with the caller's spelling of the root when the OCC
                    # symbol agrees (case-insensitively), else the parsed root.
                    tag = root if not parsed or parsed == root.upper() else parsed
                    out[row["ticker"]] = (
                        date.fromisoformat(row["expiration_date"]),
                        float(row["strike_price"]),
                        cp,
                        tag,
                    )
    return out


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
    ladder: str = "0dte",
    roots_override: dict[str, tuple[str, ...]] | None = None,
) -> dict | None:
    """One (asset, day)'s intraday snapshots via REST — the fixture document.

    Progress is checkpointed per instant into ``<fixture>.part.json`` so an
    interrupted day resumes at the next instant, not from scratch.
    ``roots_override`` is the parsed ``--roots`` map (see backtest.roots).
    """
    instants = session_instants(day, times)
    if not instants:
        return None
    roots = roots_for(ticker, roots_override)
    style = exercise_style_for(ticker, roots_override)
    close = day_close(client, ticker, day,
                      (f"I:{ticker}", ticker) if style == "european" else (ticker,))
    contracts = discover_contracts(
        client, ticker, day, close, daily_window, anchor_window,
        anchor_max_dte=TERM_MAX_DTE if ladder == "term" else TERM_ANCHOR_MAX_DTE,
        roots=roots,
    )
    # Same-date collision policy: the first-listed root owns each expiry date.
    expiry_root, collisions = resolve_expiry_roots(
        {r: {c[0] for c in contracts.values() if c[3] == r} for r in roots}, roots)
    keep = set(LADDERS[ladder](set(expiry_root), day))
    kept = sorted(
        (occ, exp, strike, cp)
        for occ, (exp, strike, cp, root) in contracts.items()
        if exp in keep and expiry_root[exp] == root
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
    doc = {
        "asset": ticker,
        "day": day.isoformat(),
        "exercise_style": style,
        "source": "rest",
        "expiries": sorted(e.isoformat() for e in keep),
        "snapshots": snapshots,
    }
    meta = root_meta(
        ticker, roots, {e: r for e, r in expiry_root.items() if e in keep},
        [c for c in collisions if date.fromisoformat(c["expiry"]) in keep],
    )
    if meta:  # multi-root captures only: single-root fixtures keep their key set
        doc["meta"] = meta
    return doc


def run(
    start: date, end: date, tickers=UNIVERSE_0DTE,
    times: tuple[time, ...] = DEFAULT_TIMES,
    db_path: str | None = None, force: bool = False,
    workers: int = DEFAULT_WORKERS,
    client: httpx.Client | None = None,
    daily_window: float = DAILY_WINDOW,
    anchor_window: float = ANCHOR_WINDOW,
    ladder: str = "0dte",
    roots_override: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    """Capture the window via REST; returns fixture paths written (resumable).
    ``roots_override`` (ticker -> OCC roots) bypasses the universe registry."""
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
                                           daily_window, anchor_window, ladder,
                                           roots_override=roots_override)
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
    add_grid_args(ap)
    ap.add_argument("--db", default=None,
                    help="also write snapshots into this VolStore (app replay)")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--daily-window", type=float, default=DAILY_WINDOW,
                    help="moneyness window for the daily ladder (frac of close)")
    ap.add_argument("--anchor-window", type=float, default=ANCHOR_WINDOW,
                    help="moneyness window for the term anchors (frac of close)")
    add_roots_arg(ap)
    args = ap.parse_args()
    written = run(
        args.start, args.end,
        tickers=tuple(t.strip().upper() for t in args.tickers.split(",")),
        times=resolve_times(args.times, args.step, args.grid_from, args.grid_to),
        db_path=args.db, force=args.force, workers=args.workers,
        daily_window=args.daily_window, anchor_window=args.anchor_window,
        ladder=args.ladder, roots_override=roots_override_from_args(args),
    )
    print(f"wrote {len(written)} fixture file(s) under {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
