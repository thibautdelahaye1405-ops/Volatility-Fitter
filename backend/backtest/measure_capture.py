"""One-off measurement: scan a single real quotes_v1 day for the pilot watchlist
and report cost (scan wall-time, cache size) + per-asset reconstruction, so we can
size the 20-day capture before committing to it. Also confirms index coverage
(SPX/SPXW etc.). Run with flat-file creds in the env (dot-source restart.local.ps1).
"""

from __future__ import annotations

import os
import time
from datetime import datetime

from backtest.quotes_store import QuotesFlatFileStore

# 15:45 ET on the Aug-5-2024 spike day (EDT = UTC-4 → 19:45 UTC).
TS = datetime(2024, 8, 5, 19, 45, 0)

# Pilot universe: display ticker → (option roots, exercise style).
ASSETS = {
    "SPX": (["SPX", "SPXW"], "european"),
    "NDX": (["NDX", "NDXP"], "european"),
    "RUT": (["RUT", "RUTW"], "european"),
    "EEM": (["EEM"], "american"),
    "EFA": (["EFA"], "american"),
    "AAPL": (["AAPL"], "american"),
    "NVDA": (["NVDA"], "american"),
    "JPM": (["JPM"], "american"),
}
ALL_ROOTS = sorted({r for roots, _ in ASSETS.values() for r in roots})


def main() -> int:
    cache = os.path.join(os.path.dirname(__file__), "_cache")
    store = QuotesFlatFileStore(
        access_key=os.environ["VOLFIT_FLATFILES_KEY"],
        secret=os.environ["VOLFIT_FLATFILES_SECRET"],
        endpoint=os.environ.get("VOLFIT_FLATFILES_ENDPOINT", "files.massive.com"),
        cache_dir=cache,
    )
    print(f"scanning quotes_v1 {TS.date()} for {ALL_ROOTS} ...", flush=True)
    t0 = time.perf_counter()
    chains = {}
    for tk, (roots, style) in ASSETS.items():
        chains[tk] = store.chain_at(
            tk, None, TS, option_roots=roots, cache_roots=ALL_ROOTS, exercise_style=style
        )
        dt = time.perf_counter() - t0
        ch = chains[tk]
        if ch is None:
            print(f"  {tk:5s} NONE                                   (+{dt:6.1f}s)", flush=True)
            continue
        twosided = sum(1 for q in ch.quotes if q.mid is not None)
        print(
            f"  {tk:5s} spot={ch.spot:9.2f}  quotes={len(ch.quotes):5d} "
            f"({twosided} 2-sided)  expiries={len(ch.expiries())}  (+{dt:6.1f}s)",
            flush=True,
        )
    # cache size
    parquet = [f for f in os.listdir(cache) if f.endswith(".parquet")] if os.path.isdir(cache) else []
    mb = sum(os.path.getsize(os.path.join(cache, f)) for f in parquet) / 1e6
    print(f"\ntotal {time.perf_counter() - t0:.1f}s, cache {mb:.1f} MB across {len(parquet)} parquet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
