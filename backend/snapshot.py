"""One-command universe snapshot: fetch option chains into the SQLite store.

This is the ROADMAP Phase 3 exit-criterion command — "one command snapshots a
universe from Yahoo into storage".  For each ticker it fetches the chain via
the chosen provider, persists it with VolStore.save_snapshot, then implies
per-expiry forwards (put-call parity regression) and prints a compact report.

Usage (from the repo root, Windows):

    # Live Yahoo snapshot of SPY and QQQ into the default db
    ..\\.venv\\Scripts\\python backend\\snapshot.py SPY QQQ

    # Explicit db path, more expiries
    .venv\\Scripts\\python backend\\snapshot.py SPY QQQ AAPL ^
        --db backend\\data\\snapshots.sqlite --max-expiries 12

    # Offline smoke test against the deterministic synthetic provider
    .venv\\Scripts\\python backend\\snapshot.py ALPHA --provider synthetic

Exit code is 1 only if *every* ticker failed; partial failures are reported
on stderr and the run continues.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from volfit.data import VolStore, implied_forwards
from volfit.data.provider import OptionChainProvider, SyntheticProvider
from volfit.data.yahoo import YahooProvider

#: Default store location: backend/data/snapshots.sqlite next to this script.
DEFAULT_DB = Path(__file__).resolve().parent / "data" / "snapshots.sqlite"


def build_provider(name: str, tickers: list[str], max_expiries: int) -> OptionChainProvider:
    """Construct the requested provider over the CLI ticker list."""
    if name == "yahoo":
        return YahooProvider(tickers, max_expiries=max_expiries)
    return SyntheticProvider(reference_date=date.today(), tickers=tuple(tickers))


def snapshot_ticker(store: VolStore, provider: OptionChainProvider, ticker: str) -> None:
    """Fetch, persist and report one ticker (exceptions propagate to main)."""
    chain = provider.fetch_chain(ticker)
    snapshot_id = store.save_snapshot(chain)
    # Reference the observation date so American chains are de-biased (parity
    # from de-Americanized mids; data.forwards). European chains are identical.
    forwards = implied_forwards(chain, chain.timestamp.date())
    print(
        f"{ticker}: spot {chain.spot:.2f}, {len(chain.quotes)} quotes, "
        f"{len(chain.expiries())} expiries -> snapshot #{snapshot_id}"
    )
    for expiry in sorted(forwards):
        fwd = forwards[expiry]
        print(
            f"  {expiry.isoformat()}  F={fwd.forward:10.4f}  D={fwd.discount:.4f}  "
            f"pairs={fwd.n_strikes:3d}  rms={fwd.residual_rms:.4g}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="snapshot",
        description="Snapshot option chains for a list of tickers into SQLite.",
    )
    parser.add_argument("tickers", nargs="+", help="underlying tickers, e.g. SPY QQQ")
    parser.add_argument(
        "--db", default=str(DEFAULT_DB), help=f"SQLite path (default {DEFAULT_DB})"
    )
    parser.add_argument(
        "--provider", choices=("yahoo", "synthetic"), default="yahoo",
        help="market-data source (default yahoo; synthetic is offline)",
    )
    parser.add_argument(
        "--max-expiries", type=int, default=8,
        help="keep at most this many near expiries per chain (yahoo only)",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    provider = build_provider(args.provider, args.tickers, args.max_expiries)

    failures = 0
    with VolStore(db_path) as store:
        for ticker in args.tickers:
            try:
                snapshot_ticker(store, provider, ticker)
            except Exception as exc:
                failures += 1
                print(f"{ticker}: ERROR: {exc}", file=sys.stderr)
    return 1 if failures == len(args.tickers) else 0


if __name__ == "__main__":
    raise SystemExit(main())
