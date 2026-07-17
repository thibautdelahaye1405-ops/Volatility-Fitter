"""Analytic Jacobian of the raw-SVI calibration residual (FINDINGS_calibration_arb R4).

SVI was the slowest baseline only because it lacked an analytic Jacobian: scipy's
finite-difference fallback costs ``1 + P = 6`` residual evals per optimizer step (one
base + one perturbation per parameter) and re-evaluates the no-arb penalty rows every
time. This differentiates the smooth residual blocks in closed form so the fit runs
~2 evals/step, the same win LQD already has (ROADMAP perf #2).

It covers the residual configuration the calibrator gates analytic-on — the mid OR
band data term + the two no-arb penalties + the optional calendar floor. The var-swap
/ strike-gap / operator-prior blocks are NOT differentiated here; those fits fall back
to the finite-difference Jacobian (correct, just not accelerated), exactly as LQD does.

Parametrization (see ``calibrate.py``): ``theta = (a, theta_b, theta_rho, m,
theta_sigma)`` with ``b = softplus(theta_b)``, ``rho = tanh(theta_rho)``,
``sigma = exp(theta_sigma)``. The reparametrization chain factors are

    db/dtheta_b = sigmoid(theta_b) = 1 - e^{-b},
    drho/dtheta_rho = 1 - rho^2,
    dsigma/dtheta_sigma = sigma.

With ``x = k - m`` and ``s = sqrt(x^2 + sigma^2)`` the raw-variance gradient is

    dw/da = 1,  dw/db = rho x + s,  dw/drho = b x,
    dw/dm = -b (rho + x/s),  dw/dsigma = b sigma / s.
"""

from __future__ import annotations

import numpy as np

from volfit.calib.band import BandTarget, band_violation_sign
from volfit.models.svi_jw.svi import RawSVI


def _dw_dtheta(raw: RawSVI, sig_b: float, one_minus_rho2: float, kk: np.ndarray) -> np.ndarray:
    """``d w(kk) / d theta`` (after the reparametrization chain rule), shape (len(kk), 5)."""
    x = kk - raw.m
    s = np.sqrt(x * x + raw.sigma * raw.sigma)
    j = np.empty((kk.size, 5))
    j[:, 0] = 1.0  # d/da
    j[:, 1] = (raw.rho * x + s) * sig_b  # dw/db . db/dtheta_b
    j[:, 2] = (raw.b * x) * one_minus_rho2  # dw/drho . drho/dtheta_rho
    j[:, 3] = -raw.b * (raw.rho + x / s)  # dw/dm
    j[:, 4] = (raw.b * raw.sigma / s) * raw.sigma  # dw/dsigma . dsigma/dtheta_sigma
    return j


def svi_residual_jacobian(
    theta: np.ndarray,
    k: np.ndarray,
    t: float,
    sqrt_weights: np.ndarray,
    band: BandTarget | None,
    mid_anchor_weight: float,
    penalty_weight: float,
    lee_slope_max: float,
    cal_k: np.ndarray | None,
    cal_floor: np.ndarray | None,
    sqrt_cal: float,
    ceil_k: np.ndarray | None = None,
    ceil_w: np.ndarray | None = None,
) -> np.ndarray:
    """Analytic Jacobian (n_residuals x 5) of the gated SVI residual.

    Rows are assembled in the SAME order as ``calibrate.residuals`` under the analytic
    gate: the fit block (mid: N rows; band: 2N rows), the two penalty rows, the
    calendar floor rows, then the calendar CEILING rows (the symmetric overlay
    repair's two-sided target). The penalty / band / calendar hinges contribute
    their subgradient (the active linear part, else zero)."""
    raw = RawSVI(
        a=float(theta[0]), b=float(np.logaddexp(0.0, theta[1])),
        rho=float(np.tanh(theta[2])), m=float(theta[3]), sigma=float(np.exp(theta[4])),
    )
    sig_b = 1.0 - np.exp(-raw.b)  # sigmoid(theta_b) = d softplus / d theta_b
    om_rho2 = 1.0 - raw.rho * raw.rho  # drho/dtheta_rho
    q = float(np.sqrt(max(om_rho2, 0.0)))

    # Fit block: d/dtheta of model_vol = sqrt(w / t).
    w = np.maximum(raw.total_variance(k), 1e-12)
    model_vol = np.sqrt(w / t)
    dmv = _dw_dtheta(raw, sig_b, om_rho2, np.asarray(k, float)) / (2.0 * t * model_vol)[:, None]
    dmv[w <= 1e-12] = 0.0  # the variance clamp flattens the gradient there

    blocks: list[np.ndarray] = []
    if band is None:
        blocks.append(sqrt_weights[:, None] * dmv)
    else:
        sign = band_violation_sign(model_vol, band.iv_lo, band.iv_hi)
        blocks.append((sqrt_weights * sign)[:, None] * dmv)  # band violation rows
        blocks.append((np.sqrt(mid_anchor_weight) * sqrt_weights)[:, None] * dmv)  # mid anchor

    # Penalties (2 rows): subgradient is the active linear part, else zero.
    min_var = raw.a + raw.b * raw.sigma * q
    d_min = np.array([1.0, raw.sigma * q * sig_b, -raw.b * raw.sigma * raw.rho * q, 0.0,
                      raw.b * raw.sigma * q])
    row_min = (-penalty_weight * d_min) if min_var < 0.0 else np.zeros(5)
    wing = raw.b * (1.0 + abs(raw.rho))
    d_wing = np.array([0.0, (1.0 + abs(raw.rho)) * sig_b,
                       raw.b * np.sign(raw.rho) * om_rho2, 0.0, 0.0])
    row_lee = (penalty_weight * d_wing) if wing > lee_slope_max else np.zeros(5)
    blocks.append(np.vstack([row_min, row_lee]))

    # Calendar floor: sqrt_cal * max(cal_floor - w(cal_k), 0); subgradient -sqrt_cal*dw.
    if cal_k is not None and cal_floor is not None:
        active = (cal_floor - raw.total_variance(cal_k)) > 0.0
        dwc = _dw_dtheta(raw, sig_b, om_rho2, np.asarray(cal_k, float))
        blocks.append((-sqrt_cal * active)[:, None] * dwc)

    # Calendar ceiling: sqrt_cal * max(w(ceil_k) - ceil, 0); subgradient +sqrt_cal*dw.
    if ceil_k is not None and ceil_w is not None:
        active = (raw.total_variance(ceil_k) - ceil_w) > 0.0
        dwc = _dw_dtheta(raw, sig_b, om_rho2, np.asarray(ceil_k, float))
        blocks.append((sqrt_cal * active)[:, None] * dwc)

    return np.vstack(blocks)
