"""Measurement extraction for the observation filter (Note 15 §4, Phase 2).

Builds the noisy handle observation (z_t, R_t) from a data-only fit. Two
routes, selected by ``OptionsSettings.filterCovarianceMode``:

* ``jacobian`` (the default, note eq. cov-delta): propagate the fit's
  observed information through the handle map,

      R_x = G  (J^T W J + Lambda_intrinsic)^+  G^T,    R_t = rho * R_x,

  where J is the solver's solution-point Jacobian (retained by the
  calibrators' ``solver_diag`` side-channel — the sqrt-weight / inv-vega
  scaling is already folded into its rows, so J^T J IS the information matrix
  in vol units, and the intrinsic reg/calendar/barrier rows supply
  Lambda_intrinsic), G = d(handles)/d(theta), and rho the realized-
  inconsistency inflation (eq. resid-inflation). Band-mode semantics come for
  free: inactive hinge rows differentiate to zero inside the spread, so
  in-band quotes contribute nothing to the information.

* ``factors`` (eq. cheapR): the graph layer's precision vocabulary
  (rms/density/spread/freshness x per-handle confidence) — the fallback when
  no solver Jacobian is available, and the A/B diagnostic column.

UNITS. The production quote weights are RELATIVE (equal / tv_density), not
1/noise^2, so J^T J alone is the information under an implied noise of one
full volatility point per quote — meaningless. ``noise_scale`` states the
per-quote noise std in vol units (bid-ask half-spread with a floor, or the
haircut); the DATA rows of J and the residual are divided by it before the
information/chi^2 are formed, while the intrinsic regularization rows keep
their own scale (they are a prior, not a measurement). This is what ties the
covariance to the market's stated uncertainty (note §4: "R_t is measurement
covariance: bid-ask width, ...").

Pure numpy: no app state, no model imports. The app layer supplies the handle
map callable (theta -> handles) per displayed model and the per-quote noise.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from volfit.calib.observation_filter import RESID_INFLATION_CAP, FilterMeasurement
from volfit.graph.precision import (
    OBS_PRECISION_CAP,
    OBS_PRECISION_FLOOR,
    observation_precision,
)

#: Relative eigenvalue cutoff of the information matrix: eigenvalues below
#: ``rtol * max_eig`` are CLAMPED UP to the cutoff (a regularized inverse, not a
#: pseudo-inverse) so an unidentified theta-direction yields a large-but-finite
#: handle variance — R must inflate on sparse chains, never explode or, worse,
#: read as zero uncertainty (which a true pseudo-inverse would).
INFO_RANK_RTOL = 1e-10


# ------------------------------------------------------------ handle Jacobian
def handle_jacobian_fd(
    handle_fn: Callable[[np.ndarray], np.ndarray],
    theta: np.ndarray,
    rel_step: float = 1e-6,
    abs_step: float = 1e-8,
) -> np.ndarray:
    """Central-difference Jacobian G = d(handles)/d(theta), shape (d, P).

    ``handle_fn`` maps a parameter vector to the handle vector (the app layer
    wraps build_slice + the handle reader per model). Each evaluation is a
    slice BUILD, not a fit, so the 2P calls are microseconds. The step is
    scaled per parameter (h_p = abs_step + rel_step * |theta_p|)."""
    theta = np.asarray(theta, dtype=float)
    base = np.asarray(handle_fn(theta), dtype=float)
    jac = np.empty((base.size, theta.size))
    for p in range(theta.size):
        h = abs_step + rel_step * abs(theta[p])
        up = theta.copy()
        dn = theta.copy()
        up[p] += h
        dn[p] -= h
        jac[:, p] = (
            np.asarray(handle_fn(up), dtype=float)
            - np.asarray(handle_fn(dn), dtype=float)
        ) / (2.0 * h)
    return jac


# --------------------------------------------------------------- R_x algebra
def information_matrix(solver_jac: np.ndarray) -> np.ndarray:
    """I_theta = J^T W J + Lambda_intrinsic in one product: the calibrators fold
    sqrt-weights into the residual rows and stack the intrinsic regularization
    (reg / calendar / barrier) as additional rows, so J^T J is the full
    observed information of the data-only fit (note eq. cov-delta)."""
    jac = np.asarray(solver_jac, dtype=float)
    return jac.T @ jac


def covariance_from_information(
    handle_jac: np.ndarray,
    info: np.ndarray,
    rank_rtol: float = INFO_RANK_RTOL,
) -> tuple[np.ndarray, int]:
    """R_x = G I^+ G^T via a REGULARIZED eigen-inverse (note eq. cov-delta).

    Eigenvalues below ``rank_rtol * max_eig`` are clamped up to the cutoff:
    a theta-combination the quotes do not identify contributes a large, finite
    variance instead of exploding (or silently vanishing, as a strict
    pseudo-inverse would). Returns (R_x, n_clamped) — a nonzero clamp count is
    a rank-deficiency diagnostic worth surfacing."""
    g = np.asarray(handle_jac, dtype=float)
    eigval, eigvec = np.linalg.eigh(np.asarray(info, dtype=float))
    cutoff = rank_rtol * max(float(eigval[-1]), 0.0)
    if cutoff <= 0.0:
        raise ValueError("information matrix has no positive eigenvalue")
    n_clamped = int(np.sum(eigval < cutoff))
    lam = np.maximum(eigval, cutoff)
    half = g @ eigvec / np.sqrt(lam)  # G V lam^{-1/2}
    r_x = half @ half.T
    return 0.5 * (r_x + r_x.T), n_clamped


def residual_inflation(
    residual: np.ndarray,
    n_fit_rows: int,
    n_quotes: int,
    n_handles: int = 3,
    cap: float = RESID_INFLATION_CAP,
) -> float:
    """rho = clip(chi^2 / max(m - d, 1), 1, cap)  (note eq. resid-inflation).

    chi^2 is the weighted quote-block misfit — the FIT rows of the solution
    residual (weights already folded in), excluding the intrinsic
    regularization rows; m is the QUOTE count (band mode has 2 rows per quote,
    the inactive hinges contributing zero). This is what makes a dense but
    internally contradictory cluster read as measurement noise: it cannot be
    fitted within its stated weights, chi^2 grows, and the Kalman gain falls."""
    rows = np.asarray(residual, dtype=float)[: int(n_fit_rows)]
    chi2 = float(rows @ rows)
    dof = max(int(n_quotes) - int(n_handles), 1)
    return float(np.clip(chi2 / dof, 1.0, cap))


def apply_variance_envelope(cov: np.ndarray) -> tuple[np.ndarray, int]:
    """Clip per-handle variances into the graph layer's sanity envelope
    [1/OBS_PRECISION_CAP, 1/OBS_PRECISION_FLOOR], rescaling rows/columns so the
    correlation structure survives. Returns (cov, n_clipped)."""
    cov = np.asarray(cov, dtype=float)
    diag = np.diag(cov).copy()
    lo = 1.0 / OBS_PRECISION_CAP
    hi = 1.0 / OBS_PRECISION_FLOOR
    target = np.clip(diag, lo, hi)
    n_clipped = int(np.sum(target != diag))
    scale = np.sqrt(target / np.where(diag > 0.0, diag, 1.0))
    out = cov * np.outer(scale, scale)
    np.fill_diagonal(out, target)  # exact on the diagonal despite zero-variance input
    return out, n_clipped


# --------------------------------------------------------------- the builders
def _scale_data_rows(
    solver_jac: np.ndarray,
    residual: np.ndarray,
    n_fit_rows: int,
    noise_scale: np.ndarray | float,
) -> tuple[np.ndarray, np.ndarray]:
    """Divide the FIT rows of (J, r) by the stated per-quote noise std (vol
    units; scalar or per-row of length n_fit_rows). The intrinsic reg rows
    keep their own scale — they are a prior, not a measurement."""
    jac = np.array(solver_jac, dtype=float, copy=True)
    res = np.array(residual, dtype=float, copy=True)
    n = int(n_fit_rows)
    inv = 1.0 / np.maximum(
        np.broadcast_to(np.asarray(noise_scale, dtype=float), (n,)), 1e-12
    )
    jac[:n] *= inv[:, None]
    res[:n] *= inv
    return jac, res


def measurement_from_jacobian(
    handles: np.ndarray,
    solver_jac: np.ndarray,
    handle_jac: np.ndarray,
    residual: np.ndarray,
    n_fit_rows: int,
    n_quotes: int,
    noise_scale: np.ndarray | float = 1.0,
    inflate: bool = True,
    inflation_cap: float = RESID_INFLATION_CAP,
    contaminated: bool = False,
) -> FilterMeasurement:
    """The Jacobian route (note eq. cov-delta + resid-inflation), audited.

    ``noise_scale`` is the stated per-quote noise std in vol units (bid-ask
    half-spread with a floor / haircut; scalar or per data row) — see the
    module docstring UNITS note. 1.0 means the rows already carry 1/noise."""
    z = np.asarray(handles, dtype=float)
    jac, res = _scale_data_rows(solver_jac, residual, n_fit_rows, noise_scale)
    info = information_matrix(jac)
    r_x, n_clamped = covariance_from_information(handle_jac, info)
    rho = (
        residual_inflation(
            res, n_fit_rows, n_quotes, n_handles=z.size, cap=inflation_cap
        )
        if inflate
        else 1.0
    )
    cov, n_clipped = apply_variance_envelope(rho * r_x)
    rows = res[: int(n_fit_rows)]
    return FilterMeasurement(
        handles=z,
        cov=cov,
        breakdown={
            "route": 1.0,  # 1 = jacobian, 0 = factors
            "nQuotes": float(n_quotes),
            "chi2": float(rows @ rows),
            "rho": rho,
            "infoClamped": float(n_clamped),
            "envelopeClipped": float(n_clipped),
        },
        contaminated=contaminated,
    )


def measurement_from_factors(
    handles: np.ndarray,
    rms_vol: float,
    n_atm_quotes: float,
    rel_spread: float,
    age_days: float = 0.0,
    contaminated: bool = False,
) -> FilterMeasurement:
    """The cheap fallback route (note eq. cheapR): R = diag(1 / precision) from
    the graph layer's factor vocabulary. The rms already carries the realized
    misfit, so no separate rho inflation is applied (it would double-count)."""
    z = np.asarray(handles, dtype=float)
    pb = observation_precision(rms_vol, n_atm_quotes, rel_spread, age_days)
    breakdown = {"route": 0.0, "nQuotes": float(n_atm_quotes)}
    breakdown.update(pb.factors)
    return FilterMeasurement(
        handles=z,
        cov=np.diag(1.0 / pb.precision),
        breakdown=breakdown,
        contaminated=contaminated,
    )
