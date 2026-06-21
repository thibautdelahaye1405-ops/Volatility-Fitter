"""Numba CRR / de-Americanization kernel (speed note Stage 4) — the de-Am hot path.

After Stage 1 (24 bisections) and Stage 3 (pre-screen), the residual cost of
preparing an American chain is still the per-quote binomial inversion: each quote
runs a fixed number of CRR American prices inside a bisection. The NumPy batch
(`core.american.deamericanize_batch`'s fallback) prices all quotes in lockstep,
but it pays two avoidable costs every backward step: NumPy temporary allocations,
and an `exp` over the whole spot lattice to recompute the early-exercise
intrinsic. This module replaces the inversion with a compiled kernel that:

  * runs ONE scalar CRR per quote (size-`n+1` value buffer, no `(n_quote, n)`
    slabs and no per-step NumPy temporaries);
  * precomputes the up-factor powers `u^j` ONCE per price evaluation
    (`pw[j] = u^(j-n)` by a single `exp` + multiplies), so the O(n²) backward
    induction does only multiplies/adds/max — no per-step transcendentals;
  * runs the quote loop under `prange` (`parallel=True, nogil=True`): quotes are
    independent, so the chain inverts across cores.

The bracket-and-bisect logic mirrors the NumPy fallback exactly (same drift-floor
`lo`, same `<=`/`>=`/`<` comparisons whose NaN-falseness reproduces the
fallback's NaN handling for degenerate inputs), so the two agree to tree rounding
(~1e-12 in vol). Numba is a project dependency; if it is unavailable this module
degrades to a no-op decorator and `NUMBA_AVAILABLE` is False, and the caller keeps
the NumPy path.
"""

from __future__ import annotations

import numpy as np

try:  # numba is the accelerator; the NumPy batch is the always-available fallback
    from numba import njit, prange

    NUMBA_AVAILABLE = True
except Exception:  # pragma: no cover - only where numba fails to import
    NUMBA_AVAILABLE = False
    prange = range  # type: ignore

    def njit(*args, **kwargs):  # type: ignore
        def deco(fn):
            return fn

        return deco if not (len(args) == 1 and callable(args[0])) else args[0]


#: Implied-vol bracket ceiling (mirrors core.american.SIGMA_HI as a kernel const).
_SIGMA_HI = 4.0


@njit(cache=True, nogil=True)
def _crr_price(is_call, kk, base, pv_step, sigma, growth, disc, sqdt, n, vals, pw):
    """American CRR price of one quote; NaN if the CRR probability leaves (0, 1).

    ``base``/``pv_step`` are the escrowed lattice base and per-step dividend PV
    add-back (so the actual spot at node (m, i) is ``base * u^(2i-m) + pv_step[m]``,
    matching ``core.american.binomial_price_batch``). ``vals`` (len n+1) and ``pw``
    (len 2n+1) are caller-provided scratch reused across the bisection's evals.
    """
    u = np.exp(sigma * sqdt)
    d = 1.0 / u
    p = (growth - d) / (u - d)
    if not (p > 0.0 and p < 1.0):  # CRR no-arbitrage broken (e.g. near-zero sigma)
        return np.nan
    pu = disc * p
    pd = disc * (1.0 - p)

    # pw[j] = u^(j - n), j in [0, 2n]: one exp, then powers by multiplication.
    pw[0] = np.exp(-n * sigma * sqdt)
    for j in range(1, 2 * n + 1):
        pw[j] = pw[j - 1] * u

    # Terminal layer (m = n): spot_i = base * u^(2i-n) + pv_step[n] = base*pw[2i]+pvN.
    pv_n = pv_step[n]
    for i in range(n + 1):
        spot = base * pw[2 * i] + pv_n
        v = spot - kk if is_call else kk - spot
        vals[i] = v if v > 0.0 else 0.0

    # Backward induction with the American early-exercise floor at every node.
    for m in range(n - 1, -1, -1):
        pv_m = pv_step[m]
        for i in range(m + 1):
            cont = pu * vals[i + 1] + pd * vals[i]
            spot = base * pw[2 * i - m + n] + pv_m
            intr = spot - kk if is_call else kk - spot
            vals[i] = cont if cont > intr else intr
    return vals[0]


