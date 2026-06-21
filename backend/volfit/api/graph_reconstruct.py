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
    GraphExtrapolateRequest,
    GraphNodeMetrics,
    GraphNodeSmile,
    GraphQuotePoint,
    SmilePoint,
)
from volfit.api.service import (
    K_DISPLAY_HI,
    K_DISPLAY_LO,
    N_MODEL_POINTS,
    fill_nonfinite,
    fit_or_get,
    weighted_rms_error,
)
from volfit.api.state import AppState, UnknownNodeError
from volfit.calib.rms import node_error_terms, rms
from volfit.graph import precision as gprec
from volfit.graph.hyper import standardized_residuals
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.ortho import build_atm_coordinates
from volfit.models.lqd.quadrature import build_slice

Z_95 = 1.96


def _display_grid() -> np.ndarray:
    return np.linspace(K_DISPLAY_LO, K_DISPLAY_HI, N_MODEL_POINTS)


def _curve(slice_, tau: float, grid: np.ndarray) -> list[SmilePoint]:
    w = np.maximum(slice_.implied_w(grid), 0.0)
    vols = fill_nonfinite(np.sqrt(np.maximum(w, 0.0) / tau))  # edge-extend the wings
    return [SmilePoint(k=float(k), vol=float(v)) for k, v in zip(grid, vols)]


def _retarget_curve(chart, handles, tau: float, grid: np.ndarray) -> list[SmilePoint]:
    """LQD smile at target ATM ``handles`` (w0 = sigma0^2 tau). Empty on a Newton
    failure at extreme handles (the band edges of a very wide posterior)."""
    target = np.array([handles[0] * handles[0] * tau, handles[1], handles[2]])
    try:
        params = chart.retarget(target)
    except RuntimeError:
        return []
    return _curve(build_slice(params), tau, grid)


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
        return _retarget_curve(chart, meta.handles, tau, grid)
    return []


def _quote_metrics(
    state: AppState,
    ticker: str,
    iso: str,
    fit_mode: str,
    post_handles: np.ndarray,
    sd: float,
    lit: bool,
) -> tuple[GraphNodeMetrics | None, list[GraphQuotePoint]]:
    """Compare the reconstructed posterior smile to the node's market quotes.

    The standardized residual for a quoted DARK node uses the observation
    precision it WOULD carry if it were lit (derived from its own chain), so the
    posterior uncertainty is checked against a real held-out measurement."""
    record = fit_or_get(state, ticker, iso, fit_mode)
    if record is None:
        return None, []
    prepared = record.prepared
    tau = float(prepared.tau)
    k = np.asarray(prepared.k, dtype=float)
    base_params = record.result.params

    # Reconstruct the posterior smile at THIS node's shape, read it on the quotes.
    chart = build_atm_coordinates(base_params, tau)
    target = np.array(
        [post_handles[0] * post_handles[0] * tau, post_handles[1], post_handles[2]]
    )
    try:
        post_params = chart.retarget(target)
    except RuntimeError:
        post_params = base_params
    model_iv = np.sqrt(np.maximum(build_slice(post_params).implied_w(k), 1e-12) / tau)

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
    sd = float(sol.field.sd[i, 0])
    grid = _display_grid()

    base_params, tau = _base_slice(state, ticker, iso, sol.fit_mode)
    chart = build_atm_coordinates(base_params, tau) if base_params is not None else None

    if chart is not None:
        half = Z_95 * sd
        post_curve = _retarget_curve(chart, post_h, tau, grid)
        band_lo = _retarget_curve(chart, [post_h[0] - half, post_h[1], post_h[2]], tau, grid)
        band_hi = _retarget_curve(chart, [post_h[0] + half, post_h[1], post_h[2]], tau, grid)
    else:
        post_curve = band_lo = band_hi = []

    prior_curve = _prior_curve(state, ticker, iso, meta, chart, tau, grid)

    lit_curve: list[SmilePoint] = []
    if node.lit and sol.calibrated[i]:
        record = fit_or_get(state, ticker, iso, sol.fit_mode)
        if record is not None:
            lit_curve = _curve(
                build_slice(record.result.params), float(record.prepared.tau), grid
            )

    metrics, quotes = _quote_metrics(
        state, ticker, iso, sol.fit_mode, post_h, sd, node.lit
    )

    return GraphNodeSmile(
        ticker=ticker,
        expiry=iso,
        t=_node_t(state, iso),
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
        post=post_curve,
        postBandLo=band_lo,
        postBandHi=band_hi,
        prior=prior_curve,
        litCalibration=lit_curve,
        quotes=quotes,
        metrics=metrics,
    )
