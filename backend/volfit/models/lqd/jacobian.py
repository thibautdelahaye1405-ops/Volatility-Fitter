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

Covers every residual configuration except prior-anchor / operator-prior
terms (the caller gates on those); handles mid + bid-ask/haircut band fits,
the high-order regulariser, the soft calendar slack, the A_R barrier, and —
riding the same pass via the nodal quantile sensitivity — the market and
prior var-swap rows (committee revision R5: the gate that used to send every
var-swap-enabled fit to finite differences is lifted).
"""

from __future__ import annotations

import numpy as np
from scipy.special import expit

from volfit.calib.band import band_violation_sign
from volfit.calib.varswap import _W_FLOOR as _VS_W_FLOOR
from volfit.core.black import black_vega_sigma
from volfit.models.lqd.basis import LQDParams, endpoint_scales, legendre_matrix
from volfit.models.lqd.interp import hermite_eval
from volfit.models.lqd.quadrature import _cumquad, build_slice
from volfit.models.lqd.tails import (
    EPS_TAIL,
    continuation_speed,
    tail_mass_and_dlam_left,
    tail_mass_and_dlam_right,
)

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
    params: LQDParams, n_points: int, with_qz: bool = False
) -> tuple:
    """One quadrature pass plus its theta-sensitivities.

    Returns ``(slice_, d_az, d_dadz)``: the built LQDSlice and the nodal
    derivatives of the asset-share curve ``a_z`` and its slope ``dA/dz``
    w.r.t. theta = (L, R, a_2..a_N), stacked as (P, M) arrays. These are all
    the joint symmetric solver (volfit.calib.symmetric) needs to form
    dC/dtheta at arbitrary strikes via ``call_price_rows``; ``residual_jacobian``
    below builds the full single-slice residual Jacobian from the same pass.
    ``with_qz=True`` appends the nodal quantile sensitivity ``d_qz`` (P, M)
    as a fourth element — the var-swap rows need it (the default stays a
    3-tuple because the joint stack star-unpacks it into call_price_rows).

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

    # d(total)/dtheta: body integral + the two tail corrections. In the
    # exponential subclass these are the closed forms; for alpha > 0 the
    # correction is the power-continuation quadrature T(lambda, xbar_end)
    # (volfit.models.lqd.tails), whose theta-dependence enters only through
    # the boundary anchor (dT = T qbar_end) and the tail scale
    # (dT = (dT/dlam) dlam/dtheta) — the same structure as the closed forms.
    d_total = np.trapezoid(mass[None, :] * qbar, z, axis=1)
    t_r = dt_r = 0.0  # alpha_+ > 0 tail mass and its lambda-sensitivity
    if params.alpha_right == 0.0:
        tail_r = float(np.exp(q_bar[-1] - z_max))
        d_total += tail_r * (qbar[:, -1] / (1.0 - a_right) + d_ar / (1.0 - a_right) ** 2)
    else:
        t_r, dt_r = tail_mass_and_dlam_right(
            float(q_bar[-1]), a_right, params.alpha_right, z_max)
        d_total += t_r * qbar[:, -1] + dt_r * d_ar
    if params.alpha_left == 0.0:
        tail_l = float(np.exp(q_bar[0] - z_max))
        d_total += tail_l * (qbar[:, 0] / (1.0 + a_left) - d_al / (1.0 + a_left) ** 2)
    else:
        t_l, dt_l = tail_mass_and_dlam_left(
            float(q_bar[0]), a_left, params.alpha_left, z_max)
        d_total += t_l * qbar[:, 0] + dt_l * d_al
    d_mu = -d_total / total                                # (P,)

    d_qz = d_mu[:, None] + qbar                            # (P, M)
    d_massn = mass_n[None, :] * d_qz                       # d(e^{Q}u(1-u))/dtheta
    rev = np.array([_cumquad(row[::-1], dx=dz, initial=0.0)[::-1] for row in d_massn])
    if params.alpha_right == 0.0:
        # a_z right-tail correction e^{q_z[-1]-z_max}/(1-a_right) (q_z, not q_bar).
        tail_az = float(np.exp(slice_.q_z[-1] - z_max))
        d_az = rev + (tail_az * (d_qz[:, -1] / (1.0 - a_right)
                                 + d_ar / (1.0 - a_right) ** 2))[:, None]
    else:
        # Normalized addon e^{mu} T: d = e^{mu}(d_qz_end T + (dT/dlam) dlam).
        emu = float(np.exp(slice_.mu))
        d_az = rev + (emu * (t_r * d_qz[:, -1] + dt_r * d_ar))[:, None]
    if with_qz:
        return slice_, d_az, -d_massn, d_qz
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


