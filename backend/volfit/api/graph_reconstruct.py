"""Reconstructed node smiles + quote comparison (plan Phase 5, Amendment E).

The bulk ``/graph/extrapolate`` returns ATM summaries only; this module rebuilds
ONE node's full smile on demand (the live-overlay drill-in):

  posterior handles -> LQD retarget (v1 carrier) -> curve on the display k-grid,
  plus a posterior credible band, the transported-prior smile, the lit node's own
  calibration curve, the market quote bands, and quote-comparison metrics
  (weighted RMS, inside-spread hit rate, ATM-handle residuals, and — for quoted
  DARK nodes only — the standardized residual under the posterior uncertainty,
  eq. standardized-residual-final).

Reconstruction follows the sandbox round-trip (``smile_universe.reconstruct_smiles``):
retarget the ATM-orthogonal chart at a base slice to the propagated handles, leaving
the shape modes (wings, event convexity) untouched, so every reconstructed slice is a
genuine arbitrage-free density by construction.
"""

from __future__ import annotations

import numpy as np

from volfit.api import prior_transport
from volfit.api.graph_extrapolation import _node_t, _quote_stats, solve
from volfit.api.graph_nodes import current_forward
from volfit.api.schemas import (
    GraphAttributionEntry,
    GraphExtrapolateRequest,
    GraphNodeMetrics,
    GraphNodeSmile,
    GraphQuotePoint,
    SmilePoint,
)
from volfit.api.graph_band import build_band, curve_points, retarget_slice
from volfit.api.service import (
    K_DISPLAY_HI,
    K_DISPLAY_LO,
    N_MODEL_POINTS,
    fit_or_get,
    weighted_rms_error,
)
from volfit.api.state import AppState, UnknownNodeError
from volfit.calib.rms import node_error_terms, rms
from volfit.graph import precision as gprec
from volfit.api.displayed import displayed_slice
from volfit.api.fit_models import build_display_fit
from volfit.graph.hyper import standardized_residuals
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.ortho import build_atm_coordinates
from volfit.models.lqd.quadrature import build_slice

def _display_grid() -> np.ndarray:
    return np.linspace(K_DISPLAY_LO, K_DISPLAY_HI, N_MODEL_POINTS)


# The band construction (functional pushforward + the legacy level escape
# hatch) lives in volfit.api.graph_band; these aliases keep the historical
# local names used below.
_curve = curve_points
_retarget_slice = retarget_slice


def _native_slice(model: str, settings, lqd_slice, tau: float, grid: np.ndarray):
    """Fit the chosen parametric model (SVI / Multi-Core SIV) to the LQD-reconstructed
    target smile so the graph overlay matches the family the rest of the app draws
    (plan Phase 9 / Amendment G). LQD ⇒ None (the LQD slice is used directly).

    The graph propagates the model-agnostic ATM handles; the LQD reconstruction is
    the exact target smile, and the native fit lands on it (its ATM handles match the
    propagated handles within fit tolerance)."""
    if model not in ("svi", "sigmoid"):
        return None
    w = np.maximum(np.asarray(lqd_slice.implied_w(grid), dtype=float), 1e-10)
    finite = np.isfinite(w)
    if finite.sum() < 5:
        return None
    fit = build_display_fit(model, grid[finite], w[finite], tau, None, settings)
    return fit.slice if fit is not None else None


def _base_slice(state: AppState, ticker: str, iso: str, fit_mode: str):
    """(base LQD params, tau) carrying the node's shape for retargeting.

    Today's fit when available (its local shape), else the transported-prior
    backbone (active or nearest-expiry), else None — a flat/no-prior node has no
    LQD shape to draw and returns curves empty (handles still reported)."""
    record = fit_or_get(state, ticker, iso, fit_mode)
    if record is not None:
        return record.result.params, float(record.prepared.tau)
    snapshot = state.active_prior(ticker)
    if snapshot is not None:
        node = prior_transport.prior_node(snapshot, iso)
        if node is None and snapshot.nodes:
            from volfit.api.graph_nodes import _nearest_prior_node

            node = _nearest_prior_node(snapshot, iso)
        if node is not None:
            from volfit.models.lqd.basis import LQDParams

            return LQDParams.from_vector(np.asarray(node.lqd, dtype=float)), float(node.tau)
    return None, 0.0


