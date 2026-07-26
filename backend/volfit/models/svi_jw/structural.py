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
(models/diagnostics, R2) remains the acceptance authority. PRODUCTION
DEFAULT since the benchmark adjudication (FINDINGS_svi_chart.md, ratified
2026-07-26); "raw" remains explicit configuration for comparability and
rollback, and the backtest harness's frozen SVI-JW arm stays raw@2.0.
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


#: Lift saturation bound: inside ±80 every lift is STRICTLY interior in
#: float64 (logistic(-80) ~ 1.8e-35 > 0, exp(±80) finite-nonzero, softplus
#: > 0) — without it an LM trial at theta_4 < -745 underflowed exp to an
#: exact 0.0 and broke the s = b(1-rho^2)^{3/2}/kappa recovery with a
#: ZeroDivisionError (all 30 breaks of the round-1 chart sweep). k* is a
#: genuine location and stays unclipped.
_THETA_SAT = 80.0

#: Largest float64 strictly below 1. Two float-boundary leaks in the lift were
#: found by the analytic-Jacobian lock (2026-07-26), both saturation rounding:
#: (i) logistic(x) ROUNDS to an exact 1.0 for x >~ 37, putting a wing exactly
#: AT the cap — the fence the chart exists to keep strict; (ii) with one wing
#: saturated against an O(1) other the rho quotient rounds to ±1.0, so 1-rho²
#: hit an exact 0 (sigma = 0, m = k* + 0·(1/0) = NaN). The logistic is clipped
#: one ulp inside 1 and 1-rho² is computed by the exact product identity.
_INTERIOR_ONE = float(np.nextafter(1.0, 0.0))


def _wing_geometry(
    lifted: np.ndarray, cap: float
) -> tuple[float, float, float, float, float, float]:
    """(σ_ℓ, σ_r, β_L, β_R, rho, 1−rho²) of the wing lifts, strictly interior.

    The logistics are clipped to ≤ _INTERIOR_ONE (so β < cap strictly at every
    finite theta) and 1−rho² is computed by the EXACT identity 4·β_L·β_R/S² —
    the quotient form 1−rho·rho rounds to 0.0 under wing asymmetry beyond
    float eps. Both lifts are strictly positive, so u > 0 always."""
    sig_l = min(_logistic(float(lifted[0])), _INTERIOR_ONE)
    sig_r = min(_logistic(float(lifted[1])), _INTERIOR_ONE)
    beta_l = cap * sig_l
    beta_r = cap * sig_r
    total = beta_l + beta_r
    rho = float(np.clip((beta_r - beta_l) / total, -_INTERIOR_ONE, _INTERIOR_ONE))
    one_m_rho2 = 4.0 * beta_l * beta_r / (total * total)
    return sig_l, sig_r, beta_l, beta_r, rho, one_m_rho2


def unpack_structural(theta: np.ndarray, cap: float) -> RawSVI:
    """Map (ℓ, r, k*, h, q) to an admissible RawSVI (see module docstring)."""
    lifted = np.clip(np.asarray(theta, dtype=float), -_THETA_SAT, _THETA_SAT)
    _sig_l, _sig_r, beta_l, beta_r, rho, one_m_rho2 = _wing_geometry(lifted, cap)
    k_star = float(theta[2])
    w_star = _softplus(float(lifted[3]))
    kappa = float(np.exp(lifted[4]))
    b = 0.5 * (beta_l + beta_r)
    s = b * one_m_rho2**1.5 / kappa
    m = k_star + s * rho / np.sqrt(one_m_rho2)
    a = w_star - b * s * np.sqrt(one_m_rho2)
    return RawSVI(a=float(a), b=float(b), rho=float(rho), m=float(m), sigma=float(s))


