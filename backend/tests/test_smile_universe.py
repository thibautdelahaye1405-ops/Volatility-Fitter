"""End-to-end round trip: observe a few smiles, extrapolate the universe,
rebuild arbitrage-free slices with credible bands.

Scenario: two tickers x three expiries. Ticker A's whole curve shifts up
2 vol points; only A's 6-month smile is observed. The graph (strong
same-ticker calendar edges, weaker cross-ticker edges) must push A's other
expiries most of the way, move B only weakly, and every reconstructed slice
must remain a genuine arbitrage-free density with exact posterior handles.
"""

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.graph import build_increment_prior
from volfit.graph.smile_universe import (
    SmileNode,
    build_universe,
    node_handles,
    propagate_handles,
    reconstruct_smiles,
)
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.quadrature import build_slice

TICKERS = ("A", "B")
EXPIRIES = (0.25, 0.5, 1.0)
VOL_SHIFT = 0.02  # true move on ticker A's ATM vol


@pytest.fixture(scope="module")
def universe():
    smiles = [
        SmileNode(name=(tk, t), t=t, params=bm.SVI_LQD_PARAMS)
        for tk in TICKERS
        for t in EXPIRIES
    ]
    weights = {}
    for tk in TICKERS:  # strong calendar chain within a ticker
        for t_near, t_far in zip(EXPIRIES[:-1], EXPIRIES[1:]):
            weights[((tk, t_near), (tk, t_far))] = 10.0
            weights[((tk, t_far), (tk, t_near))] = 10.0
    for t in EXPIRIES:  # weaker cross-ticker edges at equal expiry
        weights[(("A", t), ("B", t))] = 2.0
        weights[(("B", t), ("A", t))] = 2.0
    return build_universe(smiles, weights)


@pytest.fixture(scope="module")
def field(universe):
    # Per-coordinate increment scales (~3 vol pts level, looser skew/curv);
    # eta keeps a fixed ratio to kappa so the smoothness residual is ~1/3 of
    # the increment scale — the regime where same-ticker propagation is
    # strong (~75% of the move) and cross-ticker stays weak (~6%).
    priors = [
        build_increment_prior(universe.graph, kappa=1.0 / scale**2, eta=eta)
        for scale, eta in ((0.03, 2.0e4), (0.05, 7.0e3), (0.5, 70.0))
    ]
    observed_node = ("A", 0.5)
    i_obs = universe.node_index(observed_node)
    observed_handles = universe.handles[i_obs] + np.array([VOL_SHIFT, 0.0, 0.0])
    return propagate_handles(
        universe,
        priors,
        observed={observed_node: observed_handles},
        baseline_precision=np.array([1.0e6, 1.0e6, 1.0e4]),
        observation_precision=np.array([1.0e6, 1.0e6, 1.0e4]),
    )


def test_observed_node_lands_on_observation(universe, field):
    i = universe.node_index(("A", 0.5))
    assert field.mean[i, 0] == pytest.approx(universe.handles[i, 0] + VOL_SHIFT, abs=1e-4)


def test_signal_propagates_along_ticker_more_than_across(universe, field):
    shift = field.mean[:, 0] - universe.handles[:, 0]
    a_near = shift[universe.node_index(("A", 0.25))]
    a_far = shift[universe.node_index(("A", 1.0))]
    b_mid = shift[universe.node_index(("B", 0.5))]
    # Same-ticker neighbors take most of the move; cross-ticker takes less.
    assert a_near > 0.5 * VOL_SHIFT
    assert a_far > 0.5 * VOL_SHIFT
    assert 0.0 < b_mid < a_near
    # Held-out A nodes end closer to the truth than the baseline was.
    assert abs(a_near - VOL_SHIFT) < VOL_SHIFT
    assert abs(a_far - VOL_SHIFT) < VOL_SHIFT


def test_uncertainty_shrinks_most_where_signal_arrives(universe, field):
    sd_vol = field.sd[:, 0]
    assert sd_vol[universe.node_index(("A", 0.5))] < 2e-3  # observed: pinned
    # Unobserved nodes keep honest, larger uncertainty.
    assert sd_vol[universe.node_index(("B", 1.0))] > sd_vol[universe.node_index(("A", 0.25))]
    lo, hi = field.atm_vol_band()
    assert np.all(lo < field.mean[:, 0]) and np.all(hi > field.mean[:, 0])


def test_reconstructed_smiles_are_arbitrage_free_with_exact_handles(universe, field):
    rebuilt = reconstruct_smiles(universe, field)
    for name, params in rebuilt.items():
        i = universe.node_index(name)
        smile = universe.smiles[i]
        slice_ = build_slice(params)  # raises if A_R >= 1
        assert slice_.martingale_check() == pytest.approx(1.0, abs=1e-9)
        h = atm_handles(slice_, smile.t)
        achieved = np.array([h.sigma0, h.skew, h.curvature])
        np.testing.assert_allclose(achieved, field.mean[i], rtol=0, atol=1e-8)


def test_build_universe_empty_is_valid():
    """An empty universe (nothing calibrated yet) builds without raising — the
    gated Graph tab hits this before any Calibrate (regression: 0x0 stationary
    solve / np.vstack([]) used to 500 GET /graph/nodes)."""
    u = build_universe([], {})
    assert u.graph.n_nodes == 0
    assert u.handles.shape == (0, 3)
    assert len(u.smiles) == 0


def test_node_handles_match_benchmark_values():
    """Sanity: the baseline handle extraction matches the known SPX-like fit."""
    smile = SmileNode(name=("A", 0.5), t=0.5, params=bm.SVI_LQD_PARAMS)
    handles = node_handles(smile)
    assert handles[0] == pytest.approx(0.206, abs=3e-3)
    assert handles[1] == pytest.approx(-0.355, abs=2e-3)
