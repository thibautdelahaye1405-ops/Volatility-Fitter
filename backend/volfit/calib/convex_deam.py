"""Wing-only convex repair of de-Americanized call prices (FINDINGS_calibration_arb R3).

De-Americanization strips the early-exercise premium **per strike independently**
(its own CRR root-find) and clamps it at ``max(EEP, 0)``. With no cross-strike
coupling, the resulting European-equivalent call curve ``C(K)`` can come out locally
**non-convex** in strike — most often in the sparse, low-vega wings. Convexity of
``C(K)`` is exactly the no-butterfly-arbitrage condition (the risk-neutral density is
``f = d²C/dK² ≥ 0``), so a non-convex curve is butterfly-arbitrageable input handed
to every model.

A first fix projected the WHOLE curve onto the convex cone with a free affine part;
minimising the global L2 residual to repair a wing also tilted the baseline and
nudged the ATM call price — a sub-penny move, but huge in ATM IV (vega), the
"ATM smile gap" seen live on SPY/NVDA. It was reverted.

This redesign confines the repair to the wings and **never moves the ATM core**.
Strikes within ``z_core`` ATM-standard-deviations of the forward are held EXACTLY
fixed; each wing is repaired by a small bounded least squares anchored at the trusted
core boundary, so the dense high-vega ATM region is byte-identical by construction
while only the low-vega wings — where the de-Am non-convexity actually lives — move.

All math is on the call price as a function of **strike** ``K`` (convexity in K is the
no-butterfly condition, not convexity in log-moneyness). Pure NumPy + one
``scipy.optimize.lsq_linear`` per non-convex wing.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import lsq_linear

#: Strikes within Z_CORE ATM-std of the forward are the trusted ATM core (dense,
#: high-vega) — NEVER moved by the repair (byte-identical). The correction is
#: confined to the wings beyond it.
Z_CORE = 1.0

#: Convexity short-circuit: if the most-negative normalized butterfly is above
#: -CONVEX_TOL the curve is left untouched (no-op, byte-identical, fast). Calibrated
#: on the captured American fixtures: DENSE liquid chains (NVDA/JPM) carry only
#: de-Am noise, clustering at ~-3e-4 normalized-price butterflies; genuinely
#: arbitraged ILLIQUID wings (EEM/EFA) run -1e-3 to -3e-2. The 1e-3 threshold sits
#: in that gap, so liquid names are never perturbed and only real wing arb is
#: repaired (~10-15% of American nodes, matching the F3b finding).
CONVEX_TOL = 1e-3


def min_norm_butterfly(strikes: np.ndarray, c: np.ndarray) -> float:
    """Most-negative normalized butterfly of a call curve (≥ 0 ⇔ convex in strike).

    The divided second difference ``c_{i-1}(K_{i+1}-K_i) - c_i(K_{i+1}-K_{i-1}) +
    c_{i+1}(K_i-K_{i-1})`` is ≥ 0 iff ``C`` is convex at strike i; dividing by the
    strike span ``K_{i+1}-K_{i-1}`` puts it in (normalized) price units so the
    tolerance is portable across chains."""
    if strikes.size < 3:
        return 0.0
    k = np.asarray(strikes, dtype=float)
    a = k[1:-1] - k[:-2]
    b = k[2:] - k[1:-1]
    fly = c[:-2] * b - c[1:-1] * (a + b) + c[2:] * a
    return float(np.min(fly / (a + b)))


def _repair_wing(u: np.ndarray, c: np.ndarray, slope_floor: float) -> np.ndarray:
    """L2-closest CONVEX call curve on one wing, anchored at the core boundary.

    ``u`` is the OUTWARD distance in strike from the anchor (``u[0] = 0``, increasing
    away from the money); ``c[0]`` is the fixed boundary price. A convex sequence
    leaving the anchor is the affine part plus non-negative hinge knots

        c(u) = c[0] + b·u + Σ_j δ_j·(u - u_j)_+ ,   δ_j ≥ 0,   b ≥ slope_floor,

    where ``slope_floor`` is the core's slope coming into the anchor (so the join is
    convex — the leaving slope cannot be below the incoming one). That is one bounded
    linear least squares: ``δ_j ≥ 0`` is the box that makes the curve convex, and the
    anchor is preserved exactly because ``u[0] = 0`` ⇒ the first basis row is zero."""
    m = u.size
    if m < 2:
        return c.copy()
    cols = [u] + [np.maximum(u - u[j], 0.0) for j in range(1, m - 1)]
    a_mat = np.column_stack(cols)  # (m, m-1): [u, (u-u_j)_+ ...]
    lb = np.zeros(a_mat.shape[1])
    lb[0] = slope_floor  # b ≥ incoming core slope (convex join); δ_j ≥ 0
    sol = lsq_linear(a_mat, c - c[0], bounds=(lb, np.full(a_mat.shape[1], np.inf)))
    return c[0] + a_mat @ sol.x


def _project_wing_banded(
    u: np.ndarray, c: np.ndarray, lo: np.ndarray, hi: np.ndarray,
    slope_floor: float, iters: int = 25, tol: float = 1e-12,
) -> np.ndarray:
    """L2-closest curve to ``c`` on a wing that is BOTH convex (anchored at the core
    boundary) AND within the bid/ask band ``[lo, hi]`` per strike — by Dykstra
    alternating projection onto the two convex sets.

    The band constraint is the fix for plain convex projection's failure mode: an
    unconstrained convex fit of an illiquid, non-convex de-Am wing can push a price to
    the no-arb boundary, inverting to an absurd IV (and a catastrophic downstream
    fit). Keeping the repaired price inside the QUOTED spread bounds the correction to
    real uncertainty. Dykstra converges to the projection onto {convex} ∩ {band}."""
    x = c.copy()
    p = np.zeros_like(c)
    q = np.zeros_like(c)
    for _ in range(iters):
        y = _repair_wing(u, x + p, slope_floor)  # project onto the convex cone
        p = x + p - y
        z = np.clip(y + q, lo, hi)  # project onto the bid/ask box
        z[0] = c[0]  # the core-boundary anchor stays exactly fixed
        q = y + q - z
        if float(np.max(np.abs(z - x))) < tol:
            x = z
            break
        x = z
    return x


def convex_wing_repair(
    k: np.ndarray,
    c: np.ndarray,
    c_lo: np.ndarray,
    c_hi: np.ndarray,
    w_atm: float,
    forward: float,
    z_core: float = Z_CORE,
    tol: float = CONVEX_TOL,
) -> np.ndarray | None:
    """Repair de-Am non-convexities in the WINGS of a normalized OTM call curve.

    ``k`` is log-moneyness (sorted), ``c`` the normalized mid call prices, ``c_lo`` /
    ``c_hi`` the bid / ask call prices (the band the repair must stay inside), ``w_atm``
    the ATM total variance (for the standardized-moneyness core band), ``forward`` the
    forward (to recover strikes ``K = F e^k``). Returns the repaired mid call curve, or
    ``None`` when the curve is already convex / there is no core+wing to work with — in
    which case the caller keeps the original prices (byte-identical).

    The ATM core (``|z| ≤ z_core``, ``z = k/√w_atm``) is held EXACTLY fixed; only the
    wings beyond it are projected (convex AND within bid/ask), each anchored at its
    core boundary."""
    n = int(k.size)
    if n < 5 or w_atm <= 0.0 or forward <= 0.0:
        return None
    strikes = forward * np.exp(np.asarray(k, dtype=float))
    if min_norm_butterfly(strikes, c) >= -tol:
        return None  # already convex to sub-tick → no-op (byte-identical path)

    z = np.asarray(k, dtype=float) / np.sqrt(w_atm)
    core = np.abs(z) <= z_core
    if int(core.sum()) < 2 or bool(core.all()):
        return None  # need a ≥2-point core and at least one wing
    idx = np.flatnonzero(core)
    lo, hi = int(idx[0]), int(idx[-1])
    c = np.asarray(c, dtype=float)
    c_lo = np.asarray(c_lo, dtype=float)
    c_hi = np.asarray(c_hi, dtype=float)
    out = c.copy()

    # Right wing: anchor at the core's outer-right strike `hi`, repair hi..n-1.
    if hi < n - 1:
        slope_in = (c[hi] - c[hi - 1]) / (strikes[hi] - strikes[hi - 1])
        u = strikes[hi:] - strikes[hi]
        out[hi:] = _project_wing_banded(u, c[hi:], c_lo[hi:], c_hi[hi:], slope_in)

    # Left wing: reflect to outward distance u = K_lo - K (increasing away from the
    # money). The incoming core slope in u is -(dc/dK) at the boundary.
    if lo > 0:
        sl = slice(0, lo + 1)
        u = (strikes[lo] - strikes[sl])[::-1]  # u[0]=0 at the anchor, increasing out
        rev = slice(None, None, -1)
        out[sl] = _project_wing_banded(
            u, c[sl][rev], c_lo[sl][rev], c_hi[sl][rev],
            -(c[lo + 1] - c[lo]) / (strikes[lo + 1] - strikes[lo]),
        )[rev]
    return out
