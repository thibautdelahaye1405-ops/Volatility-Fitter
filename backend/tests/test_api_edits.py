"""Fit-session API tests: quote exclude/include/amend, undo/redo, guards.

Runs in-process over fastapi.testclient like tests/test_api.py, on its own
app instance (module-scoped client) so nothing leaks between test files.
GAMMA is used throughout to stay clear of the tickers other suites fit.

The first five tests form a deliberate narrative on GAMMA's 6M expiry —
baseline -> exclude -> amend -> undo/undo/redo -> reset — and rely on
pytest's definition-order execution; the guard, cross-mode and bad-request
tests each use a different GAMMA expiry so their sessions are independent.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)
N_MODEL_POINTS = 161
TICKER = "GAMMA"


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def expiries(client):
    response = client.get("/universe")
    assert response.status_code == 200
    return [e["expiry"] for e in response.json()["expiries"][TICKER]]


@pytest.fixture(scope="module")
def story(client, expiries):
    """Shared narrative state: the 6M node's baseline and post-edit payloads."""
    expiry = expiries[2]  # 6M — only the narrative tests below touch it
    return {"expiry": expiry, "baseline": client.get(f"/smiles/{TICKER}/{expiry}").json()}


def post_edit(client, expiry: str, payload: dict, fit_mode: str | None = None):
    params = {} if fit_mode is None else {"fit_mode": fit_mode}
    return client.post(f"/smiles/{TICKER}/{expiry}/edits", json=payload, params=params)


def flags(data: dict) -> list[tuple[int, bool, bool]]:
    """The (index, excluded, amended) triple per quote — the edit state."""
    return [(q["index"], q["excluded"], q["amended"]) for q in data["quotes"]]


# -- baseline ------------------------------------------------------------------


def test_baseline_quotes_are_pristine(story):
    base = story["baseline"]
    assert [q["index"] for q in base["quotes"]] == list(range(len(base["quotes"])))
    assert all(not q["excluded"] and not q["amended"] for q in base["quotes"])
    assert base["canUndo"] is False and base["canRedo"] is False


# -- exclude -------------------------------------------------------------------


def test_exclude_wing_quote_refits(client, story):
    base = story["baseline"]
    wing = max(base["quotes"], key=lambda q: abs(q["k"]))["index"]
    response = post_edit(client, story["expiry"], {"action": "exclude", "index": wing})
    assert response.status_code == 200
    data = response.json()

    # The excluded quote is still listed (flagged), the display grid stable.
    assert len(data["quotes"]) == len(base["quotes"])
    assert data["quotes"][wing]["excluded"] is True
    assert sum(q["excluded"] for q in data["quotes"]) == 1
    assert len(data["model"]) == N_MODEL_POINTS
    assert data["kMin"] == base["kMin"] and data["kMax"] == base["kMax"]
    assert data["canUndo"] is True and data["canRedo"] is False

    # Dropping one wing quote barely moves the fit but it must still succeed.
    atm = data["diagnostics"]["atmVol"]
    assert np.isfinite(atm) and abs(atm - base["diagnostics"]["atmVol"]) < 0.005

    story["after_exclude"] = data


# -- amend ---------------------------------------------------------------------


def test_amend_atm_quote_moves_atm_vol(client, story):
    base = story["baseline"]
    atm_quote = min(base["quotes"], key=lambda q: abs(q["k"]))
    new_mid = atm_quote["mid"] + 0.02
    response = post_edit(
        client, story["expiry"], {"action": "amend", "index": atm_quote["index"], "mid": new_mid}
    )
    assert response.status_code == 200
    data = response.json()

    edited = data["quotes"][atm_quote["index"]]
    assert edited["amended"] is True and edited["excluded"] is False
    assert edited["mid"] == pytest.approx(new_mid)
    assert edited["bid"] == atm_quote["bid"] and edited["ask"] == atm_quote["ask"]
    # +200 bp at the ATM quote must pull the fitted ATM vol up by >= 25 bp.
    assert data["diagnostics"]["atmVol"] >= base["diagnostics"]["atmVol"] + 0.0025

    story["after_amend"] = data


# -- undo / redo ---------------------------------------------------------------


