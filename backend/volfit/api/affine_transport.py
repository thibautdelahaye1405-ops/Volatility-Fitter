"""Fast spot-move transport of the calibrated affine local-vol surface.

The Local-Vol workspace's surface / smile / density / term / table all derive
from the cached ``AffineFitResponse`` (volfit.api.affine_fit / affine_views). A
spot move must refresh them without re-running the (heavy) affine calibration, so
this module transports the cached response analytically per
Docs/spot_move_vol_surface_note_updated.tex:

  * each reconstructed smile is moved with ``volfit.dynamics.TransportedSlice``
    (its own per-expiry ``h_T`` from the forward), so density / term / table —
    which rebuild from the smile points — follow consistently;
  * the displayed quote band re-indexes to the new moneyness (fixed strikes:
    ``k -> k - h_T``);
  * the nodal local-vol grid relabels by the note's grid rule ``x_i^1 =
    x_i^0 e^{-(R/2) h_t}`` (the local vols are unchanged, only the strike
    coordinates move); a single representative ``h`` is used for the shared
    ``xNodes`` axis (uniform under continuous carry, exact for the dominant move).

Applied at the ``affine_payload`` boundary, so the calibration cache still stores
the anchor surface and the transport is recomputed cheaply on read.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from volfit.api.affine_views import _ReconSlice
from volfit.api.schemas import QuoteBand, SmilePoint, VarSwapInfo
from volfit.api.schemas_affine import AffineFitResponse, AffineSmile
from volfit.api.state import AppState
from volfit.dynamics.transport import TransportedSlice, transport_grid_strikes
from volfit.models.diagnostics import numeric_handles, numeric_var_swap_w


def _transport_smile(
    state: AppState, ticker: str, regime: str | float, smile: AffineSmile
) -> tuple[AffineSmile, float]:
    """Move one reconstructed affine smile for the active spot shift.

    Returns the transported smile and its forward log-ratio ``h`` (so the caller
    can relabel the shared nodal grid with a representative value).
    """
    from volfit.api import service

    expiry = date.fromisoformat(smile.expiry)
    fwd = state.resolved_forward(ticker, expiry)
    f1, h = service.spot_forward_shift(
        state, ticker, expiry, float(fwd.forward), float(fwd.discount), float(smile.t)
    )
    if h == 0.0:
        return smile, 0.0

    tau = smile.tau if smile.tau > 0.0 else smile.t
    base = _ReconSlice(
        np.array([p.k for p in smile.model], dtype=float),
        np.array([p.vol * p.vol * tau for p in smile.model], dtype=float),
    )
    handles = numeric_handles(base, tau)
    moved = TransportedSlice(
        base, h, regime, sigma0=handles.atm_vol, kappa=handles.skew, tau=tau
    )
    ks = np.array([p.k for p in smile.model], dtype=float)
    vols = moved.implied_vol(ks, tau)
    model = [SmilePoint(k=float(k), vol=float(v)) for k, v in zip(ks, vols)]
    # Quotes are fixed strikes: their new moneyness is k - h (IV band unchanged).
    quotes = [
        QuoteBand(
            k=float(q.k - h),
            bid=q.bid,
            ask=q.ask,
            mid=q.mid,
            index=q.index,
            excluded=q.excluded,
            amended=q.amended,
        )
        for q in smile.quotes
    ]
    vs = smile.varSwap
    moved_vs = VarSwapInfo(
        level=vs.level,
        excluded=vs.excluded,
        modelVol=float(np.sqrt(max(numeric_var_swap_w(moved), 0.0) / tau)),
        enabled=vs.enabled,
        canUndo=vs.canUndo,
        canRedo=vs.canRedo,
    )
    return (
        smile.model_copy(update={"model": model, "quotes": quotes, "varSwap": moved_vs}),
        h,
    )


def attach_affine_priors(
    state: AppState, ticker: str, response: AffineFitResponse
) -> AffineFitResponse:
    """Overlay the active fetched prior (dotted, spot-updated) on each LV smile.

    For every expiry with an active-prior node, the prior's LQD backbone is
    transported to the smile's current forward under the dynamics regime and
    sampled on the smile's own k grid (volfit.api.prior_transport) — the same
    machinery as the parametric overlay, so the two workspaces show a consistent
    prior. No active prior ⇒ the response is returned unchanged."""
    active = state.active_prior(ticker)
    if active is None:
        return response
    from volfit.api import prior_transport, service

    regime = state.dynamics_regime()
    smiles: list[AffineSmile] = []
    for smile in response.smiles:
        node = prior_transport.prior_node(active, smile.expiry)
        if node is None:
            smiles.append(smile)
            continue
        expiry = date.fromisoformat(smile.expiry)
        fwd = state.resolved_forward(ticker, expiry)
        f1, _h = service.spot_forward_shift(
            state, ticker, expiry, float(fwd.forward), float(fwd.discount), float(smile.t)
        )
        grid = np.array([p.k for p in smile.model], dtype=float)
        points = prior_transport.transported_prior_points(node, f1, regime, grid)
        smiles.append(smile.model_copy(update={"prior": points, "priorTransported": True}))
    return response.model_copy(update={"smiles": smiles})


def transport_affine_response(
    state: AppState, ticker: str, response: AffineFitResponse
) -> AffineFitResponse:
    """Transport a cached affine surface for the ticker's active spot shift.

    Returns ``response`` unchanged when no shift is active; otherwise every smile
    is moved and the nodal grid relabelled (note's LV-grid node rule).
    """
    if state.spot_shift(ticker) == 0.0:
        return response
    regime = state.dynamics_regime()
    smiles: list[AffineSmile] = []
    h_repr = 0.0
    for smile in response.smiles:
        moved, h = _transport_smile(state, ticker, regime, smile)
        smiles.append(moved)
        if h != 0.0:
            h_repr = h  # last (longest-dated) expiry's h drives the shared grid
    if h_repr == 0.0:
        return response.model_copy(update={"smiles": smiles})
    x_nodes = transport_grid_strikes(np.array(response.xNodes, dtype=float), h_repr, regime)
    return response.model_copy(
        update={"smiles": smiles, "xNodes": [float(x) for x in x_nodes]}
    )
