"""Analytic Jacobian of the LQD calibration residuals (ROADMAP perf #2).

The dominant cost of ``calibrate_slice`` was the finite-difference Jacobian:
scipy rebuilt the whole quadrature (P+1) times per iteration. Here the Jacobian
of the residual stack w.r.t. ``theta = (L, R, a_2..a_N)`` is propagated in one
quadrature pass, so a fit costs ~one residual eval per iteration instead of P+1.

Key identity (the priced call). With ``C(k) = A(z_k) - e^k (1 - u_k)`` and
``z_k`` solving ``Q(z_k) = k``, at ``z_k`` the asset-share slope
``dA/dz = -e^{Q} u(1-u) = -e^k u_k(1-u_k)`` exactly cancels ``d/dz[e^k(1-u_k)]``,
so the implicit ``z_k`` dependence drops out and

    dC/dtheta = (partial A / partial theta)|_{z fixed at z_k}
              = hermite_eval(z_k;  dA/dtheta nodal,  d(dA/dz)/dtheta nodal).

Every nodal sensitivity comes from differentiating the build_slice pipeline:
g is affine in theta with constant basis ``phi_j`` (dg/dL=1-u, dg/dR=u,
dg/da_n=P_n(1-2u)), so dQ'/dtheta = Q' phi, and the cumulative quadrature /
normalisation / asset-share integral differentiate term by term.

Covers the residual configuration with NO var-swap / prior-anchor terms (the
caller gates on that); handles mid + bid-ask/haircut band fits, the high-order
regulariser, the soft calendar slack, and the A_R barrier — the full residual
vector ``calibrate_slice`` builds in that configuration.
"""

from __future__ import annotations

import numpy as np
from scipy.special import expit

from volfit.calib.band import band_violation_sign
from volfit.models.lqd.basis import LQDParams, endpoint_scales, legendre_matrix
from volfit.models.lqd.interp import hermite_eval
from volfit.models.lqd.quadrature import _cumquad, build_slice

#: Endpoint integrability buffer (mirror of quadrature.EPS_AR for the except path).
from volfit.models.lqd.quadrature import EPS_AR, Z_MAX  # noqa: E402


def _basis_phi(u: np.ndarray, order: int) -> np.ndarray:
    """The constant basis ``phi_j(z) = dg/dtheta_j`` stacked as rows (P x M):
    (1-u) for L, u for R, and P_n(1-2u) for a_n (n = 2..order)."""
    rows = [1.0 - u, u]
    if order >= 2:
        leg = legendre_matrix(order, 1.0 - 2.0 * u)
        rows.extend(leg[2:])
    return np.asarray(rows, dtype=float)


def _endpoint_grads(a_left: float, a_right: float, order: int) -> tuple[np.ndarray, np.ndarray]:
    """(dA_L/dtheta, dA_R/dtheta). A_L=e^{L+sum a_n}, A_R=e^{R+sum (-1)^n a_n}."""
    n = np.arange(2, order + 1)
    d_al = np.concatenate(([1.0, 0.0], np.ones(n.size)))
    d_ar = np.concatenate(([0.0, 1.0], (-1.0) ** n))
    return a_left * d_al, a_right * d_ar


def slice_sensitivities(
    params: LQDParams, n_points: int
) -> tuple[object, np.ndarray, np.ndarray]:
    """One quadrature pass plus its theta-sensitivities.

    Returns ``(slice_, d_az, d_dadz)``: the built LQDSlice and the nodal
    derivatives of the asset-share curve ``a_z`` and its slope ``dA/dz``
    w.r.t. theta = (L, R, a_2..a_N), stacked as (P, M) arrays. These are all
    the joint symmetric solver (volfit.calib.symmetric) needs to form
    dC/dtheta at arbitrary strikes via ``call_price_rows``; ``residual_jacobian``
    below builds the full single-slice residual Jacobian from the same pass.

    Raises ValueError when A_R >= 1 (same contract as build_slice).
    """
    a_left, a_right = endpoint_scales(params)
    d_al, d_ar = _endpoint_grads(a_left, a_right, params.order)

    slice_ = build_slice(params, n_points=n_points)
    z, dz = slice_.z, slice_._step
    z_max = Z_MAX
    u = slice_.u
    mass_n = -slice_.da_dz                 # e^{Q} u(1-u)
    total = float(np.exp(-slice_.mu))      # mu = -log(total)
    q_bar = slice_.q_z - slice_.mu
    mass = mass_n * total                  # e^{q_bar} u(1-u)
    center = n_points // 2

    phi = _basis_phi(u, params.order)                      # (P, M)
    dq_phi = slice_.dq_dz[None, :] * phi                   # d(Q')/dtheta
    qbar = np.array([_cumquad(row, dx=dz, initial=0.0) for row in dq_phi])
    qbar -= qbar[:, center][:, None]                       # anchored, (P, M)

    # d(total)/dtheta: body integral + the two analytic tail corrections.
    d_total = np.trapezoid(mass[None, :] * qbar, z, axis=1)
    tail_r = float(np.exp(q_bar[-1] - z_max))
    tail_l = float(np.exp(q_bar[0] - z_max))
    d_total += tail_r * (qbar[:, -1] / (1.0 - a_right) + d_ar / (1.0 - a_right) ** 2)
    d_total += tail_l * (qbar[:, 0] / (1.0 + a_left) - d_al / (1.0 + a_left) ** 2)
    d_mu = -d_total / total                                # (P,)

    d_qz = d_mu[:, None] + qbar                            # (P, M)
    d_massn = mass_n[None, :] * d_qz                       # d(e^{Q}u(1-u))/dtheta
    rev = np.array([_cumquad(row[::-1], dx=dz, initial=0.0)[::-1] for row in d_massn])
    # a_z right-tail correction e^{q_z[-1]-z_max}/(1-a_right) (note q_z, not q_bar).
    tail_az = float(np.exp(slice_.q_z[-1] - z_max))
    d_az = rev + (tail_az * (d_qz[:, -1] / (1.0 - a_right) + d_ar / (1.0 - a_right) ** 2))[:, None]
    return slice_, d_az, -d_massn


