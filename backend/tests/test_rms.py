"""Calibration-consistent RMS error (volfit.calib.rms + service/affine wiring).

The reported RMS must mean "how well does the displayed fit meet its OWN
objective": distance to the chosen fit target (mid / bid-ask / haircut band),
the active weighting scheme, and the var-swap quote — and a whole-surface number
alongside the per-smile one, displayed the same way in both workspaces.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from volfit.calib.band import resolve_band
from volfit.calib.rms import node_error_terms, rms
from volfit.api import service
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


# ----------------------------------------------------------- the pure metric
def test_mid_mode_is_weighted_rms_distance_to_mid():
    model = np.array([0.21, 0.20, 0.19])
    mid = np.array([0.20, 0.20, 0.20])
    num, den = node_error_terms(model, mid, weights=None)
    assert den == 3.0
    assert rms(num, den) == pytest.approx(np.sqrt((0.01**2 + 0.0 + 0.01**2) / 3))


def test_band_mode_zero_inside_band_distance_outside():
    band = resolve_band(
        np.array([0.18, 0.18]), np.array([0.20, 0.20]), np.array([0.22, 0.22]), "bidask"
    )
    # First quote inside [0.18, 0.22] -> 0; second 0.01 above the ask -> 0.01.
    model = np.array([0.20, 0.23])
    num, den = node_error_terms(model, np.array([0.20, 0.20]), band=band)
    assert rms(num, den) == pytest.approx(np.sqrt((0.0 + 0.01**2) / 2))


def test_weights_bias_the_rms():
    model = np.array([0.22, 0.20])
    mid = np.array([0.20, 0.20])
    heavy_on_error = node_error_terms(model, mid, weights=np.array([9.0, 1.0]))
    heavy_on_clean = node_error_terms(model, mid, weights=np.array([1.0, 9.0]))
    assert rms(*heavy_on_error) > rms(*heavy_on_clean)


def test_var_swap_term_adds_at_its_weight():
    model = np.array([0.20])
    mid = np.array([0.20])  # perfect on the quote
    # Model var-swap vol 0.25 vs quoted 0.20, weight 4.
    num, den = node_error_terms(model, mid, weights=np.array([1.0]), var_swap=(0.25, 0.20, 4.0))
    assert den == 5.0
    assert rms(num, den) == pytest.approx(np.sqrt((0.0 + 4.0 * 0.05**2) / 5.0))


# --------------------------------------------------- service-level behaviour
def _state() -> AppState:
    return AppState(REF_DATE)


def test_band_mode_rms_not_above_mid_mode():
    """A bid-ask fit sits inside the band, so its band-violation RMS is <= the
    mid-distance RMS of the same node (often ~0)."""
    s = _state()
    iso = sorted(s.forwards(TICKER))[1].isoformat()
    rec_mid = service.fit_or_get(s, TICKER, iso, "mid")
    rms_mid = service.weighted_rms_error(s, TICKER, iso, rec_mid, "mid")
    rec_band = service.fit_or_get(s, TICKER, iso, "bidask")
    rms_band = service.weighted_rms_error(s, TICKER, iso, rec_band, "bidask")
    assert rms_band <= rms_mid + 1e-9
    assert rms_mid >= 0.0


def test_surface_rms_pools_expiries():
    """The surface RMS lies within the per-node RMS range (a pooled aggregate)."""
    s = _state()
    fit_mode = "mid"
    per_node = []
    for e in sorted(s.forwards(TICKER)):
        iso = e.isoformat()
        rec = service.fit_or_get(s, TICKER, iso, fit_mode)
        per_node.append(service.weighted_rms_error(s, TICKER, iso, rec, fit_mode))
    surface = service.surface_rms_error(s, TICKER, fit_mode)
    assert min(per_node) - 1e-9 <= surface <= max(per_node) + 1e-9


def test_smile_payload_exposes_both_rms():
    s = _state()
    iso = sorted(s.forwards(TICKER))[1].isoformat()
    data = service.smile_payload(s, TICKER, iso, "mid")
    assert data.diagnostics.rmsError >= 0.0
    assert data.surfaceRmsError >= 0.0
