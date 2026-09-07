"""The ANCHORING AXIS (api/compare_anchoring, 2026-09-07): shadow fits of the
displayed family that differ from production in the anchoring blocks alone —
free / + prior / + filter — derived from the live Options by subtraction.

THE LOCKS:
  * availability by INPUT existence: ``free`` always; ``prior`` once an
    active prior node exists under a calibration-prior mode; ``filter`` once
    a kept filter state has a prediction (mode overlay OR active);
  * the production cell follows the live mode (prior under overlay/off with a
    prior, filter under active) and its row is the displayed family's plain
    row — reused, never duplicated, tagged;
  * a shadow fit is READ-ONLY: no calibrated-pointer move, no fit-cache
    entry, no filter-state update, and the committed smile payload stays
    byte-identical across it;
  * the pull columns read against the free cell (which reads zero);
  * the smile / density switch draws the shadow cell (tagged in modelInfo),
    the production name / an unavailable cell falls back to production, an
    unknown name is a 422.

In-process over fastapi.testclient on the synthetic universe (the
test_api_compare.py style); the module walks ONE node through the modes in
order, so the tests below are sequential by design.
"""

from datetime import date
from math import isfinite

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.compare_anchoring import ANCHORING_CELLS, parse_anchoring

REF_DATE = date(2026, 6, 10)


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def node(client) -> tuple[str, str]:
    universe = client.get("/universe").json()
    ticker = universe["tickers"][0]
    return ticker, universe["expiries"][ticker][1]["expiry"]


def _compare(client, node, **params):
    ticker, expiry = node
    return client.get(f"/smiles/{ticker}/{expiry}/compare", params={"models": "lqd", **params})


def _smile(client, node, **params):
    ticker, expiry = node
    return client.get(f"/smiles/{ticker}/{expiry}", params=params)


def _set_options(client, **update):
    state = client.app.state.volfit
    state.set_options(state.options().model_copy(update=update))


def _curve(payload) -> list[float]:
    return [p["vol"] for p in payload["model"]]


# -- parsing ---------------------------------------------------------------------


def test_parse_anchoring_wire_order_and_422_name():
    assert parse_anchoring("") == ()
    assert parse_anchoring("prior, free,free") == ("free", "prior")
    assert parse_anchoring("filter") == ("filter",)
    with pytest.raises(ValueError):
        parse_anchoring("free,bogus")
    assert ANCHORING_CELLS == ("free", "prior", "filter")


# -- (a) a plain node: only the free cell, and it IS production -------------------


def test_plain_node_free_is_production(client, node):
    _set_options(client, priorPersistenceMode="hybrid", observationFilterMode="off")
    smile = _smile(client, node).json()
    info = smile["anchoring"]
    assert info["available"] == ["free"] and info["production"] == "free"
    assert info["family"] == "lqd" and info["priorMode"] == "hybrid" and info["filterMode"] == "off"
    assert "prior" in info["notes"] and "filter" in info["notes"]
    assert smile["modelInfo"]["anchoring"] is None

    data = _compare(client, node, anchoring="free,prior,filter").json()
    assert data["anchoring"]["requested"] == ["free", "prior", "filter"]
    rows = data["models"]
    assert [r["model"] for r in rows] == ["lqd"]  # free IS the plain row; the others unavailable
    assert rows[0]["anchoring"] == "free" and rows[0]["reused"] is True
    assert rows[0]["pullAtmBp"] == 0.0 and rows[0]["pullCurveBp"] == 0.0 and rows[0]["pullSkew"] == 0.0


def test_unknown_cell_is_422_and_production_name_is_plain(client, node):
    assert _smile(client, node, anchoring="bogus").status_code == 422
    assert _compare(client, node, anchoring="free,bogus").status_code == 422
    plain = _smile(client, node)
    assert _smile(client, node, anchoring="production").content == plain.content
    assert _smile(client, node, anchoring="prior").content == plain.content  # unavailable -> production


# -- (b) with an active prior: the prior cell exists and is production ------------


