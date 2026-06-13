"""API tests: fit-history persistence + GET /history ([REQ 2026-06-12]).

Invariants of the fit time-series scaffold (volfit.api.history):
1. Every slice fit served by the API lands in the store's `fits` table,
   keyed by the SNAPSHOT timestamp (SyntheticProvider stamps 16:00 of the
   reference date) — and exactly once: cache hits and surface refits of the
   same snapshot never duplicate rows.
2. GET /history/{ticker}/{tenor_days} returns one point per snapshot, at
   the listed expiry nearest the tenor (synthetic rungs: 30/91/182/365 d).
3. fit_mode partitions the series; unknown tickers 404; an unconfigured
   store path yields an empty series (200, not 404); a broken store must
   never break fitting (persistence is best-effort by design).
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)
#: SyntheticProvider stamps every chain at 16:00 of the reference date.
SNAPSHOT_TS = "2026-06-10T16:00:00"


@pytest.fixture()
def client(tmp_path):
    # Function-scoped with its own SQLite file: history is on-disk state.
    app = create_app(reference_date=REF_DATE, store_path=tmp_path / "fits.sqlite")
    with TestClient(app) as c:
        yield c


def _expiries(client) -> list[str]:
    """ALPHA's expiry ladder (ISO), nearest first: 30/91/182/365 days out."""
    return [e["expiry"] for e in client.get("/universe").json()["expiries"]["ALPHA"]]


def _history(client, tenor_days: int, fit_mode: str = "mid") -> dict:
    response = client.get(f"/history/ALPHA/{tenor_days}", params={"fit_mode": fit_mode})
    assert response.status_code == 200
    return response.json()


def test_smile_fit_is_persisted_with_sane_fields(client):
    first = _expiries(client)[0]  # the 30d rung
    assert client.get(f"/smiles/ALPHA/{first}").status_code == 200

    hist = _history(client, 30)
    assert (hist["ticker"], hist["tenorDays"], hist["fitMode"]) == ("ALPHA", 30, "mid")
    assert len(hist["points"]) == 1
    pt = hist["points"][0]
    assert pt["ts"] == SNAPSHOT_TS  # keyed by snapshot time, not fit time
    assert pt["expiry"] == first  # nearest-to-30d rung
    assert 0.05 < pt["atmVol"] < 1.0
    assert 0.05 < pt["varSwapVol"] < 1.0
    assert pt["forward"] > 0.0
    assert pt["t"] == pytest.approx(30.0 / 365.0)
    assert 0.0 <= pt["maxIvErrorBp"] < 100.0


def test_cache_hits_and_surface_refits_never_duplicate(client):
    expiries = _expiries(client)
    client.get(f"/smiles/ALPHA/{expiries[0]}")
    client.get(f"/smiles/ALPHA/{expiries[0]}")  # cache hit: no second insert
    assert len(_history(client, 30)["points"]) == 1

    # A full surface fit persists every rung once for the same snapshot …
    assert client.post("/fit/surface", json={"ticker": "ALPHA"}).status_code == 200
    points_30 = _history(client, 30)["points"]
    assert len(points_30) == 1  # still one point per snapshot timestamp
    assert points_30[0]["expiry"] == expiries[0]
    # … and tenor 365 picks the far rung of that same snapshot.
    points_365 = _history(client, 365)["points"]
    assert len(points_365) == 1
    assert points_365[0]["expiry"] == expiries[-1]
    assert points_365[0]["ts"] == SNAPSHOT_TS


def test_fit_mode_partitions_the_series(client):
    first = _expiries(client)[0]
    response = client.get(f"/smiles/ALPHA/{first}", params={"fit_mode": "bidask"})
    assert response.status_code == 200
    assert len(_history(client, 30, fit_mode="bidask")["points"]) == 1
    assert _history(client, 30, fit_mode="mid")["points"] == []


def test_unknown_ticker_is_404(client):
    assert client.get("/history/NOPE/30").status_code == 404


def test_no_store_path_yields_empty_series():
    # Default app (no store_path): fits are cached in memory only and the
    # history endpoint reports an empty series rather than erroring.
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        first = [e["expiry"] for e in c.get("/universe").json()["expiries"]["ALPHA"]][0]
        assert c.get(f"/smiles/ALPHA/{first}").status_code == 200
        response = c.get("/history/ALPHA/30")
        assert response.status_code == 200
        assert response.json()["points"] == []


def test_broken_store_never_breaks_fits(client, monkeypatch):
    import volfit.api.history as history_module

    def boom(*args, **kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(history_module, "VolStore", boom)
    first = _expiries(client)[0]
    # persist_fit swallows the failure into a warning; the fit still serves.
    with pytest.warns(UserWarning, match="persistence failed"):
        assert client.get(f"/smiles/ALPHA/{first}").status_code == 200