def structural_chain(theta: np.ndarray, cap: float) -> tuple[RawSVI, np.ndarray]:
    """The unpacked slice AND the 5x5 chain matrix d(raw)/d(theta).

    Rows are the raw parameters (a, b, rho, m, sigma), columns the chart
    vector (l, r, k*, h, q) — the factor an analytic residual Jacobian in
    raw-parameter space multiplies to land in chart space (the adoption
    follow-up of the R3 chart: the FD path already beat raw's analytic ~3x,
    the closed form removes the 1+P residual evals per LM step entirely).

    Mirrors ``unpack_structural`` EXACTLY, including the ±_THETA_SAT clip:
    a clipped coordinate's column is zero (the lift is locally constant
    there — the same zero scipy's finite differences measured).

    Derivation (committee algebra, differentiated): with S = β_L + β_R,
    u = 1 − ρ², the wing sensitivities are

        ∂b/∂β = 1/2,        ∂ρ/∂β_L = −2β_R/S²,  ∂ρ/∂β_R = +2β_L/S²,
        ∂s/∂b = u^{3/2}/κ,  ∂s/∂ρ = −3bρ√u/κ,
        ∂m/∂s = ρ/√u,       ∂m/∂ρ = s/u^{3/2}      (u + ρ² = 1),
        ∂a/∂b = −s√u,       ∂a/∂s = −b√u,          ∂a/∂ρ = bsρ/√u,

    and the κ column collapses to ∂(a, m, s)/∂q = (bs√u, −sρ/√u, −s)
    since dκ/dq = κ cancels the 1/κ in s.
    """
    theta = np.asarray(theta, dtype=float)
    lifted = np.clip(theta, -_THETA_SAT, _THETA_SAT)
    sig_l, sig_r, beta_l, beta_r, rho, one_m_rho2 = _wing_geometry(lifted, cap)
    k_star = float(theta[2])
    w_star = _softplus(float(lifted[3]))
    kappa = float(np.exp(lifted[4]))
    b = 0.5 * (beta_l + beta_r)
    s = b * one_m_rho2**1.5 / kappa
    m = k_star + s * rho / np.sqrt(one_m_rho2)
    a = w_star - b * s * np.sqrt(one_m_rho2)
    raw = RawSVI(a=float(a), b=float(b), rho=float(rho), m=float(m), sigma=float(s))

    # Lift derivatives; zero where the saturation clip is binding (k* never is).
    inside = np.abs(theta) < _THETA_SAT
    d_beta_l = cap * sig_l * (1.0 - sig_l) * float(inside[0])
    d_beta_r = cap * sig_r * (1.0 - sig_r) * float(inside[1])
    d_w_star = (1.0 - np.exp(-w_star)) * float(inside[3])  # sigmoid(h)

    sqrt_u = float(np.sqrt(one_m_rho2))
    total = beta_l + beta_r
    drho_l = -2.0 * beta_r / (total * total)
    drho_r = 2.0 * beta_l / (total * total)
    ds_db = one_m_rho2**1.5 / kappa
    ds_drho = -3.0 * b * rho * sqrt_u / kappa
    dm_ds = rho / sqrt_u
    dm_drho = s / one_m_rho2**1.5
    da_db = -s * sqrt_u
    da_ds = -b * sqrt_u
    da_drho = b * s * rho / sqrt_u

    chain = np.zeros((5, 5))
    for col, d_beta, drho in ((0, d_beta_l, drho_l), (1, d_beta_r, drho_r)):
        ds = 0.5 * ds_db + ds_drho * drho  # d s / d beta_wing
        chain[0, col] = (0.5 * da_db + da_ds * ds + da_drho * drho) * d_beta
        chain[1, col] = 0.5 * d_beta
        chain[2, col] = drho * d_beta
        chain[3, col] = (dm_ds * ds + dm_drho * drho) * d_beta
        chain[4, col] = ds * d_beta
    chain[3, 2] = 1.0  # m carries k* one-to-one
    chain[0, 3] = d_w_star  # a carries w* one-to-one
    in_q = float(inside[4])
    chain[0, 4] = b * s * sqrt_u * in_q
    chain[3, 4] = -s * rho / sqrt_u * in_q
    chain[4, 4] = -s * in_q
    return raw, chain


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
