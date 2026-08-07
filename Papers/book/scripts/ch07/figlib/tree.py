"""Cox-Ross-Rubinstein trees and the de-Americanizing inversion.

Self-contained numerical core for the Chapter 7 figures: a scalar CRR tree
(continuous carry), a batch tree vectorized across quotes with per-quote
volatilities, an escrowed-dividend variant for discrete cash schedules, the
analytic Black formula and its inversion, and the bracketed-bisection
American inversion the chapter calls de-Americanization.  Everything is
plain NumPy and deterministic; conventions (drift floor, bracket cap,
depths) are the constants stated in appendix 7.A.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

SIGMA_HI = 4.0          # upper volatility bracket cap
SIGMA_LO_MIN = 1e-4     # lower bracket floor before the drift lift
DRIFT_LIFT = 1.5        # safety multiple applied to the CRR drift floor
N_SCALAR = 501          # single-quote tree depth (synthetic exhibits)
N_BATCH = 256           # whole-chain tree depth (real-chain inversions)
N_REF = 4001            # converged reference depth ("true" prices)
BISECTIONS = 48         # bracketed-bisection sweeps of the batch inversion


# ------------------------------------------------------------ Black formula

def black_call_norm(k: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Normalized Black call c(k, w) = Phi(d+) - e^k Phi(d-)."""
    k = np.asarray(k, dtype=float)
    w = np.maximum(np.asarray(w, dtype=float), 1e-16)
    sw = np.sqrt(w)
    d1 = -k / sw + 0.5 * sw
    return norm.cdf(d1) - np.exp(k) * norm.cdf(d1 - sw)


def implied_vol_black(price: np.ndarray, is_call: np.ndarray, K: np.ndarray,
                      F: float, D: float, t: float,
                      iters: int = 96) -> np.ndarray:
    """European Black volatility of dollar prices (parity-normalized).

    Puts are converted to normalized calls by put-call parity before the
    inversion; lanes whose normalized call violates the static bounds
    (1-e^k)^+ < c < 1 return NaN.  Bisection on total variance.
    """
    price = np.asarray(price, dtype=float)
    is_call = np.asarray(is_call, dtype=bool)
    K = np.asarray(K, dtype=float)
    k = np.log(K / F)
    c = price / (D * F) + np.where(is_call, 0.0, 1.0 - np.exp(k))
    ok = (c > np.maximum(1.0 - np.exp(k), 0.0) + 1e-12) & (c < 1.0 - 1e-12)
    lo = np.full(c.shape, 1e-12)
    hi = np.full(c.shape, SIGMA_HI**2 * t)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        below = black_call_norm(k, mid) < c
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    w = 0.5 * (lo + hi)
    return np.where(ok, np.sqrt(w / t), np.nan)


# ------------------------------------------------------------- scalar trees

def crr_price(is_call: bool, S: float, K: float, t: float, sigma: float,
              r: float, q: float, n: int = N_SCALAR,
              american: bool = True) -> float:
    """One CRR tree price under continuous carry (r, q).

    The scalar path is loud: an invalid up-probability (the drift floor of
    eq. 7.x violated) raises instead of mispricing.
    """
    dt = t / n
    u = np.exp(sigma * np.sqrt(dt))
    d = 1.0 / u
    growth = np.exp((r - q) * dt)
    p = (growth - d) / (u - d)
    if not 0.0 < p < 1.0:
        raise ValueError(f"invalid CRR probability p={p:.4f} "
                         f"(sigma below the drift floor?)")
    disc = np.exp(-r * dt)
    pow_table = u ** np.arange(-n, n + 1)          # u^j for j = -n..n
    sT = S * pow_table[np.arange(0, 2 * n + 1, 2)]
    v = np.maximum(sT - K, 0.0) if is_call else np.maximum(K - sT, 0.0)
    for m in range(n - 1, -1, -1):
        v = disc * (p * v[1:] + (1.0 - p) * v[:-1])
        if american:
            sM = S * pow_table[np.arange(n - m, n + m + 1, 2)]
            intr = sM - K if is_call else K - sM
            v = np.maximum(v, intr)
    return float(v[0])


def crr_price_escrow(is_call: bool, S: float, K: float, t: float,
                     sigma: float, r: float,
                     divs: list[tuple[float, float]], n: int = N_SCALAR,
                     american: bool = True) -> float:
    """CRR on the escrowed base: cash dividends (t_i, d_i), zero yield.

    The tree diffuses X_0 = S - PV(dividends); at each layer the true spot
    is the base node plus the present value of the dividends not yet paid,
    and exercise is tested against that spot.  Terminal payoffs use the
    bare base (every scheduled dividend has been paid by expiry).
    """
    divs = [(ti, di) for ti, di in divs if 0.0 < ti <= t]
    pv0 = sum(di * np.exp(-r * ti) for ti, di in divs)
    X0 = S - pv0
    if X0 <= 0.0:
        raise ValueError("escrow base is non-positive")
    dt = t / n
    u = np.exp(sigma * np.sqrt(dt))
    d = 1.0 / u
    p = (np.exp(r * dt) - d) / (u - d)
    if not 0.0 < p < 1.0:
        raise ValueError(f"invalid CRR probability p={p:.4f}")
    disc = np.exp(-r * dt)
    pow_table = u ** np.arange(-n, n + 1)
    xT = X0 * pow_table[np.arange(0, 2 * n + 1, 2)]
    v = np.maximum(xT - K, 0.0) if is_call else np.maximum(K - xT, 0.0)
    for m in range(n - 1, -1, -1):
        v = disc * (p * v[1:] + (1.0 - p) * v[:-1])
        if american:
            tm = m * dt
            pv_rem = sum(di * np.exp(-r * (ti - tm))
                         for ti, di in divs if ti > tm)
            sM = X0 * pow_table[np.arange(n - m, n + m + 1, 2)] + pv_rem
            intr = sM - K if is_call else K - sM
            v = np.maximum(v, intr)
    return float(v[0])


