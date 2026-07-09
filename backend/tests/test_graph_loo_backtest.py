"""Graph leave-one-out backtest edges + scoring (backtest/graph_loo.py, roadmap Phase 6).

The bug-prone core is the directed edge construction: the DIRECTION convention
(``volfit.graph.build``: ``w_ij`` = "j informs i", so a ``GraphEdgeInput`` flows
``to`` -> ``from``), the vol-normalized cross-asset betas, and the sqrt-T calendar
betas. These gates lock that logic so a future refactor can't silently reverse the
information flow (which would invalidate every result).
"""

from __future__ import annotations

import math

from backtest.graph_edges import EdgeConfig, asset_kind, asset_sector, build_directed_edges


def test_asset_taxonomy():
    assert asset_kind("SPX") == "index"
    assert asset_kind("EEM") == "etf" and asset_kind("EFA") == "etf"
    assert asset_kind("AAPL") == "name" and asset_kind("JPM") == "name"
    assert asset_sector("AAPL") == "tech" and asset_sector("MSFT") == "tech"
    assert asset_sector("JPM") == "financials"


def _edge_map(edges):
    """{((fromTicker, fromExpiry), (toTicker, toExpiry)): GraphEdgeInput}."""
    return {((e.fromTicker, e.fromExpiry), (e.toTicker, e.toExpiry)): e for e in edges}


def test_index_to_name_direction_and_vol_normalization():
    """Index informs name: the edge is from=NAME, to=INDEX (info flows to->from), and
    the absolute beta is the vol-normalized 0.7 times sigma_name / sigma_index.

    A REVERSE edge (name informs index) is also emitted with the INVERSE beta:
    without it single names are transient states of the directed walk (stationary
    mass 0 -> reversibilized conductance 0 -> dark names fully decoupled — the
    2026-07-09 liquid_split root cause). Same relation, so no new economics."""
    iso = "2024-08-16"
    spx, aapl = ("SPX", iso), ("AAPL", iso)
    sigma = {spx: 0.20, aapl: 0.40}
    t = {spx: 0.1, aapl: 0.1}
    edges = _edge_map(build_directed_edges([spx, aapl], sigma, t, EdgeConfig()))

    assert (aapl, spx) in edges  # influenced=AAPL is `from`, informer=SPX is `to`
    e = edges[(aapl, spx)]
    assert math.isclose(e.betaAtmVol, 0.7 * 0.40 / 0.20, rel_tol=1e-9)  # vol-normalized
    assert e.betaAtmVol == e.betaSkew == e.betaCurv  # v1: same beta on all handles
    # reverse edge: same weight (conductance symmetric), inverse beta (same relation)
    r = edges[(spx, aapl)]
    assert r.weight == e.weight
    assert math.isclose(r.betaAtmVol, 1.0 / e.betaAtmVol, rel_tol=1e-9)
    # ablation switch reproduces the legacy one-way topology
    legacy = _edge_map(build_directed_edges(
        [spx, aapl], sigma, t, EdgeConfig(cross_reverse_frac=0.0)))
    assert (spx, aapl) not in legacy


def test_same_sector_name_edges_only():
    """name -> name edges exist BOTH ways within a sector (beta 0.6 vol-normalized) and
    are ABSENT across sectors."""
    iso = "2024-08-16"
    aapl, msft, jpm = ("AAPL", iso), ("MSFT", iso), ("JPM", iso)
    sigma = {aapl: 0.30, msft: 0.30, jpm: 0.30}
    t = {n: 0.1 for n in (aapl, msft, jpm)}
    edges = _edge_map(build_directed_edges([aapl, msft, jpm], sigma, t, EdgeConfig()))

    assert (aapl, msft) in edges and (msft, aapl) in edges  # same sector (tech)
    assert math.isclose(edges[(aapl, msft)].betaAtmVol, 0.6, rel_tol=1e-9)  # equal sigma
    assert (aapl, jpm) not in edges and (jpm, aapl) not in edges  # cross sector


def test_calendar_beta_scales_sqrt_t():
    """Calendar edges run both directions; beta = sqrt(T_informer / T_influenced):
    the long expiry informing the short amplifies (>1), the short informing the long
    damps (<1)."""
    near, far = ("SPX", "2024-08-09"), ("SPX", "2024-09-20")
    nodes = [near, far]
    sigma = {near: 0.2, far: 0.2}
    t = {near: 0.05, far: 0.30}
    edges = _edge_map(build_directed_edges(nodes, sigma, t, EdgeConfig()))

    # far informs near (from=near, to=far): beta = sqrt(T_far / T_near) > 1
    assert math.isclose(edges[(near, far)].betaAtmVol, math.sqrt(0.30 / 0.05), rel_tol=1e-9)
    # near informs far (from=far, to=near): beta = sqrt(T_near / T_far) < 1
    assert math.isclose(edges[(far, near)].betaAtmVol, math.sqrt(0.05 / 0.30), rel_tol=1e-9)
    assert edges[(near, far)].weight == EdgeConfig().cal_weight  # high calendar conductance


def test_beta_cap_clips_extremes():
    """A large sigma ratio is clipped to beta_cap so a degenerate vol can't blow up."""
    iso = "2024-08-16"
    spx, aapl = ("SPX", iso), ("AAPL", iso)
    sigma = {spx: 0.05, aapl: 1.0}  # ratio 20 -> 0.7*20 = 14 >> cap
    t = {spx: 0.1, aapl: 0.1}
    edges = _edge_map(build_directed_edges([spx, aapl], sigma, t, EdgeConfig(beta_cap=3.0)))
    assert edges[(aapl, spx)].betaAtmVol == 3.0
