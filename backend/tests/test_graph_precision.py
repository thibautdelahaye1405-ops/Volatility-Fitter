"""Data-derived observation / baseline precision (plan Phase 4).

Precision is part of the product truth: better fits, denser/tighter chains and
fresher data must enter the solver with more observation precision; stronger
provenance and less transport with more baseline precision. Bounded by explicit
floors/caps. These tests pin the monotonicities and the bounds, plus that the
extrapolate response surfaces the precision + factor breakdown.
"""

from datetime import date

import numpy as np

from volfit.api import priors
from volfit.api.graph_extrapolation import extrapolate
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.api.state import AppState
from volfit.graph import precision as gprec

REF_DATE = date(2026, 6, 10)


def test_lower_fit_quality_lowers_observation_precision():
    good = gprec.observation_precision(rms_vol=0.001, n_atm_quotes=8, rel_spread=0.01)
    bad = gprec.observation_precision(rms_vol=0.02, n_atm_quotes=8, rel_spread=0.01)
    assert np.all(bad.precision <= good.precision)
    assert bad.precision[0] < good.precision[0]


def test_wider_spread_lowers_observation_precision():
    tight = gprec.observation_precision(0.003, 8, rel_spread=0.01)
    wide = gprec.observation_precision(0.003, 8, rel_spread=0.20)
    assert wide.precision[0] < tight.precision[0]
    assert wide.factors["spread"] < tight.factors["spread"]


def test_sparser_chain_lowers_observation_precision():
    dense = gprec.observation_precision(0.003, n_atm_quotes=10, rel_spread=0.01)
    sparse = gprec.observation_precision(0.003, n_atm_quotes=2, rel_spread=0.01)
    assert sparse.precision[0] < dense.precision[0]


def test_staler_asof_lowers_observation_precision():
    fresh = gprec.observation_precision(0.003, 8, 0.01, age_days=0.0)
    stale = gprec.observation_precision(0.003, 8, 0.01, age_days=10.0)
    assert stale.precision[0] < fresh.precision[0]


def test_bootstrap_baseline_below_active():
    active = gprec.baseline_precision("active_transported")
    boot = gprec.baseline_precision("today_bootstrap")
    assert np.all(boot.precision < active.precision)


def test_transport_distance_lowers_baseline_precision():
    near = gprec.baseline_precision("active_transported", transport_distance=0.0)
    far = gprec.baseline_precision("active_transported", transport_distance=0.15)
    assert far.precision[0] < near.precision[0]
    assert far.factors["transport"] < 1.0


def test_design_point_reproduces_legacy_regime():
    """active / dense / tight / fresh lands on the legacy [1e6, 1e6, 1e4]."""
    obs = gprec.observation_precision(rms_vol=0.001, n_atm_quotes=8, rel_spread=0.0)
    np.testing.assert_allclose(obs.precision, [1.0e6, 1.0e6, 1.0e4], rtol=1e-9)
    base = gprec.baseline_precision("active_transported")
    np.testing.assert_allclose(base.precision, [1.0e6, 1.0e6, 1.0e4], rtol=1e-9)


def test_floors_and_caps_hold():
    # A degenerate fit cannot zero precision (floor) nor a perfect one explode (cap).
    floored = gprec.observation_precision(rms_vol=10.0, n_atm_quotes=0, rel_spread=10.0)
    assert np.all(floored.precision >= gprec.OBS_PRECISION_FLOOR)
    capped = gprec.observation_precision(rms_vol=1e-9, n_atm_quotes=1e6, rel_spread=0.0)
    assert np.all(capped.precision <= gprec.OBS_PRECISION_CAP)


def test_response_surfaces_precision_and_factors():
    state = AppState(REF_DATE)
    for tk in state.active_tickers():
        snap = priors.capture_snapshot(state, tk, "mid")
        if snap is not None:
            state.set_active_prior(tk, snap, "saved")
    # Darken one node so the response carries both an obs node and a baseline-only one.
    tk = state.active_tickers()[0]
    dark_iso = [e.isoformat() for e in sorted(state.forwards(tk))][1]
    state.set_node_lit(tk, dark_iso, False)

    resp = extrapolate(state, GraphExtrapolateRequest())
    lit = next(n for n in resp.nodes if n.calibrated)
    assert len(lit.baselinePrecision) == 3
    assert lit.obsPrecision is not None and len(lit.obsPrecision) == 3
    assert "rmsBase" in lit.precisionFactors and "sourceBase" in lit.precisionFactors

    dark = next(n for n in resp.nodes if n.ticker == tk and n.expiry == dark_iso)
    assert dark.obsPrecision is None  # dark node has no observation precision
    assert len(dark.baselinePrecision) == 3
