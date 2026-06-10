"""The Gaussian increment prior Q_Delta (note section 6).

    Q_Delta = D_kappa + eta * L_dir + lam * (A_rho + nu I)^{-1}   (eq. Qdelta-main)

Three complementary beliefs about the increment z = x^1 - x^0:
  - D_kappa: increments are locally small;
  - eta L_dir: increments respect the directed prediction rule;
  - lam (A_rho + nu I)^{-1}: increments should be producible by a low-energy
    graph flux plus nu-priced sources/sinks (the unbalanced OT tangent norm,
    eq. uot-boxed).

Dense formation is deliberate at this scale (universes of smiles are
O(10^3) nodes); the matrix-free path of note section 8 is the Phase-9
performance follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.graph.build import SmileGraph
from volfit.graph.operators import directed_residual, mobility_laplacian


@dataclass(frozen=True)
class IncrementPrior:
    """Increment precision Q_Delta plus its covariance (cached inverse)."""

    graph: SmileGraph
    precision: np.ndarray  # Q_Delta
    covariance: np.ndarray  # K_Delta = Q_Delta^{-1}
    kappa: np.ndarray
    eta: float
    ot_weight: float
    source_allowance: float


def build_increment_prior(
    graph: SmileGraph,
    kappa: float | np.ndarray = 1.0,
    eta: float = 0.0,
    ot_weight: float = 0.0,
    source_allowance: float = 0.1,
    rho: np.ndarray | None = None,
    mobility_mean: str = "logarithmic",
) -> IncrementPrior:
    """Assemble Q_Delta and its inverse for the given hyperparameters.

    ``kappa`` is the local temporal precision (scalar or per-node);
    ``eta`` weights directed smoothness; ``ot_weight`` (lambda) weights the
    OT tangent penalty with source/sink allowance ``nu`` = ``source_allowance``.
    """
    n = graph.n_nodes
    kappa_vec = np.broadcast_to(np.asarray(kappa, dtype=float), (n,)).copy()
    if np.any(kappa_vec <= 0):
        raise ValueError("kappa must be strictly positive for a proper prior")

    precision = np.diag(kappa_vec)
    if eta > 0.0:
        precision = precision + eta * directed_residual(graph)
    if ot_weight > 0.0:
        if source_allowance <= 0.0:
            raise ValueError("source allowance nu must be > 0 (eq. uot-poisson)")
        a_rho = mobility_laplacian(graph, rho=rho, mean=mobility_mean)
        precision = precision + ot_weight * np.linalg.inv(a_rho + source_allowance * np.eye(n))

    # Symmetrize against round-off before inverting; Q_Delta is PD because
    # D_kappa > 0 and the other two terms are PSD.
    precision = 0.5 * (precision + precision.T)
    covariance = np.linalg.inv(precision)

    return IncrementPrior(
        graph=graph,
        precision=precision,
        covariance=0.5 * (covariance + covariance.T),
        kappa=kappa_vec,
        eta=float(eta),
        ot_weight=float(ot_weight),
        source_allowance=float(source_allowance),
    )