def test_saving_one_node_makes_it_the_prior_at_once(client, node):
    """ONE PRIOR PER NODE, ACTIVE ON SAVE: a per-node save lights "+ Prior"
    and, under a calibration-prior mode, IS production — no Fetch step."""
    ticker, expiry = node
    state = client.app.state.volfit
    assert state.active_prior(ticker) is None
    res = client.post(f"/smiles/{ticker}/{expiry}/prior").json()
    assert res["saved"] is True and res["activeNodes"] == 1 and res["fitMode"] == "mid"
    assert state.active_prior_source(ticker) == "saved"
    info = _smile(client, node).json()["anchoring"]
    assert info["available"] == ["free", "prior"] and info["production"] == "prior"
    assert "prior" not in info["notes"] and "prior" not in info["preview"]
    rows = _compare(client, node, anchoring="free").json()["models"]
    assert [r["anchoring"] for r in rows] == ["prior", "free"]
    assert rows[0]["reused"] is True and rows[1]["ok"] and rows[1]["pullCurveBp"] is not None


def test_prior_cell_appears_after_fetch_and_is_production(client, node):
    """Save priors (all) + Fetch keep the same answer — Fetch is idempotent
    on a saved prior."""
    assert client.post("/priors/save-all").status_code == 200
    assert client.post("/priors/fetch").status_code == 200
    smile = _smile(client, node).json()
    info = smile["anchoring"]
    assert info["available"] == ["free", "prior"] and info["production"] == "prior"
    assert "prior" not in info["notes"] and "prior" not in info["preview"]


def test_shadow_free_fit_is_read_only_and_pulls_against_free(client, node):
    ticker, expiry = node
    state = client.app.state.volfit
    before = _smile(client, node)
    fits_before = set(state._fits)
    ptr_before = dict(state._calibrated)

    data = _compare(client, node, anchoring="free,prior").json()
    rows = data["models"]
    assert [r["anchoring"] for r in rows] == ["prior", "free"]  # production row first, once
    prod, free = rows
    assert prod["reused"] is True and prod["fitMs"] is None
    assert free["reused"] is False and free["fitMs"] is not None and free["fitMs"] >= 0.0
    assert free["ok"] and prod["ok"]
    for row in rows:
        for col in ("pullAtmBp", "pullSkew", "pullCurveBp"):
            assert row[col] is not None and isfinite(row[col]), (row["anchoring"], col)
    assert free["pullAtmBp"] == 0.0 and free["pullCurveBp"] == 0.0
    assert free["pullCurveBp"] >= 0.0 and prod["pullCurveBp"] >= 0.0
    assert len(free["curve"]) == len(prod["curve"])

    # read-only: no pointer move, no fit-cache entry, byte-identical smile
    assert dict(state._calibrated) == ptr_before
    assert set(state._fits) == fits_before
    assert _smile(client, node).content == before.content

    # second call: pure cache hits for the shadow cell
    hits = state._compare_cache.hits
    again = _compare(client, node, anchoring="free,prior").json()
    assert again["models"] == rows
    assert state._compare_cache.hits > hits

    # the plain (production) row joins the pull set whenever ANY cell is
    # asked — even when the production cell itself is not requested
    only_free = _compare(client, node, anchoring="free").json()["models"]
    assert [r["anchoring"] for r in only_free] == ["prior", "free"]
    assert only_free[0]["pullCurveBp"] is not None and only_free[1]["pullCurveBp"] == 0.0


def test_smile_and_density_switch_draw_the_shadow_cell(client, node):
    plain = _smile(client, node).json()
    free = _smile(client, node, anchoring="free").json()
    assert free["modelInfo"]["anchoring"] == "free"
    assert free["anchoring"] == plain["anchoring"]  # the axis report is the node's
    assert free["quotes"] == plain["quotes"]  # the quotes stay the node's
    assert free["stale"] == plain["stale"]
    assert len(free["model"]) == len(plain["model"])
    # the drawn curve is the shadow's, in BOTH frames
    assert free["market"]["model"] == free["model"]
    assert free["calib"]["model"] == free["model"]
    assert free["diagnostics"]["atmVolStd"] is None  # no side channel for a shadow
    # the production cell by name is the plain payload
    assert _smile(client, node, anchoring="prior").json() == plain
    ticker, expiry = node
    d_plain = client.get(f"/smiles/{ticker}/{expiry}/density").json()
    d_free = client.get(f"/smiles/{ticker}/{expiry}/density", params={"anchoring": "free"}).json()
    assert d_free["prior"] == d_plain["prior"]
    assert len(d_free["current"]["x"]) == len(d_plain["current"]["x"]) > 0


# -- (c) filter overlay: the filter cell is a PREVIEW, production stays prior ---