# -------------------------------------------------------------- batch trees

def crr_batch(is_call: np.ndarray, S: float, K: np.ndarray, t: float,
              sigma: np.ndarray, r: float, q: float, n: int = N_BATCH,
              american: bool = True) -> np.ndarray:
    """CRR prices for many quotes at once, each lane its own volatility.

    The batch path is silent: lanes whose up-probability leaves (0,1)
    return NaN and the rest of the chain proceeds.
    """
    is_call = np.asarray(is_call, dtype=bool)
    K = np.asarray(K, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    m_lanes = sigma.size
    dt = t / n
    u = np.exp(sigma * np.sqrt(dt))                 # (m,)
    d = 1.0 / u
    growth = np.exp((r - q) * dt)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = (growth - d) / (u - d)
    bad = ~((p > 0.0) & (p < 1.0))
    p = np.where(bad, 0.5, p)                       # placeholder; masked later
    disc = np.exp(-r * dt)
    # u^j per lane for j = -n..n: (m, 2n+1) via one exp of an outer product.
    j = np.arange(-n, n + 1)
    pow_table = np.exp(np.log(u)[:, None] * j[None, :])
    sT = S * pow_table[:, np.arange(0, 2 * n + 1, 2)]
    Kc = K[:, None]
    v = np.where(is_call[:, None], sT - Kc, Kc - sT)
    v = np.maximum(v, 0.0)
    pc = p[:, None]
    for m in range(n - 1, -1, -1):
        v = disc * (pc * v[:, 1:m + 2] + (1.0 - pc) * v[:, :m + 1])
        if american:
            sM = S * pow_table[:, np.arange(n - m, n + m + 1, 2)]
            intr = np.where(is_call[:, None], sM - Kc, Kc - sM)
            v = np.maximum(v, intr)
    out = v[:, 0].astype(float)
    out[bad] = np.nan
    return out


def deamericanize_batch(mids: np.ndarray, is_call: np.ndarray, K: np.ndarray,
                        S: float, t: float, r: float, q: float,
                        n: int = N_BATCH, iters: int = BISECTIONS
                        ) -> np.ndarray:
    """The de-Americanizing root find sigma*: A(sigma*) = quoted mid.

    Vectorized bracketed bisection through the American batch tree.  The
    lower bracket sits above the CRR drift floor; the upper bracket is the
    cap SIGMA_HI.  Lanes with a broken price (below intrinsic, above the
    static cap) or without a sign change on the bracket -- the intrinsic
    plateau -- return NaN: those quotes carry no volatility.
    """
    mids = np.asarray(mids, dtype=float)
    is_call = np.asarray(is_call, dtype=bool)
    K = np.asarray(K, dtype=float)
    intr = np.maximum(np.where(is_call, S - K, K - S), 0.0)
    cap = np.where(is_call, S, K)
    lo_val = max(SIGMA_LO_MIN, DRIFT_LIFT * abs(r - q) * np.sqrt(t / n))
    lo = np.full(mids.shape, lo_val)
    hi = np.full(mids.shape, SIGMA_HI)
    a_lo = crr_batch(is_call, S, K, t, lo, r, q, n)
    a_hi = crr_batch(is_call, S, K, t, hi, r, q, n)
    ok = (mids > intr) & (mids < cap) & (a_lo <= mids) & (a_hi >= mids)
    ok &= np.isfinite(a_lo) & np.isfinite(a_hi)
    for _ in range(iters):
        mid_sig = 0.5 * (lo + hi)
        a_mid = crr_batch(is_call, S, K, t, mid_sig, r, q, n)
        below = a_mid < mids
        lo = np.where(below, mid_sig, lo)
        hi = np.where(below, hi, mid_sig)
    sigma = 0.5 * (lo + hi)
    return np.where(ok, sigma, np.nan)


def premium_batch(sigma: np.ndarray, is_call: np.ndarray, K: np.ndarray,
                  S: float, t: float, r: float, q: float,
                  n: int = N_BATCH) -> np.ndarray:
    """Model premium A - E at the given per-lane volatilities (clamped >= 0)."""
    a = crr_batch(is_call, S, K, t, sigma, r, q, n, american=True)
    e = crr_batch(is_call, S, K, t, sigma, r, q, n, american=False)
    return np.maximum(a - e, 0.0)
