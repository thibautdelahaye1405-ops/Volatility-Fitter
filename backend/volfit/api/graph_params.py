"""Shared graph solver regime: prior hyperparameters, precisions, lattice weights.

Home of the constants both graph paths were built on. They were born in the
manual-shift sandbox (``graph_service``, retired in the P6 cleanup) and are the
regime the production extrapolator (``graph_extrapolation``), the message
operator (``graph_message``) and the prior resolution (``graph_nodes``) still
share — the tests locking the note's golden math pin these exact values.
"""

from __future__ import annotations

import itertools
from datetime import date

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


def nearest_cross_expiry_pairs(
    isos_a: list[str], isos_b: list[str], tol_days: float
) -> list[tuple[str, str, int]]:
    """Nearest-expiry cross pairs ``(iso_a, iso_b, gap_days)`` within tolerance.

    Cross-venue ladders are not synchronous, so a rung with no exact same-date
    partner on the other ticker is paired with the other ticker's NEAREST
    expiry (calendar-day gap) when that gap is <= ``tol_days``. Exact-date
    rungs are excluded (they get the standard equal-expiry edge); matching
    runs from both sides and duplicates collapse, so the result is symmetric
    in (a, b) up to column order. Empty for ``tol_days <= 0`` or an empty side.
    """
    if tol_days <= 0.0 or not isos_a or not isos_b:
        return []
    dates_a = {iso: date.fromisoformat(iso) for iso in isos_a}
    dates_b = {iso: date.fromisoformat(iso) for iso in isos_b}
    shared = set(isos_a) & set(isos_b)
    pairs: set[tuple[str, str, int]] = set()
    for isos_x, dates_x, dates_y, flip in (
        (isos_a, dates_a, dates_b, False),
        (isos_b, dates_b, dates_a, True),
    ):
        for iso in isos_x:
            if iso in shared:
                continue
            other, gap = min(
                ((o, abs((d - dates_x[iso]).days)) for o, d in dates_y.items()),
                key=lambda og: og[1],
            )
            if gap <= tol_days:
                pairs.add((other, iso, gap) if flip else (iso, other, gap))
    return sorted(pairs)


def lattice_weights(
    tickers,
    ladders: dict[str, list[str]],
    calendar_w: float,
    cross_w: float,
    cross_expiry_tol_days: float = 0.0,
) -> dict[tuple, float]:
    """Edge-weight dict for the universe lattice: symmetric calendar chains
    within a ticker (weight ``calendar_w``) plus equal-expiry cross-ticker
    edges (weight ``cross_w``). ``cross_expiry_tol_days`` > 0 additionally
    pairs asynchronous cross-venue rungs with the other ticker's nearest
    expiry within that many days, at weight ``cross_w * tol / (tol + gap)``
    (continuous with the exact-match weight as the gap -> 0); 0 keeps the
    historical exact-date topology byte-identical. Pure and cheap — no slice
    fits — so it can be rebuilt per solve when the user edits the weights."""
    weights: dict[tuple, float] = {}
    for ticker, isos in ladders.items():
        for near, far in zip(isos[:-1], isos[1:]):
            weights[((ticker, near), (ticker, far))] = calendar_w
            weights[((ticker, far), (ticker, near))] = calendar_w
    for a, b in itertools.combinations(tickers, 2):
        for iso in sorted(set(ladders.get(a, [])) & set(ladders.get(b, []))):
            weights[((a, iso), (b, iso))] = cross_w
            weights[((b, iso), (a, iso))] = cross_w
        for iso_a, iso_b, gap in nearest_cross_expiry_pairs(
            ladders.get(a, []), ladders.get(b, []), cross_expiry_tol_days
        ):
            w = cross_w * cross_expiry_tol_days / (cross_expiry_tol_days + gap)
            weights[((a, iso_a), (b, iso_b))] = w
            weights[((b, iso_b), (a, iso_a))] = w
    return weights
