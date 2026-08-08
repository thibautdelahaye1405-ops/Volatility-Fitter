"""Macro-only computation blocks (no figures, just quoted numbers).

* ``certification`` -- a reduced randomized no-arbitrage battery in the
  production audit's spirit: 27 slices (orders {4, 8, 16} x {plain,
  near-wall, wild} x 3 draws) drawn through the logistic chart, audited
  in STRIKE space at sub-grid points; worst bounds / butterfly / digital
  violations and coarse-vs-fine grid agreement are emitted.
* ``timing`` -- analytic vs finite-difference calibration wall time on a
  40-quote strip at N in {6, 12, 16}: ONE interleaved run, >= 7 solves
  per arm after warm-up, medians + IQR (never fastest-of-k).
* ``ticket`` -- the worked SPY 2026-12-18 ticket: one OTM strike priced
  by hand from the upper-share ledger.
"""

from __future__ import annotations

import time

import numpy as np
from scipy.optimize import least_squares
from scipy.special import expit

from volfit.calib.band import MID_ANCHOR_WEIGHT
from volfit.core.black import black_call, black_vega_sigma
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import (
    OPT_N_POINTS,
    _BARRIER_CENTER,
    _BARRIER_SCALE,
    _residuals,
    logistic_init,
)
from volfit.models.lqd.charts import build_chart
from volfit.models.lqd.jacobian import residual_jacobian
from volfit.models.lqd.quadrature import build_slice

import data
import synth
from macros import STORE, num, sci

CERT_SEED = 20260804
CERT_ORDERS = (4, 8, 16)
CERT_DRAWS_PER_CELL = 3
TIMING_ORDERS = (6, 12, 16)
TIMING_REPS = 9  # interleaved analytic/FD solves per order, after warm-up
TICKET_STRIKE = 800.0


# ------------------------------------------------------------ certification
def _draw_params(rng, n_order: int, near_wall: bool, wild: bool) -> LQDParams:
    """Random admissible parameters drawn THROUGH the logistic chart."""
    chart = build_chart(n_order, "logistic")
    n = np.arange(2, n_order + 1)
    psi = np.empty(n_order + 1)
    psi[0] = rng.uniform(-5.0, -0.5)
    psi[1] = rng.uniform(2.2, 5.0) if near_wall else rng.uniform(-6.0, 2.0)
    psi[2:] = (rng.normal(0.0, 0.9, n.size) / (n / 2.0) ** 2 if wild
               else rng.normal(0.0, 0.25, n.size) * (2.0 / n))
    return LQDParams.from_vector(chart.to_theta(psi))


def certification() -> str:
    """The reduced strike-space audit battery; worst violations as macros."""
    rng = np.random.default_rng(CERT_SEED)
    worst = dict(bounds=0.0, butterfly=0.0, digital=0.0, grid=0.0)
    kinds = ({}, {"near_wall": True}, {"wild": True})
    n_slices = 0
    for n_order in CERT_ORDERS:
        for kind in kinds:
            for _ in range(CERT_DRAWS_PER_CELL):
                params = _draw_params(rng, n_order,
                                      kind.get("near_wall", False),
                                      kind.get("wild", False))
                s = build_slice(params)
                n_slices += 1
                k_lo, k_hi = float(s.q_z[40]), float(s.q_z[-40])
                # Bounds at sub-grid strikes (the offsets dodge the nodes).
                k = np.linspace(k_lo, k_hi, 2001)[1:-1] + 1.2e-7
                c = np.asarray(s.call_price(k))
                lower = np.maximum(1.0 - np.exp(k), 0.0)
                worst["bounds"] = max(worst["bounds"],
                                      float(np.max(lower - c)),
                                      float(np.max(c - 1.0)))
                # Butterflies and digitals audited in STRIKE space K = e^k.
                kc = np.linspace(k_lo, k_hi, 201)[1:-1] + 3.2e-8
                strike = np.exp(kc)
                cm = np.asarray(s.call_price(kc))
                for eps in (1e-3, 1e-2, 5e-2):
                    width = eps * strike
                    cl = np.asarray(s.call_price(np.log(strike - width)))
                    cr = np.asarray(s.call_price(np.log(strike + width)))
                    worst["butterfly"] = max(
                        worst["butterfly"], -float(np.min(cl + cr - 2.0 * cm)))
                    window = np.abs(kc) <= 3.0
                    if window.any():
                        digital = (cm[window] - cr[window]) / width[window]
                        worst["digital"] = max(worst["digital"], float(
                            np.max(np.maximum(-digital, digital - 1.0))))
                # Two-grid agreement at random audit strikes.
                fine = build_slice(params, n_points=32001)
                kk = rng.uniform(k_lo, k_hi, 200)
                worst["grid"] = max(worst["grid"], float(np.max(np.abs(
                    np.asarray(s.call_price(kk))
                    - np.asarray(fine.call_price(kk))))))

    STORE.add("certification", "CertSlices", str(n_slices),
              "randomized slices in the reduced test battery")
    STORE.add("certification", "CertOrdersList", "4, 8, and 16",
              "orders covered by the battery")
    STORE.add("certification", "CertWorstBounds", sci(worst["bounds"]),
              "worst violation of the no-arbitrage call bounds")
    STORE.add("certification", "CertWorstButterfly", sci(worst["butterfly"]),
              "worst negative strike-space butterfly")
    STORE.add("certification", "CertWorstDigital", sci(worst["digital"]),
              "worst digital (call-spread slope) violation")
    STORE.add("certification", "CertGridAgree", sci(worst["grid"]),
              "worst 8001-vs-32001-point grid price disagreement")
    return (f"certification ({n_slices} slices): bounds {worst['bounds']:.1e},"
            f" fly {worst['butterfly']:.1e}, digital {worst['digital']:.1e},"
            f" grid {worst['grid']:.1e}")


