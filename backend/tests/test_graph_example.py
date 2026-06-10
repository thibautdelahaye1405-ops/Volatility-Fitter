"""Golden reproduction of the OT note's six-node running example.

Docs/ot_bayesian_graph_extrapolation_expanded.tex carries one worked example
through every section (stationary mass, conductances, Q_Delta, S_y, alpha,
posterior table). Reproducing all of its tables validates the entire graph
pipeline. The note's row-normalized kernel corresponds to the integer
out-weights below (e.g. node 2: 7/12/2 over 21 -> 0.333/0.571/0.095).
"""

import numpy as np
import pytest

from volfit.graph import (
    build_graph,
    build_increment_prior,
    marginal_log_likelihood,
    mobility_laplacian,
    posterior_update,
    reversible_laplacian,
)
from volfit.graph.operators import directed_residual

NODES = [1, 2, 3, 4, 5, 6]
WEIGHTS = {
    (1, 2): 1.0,
    (2, 1): 7.0, (2, 3): 12.0, (2, 5): 2.0,
    (3, 2): 9.0, (3, 4): 8.0,
    (4, 3): 3.0, (4, 5): 5.0,
    (5, 2): 1.0, (5, 4): 9.0, (5, 6): 11.0,
    (6, 5): 1.0,
}

BASELINE = np.array([2.00, 2.10, 1.95, 1.05, 0.90, 1.10])
BASELINE_PRECISION = np.array([25.0, 25.0, 16.0, 16.0, 20.0, 20.0])
OBSERVED = np.array([1, 4])  # nodes 2 and 5, zero-based
OBSERVATIONS = np.array([2.45, 0.65])
OBSERVATION_PRECISION = np.array([100.0, 64.0])

# Hyperparameters of the running example (note section 6).
HYPER = dict(kappa=2.0, eta=20.0, ot_weight=0.10, source_allowance=0.15)


@pytest.fixture(scope="module")
def graph():
    return build_graph(NODES, WEIGHTS)


@pytest.fixture(scope="module")
def prior(graph):
    # The example uses uniform rho = 1/6 with the *arithmetic* mobility mean.
    return build_increment_prior(graph, mobility_mean="arithmetic", **HYPER)


@pytest.fixture(scope="module")
def posterior(prior):
    return posterior_update(
        prior, BASELINE, BASELINE_PRECISION, OBSERVED, OBSERVATIONS, OBSERVATION_PRECISION
    )


def test_kernel_rows_match_note(graph):
    expected_row2 = np.array([0.333, 0.0, 0.571, 0.0, 0.095, 0.0])
    np.testing.assert_allclose(graph.kernel[1], expected_row2, atol=5e-4)
    assert graph.kernel[0, 1] == 1.0
    assert graph.kernel[5, 4] == 1.0


def test_stationary_distribution_matches_note(graph):
    expected = np.array([0.049, 0.147, 0.159, 0.200, 0.292, 0.153])
    np.testing.assert_allclose(graph.stationary, expected, atol=1e-3)


def test_conductances_match_note(graph):
    expected = {
        (0, 1): 0.0491, (1, 2): 0.0842, (1, 4): 0.0140,
        (2, 3): 0.0749, (3, 4): 0.1250, (4, 5): 0.1529,
    }
    assert set(graph.edges) == set(expected)
    for edge, c_expected in expected.items():
        c_actual = graph.conductance[graph.edges.index(edge)]
        assert c_actual == pytest.approx(c_expected, abs=1e-4)


def test_operators_are_psd_and_annihilate_constants(graph):
    ones = np.ones(graph.n_nodes)
    for op in (
        reversible_laplacian(graph),
        directed_residual(graph),
        mobility_laplacian(graph, mean="arithmetic"),
    ):
        eigenvalues = np.linalg.eigvalsh(op)
        assert eigenvalues.min() > -1e-12
    # Laplacian-type operators kill constants; L_dir does too since K1 = 1.
    np.testing.assert_allclose(reversible_laplacian(graph) @ ones, 0.0, atol=1e-14)
    np.testing.assert_allclose(mobility_laplacian(graph) @ ones, 0.0, atol=1e-14)
    np.testing.assert_allclose(directed_residual(graph) @ ones, 0.0, atol=1e-14)


