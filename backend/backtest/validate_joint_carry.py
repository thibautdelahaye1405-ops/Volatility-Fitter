"""Joint-carry validation on REAL HTB chains (R2 item 11 increment 4).

The item's two remaining exit gates, run against a captured VolStore (a
GME/AMC-class REST capture — names where borrow is a live market fact):

  * STABILITY — "known HTB names recover stably": the joint borrow read per
    (ticker, expiry) should agree across the day's instants and across days
    far more tightly than its level (a 500 bp borrow that wanders 400 bp
    between 10:00 and 15:45 is a broken read; wandering 30 bp is a market).

  * HELD-OUT PARITY — "held-out parity error improves vs implicit forward":
    per (ticker, expiry, instant), fit the carry on the EVEN-indexed strike
    pairs only, then score the ODD pairs' parity residuals
    |C_eur - P_eur - D (F - K)| where the European reprices use each
    candidate's own carry. Candidates: the v0/implicit read (raw-parity
    forward, lumped carry) vs the joint fixed point. The joint solve should
    price the strikes it never saw better, because its de-Americanized
    sides join consistently.

Run (after a capture; no credentials needed)::

    python -m backtest.validate_joint_carry --db backtest/results/htb.sqlite

VERDICT ON THE 2026-07 CAPTURE (GME + the four highest short-interest
optionable names TTAN/WGS/UAA/PLAY, 3 days x 3 instants, recorded rather
than tuned away):

  * the identifiability floor works — every 1-3 DTE weekly read (swinging
    -2,572 to +15,827 bp before the gate) is correctly skipped: t*b there
    is sub-bp of forward, unidentifiable by physics;
  * GME (median 75 bp) and TTAN Aug (-33 bp) read STABLE within their
    floors; WGS monthlies wander 1.3-2.4x the allowance — part floor
    optimism (the sigma_b ~ rms/(t sqrt(n)) formula ignores regression
    leverage on F, easily 1.5-2x), part genuine borrow volatility on a
    97%-shorted name (deam failures appear exactly there);
  * WGS's reads are consistently NEGATIVE-signed: a flat desk rate biases
    the borrow read one-for-one (100 bp of rate error = -100 bp of
    "borrow"), so borrow validation NEEDS a term-matched rate curve —
    a genuine item-11 dependency this gate surfaced;
  * held-out parity: joint 11/25 vs implicit — INCONCLUSIVE, as the
    joint-vs-lumped de-Am difference (26 bp synthetic on flat carry) sits
    far below these boards' 20-80 bp-of-spot quote noise.

The gate therefore stays OPEN pending (a) a desk rate curve input and
(b) a LIQUID hard-to-borrow episode (TSLA-class) where the de-Am edge
exceeds quote noise; the fixed point's correctness itself is locked
synthetically in tests/test_carry_solve.py where the market is exact.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date

import numpy as np

from volfit.core.american import binomial_price_batch, deamericanize_batch
from volfit.data.carry_solve import (
    BISECTIONS,
    MIN_PAIRS,
    N_STEPS,
    _paired_mids,
    _parity_fit,
    joint_borrow,
)
from volfit.data.store import VolStore
from volfit.data.types import ChainSnapshot


def _subset_chain(snap: ChainSnapshot, expiry: date, keep: np.ndarray) -> ChainSnapshot:
    """The chain restricted to one expiry's KEPT strikes (the training half)."""
    strikes, _c, _p = _paired_mids(snap, expiry)
    kept = set(strikes[keep])
    quotes = [q for q in snap.quotes_for(expiry) if q.strike in kept]
    return ChainSnapshot(snap.ticker, snap.spot, snap.timestamp, quotes,
                         snap.exercise_style, tick_size=snap.tick_size)


def _heldout_residual_bp(
    snap: ChainSnapshot, expiry: date, ref: date, rate: float,
    holdout: np.ndarray, forward: float, discount: float, borrow: float,
) -> float | None:
    """RMS parity residual (bp of spot) on the HELD-OUT pairs, de-Am'd and
    repriced European at the candidate carry (rate, borrow)."""
    t = (expiry - ref).days / 365.0
    strikes, c_mid, p_mid = _paired_mids(snap, expiry)
    k = strikes[holdout]
    if k.size == 0 or t <= 0.0:
        return None
    mids = np.concatenate([c_mid[holdout], p_mid[holdout]])
    is_call = np.concatenate([np.ones(k.size, bool), np.zeros(k.size, bool)])
    kk = np.concatenate([k, k])
    s = float(snap.spot)
    sigma = deamericanize_batch(is_call, mids, s, kk, t, r=rate, q=borrow,
                                n_steps=N_STEPS, bisections=BISECTIONS)
    good = np.isfinite(sigma)
    ok = good[: k.size] & good[k.size:]
    if int(ok.sum()) < 3:
        return None
    eur = binomial_price_batch(is_call, s, kk, t, np.where(good, sigma, 0.2),
                               r=rate, q=borrow, n_steps=N_STEPS, american=False)
    resid = (eur[: k.size] - eur[k.size:]) - discount * (forward - k)
    return float(np.sqrt(np.mean(resid[ok] ** 2)) / s * 1e4)


