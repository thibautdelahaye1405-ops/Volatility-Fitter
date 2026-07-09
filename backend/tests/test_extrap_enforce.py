"""Tapered extrapolated-region enforcement (Notes 09/10 Phase 2, calib/extrap).

Locks the four contracts: (1) OFF / absent is byte-identical (the house
additive-feature invariant); (2) the rows are INACTIVE on an admissible pair
(clean fits are untouched to fit precision); (3) on a genuine extrapolated
calendar conflict the enforcement LEANS — the crossing shrinks materially —
without outvoting the data (traded-range RMS stays bounded); (4) the
``extrapEnforce`` toggle is calibration-affecting (options-version bump).
"""

from __future__ import annotations

from datetime import date

import numpy as np

from volfit.api.state import AppState
from volfit.calib.extrap import build_extrap_target
from volfit.models.svi_jw.calibrate import calibrate_svi
from volfit.models.svi_jw.svi import RawSVI

T = 0.25
K = np.linspace(-0.25, 0.25, 21)
TRUE = RawSVI(a=0.008, b=0.08, rho=-0.3, m=0.0, sigma=0.15)
W = TRUE.total_variance(K)


def _sig(raw, k):
    return np.sqrt(np.maximum(raw.total_variance(k), 1e-12) / T)


def _rms_bp(raw):
    return float(np.sqrt(np.mean((_sig(raw, K) - np.sqrt(W / T)) ** 2))) * 1e4


def test_envelope_geometry():
    """Non-degenerate quotes produce a two-wing envelope with a decreasing
    taper that is full-strength at the traded edge; the calendar floor is the
    previous slice's w on the same grid."""
    prev = RawSVI(a=0.009, b=0.095, rho=-0.3, m=0.0, sigma=0.15)
    tgt = build_extrap_target(K, W, prev_slice=prev, prev_lee=(0.12, 0.07))
    assert tgt is not None
    assert tgt.k_left.size > 5 and tgt.k_right.size > 5
    assert tgt.taper_right[0] > 0.5  # near-full strength at the boundary
    assert np.all(np.diff(tgt.taper_right) <= 1e-12)  # monotone decay outward
    np.testing.assert_allclose(
        tgt.cal_floor_right, prev.total_variance(tgt.k_right), rtol=1e-12
    )
    assert tgt.prev_lee == (0.12, 0.07)


def test_envelope_empty_when_worthless():
    """A tiny-vol slice quoted out to far OTM strikes: nothing to enforce."""
    k = np.array([-0.8, 0.0, 0.8])
    w = np.full(3, 1e-4)
    assert build_extrap_target(k, w) is None


def test_clean_pair_is_a_noop():
    """Previous expiry strictly below: every hinge is zero, the fit lands on
    the same solution (inactive-on-admissible, the house penalty invariant)."""
    prev = RawSVI(a=0.006, b=0.06, rho=-0.3, m=0.0, sigma=0.15)
    tgt = build_extrap_target(K, W, prev_slice=prev, prev_lee=(prev.b * 1.3, prev.b * 0.7))
    off = calibrate_svi(K, W, T)
    on = calibrate_svi(K, W, T, extrap=tgt)
    assert abs(_rms_bp(on.raw) - _rms_bp(off.raw)) < 1e-3
    np.testing.assert_allclose(
        on.raw.total_variance(K), off.raw.total_variance(K), rtol=1e-6
    )


def test_conflict_leans_without_dominating():
    """A mildly fatter previous wing (a REAL extrapolated calendar crossing):
    enforcement shrinks the crossing materially while the traded-range RMS
    stays far below the publish budget — leaning, not flattening (the
    phantom-calendar lesson)."""
    prev = RawSVI(a=0.009, b=0.095, rho=-0.3, m=0.0, sigma=0.15)
    tgt = build_extrap_target(
        K, W, prev_slice=prev, prev_lee=(prev.b * (1 + 0.3), prev.b * (1 - 0.3))
    )
    kx = np.concatenate([tgt.k_left, tgt.k_right])

    def crossing_bp(raw):
        return float(np.maximum(_sig(prev, kx) - _sig(raw, kx), 0.0).max()) * 1e4

    off = calibrate_svi(K, W, T)
    on = calibrate_svi(K, W, T, extrap=tgt)
    assert crossing_bp(on.raw) < 0.7 * crossing_bp(off.raw)  # material lean
    assert _rms_bp(on.raw) < 50.0  # never outvotes the data (publish budget)
    assert _rms_bp(off.raw) < 1.0  # sanity: the unconstrained fit is exact


def test_extrap_enforce_bumps_options_version():
    state = AppState(date(2026, 6, 10))
    v0 = state.options_version
    state.set_options(state.options().model_copy(update={"extrapEnforce": True}))
    assert state.options_version == v0 + 1
    state.set_options(state.options().model_copy(update={"extrapEnforce": False}))
    assert state.options_version == v0 + 2
