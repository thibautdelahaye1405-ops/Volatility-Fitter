"""Normalized Black formula and implied total-variance inversion.

All prices are *normalized, undiscounted forward* prices: the call on
Y = S_T / F_T with log-moneyness k = log(K / F_T) is

    B(k, w) = Phi(d+) - e^k Phi(d-),   d± = -k/sqrt(w) ± sqrt(w)/2,

where w = sigma_BS^2 * T is total implied variance
(eq. (black) of Docs/lqd_model_note.tex).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.special import erf, erfinv

SQRT2 = np.sqrt(2.0)

# Inversion bracket: total variance from ~0 (vol 0.1% over 1d) to 400% vol over 4y.
W_MIN = 1e-12
W_MAX = 64.0


def norm_cdf(x: np.ndarray | float) -> np.ndarray | float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + erf(np.asarray(x) / SQRT2))


def norm_ppf(p: np.ndarray | float) -> np.ndarray | float:
    """Standard normal quantile (inverse CDF)."""
    return SQRT2 * erfinv(2.0 * np.asarray(p) - 1.0)


def norm_pdf(x: np.ndarray | float) -> np.ndarray | float:
    """Standard normal density."""
    x = np.asarray(x)
    return np.exp(-0.5 * x * x) / np.sqrt(2.0 * np.pi)


def black_call(k: np.ndarray | float, w: np.ndarray | float) -> np.ndarray:
    """Normalized Black call price B(k, w); supports broadcasting.

    At w -> 0 the price degenerates to intrinsic (1 - e^k)^+.
    """
    k = np.asarray(k, dtype=float)
    w = np.asarray(w, dtype=float)
    intrinsic = np.maximum(1.0 - np.exp(k), 0.0)
    w_safe = np.maximum(w, W_MIN)
    sq = np.sqrt(w_safe)
    d_plus = -k / sq + 0.5 * sq
    d_minus = d_plus - sq
    price = norm_cdf(d_plus) - np.exp(k) * norm_cdf(d_minus)
    return np.where(w > W_MIN, price, intrinsic)


def black_vega_w(k: np.ndarray | float, w: np.ndarray | float) -> np.ndarray:
    """dB/dw, the sensitivity to *total variance* (always positive for w > 0)."""
    k = np.asarray(k, dtype=float)
    w = np.maximum(np.asarray(w, dtype=float), W_MIN)
    sq = np.sqrt(w)
    d_plus = -k / sq + 0.5 * sq
    return norm_pdf(d_plus) / (2.0 * sq)


def black_vega_sigma(k: np.ndarray | float, sigma: np.ndarray | float, t: float) -> np.ndarray:
    """dB/dsigma = phi(d+) * sqrt(T), the Black vega in volatility units."""
    sigma = np.asarray(sigma, dtype=float)
    w = np.maximum(sigma * sigma * t, W_MIN)
    sq = np.sqrt(w)
    d_plus = -np.asarray(k, dtype=float) / sq + 0.5 * sq
    return norm_pdf(d_plus) * np.sqrt(t)


def atm_total_variance(price_atm: float) -> float:
    """Closed-form ATM inversion: B(0, w) = 2 Phi(sqrt(w)/2) - 1."""
    if not 0.0 < price_atm < 1.0:
        raise ValueError(f"ATM call price must be in (0, 1), got {price_atm}")
    return float((2.0 * norm_ppf(0.5 * (price_atm + 1.0))) ** 2)


def _implied_w_scalar(k: float, price: float) -> float:
    """Implied total variance for one strike via Brent root-finding.

    Returns nan when the price violates static bounds ((1-e^k)^+ < C < 1).
    """
    intrinsic = max(1.0 - np.exp(k), 0.0)
    if not intrinsic < price < 1.0:
        return np.nan
    if abs(k) < 1e-14:
        return atm_total_variance(price)

    def objective(w: float) -> float:
        return float(black_call(k, w)) - price

    lo, hi = W_MIN, 1.0
    # Expand the upper bracket until the Black price exceeds the target.
    while objective(hi) < 0.0:
        hi *= 4.0
        if hi > W_MAX:
            return np.nan
    return float(brentq(objective, lo, hi, xtol=1e-14, rtol=8.9e-16, maxiter=200))


def implied_total_variance(k: np.ndarray | float, price: np.ndarray | float) -> np.ndarray:
    """Vectorized implied total variance w(k) from normalized call prices."""
    k_arr = np.atleast_1d(np.asarray(k, dtype=float))
    p_arr = np.atleast_1d(np.asarray(price, dtype=float))
    k_b, p_b = np.broadcast_arrays(k_arr, p_arr)
    out = np.empty(k_b.shape, dtype=float)
    flat_k, flat_p, flat_o = k_b.ravel(), p_b.ravel(), out.ravel()
    for i in range(flat_k.size):
        flat_o[i] = _implied_w_scalar(float(flat_k[i]), float(flat_p[i]))
    return out if np.ndim(k) or np.ndim(price) else out.reshape(())


def implied_vol(k: np.ndarray | float, price: np.ndarray | float, t: float) -> np.ndarray:
    """Implied Black volatility sigma(k) = sqrt(w(k) / T)."""
    return np.sqrt(implied_total_variance(k, price) / t)
