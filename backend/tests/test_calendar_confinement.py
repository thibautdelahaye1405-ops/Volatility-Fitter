"""Common-support confinement of the calendar constraint (symmetric-surface
Phase 0) — locks the phantom-calendar mechanism of Note 10.

The failure this guards: an acutely convex short-dated slice, quoted on a
narrow strike span, extrapolates a steep LQD wing. The historical full-grid
calendar floor compared that extrapolated wing against the next expiry over
the ENTIRE tail-dense quantile grid, so a far slice that sits comfortably
ABOVE the near one everywhere both are quoted was still dragged up in the
wings — off its own quotes (the SPY/NVDA phantom-calendar case).

The confinement must happen in PRICE space at fixed strike: G(alpha)
integrates the whole upper tail, so a merely z-windowed a_z floor stays
tail-contaminated (measured: it removes only about half the drag). The
confined floor is normalized-call ordering C_far(k) >= C_near(k) on the
intersection of the retained quote spans.
"""

import numpy as np

from volfit.calib import ExpiryQuotes, calibrate_surface
from volfit.calib.calendar import (
    calendar_floor_targets,
    calendar_violation,
    calendar_violation_windowed,
    common_support,
    confined_calendar_floor,
    support_taper,
    variance_floor_grid_common,
)
from volfit.models.lqd.calibrate import calibrate_slice

# Acute short-dated slice: 2% of a year, 20% ATM vol, extreme smile curvature
# (event-style straddle), quoted only on a tight +/-6% span. Deliberately
# harder than the LQD body order resolves — what matters is the steep wing it
# extrapolates, not the residual body misfit.
T_NEAR = 0.02
K_NEAR = np.linspace(-0.06, 0.06, 13)
W_NEAR = 0.0008 + 0.6 * K_NEAR**2

# Ordinary far slice: 3 months, 20% ATM vol, flat wings, quoted much wider.
# On the common span it sits FAR above the near slice (no identified arb),
# but the near fit's extrapolated wing crosses it well inside the far span.
T_FAR = 0.25
K_FAR = np.linspace(-0.30, 0.30, 25)
W_FAR = 0.010 + 0.004 * K_FAR**2


def _fit_near():
    return calibrate_slice(K_NEAR, W_NEAR, t=T_NEAR)


def _fit_far(**cal_kwargs):
    return calibrate_slice(K_FAR, W_FAR, t=T_FAR, **cal_kwargs)


# ------------------------------------------------------------------ helpers
def test_common_support_intersection_and_disjoint():
    assert common_support(K_NEAR, K_FAR) == (-0.06, 0.06)
    assert common_support(K_FAR, K_NEAR) == (-0.06, 0.06)
    assert common_support(np.array([0.2, 0.4]), np.array([-0.4, -0.2])) is None
    assert common_support(np.array([]), K_FAR) is None


def test_support_taper_shape():
    window = (-0.1, 0.1)
    k = np.array([-0.5, -0.1, 0.0, 0.1, 0.5])
    taper = support_taper(k, window)
    assert taper[0] == 0.0 and taper[-1] == 0.0  # far outside: dropped
    assert np.all(taper[1:4] == 1.0)  # inside (incl. edges): full weight
    # Smooth monotone falloff across the margin, strictly interior in (0, 1).
    edge = support_taper(np.linspace(0.1, 0.2, 9), window)
    assert np.all(np.diff(edge) <= 1e-12)
    assert 0.0 < edge[2] < 1.0


def test_confined_floor_is_the_near_call_curve_on_common_support():
    near = _fit_near()
    window = common_support(K_NEAR, K_FAR)
    confined = confined_calendar_floor(near.slice, window)
    assert confined is not None
    k, floor, taper = confined
    assert k.size == floor.size == taper.size
    assert np.all((taper > 0.0) & (taper <= 1.0))
    # The grid spans the window plus (at most) the taper margin cap.
    assert k.min() >= window[0] - 0.25 and k.max() <= window[1] + 0.25
    # The floor is the near slice's own normalized call curve.
    assert np.allclose(floor, near.slice.call_price(k))


def test_variance_floor_grid_common():
    grid = variance_floor_grid_common(K_NEAR, K_FAR)
    assert grid is not None
    assert grid.min() == -0.06 and grid.max() == 0.06
    assert variance_floor_grid_common(np.array([0.2, 0.4]), np.array([-0.4, -0.2])) is None


def test_windowed_violation_full_grid_fallback():
    near, far = _fit_near(), _fit_far()
    full = calendar_violation(near.slice, far.slice)
    assert calendar_violation_windowed(near.slice, far.slice, None) == full


def test_taper_of_ones_matches_untapered_rows():
    """calendar_taper=None and an explicit all-ones taper are the same objective."""
    near = _fit_near()
    window = common_support(K_NEAR, K_FAR)
    k, floor, _taper = confined_calendar_floor(near.slice, window)
    a = _fit_far(calendar_k=k, calendar_price_floor=floor)
    b = _fit_far(
        calendar_k=k, calendar_price_floor=floor, calendar_taper=np.ones(k.size)
    )
    assert np.array_equal(a.params.to_vector(), b.params.to_vector())


# ------------------------------------------------- the phantom-calendar lock
def test_confined_floor_kills_the_phantom_calendar_drag():
    """Far quotes sit above the acute near slice everywhere both are quoted, so
    the identified constraint is INACTIVE — yet the historical full-grid floor
    drags the far fit off its quotes. The confined price floor must not."""
    near = _fit_near()
    far_free = _fit_far()
    window = common_support(K_NEAR, K_FAR)

    # Sanity: no identified (common-support, price-space) violation between
    # the free fits...
    assert calendar_violation_windowed(near.slice, far_free.slice, window) <= 1e-7
    # ...but the acute near wing DOES cross the far slice in the extrapolated
    # tails — the raw material of the phantom constraint.
    assert calendar_violation(near.slice, far_free.slice) > 1e-6

    # Historical behavior: full-grid floor => the far fit is dragged off quote.
    full_z, full_floor = calendar_floor_targets(near.slice)
    far_full = _fit_far(calendar_z=full_z, calendar_floor=full_floor)

    # New behavior: confined price floor => the far fit stays at its free fit.
    k, floor, taper = confined_calendar_floor(near.slice, window)
    far_conf = _fit_far(
        calendar_k=k, calendar_price_floor=floor, calendar_taper=taper
    )

    assert far_free.max_iv_error < 2e-3  # the far quotes are cleanly fittable
    assert far_conf.max_iv_error < far_free.max_iv_error + 1e-4
    assert far_full.max_iv_error > 10.0 * far_free.max_iv_error


def test_surface_ladder_with_acute_short_slice_stays_on_quote():
    """End-to-end calibrate_surface: the acute near slice must not contaminate
    the far fit, and the reported (confined) calendar residual stays clean."""
    far_free = _fit_far()
    fit = calibrate_surface(
        [
            ExpiryQuotes(t=T_NEAR, k=K_NEAR, w=W_NEAR),
            ExpiryQuotes(t=T_FAR, k=K_FAR, w=W_FAR),
        ],
        enforce_calendar=True,
    )
    assert fit.results[1].max_iv_error < far_free.max_iv_error + 1e-4
    assert fit.max_calendar_violation < 1e-6
