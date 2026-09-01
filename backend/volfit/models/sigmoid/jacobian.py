"""Analytic Jacobian of the Multi-Core SIV calibration residual (FINDINGS R5).

SIV is super-linear in cores (F2) mostly because the ``6 + 4R``-parameter fit had no
analytic Jacobian: scipy's finite differences cost ``6 + 4R + 1`` residual evals per
optimizer step, each looping over all R cores' transcendentals. This differentiates
the model variance ``v_R(z)`` in closed form so the bounded trust-region fit runs ~2
evals/step regardless of R, removing the dominant factor.

It covers the residual configuration the calibrator gates analytic-on — the mid OR
band data term (vol space, or vega-normalized price space via ``price_rows.py``
when overlayPriceResiduals is on) + the hat-amplitude ridge + the optional calendar
floor. The var-swap / strike-gap / operator-prior blocks fall back to the
finite-difference Jacobian (correct, just not accelerated), exactly as LQD and SVI do.

The model variance is ``v_R(z) = v_base(z) + Σ_r alpha_r B(z; c_r, h_r, kappa_r)``.
Building blocks (``u = z - z0`` / ``z - c``; ``Phi`` the log-cosh primitive):

  * ``dPhi_kappa(u)/dkappa = (-2 Phi(u) + u Phi'(u)) / kappa``;
  * base: ``dv/dv0=1, dv/ds0=u, dv/dk0=Phi(u), dv/dz0=-v_z`` (the slice is C^2 across
    z0, so the kappa switch adds no delta), and ``dv/dkappa_{p,c}`` active only on
    their own side of z0;
  * hat ``B = raw / norm`` with ``raw = Phi(u-h) - 2Phi(u) + Phi(u+h)``,
    ``norm = 2 Phi(h)``: ``dB/dc = -B'``, and ``dB/dh`` / ``dB/dkappa`` by the quotient
    rule on the same primitives.
"""

from __future__ import annotations

import numpy as np

from volfit.calib.band import BandTarget, band_violation_sign
from volfit.models.sigmoid.kernels import phi, phi_p
from volfit.models.sigmoid.price_rows import price_row_blocks

#: Mirrors ``calibrate._V_FLOOR`` (the variance floor under the sqrt); kept in sync.
_V_FLOOR = 1e-8


def _base_grad(z: np.ndarray, v0, s0, k0, z0, kp, kc) -> tuple[np.ndarray, np.ndarray]:
    """``(v_base, dv_base/dtheta_base)`` — variance and its 6 base partials, (N, 6)."""
    u = np.asarray(z, float) - z0
    kappa = np.where(u < 0.0, kp, kc)
    ph = phi(u, kappa)
    php = phi_p(u, kappa)
    v = v0 + s0 * u + k0 * ph
    vz = s0 + k0 * php
    dphi_dk = (-2.0 * ph + u * php) / kappa  # dPhi/dkappa at (u, kappa)
    dv = np.empty((u.size, 6))
    dv[:, 0] = 1.0  # v0
    dv[:, 1] = u  # s0
    dv[:, 2] = ph  # k0
    dv[:, 3] = -vz  # z0 (= -dv/dz)
    dv[:, 4] = k0 * dphi_dk * (u < 0.0)  # kappa_p (left side only)
    dv[:, 5] = k0 * dphi_dk * (u >= 0.0)  # kappa_c (right side only)
    return v, dv


