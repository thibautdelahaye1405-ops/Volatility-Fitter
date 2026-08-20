"""V3.1 leg 4: the MCS calendar upgrade — polished-dense certificate + the
wing-extended in-fit floor grid.

(a) ``variance_floor_grid_winged`` extends the sigmoid family's floor/ceiling
grid past the common quote support by the wing-penalty pad (2 z-units of the
fitting slice) at the SAME node budget; no-floor fits stay byte-identical
(locked in test_overlay_calendar).
(b) ``mcs_calendar_certificate``: dense scan + Brent-polished interior minima
of w_far − w_near, plus the analytic wing-order clause (eq mcsbetak) deciding
the far field. Advisory quality fields overlayCal* for sigmoid-displayed
adjacent pairs.
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.calib.calendar import (
    VAR_FLOOR_N_DATA,
    variance_floor_grid_common,
    variance_floor_grid_winged,
)
from volfit.models.sigmoid import HatCore, MultiCoreSiv
from volfit.models.sigmoid.calendar_certificate import mcs_calendar_certificate

NEAR = MultiCoreSiv(
    v0=0.04, s0=-0.004, k0=0.15, z0=0.0, kappa_p=4.0, kappa_c=3.0,
    sigma_ref=0.2, t=0.25,
)
#: Ordered far slice: everywhere above NEAR with steeper-or-equal wings.
FAR_OK = MultiCoreSiv(
    v0=0.05, s0=-0.004, k0=0.16, z0=0.0, kappa_p=4.0, kappa_c=3.0,
    sigma_ref=0.2, t=0.5,
)
#: Violating far slice: a barely-higher level with a notch dipping BELOW the
#: near slice's total variance around its centre.
FAR_BAD = MultiCoreSiv(
    v0=0.0205, s0=-0.002, k0=0.075, z0=0.0, kappa_p=4.0, kappa_c=3.0,
    sigma_ref=0.2, t=0.5, cores=(HatCore(alpha=-0.004, c=-0.8, h=0.4, kappa=6.0),),
)
#: Far slice ABOVE the near everywhere scanned but with FLATTER wings: the
#: far field must fail by the analytic wing-order clause.
FAR_FLAT = MultiCoreSiv(
    v0=0.08, s0=-0.001, k0=0.02, z0=0.0, kappa_p=4.0, kappa_c=3.0,
    sigma_ref=0.2, t=0.5,
)


def test_ordered_pair_certifies():
    cert = mcs_calendar_certificate(NEAR, FAR_OK)
    assert cert.certified(1e-6)
    assert cert.min_gap > 0.0
    assert cert.wing_order_ok


def test_violating_pair_is_caught_and_located():
    ks = np.linspace(-1.0, 1.0, 2001)
    gap = FAR_BAD.implied_w(ks) - NEAR.implied_w(ks)
    assert gap.min() < 0.0, "test premise: the pair genuinely crosses"
    cert = mcs_calendar_certificate(NEAR, FAR_BAD)
    assert not cert.certified(1e-6)
    assert cert.min_gap < 0.0
    # The polished minimizer sits where the dense reference scan says it is.
    assert abs(cert.k_star - float(ks[np.argmin(gap)])) < 5e-3
    # ... and the polish is at least as deep as any scan sample there.
    assert cert.min_gap <= float(gap.min()) + 1e-12


def test_polish_refines_the_scan():
    """Brent lands the true local minimum: no denser scan can undercut it by
    more than solver tolerance (the polished-dense contract)."""
    cert = mcs_calendar_certificate(NEAR, FAR_BAD)
    fine = np.linspace(cert.k_lo, cert.k_hi, 40001)
    gap_fine = FAR_BAD.implied_w(fine) - NEAR.implied_w(fine)
    assert cert.min_gap <= float(gap_fine.min()) + 1e-10


def test_wing_order_clause_decides_far_field():
    """A far slice above the near everywhere the scan reaches but with flatter
    asymptotic wings (eq mcsbetak): eventually the near overtakes — the
    analytic clause must fail the certificate even with a positive scan min."""
    cert = mcs_calendar_certificate(NEAR, FAR_FLAT)
    assert not cert.wing_order_ok
    assert not cert.certified(1e-6)
    n_lee, f_lee = NEAR.lee_slopes(), FAR_FLAT.lee_slopes()
    assert f_lee[0] < n_lee[0] and f_lee[1] < n_lee[1]


def test_explicit_slope_overrides_are_honoured():
    """The backtest's SVI arm passes closed-form slopes: overrides drive the
    wing clause verbatim."""
    ok = mcs_calendar_certificate(NEAR, FAR_OK, near_lee=(0.1, 0.1), far_lee=(0.2, 0.2))
    bad = mcs_calendar_certificate(NEAR, FAR_OK, near_lee=(0.3, 0.1), far_lee=(0.2, 0.2))
    assert ok.wing_order_ok and not bad.wing_order_ok


# ------------------------------------------------- the wing-extended floor grid
def test_winged_grid_extends_by_the_wing_pad_at_same_budget():
    kq = np.linspace(-0.3, 0.25, 21)
    w = NEAR.implied_w(kq)
    common = variance_floor_grid_common(kq, kq)
    winged = variance_floor_grid_winged(kq, kq, w, 0.25)
    assert winged.size == common.size == VAR_FLOOR_N_DATA  # same node budget
    # Pad = 2 z-units of the fitting slice: 2 * sigma_ref * sqrt(t), with
    # sigma_ref the quoted vol nearest the money (the calibrator's own rule).
    vol = np.sqrt(np.maximum(w, 1e-12) / 0.25)
    sigma_ref = float(vol[np.argmin(np.abs(kq))])
    pad = 2.0 * sigma_ref * np.sqrt(0.25)
    assert winged[0] == pytest.approx(common[0] - pad, rel=1e-12)
    assert winged[-1] == pytest.approx(common[-1] + pad, rel=1e-12)


def test_winged_grid_none_without_common_support():
    a = np.array([0.2, 0.4])
    b = np.array([-0.4, -0.2])
    assert variance_floor_grid_winged(a, b, np.full(2, 0.01), 0.25) is None
