"""Round trip: graph posterior on ATM handles -> arbitrage-free LQD smiles.

This is the integration layer that makes the two technical notes compose.
Each graph node is one smile (underlying, expiry) whose propagated scalar
coordinates are the trader handles

    (atm_vol sigma_0, skew s_0, curvature kappa_0)

— ATM vol rather than total variance so the level coordinate is comparable
across expiries. Each coordinate is an independent Gaussian field propagated
with volfit.graph.posterior; the posterior means are then mapped back to
*exact* arbitrage-free LQD smiles per node via the ATM-orthogonal retargeting
of volfit.models.lqd.ortho (shape modes untouched), and the marginal
precisions give per-node confidence bands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from volfit.graph.build import NodeId, SmileGraph, build_graph
from volfit.graph.posterior import GraphPosterior, posterior_update
from volfit.graph.prior import IncrementPrior
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.ortho import build_atm_coordinates
from volfit.models.lqd.quadrature import build_slice

HANDLE_NAMES = ("atm_vol", "skew", "curvature")
N_HANDLES = 3


@dataclass(frozen=True)
class SmileNode:
    """One smile in the universe: id, expiry and its baseline LQD fit."""

    name: NodeId
    t: float
    params: LQDParams


@dataclass(frozen=True)
class SmileUniverse:
    """Graph over smiles plus baseline handle values (N x 3)."""

    graph: SmileGraph
    smiles: tuple[SmileNode, ...]
    handles: np.ndarray

    def node_index(self, name: NodeId) -> int:
        return self.graph.index[name]


@dataclass(frozen=True)
class HandleField:
    """Posterior field over all nodes for the three handle coordinates."""

    mean: np.ndarray  # (N, 3)
    sd: np.ndarray  # (N, 3) marginal posterior standard deviations
    posteriors: tuple[GraphPosterior, ...]  # per coordinate

    def atm_vol_band(self, z_score: float = 1.96) -> tuple[np.ndarray, np.ndarray]:
        """Pointwise credible band on the ATM-vol coordinate."""
        half = z_score * self.sd[:, 0]
        return self.mean[:, 0] - half, self.mean[:, 0] + half


def node_handles(smile: SmileNode) -> np.ndarray:
    """(sigma_0, skew, curvature) of one baseline smile."""
    h = atm_handles(build_slice(smile.params), smile.t)
    return np.array([h.sigma0, h.skew, h.curvature])


def build_universe(
    smiles: list[SmileNode],
    weights: dict[tuple[NodeId, NodeId], float],
) -> SmileUniverse:
    """Assemble the graph (nodes ordered as given) and baseline handles."""
    graph = build_graph([s.name for s in smiles], weights)
    handles = np.vstack([node_handles(s) for s in smiles])
    return SmileUniverse(graph=graph, smiles=tuple(smiles), handles=handles)


def propagate_handles(
    universe: SmileUniverse,
    priors: IncrementPrior | Sequence[IncrementPrior],
    observed: dict[NodeId, np.ndarray],
    baseline_precision: np.ndarray,
    observation_precision: np.ndarray,
) -> HandleField:
    """Propagate observed handle updates through the graph, per coordinate.

    ``priors`` is one IncrementPrior shared by the three coordinates or a
    sequence of three (handles have very different scales, so per-coordinate
    kappa is usually right). ``baseline_precision`` and
    ``observation_precision`` are length-3 (per coordinate) or (N, 3) /
    (n_obs, 3) arrays.
    """
    if isinstance(priors, IncrementPrior):
        prior_list = [priors] * N_HANDLES
    else:
        prior_list = list(priors)
        if len(prior_list) != N_HANDLES:
            raise ValueError(f"need {N_HANDLES} priors, got {len(prior_list)}")

    n = universe.graph.n_nodes
    obs_idx = np.array([universe.node_index(name) for name in observed], dtype=int)
    obs_values = np.vstack([np.asarray(observed[name], dtype=float) for name in observed])

    bp = np.broadcast_to(np.asarray(baseline_precision, dtype=float), (n, N_HANDLES))
    op = np.broadcast_to(
        np.asarray(observation_precision, dtype=float), (obs_idx.size, N_HANDLES)
    )

    posteriors = []
    mean = np.empty((n, N_HANDLES))
    sd = np.empty((n, N_HANDLES))
    for c in range(N_HANDLES):
        post = posterior_update(
            prior_list[c],
            baseline=universe.handles[:, c],
            baseline_precision=bp[:, c],
            observed=obs_idx,
            observations=obs_values[:, c],
            observation_precision=op[:, c],
        )
        posteriors.append(post)
        mean[:, c] = post.mean
        sd[:, c] = np.sqrt(post.marginal_variance)

    return HandleField(mean=mean, sd=sd, posteriors=tuple(posteriors))


def reconstruct_smiles(
    universe: SmileUniverse,
    field: HandleField,
    nodes: Sequence[NodeId] | None = None,
) -> dict[NodeId, LQDParams]:
    """Map posterior handle means back to exact arbitrage-free LQD smiles.

    For each node the ATM-orthogonal chart at its baseline parameters is
    retargeted to (w0, skew, curvature) = (sigma0^2 t, s0, kappa0) with shape
    coordinates fixed — every reconstructed slice is a genuine density by
    construction, whatever the graph did to the handles.
    """
    names = list(nodes) if nodes is not None else [s.name for s in universe.smiles]
    out: dict[NodeId, LQDParams] = {}
    for name in names:
        i = universe.node_index(name)
        smile = universe.smiles[i]
        sigma0, skew, curvature = field.mean[i]
        target = np.array([sigma0 * sigma0 * smile.t, skew, curvature])
        chart = build_atm_coordinates(smile.params, smile.t)
        out[name] = chart.retarget(target)
    return out
