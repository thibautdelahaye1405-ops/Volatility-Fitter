"""Validate the intraday variance clock on captured REAL 0DTE chains.

The acceptance step of the R2 item-10 capture campaign: load snapshots from
a ``capture_intraday[_rest] --db`` VolStore, serve each through a
StoredChains provider (the replay pattern), and calibrate every expiry with
``intradayClock`` ON. The 0DTE node must price with a SUB-DAY maturity (the
legacy day-granular clock gives it t = 0 — unrepresentable) and produce a
finite, sane LQD fit.

Two modes (no credentials needed — everything is in the store):

    # one snapshot, full per-node table
    python -m backtest.validate_intraday_clock --db backtest\\results\\intraday.sqlite \
        --ticker SPY --ts 2026-07-10T16:30:00

    # the whole campaign: every captured (ticker, day), a few instants each
    python -m backtest.validate_intraday_clock --db backtest\\results\\intraday.sqlite \
        --per-day 3
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime

from volfit.api import service
from volfit.api.state import AppState
from volfit.data.store import VolStore
from volfit.replay_report import _StoredChains

#: A node fails when the model IV escapes a quote's bid-ask BAND by this many
#: bp. Judged band-relative deliberately: on early-session short-dated chains
#: the mid is a weak observable (the first sweep read |model - mid| up to
#: 578 bp INSIDE 1,200 bp-wide bands — wide markets, not bad fits), so a raw
#: mid-error bar flags honest data. A fit pinned through the band by vol
#: points is broken; a fit inside wide bands is not.
BAND_EXCESS_BP = 250.0


def _band_excess_bp(record, prepared) -> float:
    """Worst distance (bp of IV) the fitted slice escapes any quote's bid-ask
    band — 0 when the model threads every band. The band-space acceptance
    metric; |model - mid| stays a printed diagnostic only."""
    import numpy as np

    tau = float(prepared.tau)
    k = np.asarray(prepared.k, dtype=float)
    model = np.array([float(record.result.slice.implied_vol(float(x), tau)) for x in k])
    below = np.asarray(prepared.iv_bid) - model
    above = model - np.asarray(prepared.iv_ask)
    return float(max(0.0, np.max(np.maximum(below, above))) * 1e4)


def validate_snapshot(snap, ticker: str) -> tuple[int, list[str], float | None]:
    """Calibrate every expiry of one stored snapshot with the intraday clock ON.

    Returns (failures, per-node report lines, worst max-IV-error in bp)."""
    state = AppState(snap.timestamp.date(), provider=_StoredChains({ticker: snap}))
    # Select the FULL captured ladder explicitly: the default selection rule
    # seeds only strictly-future expiries (days > 0, expiry_select.py), which
    # silently drops the same-day rung — the very 0DTE node under validation.
    # (In the app the user reaches it via the "0dte" filter chip; replay must
    # validate what was captured, not what the live seed would pick.)
    state.set_expiries(ticker, sorted(snap.expiries()))
    state.set_options(state.options().model_copy(update={"intradayClock": True}))
    failures = 0
    lines: list[str] = []
    worst: float | None = None
    parity = state.forwards(ticker)
    for expiry in sorted(snap.expiries()):
        iso = expiry.isoformat()
        if expiry not in parity:
            # A near-settle 0DTE chain can legitimately lose every two-sided
            # pair (one-sided near-intrinsic quotes): no parity forward = the
            # node is unfittable DATA, quarantined calmly — not a clock/fit
            # failure. Surfaced so a suspicious pattern on far nodes shows up.
            lines.append(f"  {iso}: SKIPPED (no parity forward - thin/one-sided chain)")
            continue
        legacy_days = state.year_fraction(expiry) * 365.0  # day-granular reference
        try:
            prepared = service.prepared_quotes(state, ticker, expiry)
            record = service.calibrate_node(state, ticker, iso, "mid")
            err = float(record.result.max_iv_error) * 1e4
            excess = _band_excess_bp(record, prepared)
            note = "" if excess < BAND_EXCESS_BP else "  <-- UNSTABLE"
            failures += int(excess >= BAND_EXCESS_BP)
            worst = err if worst is None else max(worst, err)
            lines.append(
                f"  {iso}: t={float(prepared.t)*365:8.4f}d "
                f"tau={float(prepared.tau)*365:8.4f}d legacy={legacy_days:5.1f}d "
                f"nQ={prepared.k.size:3d} maxIvErr={err:7.1f}bp "
                f"bandExc={excess:6.1f}bp{note}"
            )
        except Exception as exc:  # noqa: BLE001 — report, keep validating the rest
            failures += 1
            lines.append(f"  {iso}: FAILED ({exc})")
    return failures, lines, worst


def validate(db_path: str, ticker: str, ts: datetime) -> int:
    """Single-snapshot mode: the full per-node table for one instant."""
    with VolStore(db_path) as vs:
        snap = vs.snapshot_at(ticker, ts)
    if snap is None:
        raise SystemExit(f"no captured snapshot for {ticker!r} at or before {ts}")
    print(
        f"snapshot ts={snap.timestamp} spot={snap.spot:.2f} "
        f"quotes={len(snap.quotes)} settlement={'yes' if snap.settlement else 'MISSING'}"
    )
    failures, lines, _worst = validate_snapshot(snap, ticker)
    print("\n".join(lines))
    print("VALIDATION " + ("OK" if failures == 0 else f"FAILED ({failures} node(s))"))
    return 0 if failures == 0 else 1


def pick_instants(timestamps: list[datetime], per_day: int) -> list[datetime]:
    """Evenly spread ``per_day`` instants over one day's sorted snapshots
    (always includes the first and last; 0 or >= n means all of them)."""
    ts = sorted(timestamps)
    n = len(ts)
    if per_day <= 0 or per_day >= n:
        return ts
    if per_day == 1:
        return [ts[-1]]
    idx = {round(i * (n - 1) / (per_day - 1)) for i in range(per_day)}
    return [ts[i] for i in sorted(idx)]


def validate_all(db_path: str, tickers: list[str] | None, per_day: int) -> int:
    """Sweep mode: every captured (ticker, day), ``per_day`` instants each.

    One summary line per validated snapshot; per-node detail only on failure."""
    with VolStore(db_path) as vs:
        listed = vs.list_snapshots(tickers or None)
        by_day: dict[tuple[str, date], list[datetime]] = defaultdict(list)
        for ticker, _sid, ts in listed:
            by_day[(ticker, ts.date())].append(ts)
        total_snaps = total_failures = 0
        for (ticker, day), stamps in sorted(by_day.items()):
            for ts in pick_instants(stamps, per_day):
                snap = vs.snapshot_at(ticker, ts)
                failures, lines, worst = validate_snapshot(snap, ticker)
                total_snaps += 1
                total_failures += failures
                status = "ok" if failures == 0 else f"FAILED ({failures})"
                worst_txt = "n/a" if worst is None else f"{worst:.1f}bp"
                print(f"{ticker} {ts}: {len(lines)} nodes, worst {worst_txt} - {status}")
                if failures:
                    print("\n".join(lines))
    print(
        f"CAMPAIGN VALIDATION {'OK' if total_failures == 0 else 'FAILED'} "
        f"({total_snaps} snapshots, {total_failures} failing node(s))"
    )
    return 0 if total_failures == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--ticker", default=None,
                    help="single ticker (with --ts) or comma list to restrict the sweep")
    ap.add_argument("--ts", default=None, type=datetime.fromisoformat,
                    help="UTC-naive instant, e.g. 2026-07-10T16:30:00 (12:30 ET in EDT); "
                         "omit to sweep every captured (ticker, day)")
    ap.add_argument("--per-day", type=int, default=3,
                    help="sweep mode: instants validated per day (0 = all; default 3)")
    args = ap.parse_args()
    if args.ts is not None:
        if not args.ticker or "," in args.ticker:
            raise SystemExit("--ts needs a single --ticker")
        return validate(args.db, args.ticker.upper(), args.ts)
    tickers = (
        [t.strip().upper() for t in args.ticker.split(",")] if args.ticker else None
    )
    return validate_all(args.db, tickers, args.per_day)


if __name__ == "__main__":
    raise SystemExit(main())
