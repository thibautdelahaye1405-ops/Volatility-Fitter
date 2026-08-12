"""Analytic tail continuations for generalized LQD slices (alpha > 0).

Book ch. 2 (Papers/book/chapters/02_lqd), "Numerical realization": beyond
the central grid the transport continues as the power law

    x_R(z) = x(Z) + lam/(1-a) [(z+1)^{1-a} - (Z+1)^{1-a}]
                                            (eq. rightcontinuation),

with the left analogue obtained by replacing z+1 with 1-z and reversing the
sign of the increment; both reduce to the straight exponential-tail line at
a = 0. Everything here evaluates that continuation CONSISTENTLY — the
chapter's design rule: normalization, strike roots, prices and calendar
tests must share one continuation. The martingale/ledger tail masses use
log-domain Gauss-Legendre quadrature (the closed forms of eq. tailcorr
exist only at a = 0); the far strike root is eq. rightroot; beyond-grid
prices are eq. beyondgrid. The saddle guard (eq. operationaltailguard) is
enforced by the slice builder BEFORE any of this is reached:
x'(Z) <= 1 - EPS_TAIL, so the right integrand decays from the boundary on
and 1 - x'(z_R) never vanishes.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

#: Saddle-guard margin (eq. operationaltailguard): refuse a build whose
#: continuation speed at the right boundary comes within this margin of the
#: martingale integrand's stationary point x' = 1. Such a forward is finite
#: in theory but numerically determined by ranks far beyond the grid — the
#: chapter's reference implementation refuses it rather than truncating.
EPS_TAIL = 1e-3

#: Gauss-Legendre resolution of the log-domain tail-mass quadrature. The
#: mapped integrand is smooth and exponentially decaying on its own scale
#: (the rational map absorbs the 1/(1 - x'(Z)) decay length), so 64 nodes
#: reach ~1e-12 relative — far below the ~1e-13 weight the tail carries in
#: the martingale integral.
TAIL_QUAD_N = 64


@lru_cache(maxsize=4)
def _unit_gauss(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Gauss-Legendre nodes/weights mapped to (0, 1), cached read-only."""
    x, w = np.polynomial.legendre.leggauss(n)
    t = 0.5 * (x + 1.0)
    w = 0.5 * w
    for arr in (t, w):
        arr.flags.writeable = False
    return t, w


def continuation_speed(lam: float, alpha: float, z_max: float) -> float:
    """x'(Z) under the tail continuation: lam (Z+1)^{-alpha}.

    Eq. xspeed at the boundary, where the far-side gauge is z + 1 and the
    near-side gauge is 1 + O(e^{-Z}). This is the quantity the saddle guard
    bounds and the decay scale the tail quadratures are mapped with.
    """
    return lam * (z_max + 1.0) ** (-alpha)


def tail_mass_right(xbar_end: float, lam: float, alpha: float, z_max: float) -> float:
    """Missing right martingale mass int_Z^inf e^{xbar_R(z)} rho(z) dz, a > 0.

    rho(z) = e^{-z} to double precision beyond Z = 40 (rho = expit(z)^2 e^{-z}
    and expit(40)^2 rounds to 1.0), so the integrand is exp(xbar_R(z) - z)
    under eq. rightcontinuation anchored at ``xbar_end`` = xbar(Z). The
    rational map z = Z + s t/(1-t) with s = 1/(1 - x'(Z)) matches the
    integrand's own decay length; the caller has enforced the saddle guard,
    so s is finite and the exponent decreases from t = 0 on.
    """
    xp = continuation_speed(lam, alpha, z_max)
    scale = 1.0 / (1.0 - xp)
    t, w = _unit_gauss(TAIL_QUAD_N)
    zz = z_max + scale * t / (1.0 - t)
    p = 1.0 - alpha
    expo = xbar_end + lam / p * ((zz + 1.0) ** p - (z_max + 1.0) ** p) - zz
    expo = expo + np.log(scale) - 2.0 * np.log1p(-t)  # + log Jacobian
    m = float(np.max(expo))
    return float(np.exp(m) * np.dot(w, np.exp(expo - m)))