# ------------------------------------------------------------------ timing
def _timing_args(n_order: int):
    """The production residual-stack arguments for the 40-quote strip."""
    k, w, t = synth.timing_strip()
    sigma = np.sqrt(w / t)
    n_idx = np.arange(2, n_order + 1, dtype=float)
    args = (
        k, black_call(k, w),
        1.0 / (black_vega_sigma(k, sigma, t) + 1e-4),
        np.ones_like(k),
        np.sqrt(1e-6) * np.where(n_idx >= 4, n_idx, 0.0),
        None, None, 1e6, None, None, None,
        None, None,
        _BARRIER_CENTER, _BARRIER_SCALE, MID_ANCHOR_WEIGHT,
        None, None, None, None, OPT_N_POINTS,
    )
    return args, float(np.interp(0.0, k, w))


def timing() -> str:
    """One interleaved analytic-vs-FD timing run per order (median + IQR)."""
    tags = {6: "NSix", 12: "NTwelve", 16: "NSixteen"}
    summary = []
    for n_order in TIMING_ORDERS:
        args, w0 = _timing_args(n_order)
        init = logistic_init(w0, n_order=n_order).to_vector()

        def solve(jac):
            start = time.perf_counter()
            result = least_squares(_residuals, init, jac=jac, args=args,
                                   method="trf", xtol=1e-10, ftol=1e-10,
                                   gtol=1e-10, max_nfev=4000)
            return time.perf_counter() - start, result

        solve(residual_jacobian)  # warm the cached grids
        solve("2-point")
        t_a, t_f = [], []
        for _ in range(TIMING_REPS):  # interleaved, never fastest-of-k
            t_a.append(solve(residual_jacobian)[0])
            t_f.append(solve("2-point")[0])
        med_a = 1e3 * float(np.median(t_a))
        med_f = 1e3 * float(np.median(t_f))
        iqr_a = 1e3 * float(np.subtract(*np.percentile(t_a, [75, 25])))
        iqr_f = 1e3 * float(np.subtract(*np.percentile(t_f, [75, 25])))
        tag = tags[n_order]
        STORE.add("timing", f"TimingAnalyticMed{tag}", num(med_a, 1),
                  f"median analytic-Jacobian fit time at N = {n_order}, ms")
        STORE.add("timing", f"TimingAnalyticIqr{tag}", num(iqr_a, 1),
                  f"IQR of the analytic fit time at N = {n_order}, ms")
        STORE.add("timing", f"TimingFdMed{tag}", num(med_f, 1),
                  f"median finite-difference fit time at N = {n_order}, ms")
        STORE.add("timing", f"TimingFdIqr{tag}", num(iqr_f, 1),
                  f"IQR of the finite-difference fit time at N = {n_order}, ms")
        STORE.add("timing", f"TimingSpeedup{tag}", num(med_f / med_a, 2),
                  f"FD / analytic median speed-up at N = {n_order}")
        summary.append(f"N={n_order}: {med_a:.0f}/{med_f:.0f} ms "
                       f"x{med_f / med_a:.2f}")
    STORE.add("timing", "TimingReps", str(TIMING_REPS),
              "interleaved solves per arm after warm-up")
    STORE.add("timing", "TimingQuoteCount", "40",
              "quotes in the timing strip")
    return "timing " + "; ".join(summary)


# ------------------------------------------------------------------ ticket
def ticket() -> str:
    """Hand-price one OTM SPY December call from the ledger."""
    node = data.node(*data.SPY_DEC)
    k = float(np.log(TICKET_STRIKE / node.forward))
    z_k = float(node.slice.strike_to_z(k))
    u_k = float(expit(z_k))
    share = float(node.slice.asset_share_at(z_k))
    cash = float(np.exp(k) * (1.0 - u_k))
    call = float(node.slice.call_price(k))
    assert abs(call - (share - cash)) < 1e-12, "ledger identity broken"
    iv = float(node.slice.implied_vol(k, node.t))

    STORE.add("ticket", "TicketStrike", f"{TICKET_STRIKE:.0f}",
              "strike of the worked SPY December call")
    STORE.add("ticket", "TicketK", num(k, 4),
              "log-moneyness of the worked strike")
    STORE.add("ticket", "TicketPercentilePct", num(100.0 * u_k, 2),
              "percentile rank u of the worked strike, %")
    STORE.add("ticket", "TicketShare", num(share, 6),
              "upper-share ledger entry G(z_k)")
    STORE.add("ticket", "TicketCash", num(cash, 6),
              "cash leg e^k (1 - u_k)")
    STORE.add("ticket", "TicketCall", num(call, 6),
              "normalized call = ledger entry minus cash leg")
    STORE.add("ticket", "TicketCallDollars", num(call * node.forward, 2),
              "the same call in dollars per share (times the forward)")
    STORE.add("ticket", "TicketIvPct", num(100.0 * iv, 2),
              "implied vol of the worked strike, %")
    return (f"ticket SPY {node.expiry} K={TICKET_STRIKE:.0f}: u={u_k:.4f}, "
            f"C={call:.6f} (${call * node.forward:.2f}), IV {100 * iv:.2f}%")