def _model_v_grad(theta: np.ndarray, z: np.ndarray, n_cores: int) -> tuple[np.ndarray, np.ndarray]:
    """``(v_R(z), dv_R/dtheta)`` — variance and its (N, 6+4R) gradient.

    The hat block evaluates ALL cores' stencils {u_r-h_r, u_r, u_r+h_r, h_r}
    with ONE stacked ``phi`` call and ONE stacked ``phi'`` call (2026-09 perf
    arc): the primitives are elementwise and kappa broadcasts per row, so
    every value is bit-identical to the historical per-core/per-point calls
    (which made ~18 small-array dispatches per core per iterate — the
    profiled MCS hot spot; locked by test_batched_kernels), while the
    dispatch count no longer scales with R. The v-accumulation stays a
    sequential per-core loop to preserve the historical summation order.
    """
    z = np.asarray(z, float)
    v, dv_base = _base_grad(z, *theta[:6])
    dv = np.zeros((z.size, 6 + 4 * n_cores))
    dv[:, :6] = dv_base
    if not n_cores:
        return v, dv
    cores = np.asarray(theta[6 : 6 + 4 * n_cores], float).reshape(n_cores, 4)
    alpha, c, h, kappa = cores[:, 0], cores[:, 1], cores[:, 2], cores[:, 3]
    n = z.size
    u = z[None, :] - c[:, None]  # (R, N)
    hc = h[:, None]
    pts = np.concatenate([u - hc, u, u + hc, hc], axis=1)  # (R, 3N+1)
    ph, php = phi(pts, kappa[:, None]), phi_p(pts, kappa[:, None])
    ph_m, ph_0, ph_p = ph[:, :n], ph[:, n : 2 * n], ph[:, 2 * n : 3 * n]
    pp_m, pp_0, pp_p = php[:, :n], php[:, n : 2 * n], php[:, 2 * n : 3 * n]
    ph_h, pp_h = ph[:, -1:], php[:, -1:]  # (R, 1)
    norm = 2.0 * ph_h
    b = (ph_m - 2.0 * ph_0 + ph_p) / norm
    db_dc = -((pp_m - 2.0 * pp_0 + pp_p) / norm)
    db_dh = (-pp_m + pp_p) / norm - b * (2.0 * pp_h) / norm
    # dPhi/dkappa at each stencil point from the cached (phi, phi') values.
    kcol = kappa[:, None]
    dpk_m = (-2.0 * ph_m + (u - hc) * pp_m) / kcol
    dpk_0 = (-2.0 * ph_0 + u * pp_0) / kcol
    dpk_p = (-2.0 * ph_p + (u + hc) * pp_p) / kcol
    dpk_h = (-2.0 * ph_h + hc * pp_h) / kcol
    db_dk = (dpk_m - 2.0 * dpk_0 + dpk_p) / norm - b * (2.0 * dpk_h) / norm
    for r in range(n_cores):
        v = v + alpha[r] * b[r]
        dv[:, 6 + 4 * r] = b[r]  # alpha
        dv[:, 7 + 4 * r] = alpha[r] * db_dc[r]  # c
        dv[:, 8 + 4 * r] = alpha[r] * db_dh[r]  # h
        dv[:, 9 + 4 * r] = alpha[r] * db_dk[r]  # kappa
    return v, dv


def siv_residual_jacobian(
    theta: np.ndarray,
    z: np.ndarray,
    n_cores: int,
    t: float,
    sqrt_w: np.ndarray,
    band: BandTarget | None,
    mid_anchor_weight: float,
    ridge: float,
    cal_z: np.ndarray | None,
    cal_floor: np.ndarray | None,
    sqrt_cal: float,
    ceil_z: np.ndarray | None = None,
    ceil_w: np.ndarray | None = None,
    price_rows: tuple | None = None,
) -> np.ndarray:
    """Analytic Jacobian (n_residuals x (6+4R)) of the gated SIV residual.

    Rows match ``calibrate._fit.residuals`` under the analytic gate: the fit block
    (mid: N rows; band: 2N rows) — in vol space, or in vega-normalized price
    space when ``price_rows`` (overlayPriceResiduals) is given (price_rows.py) —
    the ridge rows, the calendar floor rows, then the calendar CEILING rows (the
    symmetric overlay repair's two-sided target)."""
    v, dv = _model_v_grad(theta, np.asarray(z, float), n_cores)

    blocks: list[np.ndarray] = []
    if price_rows is not None:
        blocks.extend(price_row_blocks(v, dv, t, price_rows, sqrt_w, mid_anchor_weight))
    else:
        model_vol = np.sqrt(np.maximum(v, _V_FLOOR))
        dmv = dv / (2.0 * model_vol)[:, None]
        dmv[v <= _V_FLOOR] = 0.0  # the variance floor flattens the gradient there
        if band is None:
            blocks.append(sqrt_w[:, None] * dmv)
        else:
            sign = band_violation_sign(model_vol, band.iv_lo, band.iv_hi)
            blocks.append((sqrt_w * sign)[:, None] * dmv)  # band violation rows
            blocks.append((np.sqrt(mid_anchor_weight) * sqrt_w)[:, None] * dmv)  # mid anchor

    # Ridge: sqrt(ridge) * alpha_r — one row per core, derivative only wrt its alpha.
    if n_cores:
        ridge_block = np.zeros((n_cores, theta.size))
        for r in range(n_cores):
            ridge_block[r, 6 + 4 * r] = np.sqrt(ridge)
        blocks.append(ridge_block)

    # Calendar: sqrt_cal * max(cal_floor - v(cal_z)*t, 0); subgradient -sqrt_cal*t*dv.
    if cal_z is not None and cal_floor is not None:
        vc, dvc = _model_v_grad(theta, np.asarray(cal_z, float), n_cores)
        w_model = np.maximum(vc, _V_FLOOR) * t
        active = ((cal_floor - w_model) > 0.0) & (vc > _V_FLOOR)
        blocks.append((-sqrt_cal * t * active)[:, None] * dvc)

    # Ceiling: sqrt_cal * max(v(ceil_z)*t - ceil, 0); subgradient +sqrt_cal*t*dv.
    if ceil_z is not None and ceil_w is not None:
        vc, dvc = _model_v_grad(theta, np.asarray(ceil_z, float), n_cores)
        w_model = np.maximum(vc, _V_FLOOR) * t
        active = ((w_model - ceil_w) > 0.0) & (vc > _V_FLOOR)
        blocks.append((sqrt_cal * t * active)[:, None] * dvc)

    return np.vstack(blocks)
