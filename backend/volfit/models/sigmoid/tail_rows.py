"""Tail-matching rows of the Multi-Core Sigmoid refine (volfit.calib.tails) and
their ANALYTIC Jacobian in the raw parameter space.

The residual block is the generic ``tail_match_residuals`` on the iterate's
total-variance curve w(k) = t v(k / (sigma_ref sqrt t)) and its closed-form
k-space Lee slopes (eq mcsbetak). The Jacobian rides ``jacobian._model_v_grad``
— v(z) and dv/dtheta on any z grid, the same primitive the data rows use —
through ``tail_match_jacobian``: one replication per Jacobian instead of the
2P finite-difference replications that made the bounded solver crawl (a
stiff var-swap row on a 14-parameter slice ran to its evaluation budget in
~45 s; measured on the six-month synthetic node). Raw chart only: the
structural chart chains the 6 base columns in ``calibrate._fit``.
"""

from __future__ import annotations

import numpy as np

from volfit.calib.tails import TailMatchTarget, tail_match_jacobian, tail_match_residuals
from volfit.models.sigmoid.jacobian import _V_FLOOR, _model_v_grad
from volfit.models.sigmoid.seeding import _eval_v
from volfit.models.sigmoid.sigmoid import analytic_lee_slopes


def _lee_of(theta_raw: np.ndarray, sigma_ref: float, t: float) -> tuple[float, float]:
    """Closed-form k-space Lee slopes of the raw base (the kernels are
    zero-wing, so the base decides both tails)."""
    _v0, s0, k0, _z0, kp, kc = (float(x) for x in theta_raw[:6])
    return analytic_lee_slopes(s0 - 2.0 * k0 / kp, s0 + 2.0 * k0 / kc, sigma_ref, t)


def mcs_tail_rows(
    theta_raw: np.ndarray, n_cores: int, sigma_ref: float, t: float, target: TailMatchTarget
) -> np.ndarray:
    """The tail-matching residual block of one raw iterate."""
    scale = sigma_ref * np.sqrt(t)

    def w_of_k(kk: np.ndarray) -> np.ndarray:
        zz = np.asarray(kk, float) / scale
        return np.maximum(_eval_v(theta_raw, zz, n_cores), _V_FLOOR) * t

    return tail_match_residuals(w_of_k, lambda: _lee_of(theta_raw, sigma_ref, t), target)


def mcs_tail_jacobian(
    theta_raw: np.ndarray, n_cores: int, sigma_ref: float, t: float, target: TailMatchTarget
) -> np.ndarray:
    """d(tail rows) / d(raw theta), shape (rows, 6 + 4R) — closed form.

    dw/dtheta = t dv/dtheta where the variance floor does not bind (zero
    there, like the residual's clamp); the Lee slopes beta_L = c (2K0/kappa_P
    - S0) and beta_R = c (S0 + 2K0/kappa_C) with c = sqrt(t)/sigma_ref have
    the three non-zero partials each (S0, K0, their kappa)."""
    scale = sigma_ref * np.sqrt(t)
    n_params = 6 + 4 * n_cores

    def w_grad(kk: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        zz = np.asarray(kk, float) / scale
        v, dv = _model_v_grad(theta_raw, zz, n_cores)
        live = (v > _V_FLOOR)[:, None]
        return np.maximum(v, _V_FLOOR) * t, dv * t * live

    def lee_grad() -> tuple[tuple[float, float], tuple[np.ndarray, np.ndarray]]:
        _v0, s0, k0, _z0, kp, kc = (float(x) for x in theta_raw[:6])
        c = float(np.sqrt(t)) / float(sigma_ref)
        g_l = np.zeros(n_params)
        g_l[1] = -c
        g_l[2] = 2.0 * c / kp
        g_l[4] = -2.0 * c * k0 / (kp * kp)
        g_r = np.zeros(n_params)
        g_r[1] = c
        g_r[2] = 2.0 * c / kc
        g_r[5] = -2.0 * c * k0 / (kc * kc)
        return _lee_of(theta_raw, sigma_ref, t), (g_l, g_r)

    return tail_match_jacobian(w_grad, lee_grad, target)
