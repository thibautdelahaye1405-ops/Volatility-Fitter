"""Intraday observation-filter tuning (R2 item 10, temporal-filter phase).

The Note 15 filter's process-noise clock was tuned on DAILY snapshot pairs
(``observation_filter.py``, the 3-regime sweep that set 30 bp/sqrt-day). The
0DTE campaign store has 13 instants/day x 8 days x SPY/QQQ/IWM — enough to
ask, on real data: does sqrt(calendar-dt) hold at 30-minute steps and across
overnights, or does variance accrue on the SESSION clock
(volfit.calib.intraday_time — an in-session hour carries far more variance
than a closed-market hour)?

Two phases, because the fits are the expensive part and the Kalman core is
microseconds:

  --build  one data-only LQD measurement per (ticker, expiry, instant) —
           handles z, diag R (Jacobian route), forward, tau — written to
           results/intraday_filter/<TICKER>_<day>.json (resumable per
           ticker-day, ~40 fits each);
  --sweep  replay the PURE filter core over the table for every
           (clock, process-bp) config; score per STEP TYPE (intraday ~30 min /
           overnight / weekend):
             * zeta = innovation / sqrt(diag(P^- + R)) BEFORE adaptive
               inflation — std(zeta) ~ 1 iff Q is scaled right at that
               cadence (THE tuning verdict);
             * next-snapshot held-out: |m^- - z_next| (filter prediction) vs
               |transport(z_prev) - z_next| (raw persistence, no filter);
             * adaptive-inflation trip rate (|zeta| > gate).

Clocks are (session_share, nontrading_weight) pairs fed to the PRODUCTION
``intraday_variance_days`` — (6.5/24, 1.0) reproduces the calendar clock the
app layer uses today, so a winning research clock maps 1:1 onto existing
machinery. Transport uses SSR = 1.0 for both the filter and the persistence
baseline (neutral for the comparison; h is the realized log-forward move).

Run (store from the capture campaign)::

    python -m backtest.observation_filter_intraday --build \
        --db backtest/results/intraday.sqlite
    python -m backtest.observation_filter_intraday --sweep
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import date, datetime

import numpy as np

from volfit.calib.intraday_time import UNIFORM_SESSION_SHARE, intraday_variance_days
from volfit.calib.observation_filter import (
    adaptive_inflation,
    kalman_update,
    predict,
    process_noise,
    transport_handles,
)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "intraday_filter")

#: Step-type buckets by calendar gap (hours). Steps past RESET_HOURS are
#: dropped — production reseeds there (OptionsSettings.filterResetHours=96).
STEP_TYPES = (("intraday", 1.0), ("overnight", 24.0), ("weekend", 96.0))

#: The sweep grid. Clocks: production calendar first, then session-weighted
#: research clocks (share = fraction of a day's variance inside the 6.5h
#: session; nontrading_weight = a closed day's worth of variance).
CLOCKS = (
    ("calendar", UNIFORM_SESSION_SHARE, 1.0),
    ("session50", 0.50, 0.10),
    ("session60", 0.60, 0.10),
    ("session60w0", 0.60, 0.0),
    ("session70", 0.70, 0.10),
    ("session85", 0.85, 0.25),
)
PROCESS_BPS = (30.0, 60.0, 90.0, 120.0, 180.0)
SIGMA_GATE = 3.0  # production filterAdaptiveSigma default — part of the system


# ------------------------------------------------------------------- build
def _pick_expiries(snap) -> list[date]:
    """Stable within-day nodes: the farthest daily (<= 7d) + both monthlies."""
    day = snap.timestamp.date()
    expiries = sorted(snap.expiries())
    dailies = [e for e in expiries if (e - day).days <= 7]
    anchors = [e for e in expiries if (e - day).days > 7]
    picked = dailies[-1:] + anchors[:2]
    return sorted(set(picked))


def _measure(state, ticker: str, expiry: date):
    """One data-only LQD measurement: (z, diag R, F, tau) or None on failure."""
    from volfit.api import service
    from volfit.calib.observation_measurement import (
        handle_jacobian_fd,
        measurement_from_jacobian,
    )
    from volfit.calib.precision import RMS_FLOOR
    from volfit.models.lqd.atm import atm_handles
    from volfit.models.lqd.basis import LQDParams
    from volfit.models.lqd.quadrature import build_slice

    from backtest.observation_filter import _fit_data_only, _handles

    prepared = service.prepared_quotes(state, ticker, expiry)
    if prepared.k.size < 5:
        return None
    fd: dict = {}
    result = _fit_data_only(prepared.k, prepared.w_mid, prepared.tau, solver_diag=fd)
    z = _handles(result, prepared.tau)

    def handle_fn(theta):
        h = atm_handles(build_slice(LQDParams.from_vector(theta)), prepared.tau)
        return np.array([h.sigma0, h.skew, h.curvature])

    half = np.maximum(
        (np.asarray(prepared.iv_ask) - np.asarray(prepared.iv_bid)) / 2.0, RMS_FLOOR
    )
    noise = half if half.size == fd["n_quotes"] else float(np.median(half))
    g = handle_jacobian_fd(handle_fn, fd["theta"])
    m = measurement_from_jacobian(
        z, fd["jac"], g, fd["residual"], fd["n_fit_rows"], fd["n_quotes"],
        noise_scale=noise,
    )
    return {
        "z": [float(v) for v in z],
        "r_diag": [float(v) for v in np.diag(m.cov)],
        "forward": float(prepared.forward),
        "tau": float(prepared.tau),
    }


def build(db_path: str, tickers: list[str]) -> None:
    """The measurement table, one JSON per (ticker, day); existing files skip."""
    from volfit.api.state import AppState
    from volfit.data.store import VolStore
    from volfit.replay_report import _StoredChains

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with VolStore(db_path) as vs:
        listed = vs.list_snapshots(tickers or None)
        by_day = defaultdict(list)
        for ticker, _sid, ts in listed:
            by_day[(ticker, ts.date())].append(ts)
        for (ticker, day), stamps in sorted(by_day.items()):
            path = os.path.join(RESULTS_DIR, f"{ticker}_{day.isoformat()}.json")
            if os.path.exists(path):
                print(f"{ticker} {day}: exists, skipped")
                continue
            rows = []
            for ts in sorted(stamps):
                snap = vs.snapshot_at(ticker, ts)
                state = AppState(ts.date(), provider=_StoredChains({ticker: snap}))
                state.set_expiries(ticker, sorted(snap.expiries()))
                state.set_options(
                    state.options().model_copy(update={"intradayClock": True})
                )
                for expiry in _pick_expiries(snap):
                    try:
                        m = _measure(state, ticker, expiry)
                    except Exception as exc:  # noqa: BLE001 — skip broken nodes
                        print(f"  {ts} {expiry}: failed ({exc})")
                        m = None
                    if m is not None:
                        rows.append({"ts": ts.isoformat(),
                                     "expiry": expiry.isoformat(), **m})
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(rows, fh)
            print(f"{ticker} {day}: {len(rows)} measurements")


# ------------------------------------------------------------------- sweep
def _load_table() -> dict[tuple[str, str], list[dict]]:
    """(ticker, expiry) -> chronological measurement rows, across all days."""
    series: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for name in sorted(os.listdir(RESULTS_DIR)):
        # only the per-(ticker, day) measurement files — not sweep.json
        if not re.fullmatch(r"[A-Z]+_\d{4}-\d{2}-\d{2}\.json", name):
            continue
        ticker = name.split("_")[0]
        with open(os.path.join(RESULTS_DIR, name), encoding="utf-8") as fh:
            for row in json.load(fh):
                series[(ticker, row["expiry"])].append(row)
    for rows in series.values():
        rows.sort(key=lambda r: r["ts"])
    return dict(series)


def _step_type(gap_hours: float) -> str | None:
    for name, cap in STEP_TYPES:
        if gap_hours <= cap:
            return name
    return None  # past the production reset horizon: no prediction is made


def _empirical_moves(series) -> None:
    """Config-free realized handle-move stats per step type — the raw clock
    evidence (what does 30 minutes / one night / one weekend actually move?)."""
    moves = defaultdict(list)
    for (ticker, expiry), rows in series.items():
        for prev, cur in zip(rows, rows[1:]):
            t0 = datetime.fromisoformat(prev["ts"])
            t1 = datetime.fromisoformat(cur["ts"])
            kind = _step_type((t1 - t0).total_seconds() / 3600.0)
            if kind is None:
                continue
            dte = (date.fromisoformat(expiry) - t0.date()).days
            bucket = "daily" if dte <= 7 else "anchor"
            h = float(np.log(cur["forward"] / prev["forward"]))
            trans = transport_handles(np.array(prev["z"]), h, 1.0)
            moves[(kind, bucket)].append(np.array(cur["z"]) - trans)
    print("\nRealized transported handle moves (std | ATM in bp):")
    for kind, _ in STEP_TYPES:
        for bucket in ("daily", "anchor"):
            if (kind, bucket) not in moves:
                continue
            arr = np.array(moves[(kind, bucket)])
            std = arr.std(axis=0)
            print(f"  {kind:9s} {bucket:6s} n={arr.shape[0]:4d}  "
                  f"atm={std[0]*1e4:7.1f}bp  skew={std[1]:.4f}  curv={std[2]:.3f}")


def sweep() -> list[dict]:
    """Replay the filter core over the table for every config; print + return
    the per-(config, step-type) scores."""
    series = _load_table()
    if not series:
        raise SystemExit(f"no measurement table under {RESULTS_DIR} — run --build")
    _empirical_moves(series)
    out = []
    for clock_name, share, nontrading in CLOCKS:
        for bp in PROCESS_BPS:
            zeta = defaultdict(list)
            pred_err = defaultdict(list)
            persist_err = defaultdict(list)
            trips = defaultdict(list)
            for rows in series.values():
                mean = np.array(rows[0]["z"])
                cov = np.diag(rows[0]["r_diag"])
                prev = rows[0]
                for cur in rows[1:]:
                    t0 = datetime.fromisoformat(prev["ts"])
                    t1 = datetime.fromisoformat(cur["ts"])
                    gap_h = (t1 - t0).total_seconds() / 3600.0
                    kind = _step_type(gap_h)
                    if kind is None:  # production resets: reseed from data
                        mean, cov = np.array(cur["z"]), np.diag(cur["r_diag"])
                        prev = cur
                        continue
                    h = float(np.log(cur["forward"] / prev["forward"]))
                    dt = intraday_variance_days(t0, t1, share, nontrading)
                    q, _ = process_noise(dt, h, vol_bp_sqrt_day=bp)
                    pred = predict(transport_handles(mean, h, 1.0), cov, q, h)
                    z = np.array(cur["z"])
                    r = np.array(cur["r_diag"])
                    nu = z - pred.mean
                    zeta[kind].append(nu / np.sqrt(np.diag(pred.cov) + r))
                    pred_err[kind].append(np.abs(nu))
                    persist_err[kind].append(
                        np.abs(z - transport_handles(np.array(prev["z"]), h, 1.0))
                    )
                    infl = adaptive_inflation(nu, np.diag(pred.cov), r, SIGMA_GATE)
                    trips[kind].append(float(np.any(infl > 1.0)))
                    cov_infl = pred.cov + np.diag((infl - 1.0) * np.diag(pred.cov))
                    up = kalman_update(pred.mean, cov_infl, z, np.diag(r))
                    mean, cov = up.mean, up.cov
                    prev = cur
            for kind, _ in STEP_TYPES:
                if kind not in zeta:
                    continue
                zs = np.array(zeta[kind])
                pe = np.array(pred_err[kind])
                be = np.array(persist_err[kind])
                out.append({
                    "clock": clock_name, "process_bp": bp, "step": kind,
                    "n": int(zs.shape[0]),
                    "zeta_std": [float(v) for v in zs.std(axis=0)],
                    "pred_atm_bp": float(np.median(pe[:, 0]) * 1e4),
                    "persist_atm_bp": float(np.median(be[:, 0]) * 1e4),
                    "trip_rate": float(np.mean(trips[kind])),
                })
    print("\nconfig                     step       n   zeta(atm,skew,curv)"
          "      pred|persist atm   trips")
    for r in out:
        z = r["zeta_std"]
        print(f"  {r['clock']:10s} q={r['process_bp']:5.0f}bp {r['step']:9s} "
              f"{r['n']:4d}  {z[0]:5.2f} {z[1]:5.2f} {z[2]:5.2f}   "
              f"{r['pred_atm_bp']:6.1f} | {r['persist_atm_bp']:6.1f} bp   "
              f"{r['trip_rate']*100:4.0f}%")
    # Joint calibration ranking: a config is right when std(zeta_atm) ~ 1 on
    # EVERY step type at once — that is what "the clock is right" means.
    scores = defaultdict(float)
    for r in out:
        scores[(r["clock"], r["process_bp"])] += (
            np.log(max(r["zeta_std"][0], 1e-6)) ** 2 * np.sqrt(r["n"])
        )
    print("\nJoint ATM-zeta calibration ranking (lower = jointly closer to 1):")
    for (clock, bp), loss in sorted(scores.items(), key=lambda kv: kv[1])[:8]:
        parts = {r["step"]: r["zeta_std"][0] for r in out
                 if r["clock"] == clock and r["process_bp"] == bp}
        detail = "  ".join(f"{k}={v:.2f}" for k, v in parts.items())
        print(f"  {clock:12s} q={bp:5.0f}bp  loss={loss:7.2f}   {detail}")
    with open(os.path.join(RESULTS_DIR, "sweep.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Intraday filter clock tuning.")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--db", default=os.path.join("backtest", "results", "intraday.sqlite"))
    ap.add_argument("--tickers", default="SPY,QQQ,IWM")
    args = ap.parse_args()
    if args.build:
        build(args.db, [t.strip().upper() for t in args.tickers.split(",")])
    if args.sweep:
        sweep()
    if not (args.build or args.sweep):
        raise SystemExit("pass --build and/or --sweep")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