def test_undo_twice_then_redo(client, story):
    expiry, base = story["expiry"], story["baseline"]

    one = client.post(f"/smiles/{TICKER}/{expiry}/undo").json()  # undo the amend
    assert flags(one) == flags(story["after_exclude"])
    two = client.post(f"/smiles/{TICKER}/{expiry}/undo").json()  # undo the exclude
    assert two["diagnostics"] == base["diagnostics"]
    assert flags(two) == flags(base)
    assert two["canUndo"] is False and two["canRedo"] is True

    # A further undo on the empty stack is a 200 no-op, not an error.
    again = client.post(f"/smiles/{TICKER}/{expiry}/undo")
    assert again.status_code == 200
    assert again.json()["diagnostics"] == base["diagnostics"]

    redo = client.post(f"/smiles/{TICKER}/{expiry}/redo").json()  # exclude is back
    assert redo["diagnostics"] == story["after_exclude"]["diagnostics"]
    assert flags(redo) == flags(story["after_exclude"])
    assert redo["canUndo"] is True and redo["canRedo"] is True

    redo_two = client.post(f"/smiles/{TICKER}/{expiry}/redo").json()  # amend is back
    assert redo_two["diagnostics"] == story["after_amend"]["diagnostics"]
    assert flags(redo_two) == flags(story["after_amend"])


# -- reset ---------------------------------------------------------------------


def test_reset_clears_edits_and_is_undoable(client, story):
    response = post_edit(client, story["expiry"], {"action": "reset"})
    assert response.status_code == 200
    data = response.json()
    assert all(not q["excluded"] and not q["amended"] for q in data["quotes"])
    assert data["canUndo"] is True
    assert data["diagnostics"] == story["baseline"]["diagnostics"]

    # reset is one undo step: undoing it restores the amended state exactly.
    undone = client.post(f"/smiles/{TICKER}/{story['expiry']}/undo").json()
    assert flags(undone) == flags(story["after_amend"])


# -- minimum-quote guard -------------------------------------------------------


def test_exclusion_guard_protects_minimum_quote_count(client, expiries):
    expiry = expiries[0]  # 1M: shortest quote list, untouched by other tests
    base = client.get(f"/smiles/{TICKER}/{expiry}").json()
    n = len(base["quotes"])
    assert n >= 6

    # Exclude outermost strikes first, alternating wings, down to 5 included.
    order, lo, hi = [], 0, n - 1
    while lo <= hi:
        order.append(lo)
        lo += 1
        if lo <= hi:
            order.append(hi)
            hi -= 1
    for index in order[: n - 5]:
        response = post_edit(client, expiry, {"action": "exclude", "index": index})
        assert response.status_code == 200
    excluded = {q["index"] for q in response.json()["quotes"] if q["excluded"]}
    assert len(excluded) == n - 5

    # One more exclusion would leave 4 quotes: 422 and the session untouched.
    denied = post_edit(client, expiry, {"action": "exclude", "index": order[n - 5]})
    assert denied.status_code == 422
    assert "too few quotes" in denied.json()["detail"]
    after = client.get(f"/smiles/{TICKER}/{expiry}").json()
    assert {q["index"] for q in after["quotes"] if q["excluded"]} == excluded


# -- edits shared across fit modes ---------------------------------------------


def test_edits_are_shared_across_fit_modes(client, expiries):
    expiry = expiries[1]  # 3M
    response = post_edit(client, expiry, {"action": "exclude", "index": 0}, fit_mode="mid")
    assert response.status_code == 200

    other = client.get(f"/smiles/{TICKER}/{expiry}", params={"fit_mode": "bidask"}).json()
    assert other["quotes"][0]["excluded"] is True
    assert other["canUndo"] is True


# -- bad requests --------------------------------------------------------------


def test_bad_edit_requests(client, expiries):
    expiry = expiries[3]  # 1Y, never edited successfully in this suite
    url = f"/smiles/{TICKER}/{expiry}/edits"
    n = len(client.get(f"/smiles/{TICKER}/{expiry}").json()["quotes"])

    assert client.post(url, json={"action": "amend", "index": 0}).status_code == 422
    assert client.post(url, json={"action": "exclude"}).status_code == 422
    assert client.post(url, json={"action": "exclude", "index": n}).status_code == 422
    assert client.post(url, json={"action": "exclude", "index": -1}).status_code == 422
    assert client.post(f"/smiles/NOPE/{expiry}/edits", json={"action": "reset"}).status_code == 404
    assert client.post(f"/smiles/NOPE/{expiry}/undo").status_code == 404
    assert client.post(f"/smiles/NOPE/{expiry}/redo").status_code == 404

    # None of the failed edits left session state behind.
    data = client.get(f"/smiles/{TICKER}/{expiry}").json()
    assert data["canUndo"] is False
    assert all(not q["excluded"] and not q["amended"] for q in data["quotes"])
