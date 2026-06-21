"""Project the graph-extrapolated smile onto an affine Local-Vol surface
(plan Phase 9 / Amendment G).

Local-Vol has no cheap 3-parameter transport — LV calibration is a full surface
optimisation, not a parameter mutation — so we do NOT transport native LV params.
Instead the graph-extrapolated PARAMETRIC smile is the projection TARGET: reusing
each expiry's live strike grid + forward/discount, we swap the target total variance
``w`` for the graph reconstruction and run the standard affine LV calibration against
it. The result is a genuine arb-free local-vol surface (the Dupire PDE keeps density
>= 0) that reproduces the extrapolated smiles rather than the raw quotes.

This is the bridge the plan calls for: graph -> parametric target -> LV projection.
Only expiries with a live strike grid are projected (the projection samples the
extrapolated smile on those strikes); a node with no chain keeps its live row.
"""

from __future__ import annotations

import numpy as np

from volfit.api import affine_fit, graph_reconstruct
from volfit.api.graph_extrapolation import solve
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.api.schemas_affine import AffineFitRequest, AffineFitResponse
from volfit.api.state import AppState
from volfit.models.lqd.ortho import build_atm_coordinates


def _graph_rows(state: AppState, ticker: str, sol, rows, fit_mode: str):
    """Live affine rows with each expiry's target total variance replaced by the
    graph-reconstructed smile (sampled on the row's strikes). Band -> None so the
    fit targets the extrapolated mid smile."""
    out = []
    for iso, tau, k, w, prepared, band in rows:
        try:
            i = sol.universe.node_index((ticker, iso))
        except KeyError:
            out.append((iso, tau, k, w, prepared, band))  # node not in the graph
            continue
        post_h = sol.field.mean[i]
        base_params, _ = graph_reconstruct._base_slice(state, ticker, iso, fit_mode)
        if base_params is None:
            out.append((iso, tau, k, w, prepared, band))  # no shape to reconstruct
            continue
        chart = build_atm_coordinates(base_params, tau)
        sl = graph_reconstruct._retarget_slice(chart, post_h, tau)
        if sl is None:
            out.append((iso, tau, k, w, prepared, band))  # retarget failed
            continue
        kk = np.asarray(k, dtype=float)
        w_graph = np.maximum(np.asarray(sl.implied_w(kk), dtype=float), 1e-10)
        out.append((iso, tau, kk, w_graph, prepared, None))
    return out


def project_to_lv(
    state: AppState, ticker: str, request: AffineFitRequest
) -> AffineFitResponse:
    """Calibrate an affine LV surface to the ticker's graph-extrapolated smiles."""
    rows = affine_fit._gather(state, ticker, request.fitMode)
    if len(rows) < 2:
        return affine_fit._empty_affine_response(ticker)
    sol = solve(state, GraphExtrapolateRequest())
    if sol is None:
        return affine_fit._empty_affine_response(ticker)
    graph_rows = _graph_rows(state, ticker, sol, rows, request.fitMode)
    return affine_fit._fit(state, ticker, request, rows=graph_rows)
