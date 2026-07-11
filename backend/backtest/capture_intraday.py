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

Run (flat-file creds in env — dot-source restart.local.ps1 first; the scan is
quota-bound and takes minutes per day, so full campaigns belong in the USER'S
window):

    python -m backtest.capture_intraday --start 2026-07-06 --end 2026-07-10
    python -m backtest.capture_intraday --start ... --db backtest/results/intraday.sqlite
"""

from __future__ import annotations

import argparse
import json
import os
import time as _time
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from volfit.data.expiry_time import is_trading_day, session_close, settlement_map

from backtest.quotes_store import QuotesFlatFileStore

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

ROOT = os.path.dirname(__file__)
FIXTURE_DIR = os.path.join(ROOT, "fixtures", "intraday")
CACHE_DIR = os.path.join(ROOT, "_cache")

#: The 0DTE pilot universe (roadmap: research grade, no index-feed spend).
#: ETF options: root == ticker, American exercise.
UNIVERSE_0DTE = ("SPY", "QQQ", "IWM")

#: Expiry ladder kept per day: every expiry within MAX_DAILY_DTE calendar days
#: (the 0DTE/daily structure under study) plus up to TERM_ANCHORS third-Friday
#: monthlies within TERM_ANCHOR_MAX_DTE (the term/calendar anchor the fits and
#: the graph need). Everything else on the OPRA board is dropped.
MAX_DAILY_DTE = 7
TERM_ANCHORS = 2
TERM_ANCHOR_MAX_DTE = 90

#: Default intraday sampling: every 30 minutes from 10:00 ET (past the opening
#: auction noise) to 15:30, plus the 15:45 before-close instant the daily
#: capture uses (so the two campaigns share a comparable end-of-day point).
DEFAULT_TIMES = tuple(
    time(h, m) for h in range(10, 16) for m in (0, 30) if not (h == 15 and m == 30)
) + (time(15, 30), time(15, 45))


def _is_monthly(e: date) -> bool:
    return e.weekday() == 4 and 15 <= e.day <= 21


def select_expiries(available: set[date], day: date) -> list[date]:
    """The kept ladder: dailies (DTE <= MAX_DAILY_DTE) + nearby monthlies."""
    dailies = [e for e in available if 0 <= (e - day).days <= MAX_DAILY_DTE]
    monthlies = sorted(
        e for e in available
        if _is_monthly(e) and MAX_DAILY_DTE < (e - day).days <= TERM_ANCHOR_MAX_DTE
    )[:TERM_ANCHORS]
    return sorted(set(dailies) | set(monthlies))


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


def capture_day(
    store: QuotesFlatFileStore,
    ticker: str,
    day: date,
    times: tuple[time, ...] = DEFAULT_TIMES,
) -> dict | None:
    """All of one (asset, day)'s intraday snapshots as a fixture document.

    One flat-file scan (``chains_at``); the expiry ladder is selected from the
    board actually present in the file. None when the day yields no usable
    snapshot (e.g. a file gap)."""
    instants = session_instants(day, times)
    if not instants:
        return None
    chains = store.chains_at(ticker, None, instants)
    usable = {ts: ch for ts, ch in chains.items() if ch is not None}
    if not usable:
        return None
    board = {q.expiry for ch in usable.values() for q in ch.quotes}
    keep = set(select_expiries(board, day))
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
    return {
        "asset": ticker,
        "day": day.isoformat(),
        "exercise_style": "american",
        "expiries": sorted(e.isoformat() for e in keep),
        "snapshots": snapshots,
    }


def _persist_db(db_path: str, ticker: str, doc: dict) -> int:
    """Write the day's snapshots into a VolStore (app as-of 'captured' replay).

    Each snapshot carries the per-expiry settlement map, so the intraday
    variance clock prices these chains exactly on replay."""
    from volfit.data.store import VolStore
    from volfit.data.types import ChainSnapshot, OptionQuote

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
                exercise_style="american",
                settlement=settlement_map(expiries, root=ticker),
            ))
            n += 1
    return n


def run(
    start: date, end: date, tickers=UNIVERSE_0DTE,
    times: tuple[time, ...] = DEFAULT_TIMES,
    db_path: str | None = None, force: bool = False,
    store: QuotesFlatFileStore | None = None,
) -> list[str]:
    """Capture the window; returns the fixture paths written (resumable)."""
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
                    doc = capture_day(store, ticker, day, times)
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


def _parse_times(raw: str | None) -> tuple[time, ...]:
    if not raw:
        return DEFAULT_TIMES
    return tuple(time.fromisoformat(part.strip()) for part in raw.split(","))


def main() -> int:
    ap = argparse.ArgumentParser(description="Intraday 0DTE flat-file capture.")
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--tickers", default=",".join(UNIVERSE_0DTE))
    ap.add_argument("--times", default=None,
                    help="comma-separated ET wall times (default 10:00..15:45)")
    ap.add_argument("--db", default=None,
                    help="also write snapshots into this VolStore (app replay)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    written = run(
        args.start, args.end,
        tickers=tuple(t.strip().upper() for t in args.tickers.split(",")),
        times=_parse_times(args.times),
        db_path=args.db, force=args.force,
    )
    print(f"wrote {len(written)} fixture file(s) under {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
