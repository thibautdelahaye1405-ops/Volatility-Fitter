"""One-expiry eSSVI calibration: (theta, rho, phi) by bounded least squares.

Fits the SSVI slice of models/essvi/essvi.py (Gatheral-Jacquier 2014 eq.
4.1, per-expiry rho as in Hendriks-Martini 2019) to total-variance quotes
with the SAME data term the SVI-JW comparator fit uses
(models/svi_jw/calibrate.py, default chart, vol-space residuals): residuals
in implied-vol units, optional per-quote scheme weights, and in the band
modes the bid-ask / haircut hinge + soft mid anchor of volfit.calib.band
evaluated in vol space — so the rms / max columns of the compare row score
the four families against one and the same objective. Comparator-only, so
the SVI overlay's production extras (var-swap / prior / calendar / extrap
blocks, robust IRLS passes, price-space residuals, belly repair) are
deliberately NOT carried.

The three handles are reparametrized so the solver can only propose an
admissible slice, then run under trf with the stated bounds:

    theta = exp(x0) >= 1e-8,   rho = 0.999 tanh(x1) in (-0.999, 0.999),
    phi = exp(x2) >= 1e-6.

The two no-butterfly conditions of GJ Theorem 4.2 enter as soft hinges
(``penalty_weight * relu``, exactly zero on an admissible slice):

    (i)  theta phi (1 + |rho|) < 4 — written in Lee-slope form,
         theta phi (1 + |rho|) / 2 <= lee_slope_max, with the SAME strictly
         buffered cap the SVI family honours (2 - LEE_SLOPE_BUFFER = 1.95):
         the boundary 4 itself admits negative tail density;
    (ii) theta phi^2 (1 + |rho|) <= 4, held at 4 - _CURVATURE_BUFFER for the
         same reason: AT the boundary g touches zero, and a soft hinge lands
         a hair (~1e-6) past its target — the buffer keeps that overshoot
         strictly inside the theorem's region, so the fitted slice always
         certifies (g >= 0 on the whole line).

Seed (data-driven, ``seed_slice``): theta_0 is the quote strip interpolated
at k = 0 (w(0) = theta exactly). A local quadratic through the quotes
nearest ATM reads w'(0) = rho phi theta and w''(0) = theta phi^2 (1-rho^2)/2,
which invert in closed form to phi_0 = sqrt(c + s^2), rho_0 = s / phi_0 with
s = w'(0)/theta and c = 2 w''(0)/theta — the skew fixes the sign of rho, the
curvature the size of phi. When the local curvature is not positive (a
kinked or one-sided strip) the seed falls back to the two chord slopes
about the belly, which estimate theta phi (1 -/+ rho)/2 the way SVI's
initializer reads its wings. Either seed is projected inside the GJ region.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from volfit.calib.band import (
    MID_ANCHOR_WEIGHT,
    BandTarget,
    band_residuals,
    effective_mid_anchor,
)
from volfit.calib.rms import max_quote_error
from volfit.models.essvi.essvi import ESSVISlice, butterfly_lhs
from volfit.models.svi_jw.calibrate import LEE_SLOPE_BUFFER

#: Soft-penalty weight of the two GJ hinges (the SVI family's constant).
_PENALTY = 1e3
#: The buffered Lee cap shared with SVI-JW (strictly inside condition (i)).
_LEE_SLOPE_MAX = 2.0 - LEE_SLOPE_BUFFER
#: Condition (ii) target: 4 minus a buffer (module docstring), economically
#: free — it trims phi by 0.25 % at most.
_CURVATURE_BUFFER = 0.02
_CURVATURE_MAX = 4.0 - _CURVATURE_BUFFER
#: Solver stopping rule: converged to fit precision (the residual is in vol
#: units, so 1e-12 is far below any quote), with an evaluation budget that
#: three handles never approach — trf must end with a status, not a budget.
_TOL = 1e-12
_MAX_NFEV = 2000
#: Parameter bounds of the stated reparametrization.
_THETA_MIN = 1e-8
_PHI_MIN = 1e-6
_RHO_CAP = 0.999
#: Seed projection factor: the start sits strictly inside both GJ conditions.
_SEED_SHRINK = 0.9
#: Quotes nearest ATM read by the local-quadratic seed.
_SEED_LOCAL = 7


@dataclass(frozen=True)
class ESSVICalibration:
    """Fitted eSSVI slice plus convergence / fit diagnostics."""

    slice: ESSVISlice
    cost: float
    n_evaluations: int
    success: bool
    max_iv_error: float  # max |model - target| implied vol over the quotes


def _unpack(x: np.ndarray, t: float) -> ESSVISlice:
    """Map the bounded solver vector to an admissible slice."""
    return ESSVISlice(
        theta=float(np.exp(x[0])),
        rho=float(_RHO_CAP * np.tanh(x[1])),
        phi=float(np.exp(x[2])),
        t=t,
    )


def _pack(slice_: ESSVISlice) -> np.ndarray:
    """Invert the reparametrization (clipped strictly inside the bounds)."""
    rho = float(np.clip(slice_.rho / _RHO_CAP, -1.0 + 1e-9, 1.0 - 1e-9))
    return np.array([
        np.log(max(slice_.theta, 10.0 * _THETA_MIN)),
        np.arctanh(rho),
        np.log(max(slice_.phi, 10.0 * _PHI_MIN)),
    ])


def butterfly_hinges(slice_: ESSVISlice, lee_slope_max: float = _LEE_SLOPE_MAX) -> np.ndarray:
    """relu rows of the two GJ Theorem 4.2 conditions (zero when admissible):
    ``[max(theta phi (1+|rho|)/2 - lee_slope_max, 0),
    max(theta phi^2 (1+|rho|) - _CURVATURE_MAX, 0)]``."""
    c1, c2 = butterfly_lhs(slice_)
    return np.array([max(0.5 * c1 - lee_slope_max, 0.0), max(c2 - _CURVATURE_MAX, 0.0)])


def _project_seed(theta: float, rho: float, phi: float, t: float, lee_slope_max: float) -> ESSVISlice:
    """Cap phi so the seed satisfies both GJ conditions with a margin."""
    lift = theta * (1.0 + abs(rho))
    phi_max = _SEED_SHRINK * min(2.0 * lee_slope_max / lift, np.sqrt(_CURVATURE_MAX / lift))
    phi = min(max(phi, 10.0 * _PHI_MIN), float(phi_max))
    return ESSVISlice(theta=theta, rho=rho, phi=phi, t=t)


def seed_slice(
    k: np.ndarray, w: np.ndarray, t: float, lee_slope_max: float = _LEE_SLOPE_MAX
) -> ESSVISlice:
    """Data-driven start (module docstring): ATM level, then the local ATM
    quadratic (skew -> sign of rho, curvature -> phi) with a chord fallback."""
    k = np.asarray(k, dtype=float)
    w = np.asarray(w, dtype=float)
    order = np.argsort(k)
    k_s, w_s = k[order], w[order]
    theta0 = max(float(np.interp(0.0, k_s, w_s)), 10.0 * _THETA_MIN)

    rho0 = phi0 = None
    n_loc = min(k_s.size, _SEED_LOCAL)
    if n_loc >= 3:
        idx = np.argsort(np.abs(k_s))[:n_loc]
        design = np.column_stack([k_s[idx] ** 2, k_s[idx], np.ones(n_loc)])
        c2, c1, _c0 = np.linalg.lstsq(design, w_s[idx], rcond=None)[0]
        # c1 = w'(0) = rho phi theta;  c2 = w''(0)/2 = theta phi^2 (1-rho^2)/4.
        s, c = c1 / theta0, 4.0 * c2 / theta0  # rho phi, phi^2 (1 - rho^2)
        if c > 0.0:
            phi0 = float(np.sqrt(c + s * s))
            rho0 = float(s / phi0)
    if phi0 is None:  # chord fallback: theta phi (1 -/+ rho) / 2 from the wings
        mid = int(np.argmin(np.abs(k_s)))
        right = (w_s[-1] - w_s[mid]) / max(k_s[-1] - k_s[mid], 1e-3)
        left = (w_s[mid] - w_s[0]) / max(k_s[mid] - k_s[0], 1e-3)
        slope_r, slope_l = max(right, 1e-3), max(-left, 1e-3)
        phi0 = float((slope_r + slope_l) / theta0)
        rho0 = float((slope_r - slope_l) / (slope_r + slope_l))
    rho0 = float(np.clip(rho0, -0.95, 0.95))
    return _project_seed(theta0, rho0, phi0, t, lee_slope_max)


def calibrate_essvi(
    k: np.ndarray,
    w_quotes: np.ndarray,
    t: float,
    weights: np.ndarray | None = None,
    band: BandTarget | None = None,
    penalty_weight: float = _PENALTY,
    lee_slope_max: float = _LEE_SLOPE_MAX,
    mid_anchor_weight: float = MID_ANCHOR_WEIGHT,
    mid_anchor_tau_ref: float | None = None,
    seed: ESSVISlice | None = None,
) -> ESSVICalibration:
    """Least-squares fit of an SSVI slice to total-variance quotes.

    ``k``/``w_quotes`` are log-moneyness and total implied variance; ``t`` the
    expiry year fraction. ``weights`` are per-quote LSQ weights multiplying
    the squared vol residual (None = unit). ``band`` switches the data term to
    the bid-ask / haircut band objective in vol space (None = mid LSQ);
    ``mid_anchor_weight`` / ``mid_anchor_tau_ref`` are the band's (tau-
    attenuated) mid anchor exactly as the SVI overlay reads them.
    ``penalty_weight`` / ``lee_slope_max`` are the GJ hinge coefficients.
    ``seed`` overrides the data-driven start (tests: a violating seed must
    be repaired by the hinges; the caller owns its admissibility).

    Refuses DETERMINISTICALLY with a reason below three usable quotes (the
    SVI convention): three handles against fewer quotes are unidentified.
    """
    k = np.asarray(k, dtype=float)
    w_quotes = np.asarray(w_quotes, dtype=float)
    if k.size < 3:
        raise ValueError(
            f"eSSVI needs at least 3 usable quotes (got {k.size}): "
            "three handles against fewer quotes are unidentified"
        )
    vol_quotes = np.sqrt(w_quotes / t)
    sq_w = np.ones_like(k) if weights is None else np.sqrt(np.asarray(weights, float))
    maw_eff = effective_mid_anchor(mid_anchor_weight, t, mid_anchor_tau_ref)

    def residuals(x: np.ndarray) -> np.ndarray:
        slice_ = _unpack(x, t)
        model_vol = np.sqrt(np.maximum(slice_.total_variance(k), 1e-12) / t)
        if band is None:
            fit = sq_w * (model_vol - vol_quotes)
        else:
            fit = band_residuals(model_vol, band.iv_lo, band.iv_hi, band.iv_mid, sq_w, maw_eff)
        return np.concatenate((fit, penalty_weight * butterfly_hinges(slice_, lee_slope_max)))

    start = seed if seed is not None else seed_slice(k, w_quotes, t, lee_slope_max)
    lower = np.array([np.log(_THETA_MIN), -np.inf, np.log(_PHI_MIN)])
    result = least_squares(
        residuals, _pack(start), method="trf", bounds=(lower, np.full(3, np.inf)),
        xtol=_TOL, ftol=_TOL, gtol=_TOL, max_nfev=_MAX_NFEV,
    )
    fitted = _unpack(result.x, t)
    model_vol = np.sqrt(np.maximum(fitted.total_variance(k), 1e-12) / t)
    return ESSVICalibration(
        slice=fitted,
        cost=float(result.cost),
        n_evaluations=int(result.nfev),
        success=bool(result.success),
        max_iv_error=max_quote_error(model_vol, vol_quotes, band),  # vs the fit target
    )