def test_filter_cell_under_overlay_previews_without_touching_state(client, node):
    ticker, expiry = node
    state = client.app.state.volfit
    _set_options(client, observationFilterMode="overlay")
    # off -> overlay busts no fit cache (state.set_options): the state is
    # seeded at the next genuine calibration — a new observation of the chain.
    state.bump_data_version(ticker)
    smile = _smile(client, node).json()  # refit + commit seeds the filter state
    info = smile["anchoring"]
    assert info["available"] == ["free", "prior", "filter"], info
    assert info["production"] == "prior" and info["filterMode"] == "overlay"
    assert "active mode" in info["preview"]["filter"]  # the overlay cell is a preview

    holder = state.filter_node((ticker, expiry, "mid"))
    assert holder is not None
    data = _compare(client, node, anchoring="filter").json()
    rows = data["models"]
    assert [r["anchoring"] for r in rows] == ["prior", "filter"]
    filt = rows[1]
    assert filt["ok"] and filt["reused"] is False and filt["fitMs"] is not None
    assert filt["pullCurveBp"] is not None and isfinite(filt["pullCurveBp"])
    assert state.filter_node((ticker, expiry, "mid")) is holder  # no state update
    assert _smile(client, node, anchoring="filter").json()["modelInfo"]["anchoring"] == "filter"


# -- (d) filter active: the filter cell IS production, prior is the full body ---


def test_filter_active_production_is_filter_and_prior_is_shadow(client, node):
    _set_options(client, observationFilterMode="active")
    smile = _smile(client, node).json()  # MAP refit from the kept state
    info = smile["anchoring"]
    assert info["production"] == "filter" and info["filterMode"] == "active"
    assert info["available"] == ["free", "prior", "filter"]

    data = _compare(client, node, anchoring="prior,filter,free").json()
    rows = data["models"]
    assert [r["anchoring"] for r in rows] == ["filter", "free", "prior"]
    assert rows[0]["reused"] is True
    assert rows[2]["reused"] is False and rows[2]["ok"]
    assert all(r["pullCurveBp"] is not None for r in rows)


# -- (e) persistence mode off: "+ Prior" previews hybrid, production is free --


def test_mode_off_prior_cell_previews_hybrid(client, node):
    _set_options(client, priorPersistenceMode="off", observationFilterMode="off")
    info = _smile(client, node).json()["anchoring"]
    assert "prior" in info["available"] and info["production"] == "free"
    assert "hybrid" in info["preview"]["prior"] and "prior" not in info["notes"]
    assert "filter" in info["notes"] and "Overlay" in info["notes"]["filter"]
    rows = _compare(client, node, anchoring="prior,free").json()["models"]
    assert [r["anchoring"] for r in rows] == ["free", "prior"]
    assert rows[0]["reused"] is True and rows[1]["ok"] and rows[1]["reused"] is False
    _set_options(client, priorPersistenceMode="hybrid")


# -- (f) the model chip under a spot transport --------------------------------


def test_model_chip_keeps_its_family_under_a_spot_transport(client, node):
    """A moved spot wraps the displayed slice in a transport overlay; the chip
    must still name the calibrated family + degree (it used to say SVI-JW)."""
    ticker, expiry = node
    plain = _smile(client, node).json()
    assert plain["modelInfo"]["id"] == "lqd" and plain["modelInfo"]["params"][0]["label"] == "Degree N"
    assert client.put(f"/spot/{ticker}", json={"spotReturn": 0.02}).status_code == 200
    try:
        moved = _smile(client, node).json()
        assert moved["forward"] != plain["forward"]  # the transport is on
        assert moved["modelInfo"]["id"] == "lqd" and moved["modelInfo"]["label"] == "LQD"
        assert moved["modelInfo"]["params"] == plain["modelInfo"]["params"]
        # the axis report and the shadow switch survive the transport
        assert moved["anchoring"]["available"] == plain["anchoring"]["available"]
        free = _smile(client, node, anchoring="free").json()
        assert free["modelInfo"]["anchoring"] == "free" and free["modelInfo"]["id"] == "lqd"
    finally:
        assert client.put(f"/spot/{ticker}", json={"spotReturn": 0.0}).status_code == 200


# -- (g) the prior routes honour the session fit mode -------------------------


def test_save_all_snapshots_the_requested_fit_mode(client, node):
    """A haircut session must snapshot its haircut fits (the route's default
    is mid — the top bar passes fitMode)."""
    ticker, expiry = node
    assert _smile(client, node, fit_mode="haircut").status_code == 200
    res = client.post("/priors/save-all", params={"fitMode": "haircut"}).json()
    assert ticker in res["tickers"] and res["nodes"] >= 1
