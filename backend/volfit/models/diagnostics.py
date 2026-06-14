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
#: Density grid: log-return support in +-_DENSITY_SD ATM standard deviations,
#: sampled at _DENSITY_POINTS for the risk-neutral pdf / CDF.
_DENSITY_SD = 8.0
_DENSITY_POINTS = 1201
_DENSITY_MIN_HALF = 0.30  # floor on the half-width for very short maturities


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


def weighted_rms_vol(
    slice_: SmileModel,
    k: np.ndarray,
    w: np.ndarray,
    t: float,
    weights: np.ndarray | None = None,
) -> float:
    """Weighted RMS implied-vol error of a slice vs total-variance quotes.

    sqrt(sum_i u_i (sigma_model - sigma_quote)^2 / sum_i u_i) in decimal vol,
    with u_i the per-quote weights (None = equal). sigma = sqrt(w / t).
    """
    k = np.asarray(k, dtype=float)
    if k.size == 0:
        return 0.0
    model_vol = np.sqrt(np.maximum(slice_.implied_w(k), 1e-12) / t)
    quote_vol = np.sqrt(np.maximum(np.asarray(w, dtype=float), 1e-12) / t)
    sq = (model_vol - quote_vol) ** 2
    if weights is None:
        return float(np.sqrt(np.mean(sq)))
    weights = np.asarray(weights, dtype=float)
    return float(np.sqrt(np.sum(weights * sq) / np.sum(weights)))


def numeric_density(slice_: SmileModel) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Risk-neutral log-return density and CDF of any slice from w(k) alone.

    Breeden-Litzenberger via the Durrleman/Gatheral functional: with total
    variance w(k), k = log(K/F), the density of the log-return X = log(S_T/F)
    (forward measure) is

        p(k) = g(k) / sqrt(2 pi w(k)) * exp(-d_-(k)^2 / 2),
        d_-(k) = -k / sqrt(w) - sqrt(w) / 2,
        g(k) = (1 - k w'/(2w))^2 - (w'/2)^2 (1/w + 1/4) + w''/2,

    matching LQDSlice's exact density on an LQD slice and giving the SVI /
    Multi-Core-SIV overlays their own density. w', w'' are central differences;
    a non-arbitrage-free overlay can make g (hence p) dip below zero, so the pdf
    is floored at 0 and renormalized. Returns ``(k, pdf, cdf)`` on a shared grid.
    """
    sd = float(np.sqrt(max(float(slice_.implied_w(0.0)), 1e-8)))
    half = max(_DENSITY_SD * sd, _DENSITY_MIN_HALF)
    k = np.linspace(-half, half, _DENSITY_POINTS)
    w = np.maximum(np.asarray(slice_.implied_w(k), dtype=float), 1e-12)
    wk = np.gradient(w, k)
    wkk = np.gradient(wk, k)
    g = (1.0 - k * wk / (2.0 * w)) ** 2 - 0.25 * wk**2 * (1.0 / w + 0.25) + 0.5 * wkk
    sqrt_w = np.sqrt(w)
    d_minus = -k / sqrt_w - 0.5 * sqrt_w
    pdf = np.maximum(g, 0.0) / np.sqrt(2.0 * np.pi * w) * np.exp(-0.5 * d_minus**2)
    area = float(np.trapezoid(pdf, k))
    if area > 0.0:
        pdf = pdf / area
    cdf = np.concatenate([[0.0], np.cumsum(0.5 * (pdf[1:] + pdf[:-1]) * np.diff(k))])
    return k, pdf, np.clip(cdf, 0.0, 1.0)


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
