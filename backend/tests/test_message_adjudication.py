"""Phase-4 tests: the adjudication machinery (message arc P4).

Locks the message topology builder (same taxonomy as the smooth-field edge
builder, canonical one-factor-per-relation orientation), the hops/coverage
metrics, and the MessageKnobs plumbing — the parts of the campaign that must
be right BEFORE the user burns hours on the sweep."""

from __future__ import annotations

import math

import numpy as np

from backtest.benchmark_pack import summarize_by
from backtest.graph_edges import (
    MSG_INDEX_PRECISION,
    MSG_PEER_PRECISION,
    EdgeConfig,
    build_message_edges,
)
from backtest.graph_loo import COVERAGE_Z, MessageKnobs, _adjacency, _hops_from_lit

from volfit.api.graph_params import nearest_cross_expiry_pairs
from volfit.api.graph_universe import SelectedNode, SelectedUniverse
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.graph.message import CALENDAR_PRECISION_EPSILON, cross_expiry_precision


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


# ------------------------------------------------ cross-venue async expiries
#: Deliberately asynchronous ladders (mirrors test_graph_loo_backtest): each
#: AAPL rung sits one day BEFORE its SPX rung; MSFT shares one ISO with each.
ASYNC_LADDERS = {
    "SPX": ["2024-08-16", "2024-09-20"],
    "AAPL": ["2024-08-15", "2024-09-19"],
    "MSFT": ["2024-08-16", "2024-09-19"],
}


def _async_universe():
    nodes = [(tk, iso) for tk, isos in ASYNC_LADDERS.items() for iso in isos]
    sigma = {n: {"SPX": 0.15, "AAPL": 0.25, "MSFT": 0.30}[n[0]] for n in nodes}
    t_iso = {"2024-08-15": 0.049, "2024-08-16": 0.052, "2024-09-19": 0.145, "2024-09-20": 0.148}
    return nodes, sigma, {n: t_iso[n[1]] for n in nodes}


def test_cross_expiry_default_is_exact_iso_only():
    """Rider lock: the default message topology is exact-ISO only — bit-
    identical to an explicit tol 0.0, and no cross-asset factor joins two
    different expiries (only calendar factors change maturity)."""
    nodes, sigma, t = _async_universe()
    base = build_message_edges(nodes, sigma, t, EdgeConfig())
    assert base == build_message_edges(nodes, sigma, t, EdgeConfig(cross_expiry_tol_days=0.0))
    cross = [r for r in base if r.relationClass != "calendar"]
    assert all(r.sourceExpiry == r.targetExpiry for r in cross)
    assert {(r.targetTicker, r.sourceTicker, r.targetExpiry) for r in cross} == {
        ("MSFT", "SPX", "2024-08-16"), ("AAPL", "MSFT", "2024-09-19"),
    }
    assert base == build_message_edges(nodes, sigma, t, EdgeConfig(cross_expiry_tol_days=0.5))


def test_cross_expiry_pairs_reuse_production_helper():
    """tol 3: one factor per asynchronous nearest pair (the production
    helper's pairing), |dT|-decayed precision normalized to the class seed,
    maturity-shape beta composed onto the sigma ratio (shape handles carry
    the maturity beta alone); the same-ISO rows are a strict prefix."""
    nodes, sigma, t = _async_universe()
    cfg = EdgeConfig(cross_expiry_tol_days=3.0)
    base = build_message_edges(nodes, sigma, t, EdgeConfig(), alpha_t=0.5)
    rows = build_message_edges(nodes, sigma, t, cfg, alpha_t=0.5)
    assert rows[: len(base)] == base
    new = rows[len(base):]
    assert len(new) == 4
    got = {frozenset({(r.sourceTicker, r.sourceExpiry), (r.targetTicker, r.targetExpiry)}) for r in new}
    want = set()
    for a, b in (("AAPL", "MSFT"), ("AAPL", "SPX"), ("MSFT", "SPX")):
        for iso_a, iso_b, _gap in nearest_cross_expiry_pairs(ASYNC_LADDERS[a], ASYNC_LADDERS[b], 3.0):
            want.add(frozenset({(a, iso_a), (b, iso_b)}))
    assert got == want
    by = {(r.targetTicker, r.targetExpiry, r.sourceTicker, r.sourceExpiry): r for r in new}

    # Hub class keeps the taxonomy orientation: SPX (source) informs AAPL.
    r = by[("AAPL", "2024-08-15", "SPX", "2024-08-16")]
    assert r.relationClass == "broad_index" and r.precisionRule == "explicit"
    t_r, t_i = t[("AAPL", "2024-08-15")], t[("SPX", "2024-08-16")]
    shape = (t_i / t_r) ** 0.5
    np.testing.assert_allclose(r.betaAtmVol, (0.25 / 0.15) * shape)
    np.testing.assert_allclose((r.betaSkew, r.betaCurv), (shape, shape))
    eps = CALENDAR_PRECISION_EPSILON
    np.testing.assert_allclose(
        r.messagePrecision, MSG_INDEX_PRECISION * eps / (eps + math.sqrt(abs(t_i - t_r)))
    )
    np.testing.assert_allclose(
        r.messagePrecision, cross_expiry_precision(t_r, t_i, scale=MSG_INDEX_PRECISION)
    )
    assert r.messagePrecision < MSG_INDEX_PRECISION  # decayed, never above the seed

    # Peer class: canonical SHORT receiver (AAPL Aug-15 before MSFT Aug-16).
    p = by[("AAPL", "2024-08-15", "MSFT", "2024-08-16")]
    assert p.relationClass == "sector_peer"
    t_m = t[("MSFT", "2024-08-16")]
    np.testing.assert_allclose(p.betaAtmVol, (0.25 / 0.30) * (t_m / t_r) ** 0.5)
    np.testing.assert_allclose(
        p.messagePrecision, cross_expiry_precision(t_r, t_m, scale=MSG_PEER_PRECISION)
    )

    # The cross precision multiplier scales the asynchronous seeds too.
    doubled = build_message_edges(nodes, sigma, t, cfg, alpha_t=0.5, cross_precision_mult=2.0)
    np.testing.assert_allclose(
        [x.messagePrecision for x in doubled[len(base):]],
        [2.0 * x.messagePrecision for x in new],
    )
