"""One-expiry LQD calibration (note section 7 and Appendix C).

Objective: vega-normalized price residuals (eq. vega_resid) so the loss is
approximately a volatility error while every feasible iterate remains a
genuine arbitrage-free density,

    min_theta  sum_i w_i ((C_lqd(k_i) - B(k_i, w_i)) / (vega_i + eta))^2
             + lam * sum_{n>=4} n^{2r} a_n^2          (eq. calib_objective)

subject to the structural right-tail bound A_R < 1 (eq. right_admissible),
handled with a smooth soft barrier plus a hard rejection.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from volfit.core.black import black_call, black_vega_sigma
from volfit.models.lqd.basis import LQDParams, endpoint_scales
from volfit.models.lqd.quadrature import LQDSlice, build_slice

# Soft-barrier location/steepness for A_R: starts pushing back well before
# the hard integrability bound A_R < 1 so finite-difference Jacobians stay smooth.
_BARRIER_CENTER = 0.90
_BARRIER_SCALE = 50.0
_VEGA_FLOOR = 1e-4


@dataclass(frozen=True)
class CalibrationResult:
    """Fitted parameters plus convergence/fit diagnostics."""

    params: LQDParams
    slice: LQDSlice
    cost: float
    n_evaluations: int
    success: bool
    max_iv_error: float  # max |model - quote| implied vol over the quotes


def logistic_init(w0_guess: float, n_order: int = 6) -> LQDParams:
    """Logistic base initializer (note 7.2): a_n = 0, L = R = log s with the
    variance match Var(X) ~ pi^2 s^2 / 3 = w0."""
    s = np.sqrt(3.0 * w0_guess) / np.pi
    return LQDParams(L=float(np.log(s)), R=float(np.log(s)), a=np.zeros(n_order - 1))


def _residuals(
    theta: np.ndarray,
    k: np.ndarray,
    target_price: np.ndarray,
    inv_vega: np.ndarray,
    sqrt_weights: np.ndarray,
    reg: np.ndarray,
) -> np.ndarray:
    """Stacked fit + regularization + barrier residuals for one trial theta."""
    params = LQDParams.from_vector(theta)
    _, a_right = endpoint_scales(params)
    try:
        slice_ = build_slice(params)
        fit = sqrt_weights * (slice_.call_price(k) - target_price) * inv_vega
    except ValueError:
        # Infeasible tail (A_R >= 1): large smooth-ish penalty keeps trf moving back.
        fit = np.full(k.size, 10.0 + a_right)
    barrier = np.log1p(np.exp(_BARRIER_SCALE * (a_right - _BARRIER_CENTER)))
    return np.concatenate((fit, reg * theta[2:], [barrier]))


def calibrate_slice(
    k: np.ndarray,
    w_quotes: np.ndarray,
    t: float,
    n_order: int = 6,
    weights: np.ndarray | None = None,
    reg_lambda: float = 0.0,
    reg_power: float = 1.0,
    init: LQDParams | None = None,
) -> CalibrationResult:
    """Fit one LQD slice to total-variance quotes (k_i, w_i) at expiry ``t``.

    ``reg_lambda``/``reg_power`` implement the high-order damping
    lam * n^{2r} a_n^2; the first Legendre mode a_2..a_3 is left free.
    """
    k = np.asarray(k, dtype=float)
    w_quotes = np.asarray(w_quotes, dtype=float)
    weights = np.ones_like(k) if weights is None else np.asarray(weights, dtype=float)

    # Quote prices and vega normalizers are fixed during optimization.
    target_price = black_call(k, w_quotes)
    sigma = np.sqrt(w_quotes / t)
    inv_vega = 1.0 / (black_vega_sigma(k, sigma, t) + _VEGA_FLOOR)
    sqrt_weights = np.sqrt(weights)

    # Regularization vector aligned with theta[2:] = (a_2, ..., a_N).
    n_idx = np.arange(2, n_order + 1, dtype=float)
    reg = np.sqrt(reg_lambda) * np.where(n_idx >= 4, n_idx**reg_power, 0.0)

    if init is None:
        w0_guess = float(np.interp(0.0, k, w_quotes))
        init = logistic_init(w0_guess, n_order=n_order)

    result = least_squares(
        _residuals,
        init.to_vector(),
        args=(k, target_price, inv_vega, sqrt_weights, reg),
        method="trf",
        xtol=1e-15,
        ftol=1e-15,
        gtol=1e-15,
        max_nfev=4000,
    )

    params = LQDParams.from_vector(result.x)
    slice_ = build_slice(params)
    iv_model = np.sqrt(slice_.implied_w(k) / t)
    max_iv_error = float(np.nanmax(np.abs(iv_model - sigma)))

    return CalibrationResult(
        params=params,
        slice=slice_,
        cost=float(result.cost),
        n_evaluations=int(result.nfev),
        success=bool(result.success),
        max_iv_error=max_iv_error,
    )
