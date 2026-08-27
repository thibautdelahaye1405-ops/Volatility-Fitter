"""Snapshot FILES (UI shell v2 wave 3, A2): quotes + prevailing calibrations as
a file, and the ``file`` data source that serves them back.

Contracts (certification case ``snapshot_roundtrip``): (1) the export embeds
every fetched chain + every committed fit (cached state only); (2) opening
the file in a FRESH backend registers the ``file`` source, switches to it,
re-serves the embedded chains and reinstalls the calibrations so the
Quality report's per-node numbers are BYTE-IDENTICAL to the source app's,
with provenance ``loaded``; (3) a fetch under the file source re-serves the
same chain (a no-op for the data); (4) a second file unions its tickers,
last-loaded-wins per node; (5) foreign / broken files are 422 and leave the
state untouched; (6) nothing fetched → 409 on export.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.snapshot_files import SNAPSHOT_SCHEMA

REF = date(2026, 6, 10)


@pytest.fixture
def source():
    with TestClient(create_app(reference_date=REF)) as c:
        yield c


def _calibrated(client: TestClient, ticker: str, n: int = 2) -> list[str]:
    """Fetch + calibrate the first ``n`` expiries of a ticker; returns the ISOs."""
    uni = client.get("/universe").json()
    isos = [r["expiry"] for r in uni["expiries"][ticker]][:n]
    for iso in isos:
        assert client.get(f"/smiles/{ticker}/{iso}").status_code == 200  # ungated: fits
    return isos


def _quality_rows(client: TestClient, ticker: str) -> dict[str, dict]:
    rep = client.get("/quality").json()
    return {n["expiry"]: n for n in rep["nodes"] if n["ticker"] == ticker and n["hasFit"]}


COMPARE = ("model", "rmsBp", "maxIvBp", "atmVol", "skew", "leeLeft", "leeRight", "nQuotes", "tau")


# ------------------------------------------------------------------ export
def test_export_embeds_chains_and_committed_fits(source):
    isos = _calibrated(source, "ALPHA")
    res = source.post("/snapshot/export", json={"tickers": ["ALPHA"]})
    assert res.status_code == 200, res.text
    assert "attachment" in res.headers["content-disposition"]
    b = res.json()
    assert b["schema"] == SNAPSHOT_SCHEMA
    assert b["manifest"]["tickers"] == ["ALPHA"]
    (t,) = b["tickers"]
    assert t["ticker"] == "ALPHA" and t["spot"] > 0
    assert len(t["chain"]["quotes"]) > 50 and t["chain"]["quoteColumns"][0] == "expiry"
    # The ungated test app fits the whole selected ladder on the first read.
    got = [c["expiry"] for c in t["calibrations"]]
    assert got == sorted(got) and set(isos) <= set(got)
    cal = t["calibrations"][0]
    assert cal["fitMode"] == "mid" and cal["model"] == "lqd" and cal["provenance"] == "fit"
    assert set(cal["lqd"]) == {"L", "R", "a", "alphaL", "alphaR"}
    assert set(cal["diagnostics"]) == {"cost", "nEvaluations", "success", "maxIvError"}


def test_export_without_any_chain_is_409():
    with TestClient(create_app(reference_date=REF, gated=True)) as c:
        assert c.post("/snapshot/export").status_code == 409


# -------------------------------------------------------------- round trip
def test_fresh_backend_reinstalls_calibrations_byte_identically(source):
    isos = _calibrated(source, "ALPHA")
    before = _quality_rows(source, "ALPHA")
    bundle = source.post("/snapshot/export", json={"tickers": ["ALPHA"]}).json()

    with TestClient(create_app(reference_date=REF, gated=True)) as fresh:
        res = fresh.post("/snapshot/import", params={"name": "alpha_0610"}, json=bundle)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["source"] == "file" and body["tickers"] == ["ALPHA"]
        assert body["calibrations"] == len(bundle["tickers"][0]["calibrations"]) and body["failed"] == []
        assert body["label"] == "File · alpha_0610"
        # The file source is active and named after the file.
        ds = fresh.get("/datasources").json()
        assert ds["active"] == "file"
        f = next(s for s in ds["sources"] if s["id"] == "file")
        assert f["label"] == "File · alpha_0610" and f["status"] == "green"
        assert fresh.get("/universe").json()["tickers"] == ["ALPHA"]
        # Byte-identical per-node quality, provenance "loaded".
        after = _quality_rows(fresh, "ALPHA")
        assert set(after) == set(before)
        for iso in isos:
            for k in COMPARE:
                assert after[iso][k] == before[iso][k], (iso, k)
            assert after[iso]["provenance"] == "loaded" and before[iso]["provenance"] == "fit"
        # The smile payload names the loaded model too.
        smile = fresh.get(f"/smiles/ALPHA/{isos[0]}").json()
        assert smile["modelInfo"]["provenance"] == "loaded"
        # A fetch under the file source re-serves the embedded chain.
        assert fresh.post("/fetch/options", json={}).status_code == 200
        again = _quality_rows(fresh, "ALPHA")
        assert set(again) == set(before)
        # Calibrate refits from the embedded quotes: same numbers, provenance "fit".
        assert fresh.get(f"/smiles/ALPHA/{isos[0]}", params={"fit_mode": "mid"}).status_code == 200
        fresh.post("/calibrate")
        rows = _quality_rows(fresh, "ALPHA")
        assert rows[isos[0]]["rmsBp"] == pytest.approx(before[isos[0]]["rmsBp"], abs=1e-9)


def test_second_file_unions_tickers_last_loaded_wins(source):
    _calibrated(source, "ALPHA", 1)
    _calibrated(source, "BETA", 1)
    a = source.post("/snapshot/export", json={"tickers": ["ALPHA"]}).json()
    b = source.post("/snapshot/export", json={"tickers": ["BETA"]}).json()
    with TestClient(create_app(reference_date=REF, gated=True)) as fresh:
        assert fresh.post("/snapshot/import", params={"name": "a"}, json=a).status_code == 200
        assert fresh.post("/snapshot/import", params={"name": "b"}, json=b).status_code == 200
        assert fresh.get("/universe").json()["tickers"] == ["ALPHA", "BETA"]
        f = next(s for s in fresh.get("/datasources").json()["sources"] if s["id"] == "file")
        assert f["label"] == "File · a + b"
        # Re-loading ALPHA with a bumped spot replaces its chain (last wins).
        a2 = dict(a)
        a2["tickers"] = [dict(a["tickers"][0], spot=a["tickers"][0]["spot"] * 1.1, calibrations=[])]
        assert fresh.post("/snapshot/import", params={"name": "a2"}, json=a2).status_code == 200
        assert fresh.app.state.volfit.provider.spot("ALPHA") == pytest.approx(a["tickers"][0]["spot"] * 1.1)
        assert fresh.get(f"/smiles/ALPHA/{a['tickers'][0]['calibrations'][0]['expiry']}").status_code == 200


# ---------------------------------------------------------------- refusals
@pytest.mark.parametrize(
    "body, needle",
    [
        ({"schema": "volfit-workspace/1", "tickers": [{}]}, "not a snapshot file"),
        ({"schema": "volfit-snapshot/2", "tickers": [{}]}, "not supported"),
        ({"schema": "volfit-snapshot/1"}, "no tickers"),
        ({"schema": "volfit-snapshot/1", "tickers": [{"ticker": "X"}]}, "malformed ticker"),
        ({"schema": "volfit-snapshot/1", "tickers": [{"ticker": "X", "chain": {"quoteColumns": ["expiry"], "quotes": [["nope"]]}}]}, "could not be read"),
    ],
)
def test_bad_files_are_422_and_leave_state_untouched(source, body, needle):
    before = source.get("/datasources").json()
    res = source.post("/snapshot/import", json=body)
    assert res.status_code == 422, res.text
    assert needle in res.json()["detail"]
    assert source.get("/datasources").json()["active"] == before["active"]
    assert all(s["id"] != "file" for s in source.get("/datasources").json()["sources"])
