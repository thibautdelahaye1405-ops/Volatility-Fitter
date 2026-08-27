"""Intraday 0DTE capture — SPY/QQQ/IWM chains at several instants per day
(roadmap R2 item 10, the research-grade 0DTE data campaign).

The daily capture (``backtest.capture``) freezes ONE 15:45-ET snapshot per
(asset, day) and deliberately excludes sub-week expiries (MIN_DTE = 7). The
0DTE work needs the opposite: the SAME day observed at many instants through
the session, with the daily ladder (0-7 DTE) plus a couple of monthlies for
term anchoring. This module reconstructs those chains from the ``quotes_v1``
flat files via ``QuotesFlatFileStore.chains_at`` — ONE firehose scan per day
however many instants — and writes:

  * one JSON fixture per (asset, day) under ``backtest/fixtures/intraday/``
    (all snapshots of the day; resumable — existing files are skipped);
  * optionally (``--db``) every snapshot into a VolStore, WITH the per-expiry
    settlement map, so the app replays them via the As-of selector
    ("captured") and the intraday variance clock prices real 0DTE chains.

Multi-root indices (V3.8 rider): ``backtest.roots`` resolves each ticker's
OCC roots (``--roots`` override, else the universe registry: SPX = SPX + SPXW,
else the ticker itself — the SPY/QQQ/IWM path is byte-identical). A
multi-root day is reconstructed ONCE PER ROOT (``chains_at`` with
``option_roots=[root]``; all calls share one cached scan through
``cache_roots``) and merged per instant, because the store's OptionQuote
keeps only the display ticker — the per-root split is what lets the
settlement stamp follow the CONTRACT root (SPXW Monday = "pm", SPX monthly =
"am"). Same-date collisions use the first-listed-root policy; multi-root
fixtures carry a ``meta`` block (``roots``, ``expiryRoots``, and
``rootCollisions`` only when some were dropped). Cross-ticker co-caching is
deliberately NOT enabled (it would change the pilot path's cache keys).

Run (flat-file creds in env — dot-source restart.local.ps1 first; the scan is
quota-bound and takes minutes per day, so full campaigns belong in the USER'S
window):

    python -m backtest.capture_intraday --start 2026-07-06 --end 2026-07-10
    python -m backtest.capture_intraday --start ... --db backtest/results/intraday.sqlite
    python -m backtest.capture_intraday --start ... --tickers SPX --roots 'SPX=SPX,SPXW'
"""

from __future__ import annotations

import argparse
import json
import os
import time as _time
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from volfit.data.expiry_time import (
    default_settlement,
    is_trading_day,
    session_close,
    settlement_map,
)
from volfit.data.types import US_OPTION_TICK, ChainSnapshot, OptionQuote

from backtest.intraday_cli import (  # noqa: F401 — re-exported (both twins + tests)
    DEFAULT_TIMES,
    GRID_FROM,
    GRID_TO,
    add_grid_args,
    add_roots_arg,
    grid_times,
    resolve_times,
    roots_override_from_args,
)
from backtest.intraday_ladder import (  # noqa: F401 — re-exported (both twins + tests)
    LADDERS,
    MAX_DAILY_DTE,
    TERM_ANCHOR_MAX_DTE,
    TERM_ANCHORS,
    TERM_FRONT_WEEKLIES,
    TERM_MAX_DTE,
    TERM_MAX_EXPIRIES,
    _is_monthly,
    select_expiries,
    select_expiries_term,
)
from backtest.quotes_store import QuotesFlatFileStore, _parity_spot
from backtest.roots import exercise_style_for, resolve_expiry_roots, root_meta, roots_for

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

ROOT = os.path.dirname(__file__)
FIXTURE_DIR = os.path.join(ROOT, "fixtures", "intraday")
CACHE_DIR = os.path.join(ROOT, "_cache")

#: The 0DTE pilot universe (roadmap: research grade, no index-feed spend).
#: ETF options: root == ticker, American exercise. Indices (SPX/NDX/RUT) are
#: capturable too — ``--tickers SPX`` resolves its roots from the registry —
#: but stay out of the default basket (a user-window run).
UNIVERSE_0DTE = ("SPY", "QQQ", "IWM")


