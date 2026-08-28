"""Graph leave-one-out backtest edges + scoring (backtest/graph_loo.py, roadmap Phase 6).

The bug-prone core is the directed edge construction: the DIRECTION convention
(``volfit.graph.build``: ``w_ij`` = "j informs i", so a ``GraphEdgeInput`` flows
``to`` -> ``from``), the vol-normalized cross-asset betas, and the sqrt-T calendar
betas. These gates lock that logic so a future refactor can't silently reverse the
information flow (which would invalidate every result).
"""

from __future__ import annotations

import math

import pytest

from backtest.graph_edges import EdgeConfig, asset_kind, asset_sector, build_directed_edges
from volfit.api.graph_params import nearest_cross_expiry_pairs


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


# ------------------------------------------------ cross-venue async expiries
#: Deliberately asynchronous ladders: each AAPL rung sits one day BEFORE its
#: SPX rung; MSFT shares one ISO with each of them.
ASYNC_LADDERS = {
    "SPX": ["2024-08-16", "2024-09-20"],
    "AAPL": ["2024-08-15", "2024-09-19"],
    "MSFT": ["2024-08-16", "2024-09-19"],
}


def _async_universe():
    """SPX hub + two tech names (AAPL/MSFT) over ASYNC_LADDERS."""
    nodes = [(tk, iso) for tk, isos in ASYNC_LADDERS.items() for iso in isos]
    sigma = {n: {"SPX": 0.15, "AAPL": 0.25, "MSFT": 0.30}[n[0]] for n in nodes}
    t_iso = {"2024-08-15": 0.049, "2024-08-16": 0.052, "2024-09-19": 0.145, "2024-09-20": 0.148}
    return nodes, sigma, {n: t_iso[n[1]] for n in nodes}


def test_cross_expiry_default_is_exact_iso_only():
    """Rider lock (ROADMAP 2026-08-25a): the default EdgeConfig is exact-ISO
    only — the default edge list is bit-identical to an explicit tol 0.0, and
    structurally NO cross-ticker edge joins two different expiries (only the
    same-ticker calendar edges change maturity)."""
    nodes, sigma, t = _async_universe()
    base = build_directed_edges(nodes, sigma, t, EdgeConfig())
    assert base == build_directed_edges(nodes, sigma, t, EdgeConfig(cross_expiry_tol_days=0.0))
    cross = [e for e in base if e.fromTicker != e.toTicker]
    assert all(e.fromExpiry == e.toExpiry for e in cross)
    # Exactly the shared rungs: SPX<->MSFT on 08-16 (forward + recurrence
    # reverse) and the AAPL<->MSFT peer pair on 09-19 (both directions);
    # SPX and AAPL never meet.
    assert len(cross) == 4
    assert not any({e.fromTicker, e.toTicker} == {"SPX", "AAPL"} for e in cross)
    # A tolerance BELOW the one-day gap changes nothing either.
    assert base == build_directed_edges(nodes, sigma, t, EdgeConfig(cross_expiry_tol_days=0.5))


def test_cross_expiry_pairs_reuse_production_helper():
    """tol 3: every unmatched rung pairs with the other ticker's nearest
    expiry — the production nearest_cross_expiry_pairs pairing, verbatim — at
    the class weight attenuated by tol/(tol+gap), betas untouched; the same-ISO
    edges are a strict, untouched prefix."""
    nodes, sigma, t = _async_universe()
    cfg = EdgeConfig(cross_expiry_tol_days=3.0)
    base = build_directed_edges(nodes, sigma, t, EdgeConfig())
    edges = build_directed_edges(nodes, sigma, t, cfg)
    assert edges[: len(base)] == base
    new = edges[len(base):]
    # SPX->AAPL on both rungs (forward + reverse), SPX->MSFT Sep (forward +
    # reverse), AAPL<->MSFT Aug peers (both directions): 8 edges, 1 day apart.
    assert len(new) == 8
    got = {frozenset({(e.fromTicker, e.fromExpiry), (e.toTicker, e.toExpiry)}) for e in new}
    want = set()
    for a, b in (("AAPL", "MSFT"), ("AAPL", "SPX"), ("MSFT", "SPX")):
        for iso_a, iso_b, gap in nearest_cross_expiry_pairs(ASYNC_LADDERS[a], ASYNC_LADDERS[b], 3.0):
            assert gap == 1
            want.add(frozenset({(a, iso_a), (b, iso_b)}))
    assert got == want and len(want) == 4
    m = _edge_map(new)
    att = 3.0 / (3.0 + 1)
    e = m[(("AAPL", "2024-08-15"), ("SPX", "2024-08-16"))]  # SPX informs AAPL
    assert e.weight == pytest.approx(cfg.index_weight * att)
    assert e.betaAtmVol == pytest.approx(0.7 * 0.25 / 0.15)  # vol-normalized, no maturity term
    r = m[(("SPX", "2024-08-16"), ("AAPL", "2024-08-15"))]  # recurrence reverse edge
    assert r.weight == pytest.approx(cfg.index_weight * att * cfg.cross_reverse_frac)
    assert r.betaAtmVol == pytest.approx(1.0 / e.betaAtmVol)
    p = m[(("MSFT", "2024-08-16"), ("AAPL", "2024-08-15"))]  # peers, both ways
    assert p.weight == pytest.approx(cfg.name_weight * att)
    assert (("AAPL", "2024-08-15"), ("MSFT", "2024-08-16")) in m
