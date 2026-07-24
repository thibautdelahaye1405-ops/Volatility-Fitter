"""Structural SVI chart (committee revision R3): (β_L, β_R, k*, w*, κ*).

The raw chart guarantees only the hyperbola's structure (b > 0, |ρ| < 1,
s > 0) and leans on two unit-mixed soft penalties plus a trial-w floor for
everything else. The committee's chart parameterizes the slice by the
quantities the guarantees are ABOUT — the two actual asymptotic wing slopes,
the vertex location, the minimum total variance, and the vertex curvature —
each lifted so every finite optimizer vector is admissible:

    β_L = cap · logistic(ℓ),   β_R = cap · logistic(r)   (strictly Lee-clean,
                                cap = the R1-buffered lee_slope_max < 2)
    w*  = softplus(h) > 0      (strictly positive minimum total variance)
    κ*  = e^q > 0              (strictly convex vertex)
    k*  free                   (vertex log-moneyness)

Raw recovery is exact (the committee algebra, verified in the triage):

    b = (β_L + β_R)/2,  ρ = (β_R − β_L)/(β_R + β_L),
    s = b (1 − ρ²)^{3/2} / κ*,  m = k* + s ρ/√(1−ρ²),  a = w* − b s √(1−ρ²).

Under this chart the floor and Lee penalty rows are structurally zero and the
trial-w clip never fires (w(k) ≥ w* > 0 everywhere) — the fences become
inert bookkeeping. It does NOT guarantee g ≥ 0: the belly certificate
(models/diagnostics, R2) remains the acceptance authority. Opt-in via
FitSettings.sviChart ("raw" stays the default until the benchmark
adjudication — the Note 01 R1 precedent).
"""

from __future__ import annotations

import numpy as np

from volfit.models.svi_jw.svi import RawSVI

#: Keep the lift inputs off exact saturation when inverting (logit/log).
_EDGE = 1e-9


def _softplus(x: float) -> float:
    return float(np.logaddexp(0.0, x))


def _inv_softplus(y: float) -> float:
    """log(e^y − 1), stable for small y."""
    y = max(float(y), 1e-12)
    return float(y + np.log(-np.expm1(-y)))


def _logistic(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))


def _logit(p: float) -> float:
    p = float(np.clip(p, _EDGE, 1.0 - _EDGE))
    return float(np.log(p / (1.0 - p)))


def unpack_structural(theta: np.ndarray, cap: float) -> RawSVI:
    """Map (ℓ, r, k*, h, q) to an admissible RawSVI (see module docstring)."""
    beta_l = cap * _logistic(float(theta[0]))
    beta_r = cap * _logistic(float(theta[1]))
    k_star = float(theta[2])
    w_star = _softplus(float(theta[3]))
    kappa = float(np.exp(theta[4]))
    b = 0.5 * (beta_l + beta_r)
    rho = (beta_r - beta_l) / (beta_r + beta_l)
    one_m_rho2 = 1.0 - rho * rho
    s = b * one_m_rho2**1.5 / kappa
    m = k_star + s * rho / np.sqrt(one_m_rho2)
    a = w_star - b * s * np.sqrt(one_m_rho2)
    return RawSVI(a=float(a), b=float(b), rho=float(rho), m=float(m), sigma=float(s))


def pack_structural(raw: RawSVI, cap: float) -> np.ndarray:
    """Invert an admissible raw slice into the structural chart (clipping the
    wings strictly inside (0, cap) — a raw slice AT/above the cap enters at
    the lift's edge, which is exactly the fence the chart exists to impose)."""
    beta_l = raw.b * (1.0 - raw.rho)
    beta_r = raw.b * (1.0 + raw.rho)
    one_m_rho2 = 1.0 - raw.rho * raw.rho
    kappa = raw.b * one_m_rho2**1.5 / max(raw.sigma, 1e-12)
    k_star = raw.m - raw.sigma * raw.rho / np.sqrt(one_m_rho2)
    w_star = raw.a + raw.b * raw.sigma * np.sqrt(one_m_rho2)
    return np.array(
        [
            _logit(beta_l / cap),
            _logit(beta_r / cap),
            k_star,
            _inv_softplus(max(w_star, 1e-8)),
            float(np.log(max(kappa, 1e-12))),
        ]
    )
