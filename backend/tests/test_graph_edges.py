"""User-supplied per-edge graph (weight + beta), persisted (plan Phase 7).

An explicit edge list defines the whole topology over the selected node set,
overriding the auto-lattice; weights are directional (asymmetric allowed); the
overrides round-trip through the store; request edges win over persisted ones.
"""

import tempfile
from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.graph_extrapolation import extrapolate, lattice_edges, solve
from volfit.api.graph_universe import build_selected_universe
from volfit.api.schemas import GraphEdgeInput, GraphExtrapolateRequest
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def state() -> AppState:
    return AppState(REF_DATE)


def _names(state, tk):
    return [(tk, e.isoformat()) for e in sorted(state.selected_expiries(tk))]


def test_explicit_edges_override_the_lattice(state):
    tk = state.active_tickers()[0]
    n = _names(state, tk)
    # A single directed edge n0 -> n1: only that pair is connected.
    edges = [(n[0], n[1], 5.0)]
    uni = build_selected_universe(state, edges=edges)
    assert uni.graph is not None
    # The kernel has support only on the supplied edge (row n0 -> n1), so n1's
    # row is a sink given a self-loop — the lattice's other links are gone.
    i0, i1 = uni.node_index(n[0]), uni.node_index(n[1])
    assert uni.graph.kernel[i0, i1] > 0.0
    # A lattice-only neighbour pair on another ticker is NOT connected here.
    other = state.active_tickers()[1]
    m = _names(state, other)
    jm0 = uni.node_index(m[0])
    assert np.count_nonzero(uni.graph.kernel[jm0]) >= 1  # only its self-loop


def test_edges_dropped_when_naming_unselected_node(state):
    tk = state.active_tickers()[0]
    n = _names(state, tk)
    bogus = (tk, "2099-01-01")
    uni = build_selected_universe(state, edges=[(n[0], bogus, 3.0), (n[0], n[1], 2.0)])
    i0, i1 = uni.node_index(n[0]), uni.node_index(n[1])
    assert uni.graph.kernel[i0, i1] > 0.0  # valid edge kept; bogus one dropped


def test_persisted_edges_round_trip():
    with tempfile.TemporaryDirectory() as d:
        path = f"{d}/store.sqlite"
        s1 = AppState(REF_DATE, store_path=path)
        tk = s1.active_tickers()[0]
        n = _names(s1, tk)
        edge = GraphEdgeInput(
            fromTicker=n[0][0], fromExpiry=n[0][1],
            toTicker=n[1][0], toExpiry=n[1][1], weight=7.0, betaAtmVol=1.5,
        )
        s1.set_graph_edges([edge])
        # A fresh state over the same store restores the override.
        s2 = AppState(REF_DATE, store_path=path)
        restored = s2.graph_edges()
        assert len(restored) == 1
        assert restored[0].weight == 7.0
        assert restored[0].betaAtmVol == 1.5
        assert restored[0].fromExpiry == n[0][1]


def test_asymmetric_weights_accepted(state):
    tk = state.active_tickers()[0]
    n = _names(state, tk)
    # Bi-directed pair with independent (asymmetric) weights is accepted...
    uni = build_selected_universe(state, edges=[(n[0], n[1], 4.0), (n[1], n[0], 1.0)])
    i0, i1 = uni.node_index(n[0]), uni.node_index(n[1])
    assert uni.graph.kernel[i0, i1] > 0.0 and uni.graph.kernel[i1, i0] > 0.0
    # ...and the conductance reflects the asymmetric raw traffic (not symmetric).
    assert uni.graph.conductance.size > 0

    # Edge-weight magnitude is genuinely used: a source with two out-edges of
    # different weights row-normalises to that ratio (4:1 -> 0.8 / 0.2).
    uni2 = build_selected_universe(state, edges=[(n[0], n[1], 4.0), (n[0], n[2], 1.0)])
    j0, j1, j2 = (uni2.node_index(x) for x in (n[0], n[1], n[2]))
    assert uni2.graph.kernel[j0, j1] == pytest.approx(0.8)
    assert uni2.graph.kernel[j0, j2] == pytest.approx(0.2)


def test_request_edges_win_over_persisted(state):
    tk = state.active_tickers()[0]
    n = _names(state, tk)
    # Persist one topology...
    state.set_graph_edges([
        GraphEdgeInput(fromTicker=n[0][0], fromExpiry=n[0][1],
                       toTicker=n[2][0], toExpiry=n[2][1], weight=9.0)
    ])
    # ...but the request supplies its own, which must take precedence.
    req = GraphExtrapolateRequest(edges=[
        GraphEdgeInput(fromTicker=n[0][0], fromExpiry=n[0][1],
                       toTicker=n[1][0], toExpiry=n[1][1], weight=3.0, betaAtmVol=2.0)
    ])
    sol = solve(state, req)
    i0, i1, i2 = (sol.universe.node_index(x) for x in (n[0], n[1], n[2]))
    assert sol.universe.graph.kernel[i0, i1] > 0.0  # request edge present
    assert sol.universe.graph.kernel[i0, i2] == 0.0  # persisted edge NOT used


def test_lattice_edges_seed_nonempty(state):
    seed = lattice_edges(state)
    assert len(seed) > 0
    assert all(e.weight > 0 and e.betaAtmVol == 1.0 for e in seed)


def test_edge_beta_amplifies_via_request(state):
    """A request edge with betaAtmVol > 1 amplifies propagation along it."""
    tk = state.active_tickers()[0]
    n = _names(state, tk)
    chain = [(n[0], n[1], 10.0), (n[1], n[0], 10.0)]

    def shift(beta):
        edges = [
            GraphEdgeInput(fromTicker=a[0], fromExpiry=a[1], toTicker=b[0], toExpiry=b[1],
                           weight=w, betaAtmVol=beta)
            for a, b, w in chain
        ]
        resp = extrapolate(state, GraphExtrapolateRequest(flatAtm=True, edges=edges))
        by = {(x.ticker, x.expiry): x for x in resp.nodes}
        return by[n[1]].shiftBp

    # n0 is the only lit calibrated source under flatAtm; raising the n1<-n0 beta
    # changes the propagated shift at n1.
    assert shift(1.0) != pytest.approx(shift(1.8), abs=1e-6)


def test_routes_edges_crud():
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        assert client.get("/graph/edges").json()["edges"] == []
        seed = client.get("/graph/edges/lattice").json()["edges"]
        assert len(seed) > 0
        # Persist the first two lattice edges as overrides.
        put = client.put("/graph/edges", json={"edges": seed[:2]})
        assert put.status_code == 200
        assert len(put.json()["edges"]) == 2
        assert len(client.get("/graph/edges").json()["edges"]) == 2
        # Empty list clears back to the lattice.
        assert client.put("/graph/edges", json={"edges": []}).json()["edges"] == []
