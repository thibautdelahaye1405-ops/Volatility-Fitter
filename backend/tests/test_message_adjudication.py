"""Phase-4 tests: the adjudication machinery (message arc P4).

Locks the message topology builder (same taxonomy as the smooth-field edge
builder, canonical one-factor-per-relation orientation), the hops/coverage
metrics, and the MessageKnobs plumbing — the parts of the campaign that must
be right BEFORE the user burns hours on the sweep."""

from __future__ import annotations

import numpy as np

from backtest.benchmark_pack import summarize_by
from backtest.graph_edges import (
    MSG_INDEX_PRECISION,
    MSG_PEER_PRECISION,
    EdgeConfig,
    build_message_edges,
)
from backtest.graph_loo import COVERAGE_Z, MessageKnobs, _adjacency, _hops_from_lit

from volfit.api.graph_universe import SelectedNode, SelectedUniverse
from volfit.api.schemas import GraphExtrapolateRequest


# --------------------------------------------------------- topology builder
def _toy_universe():
    """SPX hub + two same-sector names (AAPL/MSFT = tech) + a lone-sector
    name (CAT = industrials), two shared expiries."""
    nodes = [
        ("SPX", "2024-08-16"), ("SPX", "2024-09-20"),
        ("MSFT", "2024-08-16"), ("MSFT", "2024-09-20"),
        ("AAPL", "2024-08-16"),
        ("CAT", "2024-08-16"),
    ]
    sigma = {n: {"SPX": 0.15, "MSFT": 0.50, "AAPL": 0.25, "CAT": 0.20}[n[0]] for n in nodes}
    t = {n: {"2024-08-16": 0.05, "2024-09-20": 0.15}[n[1]] for n in nodes}
    return nodes, sigma, t


def test_build_message_edges_taxonomy_and_orientation():
    nodes, sigma, t = _toy_universe()
    rows = build_message_edges(nodes, sigma, t, EdgeConfig(), alpha_t=1.0)
    by_class: dict = {}
    for r in rows:
        by_class.setdefault(r.relationClass, []).append(r)

    # calendar: one factor per adjacent pair per ticker, receiver = SHORTER
    cal = by_class["calendar"]
    assert {(r.targetTicker, r.sourceTicker) for r in cal} == {("SPX", "SPX"), ("MSFT", "MSFT")}
    for r in cal:
        assert r.targetExpiry == "2024-08-16" and r.sourceExpiry == "2024-09-20"
        assert r.precisionRule == "calendar_distance"
        np.testing.assert_allclose(r.betaAtmVol, 3.0)  # (0.15/0.05)^1

    # broad_index: hub informs each single name, beta = sigma_name / sigma_idx
    idx = by_class["broad_index"]
    assert {(r.targetTicker, r.targetExpiry) for r in idx} == {
        ("MSFT", "2024-08-16"), ("MSFT", "2024-09-20"),
        ("AAPL", "2024-08-16"), ("CAT", "2024-08-16"),
    }
    msft = next(r for r in idx if r.targetTicker == "MSFT")
    assert msft.sourceTicker == "SPX"
    assert msft.betaAtmVol == 3.0  # sigma ratio 0.50/0.15 = 3.33, capped at 3
    aapl = next(r for r in idx if r.targetTicker == "AAPL")
    np.testing.assert_allclose(aapl.betaAtmVol, 0.25 / 0.15)
    assert msft.messagePrecision == MSG_INDEX_PRECISION

    # sector_peer: ONE factor per unordered same-sector pair, lexicographic
    # receiver (AAPL < MSFT), beta = sigma_receiver / sigma_informer
    peers = by_class["sector_peer"]
    assert len(peers) == 1
    (p,) = peers
    assert (p.targetTicker, p.sourceTicker) == ("AAPL", "MSFT")
    np.testing.assert_allclose(p.betaAtmVol, 0.25 / 0.50)
    assert p.messagePrecision == MSG_PEER_PRECISION
    # CAT has no same-sector peer and no ETF -> index row only
    assert not any(r.targetTicker == "CAT" for r in peers)


def test_build_message_edges_alpha_and_precision_mult():
    nodes, sigma, t = _toy_universe()
    rows = build_message_edges(
        nodes, sigma, t, EdgeConfig(), alpha_t=0.5, cross_precision_mult=2.0
    )
    cal = [r for r in rows if r.relationClass == "calendar"]
    np.testing.assert_allclose(cal[0].betaAtmVol, np.sqrt(3.0))  # (0.15/0.05)^0.5
    idx = [r for r in rows if r.relationClass == "broad_index"]
    assert idx[0].messagePrecision == 2.0 * MSG_INDEX_PRECISION


# ------------------------------------------------------------- hops metric
def test_adjacency_and_hops_message_mode():
    nodes = (
        SelectedNode("SPX", "E", True),
        SelectedNode("NVDA", "E", False),
        SelectedNode("NVDA", "F", False),
        SelectedNode("ZZZ", "Q", False),  # disconnected
    )
    universe = SelectedUniverse(nodes=nodes, graph=None)
    n, sigma = list(universe.names), {u: 0.2 for u in universe.names}
    t = {("SPX", "E"): 0.1, ("NVDA", "E"): 0.1, ("NVDA", "F"): 0.3, ("ZZZ", "Q"): 0.2}
    rows = build_message_edges(n, sigma, t, EdgeConfig())
    req = GraphExtrapolateRequest(
        propagationMode="precision_messages", messageEdges=rows
    )
    adj = _adjacency(universe, req)
    lit = {0}
    assert _hops_from_lit(adj, lit, 0) == 0
    assert _hops_from_lit(adj, lit, 1) == 1  # SPX-E -> NVDA-E (index edge)
    assert _hops_from_lit(adj, lit, 2) == 2  # ... -> NVDA-F (calendar edge)
    assert _hops_from_lit(adj, lit, 3) is None  # unreachable


# ------------------------------------------------------- coverage summaries
def test_summarize_by_band_coverage():
    """cov_p = P(|zeta| <= z_p) lands in the aggregates (retroactively valid
    for every stored row that carries zeta)."""
    rows = [
        {"design": "liquid_split", "ssr": 1, "zeta": z,
         "res_atm": 0.001, "base_atm": 0.002}
        for z in (-0.5, 0.5, 1.0, -1.5, 2.5)
    ]
    (rec,) = summarize_by(rows, ("design", "ssr"))
    assert rec["cov50"] == 0.4   # |z| <= 0.6745: two of five
    assert rec["cov80"] == 0.6   # + 1.0
    assert rec["cov95"] == 0.8   # + 1.5
    assert set(COVERAGE_Z) == {"cov50", "cov80", "cov95"}


def test_message_knobs_defaults_are_inert():
    assert MessageKnobs().mode == "smooth_field"
    learned = MessageKnobs(mode="precision_messages", amp_cal=0.23, amp_cross=0.39)
    assert learned.cal_decay == "inverse_sqrt_gap"
    assert learned.cal_precision == 1.7e3 and learned.cal_epsilon == 0.97
