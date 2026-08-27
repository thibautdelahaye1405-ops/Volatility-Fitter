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

Index-root discovery (workbench follow-on, 2026-08-27): (7) a bundle keyed
under a weekly root (SPXW) is found by its parent root — /universe/search
lists it for "SPX" and adding "SPX" under the file source resolves to SPXW;
(8) the export stamps ``root`` ONLY for known index tickers, so the ALPHA /
BETA bundles are byte-identical to before.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.snapshot_files import SNAPSHOT_SCHEMA
from volfit.data.provider import SyntheticProvider

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


# ------------------------------------------------------------- index roots
TICKER_KEYS = ["ticker", "spot", "timestamp", "exerciseStyle", "chain", "forwards", "calibrations"]


def _renamed(bundle: dict, old: str, new: str) -> dict:
    """The bundle with one ticker entry re-keyed (a file exported from a
    universe that filed the index under its weekly root)."""
    out = dict(bundle)
    out["manifest"] = dict(
        bundle["manifest"], tickers=[new if t == old else t for t in bundle["manifest"]["tickers"]]
    )
    out["tickers"] = [dict(t, ticker=new) if t["ticker"] == old else t for t in bundle["tickers"]]
    return out


def test_non_index_exports_carry_no_root_key(source):
    """Lock: ``root`` appears only for known index roots (volfit.data.roots) —
    the ALPHA / BETA entries keep exactly their historical keys, in order."""
    _calibrated(source, "ALPHA", 1)
    _calibrated(source, "BETA", 1)
    b = source.post("/snapshot/export", json={"tickers": ["ALPHA", "BETA"]}).json()
    assert [t["ticker"] for t in b["tickers"]] == ["ALPHA", "BETA"]
    for t in b["tickers"]:
        assert list(t) == TICKER_KEYS


def test_index_ticker_export_stamps_its_parent_root():
    prov = SyntheticProvider(reference_date=REF, tickers=("SPXW", "BETA"))
    app = create_app(reference_date=REF, gated=True, providers={"synthetic": prov}, active_source="synthetic")
    with TestClient(app) as c:
        # Resolve the expiry ladder first (the UI always loads /universe before
        # a fetch; an unresolved ladder yields an empty, uncached chain).
        assert c.get("/universe").status_code == 200
        assert c.post("/fetch/options", json={}).status_code == 200
        b = c.post("/snapshot/export").json()
        spxw, beta = b["tickers"]
        assert list(spxw) == ["ticker", "root", *TICKER_KEYS[1:]] and spxw["root"] == "SPX"
        assert list(beta) == TICKER_KEYS  # non-index: untouched
        # A malformed root is refused like any other malformed entry.
        bad = dict(b, tickers=[dict(spxw, root=7)])
        assert c.post("/snapshot/import", json=bad).status_code == 422


def test_index_root_alias_finds_the_files_node(source):
    """A file keyed SPXW: searching / adding the parent root SPX lands on it."""
    _calibrated(source, "ALPHA", 1)
    _calibrated(source, "BETA", 1)
    bundle = _renamed(source.post("/snapshot/export", json={"tickers": ["ALPHA", "BETA"]}).json(), "ALPHA", "SPXW")
    with TestClient(create_app(reference_date=REF, gated=True)) as fresh:
        res = fresh.post("/snapshot/import", params={"name": "spx"}, json=bundle)
        assert res.status_code == 200, res.text
        assert fresh.get("/universe").json()["tickers"] == ["SPXW", "BETA"]
        # No 'root' in the doc -> the registry supplies the parent.
        assert fresh.app.state.volfit.provider.roots() == {"SPXW": "SPX", "BETA": "BETA"}
        # The parent root, the sibling itself (any case / spelling) and a prefix all find it.
        for q in ("SPX", "spxw", "^SPX", "SP"):
            hits = fresh.get("/universe/search", params={"q": q}).json()["matches"]
            assert [m["symbol"] for m in hits] == ["SPXW"], q
        hit = fresh.get("/universe/search", params={"q": "SPX"}).json()["matches"][0]
        assert hit["name"] == "SPXW · file (SPX weeklies)" and hit["type"] == "INDEX" and hit["exchange"] == "file"
        beta = fresh.get("/universe/search", params={"q": "bet"}).json()["matches"]
        assert [m["symbol"] for m in beta] == ["BETA"] and beta[0]["name"] == "BETA · file"
        # No free-text echo: a symbol the file lacks is not offered.
        assert fresh.get("/universe/search", params={"q": "NVDA"}).json()["matches"] == []
        # Adding "SPX" resolves to the bundle ticker: idempotent while active ...
        assert fresh.post("/universe/tickers", json={"symbol": "SPX"}).json()["tickers"] == ["SPXW", "BETA"]
        # ... and re-adds the file's node after a removal.
        assert fresh.delete("/universe/tickers/SPXW").json()["tickers"] == ["BETA"]
        assert fresh.post("/universe/tickers", json={"symbol": "SPX"}).json()["tickers"] == ["BETA", "SPXW"]
        assert fresh.get(f"/smiles/SPXW/{bundle['tickers'][0]['calibrations'][0]['expiry']}").status_code == 200
        # A root the file does not carry still 404s.
        assert fresh.post("/universe/tickers", json={"symbol": "NDX"}).status_code == 404
