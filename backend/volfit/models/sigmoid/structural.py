"""Structural Multi-Core SIV base chart: (β_L, β_R, z*, v*, κ_P, κ_C).

The MCS committee-arc port of the SVI structural chart precedent
(models/svi_jw/structural.py, ratified R3): parameterize the BASE slice by
the quantities the wing guarantees are ABOUT — the two actual asymptotic
k-space total-variance Lee slopes (eq mcsbetak,

    β_P = √t/σ_ref (2 K0/κ_P − S0),   β_C = √t/σ_ref (S0 + 2 K0/κ_C),

which the zero-wing kernels never move, lem zerowing) — each lifted so every
finite optimizer vector is admissible:

    β_L = cap · logistic(ℓ),  β_R = cap · logistic(r)   (strictly Lee-clean,
                               cap = the R1-buffered leeSlopeMax < 2)
    v*  = softplus(h) > 0     (strictly positive base variance level at z*)
    κ_P = e^{q_p}, κ_C = e^{q_c} > 0  (strictly positive wing steepnesses)
    z*  free                  (base centre in z-space; z* = z0 one-to-one)

Raw recovery is exact: with s = √t/σ_ref the slope scale,

    K0 = (β_L + β_R) / (2 s) · κ_P κ_C / (κ_P + κ_C)   (> 0 strictly),
    S0 = β_R / s − 2 K0 / κ_C,   V0 = v*,   z0 = z*.

Under this chart both base wings live strictly inside (0, cap) at every
finite theta — the Lee fence is the chart, not a penalty. It fences the BASE
only: hats stay in the raw (α, c, h, κ) block with their box bounds, and it
does NOT guarantee g >= 0 anywhere (the wing penalty and belly certificate
remain the authorities), nor positivity of the full multi-core curve (v* > 0
is the base level at z*, hats can still dig below — the variance floor and
positivity check govern that, unchanged).

Float-boundary saturation guards carried over from the SVI arc: the lifts
are clipped at ±_THETA_SAT so exp/logistic under/overflow cannot produce
0/inf raw parameters, and the logistic is clipped one ulp inside 1
(_INTERIOR_ONE) so a saturated wing stays strictly UNDER the cap. The SVI
arc's second class (the rho quotient rounding to ±1) has no analogue here:
the chart forms only the SUM β_L + β_R, never their normalized difference.
"""

from __future__ import annotations

import numpy as np

from volfit.models.sigmoid.jacobian import siv_residual_jacobian

#: Keep the lift inputs off exact saturation when inverting (logit/log).
_EDGE = 1e-9

#: Lift saturation bound (the SVI arc's round-1 sweep bug): inside ±80 every
#: lift is STRICTLY interior in float64 (logistic(-80) ~ 1.8e-35 > 0, exp(±80)
#: finite-nonzero, softplus > 0). z* is a genuine location and stays unclipped.
_THETA_SAT = 80.0

#: Largest float64 strictly below 1: logistic(x) ROUNDS to an exact 1.0 for
#: x >~ 37, which would put a wing exactly AT the cap — the fence the chart
#: exists to keep strict (the SVI arc's saturation class (i)).
_INTERIOR_ONE = float(np.nextafter(1.0, 0.0))


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


def _lifts(lifted: np.ndarray, cap: float) -> tuple[float, float, float, float]:
    """(σ_ℓ, σ_r, β_L, β_R) of the wing lifts, strictly interior in (0, cap)."""
    sig_l = min(_logistic(float(lifted[0])), _INTERIOR_ONE)
    sig_r = min(_logistic(float(lifted[1])), _INTERIOR_ONE)
    return sig_l, sig_r, cap * sig_l, cap * sig_r