def _prior_curve(
    state: AppState, ticker: str, iso: str, meta, chart, tau: float, grid: np.ndarray
) -> list[SmilePoint]:
    """The transported-prior smile (active/nearest), else the retargeted baseline."""
    snapshot = state.active_prior(ticker)
    node = prior_transport.prior_node(snapshot, iso) if snapshot is not None else None
    if node is not None:
        f_now = current_forward(state, ticker, iso) or node.forward
        return prior_transport.transported_prior_points(
            node, float(f_now), state.dynamics_regime(), grid
        )
    if chart is not None:
        sl = _retarget_slice(chart, meta.handles, tau)
        if sl is not None:
            return _curve(sl, tau, grid)
    return []


def _quote_metrics(
    state: AppState,
    ticker: str,
    iso: str,
    fit_mode: str,
    post_slice,
    post_handles: np.ndarray,
    sd: float,
    lit: bool,
) -> tuple[GraphNodeMetrics | None, list[GraphQuotePoint]]:
    """Compare the reconstructed posterior smile (``post_slice``, the displayed
    model) to the node's market quotes.

    The standardized residual for a quoted DARK node uses the observation
    precision it WOULD carry if it were lit (derived from its own chain), so the
    posterior uncertainty is checked against a real held-out measurement."""
    record = fit_or_get(state, ticker, iso, fit_mode)
    if record is None or post_slice is None:
        return None, []
    prepared = record.prepared
    tau = float(prepared.tau)
    k = np.asarray(prepared.k, dtype=float)
    base_params = record.result.params

    # Read the reconstructed (displayed-model) posterior smile on the quotes.
    model_iv = np.sqrt(np.maximum(post_slice.implied_w(k), 1e-12) / tau)

    num, den = node_error_terms(model_iv, np.asarray(prepared.iv_mid, dtype=float))
    inside = np.logical_and(
        model_iv >= np.asarray(prepared.iv_bid, dtype=float),
        model_iv <= np.asarray(prepared.iv_ask, dtype=float),
    )
    hit_rate = float(np.mean(inside)) if k.size else 0.0

    market = atm_handles(build_slice(base_params), tau)
    market_h = np.array([market.sigma0, market.skew, market.curvature])

    std_resid = None
    if not lit:  # standardized residual: quoted DARK nodes only
        rms_vol = weighted_rms_error(state, ticker, iso, record, fit_mode)
        n_atm, rel_spread = _quote_stats(prepared)
        obs_prec = gprec.observation_precision(rms_vol, n_atm, rel_spread).precision
        zeta = standardized_residuals(
            np.array([market_h[0]]),
            np.array([post_handles[0]]),
            np.array([sd * sd]),
            np.array([obs_prec[0]]),
        )
        std_resid = float(zeta[0])

    metrics = GraphNodeMetrics(
        nQuotes=int(k.size),
        rmsVol=rms(num, den),
        insideSpreadHitRate=hit_rate,
        atmResidualBp=float((post_handles[0] - market_h[0]) * 1e4),
        skewResidual=float(post_handles[1] - market_h[1]),
        curvResidual=float(post_handles[2] - market_h[2]),
        standardizedResidual=std_resid,
    )
    quotes = [
        GraphQuotePoint(k=float(kk), bid=float(b), mid=float(m), ask=float(a))
        for kk, b, m, a in zip(
            k, prepared.iv_bid, prepared.iv_mid, prepared.iv_ask
        )
    ]
    return metrics, quotes


#: Attribution list cap — the truncated tail folds into ``attributionOthersBp``
#: so the readout stays exact while the payload stays screen-sized.
_MAX_ATTRIBUTION = 20


def _direct_edge_betas(
    request: GraphExtrapolateRequest, target: tuple[str, str]
) -> dict[tuple[str, str], float]:
    """ATM beta of every EXPLICIT request edge touching the target, keyed by the
    other endpoint. Context only (empty when the topology came from the
    persisted edges / auto-lattice): the gain already folds all paths."""
    out: dict[tuple[str, str], float] = {}
    for edge in request.edges:
        a = (edge.fromTicker, edge.fromExpiry)
        b = (edge.toTicker, edge.toExpiry)
        if a == target:
            out[b] = float(edge.betaAtmVol)
        elif b == target:
            out[a] = float(edge.betaAtmVol)
    return out


