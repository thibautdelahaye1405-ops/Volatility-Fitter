"""Cross-venue asynchronous expiries: edges between (A, T_A) and (B, T_B).

Cross-venue ladders are not synchronous (an SPX Friday vs a DAX Thursday), so
the exact-ISO intersection that generates the cross-ticker lattice/relations
finds nothing between venues. ``crossExpiryToleranceDays`` > 0 opts into
nearest-expiry pairing (graph_params.nearest_cross_expiry_pairs and the
message-mode ``_cross_expiry_message_edges``): attenuated lattice weight
tol/(tol+gap), |dT|-decayed cross precision normalized to the synchronous
value, and the maturity-shape beta (T_inf/T_recv)^alphaT. The default 0 is
locked byte-identical to the historical exact-date topology.
"""

import math

import pytest

from volfit.api.graph_message import auto_message_edges
from volfit.api.graph_params import lattice_weights, nearest_cross_expiry_pairs
from volfit.api.graph_universe import SelectedNode, SelectedUniverse
from volfit.api.schemas import GraphExtrapolateRequest

# Deliberately asynchronous venue ladders: one day apart at both rungs.
SPX = ["2026-09-18", "2026-12-18"]
DAX = ["2026-09-17", "2026-12-17"]
LADDERS = {"SPX": SPX, "DAX": DAX}


def test_default_tolerance_zero_is_exact_match_only():
    """tol=0 keeps the historical topology byte-identical: calendar chains
    only (no ISO is shared, so no cross edge exists at all)."""
    weights = lattice_weights(["SPX", "DAX"], LADDERS, 10.0, 2.0)
    expected = {
        (("SPX", SPX[0]), ("SPX", SPX[1])): 10.0,
        (("SPX", SPX[1]), ("SPX", SPX[0])): 10.0,
        (("DAX", DAX[0]), ("DAX", DAX[1])): 10.0,
        (("DAX", DAX[1]), ("DAX", DAX[0])): 10.0,
    }
    assert weights == expected


def test_nearest_pairs_within_tolerance():
    """Each unmatched rung pairs with the other venue's nearest expiry; the
    two directions dedup to one symmetric pair per rung."""
    pairs = nearest_cross_expiry_pairs(SPX, DAX, tol_days=5.0)
    assert pairs == [
        ("2026-09-18", "2026-09-17", 1),
        ("2026-12-18", "2026-12-17", 1),
    ]
    # Tolerance cut: a 1-day gap needs tol >= 1; tol below the gap drops it.
    assert nearest_cross_expiry_pairs(SPX, DAX, tol_days=0.5) == []


def test_shared_iso_keeps_full_weight_and_is_not_repaired():
    """A rung with an exact partner keeps the standard edge; only the
    unmatched rung gets a nearest-expiry edge, at the attenuated weight."""
    ladders = {"SPX": ["2026-09-18", "2026-12-18"], "ESX": ["2026-09-18", "2026-12-17"]}
    weights = lattice_weights(["SPX", "ESX"], ladders, 10.0, 2.0, cross_expiry_tol_days=5.0)
    # Exact-date cross edge: untouched full cross weight.
    assert weights[(("SPX", "2026-09-18"), ("ESX", "2026-09-18"))] == 2.0
    # Asynchronous rung: nearest pair at weight cross_w * tol / (tol + gap).
    w = weights[(("SPX", "2026-12-18"), ("ESX", "2026-12-17"))]
    assert w == pytest.approx(2.0 * 5.0 / 6.0)
    assert weights[(("ESX", "2026-12-17"), ("SPX", "2026-12-18"))] == pytest.approx(w)
    # The September rung must not ALSO pair across dates.
    assert (("SPX", "2026-09-18"), ("ESX", "2026-12-17")) not in weights


def _universe(nodes):
    return SelectedUniverse(nodes=tuple(nodes), graph=None)


def test_auto_message_edges_cross_expiry_factor():
    """Message mode: the asynchronous pair gets one custom factor with the
    canonical short receiver, maturity-shape beta and normalized |dT| decay."""
    nodes = [
        SelectedNode("SPX", "2026-09-18", lit=True),
        SelectedNode("DAX", "2026-09-17", lit=False),
    ]
    t_by = {("SPX", "2026-09-18"): 0.30, ("DAX", "2026-09-17"): 0.30 - 1.0 / 365.0}
    base = GraphExtrapolateRequest()
    # Default tolerance 0: different ISO dates -> no cross factor at all.
    assert auto_message_edges(_universe(nodes), t_by, base) == []

    request = GraphExtrapolateRequest(crossExpiryToleranceDays=5.0)
    edges = auto_message_edges(_universe(nodes), t_by, request)
    assert len(edges) == 1
    edge = edges[0]
    t_recv, t_inf = t_by[("DAX", "2026-09-17")], t_by[("SPX", "2026-09-18")]
    assert edge.receiver == ("DAX", "2026-09-17")  # shorter maturity receives
    assert edge.informer == ("SPX", "2026-09-18")
    assert edge.relation_class == "custom"
    beta = (t_inf / t_recv) ** request.calendarBetaExponent
    assert edge.beta == pytest.approx((beta, beta, beta))
    eps = request.calendarPrecisionEpsilon
    gap = abs(t_inf - t_recv)
    expect_p = request.crossPrecisionScale * eps / (eps + math.sqrt(gap))
    assert edge.precision == pytest.approx(expect_p)
    assert edge.precision < request.crossPrecisionScale  # decayed, never above


def test_cross_expiry_tolerance_cut_in_message_mode():
    """A gap beyond the tolerance produces no factor (365 days apart)."""
    nodes = [
        SelectedNode("SPX", "2026-09-18", lit=True),
        SelectedNode("DAX", "2027-09-17", lit=False),
    ]
    t_by = {("SPX", "2026-09-18"): 0.30, ("DAX", "2027-09-17"): 1.30}
    request = GraphExtrapolateRequest(crossExpiryToleranceDays=5.0)
    assert auto_message_edges(_universe(nodes), t_by, request) == []


def test_request_schema_default_and_bounds():
    assert GraphExtrapolateRequest().crossExpiryToleranceDays == 0.0
    with pytest.raises(ValueError):
        GraphExtrapolateRequest(crossExpiryToleranceDays=-1.0)
