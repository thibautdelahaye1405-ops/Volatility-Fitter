"""Per-node transported-prior baselines with provenance (plan Phase 2).

Every production graph node needs a baseline ``x^0`` = its transported-prior ATM
handles (plan Amendment B + the Q1 hierarchy). The model propagates *innovations*
relative to this baseline, so the baseline must be a genuine spot-consistent prior
— never a flat default, which would manufacture innovations wherever the market
has a real smile.

The prior is resolved by a strict hierarchy, each branch carrying explicit
provenance + precision metadata so a result is always explainable:

1. ``active_transported``        — the active saved/fetched prior node for this
                                   expiry, transported to the current forward;
2. ``nearest_expiry_transported``— failing that, the nearest-expiry prior node on
                                   the same ticker, transported, precision reduced;
3. ``today_bootstrap``           — failing that, today's mid fit, low precision and
                                   ``valid_for_validation=False`` (it would make a
                                   dark-node quote test "today vs today", circular);
4. ``flat_atm``                  — a flat ATM-only baseline, diagnostic/stress only.

The ATM carrier is ``(sigma0, skew, curvature)`` in the prior's own variance clock
``tau`` (vols are quoted in tau), matching ``prior_transport``. Transported handles
are read exactly off the LQD backbone at ``h=0`` and numerically off the
transported total-variance curve otherwise.

Phase 2 sets the per-source precision from provenance tiers (constants); Phase 4
replaces those with data-derived precision (fit quality / quote density / freshness),
keeping these as floors/caps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import numpy as np

from volfit.api import prior_transport
from volfit.api.graph_service import GRAPH_PRECISION
from volfit.api.schemas_prior import PriorNode, PriorSurfaceSnapshot
from volfit.api.service import fit_or_get
from volfit.api.state import AppState
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.quadrature import build_slice

if TYPE_CHECKING:
    from volfit.api.graph_universe import SelectedUniverse

#: Per-source baseline-precision scale on GRAPH_PRECISION (the active-prior tier).
#: A weaker provenance enters the solver with materially less confidence so its
#: baseline is more readily overridden by propagated signal. Phase 4 derives the
#: real precision; these remain the provenance multiplier.
PRIOR_SOURCE_PRECISION_SCALE = {
    "active_transported": 1.0,
    "nearest_expiry_transported": 0.25,
    "today_bootstrap": 0.05,
    "flat_atm": 0.01,
    "none": 0.01,
}

#: Flat-baseline ATM vol when the flat_atm diagnostic is requested and nothing
#: better exists (handles = (flat_vol, 0, 0)).
DEFAULT_FLAT_ATM_VOL = 0.20


@dataclass(frozen=True)
class NodePrior:
    """One node's resolved baseline handles plus full provenance (plan Phase 2)."""

    handles: np.ndarray  # (3,) (sigma0, skew, curvature) in the prior's tau clock
    source: str  # see the hierarchy in the module docstring
    as_of: str | None  # the prior snapshot's market moment (dataTs), if any
    prior_forward: float | None  # forward the prior was calibrated at
    current_forward: float | None  # forward transported to (None ⇒ no transport)
    transport_distance: float  # h = log(F_now / F_prior); 0 when no transport
    precision: np.ndarray  # (3,) baseline precision per handle
    valid_for_validation: bool  # False for bootstrap/flat (circular as a prior test)


def _lqd_handles(node: PriorNode | object, tau: float) -> np.ndarray:
    """Exact ATM handles of an LQD backbone at variance time ``tau``."""
    if isinstance(node, PriorNode):
        slice_ = prior_transport.prior_lqd_slice(node)
    else:  # a calibrated FitRecord's LQD params
        slice_ = build_slice(node.result.params)  # type: ignore[attr-defined]
    h = atm_handles(slice_, tau)
    return np.array([h.sigma0, h.skew, h.curvature])


def _handles_from_w(w_fn, tau: float, eps: float = 5e-3) -> np.ndarray:
    """Numeric ATM handles of a transported total-variance curve near k=0.

    Central differences of the implied vol ``sqrt(w(k)/tau)`` give the skew
    (dσ/dk) and curvature (d²σ/dk²); the level is read at k=0. Used only when the
    forward actually moved (h≠0), where the curve is no longer an LQD slice.
    """
    k = np.array([-2.0 * eps, -eps, 0.0, eps, 2.0 * eps])
    w = np.maximum(np.asarray(w_fn(k), dtype=float), 1e-12)
    vol = np.sqrt(w / tau)
    sigma0 = float(vol[2])
    skew = float((vol[3] - vol[1]) / (2.0 * eps))
    curvature = float((vol[3] - 2.0 * vol[2] + vol[1]) / (eps * eps))
    return np.array([sigma0, skew, curvature])


def _transport_log_ratio(prior_forward: float, current_forward: float | None) -> float:
    """h = log(F_now / F_prior); 0 when the current forward is unknown/invalid."""
    if current_forward is None or current_forward <= 0.0 or prior_forward <= 0.0:
        return 0.0
    return float(np.log(current_forward / prior_forward))