def session_instants(day: date, times: tuple[time, ...] = DEFAULT_TIMES) -> list[datetime]:
    """ET wall times -> UTC-naive instants, clipped to the session close (a
    half-day keeps only instants at or before its 13:00 close)."""
    close = session_close(day)
    out = []
    for t in times:
        if t > close:
            continue
        aware = datetime.combine(day, t, tzinfo=ET)
        out.append(aware.astimezone(UTC).replace(tzinfo=None))
    return out


def _quote_dict(q) -> dict:
    return {
        "expiry": q.expiry.isoformat(),
        "strike": float(q.strike),
        "cp": q.call_put,
        "bid": None if q.bid is None else float(q.bid),
        "ask": None if q.ask is None else float(q.ask),
        "size": None if q.open_interest is None else int(q.open_interest),
    }


def _merge_root_chains(
    store: QuotesFlatFileStore, ticker: str, roots: tuple[str, ...],
    instants: list[datetime], style: str,
) -> tuple[dict[datetime, ChainSnapshot], dict[date, str], list[dict]]:
    """Multi-root reconstruction: ``chains_at`` once PER ROOT (one shared cached
    scan via ``cache_roots``), merged per instant under the same-date collision
    policy so every quote's root is known. Returns the usable snapshots, the
    expiry -> root map and the collisions."""
    per_root = {
        r: store.chains_at(ticker, None, instants, option_roots=[r],
                           cache_roots=list(roots), exercise_style=style)
        for r in roots
    }
    boards = {
        r: {q.expiry for ch in chains.values() if ch is not None for q in ch.quotes}
        for r, chains in per_root.items()
    }
    expiry_root, collisions = resolve_expiry_roots(boards, roots)
    usable: dict[datetime, ChainSnapshot] = {}
    for ts in instants:
        quotes: list[OptionQuote] = []
        for r in roots:
            ch = per_root[r].get(ts)
            if ch is not None:
                quotes += [q for q in ch.quotes if expiry_root[q.expiry] == r]
        spot = _parity_spot(quotes) if quotes else None
        if spot is not None:
            usable[ts] = ChainSnapshot(
                ticker=ticker.upper(), spot=spot, timestamp=ts, quotes=quotes,
                exercise_style=style, tick_size=US_OPTION_TICK,
            )
    return usable, expiry_root, collisions


