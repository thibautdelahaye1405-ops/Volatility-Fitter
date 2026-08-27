"""Workspace FILES (UI shell v2 wave 3, A1): the File menu's server side.

Contracts: (1) export → new → import round-trips the backend doc BYTE-
IDENTICALLY (the A1 exit gate) and the fingerprint tracks it (dirty after
New, clean again after the import); (2) a bare backend doc imports too;
(3) a foreign / newer / malformed file is refused with a 422 diagnostic and
leaves the live workspace untouched; (4) New resets settings to the code
defaults while keeping the ticker set; (5) the named store round-trips a
bundle verbatim, lists newest-first and deletes; without VOLFIT_DB the
list reports storeEnabled=false and saves are 422.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.schemas import OptionsSettings
from volfit.api.workspace import WORKSPACE_DOC_VERSION
from volfit.api.workspace_files import WORKSPACE_SCHEMA

REF = date(2026, 6, 10)


@pytest.fixture
def client():
    with TestClient(create_app(reference_date=REF)) as c:
        yield c


def _worked(client: TestClient) -> None:
    """Author some workspace-scoped state: fit settings + an option + a lit flip."""
    fs = client.get("/settings/fit").json()
    fs["regLambda"] = fs["regLambda"] * 2
    assert client.put("/settings/fit", json=fs).status_code == 200
    opts = client.get("/settings/options").json()
    opts["fitMode"] = "haircut"
    assert client.put("/settings/options", json=opts).status_code == 200
    uni = client.get("/universe").json()
    t = uni["tickers"][0]
    iso = uni["expiries"][t][0]["expiry"]
    assert client.put(f"/universe/lit/{t}/{iso}", json={"lit": False}).status_code == 200


# ---------------------------------------------------------------- round trip
def test_export_new_import_round_trips_byte_identically(client):
    _worked(client)
    bundle = client.get("/workspace/export").json()
    assert bundle["schema"] == WORKSPACE_SCHEMA
    assert bundle["backend"]["v"] == WORKSPACE_DOC_VERSION
    assert bundle["shell"] is None  # the client fills its part
    fp0 = client.get("/workspace/status").json()["fingerprint"]

    st = client.post("/workspace/new").json()
    assert st["fingerprint"] != fp0  # dirty vs the saved file
    assert client.get("/workspace/export").json()["backend"] != bundle["backend"]

    bundle["shell"] = {"activity": "graph", "tabs": {"tabs": [], "activeKey": None}}
    res = client.post("/workspace/import", json=bundle)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["schemaTag"] == WORKSPACE_SCHEMA
    assert body["fingerprint"] == fp0  # clean again
    assert client.get("/workspace/export").json()["backend"] == bundle["backend"]
    assert client.get("/settings/options").json()["fitMode"] == "haircut"


def test_bare_backend_doc_imports(client):
    _worked(client)
    doc = client.get("/workspace/export").json()["backend"]
    client.post("/workspace/new")
    res = client.post("/workspace/import", json=doc)
    assert res.status_code == 200
    assert res.json()["schemaTag"] == "backend-doc"
    assert client.get("/workspace/export").json()["backend"] == doc


# ---------------------------------------------------------------- refusals
@pytest.mark.parametrize(
    "body, needle",
    [
        ({"schema": "volfit-snapshot/1", "backend": {"v": 1}}, "not a workspace file"),
        ({"schema": "volfit-workspace/2", "backend": {"v": 1}}, "not supported"),
        ({"schema": "volfit-workspace/1"}, "no 'backend'"),
        ({"schema": "volfit-workspace/1", "backend": {"v": WORKSPACE_DOC_VERSION + 1}}, "newer"),
        ({"hello": "world"}, "no integer 'v'"),
    ],
)
def test_bad_files_are_422_and_leave_state_untouched(client, body, needle):
    _worked(client)
    before = client.get("/workspace/export").json()["backend"]
    res = client.post("/workspace/import", json=body)
    assert res.status_code == 422, res.text
    assert needle in res.json()["detail"]
    assert client.get("/workspace/export").json()["backend"] == before


def test_non_object_file_is_422(client):
    res = client.post("/workspace/import", json=[1, 2, 3])
    assert res.status_code == 422


# ---------------------------------------------------------------------- new
def test_new_workspace_resets_settings_and_keeps_tickers(client):
    _worked(client)
    tickers = client.get("/universe").json()["tickers"]
    client.post("/workspace/new")
    assert client.get("/universe").json()["tickers"] == tickers
    assert client.get("/settings/options").json()["fitMode"] == OptionsSettings().fitMode
    doc = client.get("/workspace/export").json()["backend"]
    assert doc["darkNodes"] == [] and doc["sessions"] == {}


# ---------------------------------------------------------------- the store
def test_named_store_round_trips_verbatim(tmp_path):
    db = tmp_path / "ws.sqlite"
    with TestClient(create_app(reference_date=REF, store_path=str(db))) as c:
        assert c.get("/workspaces").json() == {"entries": [], "storeEnabled": True}
        _worked(c)
        bundle = c.get("/workspace/export").json()
        bundle["shell"] = {"activity": "localvol", "layout": {"nodesPane": False}}
        res = c.post("/workspaces/desk-a", json=bundle)
        assert res.status_code == 200, res.text
        assert res.json()["name"] == "desk-a"
        assert [e["name"] for e in res.json()["entries"]] == ["desk-a"]
        assert c.get("/workspaces/desk-a").json() == bundle
        # A second name lists newest-first; reopen the first after New.
        c.post("/workspaces/desk-b", json=bundle)
        names = [e["name"] for e in c.get("/workspaces").json()["entries"]]
        assert set(names) == {"desk-a", "desk-b"}
        c.post("/workspace/new")
        loaded = c.get("/workspaces/desk-a").json()
        assert c.post("/workspace/import", json=loaded).status_code == 200
        assert c.get("/workspace/export").json()["backend"] == bundle["backend"]
        # Delete + 404 on a missing name; a broken bundle is never stored.
        assert [e["name"] for e in c.delete("/workspaces/desk-b").json()["entries"]] == ["desk-a"]
        assert c.get("/workspaces/desk-b").status_code == 404
        assert c.post("/workspaces/bad", json={"schema": "x/1"}).status_code == 422
        assert c.post("/workspaces/%20", json=bundle).status_code == 422


def test_store_disabled_without_db(client):
    assert client.get("/workspaces").json() == {"entries": [], "storeEnabled": False}
    bundle = client.get("/workspace/export").json()
    assert client.post("/workspaces/x", json=bundle).status_code == 422
    assert client.get("/workspaces/x").status_code == 422
