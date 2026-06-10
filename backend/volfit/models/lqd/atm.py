"""Exact ATM level / skew / curvature of an LQD slice.

Implements note section 6.1 (Docs/lqd_model_note.tex): the first two
log-strike derivatives of the call at k = 0 are known exactly from the
quantile representation (eqs. C1, C2), and chain-ruling through the Black
formula (eqs. Bk..Bww, w1, w2) yields the actual ATM implied-vol handles
sigma_0, s_0, kappa_0 (eqs. sigma0, skew0, curv0) with no finite differences
of implied volatility.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import expit

from volfit.core.black import atm_total_variance, norm_cdf, norm_pdf
from volfit.models.lqd.basis import g_eval
from volfit.models.lqd.quadrature import LQDSlice


@dataclass(frozen=True)
class ATMHandles:
    """ATM diagnostics of one slice at expiry ``t``."""

    w0: float  # ATM total implied variance
    w1: float  # dw/dk at k = 0
    w2: float  # d2w/dk2 at k = 0
    sigma0: float  # ATM implied volatility
    skew: float  # d sigma / dk at k = 0
    curvature: float  # d2 sigma / dk2 at k = 0


def atm_handles(slice_: LQDSlice, t: float) -> ATMHandles:
    """Compute exact ATM level, skew and curvature for one built slice."""
    # CDF point of the forward ATM strike: Q(z0) = 0  (eq. atm_price_quantities).
    z0 = float(slice_.strike_to_z(0.0))
    u0 = float(expit(z0))

    # ATM density f_X(0) = 1 / q(u0) with q(u) = e^{g(u)} / (u (1-u)).
    g0 = float(g_eval(slice_.params, np.array([u0]))[0])
    f0 = u0 * (1.0 - u0) * np.exp(-g0)

    # Exact call derivatives in log-strike (eqs. C1, C2).
    c0 = float(slice_.call_price(0.0))
    c1 = -(1.0 - u0)
    c2 = f0 - (1.0 - u0)

    # ATM total variance from the closed-form inversion B(0, w) = 2 Phi(sqrt(w)/2) - 1.
    w0 = atm_total_variance(c0)

    # Black partials at k = 0 (eqs. Bk..Bww), with a = sqrt(w0)/2.
    a = 0.5 * np.sqrt(w0)
    n_pdf = float(norm_pdf(a))
    n_cdf = float(norm_cdf(a))
    sqw = np.sqrt(w0)
    b_k = -(1.0 - n_cdf)
    b_w = n_pdf / (2.0 * sqw)
    b_kk = -(1.0 - n_cdf) + n_pdf / sqw
    b_kw = n_pdf / (4.0 * sqw)
    b_ww = -n_pdf / (4.0 * w0 * sqw) - n_pdf / (16.0 * sqw)

    # Implicit differentiation of B(k, w(k)) = C(k)  (eqs. w1, w2).
    w1 = (c1 - b_k) / b_w
    w2 = (c2 - b_kk - 2.0 * b_kw * w1 - b_ww * w1 * w1) / b_w

    # Convert to implied-vol handles (eqs. sigma0, skew0, curv0).
    sigma0 = np.sqrt(w0 / t)
    skew = w1 / (2.0 * np.sqrt(t * w0))
    curvature = w2 / (2.0 * np.sqrt(t * w0)) - w1 * w1 / (4.0 * np.sqrt(t) * w0 * sqw)

    return ATMHandles(
        w0=float(w0),
        w1=float(w1),
        w2=float(w2),
        sigma0=float(sigma0),
        skew=float(skew),
        curvature=float(curvature),
    )
