"""Coarse scale guard: a 1k-node universe must solve comfortably fast.

Roadmap Phase-4 exit criterion is "1k-node synthetic universe updates < 1 s";
this asserts a loose multiple to stay robust on slow CI machines while still
catching accidental O(N^4) regressions.
"""

import time

import numpy as np
import pytest

from volfit.graph import build_graph, build_increment_prior, posterior_update


@pytest.fixture(scope="module")
def big_universe():
    """Ring of 1000 smiles plus random cross-asset chords (deterministic)."""
    rng = np.random.RandomState(7)
    n = 1000
    nodes = list(range(n))
    weights = {}
    for i in range(n):
        weights[(i, (i + 1) % n)] = 1.0 + rng.rand()
        weights[((i + 1) % n, i)] = 1.0 + rng.rand()
    for _ in range(2000):
        i, j = rng.randint(0, n, size=2)
        if i != j:
            weights[(i, j)] = 0.2 * rng.rand()
    return nodes, weights


def test_thousand_node_update_is_fast_and_sane(big_universe):
    nodes, weights = big_universe
    n = len(nodes)
    rng = np.random.RandomState(11)

    start = time.perf_counter()
    graph = build_graph(nodes, weights)
    prior = build_increment_prior(
        graph, kappa=2.0, eta=5.0, ot_weight=0.1, source_allowance=0.15
    )
    baseline = rng.rand(n) + 1.0
    observed = rng.choice(n, size=25, replace=False)
    observations = baseline[observed] + 0.1 * rng.randn(25)
    posterior = posterior_update(
        prior,
        baseline,
        baseline_precision=np.full(n, 25.0),
        observed=observed,
        observations=observations,
        observation_precision=np.full(25, 100.0),
    )
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, f"1k-node pipeline took {elapsed:.2f}s"
    assert np.all(posterior.marginal_variance > 0)
    # Observed nodes end near their observations, unobserved near baseline.
    assert np.max(np.abs(posterior.mean[observed] - observations)) < 0.1
    far = np.setdiff1d(np.arange(n), observed)
    assert np.median(np.abs(posterior.mean[far] - baseline[far])) < 0.05
