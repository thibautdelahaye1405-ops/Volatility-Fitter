"""Symmetric graph operators: Laplacians and the OT mobility metric.

Note sections 4.2-5.1. All three operators are symmetric positive
semidefinite by construction, hence valid Gaussian precision contributions:

  - reversible Laplacian   L_rev = B C B^T            (eq. Lrev)
  - directed residual      L_dir = (I-K)^T Pi (I-K)   (eq. Ldir)
  - mobility Laplacian     A_rho = B M B^T            (eq. Arho)

with B the signed incidence matrix, C = diag(c_e) the reversible
conductances and M = diag(m_e), m_e = c_e * theta(rho_i, rho_j) the OT
mobilities for a positive reference density rho.
"""

from __future__ import annotations

import numpy as np

from volfit.graph.build import SmileGraph


def incidence_matrix(n_nodes: int, edges: tuple[tuple[int, int], ...]) -> np.ndarray:
    """Signed node-edge incidence B (one +1 / -1 per column, orientation i->j)."""
    b = np.zeros((n_nodes, len(edges)))
    for e, (i, j) in enumerate(edges):
        b[i, e] = 1.0
        b[j, e] = -1.0
    return b


def reversible_laplacian(graph: SmileGraph) -> np.ndarray:
    """L_rev = B C B^T; v^T L_rev v = sum_e c_e (v_i - v_j)^2 >= 0."""
    b = incidence_matrix(graph.n_nodes, graph.edges)
    return (b * graph.conductance) @ b.T


def directed_residual(graph: SmileGraph) -> np.ndarray:
    """L_dir = (I-K)^T Pi (I-K): increments should match their directed
    neighbor average (eq. Ldir-psd); remembers edge direction safely."""
    n = graph.n_nodes
    residual = np.eye(n) - graph.kernel
    return residual.T @ (graph.stationary[:, None] * residual)


def _theta_mean(a: np.ndarray, b: np.ndarray, kind: str) -> np.ndarray:
    """Positive mean theta(a, b) weighting edge mobility (eq. log-mean)."""
    if kind == "arithmetic":
        return 0.5 * (a + b)
    if kind == "logarithmic":
        # Logarithmic mean, continuous at a == b (Maas-Mielke metric).
        diff = a - b
        log_ratio = np.log(a) - np.log(b)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(np.abs(log_ratio) > 1e-12, diff / log_ratio, a)
        return mean
    raise ValueError(f"unknown mobility mean '{kind}'")


def mobility_laplacian(
    graph: SmileGraph,
    rho: np.ndarray | None = None,
    mean: str = "logarithmic",
) -> np.ndarray:
    """A_rho = B M B^T with m_e = c_e * theta(rho_i, rho_j)  (eqs. edge-mobility, Arho).

    ``rho`` is the positive mobility reference density encoding where
    transport is cheap; default uniform. It need not be the signal itself —
    for signed smile coordinates an exogenous density is the safe choice
    (note warning in section 5).
    """
    n = graph.n_nodes
    if rho is None:
        rho = np.full(n, 1.0 / n)
    rho = np.asarray(rho, dtype=float)
    if np.any(rho <= 0):
        raise ValueError("mobility density must be strictly positive")

    i_idx = np.array([i for i, _ in graph.edges], dtype=int)
    j_idx = np.array([j for _, j in graph.edges], dtype=int)
    mobility = graph.conductance * _theta_mean(rho[i_idx], rho[j_idx], mean)

    b = incidence_matrix(n, graph.edges)
    return (b * mobility) @ b.T
