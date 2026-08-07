"""Normalized Black formula utilities for the Chapter 9 figures.

Everything is in the book's normalized coordinates (Chapter 2 eq. black):
log-moneyness k = log(K/F), total implied variance w, normalized call
B(k, w) = Phi(d+) - e^k Phi(d-) with d± = -k/sqrt(w) ± sqrt(w)/2.
The implied-variance inversion is a plain vectorized bisection -- B is
strictly increasing in w -- accurate far below the chapter's vol-bp scale.
"""

from __future__ import annotations

import numpy as np
from scipy.special import ndtr


def phi(x: np.ndarray) -> np.ndarray:
    """Standard normal density."""
    return np.exp(-0.5 * np.asarray(x, dtype=float) ** 2) / np.sqrt(2.0 * np.pi)


def d_plus(k: np.ndarray, w: np.ndarray) -> np.ndarray:
    sw = np.sqrt(w)
    return -np.asarray(k, dtype=float) / sw + 0.5 * sw


def black_call(k: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Normalized Black call price B(k, w)."""
    k = np.asarray(k, dtype=float)
    sw = np.sqrt(np.asarray(w, dtype=float))
    d_p = -k / sw + 0.5 * sw
    d_m = d_p - sw
    return ndtr(d_p) - np.exp(k) * ndtr(d_m)


def implied_w(k: np.ndarray, price: np.ndarray, n_iter: int = 100) -> np.ndarray:
    """Total implied variance from normalized call prices (bisection).

    Prices outside the static no-arbitrage interval
    (max(1 - e^k, 0), 1) come back as NaN.
    """
    k = np.asarray(k, dtype=float)
    price = np.asarray(price, dtype=float)
    lo = np.full_like(k, 1e-12)
    hi = np.full_like(k, 16.0)
    bad = (price <= np.maximum(1.0 - np.exp(k), 0.0) + 1e-14) | (price >= 1.0)
    for _ in range(n_iter):
        mid = 0.5 * (lo + hi)
        under = black_call(k, mid) < price
        lo = np.where(under, mid, lo)
        hi = np.where(under, hi, mid)
    w = 0.5 * (lo + hi)
    return np.where(bad, np.nan, w)
