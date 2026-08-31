"""Normalized Black formula and implied total-variance inversion.

All prices are *normalized, undiscounted forward* prices: the call on
Y = S_T / F_T with log-moneyness k = log(K / F_T) is

    B(k, w) = Phi(d+) - e^k Phi(d-),   d± = -k/sqrt(w) ± sqrt(w)/2,

where w = sigma_BS^2 * T is total implied variance
(eq. (black) of Docs/lqd_model_note.tex).
"""

from __future__ import annotations

import numpy as np
from scipy.special import erf, erfc, erfinv

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


def _phi(x: np.ndarray) -> np.ndarray:
    """Phi via 0.5 erfc(-x/sqrt2): full RELATIVE accuracy into the lower tail
    (down to ~1e-308), where the 0.5 (1 + erf) form of ``norm_cdf`` cancels to
    ~1e-16 ABSOLUTE noise and rounds to exactly 0 beyond x ~ -8.3. Short-dated
    wing inversion lives entirely below that floor. ``norm_cdf``/``black_call``
    keep the historical evaluation — every calibration target is built on them."""
    return 0.5 * erfc(-np.asarray(x, dtype=float) / SQRT2)


def black_otm(k: np.ndarray | float, w: np.ndarray | float) -> np.ndarray:
    """Normalized Black price of the OTM instrument: the call for k >= 0, the
    put for k < 0, tail-accurate; supports broadcasting.

    Uses the parity symmetry P(k, w) = e^k B(-k, w), so one call evaluation at
    |k| serves both sides, with ``_phi`` carrying relative precision down to
    the price's double-precision floor: a 2-day far-wing option prices at
    ~1e-40 — perfectly representable, yet invisible to ``black_call``, whose
    erf-based CDF is quantized in ~1e-16 absolute steps. The OTM intrinsic is
    zero, so w <= W_MIN degenerates to 0 and the price IS the time value.
    """
    k = np.asarray(k, dtype=float)
    w = np.asarray(w, dtype=float)
    k_abs = np.abs(k)
    sq = np.sqrt(np.maximum(w, W_MIN))
    d_plus = -k_abs / sq + 0.5 * sq
    price = _phi(d_plus) - np.exp(k_abs) * _phi(d_plus - sq)
    price = np.where(k < 0.0, np.exp(k) * price, price)
    # The subtraction can leave a tiny negative at the underflow floor; the
    # OTM price is >= 0 by static no-arbitrage and the inversion brackets by sign.
    return np.where(w > W_MIN, np.maximum(price, 0.0), 0.0)


def _invert_w_newton(k: np.ndarray, price: np.ndarray) -> np.ndarray:
    """Implied total variance for non-ATM, in-bounds OTM quotes (safeguarded
    Newton).

    ``price`` is the OTM instrument's price (call at k >= 0, put below).
    B_otm(k, .) is strictly increasing with dB/dw = black_vega_w (parity: the
    put and the call share vega), so a single bracket per quote frames the
    root; each iterate takes a Newton step when it stays inside the bracket,
    falling back to a bisection otherwise. This ``rtsafe`` scheme keeps
    Newton's quadratic convergence while never diverging, and runs on the
    whole array at once. Quotes whose price is unreachable for w <= W_MAX
    (too close to the upper bound) return nan.
    """
    lo = np.full(k.shape, W_MIN)
    hi = np.ones(k.shape)
    # Grow the upper bracket geometrically until B(k, hi) >= price (or W_MAX).
    for _ in range(64):
        grow = (black_otm(k, hi) < price) & (hi < W_MAX)
        if not grow.any():
            break
        hi = np.where(grow, np.minimum(hi * 4.0, W_MAX), hi)
    unreachable = black_otm(k, hi) < price  # not invertible within [W_MIN, W_MAX]

    # Brenner-Subrahmanyam ATM seed w ~ 2*pi*(time value)^2 (the OTM price IS
    # the time value), framed by the bracket.
    w = np.clip(2.0 * np.pi * price * price, lo, hi)
    for _ in range(80):
        b = black_otm(k, w)
        f = b - price
        hi = np.where(f > 0.0, w, hi)  # B increasing: tighten the bracket by sign
        lo = np.where(f < 0.0, w, lo)
        vega = black_vega_w(k, w)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            # Newton on LOG price: deep OTM, B(w) ~ exp(-k^2 / 2w) spans
            # hundreds of e-folds across the bracket and raw-price Newton
            # gains only ~one e-fold per step (it stays inside the bracket,
            # so the bisection safeguard never rescues it); ln B is nearly
            # affine in the tail, and for body quotes the step matches raw
            # Newton to first order. b = 0 yields nan -> bisection.
            w_newton = w - np.log(b / price) * b / vega
        take_newton = (w_newton > lo) & (w_newton < hi) & (vega > 0.0) & np.isfinite(w_newton)
        w_next = np.where(take_newton, w_newton, 0.5 * (lo + hi))
        step = np.abs(w_next - w)
        w = w_next
        if np.all(step <= 1e-14 * np.maximum(w, 1.0)):
            break
    return np.where(unreachable, np.nan, w)


