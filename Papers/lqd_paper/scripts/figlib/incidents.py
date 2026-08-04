"""Reproduced incidents and one-off measured numbers (macro-only block).

Everything here is computed fresh and deterministically (fixed inputs,
warm-ups before any timing):

* the latency cliff on the frozen NVDA 1-day node (params/quotes ~
  0.47 / 0.59 / 0.71, i.e. N = 7 / 9 / 11 on 17 quotes);
* warm single-fit wall times (NVDA 1d at its guarded order; SPY Dec at
  N = 16) and the belly-certificate wall time;
* the rank-saturation incident: far-right-wing pricing with the naive
  cash leg e^k (1 - u) vs the production log-space form, as a butterfly
  violation (mirrors the far-wing regression lock in the test suite);
* the phantom-drag experiment: an acute synthetic near/far pair fitted
  with the FULL-grid G-space calendar floor vs the support-confined
  price floor;
* grid- and chart-robustness of the optimum (2001- vs 8001-point
  optimization grid; lr vs logistic chart) on SPY Dec;
* analytic-vs-FD same-optimum agreement on the timing strip.
"""

from __future__ import annotations

import time

import numpy as np
from scipy.optimize import least_squares
from scipy.special import expit

from volfit.calib.calendar import calendar_floor_targets, confined_calendar_floor
from volfit.models.diagnostics import belly_certificate
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.lqd.charts import build_chart
from volfit.models.lqd.interp import hermite_eval
from volfit.models.lqd.jacobian import residual_jacobian
from volfit.models.lqd.quadrature import build_slice

import audit as audit_mod
import data
from macros import STORE, num, sci

CLIFF_ORDERS = ((7, "Lo"), (9, "Mid"), (11, "Hi"))
_PROD_REG = dict(reg_lambda=1e-6, reg_power=1.0)


def _ms(value_ms: float) -> str:
    """'NN ms' below one second, 'X.X s' above (contract render style)."""
    if value_ms >= 995.0:
        return f"{value_ms / 1e3:.1f} s"
    return f"{value_ms:.0f} ms" if value_ms >= 9.95 else f"{value_ms:.1f} ms"


def _timed_fit(node: data.Node, n_order: int, reps: int = 5):
    """Median wall ms + deterministic result of one frozen-node fit at a
    forced order with the production objective (after one warm-up)."""
    w = node.iv_mid**2 * node.t
    calibrate_slice(node.k, w, node.t, n_order=n_order,
                    coords="logistic", **_PROD_REG)  # warm-up
    times, result = [], None
    for _ in range(reps):
        start = time.perf_counter()
        result = calibrate_slice(node.k, w, node.t, n_order=n_order,
                                 coords="logistic", **_PROD_REG)
        times.append(time.perf_counter() - start)
    return 1e3 * float(np.median(times)), result


def cliff_and_fit_times() -> str:
    """The latency cliff (NVDA 1d) + the two headline warm fit times."""
    short = data.node(*data.NVDA_SHORT)
    parts = []
    for n_order, tag in CLIFF_ORDERS:
        ms, result = _timed_fit(short, n_order)
        ratio = (n_order + 1) / short.n_quotes
        STORE.add("cliff", f"Cliff{tag}Ratio", num(ratio, 2),
                  f"params/quotes ratio at N = {n_order} on the 17-quote"
                  " NVDA 1d node")
        STORE.add("cliff", f"Cliff{tag}Evals", str(result.n_evaluations),
                  f"solver residual evaluations at N = {n_order}")
        STORE.add("cliff", f"Cliff{tag}Ms", _ms(ms),
                  f"median warm fit wall time at N = {n_order}")
        parts.append(f"N={n_order}: {ratio:.2f} {result.n_evaluations}ev"
                     f" {ms:.0f}ms")

    zero_ms, _ = _timed_fit(short, short.order)
    STORE.add("cliff", "FitMsZeroDte", _ms(zero_ms),
              "median warm fit of the NVDA 1d node at its guarded order"
              f" N = {short.order}")
    spy = data.node(*data.SPY_DEC)
    spy_ms, _ = _timed_fit(spy, 16)
    STORE.add("cliff", "FitMsOrderSixteen", _ms(spy_ms),
              f"median warm fit of SPY Dec ({spy.n_quotes} quotes) at N = 16")
    return "cliff " + "; ".join(parts) + \
        f"; fitMs 0dte {zero_ms:.0f} / N16 {spy_ms:.0f}"


