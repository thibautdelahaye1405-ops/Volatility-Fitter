"""Re-persist intraday fixture JSONs into a VolStore — no network (V3.8 item 6).

The intraday captures write two artifacts: the JSON fixture (the immutable
record) and, optionally, VolStore snapshots (the app/replay input). Before this
module, rebuilding a replay DB from existing fixtures meant re-hitting the
network. This CLI closes that gap: it pushes fixture documents through the
SAME ``capture_intraday._persist_db`` writer, so the per-expiry settlement map
and the ``US_OPTION_TICK`` stamp — both load-bearing on replay (the intraday
variance clock; the OTM band floor that caught the QQQ cent-lottery quotes) —
are preserved exactly.

Idempotent: snapshots already stored at the same (ticker, instant) are deleted
first, so re-loading OVERWRITES rather than duplicates.

Run (offline; any fixture written by capture_intraday or capture_intraday_rest)::

    python -m backtest.load_fixtures --db backtest/results/replay_day.sqlite \
        backtest/fixtures/intraday/SPY_2026-07-10.json ...
"""

from __future__ import annotations

import argparse
import glob
import json

from volfit.data.store import VolStore

from backtest.capture_intraday import _persist_db


def _delete_existing(db_path: str, ticker: str, iso_instants: list[str]) -> int:
    """Drop stored snapshots (and their quotes) at the fixture's instants.

    ``ts`` is persisted as ``datetime.isoformat()`` and the fixture's
    ``snap["ts"]`` is the same string ``_persist_db`` round-trips through
    ``datetime.fromisoformat(...).isoformat()``, so string equality is exact.
    """
    n = 0
    with VolStore(db_path) as vs:
        for iso in iso_instants:
            ids = [int(r[0]) for r in vs.conn.execute(
                "SELECT id FROM snapshots WHERE ticker = ? AND ts = ?", (ticker, iso)
            )]
            for sid in ids:
                vs.conn.execute("DELETE FROM quotes WHERE snapshot_id = ?", (sid,))
                vs.conn.execute("DELETE FROM snapshots WHERE id = ?", (sid,))
            n += len(ids)
        vs.conn.commit()
    return n


def load_fixture_file(db_path: str, path: str) -> tuple[str, int]:
    """One fixture JSON -> VolStore snapshots; returns (ticker, snapshots)."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if "asset" not in doc or "snapshots" not in doc:
        raise SystemExit(f"{path}: not an intraday fixture (missing asset/snapshots)")
    ticker = doc["asset"]
    _delete_existing(db_path, ticker, [s["ts"] for s in doc["snapshots"]])
    return ticker, _persist_db(db_path, ticker, doc)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Re-persist intraday fixture JSONs into a VolStore (offline)."
    )
    ap.add_argument("--db", required=True, help="target VolStore path")
    ap.add_argument("fixtures", nargs="+",
                    help="fixture JSON path(s); globs are expanded")
    args = ap.parse_args()
    paths = [p for pat in args.fixtures for p in (sorted(glob.glob(pat)) or [pat])]
    total = 0
    for path in paths:
        ticker, n = load_fixture_file(args.db, path)
        total += n
        print(f"{ticker}: {n} snapshot(s) <- {path}")
    print(f"loaded {total} snapshot(s) into {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