def capture_day(
    store: QuotesFlatFileStore,
    ticker: str,
    day: date,
    times: tuple[time, ...] = DEFAULT_TIMES,
    ladder: str = "0dte",
    roots_override: dict[str, tuple[str, ...]] | None = None,
) -> dict | None:
    """All of one (asset, day)'s intraday snapshots as a fixture document.

    One flat-file scan (``chains_at``); the expiry ladder (``LADDERS[ladder]``)
    is selected from the board actually present in the file. None when the day
    yields no usable snapshot (e.g. a file gap). ``roots_override`` is the
    parsed ``--roots`` map (see backtest.roots)."""
    instants = session_instants(day, times)
    if not instants:
        return None
    roots = roots_for(ticker, roots_override)
    style = exercise_style_for(ticker, roots_override)
    if len(roots) == 1:  # the pilot path: one call, byte-identical
        chains = store.chains_at(ticker, None, instants, option_roots=list(roots),
                                 exercise_style=style)
        usable = {ts: ch for ts, ch in chains.items() if ch is not None}
        board = {q.expiry for ch in usable.values() for q in ch.quotes}
        expiry_root, collisions = {e: roots[0] for e in board}, []
    else:
        usable, expiry_root, collisions = _merge_root_chains(
            store, ticker, roots, instants, style)
    if not usable:
        return None
    keep = set(LADDERS[ladder](set(expiry_root), day))
    snapshots = []
    for ts in sorted(usable):
        ch = usable[ts]
        quotes = [q for q in ch.quotes if q.expiry in keep]
        if not quotes:
            continue
        snapshots.append({
            "ts": ts.isoformat(),
            "spot": float(ch.spot),
            "quotes": [_quote_dict(q) for q in quotes],
        })
    if not snapshots:
        return None
    doc = {
        "asset": ticker,
        "day": day.isoformat(),
        "exercise_style": style,
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


def _doc_settlement(doc: dict, ticker: str, expiries: set[date]) -> dict:
    """The snapshot's settlement map: per CONTRACT root when the fixture's
    ``meta.expiryRoots`` says which root listed each expiry (an SPXW Monday is
    "pm", the SPX monthly "am"), else the legacy per-ticker rule."""
    expiry_roots = (doc.get("meta") or {}).get("expiryRoots") or {}
    if not expiry_roots:
        return settlement_map(expiries, root=ticker)
    return {e: default_settlement(e, expiry_roots.get(e.isoformat(), ticker))
            for e in sorted(expiries)}


def _persist_db(db_path: str, ticker: str, doc: dict) -> int:
    """Write the day's snapshots into a VolStore (app as-of 'captured' replay).

    Each snapshot carries the per-expiry settlement map, so the intraday
    variance clock prices these chains exactly on replay."""
    from volfit.data.store import VolStore

    style = doc.get("exercise_style", "american")
    n = 0
    with VolStore(db_path) as vs:
        for snap in doc["snapshots"]:
            ts = datetime.fromisoformat(snap["ts"])
            quotes = [
                OptionQuote(
                    ticker=ticker, expiry=date.fromisoformat(q["expiry"]),
                    strike=q["strike"], call_put=q["cp"], bid=q["bid"],
                    ask=q["ask"], last=None, volume=None,
                    open_interest=q["size"], timestamp=ts,
                )
                for q in snap["quotes"]
            ]
            expiries = {q.expiry for q in quotes}
            vs.save_snapshot(ChainSnapshot(
                ticker=ticker, spot=snap["spot"], timestamp=ts, quotes=quotes,
                exercise_style=style,
                # Captured chains are REAL NBBO (flat files or REST), so stamp
                # the tick like every live provider does — without it the
                # 3-tick OTM band floor is disabled and cent-level lottery
                # quotes masquerade as tight IV bands (seen on QQQ 9-DTE
                # +16% calls quoted 0.01/0.03 in the 2026-07 campaign).
                tick_size=US_OPTION_TICK,
                settlement=_doc_settlement(doc, ticker, expiries),
            ))
            n += 1
    return n


def run(
    start: date, end: date, tickers=UNIVERSE_0DTE,
    times: tuple[time, ...] = DEFAULT_TIMES,
    db_path: str | None = None, force: bool = False,
    store: QuotesFlatFileStore | None = None,
    ladder: str = "0dte",
    roots_override: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    """Capture the window; returns the fixture paths written (resumable).
    ``roots_override`` (ticker -> OCC roots) bypasses the universe registry."""
    if store is None:
        store = QuotesFlatFileStore(
            access_key=os.environ.get("VOLFIT_FLATFILES_KEY", ""),
            secret=os.environ.get("VOLFIT_FLATFILES_SECRET", ""),
            endpoint=os.environ.get("VOLFIT_FLATFILES_ENDPOINT", "files.massive.com"),
            cache_dir=CACHE_DIR,
        )
    if not store.available():
        raise SystemExit("no flat-file credentials (dot-source restart.local.ps1)")
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
                    doc = capture_day(store, ticker, day, times, ladder,
                                      roots_override=roots_override)
                    break
                except Exception as exc:  # noqa: BLE001 — network stalls happen
                    print(f"{ticker} {day}: attempt {attempt} failed: {exc}")
            if doc is None:
                print(f"{ticker} {day}: no usable quotes (file gap / network?)")
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
    ap = argparse.ArgumentParser(description="Intraday 0DTE flat-file capture.")
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--tickers", default=",".join(UNIVERSE_0DTE))
    add_grid_args(ap)
    add_roots_arg(ap)
    ap.add_argument("--db", default=None,
                    help="also write snapshots into this VolStore (app replay)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    written = run(
        args.start, args.end,
        tickers=tuple(t.strip().upper() for t in args.tickers.split(",")),
        times=resolve_times(args.times, args.step, args.grid_from, args.grid_to),
        db_path=args.db, force=args.force, ladder=args.ladder,
        roots_override=roots_override_from_args(args),
    )
    print(f"wrote {len(written)} fixture file(s) under {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