def belly_ms(reps: int = 25) -> str:
    """Median wall time of the dense Durrleman belly certificate."""
    node = data.node(*data.SPY_DEC)
    k_lo, k_hi = float(node.k.min()), float(node.k.max())
    belly_certificate(node.slice, k_lo, k_hi)  # warm-up
    times = []
    for _ in range(reps):
        start = time.perf_counter()
        belly_certificate(node.slice, k_lo, k_hi)
        times.append(time.perf_counter() - start)
    ms = 1e3 * float(np.median(times))
    STORE.add("incidents", "BellyCertMs", _ms(ms),
              "median wall time of the 801-point belly certificate on the"
              " SPY Dec traded range")
    return f"belly certificate {ms:.2f} ms"


def flyfix() -> str:
    """Rank saturation: naive e^k(1-u) cash leg vs the log-space form.

    Near-wall slice (A_R ~ 0.97); strikes straddling the double-rounding
    point expit(z) -> 1 (z ~ 36.7).  The naive evaluation loses the cash
    leg and steps the call up to the bare share A(z_k); the worst strike-
    space butterfly of each evaluation is the incident's before/after.
    """
    chart = build_chart(6, "logistic")
    psi = np.array([-2.0, 3.5, 0.1, -0.05, 0.02, 0.0, 0.0])  # A_R ~ 0.97
    slice_ = build_slice(LQDParams.from_vector(chart.to_theta(psi)))
    z_lo, z_hi = 33.0, 39.5  # straddles the rounding point
    kc = np.interp(np.linspace(z_lo, z_hi, 401), slice_.z, slice_.q_z)

    def naive(k: np.ndarray) -> np.ndarray:
        z_k = slice_.strike_to_z(k)
        share = hermite_eval(z_k, float(slice_.z[0]), slice_._step,
                             slice_.a_z, slice_.da_dz)
        return share - np.exp(k) * (1.0 - expit(z_k))  # BUG: 1-u rounds to 0

    worst = {}
    for name, price in (("pre", naive), ("post", slice_.call_price)):
        strike = np.exp(kc[1:-1])
        width = 1e-3 * strike
        fly = (np.asarray(price(np.log(strike - width)))
               - 2.0 * np.asarray(price(kc[1:-1]))
               + np.asarray(price(np.log(strike + width))))
        worst[name] = max(0.0, -float(fly.min()))
    STORE.add("incidents", "AuditPreFixFly", sci(worst["pre"]),
              "worst butterfly violation with the naive e^k(1-u) cash leg"
              " past the expit rounding point")
    STORE.add("incidents", "AuditPostFixFly", sci(worst["post"]),
              "same strikes and stencil with the production log-space leg")
    return f"flyfix pre {worst['pre']:.1e} post {worst['post']:.1e}"


