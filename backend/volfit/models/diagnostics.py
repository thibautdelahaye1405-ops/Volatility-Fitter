"""Model-agnostic smile diagnostics from the SmileModel interface alone.

LQD slices have exact closed-form ATM handles and var-swap level
(models/lqd/atm.py, LQDSlice.var_swap_strike). The other calibratable
families (SVI, sigmoid) expose only total implied variance w(k), so the API
needs the same headline diagnostics computed numerically from w(k):

  * ATM level / skew / curvature as finite differences of sigma(k) =
    sqrt(w(k)/t) at k = 0;
  * var-swap fair variance by log-contract static replication, the
    model-free integral 2 [ int_0^inf B(k,w) e^{-k} dk
    + int_{-inf}^0 (B(k,w) + e^k - 1) e^{-k} dk ] where B is the normalized
    Black call (matches LQDSlice.var_swap_strike = -2 E[X] to grid accuracy);
  * Lee wing slopes dw/d|k| at the far ends of a wide grid.

These power volfit.api.fit_models for non-LQD display fits; the values are
exact for LQD via the dedicated module, so this stays a fallback path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.core.black import black_call
from volfit.models.base import SmileModel

#: Central-difference step in log-moneyness for the ATM handles.
_ATM_H = 1e-3
#: Replication grid for the var-swap integral; +-6 in k captures the OTM
#: option mass to double precision for any reasonable smile.
_VS_HALF_WIDTH = 6.0
_VS_POINTS = 4001


@dataclass(frozen=True)
class SliceHandles:
    """Numeric ATM level/skew/curvature of a smile at expiry ``t``."""

    atm_vol: float
    skew: float
    curvature: float


def numeric_handles(slice_: SmileModel, t: float) -> SliceHandles:
    """ATM vol, skew and curvature by central differences of sqrt(w/t)."""
    h = _ATM_H
    ks = np.array([-h, 0.0, h])
    vol = np.sqrt(np.maximum(slice_.implied_w(ks), 1e-12) / t)
    skew = (vol[2] - vol[0]) / (2.0 * h)
    curvature = (vol[2] - 2.0 * vol[1] + vol[0]) / (h * h)
    return SliceHandles(atm_vol=float(vol[1]), skew=float(skew), curvature=float(curvature))


def numeric_var_swap_w(slice_: SmileModel) -> float:
    """Var-swap fair total variance by OTM log-contract replication.

    Returns w_varswap (same units as LQDSlice.var_swap_strike); the var-swap
    vol is sqrt(w_varswap / t).
    """
    k = np.linspace(-_VS_HALF_WIDTH, _VS_HALF_WIDTH, _VS_POINTS)
    w = np.maximum(slice_.implied_w(k), 1e-12)
    call = black_call(k, w)  # normalized OTM call price B(k, w)
    # OTM integrand: calls (k >= 0) priced directly, puts (k < 0) by parity.
    integrand = call * np.exp(-k)
    put_side = k < 0.0
    integrand[put_side] += 1.0 - np.exp(-k[put_side])  # (e^k - 1) e^{-k}
    return 2.0 * float(np.trapezoid(integrand, k))


def numeric_lee_slopes(slice_: SmileModel) -> tuple[float, float]:
    """Left/right total-variance wing slopes dw/d|k| at +-_VS_HALF_WIDTH."""
    edge = _VS_HALF_WIDTH
    dk = 1e-2
    w_rr = float(slice_.implied_w(edge))
    w_r = float(slice_.implied_w(edge - dk))
    w_ll = float(slice_.implied_w(-edge))
    w_l = float(slice_.implied_w(-edge + dk))
    right = (w_rr - w_r) / dk
    left = (w_ll - w_l) / dk  # dw/d(-k): positive when the left wing rises
    return float(left), float(right)
