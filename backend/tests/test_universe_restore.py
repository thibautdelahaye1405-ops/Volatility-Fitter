"""On startup, restore the last saved/loaded named universe as the default.

A restart should resume the user's curated universe (tickers + custom expiry
picks) instead of the provider's default watchlist — restored network-free, with
custom picks applied lazily as each ladder resolves.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, universe_service
from volfit.api.state import AppState

REF = date(2026, 6, 10)


@pytest.fixture()
def db() -> str:
    return str(Path(tempfile.mkdtemp()) / "u.sqlite")


def test_startup_restores_last_saved_universe(db):
    state = AppState(REF, store_path=db)
    assert state.active_tickers() == ["ALPHA", "BETA", "GAMMA"]  # provider default
    state.remove_ticker("ALPHA")  # curate -> [BETA, GAMMA]
    pick = state.available_expiries("BETA")[1]
    state.set_expiries("BETA", [pick])  # a custom pick on BETA
    universe_service.save_current(state, "deskA")

    restored = create_app(reference_date=REF, store_path=db).state.volfit
    assert restored.active_tickers() == ["BETA", "GAMMA"]
    assert restored.selection_mode("BETA") == "custom"
    assert restored.selected_expiries("BETA") == [pick]  # lazy custom-pick application


def test_load_makes_a_universe_the_startup_default(db):
    state = AppState(REF, store_path=db)
    state.remove_ticker("GAMMA")
    universe_service.save_current(state, "deskA")  # [ALPHA, BETA]
    state.set_active_tickers(["GAMMA"])
    universe_service.save_current(state, "deskB")  # last saved -> deskB ([GAMMA])

    assert create_app(reference_date=REF, store_path=db).state.volfit.active_tickers() == ["GAMMA"]

    universe_service.load_saved(state, "deskA")  # loading deskA makes it the default
    assert create_app(reference_date=REF, store_path=db).state.volfit.active_tickers() == [
        "ALPHA", "BETA",
    ]


def test_deleting_the_active_universe_falls_back_to_default(db):
    state = AppState(REF, store_path=db)
    state.remove_ticker("ALPHA")
    universe_service.save_current(state, "deskA")
    universe_service.delete_saved(state, "deskA")  # pointer cleared
    # No active pointer -> the provider's default watchlist.
    assert create_app(reference_date=REF, store_path=db).state.volfit.active_tickers() == [
        "ALPHA", "BETA", "GAMMA",
    ]


def test_no_store_keeps_default_watchlist():
    assert create_app(reference_date=REF).state.volfit.active_tickers() == [
        "ALPHA", "BETA", "GAMMA",
    ]


def test_restore_visible_over_http(db):
    with TestClient(create_app(reference_date=REF, store_path=db)) as c:
        c.delete("/universe/tickers/ALPHA")  # curate via the API -> [BETA, GAMMA]
        c.post("/universes/deskA")  # save current
    # A fresh app on the same store serves the restored universe on GET /universe.
    with TestClient(create_app(reference_date=REF, store_path=db)) as c2:
        tickers = c2.get("/universe").json()["tickers"]
    assert tickers == ["BETA", "GAMMA"]