def phantom_drag() -> str:
    """Full-grid G-space calendar floor vs the support-confined price floor.

    The acute scenario of the shipped confinement lock (near: 13 quotes on
    +-0.06 with steep total variance 0.0008 + 0.6 k^2 at t = 0.02; far: 25
    quotes on +-0.30, nearly flat 0.010 + 0.004 k^2 at t = 0.25).  The far
    strip EXTENDS BEYOND the near span, so the near slice is pure
    extrapolation exactly where the far node still has quotes — the
    full-grid ledger floor drags the far fit off those quotes; the
    support-confined price floor leaves them alone.  Reported: worst far
    quote error under each floor (the incident's own metric).
    """
    k_near = np.linspace(-0.06, 0.06, 13)
    k_far = np.linspace(-0.30, 0.30, 25)
    w_near = 0.0008 + 0.6 * k_near**2
    w_far = 0.010 + 0.004 * k_far**2
    t_near, t_far = 0.02, 0.25
    from volfit.calib.calendar import common_support

    near = calibrate_slice(k_near, w_near, t=t_near)
    window = common_support(k_near, k_far)

    def worst_bp(result) -> float:
        err = 1e4 * (np.asarray(result.slice.implied_vol(k_far, t_far))
                     - np.sqrt(w_far / t_far))
        return float(np.max(np.abs(err)))

    cal_z, cal_floor = calendar_floor_targets(near.slice)  # FULL z grid
    dragged = calibrate_slice(k_far, w_far, t=t_far,
                              calendar_z=cal_z, calendar_floor=cal_floor)
    cal_k, price_floor, taper = confined_calendar_floor(near.slice, window)
    healed = calibrate_slice(k_far, w_far, t=t_far, calendar_k=cal_k,
                             calendar_price_floor=price_floor,
                             calendar_taper=taper)
    from_bp, to_bp = worst_bp(healed), worst_bp(dragged)
    STORE.add("incidents", "PhantomDragFromBp", num(from_bp, 1),
              "worst far-quote error with the support-confined price"
              " floor, vol bp (acute synthetic pair)")
    STORE.add("incidents", "PhantomDragToBp", num(to_bp, 1),
              "worst far-quote error with the calendar floor on the FULL"
              " z-grid ledger, vol bp (same pair)")
    return f"phantom drag {from_bp:.1f} -> {to_bp:.1f} bp (worst quote err)"


def optimum_robustness() -> str:
    """2001-vs-8001 grid, lr-vs-logistic chart, analytic-vs-FD optimum."""
    spy = data.node(*data.SPY_DEC)
    w = spy.iv_mid**2 * spy.t

    def fit(**kw):
        return calibrate_slice(spy.k, w, spy.t, n_order=16,
                               coords=kw.pop("coords", "logistic"),
                               **_PROD_REG, **kw)

    d_grid = float(np.max(np.abs(
        fit(opt_n_points=2001).params.to_vector()
        - fit(opt_n_points=8001).params.to_vector())))
    STORE.add("incidents", "TwoGridParamAgree", sci(d_grid),
              "max |dtheta| between 2001- and 8001-point optimization"
              " grids, SPY Dec")
    d_chart = float(np.max(np.abs(
        fit(coords="lr").params.to_vector() - fit().params.to_vector())))
    STORE.add("incidents", "ChartEquivParamAgree", sci(d_chart),
              "max |dtheta| between the lr and logistic charts, SPY Dec")

    # Same optimum, analytic vs FD Jacobian, on the timing strip.
    d_theta, d_cost = 0.0, 0.0
    for n_order in (6, 12, 16):
        args, w0 = audit_mod._timing_args(n_order)
        from volfit.models.lqd.calibrate import _residuals, logistic_init
        init = logistic_init(w0, n_order=n_order).to_vector()
        solves = {}
        for name, jac in (("a", residual_jacobian), ("f", "2-point")):
            solves[name] = least_squares(
                _residuals, init, jac=jac, args=args, method="trf",
                xtol=1e-10, ftol=1e-10, gtol=1e-10, max_nfev=4000)
        d_theta = max(d_theta, float(np.max(np.abs(
            solves["a"].x - solves["f"].x))))
        d_cost = max(d_cost, abs(solves["a"].cost - solves["f"].cost)
                     / max(solves["a"].cost, solves["f"].cost))
    STORE.add("incidents", "JacSameOptParams", sci(d_theta),
              "max |dtheta| between analytic- and FD-Jacobian optima,"
              " orders 6/12/16")
    STORE.add("incidents", "JacSameOptCost", sci(d_cost),
              "max relative cost gap between analytic- and FD-Jacobian"
              " optima")
    return (f"robustness: grid {d_grid:.1e}, chart {d_chart:.1e}, "
            f"same-opt dtheta {d_theta:.1e} dcost {d_cost:.1e}")


def incidents() -> str:
    """Run every block; one summary line for the orchestrator."""
    return "; ".join([
        cliff_and_fit_times(), belly_ms(), flyfix(), phantom_drag(),
        optimum_robustness(),
    ])
