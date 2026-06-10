"""Graph construction: nodes, directed weights, stationary mass, conductances.

Note sections 4.1-4.2: the raw directed weights W (w_ij >= 0, "j is relevant
when predicting i") are row-normalized to a transition kernel K; its
stationary distribution pi and the reversibilized conductances

    c_ij = (pi_i K_ij + pi_j K_ji) / 2        (eq. reversible-conductance)

turn the directed graph into objects safe for Gaussian priors and OT
geometry. Dense linear algebra throughout: smile universes are thousands of
nodes at most, where dense solves are both faster and simpler than sparse
machinery (revisit in the Phase-9 performance pass if needed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable

import numpy as np

NodeId = Hashable


@dataclass(frozen=True)
class SmileGraph:
    """A prepared graph: node registry plus the derived stochastic objects.

    ``edges`` lists undirected support pairs (i, j), i < j, with conductances
    ``conductance`` aligned; ``index`` maps node ids to row positions.
    """

    nodes: tuple[NodeId, ...]
    kernel: np.ndarray  # row-stochastic K
    stationary: np.ndarray  # pi, pi^T K = pi^T
    edges: tuple[tuple[int, int], ...]
    conductance: np.ndarray  # c_e > 0 per undirected edge

    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    @property
    def index(self) -> dict[NodeId, int]:
        return {node: i for i, node in enumerate(self.nodes)}


def _row_normalize(weights: np.ndarray, self_loop: float) -> np.ndarray:
    """K_ij = w_ij / sum_k w_ik, giving sinks a self-loop so K stays stochastic."""
    w = weights.astype(float).copy()
    np.fill_diagonal(w, np.diag(w))  # keep any explicit self-weights
    out_degree = w.sum(axis=1)
    sinks = out_degree <= 0.0
    if np.any(sinks):
        w[sinks, sinks] = self_loop
        out_degree = w.sum(axis=1)
    return w / out_degree[:, None]


def _stationary_distribution(kernel: np.ndarray) -> np.ndarray:
    """Solve pi^T K = pi^T, sum pi = 1 by a dense linear system.

    The singular system (K^T - I) pi = 0 gets its last equation replaced by
    the normalization; this is exact for irreducible chains and avoids the
    periodicity pitfalls of power iteration.
    """
    n = kernel.shape[0]
    system = kernel.T - np.eye(n)
    system[-1, :] = 1.0
    rhs = np.zeros(n)
    rhs[-1] = 1.0
    pi = np.linalg.solve(system, rhs)
    if np.any(pi <= -1e-12):
        raise ValueError("stationary distribution has negative mass; graph not irreducible?")
    pi = np.clip(pi, 0.0, None)
    return pi / pi.sum()


def build_graph(
    nodes: list[NodeId],
    weights: dict[tuple[NodeId, NodeId], float] | np.ndarray,
    sink_self_loop: float = 1.0,
) -> SmileGraph:
    """Prepare a SmileGraph from directed weights.

    ``weights`` is either a dense matrix aligned with ``nodes`` or a sparse
    dict {(from_node, to_node): w}. Nodes with no outgoing weight receive a
    self-loop so the kernel remains stochastic (note section 4.1).
    """
    n = len(nodes)
    index = {node: i for i, node in enumerate(nodes)}
    if isinstance(weights, np.ndarray):
        w = np.asarray(weights, dtype=float)
        if w.shape != (n, n):
            raise ValueError(f"weight matrix shape {w.shape} != ({n}, {n})")
    else:
        w = np.zeros((n, n))
        for (src, dst), value in weights.items():
            if value < 0:
                raise ValueError(f"negative weight on edge {src} -> {dst}")
            w[index[src], index[dst]] = value

    kernel = _row_normalize(w, sink_self_loop)
    pi = _stationary_distribution(kernel)

    # Reversibilized conductances on the undirected support, skipping loops.
    traffic = pi[:, None] * kernel
    sym = 0.5 * (traffic + traffic.T)
    edges: list[tuple[int, int]] = []
    cond: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            if sym[i, j] > 0.0:
                edges.append((i, j))
                cond.append(float(sym[i, j]))

    return SmileGraph(
        nodes=tuple(nodes),
        kernel=kernel,
        stationary=pi,
        edges=tuple(edges),
        conductance=np.asarray(cond),
    )