def asset_share_rows(
    slice_, d_az: np.ndarray, d_dadz: np.ndarray, z: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Ledger A(z) and its Jacobian dA/dtheta at arbitrary ranks z.

    The ledger-space analogue of ``call_price_rows`` (tails+calendar arc
    Phase 4): the per-theta nodal sensitivities from ``slice_sensitivities``
    are Hermite-evaluated at FIXED z — the ranks are exogenous constraint
    coordinates (the exchange's active set), so there is no implicit
    dependence to cancel. These are the rows the per-rank calendar-G ledger
    constraints (book ch. 2, eq. globalledgerconstraint) stack in the joint
    symmetric solve. Returns ``(A, dA)`` with shapes (n,), (n, P) — the
    call_price_rows convention.
    """
    p = d_az.shape[0]
    z0, dz = float(slice_.z[0]), slice_._step
    z_arr = np.asarray(z, dtype=float)
    dA = np.array(
        [hermite_eval(z_arr, z0, dz, d_az[j], d_dadz[j]) for j in range(p)]
    ).T
    return np.asarray(slice_.asset_share_at(z_arr), dtype=float), dA


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
    alphas: tuple[float, float],
    n_points: int,
) -> np.ndarray:
    """Analytic Jacobian of ``_residuals`` (prior-anchor/operator gated off).
    Rows are stacked [fit, reg, calendar, barrier, var-swap, prior-var-swap]
    in the residual's order; columns are theta = (L, R, a_2..a_N).  The two
    var-swap rows ride the same pass: with w_vs = -2 int Q u(1-u) dz (the
    slice's closed form), d(w_vs)/dtheta = -2 int (dQ/dtheta) u(1-u) dz from
    the nodal quantile sensitivity, and the vol-space residual chains through
    d(sigma_vs)/dw = 1/(2 sqrt(w_vs t)). ``alphas`` are the fixed tail
    exponents — NO alpha columns (the arc's fixed-alpha policy); the body
    pass is alpha-correct automatically because it reads the slice's own
    dq_dz (g is affine in theta and the gauges are theta-independent), and
    the tail-correction terms branch inside ``slice_sensitivities``."""
    params = LQDParams(
        L=float(theta[0]), R=float(theta[1]), a=theta[2:].copy(),
        alpha_left=alphas[0], alpha_right=alphas[1],
    )
    p = theta.size
    band_mode = price_lo is not None
    n_fit = (2 * k.size) if band_mode else k.size
    n_cal = 0 if cal_z is None else cal_z.size
    n_calk = 0 if cal_k is None else cal_k.size
    n_vs = int(var_swap is not None) + int(prior_var_swap is not None)

    a_left, a_right = endpoint_scales(params)
    # Mirror of the _residuals clamp: keep the rejection rows finite for a
    # wild trial whose endpoint exp overflowed (or went NaN).
    if not np.isfinite(a_right) or a_right > 1e6:
        a_right = 1e6
    d_al, d_ar = _endpoint_grads(a_left, a_right, params.order)

    def infeasible_jac() -> np.ndarray:
        # residual was full(n_fit, 10 + a_right) + reg + zeros(cal) + barrier
        # + zeros for the var-swap rows (their penalty-branch value is 0).
        j_fit = np.tile(d_ar, (n_fit, 1))
        j_cal = np.zeros((n_cal + n_calk, p))
        return np.vstack([j_fit, _reg_jac(reg, p), j_cal, _barrier_row(
            a_right, d_ar, barrier_center, barrier_scale),
            np.zeros((n_vs, p))])

    # --- infeasible tail: reject before building anything. The wall applies
    # only in the exponential subclass; for alpha_+ > 0 the refusal is the
    # saddle guard (eq. operationaltailguard), mirrored here so the analytic
    # path answers the same trials the residual's penalty branch rejects.
    if alphas[1] == 0.0:
        if a_right >= 1.0 - EPS_AR:
            return infeasible_jac()
    elif continuation_speed(a_right, alphas[1], Z_MAX) > 1.0 - EPS_TAIL:
        return infeasible_jac()

    # --- one quadrature pass + its theta-sensitivities (shared helper) ----
    try:
        slice_, d_az, d_dadz, d_qz = slice_sensitivities(
            params, n_points, with_qz=True)
    except ValueError:
        # Interior-excursion overflow (quadrature.EXP_BUDGET): same penalty
        # branch as the residual side, so the analytic path never crashes on
        # a trial the value path merely rejects.
        return infeasible_jac()

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
        a_cal, dA_cal = asset_share_rows(slice_, d_az, d_dadz, cal_z)  # (n_cal, P)
        active = (cal_floor - a_cal > 0.0)[:, None]
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

    # --- var-swap rows (market target, then prior companion; same form) ----
    j_vs: list[np.ndarray] = []
    if n_vs:
        u1mu = slice_.u * expit(-slice_.z)  # u(1-u), wing-stable
        w_vs = float(slice_.var_swap_strike())
        dw_vs = -2.0 * np.trapezoid(d_qz * u1mu[None, :], slice_.z, axis=1)
        # ATM-spread carrier (tail-persistence arc): a spread row subtracts
        # d(sigma_atm)/dtheta. sigma_atm is implicit through the k=0 price,
        # B(0, sigma_atm^2 t) = C(0), so d(sigma_atm) = dC(0)/vega_sigma —
        # the same call_price_rows pass as the fit block. Computed lazily,
        # once, only when some row carries the spread (absolute rows keep the
        # historical expression verbatim — byte-identical Jacobian).
        d_sig_atm = None
        for tgt in (var_swap, prior_var_swap):
            if tgt is None:
                continue
            if w_vs <= _VS_W_FLOOR or tgt.weight <= 0.0:
                j_vs.append(np.zeros((1, p)))  # residual clamped/weightless
            elif tgt.mode == "atm_spread":
                if d_sig_atm is None:
                    k0 = np.array([0.0])
                    _, dC0 = call_price_rows(slice_, d_az, d_dadz, k0)
                    w0 = float(slice_.implied_w(k0)[0])
                    sig0 = float(np.sqrt(max(w0, _VS_W_FLOOR) / tgt.t))
                    vega0 = max(float(black_vega_sigma(k0, np.array([sig0]), tgt.t)[0]), 1e-12)
                    d_sig_atm = dC0[0] / vega0
                j_vs.append((np.sqrt(tgt.weight)
                             * (dw_vs / (2.0 * np.sqrt(w_vs * tgt.t)) - d_sig_atm))[None, :])
            else:
                j_vs.append((np.sqrt(tgt.weight) * dw_vs
                             / (2.0 * np.sqrt(w_vs * tgt.t)))[None, :])

    return np.vstack([j_fit, _reg_jac(reg, p), j_cal, j_calk,
                      _barrier_row(a_right, d_ar, barrier_center, barrier_scale),
                      *j_vs])


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
