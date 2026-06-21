"""Per-edge beta on the directed increment residual (plan Phase 6, Amendment D).

Conductance answers "how much is this edge trusted?"; beta answers "how large is
node i's move when node j moves?". They are different ideas and must stay separate
fields (plan Q3): mixing beta into the conductance would lose sign, asymmetry and
handle-specific behaviour. So beta lives ONLY in the directed compatibility relation,
never in the OT mobility term ``A_rho``.

The directed prediction rule generalizes from

    z_i ≈ Σ_j K_ij z_j        (note eq. Ldir)        →        z_i ≈ Σ_j K_ij β_ij z_j,

so the directed residual precision becomes

    L_dir^β = Mᵀ Π M,   M = I − (K ∘ B),

with ``B`` the per-edge beta matrix for the handle being propagated (one ``B`` per
handle, since betas differ by handle). ``M = I − (K∘B)`` makes ``L_dir^β = MᵀΠM`` PSD
by construction (same proof as eq. Ldir-psd), so it is always a valid Gaussian
precision contribution. ``B = 1`` everywhere reproduces ``directed_residual`` exactly
(the byte-identical guard). Betas are directional: ``β_ij`` need not equal ``β_ji``.
"""

from __future__ import annotations

import numpy as np

from volfit.graph.build import NodeId, SmileGraph


def beta_matrix(
    graph: SmileGraph,
    edge_betas: dict[tuple[NodeId, NodeId], float] | None = None,
    default: float = 1.0,
) -> np.ndarray:
    """Dense ``B`` aligned with the kernel: ``B[i, j]`` scales the directed kernel
    entry ``K[i, j]`` (same (src=i, dst=j) convention as ``build_graph``'s weights).

    Off-diagonal entries default to ``default`` (1.0), the diagonal is always 1.0
    (self-prediction is never rescaled), and ``edge_betas`` overrides named directed
    pairs. ``edge_betas=None`` ⇒ all-ones ⇒ ``directed_residual`` byte-identical."""
    n = graph.n_nodes
    b = np.full((n, n), float(default))
    np.fill_diagonal(b, 1.0)
    if edge_betas:
        index = graph.index
        for (src, dst), value in edge_betas.items():
            if src in index and dst in index:
                b[index[src], index[dst]] = float(value)
    return b


def directed_residual_beta(graph: SmileGraph, beta: np.ndarray) -> np.ndarray:
    """``L_dir^β = (I − K∘B)ᵀ Π (I − K∘B)`` — the beta-weighted directed residual.

    PSD by construction; reduces to ``operators.directed_residual`` when ``beta`` is
    all ones. ``Π = diag(stationary)`` is the reversibilizing mass (note eq. Ldir)."""
    n = graph.n_nodes
    b = np.asarray(beta, dtype=float)
    if b.shape != (n, n):
        raise ValueError(f"beta shape {b.shape} != ({n}, {n})")
    m = np.eye(n) - graph.kernel * b
    return m.T @ (graph.stationary[:, None] * m)
