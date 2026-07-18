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
from volfit.graph.message import (
    MessageEdge,
    MessageOperator,
    anchor_precisions,
    build_message_operator,
    calendar_beta,
    calendar_message_precision,
    cycle_beta_products,
    expand_calendar_ladder,
    message_edge,
)

__all__ = [
    "GraphPosterior",
    "IncrementPrior",
    "MessageEdge",
    "MessageOperator",
    "SmileGraph",
    "anchor_precisions",
    "beta_matrix",
    "build_graph",
    "build_increment_prior",
    "build_message_operator",
    "calendar_beta",
    "calendar_message_precision",
    "cycle_beta_products",
    "directed_residual",
    "directed_residual_beta",
    "expand_calendar_ladder",
    "incidence_matrix",
    "marginal_log_likelihood",
    "message_edge",
    "mobility_laplacian",
    "posterior_update",
    "reversible_laplacian",
]