def unpack_structural_mcs(theta: np.ndarray, cap: float, slope_scale: float) -> np.ndarray:
    """Map (ℓ, r, z*, h, q_p, q_c) to the raw base (v0, s0, k0, z0, κ_p, κ_c).

    ``slope_scale`` = √t/σ_ref, the k-space slope per unit z-space slope
    (eq mcsbetak). Every finite theta maps to an admissible base: k0 > 0,
    v0 > 0, κ > 0 and both k-space Lee slopes strictly inside (0, cap)."""
    lifted = np.clip(np.asarray(theta, dtype=float), -_THETA_SAT, _THETA_SAT)
    _sl, _sr, beta_l, beta_r = _lifts(lifted, cap)
    kappa_p = float(np.exp(lifted[4]))
    kappa_c = float(np.exp(lifted[5]))
    harmonic = kappa_p * kappa_c / (kappa_p + kappa_c)
    k0 = (beta_l + beta_r) / (2.0 * slope_scale) * harmonic
    s0 = beta_r / slope_scale - 2.0 * k0 / kappa_c
    v0 = _softplus(float(lifted[3]))
    z0 = float(theta[2])  # genuine location, never clipped
    return np.array([v0, s0, k0, z0, kappa_p, kappa_c])


def structural_chain_mcs(
    theta: np.ndarray, cap: float, slope_scale: float
) -> tuple[np.ndarray, np.ndarray]:
    """The unpacked raw base AND the 6x6 chain matrix d(raw)/d(chart).

    Rows are the raw parameters (v0, s0, k0, z0, κ_p, κ_c), columns the chart
    vector (ℓ, r, z*, h, q_p, q_c) — the factor the analytic residual Jacobian
    in raw space multiplies to land in chart space (the SVI adoption-follow-up
    pattern). Mirrors ``unpack_structural_mcs`` EXACTLY, including the
    ±_THETA_SAT clip: a clipped coordinate's column is zero (the lift is
    locally constant there — the same zero a finite difference measures).

    Derivation (eq mcsbetak inverted, differentiated): with s the slope
    scale, T = κ_p + κ_c, H = κ_pκ_c/T and B = β_L + β_R,

        ∂k0/∂β = H/(2s),          ∂s0/∂β_R = κ_c/(sT),  ∂s0/∂β_L = −κ_p/(sT),
        ∂k0/∂κ_p = B κ_c²/(2sT²), ∂k0/∂κ_c = B κ_p²/(2sT²),
        ∂s0/∂κ_p = −B κ_c/(sT²),  ∂s0/∂κ_c = +B κ_p/(sT²),

    the q columns carrying an extra dκ/dq = κ, dv0/dh = sigmoid(h) =
    1 − e^{−v0}, and z0 carrying z* one-to-one."""
    theta = np.asarray(theta, dtype=float)
    lifted = np.clip(theta, -_THETA_SAT, _THETA_SAT)
    sig_l, sig_r, beta_l, beta_r = _lifts(lifted, cap)
    kappa_p = float(np.exp(lifted[4]))
    kappa_c = float(np.exp(lifted[5]))
    total = kappa_p + kappa_c
    harmonic = kappa_p * kappa_c / total
    b_sum = beta_l + beta_r
    k0 = b_sum / (2.0 * slope_scale) * harmonic
    s0 = beta_r / slope_scale - 2.0 * k0 / kappa_c
    v0 = _softplus(float(lifted[3]))
    raw = np.array([v0, s0, k0, float(theta[2]), kappa_p, kappa_c])

    # Lift derivatives; zero where the saturation clip binds (z* never does).
    inside = np.abs(theta) < _THETA_SAT
    d_beta_l = cap * sig_l * (1.0 - sig_l) * float(inside[0])
    d_beta_r = cap * sig_r * (1.0 - sig_r) * float(inside[1])
    d_v0 = (1.0 - np.exp(-v0)) * float(inside[3])  # sigmoid(h)
    in_qp = float(inside[4])
    in_qc = float(inside[5])

    dk0_dbeta = harmonic / (2.0 * slope_scale)
    ds0_dbeta_r = kappa_c / (slope_scale * total)
    ds0_dbeta_l = -kappa_p / (slope_scale * total)
    dk0_dqp = b_sum * kappa_c**2 / (2.0 * slope_scale * total**2) * kappa_p * in_qp
    dk0_dqc = b_sum * kappa_p**2 / (2.0 * slope_scale * total**2) * kappa_c * in_qc
    ds0_dqp = -b_sum * kappa_c / (slope_scale * total**2) * kappa_p * in_qp
    ds0_dqc = b_sum * kappa_p / (slope_scale * total**2) * kappa_c * in_qc

    chain = np.zeros((6, 6))
    chain[0, 3] = d_v0  # v0 carries h one-to-one (softplus lift)
    chain[1, 0] = ds0_dbeta_l * d_beta_l
    chain[1, 1] = ds0_dbeta_r * d_beta_r
    chain[1, 4] = ds0_dqp
    chain[1, 5] = ds0_dqc
    chain[2, 0] = dk0_dbeta * d_beta_l
    chain[2, 1] = dk0_dbeta * d_beta_r
    chain[2, 4] = dk0_dqp
    chain[2, 5] = dk0_dqc
    chain[3, 2] = 1.0  # z0 carries z* one-to-one
    chain[4, 4] = kappa_p * in_qp
    chain[5, 5] = kappa_c * in_qc
    return raw, chain


