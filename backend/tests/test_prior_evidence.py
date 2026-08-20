"""V3.9 item 8 — prior-persistence evidence: wire promotions + history + innovations.

Locks:
  * GraphExtrapolateNode.priorAgeDays == the solve's own _prior_age_days value
    (aged prior) and None where the baseline has no snapshot moment;
  * GET /graph/nodes now carries the resolved NodePrior provenance
    (priorSource/priorAsOf/priorAgeDays/transportDistance/priorPrecision) —
    populated for an active prior, None-provenance for a bootstrap baseline;
  * GET /priors reports explicit ageDays/activeAgeDays consistent with
    dataTs/activeDataTs under the same day-resolution convention;
  * GET /priors/history/{ticker}: newest save first, entries[0] == the latest
    snapshot's metadata, 404 unknown ticker, empty list when none saved,
    in-memory (storeless) app serves the latest as a one-entry history;
  * GET /graph/innovations/{ticker} returns exactly what
    record_graph_innovations stored (vol -> bp is the only wire transform);
  * PriorNode / PriorSurfaceSnapshot old wire key sets byte-identical
    (the 2026-08-13a wire rule — evidence promotions never touch snapshots).

All new reads are poll-safe: nothing here fits or solves on read.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, priors
from volfit.api.graph_extrapolation import _prior_age_days
from volfit.api.schemas_prior import PriorNode, PriorSurfaceSnapshot

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"
#: Three calendar days before REF_DATE — the aged-prior data moment.
STALE_TS = "2026-06-07T20:00:00"


# ------------------------------------------------------------- graph wires
@pytest.fixture(scope="module")
def gclient():
    """Module app with a 3-day-old active prior on ALPHA ONLY: ALPHA nodes
    resolve from the aged snapshot (priorAsOf set), the other tickers fall
    through to today_bootstrap (no prior moment) — both provenance branches
    are on every payload."""
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        state = c.app.state.volfit
        snap = priors.capture_snapshot(state, TICKER, "mid")
        assert snap is not None
        state.set_active_prior(
            TICKER, snap.model_copy(update={"dataTs": STALE_TS}), "saved"
        )
        yield c


def test_extrapolate_emits_prior_age_days(gclient):
    """priorAgeDays rides the solve wire and equals _prior_age_days exactly."""
    state = gclient.app.state.volfit
    nodes = gclient.post("/graph/extrapolate", json={}).json()["nodes"]
    assert len(nodes) == 12  # 3 tickers x 4 selected expiries
    seen_aged = seen_bare = False
    for n in nodes:
        if n["priorAsOf"] is not None:
            assert n["priorAgeDays"] == float(_prior_age_days(state, n["priorAsOf"]))
            seen_aged = True
        else:
            assert n["priorAgeDays"] is None  # nothing to age (bootstrap/flat)
            seen_bare = True
    assert seen_aged and seen_bare
    for n in nodes:
        if n["ticker"] == TICKER:
            assert n["priorAsOf"] == STALE_TS
            assert n["priorAgeDays"] == 3.0


def test_graph_nodes_carry_prior_provenance(gclient):
    """GET /graph/nodes no longer drops the resolved NodePrior's provenance."""
    nodes = gclient.get("/graph/nodes").json()["nodes"]
    alpha = [n for n in nodes if n["ticker"] == TICKER]
    others = [n for n in nodes if n["ticker"] != TICKER]
    assert alpha and others
    for n in alpha:
        assert n["priorSource"] in ("active_transported", "nearest_expiry_transported")
        assert n["priorAsOf"] == STALE_TS
        assert n["priorAgeDays"] == 3.0
        # Captured and served in the same session: the forward has not moved.
        assert n["transportDistance"] == pytest.approx(0.0, abs=1e-12)
        assert len(n["priorPrecision"]) == 3
        assert all(p > 0.0 for p in n["priorPrecision"])
    for n in others:  # no active prior: bootstrap baseline, None provenance
        assert n["priorSource"] == "today_bootstrap"
        assert n["priorAsOf"] is None
        assert n["priorAgeDays"] is None
        assert n["transportDistance"] == 0.0
        assert len(n["priorPrecision"]) == 3


# --------------------------------------------------------- /priors + history
@pytest.fixture()
def db_path() -> str:
    return str(Path(tempfile.mkdtemp()) / "evidence.sqlite")


@pytest.fixture()
def client(db_path):
    with TestClient(create_app(reference_date=REF_DATE, store_path=db_path)) as c:
        c.get("/universe")  # warm the universe
        yield c


def _first_iso(client) -> str:
    return client.get("/universe").json()["expiries"][TICKER][1]["expiry"]


def _status(client) -> dict:
    return {t["ticker"]: t for t in client.get("/priors").json()["tickers"]}