def _implicit_read(snap, expiry, ref, rate):
    """The v0/implicit candidate on the SAME training data: raw-parity
    regression (lumped carry — borrow rides inside F, the tree sees q from
    the implied carry, mirroring production's lumped-q de-Am)."""
    strikes, c_mid, p_mid = _paired_mids(snap, expiry)
    forward, discount = _parity_fit(strikes, c_mid - p_mid)
    t = (expiry - ref).days / 365.0
    if not np.isfinite(forward) or forward <= 0.0 or t <= 0.0:
        return None
    q_lumped = rate - float(np.log(forward / snap.spot)) / t
    return forward, discount, q_lumped


def validate(db_path: str, rate: float, max_floor_bp: float = 250.0) -> int:
    with VolStore(db_path) as vs:
        listed = vs.list_snapshots(None)
        borrows: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
        wins = losses = skipped = 0
        rows: list[str] = []
        for ticker, sid, ts in sorted(listed, key=lambda r: (r[0], r[2])):
            snap = vs.load_snapshot(sid)
            ref = ts.date()
            for expiry in sorted(snap.expiries()):
                strikes, c_mid, p_mid = _paired_mids(snap, expiry)
                if strikes.size < 2 * MIN_PAIRS:
                    continue  # need a training AND a held-out half
                t = (expiry - ref).days / 365.0
                if t <= 0.0:
                    continue
                # IDENTIFIABILITY floor: parity noise propagates to the borrow
                # read as sigma_b ~ (rms/spot)/(t sqrt(n)) — a 1-3 DTE weekly
                # cannot pin borrow no matter how hard it is to locate (t*b is
                # sub-bp of forward), and wide-spread boards cannot either.
                # Below the floor the read is legitimately UNIDENTIFIED (the
                # CarryCurve philosophy); it is skipped, not judged.
                _f0, _d0 = _parity_fit(strikes, c_mid - p_mid)
                resid = (c_mid - p_mid) - (_f0 * _d0 - _d0 * strikes)
                rms_frac = float(np.sqrt(np.mean(resid**2))) / float(snap.spot)
                floor_bp = rms_frac / (t * np.sqrt(strikes.size)) * 1e4
                if floor_bp > max_floor_bp:
                    skipped += 1
                    continue
                train = np.arange(strikes.size) % 2 == 0
                hold = ~train
                sub = _subset_chain(snap, expiry, train)
                joint = joint_borrow(sub, expiry, ref, rate)
                implicit = _implicit_read(sub, expiry, ref, rate)
                if joint is None or not joint.converged or implicit is None:
                    continue
                f_i, d_i, q_i = implicit
                err_joint = _heldout_residual_bp(
                    snap, expiry, ref, rate, hold,
                    joint.forward, joint.discount, joint.borrow_bp / 1e4)
                err_impl = _heldout_residual_bp(
                    snap, expiry, ref, rate, hold, f_i, d_i, q_i)
                if err_joint is None or err_impl is None:
                    continue
                borrows[(ticker, expiry.isoformat())].append(
                    (joint.borrow_bp, floor_bp))
                wins += int(err_joint <= err_impl)
                losses += int(err_joint > err_impl)
                rows.append(
                    f"  {ticker} {ts} {expiry}: borrow {joint.borrow_bp:7.1f}bp "
                    f"(noise floor {floor_bp:5.1f}bp, iters {joint.iterations}, "
                    f"fails {joint.deam_failures})  held-out parity joint "
                    f"{err_joint:6.2f} vs implicit {err_impl:6.2f} bp-of-spot"
                )
    print("\n".join(rows))
    print(f"\n({skipped} node-instants below the identifiability floor "
          f"[sigma_b > {max_floor_bp:.0f}bp] — legitimately UNIDENTIFIED, "
          "not judged)")
    print("\nBorrow stability across instants/days (per node, judged in "
          "noise-floor units):")
    unstable = 0
    for (ticker, iso), vals in sorted(borrows.items()):
        arr = np.array([v for v, _ in vals])
        floors = np.array([f for _, f in vals])
        spread = float(arr.max() - arr.min())
        level = float(np.median(arr))
        # Consistent-within-noise: reads may wander by their combined noise
        # floors (4 sigma of the pairwise difference) without being broken.
        allowed = 4.0 * float(np.sqrt(2.0)) * float(np.median(floors))
        ok = spread <= max(allowed, 0.25 * max(abs(level), 100.0))
        unstable += int(not ok)
        print(f"  {ticker} {iso}: median {level:7.1f}bp  range {spread:6.1f}bp "
              f"(allowed {allowed:5.1f}) over {arr.size} reads  "
              f"{'ok' if ok else '<-- UNSTABLE'}")
    total = wins + losses
    print(f"\nHeld-out parity (identifiable nodes only): joint wins {wins}/{total}")
    verdict = total > 0 and wins * 2 >= total and unstable == 0
    print("JOINT-CARRY VALIDATION " + ("OK" if verdict else "FAILED"))
    return 0 if verdict else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--rate", type=float, default=0.04,
                    help="flat desk rate for the theoretical leg")
    ap.add_argument("--max-floor-bp", type=float, default=250.0,
                    help="identifiability bar: skip nodes whose propagated "
                         "borrow-noise floor exceeds this many bp")
    args = ap.parse_args()
    return validate(args.db, args.rate, args.max_floor_bp)


if __name__ == "__main__":
    raise SystemExit(main())
