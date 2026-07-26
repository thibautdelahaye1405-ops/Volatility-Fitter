"""Shared graph solver regime: prior hyperparameters, precisions, lattice weights.

Home of the constants both graph paths were built on. They were born in the
manual-shift sandbox (``graph_service``, retired in the P6 cleanup) and are the
regime the production extrapolator (``graph_extrapolation``), the message
operator (``graph_message``) and the prior resolution (``graph_nodes``) still
share — the tests locking the note's golden math pin these exact values.
"""

from __future__ import annotations

import itertools

import numpy as np

#: Graph weights: strong calendar chain within a ticker, weaker cross-ticker
#: edges at equal expiry (regime validated in tests/test_smile_universe.py).
SAME_TICKER_WEIGHT = 10.0
CROSS_TICKER_WEIGHT = 2.0

#: Per-handle increment hyperparameters (scale s, eta) with kappa = 1/s^2:
#: ~3 vol pts level, looser skew/curvature — the demo.py regime.
GRAPH_PRIOR_HYPER = ((0.03, 2.0e4), (0.05, 7.0e3), (0.5, 70.0))

#: Baseline/observation precisions per handle coordinate.
GRAPH_PRECISION = np.array([1.0e6, 1.0e6, 1.0e4])

#: Auto-tune sweep: geometric grid of etaScale candidates (reach multipliers).
AUTOTUNE_ETA_GRID = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0)


def lattice_weights(
    tickers, ladders: dict[str, list[str]], calendar_w: float, cross_w: float
) -> dict[tuple, float]:
    """Edge-weight dict for the universe lattice: symmetric calendar chains
    within a ticker (weight ``calendar_w``) plus equal-expiry cross-ticker
    edges (weight ``cross_w``). Pure and cheap — no slice fits — so it can be
    rebuilt per solve when the user edits the weights."""
    weights: dict[tuple, float] = {}
    for ticker, isos in ladders.items():
        for near, far in zip(isos[:-1], isos[1:]):
            weights[((ticker, near), (ticker, far))] = calendar_w
            weights[((ticker, far), (ticker, near))] = calendar_w
    for a, b in itertools.combinations(tickers, 2):
        for iso in sorted(set(ladders.get(a, [])) & set(ladders.get(b, []))):
            weights[((a, iso), (b, iso))] = cross_w
            weights[((b, iso), (a, iso))] = cross_w
    return weights