def current_forward(state: AppState, ticker: str, iso: str) -> float | None:
    """The parity-implied forward for a node from the fetched chain, or None.

    None (no chain fetched, the gated workflow before Fetch) means a prior is
    left at its own forward — h=0, no transport — rather than guessed.
    """
    try:
        forwards = state.forwards(ticker)
    except Exception:
        return None
    try:
        target = date.fromisoformat(iso)
    except ValueError:
        return None
    fwd = forwards.get(target)
    return float(fwd.forward) if fwd is not None else None


def _nearest_prior_node(
    snapshot: PriorSurfaceSnapshot, iso: str
) -> PriorNode | None:
    """The prior node whose expiry is nearest (in days) to ``iso``, excluding an
    exact match (handled by the active_transported branch)."""
    try:
        target = date.fromisoformat(iso)
    except ValueError:
        return None
    best: PriorNode | None = None
    best_gap = None
    for node in snapshot.nodes:
        if node.expiry == iso:
            continue
        try:
            gap = abs((date.fromisoformat(node.expiry) - target).days)
        except ValueError:
            continue
        if best_gap is None or gap < best_gap:
            best, best_gap = node, gap
    return best


def _prior_handles(node: PriorNode, f_now: float | None, regime) -> tuple[np.ndarray, float]:
    """(handles, transport_distance) of a prior node moved to the current forward."""
    h = _transport_log_ratio(node.forward, f_now)
    if h == 0.0:
        return _lqd_handles(node, node.tau), 0.0
    moved = prior_transport.transported_prior_slice(node, float(f_now), regime)
    return _handles_from_w(moved.implied_w, node.tau), h


def _node_prior_from(
    node: PriorNode, f_now: float | None, regime, source: str, as_of: str | None
) -> NodePrior:
    handles, h = _prior_handles(node, f_now, regime)
    scale = PRIOR_SOURCE_PRECISION_SCALE[source]
    return NodePrior(
        handles=handles,
        source=source,
        as_of=as_of,
        prior_forward=float(node.forward),
        current_forward=f_now,
        transport_distance=h,
        precision=GRAPH_PRECISION * scale,
        valid_for_validation=True,
    )


def resolve_node_prior(
    state: AppState,
    ticker: str,
    iso: str,
    *,
    allow_bootstrap: bool = True,
    flat_atm: bool = False,
    flat_atm_vol: float = DEFAULT_FLAT_ATM_VOL,
) -> NodePrior:
    """Resolve one node's baseline by the locked prior hierarchy (plan Phase 2).

    ``flat_atm=True`` is an explicit diagnostic/stress override: it short-circuits
    the hierarchy and returns a flat ATM-only baseline at every node, ignoring any
    saved prior (so the whole universe can be stressed off a flat surface).
    """
    f_now = current_forward(state, ticker, iso)
    if flat_atm:
        return _flat_baseline(f_now, "flat_atm", flat_atm_vol)

    regime = state.dynamics_regime()
    snapshot = state.active_prior(ticker)
    as_of = snapshot.dataTs if snapshot is not None else None

    # 1. active_transported — the prior node for this exact expiry.
    if snapshot is not None:
        exact = prior_transport.prior_node(snapshot, iso)
        if exact is not None:
            return _node_prior_from(exact, f_now, regime, "active_transported", as_of)

        # 2. nearest_expiry_transported — nearest-expiry prior, reduced precision.
        near = _nearest_prior_node(snapshot, iso)
        if near is not None:
            return _node_prior_from(
                near, f_now, regime, "nearest_expiry_transported", as_of
            )

    # 3. today_bootstrap — today's mid fit; weak, NOT valid for validation.
    if allow_bootstrap:
        record = fit_or_get(state, ticker, iso, "mid")
        if record is not None:
            handles = _lqd_handles(record, record.prepared.tau)
            return NodePrior(
                handles=handles,
                source="today_bootstrap",
                as_of=None,
                prior_forward=float(record.prepared.forward),
                current_forward=f_now,
                transport_distance=0.0,
                precision=GRAPH_PRECISION * PRIOR_SOURCE_PRECISION_SCALE["today_bootstrap"],
                valid_for_validation=False,
            )

    # 4. none — a flat ATM-only baseline of last resort (no prior, no fit).
    return _flat_baseline(f_now, "none", flat_atm_vol)


def _flat_baseline(f_now: float | None, source: str, flat_atm_vol: float) -> NodePrior:
    """A flat ATM-only baseline (handles = (flat_vol, 0, 0)) — the flat_atm
    diagnostic override and the no-prior/no-fit last resort."""
    return NodePrior(
        handles=np.array([flat_atm_vol, 0.0, 0.0]),
        source=source,
        as_of=None,
        prior_forward=None,
        current_forward=f_now,
        transport_distance=0.0,
        precision=GRAPH_PRECISION * PRIOR_SOURCE_PRECISION_SCALE[source],
        valid_for_validation=False,
    )


def resolve_priors(
    state: AppState, universe: "SelectedUniverse", **opts
) -> tuple[NodePrior, ...]:
    """Resolve baselines for every node of the universe, in graph order."""
    return tuple(
        resolve_node_prior(state, node.ticker, node.expiry, **opts)
        for node in universe.nodes
    )