@njit(cache=True, nogil=True, parallel=True)
def _deam_kernel(is_call, prices, strikes, base, pv_step, r, q, dt, sqdt, n, bisections, lo):
    """De-Americanize a pre-screened chain: per-quote bracket + fixed bisection.

    Mirrors the NumPy fallback's bracketing (start the upper bracket at
    ``max(0.5, 2*lo)``, double until the model price clears the target or the
    ceiling is hit) and its bisection update, so the recovered sigma matches to
    tree rounding. Returns NaN where no vol in (lo, SIGMA_HI] brackets the price.
    """
    n_q = prices.shape[0]
    out = np.full(n_q, np.nan)
    growth = np.exp((r - q) * dt)
    disc = np.exp(-r * dt)
    for idx in prange(n_q):
        px = prices[idx]
        kk = strikes[idx]
        ic = is_call[idx]
        vals = np.empty(n + 1)  # thread-private scratch (one allocation per quote)
        pw = np.empty(2 * n + 1)

        # Lower bracket at the drift floor: the price must sit above the model
        # price there, else no vol matches (deep-ITM put at its exercise floor).
        crr_lo = _crr_price(ic, kk, base, pv_step, lo, growth, disc, sqdt, n, vals, pw)
        if not (crr_lo <= px):
            continue

        # Upper bracket: double until the model price clears the target.
        hi = max(0.5, 2.0 * lo)
        bracketed = False
        while True:
            crr_hi = _crr_price(ic, kk, base, pv_step, hi, growth, disc, sqdt, n, vals, pw)
            if crr_hi >= px:
                bracketed = True
                break
            hi *= 2.0
            if hi > _SIGMA_HI:
                break
        if not bracketed:
            continue

        # Bisect the bracket a fixed number of times (root above mid -> raise lo).
        a = lo
        b = hi
        for _ in range(bisections):
            mid = 0.5 * (a + b)
            crr_mid = _crr_price(ic, kk, base, pv_step, mid, growth, disc, sqdt, n, vals, pw)
            if crr_mid < px:
                a = mid
            else:
                b = mid
        out[idx] = 0.5 * (a + b)
    return out


def numba_available() -> bool:
    return NUMBA_AVAILABLE


def deamericanize_kernel(
    is_call: np.ndarray,
    prices: np.ndarray,
    strikes: np.ndarray,
    base: float,
    pv_step: np.ndarray,
    r: float,
    q: float,
    dt: float,
    sqdt: float,
    n_steps: int,
    bisections: int,
    lo: float,
) -> np.ndarray:
    """Python entry: coerce to contiguous dtypes and run the compiled kernel."""
    return _deam_kernel(
        np.ascontiguousarray(is_call, dtype=np.bool_),
        np.ascontiguousarray(prices, dtype=np.float64),
        np.ascontiguousarray(strikes, dtype=np.float64),
        float(base),
        np.ascontiguousarray(pv_step, dtype=np.float64),
        float(r),
        float(q),
        float(dt),
        float(sqdt),
        int(n_steps),
        int(bisections),
        float(lo),
    )


_WARMED = False


def warmup() -> None:
    """Trigger JIT compilation (cached to disk) off the hot path."""
    global _WARMED
    if _WARMED or not NUMBA_AVAILABLE:
        return
    pv = np.zeros(9)
    deamericanize_kernel(
        np.array([True, False]), np.array([5.0, 5.0]), np.array([100.0, 100.0]),
        100.0, pv, 0.02, 0.0, 0.5 / 8, float(np.sqrt(0.5 / 8)), 8, 6, 1e-3,
    )
    _WARMED = True
