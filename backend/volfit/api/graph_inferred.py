"""Graph-INFERRED smiles on the node views (user ask 2026-09-07).

After a Graph Run (POST /graph/extrapolate) every node of the solved universe
keeps its posterior — the three ATM handles, their marginal sd, the prior
tier — as the LAST RUN (``record_run``). The Smile / Table views then draw
the node's INFERRED smile: the posterior handles retargeted onto the node's
own shape (the same ``retarget_slice`` the drill-in overlay uses:
today's fit when there is one, else the transported prior backbone), wrapped
as a ``FitRecord`` so it TRANSPORTS with the spot exactly like a calibrated
fit — the market layer rolls it to the prevailing spot, the live tick stream
re-rolls it on every spot move (``inferred_rolled``). A dark node shows it as
its only curve, distinct (violet dash-dot, an "INFERRED · GRAPH" badge naming
the run); a calibrated node shows it beside its fit, for the comparison.

Nothing here is a fit: the record is never committed, never a prior, never
enters a calibration or a snapshot (the "graph output is never prior input"
invariant of priors.capture_snapshot holds — this record lives in its own
cache). A node the run did not cover, or whose shape cannot be built (no
quotes, no prior), has no inferred smile. The cache is keyed by the run
stamp and the node's fit key, so a new Run, a recalibration or a prior
change rebuilds it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from volfit.api.schemas import GraphInferredSmile, SmilePoint
from volfit.api.state import AppState, FitRecord
from volfit.models.lqd.calibrate import CalibrationResult


@dataclass(frozen=True)
class InferredNode:
    """One node's posterior from the last Run (handles in the graph's
    canonical order: ATM vol, skew, curvature)."""

    post_h: np.ndarray  # (3,)
    sd3: np.ndarray  # (3,) marginal posterior sd
    prior_source: str  # the prior tier the baseline came from
    lit: bool
    calibrated: bool


@dataclass(frozen=True)
class GraphRun:
    """The last Run: when, under which fit target, and every node's posterior."""

    ts: str  # ISO UTC wall clock of the Run
    fit_mode: str
    nodes: dict[tuple[str, str], InferredNode]


def record_run(state: AppState, sol) -> GraphRun:
    """Keep the solved field as the last Run (called by graph_extrapolation.
    extrapolate — the user's Run, never by the per-node drill-in GET)."""
    nodes: dict[tuple[str, str], InferredNode] = {}
    for i, node in enumerate(sol.universe.nodes):
        nodes[(node.ticker, node.expiry)] = InferredNode(
            post_h=np.asarray(sol.field.mean[i], dtype=float).copy(),
            sd3=np.asarray(sol.field.sd[i], dtype=float).copy(),
            prior_source=str(sol.priors_meta[i].source),
            lit=bool(node.lit),
            calibrated=bool(sol.calibrated[i]),
        )
    run = GraphRun(
        ts=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        fit_mode=str(sol.fit_mode),
        nodes=nodes,
    )
    state._graph_run = run
    state._graph_inferred_cache = {}
    return run


def graph_run(state: AppState) -> GraphRun | None:
    """The last Run, or None before the first one."""
    return getattr(state, "_graph_run", None)


def clear_run(state: AppState) -> None:
    """Forget the last Run (tests / a universe rebuild)."""
    state._graph_run = None
    state._graph_inferred_cache = {}


def _native_display(model: str, settings, lqd_slice, tau: float, grid: np.ndarray):
    """The chosen non-LQD family fitted to the LQD-reconstructed target (the
    graph_reconstruct._native_slice recipe, keeping the DisplayFit itself so
    the record's displayed slice carries its handles); None for LQD."""
    from volfit.api.fit_models import build_display_fit
    from volfit.api.service import _WING_TV_FLOOR

    if model not in ("svi", "sigmoid"):
        return None
    w = np.maximum(np.asarray(lqd_slice.implied_w(grid), dtype=float), 1e-10)
    c = np.asarray(lqd_slice.call_price(grid), dtype=float)
    p = np.asarray(lqd_slice.put_price(grid), dtype=float)
    tv = np.where(grid > 0.0, c, p)
    finite = np.isfinite(w) & (tv >= _WING_TV_FLOOR)
    if finite.sum() < 5:
        return None
    return build_display_fit(model, grid[finite], w[finite], tau, None, settings)


