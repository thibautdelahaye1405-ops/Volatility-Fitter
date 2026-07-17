"""Analytic primitives of the Multi-Core Sigmoid Implied Variance (MC-SIV) model.

Implements the closed-form building blocks of
``Docs/Multi_Core_SIV_Technical_Note.tex``:

  * the log-cosh SIV primitive Phi_kappa and its derivatives, eqs (Phi),
    (Phi-derivatives);
  * the one-core SIV base slice v_base(z) with its asymmetric wing steepnesses,
    eqs (siv-convexity), (siv-slope), (siv-variance);
  * the normalized zero-wing hat kernel B_{c,h,kappa} and derivatives, the
    centered second finite difference of Phi, eqs (H-def), (B-def), (H-prime),
    (H-second). The hats vanish with their slope and curvature in both tails
    (eq H-zero-wing), so they reshape the body of the smile without disturbing
    the SIV wing slopes;
  * the Durrleman/Gatheral density functional g(k), eq (g-function), used as the
    butterfly-arbitrage diagnostic (eq density-g, derivative conversion eq
    derivative-conversion).

All functions are NumPy-vectorized and side-effect free; they are shared by the
``MultiCoreSiv`` smile model and its calibrator.
"""

from __future__ import annotations

import numpy as np

#: Above this |x| the log-cosh is replaced by its asymptote |x| - log 2 to
#: avoid cosh overflow (eq safe-logcosh of the note).
_LOGCOSH_CLIP = 50.0


def safe_logcosh(x: np.ndarray | float) -> np.ndarray:
    """Numerically stable log(cosh(x)) = |x| - log 2 + O(e^{-2|x|}) (eq safe-logcosh)."""
    x = np.abs(np.asarray(x, dtype=float))
    return np.where(x < _LOGCOSH_CLIP, np.log(np.cosh(np.minimum(x, _LOGCOSH_CLIP))), x - np.log(2.0))


# ------------------------------------------------------------- SIV primitive Phi
def phi(u: np.ndarray | float, kappa: np.ndarray | float) -> np.ndarray:
    """Phi_kappa(u) = (4/kappa^2) log cosh(kappa u / 2), eq (Phi)."""
    kappa = np.asarray(kappa, dtype=float)
    return 4.0 / kappa**2 * safe_logcosh(0.5 * kappa * np.asarray(u, dtype=float))


def phi_p(u: np.ndarray | float, kappa: np.ndarray | float) -> np.ndarray:
    """Phi'_kappa(u) = (2/kappa) tanh(kappa u / 2), eq (Phi-derivatives)."""
    kappa = np.asarray(kappa, dtype=float)
    return 2.0 / kappa * np.tanh(0.5 * kappa * np.asarray(u, dtype=float))


def phi_pp(u: np.ndarray | float, kappa: np.ndarray | float) -> np.ndarray:
    """Phi''_kappa(u) = sech^2(kappa u / 2), eq (Phi-derivatives).

    Computed as (2 e^{-|x|} / (1 + e^{-2|x|}))^2 — algebraically identical to
    1/cosh(x)^2 but overflow-SILENT: the naive form runs cosh -> inf -> inf^2
    at |x| ~ 355 (value still correct, 0.0, but every far-wing eval emits a
    RuntimeWarning — noisy in vectorized fits on wide slices)."""
    kappa = np.asarray(kappa, dtype=float)
    x = np.abs(0.5 * kappa * np.asarray(u, dtype=float))
    s = np.exp(-x)
    return (2.0 * s / (1.0 + s * s)) ** 2


# ------------------------------------------------------- one-core SIV base slice
def siv_base(
    z: np.ndarray | float,
    v0: float,
    s0: float,
    k0: float,
    z0: float,
    kappa_p: float,
    kappa_c: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Base SIV slice variance and its first two z-derivatives (eqs siv-*).

    v_base(z)  = V0 + S0 (z - z0) + K0 Phi_{kappa_i}(z - z0)
    v_base'(z) = S0 + K0 Phi'_{kappa_i}(z - z0)
    v_base''(z)= K0 Phi''_{kappa_i}(z - z0)

    with kappa_i = kappa_P for z < z0 and kappa_C for z >= z0 (eq siv-convexity).
    Because Phi, Phi' both vanish at the origin, the slice is C^2 across z0 even
    though the steepness switches there. Returns ``(v, v', v'')``.
    """
    u = np.asarray(z, dtype=float) - z0
    kappa = np.where(u < 0.0, kappa_p, kappa_c)
    v = v0 + s0 * u + k0 * phi(u, kappa)
    vz = s0 + k0 * phi_p(u, kappa)
    vzz = k0 * phi_pp(u, kappa)
    return v, vz, vzz


# ------------------------------------------------------- zero-wing hat kernel B
def _hat_norm(h: float, kappa: float) -> float:
    """Unit-height normalizer 2 Phi_kappa(h) = B's raw centre value, eq (H-height)."""
    return float(2.0 * phi(h, kappa))


def hat(z: np.ndarray | float, c: float, h: float, kappa: float) -> np.ndarray:
    """Normalized zero-wing hat B_{c,h,kappa}(z) with B(c) = 1 (eqs H-def, B-def)."""
    u = np.asarray(z, dtype=float) - c
    raw = phi(u - h, kappa) - 2.0 * phi(u, kappa) + phi(u + h, kappa)
    return raw / _hat_norm(h, kappa)


def hat_p(z: np.ndarray | float, c: float, h: float, kappa: float) -> np.ndarray:
    """B'_{c,h,kappa}(z), eq (H-prime); B'(c) = 0."""
    u = np.asarray(z, dtype=float) - c
    raw = phi_p(u - h, kappa) - 2.0 * phi_p(u, kappa) + phi_p(u + h, kappa)
    return raw / _hat_norm(h, kappa)


def hat_pp(z: np.ndarray | float, c: float, h: float, kappa: float) -> np.ndarray:
    """B''_{c,h,kappa}(z), eq (H-second); B''(c) = 2(sech^2(kappa h/2) - 1)/norm < 0."""
    u = np.asarray(z, dtype=float) - c
    raw = phi_pp(u - h, kappa) - 2.0 * phi_pp(u, kappa) + phi_pp(u + h, kappa)
    return raw / _hat_norm(h, kappa)


# ------------------------------------------------------ butterfly-arb diagnostic
def gatheral_g_from_z(
    z: np.ndarray,
    v: np.ndarray,
    vz: np.ndarray,
    vzz: np.ndarray,
    t: float,
    sigma_ref: float,
) -> np.ndarray:
    """Durrleman/Gatheral density functional g(k), eqs (g-function, density-g).

    Converts the z-space variance and derivatives to total-variance k-space
    derivatives (eq derivative-conversion: k = sigma_ref sqrt(T) z, w = T v) and
    evaluates g. The risk-neutral density is proportional to g, so g(k) >= 0 on
    the grid is the no-butterfly condition (eq butterfly-conditions).
    """
    sq_t = np.sqrt(t)
    k = sigma_ref * sq_t * np.asarray(z, dtype=float)
    w = t * np.asarray(v, dtype=float)
    wk = sq_t / sigma_ref * np.asarray(vz, dtype=float)
    wkk = np.asarray(vzz, dtype=float) / sigma_ref**2
    return (
        (1.0 - k * wk / (2.0 * w)) ** 2
        - 0.25 * wk**2 * (1.0 / w + 0.25)
        + 0.5 * wkk
    )
