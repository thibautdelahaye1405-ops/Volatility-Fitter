"""Validate the intraday variance clock on captured REAL 0DTE chains.

The acceptance step of the R2 item-10 capture campaign: load snapshots from
a ``capture_intraday --db`` VolStore, serve each through a StoredChains
provider (the replay pattern), and calibrate every expiry with
``intradayClock`` ON. The 0DTE node must price with a SUB-DAY maturity (the
legacy day-granular clock gives it t = 0 — unrepresentable) and produce a
finite, sane LQD fit; the printed table shows exact-vs-legacy clocks and the
fit error per node.

Run (after a capture; no credentials needed — everything is in the store):

    python -m backtest.validate_intraday_clock --db backtest\\results\\intraday.sqlite \
        --ticker SPY --ts 2026-07-10T16:30:00
"""

from __future__ import annotations

import argparse
from datetime import datetime

from volfit.api import service
from volfit.api.state import AppState
from volfit.data.store import VolStore
from volfit.replay_report import _StoredChains


def validate(db_path: str, ticker: str, ts: datetime) -> int:
    with VolStore(db_path) as vs:
        snap = vs.snapshot_at(ticker, ts)
    if snap is None:
        raise SystemExit(f"no captured snapshot for {ticker!r} at or before {ts}")
    print(
        f"snapshot ts={snap.timestamp} spot={snap.spot:.2f} "
        f"quotes={len(snap.quotes)} settlement={'yes' if snap.settlement else 'MISSING'}"
    )
    state = AppState(snap.timestamp.date(), provider=_StoredChains({ticker: snap}))
    state.set_options(state.options().model_copy(update={"intradayClock": True}))
    failures = 0
    for expiry in sorted(snap.expiries()):
        iso = expiry.isoformat()
        legacy_days = state.year_fraction(expiry) * 365.0  # day-granular reference
        try:
            prepared = service.prepared_quotes(state, ticker, expiry)
            record = service.calibrate_node(state, ticker, iso, "mid")
            err = float(record.result.max_iv_error) * 1e4
            note = "" if err < 500.0 else "  <-- UNSTABLE"
            failures += int(err >= 500.0)
            print(
                f"  {iso}: t={float(prepared.t)*365:8.4f}d "
                f"tau={float(prepared.tau)*365:8.4f}d legacy={legacy_days:5.1f}d "
                f"nQ={prepared.k.size:3d} maxIvErr={err:7.1f}bp{note}"
            )
        except Exception as exc:  # noqa: BLE001 — report, keep validating the rest
            failures += 1
            print(f"  {iso}: FAILED ({exc})")
    print("VALIDATION " + ("OK" if failures == 0 else f"FAILED ({failures} node(s))"))
    return 0 if failures == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--ticker", default="SPY")
    ap.add_argument("--ts", required=True, type=datetime.fromisoformat,
                    help="UTC-naive instant, e.g. 2026-07-10T16:30:00 (12:30 ET in EDT)")
    args = ap.parse_args()
    return validate(args.db, args.ticker.upper(), args.ts)


if __name__ == "__main__":
    raise SystemExit(main())