def inferred_record(state: AppState, ticker: str, iso: str, fit_mode: str) -> FitRecord | None:
    """The node's inferred smile as a FitRecord (never committed), or None —
    no Run yet, the node not in it, or no shape to retarget (no prepared
    quotes for a forward / clock, no fit and no prior backbone).

    The posterior handles are retargeted at the NODE's own variance clock
    (``prepared.tau``): the handles are vols at this maturity, so
    w0 = sigma0^2 tau_node whatever expiry the base shape came from."""
    from volfit.api import graph_reconstruct, service
    from volfit.api.graph_band import retarget_slice
    from volfit.models.lqd.ortho import build_atm_coordinates

    run = graph_run(state)
    if run is None:
        return None
    node = run.nodes.get((ticker, iso))
    if node is None:
        return None
    key = (run.ts, ticker, iso, fit_mode, service.fit_key(state, ticker, iso, fit_mode))
    cache: dict = getattr(state, "_graph_inferred_cache", None) or {}
    state._graph_inferred_cache = cache
    if key in cache:
        return cache[key]
    record: FitRecord | None = None
    prepared = service.prepare_slice(state, ticker, iso)
    base_params, _base_tau = graph_reconstruct._base_slice(state, ticker, iso, fit_mode)
    if prepared is not None and base_params is not None:
        tau = float(prepared.tau)
        chart = build_atm_coordinates(base_params, tau)
        lqd_post = retarget_slice(chart, node.post_h, tau)
        if lqd_post is not None:
            settings = state.fit_settings()
            display = _native_display(
                settings.model, settings, lqd_post, tau, graph_reconstruct._display_grid()
            )
            record = FitRecord(
                prepared=prepared,
                result=CalibrationResult(
                    params=lqd_post.params, slice=lqd_post, cost=0.0,
                    n_evaluations=0, success=True, max_iv_error=0.0,
                ),
                display=display,
                provenance="graph",
            )
    cache[key] = record
    return record


def inferred_rolled(
    state: AppState, ticker: str, iso: str, fit_mode: str, shift: float
) -> list[SmilePoint] | None:
    """The inferred smile ROLLED by ``shift`` under the dynamics regime (the
    live tick stream's frame), or None when the node has none."""
    from volfit.api.smile_layers import rolled_model

    record = inferred_record(state, ticker, iso, fit_mode)
    if record is None:
        return None
    return rolled_model(state, ticker, iso, record, shift)


def inferred_payload(
    state: AppState, ticker: str, iso: str, fit_mode: str, record: FitRecord | None = None
) -> GraphInferredSmile | None:
    """The node's inferred smile for the smile payload: the curve at the
    ACTIVE spot shift (transported exactly like fit_or_get transports a fit)
    plus what it is — the Run stamp, the prior tier, the posterior ATM ± sd,
    the family it is drawn in, the node's lit / calibrated flags."""
    from volfit.api.service import model_curve, transport_record

    run = graph_run(state)
    if run is None:
        return None
    node = run.nodes.get((ticker, iso))
    if node is None:
        return None
    if record is None:
        record = inferred_record(state, ticker, iso, fit_mode)
    if record is None:
        return None
    drawn = transport_record(state, ticker, iso, record) if state.spot_shift(ticker) != 0.0 else record
    return GraphInferredSmile(
        curve=model_curve(drawn),
        runTs=run.ts,
        fitMode=run.fit_mode,
        priorSource=node.prior_source,
        postAtmVol=float(node.post_h[0]),
        sd=float(node.sd3[0]),
        model=record.display.model if record.display is not None else "lqd",
        lit=node.lit,
        calibrated=node.calibrated,
    )
