"""Signed-basket operator-prior residuals in the affine LV calibration (Phase 4).

The basket is a dense linear functional of the leg call prices (like a var-swap),
so it keeps the RR/BF coupling the per-leg projection drops. Gates:
  * baskets=[] is byte-identical to no baskets (golden guard);
  * a strong basket pulls the fitted surface's basket value toward its target;
  * baskets run through both the TRF and the (dense-operator) GN solver.
"""

import numpy as np

from volfit.models.localvol import (
    AffineVarianceSurface,
    BasketQuote,
    OptionQuote,
    calibrate_affine,
)

TAU = np.array([0.0, 0.5, 1.0])
XI = np.array([0.0, 0.70, 0.90, 1.00, 1.10, 1.30, 2.20])
X_GRID = 0.01 * np.arange(221)
T_GRID = 0.005 * np.arange(201)
QUOTE_TABLE = [
    (0.25, 0.80, 0.200277), (0.25, 0.90, 0.105645), (0.25, 1.00, 0.036544),
    (0.25, 1.10, 0.007310), (0.25, 1.20, 0.000861),
    (0.50, 0.80, 0.202596), (0.50, 0.90, 0.115765), (0.50, 1.00, 0.053085),
    (0.50, 1.10, 0.019104), (0.50, 1.20, 0.005456),
    (1.00, 0.80, 0.211163), (1.00, 0.90, 0.133968), (1.00, 1.00, 0.076657),
    (1.00, 1.10, 0.039690), (1.00, 1.20, 0.018833),
]


def _inputs():
    options = [OptionQuote(t=t, x=x, price=p, tol=2e-4) for t, x, p in QUOTE_TABLE]
    flat = AffineVarianceSurface(t_nodes=TAU, x_nodes=XI, theta=np.full((3, 7), 0.04))
    return flat, options


def _basket_value(cal, t, xs, weights):
    """Σ weights·P_model(xs) on a fitted calibration's solution at expiry t."""
    idx = {float(e): i for i, e in enumerate(cal.solution.expiries)}
    p = cal.solution.price_at(idx[t], np.asarray(xs))
    return float(np.asarray(weights) @ p)


def test_empty_baskets_byte_identical():
    flat, options = _inputs()
    base = calibrate_affine(flat, options, X_GRID, T_GRID, reg_lambda=50.0)
    with_empty = calibrate_affine(flat, options, X_GRID, T_GRID, reg_lambda=50.0, baskets=[])
    assert np.array_equal(base.surface.theta, with_empty.surface.theta)


def test_basket_pulls_surface_toward_target():
    flat, options = _inputs()
    xs, w = [1.15, 0.85], [1.0, -1.0]  # a skew (difference) functional between quotes
    base = calibrate_affine(flat, options, X_GRID, T_GRID, reg_lambda=50.0)
    b0 = _basket_value(base, 0.5, xs, w)
    target = 0.5 * b0  # ask the fit to halve the skew functional
    basket = BasketQuote(t=0.5, xs=np.array(xs), weights=np.array(w), target=target, tol=1e-3)
    pulled = calibrate_affine(
        flat, options, X_GRID, T_GRID, reg_lambda=50.0, baskets=[basket]
    )
    b1 = _basket_value(pulled, 0.5, xs, w)
    assert abs(b1 - target) < abs(b0 - target)  # moved toward the target
    # the basket is a soft difference penalty, not a quote wreck: the option fit
    # stays a clean sub-percent price RMS (the golden quotes resist the skew push
    # since the legs sit among them, but the surface is not destabilized)
    assert pulled.rms_price_error < 5e-3


def test_basket_runs_under_gn():
    flat, options = _inputs()
    basket = BasketQuote(
        t=0.5, xs=np.array([1.15, 0.85]), weights=np.array([1.0, -1.0]),
        target=-0.05, tol=1e-2,
    )
    cal = calibrate_affine(
        flat, options, X_GRID, T_GRID, reg_lambda=50.0, baskets=[basket], gn=True
    )
    assert np.all(np.isfinite(cal.surface.theta))
    assert cal.surface.theta.min() >= 0.005 - 1e-9
