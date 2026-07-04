"""Temporal observation-filter scoring (Docs/observation_filter_roadmap.md, Phase 5).

THE acceptance gate for the Note 15 filter: does the Kalman layer DENOISE a
noisy observation without DAMPING a real market move? For every consecutive
captured day pair (T-1, T) and expiry, driving the PRODUCTION filter path
(``observation_filter.on_fit_commit``):

  1. fit day T-1's FULL chain data-only and commit it through the filter in
     overlay mode -> the day-(T-1) posterior FilterState (a realistic, tightly
     converged state);
  2. carry that state into day T's AppState (real dt from the snapshot
     timestamps, real forward transport) and freeze T-1 as the active prior;
  3. build day T's measurement from a THINNED (ATM-only) data-only fit under a
     SCENARIO, commit -> prediction m-, measurement z, posterior m+;
  4. score against the day-T TRUTH = the full-chain data-only fit's handles,
     plus the held-out moderate-wing quotes:
       * posterior |error| vs the two baselines - the raw measurement (no
         filter) and the pure transported prediction (gain 0);
       * zeta = (truth - m+) / sqrt(diag P+)  (calibration of uncertainty);
       * reconstructed-smile wing RMS (the thinned backbone retargeted to m+).

Scenarios (the note's SS9 protocol; gap preservation is BY CONSTRUCTION in the
3-handle state - the tails are not filter coordinates, they belong to prior
persistence / the graph):

  thinned        the plain consecutive-snapshot test (protocol item 1);
  contradiction  two adjacent near-ATM strikes kinked in opposite directions
                 (a stale-market curvature artifact, item 2) - the filter must
                 reject the curvature noise while keeping the level;
  shock          a true +5 vol-point jump on ALL day-T quotes with unchanged
                 spreads (item 3) - the filter must FOLLOW (high gain, no lag).

Sweeps the covariance route (jacobian vs factors - the zeta comparison is the
empirical verdict on the Jacobian R_t) and the clock process noise.

Run::

    python -m backtest.observation_filter --regime spike_aug2024
    python -m backtest.observation_filter --regime spike_aug2024 --asset SPX \
        --cov-modes jacobian,factors --process-bps 5,10,20 --max-pairs 2
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from dataclasses import dataclass, replace

import numpy as np

from volfit.api import observation_filter as ofilt
from volfit.api import priors, service
from volfit.api.state import FitRecord
from volfit.calib.weights import resolve_weights
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.lqd.ortho import build_atm_coordinates
from volfit.models.lqd.quadrature import build_slice

from backtest.dispatch import _LQD
from backtest.replay import list_fixtures, load_fixture, state_for_day
from backtest.temporal import _atm_mask, _day_pairs, _wing_rmse_bp

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

SCENARIOS = ("thinned", "contradiction", "shock")
HANDLES = ("atm", "skew", "curv")
SHOCK_VOL = 0.05  # the true jump applied in the shock scenario (5 vol points)


@dataclass(frozen=True)
class NodeResult:
    """One (asset, expiry, scenario, config) filter step, fully scored."""

    asset: str
    as_of: str
    prior_as_of: str
    expiry: str
    regime: str
    scenario: str
    cov_mode: str
    process_bp: float
    t: float
    n_atm: int
    n_wing: int
    gain: list  # diag K per handle
    rho: float | None
    err_post: list  # |m+ - truth| per handle
    err_meas: list  # |z  - truth| per handle (the no-filter baseline)
    err_pred: list  # |m- - truth| per handle (the gain-0 baseline)
    zeta: list  # (truth - m+) / sd(P+) per handle
    wing_post_bp: float | None  # retargeted-to-m+ smile vs held-out quotes
    wing_meas_bp: float | None  # the data-only thinned fit (no filter)


def _handles(result, tau: float) -> np.ndarray:
    h = atm_handles(result.slice, tau)
    return np.array([h.sigma0, h.skew, h.curvature])


def _fit_data_only(k, w, tau, solver_diag=None):
    """The measurement-pass fit: LQD-6, no priors (the note's data-only pass)."""
    weights = resolve_weights("equal", k, w)
    return calibrate_slice(
        k, w, t=tau, n_order=6, weights=weights, solver_diag=solver_diag, **_LQD
    )


def _truth_with_cov(prepared, k, w_truth, tau):
    """The day-T truth handles AND their own covariance R_truth (the note's
    protocol scores zeta against sqrt(P+ + R_heldout): the full-chain fit is
    itself a noisy estimate, and omitting its noise overstates the filter's
    miscalibration). Built with the same Jacobian machinery as the
    measurement, noise = the full chain's bid-ask half-spreads."""
    from volfit.calib.observation_measurement import (
        handle_jacobian_fd,
        measurement_from_jacobian,
    )
    from volfit.calib.precision import RMS_FLOOR
    from volfit.models.lqd.basis import LQDParams

    fd: dict = {}
    result = _fit_data_only(k, w_truth, tau, solver_diag=fd)
    truth = _handles(result, tau)

    def handle_fn(theta):
        h = atm_handles(build_slice(LQDParams.from_vector(theta)), tau)
        return np.array([h.sigma0, h.skew, h.curvature])

    half = np.maximum(
        (np.asarray(prepared.iv_ask) - np.asarray(prepared.iv_bid)) / 2.0, RMS_FLOOR
    )
    noise = half if half.size == fd["n_quotes"] else float(np.median(half))
    g = handle_jacobian_fd(handle_fn, fd["theta"])
    m = measurement_from_jacobian(
        truth, fd["jac"], g, fd["residual"], fd["n_fit_rows"], fd["n_quotes"],
        noise_scale=noise,
    )
    return truth, np.diag(m.cov)


def _apply_scenario(scenario: str, k_in, w_in, tau: float):
    """Perturb the thinned day-T inputs per the protocol; returns (k, w, dvol)
    where dvol is the true level shift baked into the truth for scoring."""
    if scenario == "contradiction":
        vol = np.sqrt(np.maximum(w_in, 1e-12) / tau)
        order = np.argsort(np.abs(k_in))
        kink = np.zeros_like(vol)
        if order.size >= 3:  # two adjacent strikes, opposite signs = a local kink
            kink[order[1]] += 0.02
            kink[order[2]] -= 0.02
        return k_in, (vol + kink) ** 2 * tau, 0.0
    if scenario == "shock":
        vol = np.sqrt(np.maximum(w_in, 1e-12) / tau)
        return k_in, (vol + SHOCK_VOL) ** 2 * tau, SHOCK_VOL
    return k_in, w_in, 0.0


def prior_holder(state_tm1, asset: str, iso: str):
    """The day-(T-1) posterior FilterState via the PRODUCTION commit path: fit
    the full chain data-only, seed + update in overlay mode. None on failure."""
    expiry = state_tm1.resolve_expiry(asset, iso)
    prepared = service.prepared_quotes(state_tm1, asset, expiry)
    if prepared.k.size < 5:
        return None
    fd: dict = {}
    result = _fit_data_only(prepared.k, prepared.w_mid, prepared.tau, solver_diag=fd)
    record = FitRecord(prepared=prepared, result=result, display=None)
    return ofilt.on_fit_commit(state_tm1, asset, iso, "mid", record, fd)


def filter_step(
    state_t, asset: str, iso: str, holder_prev, scenario: str,
    c_atm: float, c_wing: float, min_atm: int, min_wing: int,
):
    """One day-T filter step under a scenario. Returns the scoring dict or None
    (not enough ATM/wing support, or a fit break)."""
    expiry = state_t.resolve_expiry(asset, iso)
    prepared = service.prepared_quotes(state_t, asset, expiry)
    k, w, tau = prepared.k, prepared.w_mid, prepared.tau
    if k.size == 0 or tau <= 0.0:
        return None
    atm_vol = float(np.sqrt(max(np.interp(0.0, k, w), 1e-12) / tau))
    atm = _atm_mask(k, atm_vol, tau, c_atm)
    wing = (~atm) & _atm_mask(k, atm_vol, tau, c_wing)
    if int(atm.sum()) < min_atm or int(wing.sum()) < min_wing:
        return None

    k_in, w_in, dvol = _apply_scenario(scenario, k[atm], w[atm], tau)

    # Truth = the full-chain data-only fit (level-shifted in the shock scenario
    # so the truth carries the same genuine jump the measurement saw), with its
    # OWN covariance for the zeta denominator.
    w_truth = w if dvol == 0.0 else (np.sqrt(np.maximum(w, 1e-12) / tau) + dvol) ** 2 * tau
    truth, r_truth = _truth_with_cov(prepared, k, w_truth, tau)
    w_wing = w_truth[wing]

    # The measurement fit (thinned + scenario), committed through PRODUCTION.
    fd: dict = {}
    result = _fit_data_only(k_in, w_in, tau, solver_diag=fd)
    record = FitRecord(prepared=prepared, result=result, display=None)
    key = (asset, iso, "mid")
    # inject the carried T-1 state; data_version -1 guarantees "new observation"
    state_t.set_filter_node(key, replace(holder_prev, data_version=-1))
    holder = ofilt.on_fit_commit(state_t, asset, iso, "mid", record, fd)
    if holder is None or holder.update is None:
        return None
    if holder.state.reset_reason is not None:
        return None  # a reseed is not a filter step; skip (e.g. > resetHours gap)

    m_post, p_post = holder.state.mean, holder.state.cov
    m_pred = holder.prediction.mean
    z = holder.measurement.handles
    # zeta denominator = sqrt(P+ + R_truth): the held-out truth is itself noisy
    # (note SS9 item 6 scores against P+ + R_heldout).
    sd = np.sqrt(np.maximum(np.diag(p_post) + r_truth, 1e-18))

    # Reconstructed smiles: the thinned backbone retargeted to the posterior.
    chart = build_atm_coordinates(result.params, tau)
    try:
        target = np.array([m_post[0] ** 2 * tau, m_post[1], m_post[2]])
        post_slice = build_slice(chart.retarget(target))
        wing_post = _wing_rmse_bp(post_slice, k[wing], w_wing, tau)
    except (RuntimeError, ValueError):  # Newton failure / A_R inadmissible
        wing_post = None
    wing_meas = _wing_rmse_bp(result.slice, k[wing], w_wing, tau)

    return dict(
        t=float(prepared.t), n_atm=int(atm.sum()), n_wing=int(wing.sum()),
        gain=[round(float(g), 4) for g in np.diag(holder.update.gain)],
        rho=holder.measurement.breakdown.get("rho"),
        err_post=[round(float(abs(a - b)), 6) for a, b in zip(m_post, truth)],
        err_meas=[round(float(abs(a - b)), 6) for a, b in zip(z, truth)],
        err_pred=[round(float(abs(a - b)), 6) for a, b in zip(m_pred, truth)],
        zeta=[round(float((tr - mp) / s), 3) for tr, mp, s in zip(truth, m_post, sd)],
        wing_post_bp=wing_post, wing_meas_bp=wing_meas,
    )


def run(
    regime: str, asset: str | None, cov_modes, process_bps, scenarios,
    c_atm: float, c_wing: float, min_atm: int, min_wing: int, max_pairs: int | None,
) -> list[NodeResult]:
    """Score every consecutive day pair x expiry x scenario x config."""
    paths = list_fixtures(regime=regime, asset=asset)
    if not paths:
        raise SystemExit(f"no fixtures for regime={regime} asset={asset}")
    pairs = _day_pairs(paths)
    results: list[NodeResult] = []
    for tk in sorted(pairs):
        seq = pairs[tk][:max_pairs] if max_pairs else pairs[tk]
        for prior_path, today_path in seq:
            prior_fx, today_fx = load_fixture(prior_path), load_fixture(today_path)
            state_tm1 = state_for_day([prior_fx])
            state_tm1.set_options(state_tm1.options().model_copy(
                update={"observationFilterMode": "overlay",
                        "priorPersistenceMode": "off"}))
            snap = priors.capture_snapshot(state_tm1, tk, "mid", lv=False)
            for expiry in today_fx.expiries:
                iso = expiry.isoformat()
                try:
                    holder_prev = prior_holder(state_tm1, tk, iso)
                except Exception:  # noqa: BLE001 — a broken prior node is a skip
                    holder_prev = None
                if holder_prev is None:
                    continue
                for cov_mode in cov_modes:
                    for bp in process_bps:
                        state_t = state_for_day([today_fx])
                        state_t.set_options(state_t.options().model_copy(update={
                            "observationFilterMode": "overlay",
                            "priorPersistenceMode": "off",
                            "filterCovarianceMode": cov_mode,
                            "filterProcessVolBpSqrtDay": bp,
                        }))
                        if snap is not None:  # seeding fallback parity with prod
                            state_t.set_active_prior(tk, snap, "saved")
                        for scenario in scenarios:
                            try:
                                s = filter_step(state_t, tk, iso, holder_prev,
                                                scenario, c_atm, c_wing,
                                                min_atm, min_wing)
                            except Exception:  # noqa: BLE001 — skip, don't crash
                                s = None
                            if s is not None:
                                results.append(NodeResult(
                                    asset=tk, as_of=today_fx.as_of.isoformat(),
                                    prior_as_of=prior_fx.as_of.isoformat(),
                                    expiry=iso, regime=regime, scenario=scenario,
                                    cov_mode=cov_mode, process_bp=bp, **s))
            print(f"  {tk} {today_fx.as_of}: "
                  f"{sum(1 for r in results if r.asset == tk and r.as_of == today_fx.as_of.isoformat())} "
                  f"steps scored", flush=True)
    return results


#: Maturity split for the summary: the short bucket isolates the known
#: short-dated quote/de-Am noise regime (LV short-dated diagnosis) where the
#: thinned-vs-full ATM discrepancy is dominated by data noise, not the filter.
SHORT_DTE_YEARS = 30.0 / 365.0


def summarize(results: list[NodeResult]) -> list[dict]:
    """Aggregate per (scenario, cov_mode, process_bp, maturity bucket): the
    denoise-vs-damp verdict numbers. err_* are per-handle medians in ATM-vol
    bp / raw units; win = fraction of nodes where the posterior beats the raw
    measurement. The <=30d / >30d split keeps the short-dated noise regime
    from masking (or being masked by) the normal-maturity calibration."""
    by_cfg: dict[tuple, list[NodeResult]] = defaultdict(list)
    for r in results:
        bucket = "<=30d" if r.t <= SHORT_DTE_YEARS else ">30d"
        by_cfg[(r.scenario, r.cov_mode, r.process_bp, bucket)].append(r)
    out: list[dict] = []
    for (scenario, cov, bp, bucket), grp in sorted(by_cfg.items()):
        post = np.array([g.err_post for g in grp], float)
        meas = np.array([g.err_meas for g in grp], float)
        pred = np.array([g.err_pred for g in grp], float)
        zeta = np.array([g.zeta for g in grp], float)
        gains = np.array([g.gain for g in grp], float)
        wp = np.array([g.wing_post_bp for g in grp if g.wing_post_bp is not None], float)
        wm = np.array([g.wing_meas_bp for g in grp if g.wing_meas_bp is not None], float)
        out.append(dict(
            scenario=scenario, cov_mode=cov, process_bp=bp, bucket=bucket, n=len(grp),
            med_err_post=[round(float(v), 5) for v in np.median(post, axis=0)],
            med_err_meas=[round(float(v), 5) for v in np.median(meas, axis=0)],
            med_err_pred=[round(float(v), 5) for v in np.median(pred, axis=0)],
            win_vs_meas=[round(float(np.mean(post[:, i] < meas[:, i])), 3) for i in range(3)],
            med_gain=[round(float(v), 3) for v in np.median(gains, axis=0)],
            zeta_mean=[round(float(v), 3) for v in np.mean(zeta, axis=0)],
            zeta_std=[round(float(v), 3) for v in np.std(zeta, axis=0)],
            med_wing_post_bp=round(float(np.median(wp)), 2) if wp.size else None,
            med_wing_meas_bp=round(float(np.median(wm)), 2) if wm.size else None,
        ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Temporal observation-filter scoring.")
    ap.add_argument("--regime", default="spike_aug2024")
    ap.add_argument("--asset", default=None)
    ap.add_argument("--cov-modes", default="jacobian,factors")
    ap.add_argument("--process-bps", default="10", help="filterProcessVolBpSqrtDay sweep")
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--c-atm", type=float, default=0.5)
    ap.add_argument("--c-wing", type=float, default=2.0)
    ap.add_argument("--min-atm", type=int, default=5)
    ap.add_argument("--min-wing", type=int, default=3)
    ap.add_argument("--max-pairs", type=int, default=None)
    args = ap.parse_args()

    cov_modes = tuple(m.strip() for m in args.cov_modes.split(","))
    process_bps = tuple(float(b) for b in args.process_bps.split(","))
    scenarios = tuple(s.strip() for s in args.scenarios.split(","))
    print(f"regime={args.regime} asset={args.asset or '*'} cov={cov_modes} "
          f"bp={process_bps} scenarios={scenarios}", flush=True)

    results = run(args.regime, args.asset, cov_modes, process_bps, scenarios,
                  args.c_atm, args.c_wing, args.min_atm, args.min_wing, args.max_pairs)
    summary = summarize(results)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    suffix = f"_{args.asset}" if args.asset else ""
    base = os.path.join(RESULTS_DIR, f"{args.regime}_observation_filter{suffix}")
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump({"rows": [r.__dict__ for r in results], "summary": summary},
                  fh, default=str, indent=2)
    print(f"\nwrote {base}.json  ({len(results)} steps)\n")
    hdr = (f"{'scenario':<15}{'cov':<10}{'bp':>5}{'bucket':>8}{'n':>5}"
           "  errPost(atm)  errMeas(atm)  win  gain(atm)  zstd(atm)")
    print(hdr)
    for s in summary:
        print(f"{s['scenario']:<15}{s['cov_mode']:<10}{s['process_bp']:>5}"
              f"{s['bucket']:>8}{s['n']:>5}"
              f"  {s['med_err_post'][0]:>11}  {s['med_err_meas'][0]:>11}"
              f"  {s['win_vs_meas'][0]:>4}  {s['med_gain'][0]:>8}  {s['zeta_std'][0]:>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
