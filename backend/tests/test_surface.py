"""Sequential surface fitting with the integrated-quantile calendar constraint."""

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.calib import ExpiryQuotes, calibrate_surface
from volfit.calib.calendar import calendar_violation

K_GRID = np.linspace(*bm.SVI_FIT_RANGE, 41)
W_NEAR = bm.SVI_RAW.total_variance(K_GRID)


def test_arbitrage_free_surface_fits_clean():
    """Proportional total variance (flat vol in T) has no calendar arb; the
    constrained fit should match both slices and report ~zero violation."""
    quotes = [
        ExpiryQuotes(t=0.5, k=K_GRID, w=W_NEAR),
        ExpiryQuotes(t=1.0, k=K_GRID, w=2.0 * W_NEAR),
    ]
    fit = calibrate_surface(quotes, enforce_calendar=True)
    assert fit.expiries == [0.5, 1.0]
    assert all(r.max_iv_error < 5e-4 for r in fit.results)
    assert fit.max_calendar_violation < 1e-7


def test_violating_quotes_get_repaired_when_enforced():
    """A later expiry quoted *below* the near one in total variance is a hard
    calendar arbitrage; enforcement should crush the violation by orders of
    magnitude relative to independent fits."""
    quotes = [
        ExpiryQuotes(t=0.5, k=K_GRID, w=W_NEAR),
        ExpiryQuotes(t=1.0, k=K_GRID, w=0.8 * W_NEAR),
    ]

    free = calibrate_surface(quotes, enforce_calendar=False)
    constrained = calibrate_surface(quotes, enforce_calendar=True)

    violation_free = calendar_violation(free.results[0].slice, free.results[1].slice)
    assert violation_free > 1e-3  # the data really is in calendar arbitrage

    assert constrained.max_calendar_violation < 1e-3
    assert constrained.max_calendar_violation < 0.05 * violation_free

    # The repaired far slice can no longer match the inconsistent quotes —
    # the residual misfit is the slack diagnostic, and it must be visible.
    assert constrained.results[1].max_iv_error > 0.005


def test_unsorted_input_is_sorted_by_expiry():
    quotes = [
        ExpiryQuotes(t=1.0, k=K_GRID, w=2.0 * W_NEAR),
        ExpiryQuotes(t=0.5, k=K_GRID, w=W_NEAR),
    ]
    fit = calibrate_surface(quotes, enforce_calendar=True)
    assert fit.expiries == [0.5, 1.0]