def test_priors_status_reports_ages(client):
    """ageDays/activeAgeDays are day-resolution ages of dataTs/activeDataTs
    against the reference date (the _prior_age_days convention, floored 0)."""
    client.get(f"/smiles/{TICKER}/{_first_iso(client)}")  # bootstrap a calibration
    client.post("/priors/save-all")
    row = _status(client)[TICKER]
    # save-all's dataTs is the live wall clock — never negative, clamped to 0.
    assert row["ageDays"] == 0.0
    assert row["activeSource"] is None and row["activeAgeDays"] is None

    # Backdate the latest snapshot 3 days: the age must follow the dataTs.
    state = client.app.state.volfit
    stale = state.latest_prior_snapshot(TICKER).model_copy(update={"dataTs": STALE_TS})
    state.save_prior_snapshot(stale)
    row = _status(client)[TICKER]
    assert row["dataTs"] == STALE_TS
    assert row["ageDays"] == float((REF_DATE - date(2026, 6, 7)).days) == 3.0

    client.post("/priors/fetch")  # the saved snapshot becomes the active prior
    row = _status(client)[TICKER]
    assert row["activeSource"] == "saved"
    assert row["activeDataTs"] == STALE_TS
    assert row["activeAgeDays"] == 3.0


def test_priors_history_ordering_latest_and_404(client):
    # Nothing saved yet: an empty history, not an error.
    fresh = client.get(f"/priors/history/{TICKER}")
    assert fresh.status_code == 200
    assert fresh.json()["entries"] == []

    iso = _first_iso(client)
    client.get(f"/smiles/{TICKER}/{iso}")
    client.post("/priors/save-all")
    client.post("/priors/save-all")  # a second save: history keeps both

    response = client.get(f"/priors/history/{TICKER}")
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == TICKER
    entries = body["entries"]
    assert len(entries) == 2
    assert entries[0]["savedTs"] >= entries[1]["savedTs"]  # newest save first

    # Lock: history[0] IS the latest snapshot's metadata (GET /priors row).
    row = _status(client)[TICKER]
    assert entries[0]["dataTs"] == row["dataTs"]
    assert entries[0]["savedTs"] == row["savedTs"]
    assert entries[0]["nodeCount"] == row["nodeCount"]
    assert entries[0]["asOfLabel"] == row["asOfLabel"]

    # Unknown ticker: 404, never an empty 200 (a typo must be loud).
    assert client.get("/priors/history/NOPE").status_code == 404


def test_priors_history_without_store_serves_latest_only():
    """Storeless (in-memory) app: the latest snapshot is the whole history —
    the history[0]==latest lock holds in both persistence regimes."""
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        c.get(f"/smiles/{TICKER}/{_first_iso(c)}")
        c.post("/priors/save-all")
        entries = c.get(f"/priors/history/{TICKER}").json()["entries"]
        row = _status(c)[TICKER]
        assert len(entries) == 1
        assert entries[0]["savedTs"] == row["savedTs"]
        assert entries[0]["dataTs"] == row["dataTs"]
        assert entries[0]["nodeCount"] == row["nodeCount"]
        assert entries[0]["asOfLabel"] == row["asOfLabel"]


# ------------------------------------------------------------- innovations
def test_graph_innovations_returns_exactly_what_was_recorded():
    """The endpoint serves the idio store verbatim: write via the state API,
    read via HTTP — vol -> bp (x 1e4) is the only wire transform."""
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        c.get("/universe")
        state = c.app.state.volfit
        isos = [e.isoformat() for e in sorted(state.forwards(TICKER))][:2]
        state.record_graph_innovations(
            {(TICKER, isos[0]): 0.0025, (TICKER, isos[1]): -0.001}
        )

        body = c.get(f"/graph/innovations/{TICKER}").json()
        day = REF_DATE.isoformat()
        assert body["ticker"] == TICKER
        assert body["series"] == [
            {"day": day, "expiry": isos[0], "innovationBp": 0.0025 * 1e4},
            {"day": day, "expiry": isos[1], "innovationBp": -0.001 * 1e4},
        ]

        # Idempotent store: a re-record of the same key overwrites, no new row.
        state.record_graph_innovations({(TICKER, isos[0]): 0.004})
        series = c.get(f"/graph/innovations/{TICKER}").json()["series"]
        assert len(series) == 2
        assert series[0] == {"day": day, "expiry": isos[0], "innovationBp": 0.004 * 1e4}

        # Nothing recorded (any other ticker): an empty series, not an error.
        other = c.get("/graph/innovations/OMEGA").json()
        assert other["series"] == []


# ------------------------------------------------------------ wire identity
def test_prior_wire_key_sets_byte_identical():
    """The 2026-08-13a wire rule: the evidence promotions add NOTHING to the
    persisted snapshot documents — PriorNode / PriorSurfaceSnapshot keep the
    exact historical key set (old stored priors load and re-save unchanged)."""
    assert set(PriorNode.model_fields) == {
        "expiry", "tCal", "tau", "forward", "discount", "model", "lqd",
        "alphaL", "alphaR", "display", "atmVol", "skew",
    }
    assert set(PriorSurfaceSnapshot.model_fields) == {
        "ticker", "dataTs", "savedTs", "asOfLabel", "refSpot", "market",
        "events", "nodes", "lvSurface",
    }
