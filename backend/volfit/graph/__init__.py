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
from volfit.graph.message_posterior import (
    MessagePosterior,
    message_posterior_update,
)
from volfit.graph.temporal_state import (
    LeasePolicy,
    ObservationState,
    PersistenceGuardError,
    ResidualDynamics,
    ResidualState,
    TemporalOrderError,
    assert_persistable,
    empty_residual,
    migrate_atm_floor_history,
    observation_state,
    residual_dynamics,
    residual_measurement,
    residual_measurement_variance,
    reuse_or_invalidate,
)

__all__ = [
    "LeasePolicy",
    "ObservationState",
    "PersistenceGuardError",
    "ResidualDynamics",
    "ResidualState",
    "TemporalOrderError",
    "assert_persistable",
    "empty_residual",
    "migrate_atm_floor_history",
    "observation_state",
    "residual_dynamics",
    "residual_measurement",
    "residual_measurement_variance",
    "reuse_or_invalidate",
    "GraphPosterior",
    "IncrementPrior",
    "MessageEdge",
    "MessageOperator",
    "MessagePosterior",
    "message_posterior_update",
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
