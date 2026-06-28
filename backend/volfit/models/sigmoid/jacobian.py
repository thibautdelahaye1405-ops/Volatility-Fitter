"""Analytic Jacobian of the Multi-Core SIV calibration residual (FINDINGS R5).

SIV is super-linear in cores (F2) mostly because the ``6 + 4R``-parameter fit had no
analytic Jacobian: scipy's finite differences cost ``6 + 4R + 1`` residual evals per
optimizer step, each looping over all R cores' transcendentals. This differentiates
the model variance ``v_R(z)`` in closed form so the bounded trust-region fit runs ~2
evals/step regardless of R, removing the dominant factor.

It covers the residual configuration the calibrator gates analytic-on — the mid OR
band data term + the hat-amplitude ridge + the optional calendar floor. The var-swap /
strike-gap / operator-prior blocks fall back to the finite-difference Jacobian
(correct, just not accelerated), exactly as LQD and SVI do.

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
from volfit.models.sigmoid.kernels import _hat_norm, hat, hat_p, phi, phi_p

#: Mirrors ``calibrate._V_FLOOR`` (the variance floor under the sqrt); kept in sync.
_V_FLOOR = 1e-8


def _dphi_dkappa(x: np.ndarray, kappa: np.ndarray | float) -> np.ndarray:
    """``dPhi_kappa(x)/dkappa = (-2 Phi(x) + x Phi'(x)) / kappa`` (from eq Phi)."""
    return (-2.0 * phi(x, kappa) + np.asarray(x, float) * phi_p(x, kappa)) / kappa


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


def _hat_grad(z: np.ndarray, c, h, kappa) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """``(B, dB/dc, dB/dh, dB/dkappa)`` for one hat core."""
    u = np.asarray(z, float) - c
    norm = _hat_norm(h, kappa)
    b = hat(z, c, h, kappa)
    db_dc = -hat_p(z, c, h, kappa)
    db_dh = (-phi_p(u - h, kappa) + phi_p(u + h, kappa)) / norm - b * (2.0 * phi_p(h, kappa)) / norm
    draw_dk = _dphi_dkappa(u - h, kappa) - 2.0 * _dphi_dkappa(u, kappa) + _dphi_dkappa(u + h, kappa)
    db_dk = draw_dk / norm - b * (2.0 * _dphi_dkappa(h, kappa)) / norm
    return b, db_dc, db_dh, db_dk


def _model_v_grad(theta: np.ndarray, z: np.ndarray, n_cores: int) -> tuple[np.ndarray, np.ndarray]:
    """``(v_R(z), dv_R/dtheta)`` — variance and its (N, 6+4R) gradient."""
    v, dv_base = _base_grad(z, *theta[:6])
    dv = np.zeros((np.asarray(z).size, 6 + 4 * n_cores))
    dv[:, :6] = dv_base
    for r in range(n_cores):
        alpha, c, h, kappa = theta[6 + 4 * r : 10 + 4 * r]
        b, db_dc, db_dh, db_dk = _hat_grad(z, c, h, kappa)
        v = v + alpha * b
        dv[:, 6 + 4 * r] = b  # alpha
        dv[:, 7 + 4 * r] = alpha * db_dc  # c
        dv[:, 8 + 4 * r] = alpha * db_dh  # h
        dv[:, 9 + 4 * r] = alpha * db_dk  # kappa
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
) -> np.ndarray:
    """Analytic Jacobian (n_residuals x (6+4R)) of the gated SIV residual.

    Rows match ``calibrate._fit.residuals`` under the analytic gate: the fit block
    (mid: N rows; band: 2N rows), the ridge rows, then the calendar rows."""
    v, dv = _model_v_grad(theta, np.asarray(z, float), n_cores)
    model_vol = np.sqrt(np.maximum(v, _V_FLOOR))
    dmv = dv / (2.0 * model_vol)[:, None]
    dmv[v <= _V_FLOOR] = 0.0  # the variance floor flattens the gradient there

    blocks: list[np.ndarray] = []
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

    return np.vstack(blocks)
