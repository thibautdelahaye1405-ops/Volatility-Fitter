"""Observation-plan API: rank the dark nodes worth quoting next (R3 item 13).

Assembles ``volfit.graph.select.observation_gains`` (closed-form rank-one
gains on the ATM coordinate of the SOLVED posterior — no refit) into the
product payload:

  - candidates = every selected node that did not contribute an observation
    today (dark, or lit without a calibration);
  - each candidate's assumed observation precision is its OWN chain quality
    when it has a fit today (the precision it WOULD carry if lit — the
    standardized-residual seam), else the median of today's lit precisions
    ("quoted like a typical lit node"), else the nominal tier;
  - exposure weights are per-ticker multipliers (default 1) so a desk can
    steer the ranking toward the books it actually holds;
  - gains are reported in band units (sd before/after, bp) plus the share of
    the universe's remaining weighted ATM variance each candidate removes.

Model-variance honesty: shares use the RAW model posterior (the idio floor is
a reporting floor on bands; its variance is exactly what observing OTHER
nodes cannot remove — quoting the node itself does, which is the point).
"""

from __future__ import annotations

import numpy as np

from volfit.api.graph_extrapolation import _quote_stats, solve
from volfit.api.schemas import (
    GraphObservationBeneficiary,
    GraphObservationCandidate,
    GraphObservationPlanRequest,
    GraphObservationPlanResponse,
)
from volfit.api.service import fit_or_get, weighted_rms_error
from volfit.api.state import AppState
from volfit.graph import precision as gprec
from volfit.graph.select import observation_gains

_ATM = 0  # the coordinate the plan ranks on (the product headline)
_MAX_BENEFICIARIES = 5


def _bp(x: float) -> float:
    return float(x) * 1e4


def _candidate_precision(state: AppState, sol, i: int, nominal: float) -> float:
    """The ATM observation precision candidate ``i`` would carry if quoted."""
    node = sol.universe.nodes[i]
    record = fit_or_get(state, node.ticker, node.expiry, sol.fit_mode)
    if record is None:
        return nominal
    rms = weighted_rms_error(state, node.ticker, node.expiry, record, sol.fit_mode)
    n_atm, rel_spread = _quote_stats(record.prepared)
    return float(gprec.observation_precision(rms, n_atm, rel_spread).precision[_ATM])


def observation_plan(
    state: AppState, request: GraphObservationPlanRequest
) -> GraphObservationPlanResponse:
    """Rank the next observations by exposure-weighted posterior-variance gain."""
    sol = solve(state, request)
    if sol is None:
        return GraphObservationPlanResponse(candidates=[], nCandidates=0)
    n = len(sol.universe.nodes)
    post = sol.field.posteriors[_ATM]
    prior = sol.increment_priors[_ATM]
    p0 = sol.baseline_precision[:, _ATM]

    observed = set(int(i) for i in post.observed) if post is not None else set()
    cand = np.array([i for i in range(n) if i not in observed], dtype=int)
    if cand.size == 0:
        return GraphObservationPlanResponse(candidates=[], nCandidates=0)

    # Assumed precision per candidate; the nominal tier is today's median lit
    # precision (else the provenance-tier default).
    lit_prec = [float(b.precision[_ATM]) for b in sol.obs_breakdowns.values()]
    nominal = float(np.median(lit_prec)) if lit_prec else float(
        gprec.observation_precision(0.005, 5, 0.1).precision[_ATM]
    )
    r = np.array([_candidate_precision(state, sol, int(i), nominal) for i in cand])

    # Exposure weights: per-ticker multipliers, default 1.
    w = np.ones(n)
    if request.exposureWeights:
        for i, node in enumerate(sol.universe.nodes):
            w[i] = float(request.exposureWeights.get(node.ticker, 1.0))

    gains = observation_gains(prior.covariance, p0, post, cand, r, weights=w)
    r_by_idx = {int(c): float(rc) for c, rc in zip(cand, r)}

    # Remaining weighted model variance (raw posterior — see module docstring).
    var_before = (
        post.marginal_variance
        if post is not None
        else 1.0 / p0 + np.diag(prior.covariance)
    )
    total_var = float(w @ var_before)
    sd_before = np.sqrt(np.maximum(var_before, 0.0))

    ranked = sorted(gains, key=lambda g: -g.total_gain)[: max(request.topN, 0)]
    out = []
    for g in ranked:
        node = sol.universe.nodes[g.index]
        drop = g.per_node_var_drop
        order = np.argsort(-(w * drop))
        bens = []
        for j in order[: _MAX_BENEFICIARIES + 1]:
            if int(j) == g.index or drop[j] <= 0.0:
                continue  # self is reported via the selfSd fields
            b = sol.universe.nodes[int(j)]
            after = max(var_before[int(j)] - drop[int(j)], 0.0)
            bens.append(
                GraphObservationBeneficiary(
                    ticker=b.ticker,
                    expiry=b.expiry,
                    sdBeforeBp=_bp(sd_before[int(j)]),
                    sdAfterBp=_bp(float(np.sqrt(after))),
                )
            )
            if len(bens) == _MAX_BENEFICIARIES:
                break
        out.append(
            GraphObservationCandidate(
                ticker=node.ticker,
                expiry=node.expiry,
                lit=node.lit,
                selfSdBeforeBp=_bp(float(np.sqrt(g.self_var_before))),
                selfSdAfterBp=_bp(float(np.sqrt(g.self_var_after))),
                totalVarReductionPct=(
                    100.0 * g.total_gain / total_var if total_var > 0.0 else 0.0
                ),
                assumedPrecision=r_by_idx[g.index],
                beneficiaries=bens,
            )
        )
    return GraphObservationPlanResponse(candidates=out, nCandidates=int(cand.size))