def _attribution(
    sol, request: GraphExtrapolateRequest, i: int, target: tuple[str, str]
) -> tuple[list[GraphAttributionEntry], float]:
    """The target node's exact per-lit-node ATM attribution (largest first).

    Reads the ATM coordinate's own posterior update (``field.posteriors[0]``,
    the update that produced the displayed mean), so the entries + the folded
    remainder sum to (post - prior) ATM to solver precision."""
    post0 = sol.field.posteriors[0]
    if post0.observed.size == 0:
        return [], 0.0
    gain, innovation, contrib = post0.attribution(i)
    betas = _direct_edge_betas(request, target)
    order = np.argsort(-np.abs(contrib))
    entries: list[GraphAttributionEntry] = []
    others = 0.0
    for rank, j in enumerate(order):
        if rank < _MAX_ATTRIBUTION:
            name = sol.universe.nodes[int(post0.observed[j])].name
            entries.append(
                GraphAttributionEntry(
                    ticker=name[0],
                    expiry=name[1],
                    innovationBp=float(innovation[j] * 1e4),
                    gain=float(gain[j]),
                    contributionBp=float(contrib[j] * 1e4),
                    edgeBeta=betas.get(name),
                )
            )
        else:
            others += float(contrib[j] * 1e4)
    return entries, others


def node_smile(
    state: AppState, ticker: str, iso: str, request: GraphExtrapolateRequest
) -> GraphNodeSmile:
    """Reconstruct one selected node's full extrapolated smile (plan Phase 5)."""
    iso = state.resolve_expiry(ticker, iso).isoformat()
    sol = solve(state, request)
    if sol is None:
        raise UnknownNodeError(f"empty selected universe; ({ticker}, {iso}) not solvable")
    try:
        i = sol.universe.node_index((ticker, iso))
    except KeyError:
        raise UnknownNodeError(f"({ticker}, {iso}) is not in the selected universe") from None

    node = sol.universe.nodes[i]
    meta = sol.priors_meta[i]
    post_h = sol.field.mean[i]
    sd3 = sol.field.sd[i]
    sd = float(sd3[0])
    grid = _display_grid()

    model = state.fit_settings().model
    base_params, tau = _base_slice(state, ticker, iso, sol.fit_mode)
    chart = build_atm_coordinates(base_params, tau) if base_params is not None else None

    # Reconstruct the LQD target smile (exact handles), then — if the chosen model
    # is SVI / Multi-Core SIV — refit that family to the target so the overlay
    # matches what the rest of the app draws (plan Phase 9). The band is the
    # functional pushforward of the full 3-handle posterior (R3 item 12), or the
    # legacy ATM-level band when ``functionalBand`` is off.
    pb = build_band(
        lambda lqd: _native_slice(model, state.fit_settings(), lqd, tau, grid),
        chart,
        post_h,
        sd3,
        tau,
        grid,
        functional=request.functionalBand,
    )
    post_slice, post_curve = pb.post_slice, pb.post
    band_lo, band_hi = pb.band_lo, pb.band_hi

    prior_curve = _prior_curve(state, ticker, iso, meta, chart, tau, grid)

    lit_curve: list[SmilePoint] = []
    if node.lit and sol.calibrated[i]:
        record = fit_or_get(state, ticker, iso, sol.fit_mode)
        if record is not None:  # the lit node's own calibration in the displayed model
            lit_curve = _curve(displayed_slice(record), float(record.prepared.tau), grid)

    metrics, quotes = _quote_metrics(
        state, ticker, iso, sol.fit_mode, post_slice, post_h, sd, node.lit
    )
    attribution, attribution_others = _attribution(sol, request, i, (ticker, iso))

    return GraphNodeSmile(
        ticker=ticker,
        expiry=iso,
        t=_node_t(state, iso),
        model=model,
        lit=node.lit,
        calibrated=sol.calibrated[i],
        priorSource=meta.source,
        validForValidation=meta.valid_for_validation,
        priorAtmVol=float(meta.handles[0]),
        priorSkew=float(meta.handles[1]),
        priorCurv=float(meta.handles[2]),
        postAtmVol=float(post_h[0]),
        postSkew=float(post_h[1]),
        postCurv=float(post_h[2]),
        sd=sd,
        sdSkew=float(sd3[1]),
        sdCurv=float(sd3[2]),
        bandKind=pb.kind,
        varSwapVol=pb.functional.var_swap_vol if pb.functional else None,
        varSwapVolSd=pb.functional.var_swap_vol_sd if pb.functional else None,
        tailMassLeft=pb.functional.tail_mass_left if pb.functional else None,
        tailMassLeftSd=pb.functional.tail_mass_left_sd if pb.functional else None,
        tailMassRight=pb.functional.tail_mass_right if pb.functional else None,
        tailMassRightSd=pb.functional.tail_mass_right_sd if pb.functional else None,
        post=post_curve,
        postBandLo=band_lo,
        postBandHi=band_hi,
        prior=prior_curve,
        litCalibration=lit_curve,
        quotes=quotes,
        metrics=metrics,
        attribution=attribution,
        attributionOthersBp=attribution_others,
    )