def tail_mass_left(xbar_start: float, lam: float, alpha: float, z_max: float) -> float:
    """Missing left martingale mass int_{-inf}^{-Z} e^{xbar_L(z)} rho(z) dz.

    Mirror of ``tail_mass_right`` (rho = e^{z} to double precision below
    -Z); the exponent decays at rate 1 + x' >= 1, so no guard is needed on
    this side — the map scale 1/(1 + x'(-Z)) only sharpens it.
    """
    xp = continuation_speed(lam, alpha, z_max)
    scale = 1.0 / (1.0 + xp)
    t, w = _unit_gauss(TAIL_QUAD_N)
    zz = -z_max - scale * t / (1.0 - t)
    p = 1.0 - alpha
    expo = xbar_start - lam / p * ((1.0 - zz) ** p - (z_max + 1.0) ** p) + zz
    expo = expo + np.log(scale) - 2.0 * np.log1p(-t)
    m = float(np.max(expo))
    return float(np.exp(m) * np.dot(w, np.exp(expo - m)))


def right_root(
    k: np.ndarray, q_end: float, lam: float, alpha: float, z_max: float
) -> np.ndarray:
    """z_R(k) solving the right continuation x_R(z) = k (eq. rightroot).

    Vectorized over strikes. The power base is floored at 1 so the
    where-unused branch of the caller (k inside the grid) stays finite
    instead of raising fractional powers of negative numbers; in the
    applied region k > x(Z) the base is >= (Z+1)^{1-a} anyway.
    """
    p = 1.0 - alpha
    base = (z_max + 1.0) ** p + p * (np.asarray(k, dtype=float) - q_end) / lam
    return np.maximum(base, 1.0) ** (1.0 / p) - 1.0


def right_tail_call(
    k: np.ndarray, q_end: float, lam: float, alpha: float, z_max: float
) -> np.ndarray:
    """Normalized far call under the right continuation (eq. beyondgrid):
    c(k) = e^{k - z_R} x'(z_R) / (1 - x'(z_R)).

    x'(z_R) = lam (z_R + 1)^{-alpha} decreases beyond the boundary, so the
    saddle guard's 1 - x' >= eps holds at every applied root. Exponents are
    clipped at 0 only to keep the caller's unused where-branch from
    overflowing; in the applied region they are always negative.
    """
    z_r = right_root(k, q_end, lam, alpha, z_max)
    xp = lam * (z_r + 1.0) ** (-alpha)
    return np.exp(np.minimum(np.asarray(k, dtype=float) - z_r, 0.0)) * xp / (1.0 - xp)


def left_root(
    k: np.ndarray, q_start: float, lam: float, alpha: float, z_max: float
) -> np.ndarray:
    """z_L(k) solving the left continuation x_L(z) = k (left analogue of
    eq. rightroot, in the 1 - z variable; same base floor as right_root)."""
    p = 1.0 - alpha
    base = (z_max + 1.0) ** p + p * (q_start - np.asarray(k, dtype=float)) / lam
    return 1.0 - np.maximum(base, 1.0) ** (1.0 / p)


def left_tail_put(
    k: np.ndarray, q_start: float, lam: float, alpha: float, z_max: float
) -> np.ndarray:
    """Normalized far put under the left continuation (mirror of
    eq. beyondgrid): P(k) = e^{k + z_L} x'(z_L) / (1 + x'(z_L)); the caller
    assembles the deep-left CALL as (1 - e^k) + P by parity, avoiding the
    subtraction of two numbers close to one."""
    z_l = left_root(k, q_start, lam, alpha, z_max)
    xp = lam * (1.0 - z_l) ** (-alpha)
    return np.exp(np.minimum(np.asarray(k, dtype=float) + z_l, 0.0)) * xp / (1.0 + xp)
