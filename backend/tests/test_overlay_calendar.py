"""Model-agnostic calendar constraint for the SVI / Multi-Core SIV overlays.

The LQD backbone enforces calendar order through its asset-share curve
(tests/test_surface.py); the SVI and sigmoid display overlays carry no such
curve, so they use Gatheral's equivalent surface condition — total variance
non-decreasing in maturity at every fixed log-moneyness, w_far(k) >= w_near(k)
(volfit.calib.calendar.variance_floor_targets).

Golden invariant: with no floor the calibrators are byte-identical to before
(so every other test still pins the unconstrained fit); given a floor from a
nearer slice quoted *above* the far quotes (a calendar arbitrage in the data),
the constraint crushes the violation by orders of magnitude.
"""

import numpy as np

from tests import benchmarks as bm
from volfit.api.fit_models import build_display_fit
from volfit.api.schemas import FitSettings
from volfit.calib.calendar import (
    variance_floor_grid,
    variance_floor_grid_from,
    variance_floor_targets,
)
from volfit.models.sigmoid import calibrate_sigmoid
from volfit.models.svi_jw import RawSVI, calibrate_svi

K = np.linspace(*bm.SVI_FIT_RANGE, 41)
W_NEAR = bm.SVI_RAW.total_variance(K)
T_FAR = 1.0
#: Far quotes that sit *below* the near slice in total variance => calendar arb.
W_FAR_ARB = 0.8 * W_NEAR


def _violation(model, floor_k, floor_w) -> float:
    """Worst amount the model's total variance drops below the floor (>=0)."""
    return float(np.max(floor_w - model.implied_w(floor_k)))


# --------------------------------------------------------------- the floor
def test_variance_floor_reads_prev_total_variance():
    """The floor is exactly the previous slice's total variance on the grid."""
    k, w = variance_floor_targets(bm.SVI_RAW, K)
    np.testing.assert_allclose(w, bm.SVI_RAW.total_variance(K))
    np.testing.assert_array_equal(k, K)


def test_variance_floor_default_grid_spans_wings():
    """The default grid covers the drawn wing range k in [-1, 1]."""
    k, _ = variance_floor_targets(bm.SVI_RAW)
    np.testing.assert_array_equal(k, variance_floor_grid())
    assert k[0] == -1.0 and k[-1] == 1.0


# ------------------------------------------------------------------- SVI
def test_svi_no_floor_is_byte_identical():
    """Passing no calendar floor leaves the SVI fit byte-for-byte unchanged."""
    base = calibrate_svi(K, W_FAR_ARB, t=T_FAR)
    same = calibrate_svi(K, W_FAR_ARB, t=T_FAR, calendar_k=None, calendar_floor=None)
    got = np.array([same.raw.a, same.raw.b, same.raw.rho, same.raw.m, same.raw.sigma])
    want = np.array([base.raw.a, base.raw.b, base.raw.rho, base.raw.m, base.raw.sigma])
    np.testing.assert_array_equal(got, want)


def test_svi_floor_crushes_calendar_violation():
    """A near slice above the far quotes is calendar arb; the floor repairs it."""
    floor_k, floor_w = variance_floor_targets(bm.SVI_RAW, K)
    free = calibrate_svi(K, W_FAR_ARB, t=T_FAR)
    bound = calibrate_svi(
        K, W_FAR_ARB, t=T_FAR, calendar_k=floor_k, calendar_floor=floor_w
    )
    free_v = _violation(free.raw, floor_k, floor_w)
    bound_v = _violation(bound.raw, floor_k, floor_w)
    assert free_v > 1e-3  # the data really is in calendar arbitrage
    assert bound_v < 0.05 * free_v
    # The repaired far slice can no longer match the inconsistent quotes.
    assert bound.max_iv_error > free.max_iv_error


# --------------------------------------------------------------- sigmoid
def test_sigmoid_no_floor_is_byte_identical():
    """Passing no calendar floor leaves the Multi-Core SIV fit unchanged."""
    base = calibrate_sigmoid(K, W_FAR_ARB, t=T_FAR, n_cores=2)
    same = calibrate_sigmoid(
        K, W_FAR_ARB, t=T_FAR, n_cores=2, calendar_k=None, calendar_floor=None
    )
    np.testing.assert_array_equal(base.implied_w(K), same.implied_w(K))


