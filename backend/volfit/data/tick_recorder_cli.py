"""The tick recorder's commands (TICK RECORDER, 2026-09-24; the loop is
volfit.data.tick_recorder):

    python -m volfit.data.tick_recorder record --tickers SPY,NVDA
        [--expiries all|monthly|weekly|<csv>] [--out DIR] [--store VOLFIT_DB]
        [--frame-minutes 1] [--interval 1.0] [--cap 950] [--connections 1] [--no-rest]
    … replay --db ticks_YYYY-MM-DD.sqlite --ticker SPY --at 2026-09-24T15:45:00
        [--expiries …] [--store VOLFIT_DB]        the chain at an instant, saved like a frame
    … status [--out DIR | --db FILE]              the recorder's meta (pid, heartbeat, acked, frames)
    … stop   [--out DIR | --db FILE] [--grace 15] a clean stop through the store, the pid as fallback

WHY ``stop`` goes through the store: a detached Windows process has no
Ctrl-C to receive and ``TerminateProcess`` skips the final fold and the
stream teardown; the recorder polls the ``stop`` meta key every tick and
shuts down cleanly, and only a recorder that does not answer within the
grace is killed by the pid it recorded.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from volfit.data.tick_recorder import (
    DEFAULT_OUT,
    STOP_KEY,
    Recorder,
    provider_from_env,
    resolve_expiries,
    save_frame,
    select_expiries,
)
from volfit.data.tick_store import TickStore, daily_path
from volfit.data.types import ChainSnapshot

log = logging.getLogger("volfit.tick_recorder")



def replay(db, ticker: str, at: datetime, rule: str = "all", store_path=None, provider=None) -> ChainSnapshot:
    """The ticker's chain at ``at`` from the recorded ticks (``book_at``),
    built through the provider's own book read over a frozen book, saved like
    a frame when ``store_path`` is given. ``provider`` is injectable (tests)."""
    from volfit.data.massive_recorded import StaticBook

    with TickStore(db) as store:
        quotes = store.book_at(at)
    prov = provider or provider_from_env([ticker])
    exps = select_expiries(prov.available_expiries(ticker), rule)
    prov.use_recorded_book(StaticBook(quotes))
    prov.start_streaming([])
    try:
        chain = prov.live_chain(ticker, exps)
    finally:
        prov.stop_streaming()
    if chain is None:
        raise SystemExit(f"{ticker}: no booked quote at {at.isoformat()} in {db}")
    frame = replace(chain, timestamp=at, quotes=[q for q in chain.quotes if q.bid is not None or q.ask is not None])
    sid = save_frame(store_path, frame, exps) if store_path else None
    print(f"{ticker} @ {at.isoformat()}: {len(frame.quotes)} quotes over {len(frame.expiries())} expiries, "
          f"spot {frame.spot:.2f}" + (f", saved as snapshot #{sid} in {store_path}" if sid else ""))
    return frame


def _db_of(args) -> Path:
    return Path(args.db) if getattr(args, "db", None) else daily_path(args.out)


def status_lines(db) -> list[str]:
    """The recorder's meta as printable lines."""
    path = Path(db)
    if not path.is_file():
        return [f"no tick store at {path}"]
    with TickStore(path) as store:
        meta, stats = store.meta(), store.stats() or {}
        age = store.heartbeat_age_s()
        lines = [
            f"store      {path}",
            f"pid        {meta.get('pid')}  started {meta.get('startedAt')}  stopped {meta.get('stoppedAt') or '-'}",
            f"heartbeat  {'never' if age is None else f'{age:.0f} s ago'}",
            f"stream     {stats.get('level')} · {stats.get('detail')}",
            f"acked      {stats.get('acknowledged')} / subscribed {stats.get('subscribed')} / over cap {stats.get('overCap')} / refused {stats.get('refused')}",
            f"per ticker {json.dumps(stats.get('ackedByTicker'))}",
            f"book       {store.latest_count()} contracts · {store.tick_count()} ticks · newest {store.newest_ts_ns()}",
            f"frames     {stats.get('framesSaved')} saved · plan {json.dumps(store.plan() or {}, default=str)[:200]}",
        ]
    return lines


def stop_recorder(db, grace_s: float = 15.0) -> bool:
    """Ask the recorder to stop (the ``stop`` meta key it polls every tick),
    wait up to ``grace_s`` for its ``stoppedAt``, then kill the pid."""
    path = Path(db)
    if not path.is_file():
        print(f"no tick store at {path}")
        return False
    with TickStore(path) as store:
        pid = store.get_meta("pid")
        store.set_meta(STOP_KEY, "1")
        deadline = time.time() + grace_s
        while time.time() < deadline:
            if store.get_meta("stoppedAt") is not None:
                print(f"recorder (pid {pid}) stopped cleanly")
                return True
            time.sleep(0.5)
    if pid:
        try:
            os.kill(int(pid), signal.SIGTERM)
            print(f"recorder (pid {pid}) killed after {grace_s:.0f} s without a clean stop")
            return True
        except (ProcessLookupError, PermissionError, ValueError, OSError) as exc:
            print(f"recorder (pid {pid}) not killed: {exc}")
    return False


def _log_setup() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    logging.getLogger("volfit.massive_ws").setLevel(logging.INFO)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m volfit.data.tick_recorder", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="own the socket, record the book, save frames")
    rec.add_argument("--tickers", required=True, help="comma-separated, e.g. SPY,NVDA")
    rec.add_argument("--expiries", default="all", help="all | monthly | weekly | csv of ISO dates")
    rec.add_argument("--out", default=str(DEFAULT_OUT), help="tick directory (daily files)")
    rec.add_argument("--store", default=os.environ.get("VOLFIT_DB") or None, help="the app's VolStore for frames")
    rec.add_argument("--frame-minutes", type=int, default=1)
    rec.add_argument("--interval", type=float, default=1.0)
    rec.add_argument("--cap", type=int, default=None)
    rec.add_argument("--connections", type=int, default=None)
    rec.add_argument("--no-rest", action="store_true", help="no per-minute REST memory (wings unquoted)")
    rep = sub.add_parser("replay", help="the chain at an instant from the ticks")
    rep.add_argument("--db", required=True)
    rep.add_argument("--ticker", required=True)
    rep.add_argument("--at", required=True, help="UTC instant, ISO 8601")
    rep.add_argument("--expiries", default="all")
    rep.add_argument("--store", default=os.environ.get("VOLFIT_DB") or None)
    for name in ("status", "stop"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--db", default=None)
        cmd.add_argument("--out", default=str(DEFAULT_OUT))
        if name == "stop":
            cmd.add_argument("--grace", type=float, default=15.0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _log_setup()
    if args.cmd == "record":
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        prov = provider_from_env(tickers, cap=args.cap, connections=args.connections)
        rec = Recorder(
            prov, resolve_expiries(prov, tickers, args.expiries), args.out, store_path=args.store,
            frame_minutes=args.frame_minutes, interval=args.interval, rest_memory=not args.no_rest,
        )
        for sig in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGBREAK", signal.SIGINT)):
            signal.signal(sig, lambda *_: rec.stop.set())
        rec.run()
        return 0
    if args.cmd == "replay":
        replay(args.db, args.ticker.upper(), datetime.fromisoformat(args.at), args.expiries, args.store)
        return 0
    if args.cmd == "status":
        print("\n".join(status_lines(_db_of(args))))
        return 0
    return 0 if stop_recorder(_db_of(args), args.grace) else 1


__all__ = ["main", "replay", "status_lines", "stop_recorder"]


if __name__ == "__main__":
    sys.exit(main())