def pack_structural_mcs(raw: np.ndarray, cap: float, slope_scale: float) -> np.ndarray:
    """Invert a raw base (v0, s0, k0, z0, κ_p, κ_c) into the structural chart
    (clipping the wings strictly inside (0, cap) — a raw base AT/above the cap,
    or with a non-rising wing, enters at the lift's edge: exactly the fence the
    chart exists to impose)."""
    v0, s0, k0, z0, kappa_p, kappa_c = (float(x) for x in np.asarray(raw, float)[:6])
    beta_l = slope_scale * (2.0 * k0 / kappa_p - s0)
    beta_r = slope_scale * (s0 + 2.0 * k0 / kappa_c)
    return np.array(
        [
            _logit(beta_l / cap),
            _logit(beta_r / cap),
            z0,
            _inv_softplus(max(v0, 1e-8)),
            float(np.log(max(kappa_p, 1e-12))),
            float(np.log(max(kappa_c, 1e-12))),
        ]
    )


def structural_bounds_mcs(z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Chart-space box bounds for the trf refine (the raw ``_base_bounds``
    mapped through the monotone lifts where one-to-one): z* keeps the raw z0
    box, h maps the raw v0 box [1e-6, 25] through softplus⁻¹, q maps the raw
    κ box [0.2, 25] through log. The raw s0/k0 boxes are REPLACED by the wing
    lifts' ±_THETA_SAT range — the cap fences the combination that matters."""
    lo = np.array(
        [-_THETA_SAT, -_THETA_SAT, z.min() - 2.0, _inv_softplus(1e-6), np.log(0.2), np.log(0.2)]
    )
    hi = np.array(
        [_THETA_SAT, _THETA_SAT, z.max() + 2.0, _inv_softplus(25.0), np.log(25.0), np.log(25.0)]
    )
    return lo, hi


def siv_residual_jacobian_structural(
    theta: np.ndarray,
    z: np.ndarray,
    n_cores: int,
    t: float,
    sqrt_w: np.ndarray,
    band,
    mid_anchor_weight: float,
    ridge: float,
    cal_z: np.ndarray | None,
    cal_floor: np.ndarray | None,
    sqrt_cal: float,
    ceil_z: np.ndarray | None,
    ceil_w: np.ndarray | None,
    cap: float,
    slope_scale: float,
    price_rows: tuple | None = None,
) -> np.ndarray:
    """Analytic Jacobian of the gated residual in CHART space: the raw-space
    Jacobian right-multiplied by blockdiag(chain₆, I₄ᵣ) — the hat block is a
    raw pass-through, so only the 6 base columns transform. ``price_rows``
    (overlayPriceResiduals) passes through: the chain is space-agnostic."""
    theta = np.asarray(theta, dtype=float)
    raw6, chain = structural_chain_mcs(theta[:6], cap, slope_scale)
    theta_raw = np.concatenate([raw6, theta[6:]])
    j = siv_residual_jacobian(
        theta_raw, z, n_cores, t, sqrt_w, band, mid_anchor_weight, ridge,
        cal_z, cal_floor, sqrt_cal, ceil_z, ceil_w, price_rows=price_rows,
    )
    j[:, :6] = j[:, :6] @ chain
    return j