def test_sigmoid_floor_crushes_calendar_violation():
    """The total-variance floor lifts the Multi-Core SIV far slice above arb."""
    floor_k, floor_w = variance_floor_targets(bm.SVI_RAW, K)
    free = calibrate_sigmoid(K, W_FAR_ARB, t=T_FAR, n_cores=2)
    bound = calibrate_sigmoid(
        K, W_FAR_ARB, t=T_FAR, n_cores=2, calendar_k=floor_k, calendar_floor=floor_w
    )
    free_v = _violation(free, floor_k, floor_w)
    bound_v = _violation(bound, floor_k, floor_w)
    assert free_v > 1e-3
    assert bound_v < 0.1 * free_v


# ------------------------------- the wide-grid extrapolation bug (regression)
# A steep short-dated near slice (large b, like a single-name skew) has linear
# wings that extrapolate to far higher total variance at the wide-grid edges
# (k = +/-1) than a flatter long-dated far slice. The fixed [-1, 1] floor reads
# that as a calendar violation in a no-data region and wrecks the in-data fit;
# confining the floor to the traded range repairs it. (Reported live on NVDA /
# SPY: the far SVI expiries fit flat with huge RMS under the wide grid.)
NEAR_STEEP = RawSVI(a=0.01, b=0.20, rho=-0.7, m=0.0, sigma=0.05)
FAR_FLAT = RawSVI(a=0.08, b=0.08, rho=-0.3, m=0.0, sigma=0.10)
K_NARROW = np.linspace(-0.25, 0.20, 21)  # the far expiry's traded span only
W_FAR_NARROW = FAR_FLAT.total_variance(K_NARROW)


def test_far_above_near_inside_data_but_not_in_wings():
    """The scenario is calendar-consistent on the data but not in extrapolation."""
    # Far sits above near across the traded range (no real arb to repair)...
    assert np.all(FAR_FLAT.total_variance(K_NARROW) > NEAR_STEEP.total_variance(K_NARROW))
    # ...yet the steep near slice extrapolates ABOVE far at the wide-grid edge.
    assert NEAR_STEEP.total_variance(-1.0) > FAR_FLAT.total_variance(-1.0)


def test_wide_grid_breaks_svi_but_data_grid_does_not():
    """The data-confined floor keeps the far SVI fit clean; the wide grid ruins it."""
    clean = calibrate_svi(K_NARROW, W_FAR_NARROW, t=1.0)

    wide_k, wide_w = variance_floor_targets(NEAR_STEEP, variance_floor_grid())
    wide = calibrate_svi(K_NARROW, W_FAR_NARROW, t=1.0, calendar_k=wide_k, calendar_floor=wide_w)

    data_k, data_w = variance_floor_targets(NEAR_STEEP, variance_floor_grid_from(K_NARROW))
    data = calibrate_svi(K_NARROW, W_FAR_NARROW, t=1.0, calendar_k=data_k, calendar_floor=data_w)

    # The wide grid manufactures a wing violation and destroys the in-data fit.
    assert wide.max_iv_error > 5e-3
    # The data-confined floor stays essentially as clean as the unconstrained fit.
    assert data.max_iv_error < 1e-3
    assert data.max_iv_error < 0.1 * wide.max_iv_error
    np.testing.assert_allclose(data.max_iv_error, clean.max_iv_error, atol=1e-3)


# --------------------------------------- build_display_fit (service entry)
def test_build_display_fit_threads_floor_to_overlays():
    """The service-facing builder applies the floor to both overlay families."""
    floor = variance_floor_targets(bm.SVI_RAW, K)
    for model in ("svi", "sigmoid"):
        settings = FitSettings(model=model)
        free = build_display_fit(model, K, W_FAR_ARB, T_FAR, None, settings)
        bound = build_display_fit(
            model, K, W_FAR_ARB, T_FAR, None, settings, calendar_floor=floor
        )
        free_v = _violation(free.slice, floor[0], floor[1])
        bound_v = _violation(bound.slice, floor[0], floor[1])
        assert free_v > 1e-3, model
        assert bound_v < 0.1 * free_v, model


def test_build_display_fit_no_floor_byte_identical():
    """No floor (the LQD-coupled-only default) leaves the overlay unchanged."""
    for model in ("svi", "sigmoid"):
        settings = FitSettings(model=model)
        a = build_display_fit(model, K, W_FAR_ARB, T_FAR, None, settings)
        b = build_display_fit(
            model, K, W_FAR_ARB, T_FAR, None, settings, calendar_floor=None
        )
        np.testing.assert_array_equal(a.slice.implied_w(K), b.slice.implied_w(K))
