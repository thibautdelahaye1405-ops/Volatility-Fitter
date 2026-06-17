"""Spot-update a fetched prior to the current forward (the dotted overlay + anchor).

A fetched prior (``PriorSurfaceSnapshot``) was calibrated at its own spot/forward.
To overlay it on — or anchor a fit to — today's smile, it must be moved to the
current forward under the chosen spot-vol dynamics, exactly like the live surface
is transported (``volfit.dynamics.transport``). The prior's LQD backbone is the
canonical priced object, so we transport that:

    h_T = log(F_current / F_prior),     w~(k) = transport(w_prior, h_T, regime),

and read the prior vol at the current log-moneyness as ``sqrt(w~(k) / tau_prior)``.
``h_T = 0`` (no forward move) is the identity, so a prior fetched at the current
spot overlays unchanged.
"""

from __future__ import annotations

import math

import numpy as np

from volfit.api.schemas import SmilePoint
from volfit.api.schemas_prior import PriorNode, PriorSurfaceSnapshot
from volfit.dynamics.transport import TransportedSlice
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.quadrature import LQDSlice, build_slice


def prior_node(snapshot: PriorSurfaceSnapshot | None, iso: str) -> PriorNode | None:
    """The snapshot's node for an expiry ISO, or None."""
    if snapshot is None:
        return None
    return next((n for n in snapshot.nodes if n.expiry == iso), None)


def prior_lqd_slice(node: PriorNode) -> LQDSlice:
    """Rebuild the prior's LQD backbone slice from its stored parameter vector."""
    return build_slice(LQDParams.from_vector(np.asarray(node.lqd, dtype=float)))


def transported_prior_slice(
    node: PriorNode, current_forward: float, regime: str | float
) -> TransportedSlice:
    """The prior's LQD slice transported to ``current_forward`` under ``regime``.

    ``TransportedSlice.implied_w(k)`` then returns the prior's total variance at the
    NEW log-moneyness (same units as the prior, i.e. the prior's ``tau``)."""
    h = math.log(current_forward / node.forward) if node.forward > 0.0 else 0.0
    return TransportedSlice(prior_lqd_slice(node), h, regime, tau=node.tau)


def transported_prior_points(
    node: PriorNode, current_forward: float, regime: str | float, k_grid: np.ndarray
) -> list[SmilePoint]:
    """Prior implied-vol curve, spot-updated to ``current_forward``, on ``k_grid``.

    Vols use the prior's own variance time (``node.tau``) — the prior is the same
    node, so its clock matches today's to within a day; this keeps the overlay a
    faithful vol-shape transport."""
    moved = transported_prior_slice(node, current_forward, regime)
    k = np.asarray(k_grid, dtype=float)
    w = np.maximum(moved.implied_w(k), 0.0)
    vol = np.sqrt(w / node.tau)
    return [SmilePoint(k=float(kk), vol=float(v)) for kk, v in zip(k, vol)]
