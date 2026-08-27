"""Robust (IRLS) driver for the affine LV calibration — FitSettings.robustLoss.

The LV analogue of the parametric models' robust data objective (models/lqd/
calibrate.py, svi_jw/calibrate.py — the original LV "fix-order #3", shipped
2026-08-27). Implemented as Iteratively Reweighted Least Squares over the
OPTION-QUOTE block only: scipy's global ``loss=`` would also soften the
var-swap / basket / roughness / convexity / front-tie rows, which must stay
quadratic to keep their prior-and-penalty semantics.

Units. An LV option row is ``(P_model − P_mid) / tol`` with ``tol = vega ·
VOL_TOL / √w`` (affine_fit._option_quotes), i.e. a SCHEME-weighted vol error
in units of VOL_TOL. The IRLS multiplier must NOT see the scheme weight
(FitSettings.robustFScale is specified in the residual's own units — vol —
not in weighted units), so the per-quote magnitude is rebuilt from the price
error and the quote's own vega:

    mid mode   |P_model − P_mid| / vega                  ≈ |σ_model − σ_mid|
    band mode  sqrt(viol² + maw · (P_model − P_mid)²) / vega

exactly ``calib.band.quote_residual_magnitude`` with ``scale = 1/vega`` — the
same helper (and the same ``robust_multipliers``) the parametric models use,
so one ``robustFScale`` (default 0.005 = 50 vol bp) means the same thing for
every model. ``vega`` is the Black vega at the quote's own implied vol,
inverted from (x, price, t) so the driver needs nothing beyond the quotes.

Each pass folds ``√m_i`` into the row weight by scaling the quote tolerance
``tol_i → tol_i / √m_i`` (the squared residual then carries ``m_i``) and
re-solves WARM-STARTED from the previous surface (``theta_ref`` and every
other kwarg unchanged, so the regularization is untouched) — two passes, like
the parametric IRLS. ``robust_loss == "off"`` returns the single base solve
untouched: byte-identical. The multipliers are SOLVER-INTERNAL: the reported
``option_errors`` are still ``P_model − P_mid`` per quote and every RMS the
API shows keeps the scheme weights.
"""

from __future__ import annotations

from dataclasses import replace as dc_replace

import numpy as np

from volfit.calib.band import (
    MID_ANCHOR_WEIGHT,
    quote_residual_magnitude,
    robust_multipliers,
)
from volfit.core.black import black_vega_sigma, implied_total_variance
from volfit.models.localvol.affine import AffineVarianceSurface
from volfit.models.localvol.affine_calib import (
    AffineCalibration,
    OptionQuote,
    calibrate_affine,
)

#: Number of warm-started IRLS re-solves after the base fit (parametric parity).
IRLS_PASSES = 2
#: Vega floor for the 1/vega magnitude scale (deep wings at tiny vega).
_VEGA_FLOOR = 1e-4
#: Multiplier floor: a redescending (cauchy) weight can vanish; keep tol finite.
_M_FLOOR = 1e-12
_W_FLOOR = 1e-12


def quote_inv_vega(options: list[OptionQuote]) -> np.ndarray:
    """1/vega per quote at the quote's OWN implied vol (Black-inverted from its
    normalized forward call price), floored. This is the price-to-vol scale of
    the residual magnitude; a price outside the static bounds (no implied vol)
    gets the floor vega so it simply keeps full weight."""
    k = np.array([np.log(o.x) for o in options], dtype=float)
    t = np.array([o.t for o in options], dtype=float)
    p = np.array([o.price for o in options], dtype=float)
    w = np.asarray(implied_total_variance(k, p), dtype=float)
    ok = np.isfinite(w) & (w > 0.0)
    sigma = np.sqrt(np.where(ok, np.maximum(w, _W_FLOOR), _W_FLOOR) / t)
    vega = np.where(ok, black_vega_sigma(k, sigma, t), 0.0)
    return 1.0 / np.maximum(np.where(np.isfinite(vega), vega, 0.0), _VEGA_FLOOR)


def option_block_magnitudes(
    cal: AffineCalibration, options: list[OptionQuote], mid_anchor_weight: float
) -> np.ndarray:
    """Per-quote UNWEIGHTED residual magnitude in VOL units (see module doc)."""
    mid = np.array([o.price for o in options], dtype=float)
    band = bool(options) and options[0].price_lo is not None
    lo = np.array([o.price_lo for o in options], dtype=float) if band else None
    hi = np.array([o.price_hi for o in options], dtype=float) if band else None
    return quote_residual_magnitude(
        cal.option_prices, mid, lo, hi, mid_anchor_weight, quote_inv_vega(options)
    )


def irls_multipliers(magnitudes: np.ndarray, loss: str, f_scale: float) -> np.ndarray:
    """IRLS weight multipliers m_i (huber: min(1, f/|r|); cauchy: 1/(1+(r/f)²)) —
    the SAME formulas as the parametric models (calib.band.robust_multipliers,
    reused, not duplicated). ``magnitudes`` in vol units, ``f_scale`` likewise."""
    return robust_multipliers(magnitudes, loss, f_scale)


def reweighted_quotes(options: list[OptionQuote], m: np.ndarray) -> list[OptionQuote]:
    """Fold √m_i into each quote by scaling its tolerance ``tol_i / √m_i`` (the
    squared LSQ residual then carries ``m_i``); band edges and prices untouched."""
    return [
        dc_replace(o, tol=float(o.tol / np.sqrt(max(float(mi), _M_FLOOR))))
        for o, mi in zip(options, m)
    ]


def calibrate_affine_robust(
    surface0: AffineVarianceSurface,
    options: list[OptionQuote],
    x_grid: np.ndarray,
    t_grid: np.ndarray,
    *,
    robust_loss: str = "off",
    robust_f_scale: float = 0.005,
    n_passes: int = IRLS_PASSES,
    **kwargs,
) -> AffineCalibration:
    """``calibrate_affine`` plus ``n_passes`` warm-started IRLS re-solves.

    ``robust_loss`` "off" (or no quotes) ⇒ exactly one ``calibrate_affine`` call
    with the given kwargs — byte-identical to calling it directly. Otherwise
    each pass derives the quote multipliers at the current solution (module
    doc), rescales the quote tolerances, and re-solves from the current
    surface (theta AND the fitted left-wing slope) with every other kwarg —
    ``theta_ref``, bounds, penalties, var-swaps, baskets, solver knobs — as
    given. The returned calibration is the last pass's, with ``n_evals`` summed
    over all passes so the diagnostics stay honest about the cost.
    """
    cal = calibrate_affine(surface0, options, x_grid, t_grid, **kwargs)
    if robust_loss == "off" or not options:
        return cal
    maw = float(kwargs.get("mid_anchor_weight", MID_ANCHOR_WEIGHT))
    total_evals = cal.n_evals
    for _ in range(max(0, int(n_passes))):
        mag = option_block_magnitudes(cal, options, maw)
        m = irls_multipliers(mag, robust_loss, robust_f_scale)
        warm = surface0.with_theta(cal.surface.theta.ravel()).with_left_extrap_a(
            cal.left_extrap_a
        )
        cal = calibrate_affine(warm, reweighted_quotes(options, m), x_grid, t_grid, **kwargs)
        total_evals += cal.n_evals
    return dc_replace(cal, n_evals=total_evals)
