"""Graph-based Bayesian extrapolation of smile signals.

Implements Docs/ot_bayesian_graph_extrapolation_expanded.tex: nodes are
smiles (underlying, expiry) carrying scalar coordinates; sparse time-1
observations are propagated to the full universe through a Gaussian
increment prior built from directed-graph smoothness and an optimal-transport
tangent metric, with honest marginal posterior precisions.
"""

from volfit.graph.beta import beta_matrix, directed_residual_beta
from volfit.graph.build import SmileGraph, build_graph
from volfit.graph.operators import (
    directed_residual,
    incidence_matrix,
    mobility_laplacian,
    reversible_laplacian,
)
from volfit.graph.prior import IncrementPrior, build_increment_prior
from volfit.graph.posterior import GraphPosterior, posterior_update
from volfit.graph.hyper import marginal_log_likelihood

__all__ = [
    "GraphPosterior",
    "IncrementPrior",
    "SmileGraph",
    "beta_matrix",
    "build_graph",
    "build_increment_prior",
    "directed_residual",
    "directed_residual_beta",
    "incidence_matrix",
    "marginal_log_likelihood",
    "mobility_laplacian",
    "posterior_update",
    "reversible_laplacian",
]
