"""V3.2 item 12: GET /smiles/{t}/{e}/compare — side-by-side model comparison.

THE deliverable under test is the read-only guarantee: a compare call moves
NO calibrated pointer, creates NO fit-cache entry, and the committed smile
payload is byte-identical across it (the quality.py no-fit-on-read doctrine).
Plus: the three-family metric rows (finite metrics, per-family validity kind
— LQD density positivity vs SVI/MCS Durrleman g), the (fit_key, model) side
cache (second call = pure cache hits), and the 422/404 error paths.

In-process over fastapi.testclient on the synthetic universe, one app per
module (the test_api.py style).
"""

from datetime import date
from math import isfinite

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)
ALL = "lqd,svi,sigmoid"


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def universe(client):
    response = client.get("/universe")
    assert response.status_code == 200
    return response.json()


def _node(universe, ticker_ix: int = 0, expiry_ix: int = 0) -> tuple[str, str]:
    ticker = universe["tickers"][ticker_ix]
    return ticker, universe["expiries"][ticker][expiry_ix]["expiry"]


def _compare(client, ticker, expiry, **params):
    return client.get(f"/smiles/{ticker}/{expiry}/compare", params=params)


# -- (a) THE LOCK: compare is read-only w.r.t. the committed calibration -------


def test_compare_on_uncalibrated_node_creates_no_fit_state(client, universe):
    """Before ANY smile read of the node: all families fit ad hoc, and still
    no calibrated pointer / fit-cache entry appears (nothing reused)."""
    ticker, expiry = _node(universe, ticker_ix=1)  # untouched by other tests
    state = client.app.state.volfit
    state.snapshot(ticker)  # warm the chain only (ungated read fetch) — no fit
    assert state.get_calibrated_ptr(ticker, expiry, "mid") is None
    fits_before = set(state._fits)

    response = _compare(client, ticker, expiry, models=ALL)
    assert response.status_code == 200
    rows = response.json()["models"]
    assert [r["model"] for r in rows] == ["lqd", "svi", "sigmoid"]
    assert all(r["ok"] for r in rows), [r.get("error") for r in rows]
    assert all(not r["reused"] for r in rows)  # no committed record to reuse

    assert state.get_calibrated_ptr(ticker, expiry, "mid") is None
    assert set(state._fits) == fits_before


def test_compare_moves_no_pointer_and_smile_stays_byte_identical(client, universe):
    ticker, expiry = _node(universe)
    before = client.get(f"/smiles/{ticker}/{expiry}")  # bootstraps the fit
    assert before.status_code == 200

    state = client.app.state.volfit
    fits_before = set(state._fits)
    ptr_before = dict(state._calibrated)

    response = _compare(client, ticker, expiry, models=ALL)
    assert response.status_code == 200

    # No pointer move, no new fit-cache entry — the compare fits live only in
    # its own side cache.
    assert dict(state._calibrated) == ptr_before
    assert set(state._fits) == fits_before

    after = client.get(f"/smiles/{ticker}/{expiry}")
    assert after.status_code == 200
    assert after.content == before.content  # byte-identical committed payload


def test_compare_reuses_fresh_committed_active_family(client, universe):
    """The ACTIVE displayed family (default lqd) reads the committed record
    (reused=True, no fitMs); the other families are ad-hoc fits."""
    ticker, expiry = _node(universe)  # calibrated by the lock test above
    rows = _compare(client, ticker, expiry, models=ALL).json()["models"]
    by_model = {r["model"]: r for r in rows}
    assert by_model["lqd"]["reused"] is True
    assert by_model["lqd"]["fitMs"] is None
    for family in ("svi", "sigmoid"):
        assert by_model[family]["reused"] is False
        assert by_model[family]["fitMs"] is not None and by_model[family]["fitMs"] >= 0.0


def test_band_mode_columns_score_the_band_not_the_mid(client, universe):
    """In a band fit mode the rms AND max columns are distances to the band
    (zero inside): a family sitting inside its bid-ask band reports 0 / 0 — a
    mid-based max would stay strictly positive."""
    ticker, expiry = _node(universe)
    rows = client.get(
        f"/smiles/{ticker}/{expiry}/compare",
        params={"models": "lqd,svi,sigmoid", "fit_mode": "bidask"},
    ).json()["models"]
    assert [r["model"] for r in rows] == ["lqd", "svi", "sigmoid"]
    for row in rows:
        assert row["ok"], row.get("error")
        assert row["maxIvBp"] >= row["rmsBp"] >= 0.0
        if row["rmsBp"] < 1e-9:
            assert row["maxIvBp"] < 1e-9, (row["model"], row["maxIvBp"])
    assert any(r["rmsBp"] < 1e-9 for r in rows)  # the synthetic book's bands are wide


