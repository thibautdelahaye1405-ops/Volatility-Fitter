"""Active observation selection (graph/select): closed form == brute force.

The whole point of the rank-one machinery is that scoring a candidate must
cost one small solve, not a re-solve — so the lock here is EXACTNESS: the
closed-form per-node variance drops must equal the drop measured by actually
re-running ``posterior_update`` with the candidate added as an observation
(the variance of a Gaussian update does not depend on the observed VALUE,
which is what makes the brute-force comparison well-posed).
"""

import numpy as np
import pytest

from volfit.graph import build_increment_prior
from volfit.graph.build import build_graph
from volfit.graph.posterior import posterior_update
from volfit.graph.select import observation_gains

NAMES = [("A", t) for t in (0.25, 0.5, 1.0, 2.0)] + [("B", t) for t in (0.5, 1.0)]


@pytest.fixture(scope="module")
def setup():
    weights = {}
    for tk, ts in (("A", (0.25, 0.5, 1.0, 2.0)), ("B", (0.5, 1.0))):
        for a, b in zip(ts[:-1], ts[1:]):
            weights[((tk, a), (tk, b))] = 10.0
            weights[((tk, b), (tk, a))] = 10.0
    weights[(("A", 0.5), ("B", 0.5))] = 2.0
    weights[(("B", 0.5), ("A", 0.5))] = 2.0
    graph = build_graph(NAMES, weights)
    prior = build_increment_prior(graph, kappa=1.0 / 0.03**2, eta=2.0e4)
    n = graph.n_nodes
    baseline = np.zeros(n)
    p0 = np.full(n, 1.0e6)
    obs_idx = np.array([graph.index[("A", 0.5)]])
    post = posterior_update(
        prior,
        baseline=baseline,
        baseline_precision=p0,
        observed=obs_idx,
        observations=np.array([0.02]),
        observation_precision=np.array([1.0e6]),
    )
    return graph, prior, p0, post


def _brute_force_drop(prior, p0, observed, r_obs, candidate, r_c):
    """Variance drop per node from actually adding the candidate observation."""
    n = p0.size
    base = posterior_update(
        prior,
        baseline=np.zeros(n),
        baseline_precision=p0,
        observed=np.asarray(observed, dtype=int),
        observations=np.zeros(len(observed)),
        observation_precision=np.asarray(r_obs, dtype=float),
    )
    both = posterior_update(
        prior,
        baseline=np.zeros(n),
        baseline_precision=p0,
        observed=np.append(np.asarray(observed, dtype=int), candidate),
        observations=np.zeros(len(observed) + 1),
        observation_precision=np.append(np.asarray(r_obs, dtype=float), r_c),
    )
    return base.marginal_variance - both.marginal_variance


def test_closed_form_equals_refit(setup):
    graph, prior, p0, post = setup
    obs = [graph.index[("A", 0.5)]]
    candidates = np.array(
        [graph.index[name] for name in NAMES if graph.index[name] not in obs]
    )
    r_c = 5.0e5
    gains = observation_gains(
        prior.covariance, p0, post, candidates, np.full(candidates.size, r_c)
    )
    for g in gains:
        brute = _brute_force_drop(prior, p0, obs, [1.0e6], g.index, r_c)
        np.testing.assert_allclose(g.per_node_var_drop, brute, rtol=1e-8, atol=1e-16)
        assert g.total_gain == pytest.approx(float(np.sum(brute)), rel=1e-8)
        assert g.self_var_after == pytest.approx(
            post.marginal_variance[g.index] - brute[g.index], rel=1e-8
        )


def test_no_observation_case_equals_first_observation(setup):
    graph, prior, p0, _post = setup
    c = graph.index[("A", 1.0)]
    r_c = 1.0e6
    [gain] = observation_gains(
        prior.covariance, p0, None, np.array([c]), np.array([r_c])
    )
    n = p0.size
    first = posterior_update(
        prior,
        baseline=np.zeros(n),
        baseline_precision=p0,
        observed=np.array([c]),
        observations=np.array([0.0]),
        observation_precision=np.array([r_c]),
    )
    k_minus = 1.0 / p0 + np.diag(prior.covariance)
    np.testing.assert_allclose(
        gain.per_node_var_drop, k_minus - first.marginal_variance, rtol=1e-8
    )


def test_central_node_wins_on_a_symmetric_chain():
    names = [("X", t) for t in (0.25, 0.5, 1.0)]
    weights = {}
    for a, b in zip(names[:-1], names[1:]):
        weights[(a, b)] = 10.0
        weights[(b, a)] = 10.0
    graph = build_graph(names, weights)
    prior = build_increment_prior(graph, kappa=1.0 / 0.03**2, eta=2.0e4)
    p0 = np.full(3, 1.0e4)
    cand = np.arange(3)
    gains = observation_gains(
        prior.covariance, p0, None, cand, np.full(3, 1.0e6)
    )
    total = [g.total_gain for g in gains]
    assert np.argmax(total) == 1  # the middle node informs both neighbours


def test_exposure_weights_select_the_beneficiary(setup):
    graph, prior, p0, post = setup
    c = graph.index[("A", 1.0)]
    target = graph.index[("A", 2.0)]
    w = np.zeros(p0.size)
    w[target] = 1.0
    [gain] = observation_gains(
        prior.covariance, p0, post, np.array([c]), np.array([1.0e6]), weights=w
    )
    assert gain.total_gain == pytest.approx(gain.per_node_var_drop[target])


def test_input_validation(setup):
    graph, prior, p0, post = setup
    observed = graph.index[("A", 0.5)]
    with pytest.raises(ValueError):
        observation_gains(
            prior.covariance, p0, post, np.array([observed]), np.array([1e6])
        )
    with pytest.raises(ValueError):
        observation_gains(
            prior.covariance, p0, post, np.array([0]), np.array([-1.0])
        )
