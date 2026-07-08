"""Ticker-block topology rules (sparse block-matrix editor) — expansion + routes.

The user writes rules at ticker-pair level (plus per-ticker calendar weights and
optional per-edge overrides); the backend persists the RULE verbatim (a lossless
round-trip through GET/PUT /graph/edges/blocks) and expands it into the per-edge
list ``/graph/edges`` continues to serve. Expansion pairing must match the
auto-lattice: cross edges on shared expiries only, calendar chains in both
directions. The raw per-edge PUT clears the stored rule (a hand-edited list
would make a kept rule lie).
"""

import tempfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.graph_blocks import expand_block_rule
from volfit.api.graph_extrapolation import lattice_edges
from volfit.api.schemas import (
    GraphBlockCalendar,
    GraphBlockPair,
    GraphBlockRule,
    GraphEdgeInput,
)
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)

EMPTY_RULE = {"pairs": [], "calendar": [], "overrides": []}


@pytest.fixture()
def state() -> AppState:
    return AppState(REF_DATE)


def _two_tickers_sharing_two(state):
    """Carve overlapping ladders: ticker ``a`` keeps 3 expiries, ``b`` keeps 2 of
    them — so exactly 2 expiries are shared (the synthetic grid is common)."""
    a, b = state.active_tickers()[:2]
    grid = state.available_expiries(a)
    assert len(grid) >= 3
    state.set_expiries(a, grid[:3])
    state.set_expiries(b, grid[:2])
    return a, b, [e.isoformat() for e in grid[:2]]


def test_symmetric_pair_expands_on_shared_expiries_only(state):
    a, b, shared = _two_tickers_sharing_two(state)
    rule = GraphBlockRule(pairs=[GraphBlockPair(a=a, b=b, weight=2.5, beta=1.3)])
    edges = expand_block_rule(state, rule)
    # 2 shared expiries x both directions; a's unshared third expiry contributes
    # nothing (the lattice's cross pairing: expiries present in BOTH ladders).
    assert len(edges) == 4
    keys = {(e.fromTicker, e.fromExpiry, e.toTicker, e.toExpiry) for e in edges}
    for iso in shared:
        assert (a, iso, b, iso) in keys and (b, iso, a, iso) in keys
    assert all(e.weight == 2.5 for e in edges)
    assert all(e.betaAtmVol == e.betaSkew == e.betaCurv == 1.3 for e in edges)


def test_asymmetric_pair_expands_one_direction(state):
    a, b, shared = _two_tickers_sharing_two(state)
    rule = GraphBlockRule(pairs=[GraphBlockPair(a=a, b=b, weight=1.0, symmetric=False)])
    edges = expand_block_rule(state, rule)
    assert len(edges) == 2  # a -> b only, on the 2 shared expiries
    assert all(e.fromTicker == a and e.toTicker == b for e in edges)
    assert {e.fromExpiry for e in edges} == set(shared)


def test_calendar_rule_matches_lattice_directionality(state):
    tk = state.active_tickers()[0]
    isos = [e.isoformat() for e in sorted(state.selected_expiries(tk))]
    rule = GraphBlockRule(calendar=[GraphBlockCalendar(ticker=tk, weight=3.0, beta=0.9)])
    edges = expand_block_rule(state, rule)
    got = {(e.fromExpiry, e.toExpiry) for e in edges}
    want = set()
    for near, far in zip(isos[:-1], isos[1:]):
        want.update({(near, far), (far, near)})  # consecutive, BOTH directions
    assert got == want
    # The auto-lattice carries exactly these directed calendar pairs for the
    # ticker, so the block expansion reproduces its directionality.
    lattice = {
        (e.fromExpiry, e.toExpiry)
        for e in lattice_edges(state)
        if e.fromTicker == tk and e.toTicker == tk
    }
    assert want == lattice
    assert all(e.weight == 3.0 and e.betaAtmVol == 0.9 for e in edges)


