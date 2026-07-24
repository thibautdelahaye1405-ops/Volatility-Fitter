"""Committee revision R1 (Note 02 review, 2026-07-24): the Lee boundary trap.

Lee's moment bound is beta <= 2, but the boundary itself is NOT safe: at
beta = 2 the tail limit of Durrleman's g is (4 - beta^2)/16 = 0 and the sign
is decided at the next order, g(k) = (alpha - 2)/(4k) + O(k^-2) with
alpha = a - 2m on the right wing. The committee counterexample

    (a, b, rho, m, s) = (0.04, 2, 0, 0, 0.2)

has positive minimum variance (0.44) and both wings exactly AT the bound, so
the OLD default cap (2.0, hinge zero at equality) charged it NO penalty —
yet g(10) = -0.0485: genuinely negative tail density behind passing screens.

These locks guard the fix forever (certification case svi_lee_boundary):
the production default cap is strictly buffered (2 - LEE_SLOPE_BUFFER); a
fit pulled toward beta = 2 is fenced at the buffer, restoring a strictly
positive tail limit; and the historical cap stays reachable as explicit
configuration (the harness pins it for part comparability).
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.api.schemas import FitSettings
from volfit.models.svi_jw.calibrate import (
    LEE_SLOPE_BUFFER,
    _LEE_SLOPE_MAX,
    calibrate_svi,
)
from volfit.models.svi_jw.svi import RawSVI

#: The committee counterexample: both wings exactly at Lee's bound.
BOUNDARY_SLICE = RawSVI(a=0.04, b=2.0, rho=0.0, m=0.0, sigma=0.2)


def durrleman_g(raw: RawSVI, k: float) -> float:
    """Durrleman's g from the slice's OWN derivatives (closed form — the
    production rule: never finite-difference prices)."""
    km = k - raw.m
    r = np.sqrt(km * km + raw.sigma**2)
    w = raw.a + raw.b * (raw.rho * km + r)
    wp = raw.b * (raw.rho + km / r)
    wpp = raw.b * raw.sigma**2 / r**3
    return float(
        (1.0 - k * wp / (2.0 * w)) ** 2 - (wp * wp / 4.0) * (1.0 / w + 0.25) + wpp / 2.0
    )


def test_beta2_boundary_admits_negative_tail_density():
    """The trap itself: both screens pass at the OLD cap, g < 0 in the tail."""
    raw = BOUNDARY_SLICE
    min_var = raw.a + raw.b * raw.sigma * np.sqrt(1.0 - raw.rho**2)
    assert min_var == pytest.approx(0.44)  # floor screen passes
    wing = raw.b * (1.0 + abs(raw.rho))
    assert wing == 2.0  # exactly AT Lee's bound: old hinge max(wing-2,0) == 0
    # Negative tail density — matching the next-order law (alpha-2)/(4k).
    assert durrleman_g(raw, 10.0) == pytest.approx(-0.04852, abs=5e-4)
    alpha = raw.a - 2.0 * raw.m
    assert durrleman_g(raw, 10.0) == pytest.approx((alpha - 2.0) / 40.0, rel=0.05)
    for k in (5.0, 10.0, 20.0, 50.0, 1000.0):
        assert durrleman_g(raw, k) < 0.0  # eventually (and persistently) negative


def test_default_cap_is_strictly_buffered():
    """The shipped defaults sit strictly under 2, everywhere they are set."""
    assert _LEE_SLOPE_MAX == pytest.approx(2.0 - LEE_SLOPE_BUFFER)
    assert _LEE_SLOPE_MAX < 2.0
    assert FitSettings().leeSlopeMax == pytest.approx(_LEE_SLOPE_MAX)
    # The buffer restores the theorem: a strictly positive tail LIMIT.
    assert (4.0 - _LEE_SLOPE_MAX**2) / 16.0 > 0.0


def test_fit_toward_the_boundary_is_fenced_at_the_buffer():
    """Quotes sampled FROM the beta=2 slice: the default fit lands at the
    buffered cap (strictly under 2, positive tail limit); the historical cap
    stays reachable as explicit configuration and reproduces the loophole."""
    t = 0.25
    k = np.linspace(-1.5, 1.5, 25)
    w = BOUNDARY_SLICE.total_variance(k)

    fenced = calibrate_svi(k, w, t)  # default lee_slope_max
    wing = fenced.raw.b * (1.0 + abs(fenced.raw.rho))
    assert wing <= _LEE_SLOPE_MAX + 1e-3  # the soft fence holds
    assert (4.0 - wing**2) / 16.0 > 0.0  # strictly positive tail limit
    assert durrleman_g(fenced.raw, 1e4) > 0.0  # tail density positive far out

    legacy = calibrate_svi(k, w, t, lee_slope_max=2.0)  # explicit old cap
    legacy_wing = legacy.raw.b * (1.0 + abs(legacy.raw.rho))
    assert legacy_wing > _LEE_SLOPE_MAX + 1e-3  # the loophole, on request only
    assert legacy_wing <= 2.0 + 1e-6