# -- (b) three-family metric rows ----------------------------------------------


def test_three_family_metrics_finite_and_validity_kinds(client, universe):
    ticker, expiry = _node(universe)
    data = _compare(client, ticker, expiry, models=ALL).json()
    assert data["ticker"] == ticker and data["expiry"] == expiry
    assert data["fitMode"] == "mid" and data["activeModel"] == "lqd"
    rows = data["models"]
    assert [r["model"] for r in rows] == ["lqd", "svi", "sigmoid"]
    for row in rows:
        assert row["ok"], row.get("error")
        assert row["label"] in ("LQD", "SVI-JW", "MCS")
        for metric in ("rmsBp", "maxIvBp", "atmVol", "skew",
                       "leeLeft", "leeRight", "varSwapVol"):
            assert row[metric] is not None and isfinite(row[metric]), (row["model"], metric)
        assert row["rmsBp"] >= 0.0 and row["maxIvBp"] >= row["rmsBp"] * 0.0
        assert 0.01 < row["atmVol"] < 2.0
        assert row["nParams"] is not None and row["nParams"] >= 5
        # The display-grid curve: non-empty, finite, positive vols.
        assert len(row["curve"]) > 100
        assert all(p["vol"] > 0.0 and isfinite(p["vol"]) for p in row["curve"])
        assert row["validity"] is not None
    kinds = {r["model"]: r["validity"]["kind"] for r in rows}
    assert kinds == {"lqd": "density", "svi": "g", "sigmoid": "g"}
    for row in rows:  # the synthetic fixture is clean: everything certifies
        assert row["validity"]["certified"] is True, (row["model"], row["validity"])
        assert row["validity"]["minValue"] is not None


def test_models_subset_returns_only_requested(client, universe):
    ticker, expiry = _node(universe)
    rows = _compare(client, ticker, expiry, models="svi").json()["models"]
    assert [r["model"] for r in rows] == ["svi"]


def test_tail_contract_columns(client, universe):
    """Every family declares its structural tail class (volfit.models.wings):
    all three are exponential at the default alpha = 0 settings."""
    ticker, expiry = _node(universe)
    rows = _compare(client, ticker, expiry, models=ALL).json()["models"]
    for row in rows:
        assert row["tailLeft"] == "exponential", row["model"]
        assert row["tailRight"] == "exponential", row["model"]


# -- (c) the (fit_key, model) side cache ----------------------------------------


def test_second_compare_call_hits_cache(client, universe):
    ticker, expiry = _node(universe)
    state = client.app.state.volfit
    first = _compare(client, ticker, expiry, models=ALL).json()
    hits_before = state._compare_cache.hits
    second = _compare(client, ticker, expiry, models=ALL).json()
    assert state._compare_cache.hits == hits_before + 3  # one hit per family
    assert second == first  # identical rows (fitMs included: no refit happened)


def test_cache_is_bounded_fifo(client):
    from volfit.api.compare import CompareCache

    cache = CompareCache(max_entries=2)
    for i in range(4):
        cache.put((("k", i), "lqd"), object())  # type: ignore[arg-type]
    assert len(cache.entries) == 2
    assert (("k", 0), "lqd") not in cache.entries  # oldest evicted first
    assert (("k", 3), "lqd") in cache.entries


# -- (d) error paths -------------------------------------------------------------


def test_unknown_model_csv_is_422(client, universe):
    ticker, expiry = _node(universe)
    assert _compare(client, ticker, expiry, models="lqd,essvi").status_code == 422
    assert _compare(client, ticker, expiry, models="").status_code == 422


def test_unknown_node_is_404(client, universe):
    assert _compare(client, "NOPE", "2026-12-18", models=ALL).status_code == 404
    ticker, _ = _node(universe)
    assert _compare(client, ticker, "2031-01-03", models=ALL).status_code == 404