def test_override_replaces_expanded_edge(state):
    a, b, shared = _two_tickers_sharing_two(state)
    iso = shared[0]
    override = GraphEdgeInput(
        fromTicker=a, fromExpiry=iso, toTicker=b, toExpiry=iso,
        weight=9.0, betaAtmVol=2.0,
    )
    rule = GraphBlockRule(
        pairs=[GraphBlockPair(a=a, b=b, weight=1.0)], overrides=[override]
    )
    edges = expand_block_rule(state, rule)
    assert len(edges) == 4  # replaced in place, NOT duplicated
    hit = [
        e for e in edges
        if (e.fromTicker, e.fromExpiry, e.toTicker, e.toExpiry) == (a, iso, b, iso)
    ]
    assert len(hit) == 1
    assert hit[0].weight == 9.0 and hit[0].betaAtmVol == 2.0
    # The reverse direction is untouched: still the pair rule's weight.
    rev = [e for e in edges if (e.fromTicker, e.toTicker, e.fromExpiry) == (b, a, iso)]
    assert len(rev) == 1 and rev[0].weight == 1.0


def test_unknown_tickers_skipped_silently(state):
    rule = GraphBlockRule(
        pairs=[GraphBlockPair(a="ZZTOP", b=state.active_tickers()[0], weight=1.0)],
        calendar=[GraphBlockCalendar(ticker="NOPE", weight=2.0)],
    )
    assert expand_block_rule(state, rule) == []  # no crash, no edges


def test_routes_blocks_round_trip():
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        # No rule stored: an empty rule with a zero-sized expansion.
        got = client.get("/graph/edges/blocks").json()
        assert got["rule"] == EMPTY_RULE and got["expandedCount"] == 0

        seed = client.get("/graph/edges/lattice").json()["edges"]
        t0, t1 = sorted({e["fromTicker"] for e in seed})[:2]
        rule = {
            "pairs": [{"a": t0, "b": t1, "weight": 2.0, "beta": 1.2, "symmetric": True}],
            "calendar": [],
            "overrides": [],
        }
        put = client.put("/graph/edges/blocks", json=rule).json()
        assert put["rule"] == rule  # the rule round-trips exactly as written
        assert put["expandedCount"] > 0
        # /graph/edges serves the EXPANDED list immediately.
        edges = client.get("/graph/edges").json()["edges"]
        assert len(edges) == put["expandedCount"]
        assert all(e["weight"] == 2.0 and e["betaAtmVol"] == 1.2 for e in edges)
        # GET returns the same persisted rule.
        assert client.get("/graph/edges/blocks").json()["rule"] == rule

        # An all-empty rule clears both — back to the auto-lattice.
        cleared = client.put("/graph/edges/blocks", json=EMPTY_RULE).json()
        assert cleared["rule"] == EMPTY_RULE and cleared["expandedCount"] == 0
        assert client.get("/graph/edges").json()["edges"] == []


def test_raw_edges_put_clears_the_rule():
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        seed = client.get("/graph/edges/lattice").json()["edges"]
        t0, t1 = sorted({e["fromTicker"] for e in seed})[:2]
        rule = {
            "pairs": [{"a": t0, "b": t1, "weight": 4.0, "beta": 1.0, "symmetric": True}],
            "calendar": [],
            "overrides": [],
        }
        assert client.put("/graph/edges/blocks", json=rule).json()["rule"] == rule
        # Hand-editing the raw per-edge list drops the stale rule but keeps the
        # hand-edited list itself.
        client.put("/graph/edges", json={"edges": seed[:1]})
        assert client.get("/graph/edges/blocks").json()["rule"] == EMPTY_RULE
        assert client.get("/graph/edges").json()["edges"] == seed[:1]


def test_rule_persists_across_restart():
    with tempfile.TemporaryDirectory() as d:
        path = f"{d}/store.sqlite"
        s1 = AppState(REF_DATE, store_path=path)
        a, b = s1.active_tickers()[:2]
        rule = GraphBlockRule(pairs=[GraphBlockPair(a=a, b=b, weight=4.0, beta=1.1)])
        s1.set_graph_block_rule(rule, expand_block_rule(s1, rule))
        assert len(s1.graph_edges()) > 0
        # A fresh state over the same store restores rule AND expansion.
        s2 = AppState(REF_DATE, store_path=path)
        restored = s2.graph_block_rule()
        assert restored is not None
        assert restored.model_dump() == rule.model_dump()
        assert len(s2.graph_edges()) == len(s1.graph_edges())
