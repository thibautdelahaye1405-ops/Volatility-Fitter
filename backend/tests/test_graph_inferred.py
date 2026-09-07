"""The graph-INFERRED smile on the node views (api/graph_inferred, 2026-09-07).

After a Graph Run every node of the solved universe carries its posterior as
an inferred smile: served on the smile payload (``graphInferred`` + the market
frame's ``inferred`` curve), on the no-fit payload (a dark node's only curve),
transported with the spot exactly like a fit, re-rolled by the stream's
roller — and never a fit (no committed record, no prior). The locks below run
on the synthetic universe with every ticker's prior primed (the graph tests'
fixture), one node darkened.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, graph_inferred, priors, service

REF_DATE = date(2026, 6, 10)


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        state = c.app.state.volfit
        for tk in state.active_tickers():
            snap = priors.capture_snapshot(state, tk, "mid")
            if snap is not None:
                state.set_active_prior(tk, snap, "saved")
        yield c


@pytest.fixture(scope="module")
def nodes(client) -> tuple[str, str, str]:
    """(ticker, dark expiry, lit expiry) — the dark node darkened for the module."""
    state = client.app.state.volfit
    tk = state.active_tickers()[0]
    isos = [e["expiry"] for e in client.get("/universe").json()["expiries"][tk]]
    state.set_node_lit(tk, isos[1], False)
    return tk, isos[1], isos[0]


def _vols(curve) -> np.ndarray:
    return np.array([p["vol"] for p in curve], dtype=float)


def test_no_inferred_smile_before_a_run(client, nodes):
    tk, dark, _lit = nodes
    graph_inferred.clear_run(client.app.state.volfit)
    smile = client.get(f"/smiles/{tk}/{dark}").json()
    assert smile["graphInferred"] is None
    assert smile["market"]["inferred"] is None


def test_run_draws_the_inferred_smile_on_every_node(client, nodes):
    tk, dark, lit = nodes
    state = client.app.state.volfit
    fits_before = set(state._fits)
    assert client.post("/graph/extrapolate", json={}).status_code == 200
    run = graph_inferred.graph_run(state)
    assert run is not None and (tk, dark) in run.nodes and run.fit_mode == "mid"

    smile = client.get(f"/smiles/{tk}/{dark}").json()
    gi = smile["graphInferred"]
    assert gi is not None and gi["runTs"] == run.ts and gi["fitMode"] == "mid"
    assert gi["lit"] is False and gi["calibrated"] is False
    assert gi["priorSource"] == "active_transported"
    assert gi["model"] == "lqd"
    assert len(gi["curve"]) > 100 and np.all(np.isfinite(_vols(gi["curve"]))) and np.all(_vols(gi["curve"]) > 0)
    assert 0.01 < gi["postAtmVol"] < 2.0 and gi["sd"] > 0.0
    # the market frame carries the same curve (no spot shift active)
    assert smile["market"]["inferred"] == gi["curve"]
    # the ATM of the drawn curve reads the posterior ATM (the retarget is exact)
    ks = np.array([p["k"] for p in gi["curve"]])
    assert abs(_vols(gi["curve"])[np.argmin(np.abs(ks))] - gi["postAtmVol"]) < 2e-3

    # a lit, calibrated node has it too — beside its fit — flagged as such
    s2 = client.get(f"/smiles/{tk}/{lit}").json()
    assert s2["graphInferred"] is not None and s2["graphInferred"]["lit"] is True
    assert s2["graphInferred"]["calibrated"] is True and len(s2["model"]) > 0

    # never a fit: the inferred record is not a committed record (the Run
    # itself may bootstrap fits on the ungated test app — those are fits)
    assert all(getattr(r, "provenance", "fit") != "graph" for r in state._fits.values())
    assert len(state._fits) >= len(fits_before)


def test_inferred_smile_transports_with_the_spot(client, nodes):
    tk, dark, _lit = nodes
    state = client.app.state.volfit
    at_rest = client.get(f"/smiles/{tk}/{dark}").json()
    try:
        assert client.put(f"/spot/{tk}", json={"spotReturn": 0.02}).status_code == 200
        moved = client.get(f"/smiles/{tk}/{dark}").json()
        assert moved["forward"] != at_rest["forward"]
        assert moved["graphInferred"]["curve"] != at_rest["graphInferred"]["curve"]
        assert moved["market"]["inferred"] != at_rest["market"]["inferred"]
        assert moved["graphInferred"]["runTs"] == at_rest["graphInferred"]["runTs"]  # same Run
        # the stream's roller rolls the same record by the same shift
        rolled = graph_inferred.inferred_rolled(state, tk, dark, "mid", 0.02)
        assert rolled is not None and len(rolled) == len(at_rest["graphInferred"]["curve"])
        assert [p.vol for p in rolled] != [p["vol"] for p in at_rest["graphInferred"]["curve"]]
        assert graph_inferred.inferred_rolled(state, tk, dark, "mid", 0.0) is not None
    finally:
        assert client.put(f"/spot/{tk}", json={"spotReturn": 0.0}).status_code == 200


def test_no_fit_payload_carries_the_inferred_smile(client, nodes):
    """A truly uncalibrated node (the gated no-fit payload): no model curve,
    the inferred smile is the curve on both the payload and the market frame."""
    tk, dark, _lit = nodes
    state = client.app.state.volfit
    payload = service._no_fit_smile_payload(state, tk, dark, "mid")
    assert payload.hasFit is False and payload.model == []
    assert payload.graphInferred is not None and len(payload.graphInferred.curve) > 100
    assert payload.market is not None and payload.market.inferred is not None
    assert [p.vol for p in payload.market.inferred] == [p.vol for p in payload.graphInferred.curve]


def test_inferred_record_is_never_committed_and_caches_per_run(client, nodes):
    tk, dark, _lit = nodes
    state = client.app.state.volfit
    rec = graph_inferred.inferred_record(state, tk, dark, "mid")
    assert rec is not None and rec.provenance == "graph"
    assert graph_inferred.inferred_record(state, tk, dark, "mid") is rec  # cached
    ts0 = graph_inferred.graph_run(state).ts
    assert client.post("/graph/extrapolate", json={}).status_code == 200  # a new Run
    assert graph_inferred.graph_run(state).ts >= ts0
    assert graph_inferred.inferred_record(state, tk, dark, "mid") is not rec  # rebuilt
    # a node outside the run: nothing
    assert graph_inferred.inferred_record(state, tk, "2031-01-03", "mid") is None
