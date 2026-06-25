"""Shared precision vocabulary (Phase 1 of Docs/prior_persistence_roadmap.md).

The generic factors + the activation gate (design note §9.3) used by every prior
mode. The graph baseline must remain byte-identical after the lift (graph/
precision.py now re-imports these), which test_graph_precision.py also guards; here
we test the gate directly.
"""

import numpy as np

from volfit.calib import precision as prec
from volfit.graph import precision as gprec


# ---------------------------------------------------------- scalar factors
def test_factors_monotone_and_bounded():
    # quote density saturates and floors
    assert prec.quote_density_factor(100.0) == 1.0
    assert prec.quote_density_factor(0.0) == prec.MIN_DENSITY_FACTOR
    assert prec.quote_density_factor(2.0) < prec.quote_density_factor(6.0)
    # wider spread, older age, further transport => smaller factor, all in (0, 1]
    assert prec.spread_factor(0.0) == 1.0
    assert 0.0 < prec.spread_factor(0.2) < prec.spread_factor(0.02) <= 1.0
    assert prec.freshness_factor(0.0) == 1.0
    assert prec.freshness_factor(10.0) < prec.freshness_factor(1.0)
    assert prec.transport_factor(0.0) == 1.0
    assert prec.transport_factor(0.2) < prec.transport_factor(0.05)


# ------------------------------------------------------------- the gate (§9.3)
def test_gap_zero_when_well_observed():
    """obs >= required => gap 0 => the prior turns fully off (don't damp signal)."""
    assert float(prec.activation_gap(5.0, 1.0)) == 0.0
    assert float(prec.activation_gap(1.0, 1.0)) == 0.0


def test_gap_one_when_unobserved():
    """obs = 0 => gap 1 => the prior is fully active."""
    assert float(prec.activation_gap(0.0, 1.0)) == 1.0


def test_gap_monotone_and_gamma_sharpens():
    half = float(prec.activation_gap(0.5, 1.0, gamma=1.0))
    assert abs(half - 0.5) < 1e-12
    # a larger gamma sharpens the transition (smaller gap for the same partial obs)
    assert float(prec.activation_gap(0.5, 1.0, gamma=2.0)) < half


def test_gap_vectorized():
    obs = np.array([0.0, 0.5, 2.0])
    gap = prec.activation_gap(obs, np.array([1.0, 1.0, 1.0]))
    assert np.allclose(gap, [1.0, 0.5, 0.0])


def test_active_prior_precision_scales_by_gap():
    base = np.array([1e6, 1e4])
    gap = np.array([1.0, 0.0])
    assert np.allclose(prec.active_prior_precision(base, gap), [1e6, 0.0])


# ------------------------------------------------- graph re-export is the same
def test_graph_reexports_shared_factors():
    assert gprec.spread_factor is prec.spread_factor
    assert gprec.freshness_factor is prec.freshness_factor
    assert gprec.transport_factor is prec.transport_factor
    assert gprec.RMS_FLOOR == prec.RMS_FLOOR


def test_graph_design_point_unchanged():
    """The legacy [1e6, 1e6, 1e4] regime at the design point (active/dense/tight/
    fresh) survives the refactor — the golden anchor for the whole graph path."""
    obs = gprec.observation_precision(rms_vol=0.001, n_atm_quotes=8, rel_spread=0.0)
    base = gprec.baseline_precision("active_transported")
    assert np.allclose(obs.precision, [1e6, 1e6, 1e4])
    assert np.allclose(base.precision, [1e6, 1e6, 1e4])