def implied_total_variance_otm(
    k: np.ndarray | float, price: np.ndarray | float
) -> np.ndarray:
    """Vectorized implied total variance from normalized OTM prices (the put
    for k < 0, the call at k >= 0).

    The OTM instrument's intrinsic is zero, so its price IS its time value: a
    pricer that can evaluate the OTM side directly (LQDSlice prices left-wing
    puts on their own quadrature side) must hand it over here rather than as a
    call near intrinsic, whose time value has already been rounded away at
    ~1e-16 absolute — the short-dated flat-left-wing display bug. Returns nan
    where the price violates the static bounds (0 < P < min(1, e^k)) or is
    unreachable for w <= W_MAX; ATM (|k| ~ 0) uses the closed-form inversion
    (the put and the call coincide at k = 0).
    """
    k_arr = np.atleast_1d(np.asarray(k, dtype=float))
    p_arr = np.atleast_1d(np.asarray(price, dtype=float))
    k_b, p_b = np.broadcast_arrays(k_arr, p_arr)
    kf = np.ascontiguousarray(k_b).ravel()
    pf = np.ascontiguousarray(p_b).ravel()

    out = np.full(kf.shape, np.nan)
    upper = np.where(kf < 0.0, np.exp(kf), 1.0)
    valid = (pf > 0.0) & (pf < upper)
    if valid.any():
        kk, pp = kf[valid], pf[valid]
        w = np.empty(kk.shape)
        atm = np.abs(kk) < 1e-14
        if atm.any():  # closed form B(0, w) = 2 Phi(sqrt(w)/2) - 1
            w[atm] = (2.0 * norm_ppf(0.5 * (pp[atm] + 1.0))) ** 2
        if (~atm).any():
            w[~atm] = _invert_w_newton(kk[~atm], pp[~atm])
        out[valid] = w

    out = out.reshape(k_b.shape)
    return out if np.ndim(k) or np.ndim(price) else out.reshape(())


def implied_total_variance(k: np.ndarray | float, price: np.ndarray | float) -> np.ndarray:
    """Vectorized implied total variance w(k) from normalized CALL prices.

    ITM calls (k < 0) are converted to the OTM put by parity and every quote
    is inverted through the tail-accurate OTM map — the parity subtraction
    here can only keep whatever time-value precision the incoming call price
    still carries, so a caller that can price the OTM side directly should
    use ``implied_total_variance_otm`` instead (LQDSlice.implied_w does).
    Same contract as always: nan where the price violates the static bounds
    ((1-e^k)^+ < C < 1) or is unreachable for w <= W_MAX; body-region roots
    match the former black_call-based Newton to ~1e-13.
    """
    k_arr = np.asarray(k, dtype=float)
    p_arr = np.asarray(price, dtype=float)
    otm = np.where(k_arr < 0.0, p_arr - 1.0 + np.exp(k_arr), p_arr)
    return implied_total_variance_otm(k_arr, otm)


def implied_vol(k: np.ndarray | float, price: np.ndarray | float, t: float) -> np.ndarray:
    """Implied Black volatility sigma(k) = sqrt(w(k) / T)."""
    return np.sqrt(implied_total_variance(k, price) / t)
