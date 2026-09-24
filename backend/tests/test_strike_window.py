"""The shared per-expiry strike-window rule (volfit.data.strike_window)."""

from __future__ import annotations

import math
from datetime import date

from volfit.data.strike_window import (
    HALF_WIDTH_CAP,
    HALF_WIDTH_FLOOR,
    half_width,
    inside,
    strike_bounds,
)

TODAY = date(2026, 9, 24)


def test_half_width_scales_with_sqrt_time_between_floor_and_cap():
    two_days = half_width(date(2026, 9, 26), TODAY)
    assert abs(two_days - 4.0 * math.sqrt(2 / 365)) < 1e-12  # 4 sd at 100 % vol
    assert half_width(TODAY, TODAY) == half_width(date(2026, 9, 25), TODAY)  # 0DTE = 1 day
    assert half_width(TODAY, TODAY) > HALF_WIDTH_FLOOR
    assert half_width(date(2027, 9, 24), TODAY) == HALF_WIDTH_CAP  # a year hits the cap (4·1·√1 = 4 > 3)
    assert half_width(date(2026, 9, 26), TODAY, sigma_ref=0.01) == HALF_WIDTH_FLOOR  # floor binds
    assert half_width(date(2026, 9, 26), TODAY, sigma_ref=None) is None  # window off


def test_bounds_contain_the_preps_band_under_the_stated_condition():
    """The prep keeps |ln(K/F)| <= 4 sigma sqrt(T); the window contains that
    band whenever 4 sigma sqrt(T) + |ln(F/S)| <= half_width(T) — below the
    cap every name under the reference vol by the carry margin, at the cap
    (a year) every name with ATM vol <= ~75 %."""
    spot = 100.0
    for exp, sigmas in ((date(2026, 10, 24), (0.1, 0.4, 0.9)), (date(2027, 9, 24), (0.1, 0.4, 0.7))):
        lo, hi = strike_bounds(spot, exp, TODAY)
        t = (exp - TODAY).days / 365
        hw = half_width(exp, TODAY)
        for sigma in sigmas:
            band = 4.0 * sigma * math.sqrt(t)
            for drift in (-0.02, 0.0, 0.02):  # forward vs spot
                assert band + abs(drift) <= hw  # the condition holds for these cases
                k_lo, k_hi = drift - band, drift + band
                assert lo <= spot * math.exp(k_lo) and spot * math.exp(k_hi) <= hi
    # and it is a real saving on a short rung: a 2-day window is ~30 % wide
    lo, hi = strike_bounds(spot, date(2026, 9, 26), TODAY)
    assert 0.7 < lo / spot < 0.75 and 1.33 < hi / spot < 1.4


def test_bounds_none_without_a_usable_spot_and_inside_handles_none():
    assert strike_bounds(None, TODAY, TODAY) is None
    assert strike_bounds(0.0, TODAY, TODAY) is None
    assert strike_bounds(float("nan"), TODAY, TODAY) is None
    assert inside(123.0, None) is True
    lo, hi = strike_bounds(100.0, date(2026, 9, 26), TODAY)
    assert inside(lo, (lo, hi)) and inside(hi, (lo, hi)) and not inside(hi * 1.01, (lo, hi))
