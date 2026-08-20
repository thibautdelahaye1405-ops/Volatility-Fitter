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

#: ``--step`` grid defaults (V3.8 replay campaign): 09:45 ET (past the opening
#: auction) to 15:45 ET (the daily capture's before-close instant).
GRID_FROM = time(9, 45)
GRID_TO = time(15, 45)

#: ``--ladder term`` shape: the DAILY capture's term-structure ladder
#: (capture.py: MIN/MAX_DTE 7/400, 10 expiries, 3 front weeklies) adapted to
#: the intraday horizon — front weeklies + third-Friday monthlies out to
#: TERM_MAX_DTE, capped at the TERM_MAX_EXPIRIES nearest. Same-day expiries
#: are excluded (the intraday replay drops 0DTE rungs anyway: calendar t = 0
#: in the graph clock — see graph_intraday.instant_state).
TERM_MAX_DTE = 120
TERM_MAX_EXPIRIES = 6
TERM_FRONT_WEEKLIES = 3


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


def select_expiries_term(available: set[date], day: date) -> list[date]:
    """``--ladder term``: all in-range monthlies (1 <= DTE <= TERM_MAX_DTE)
    plus the nearest TERM_FRONT_WEEKLIES non-monthly expiries, capped at the
    TERM_MAX_EXPIRIES nearest overall — capture.py's daily selection shape on
    the intraday ``select_expiries`` signature. 0DTE is deliberately excluded
    (see the TERM_* constants note)."""
    cand = sorted(e for e in available if 1 <= (e - day).days <= TERM_MAX_DTE)
    monthlies = [e for e in cand if _is_monthly(e)]
    chosen = set(monthlies)
    for e in (e for e in cand if not _is_monthly(e)):
        if len(chosen) >= len(monthlies) + TERM_FRONT_WEEKLIES:
            break
        chosen.add(e)
    return sorted(chosen)[:TERM_MAX_EXPIRIES]


#: --ladder name -> selector. "0dte" IS select_expiries (default, byte-identical).
LADDERS = {"0dte": select_expiries, "term": select_expiries_term}


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
    ladder: str = "0dte",
) -> dict | None:
    """All of one (asset, day)'s intraday snapshots as a fixture document.

    One flat-file scan (``chains_at``); the expiry ladder (``LADDERS[ladder]``)
    is selected from the board actually present in the file. None when the day
    yields no usable snapshot (e.g. a file gap)."""
    instants = session_instants(day, times)
    if not instants:
        return None
    chains = store.chains_at(ticker, None, instants)
    usable = {ts: ch for ts, ch in chains.items() if ch is not None}
    if not usable:
        return None
    board = {q.expiry for ch in usable.values() for q in ch.quotes}
    keep = set(LADDERS[ladder](board, day))
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
    from volfit.data.types import US_OPTION_TICK, ChainSnapshot, OptionQuote

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
                # Captured chains are REAL NBBO (flat files or REST), so stamp
                # the tick like every live provider does — without it the
                # 3-tick OTM band floor is disabled and cent-level lottery
                # quotes masquerade as tight IV bands (seen on QQQ 9-DTE
                # +16% calls quoted 0.01/0.03 in the 2026-07 campaign).
                tick_size=US_OPTION_TICK,
                settlement=settlement_map(expiries, root=ticker),
            ))
            n += 1
    return n


def run(
    start: date, end: date, tickers=UNIVERSE_0DTE,
    times: tuple[time, ...] = DEFAULT_TIMES,
    db_path: str | None = None, force: bool = False,
    store: QuotesFlatFileStore | None = None,
    ladder: str = "0dte",
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
                    doc = capture_day(store, ticker, day, times, ladder)
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


def grid_times(step_min: int, t_from: time = GRID_FROM, t_to: time = GRID_TO) -> tuple[time, ...]:
    """Regular ET wall-time grid ``t_from..t_to`` INCLUSIVE every ``step_min``
    minutes (the V3.8 15-minute campaign grid). ``session_instants`` still
    clips at the session close, so half-days keep only surviving instants."""
    if step_min <= 0:
        raise ValueError("--step must be a positive number of minutes")
    anchor = date(2000, 1, 3)  # any fixed day: only the wall times survive
    cur, end = datetime.combine(anchor, t_from), datetime.combine(anchor, t_to)
    out: list[time] = []
    while cur <= end:
        out.append(cur.time())
        cur += timedelta(minutes=step_min)
    return tuple(out)


def resolve_times(times: str | None, step: int | None,
                  t_from: str | None, t_to: str | None) -> tuple[time, ...]:
    """Shared CLI grid resolution for BOTH capture twins: ``--times`` XOR
    ``--step [--from --to]``; neither given = DEFAULT_TIMES (the legacy grid,
    byte-identical)."""
    if step is not None and times:
        raise SystemExit("--times and --step are mutually exclusive")
    if step is None:
        if t_from or t_to:
            raise SystemExit("--from/--to require --step")
        return _parse_times(times)
    return grid_times(step,
                      time.fromisoformat(t_from) if t_from else GRID_FROM,
                      time.fromisoformat(t_to) if t_to else GRID_TO)


def add_grid_args(ap: argparse.ArgumentParser) -> None:
    """The shared --times/--step/--from/--to/--ladder CLI block (both twins)."""
    ap.add_argument("--times", default=None,
                    help="comma-separated ET wall times (default 10:00..15:45)")
    ap.add_argument("--step", type=int, default=None,
                    help="regular grid in minutes (e.g. 15); excludes --times")
    ap.add_argument("--from", dest="grid_from", default=None, metavar="HH:MM",
                    help="grid start, ET wall time (default 09:45; needs --step)")
    ap.add_argument("--to", dest="grid_to", default=None, metavar="HH:MM",
                    help="grid end, ET wall time (default 15:45; needs --step)")
    ap.add_argument("--ladder", choices=tuple(LADDERS), default="0dte",
                    help="expiry ladder: 0dte (dailies + 2 monthly anchors, the"
                         " default) or term (front weeklies + monthlies to"
                         f" {TERM_MAX_DTE} DTE, capped at {TERM_MAX_EXPIRIES})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Intraday 0DTE flat-file capture.")
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--tickers", default=",".join(UNIVERSE_0DTE))
    add_grid_args(ap)
    ap.add_argument("--db", default=None,
                    help="also write snapshots into this VolStore (app replay)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    written = run(
        args.start, args.end,
        tickers=tuple(t.strip().upper() for t in args.tickers.split(",")),
        times=resolve_times(args.times, args.step, args.grid_from, args.grid_to),
        db_path=args.db, force=args.force, ladder=args.ladder,
    )
    print(f"wrote {len(written)} fixture file(s) under {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