def call_price_rows(
    slice_, d_az: np.ndarray, d_dadz: np.ndarray, k: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Normalized call C(k) and its Jacobian dC/dtheta at arbitrary strikes.

    Uses the module-docstring identity: the implicit z_k dependence cancels,
    so dC/dtheta = hermite_eval(z_k; d_az, d_dadz) at fixed z_k. Returns
    ``(C, dC)`` with shapes (n,), (n, P).
    """
    p = d_az.shape[0]
    z0, dz = float(slice_.z[0]), slice_._step
    z_k = slice_.strike_to_z(k)
    dC = np.array(
        [hermite_eval(z_k, z0, dz, d_az[j], d_dadz[j]) for j in range(p)]
    ).T
    return np.asarray(slice_.call_price(k), dtype=float), dC


def residual_jacobian(
    theta: np.ndarray,
    k: np.ndarray,
    target_price: np.ndarray,
    inv_vega: np.ndarray,
    sqrt_weights: np.ndarray,
    reg: np.ndarray,
    cal_z: np.ndarray | None,
    cal_floor: np.ndarray | None,
    cal_weight: float,
    cal_k: np.ndarray | None,
    cal_pfloor: np.ndarray | None,
    cal_taper: np.ndarray | None,
    price_lo: np.ndarray | None,
    price_hi: np.ndarray | None,
    barrier_center: float,
    barrier_scale: float,
    mid_anchor_weight: float,
    var_swap,  # gated None — present so the signature matches _residuals
    prior_anchor,
    prior_var_swap,
    operator_prior,
    n_points: int,
) -> np.ndarray:
    """Analytic Jacobian of ``_residuals`` (var_swap/prior gated off). Rows are
    stacked [fit, reg, calendar, barrier] in the residual's order; columns are
    theta = (L, R, a_2..a_N)."""
    params = LQDParams.from_vector(theta)
    p = theta.size
    band_mode = price_lo is not None
    n_fit = (2 * k.size) if band_mode else k.size
    n_cal = 0 if cal_z is None else cal_z.size
    n_calk = 0 if cal_k is None else cal_k.size

    a_left, a_right = endpoint_scales(params)
    d_al, d_ar = _endpoint_grads(a_left, a_right, params.order)

    # --- infeasible tail: residual was full(n_fit, 10 + a_right) + reg + barrier
    if a_right >= 1.0 - EPS_AR:
        j_fit = np.tile(d_ar, (n_fit, 1))
        j_cal = np.zeros((n_cal + n_calk, p))
        return np.vstack([j_fit, _reg_jac(reg, p), j_cal, _barrier_row(
            a_right, d_ar, barrier_center, barrier_scale)])

    # --- one quadrature pass + its theta-sensitivities (shared helper) ----
    slice_, d_az, d_dadz = slice_sensitivities(params, n_points)
    z0, dz = float(slice_.z[0]), slice_._step

    # --- fit block: dC/dtheta_j = hermite_eval(z_k; d_az[j], d_dadz[j]) ----
    model_price, dC = call_price_rows(slice_, d_az, d_dadz, k)  # (n_k,), (n_k, P)
    scale = (sqrt_weights * inv_vega)[:, None]
    if band_mode:
        sign = band_violation_sign(model_price, price_lo, price_hi)[:, None]
        j_fit = np.vstack([scale * sign * dC, np.sqrt(mid_anchor_weight) * scale * dC])
    else:
        j_fit = scale * dC

    # --- calendar block: sqrt(w) * relu(floor - A(cal_z)) -----------------
    if n_cal:
        dA_cal = np.array(
            [hermite_eval(cal_z, z0, dz, d_az[j], d_dadz[j]) for j in range(p)]
        ).T  # (n_cal, P)
        active = (cal_floor - slice_.asset_share_at(cal_z) > 0.0)[:, None]
        j_cal = np.sqrt(cal_weight) * (-dA_cal) * active
    else:
        j_cal = np.zeros((0, p))

    # --- confined price-floor block: sqrt(w) * taper * relu(pf - C(cal_k)) --
    # Same dC/dtheta identity as the fit block (implicit z_k dependence drops
    # out), evaluated at the constraint strikes on the common quote support.
    if n_calk:
        c_cal, dC_cal = call_price_rows(slice_, d_az, d_dadz, cal_k)  # (n_calk, P)
        active = (cal_pfloor - c_cal > 0.0)[:, None]
        taper = 1.0 if cal_taper is None else cal_taper[:, None]
        j_calk = np.sqrt(cal_weight) * taper * (-dC_cal) * active
    else:
        j_calk = np.zeros((0, p))

    return np.vstack([j_fit, _reg_jac(reg, p), j_cal, j_calk,
                      _barrier_row(a_right, d_ar, barrier_center, barrier_scale)])


def _reg_jac(reg: np.ndarray, p: int) -> np.ndarray:
    """Jacobian of the reg block ``reg * theta[2:]`` (diag(reg) in the a-columns)."""
    j = np.zeros((reg.size, p))
    for i in range(reg.size):
        j[i, i + 2] = reg[i]
    return j


def _barrier_row(
    a_right: float, d_ar: np.ndarray, center: float, scale: float
) -> np.ndarray:
    """Jacobian row of ``log1p(exp(scale*(a_right-center)))`` w.r.t. theta."""
    sig = float(expit(scale * (a_right - center)))
    return (sig * scale * d_ar)[None, :]