def test_increment_precision_matches_note(prior):
    expected = np.array(
        [
            [3.942, -1.932, 0.563, 0.000, 0.094, 0.000],
            [-1.932, 7.408, -3.320, 0.916, -0.551, 0.147],
            [0.563, -3.320, 7.278, -2.957, 1.102, 0.001],
            [0.000, 0.916, -2.957, 8.331, -4.942, 1.319],
            [0.094, -0.551, 1.102, -4.942, 13.003, -6.040],
            [0.000, 0.147, 0.001, 1.319, -6.040, 7.240],
        ]
    )
    np.testing.assert_allclose(prior.precision, expected, atol=2e-3)


def test_predictive_standard_deviations_match_note(prior):
    k_minus_diag = 1.0 / BASELINE_PRECISION + np.diag(prior.covariance)
    expected = np.array([0.577, 0.484, 0.515, 0.499, 0.462, 0.532])
    np.testing.assert_allclose(np.sqrt(k_minus_diag), expected, atol=1e-3)


def test_innovation_system_matches_note(posterior):
    np.testing.assert_allclose(
        posterior.innovation_cov,
        np.array([[0.2442, 0.0032], [0.0032, 0.2290]]),
        atol=5e-4,
    )
    np.testing.assert_allclose(
        posterior.innovation_weights, np.array([1.4478, -1.1118]), atol=5e-4
    )


def test_posterior_table_matches_note(posterior):
    expected_mean = np.array([2.124, 2.436, 2.064, 0.977, 0.667, 0.960])
    expected_sd = np.array([0.552, 0.098, 0.484, 0.468, 0.121, 0.468])
    expected_precision = np.array([3.286, 104.271, 4.274, 4.556, 68.687, 4.568])
    np.testing.assert_allclose(posterior.mean, expected_mean, atol=2e-3)
    np.testing.assert_allclose(np.sqrt(posterior.marginal_variance), expected_sd, atol=2e-3)
    np.testing.assert_allclose(posterior.marginal_precision, expected_precision, rtol=3e-3)


def test_ot_weight_pulls_toward_baseline(graph):
    """Note section 8: larger lambda shrinks unobserved moves and variances."""
    means, sds = [], []
    for lam in (0.0, 1.0):
        prior = build_increment_prior(
            graph, kappa=2.0, eta=20.0, ot_weight=lam,
            source_allowance=0.15, mobility_mean="arithmetic",
        )
        post = posterior_update(
            prior, BASELINE, BASELINE_PRECISION, OBSERVED, OBSERVATIONS, OBSERVATION_PRECISION
        )
        means.append(post.mean)
        sds.append(np.sqrt(post.marginal_variance))
    # Node 1 (unobserved): 2.154 at lambda=0 vs 2.036 at lambda=1 in the note.
    assert means[0][0] == pytest.approx(2.154, abs=2e-3)
    assert means[1][0] == pytest.approx(2.036, abs=2e-3)
    assert sds[1][0] < sds[0][0]  # variance shrinks with lambda


def test_marginal_likelihood_matches_reference_density(posterior):
    """ell must equal the exact Gaussian log-density N(d; 0, S_y)."""
    from scipy.stats import multivariate_normal

    innovation = OBSERVATIONS - BASELINE[OBSERVED]
    ll = marginal_log_likelihood(posterior.innovation_cov, innovation)
    reference = multivariate_normal(mean=np.zeros(2), cov=posterior.innovation_cov).logpdf(
        innovation
    )
    assert ll == pytest.approx(float(reference), abs=1e-12)
