"""Normalized Black formula and implied total-variance inversion.

All prices are *normalized, undiscounted forward* prices: the call on
Y = S_T / F_T with log-moneyness k = log(K / F_T) is

    B(k, w) = Phi(d+) - e^k Phi(d-),   d± = -k/sqrt(w) ± sqrt(w)/2,

where w = sigma_BS^2 * T is total implied variance
(eq. (black) of Docs/lqd_model_note.tex).
"""

from __future__ import annotations

import numpy as np
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


def _invert_w_newton(k: np.ndarray, price: np.ndarray, intrinsic: np.ndarray) -> np.ndarray:
    """Implied total variance for non-ATM, in-bounds quotes (safeguarded Newton).

    B(k, .) is strictly increasing, so a single bracket per quote frames the
    root; each iterate takes a Newton step (analytic dB/dw = black_vega_w) when
    it stays inside the bracket and reduces the residual, falling back to a
    bisection otherwise. This ``rtsafe`` scheme keeps Newton's quadratic
    convergence while never diverging, and runs on the whole array at once.
    Quotes whose price is unreachable for w <= W_MAX (too close to the forward)
    return nan, matching the previous scalar bracket-expansion behaviour.
    """
    lo = np.full(k.shape, W_MIN)
    hi = np.ones(k.shape)
    # Grow the upper bracket geometrically until B(k, hi) >= price (or W_MAX).
    for _ in range(64):
        grow = (black_call(k, hi) < price) & (hi < W_MAX)
        if not grow.any():
            break
        hi = np.where(grow, np.minimum(hi * 4.0, W_MAX), hi)
    unreachable = black_call(k, hi) < price  # not invertible within [W_MIN, W_MAX]

    # Brenner-Subrahmanyam ATM seed w ~ 2*pi*(time value)^2, framed by the bracket.
    w = np.clip(2.0 * np.pi * (price - intrinsic) ** 2, lo, hi)
    for _ in range(80):
        f = black_call(k, w) - price
        hi = np.where(f > 0.0, w, hi)  # B increasing: tighten the bracket by sign
        lo = np.where(f < 0.0, w, lo)
        vega = black_vega_w(k, w)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            w_newton = w - f / vega
        take_newton = (w_newton > lo) & (w_newton < hi) & (vega > 0.0) & np.isfinite(w_newton)
        w_next = np.where(take_newton, w_newton, 0.5 * (lo + hi))
        step = np.abs(w_next - w)
        w = w_next
        if np.all(step <= 1e-14 * np.maximum(w, 1.0)):
            break
    return np.where(unreachable, np.nan, w)


def implied_total_variance(k: np.ndarray | float, price: np.ndarray | float) -> np.ndarray:
    """Vectorized implied total variance w(k) from normalized call prices.

    Returns nan where the price violates the static no-arbitrage bounds
    ((1-e^k)^+ < C < 1) or is unreachable for w <= W_MAX. ATM (|k| ~ 0) uses the
    closed-form inversion; every other quote is solved by a vectorized
    safeguarded Newton iteration (``_invert_w_newton``) — matching the former
    per-strike Brent solver to ~1e-13 while pricing the whole curve at once.
    """
    k_arr = np.atleast_1d(np.asarray(k, dtype=float))
    p_arr = np.atleast_1d(np.asarray(price, dtype=float))
    k_b, p_b = np.broadcast_arrays(k_arr, p_arr)
    kf = np.ascontiguousarray(k_b).ravel()
    pf = np.ascontiguousarray(p_b).ravel()

    out = np.full(kf.shape, np.nan)
    intrinsic = np.maximum(1.0 - np.exp(kf), 0.0)
    valid = (pf > intrinsic) & (pf < 1.0)
    if valid.any():
        kk, pp, ii = kf[valid], pf[valid], intrinsic[valid]
        w = np.empty(kk.shape)
        atm = np.abs(kk) < 1e-14
        if atm.any():  # closed form B(0, w) = 2 Phi(sqrt(w)/2) - 1
            w[atm] = (2.0 * norm_ppf(0.5 * (pp[atm] + 1.0))) ** 2
        if (~atm).any():
            w[~atm] = _invert_w_newton(kk[~atm], pp[~atm], ii[~atm])
        out[valid] = w

    out = out.reshape(k_b.shape)
    return out if np.ndim(k) or np.ndim(price) else out.reshape(())


def implied_vol(k: np.ndarray | float, price: np.ndarray | float, t: float) -> np.ndarray:
    """Implied Black volatility sigma(k) = sqrt(w(k) / T)."""
    return np.sqrt(implied_total_variance(k, price) / t)
