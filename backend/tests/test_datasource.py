"""Tests for the Data Source selector: feed_status, registry switching, API.

All offline: providers use injected transports (Yahoo ticker_factory, Massive
http_get) or a tiny stub, so no network / Terminal is touched.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api.app import create_app
from volfit.api.state import AppState, _source_id_of
from volfit.data.massive import MassiveProvider
from volfit.data.provider import OptionChainProvider, SyntheticProvider
from volfit.data.types import ChainSnapshot

REF = date(2026, 6, 13)


# --------------------------------------------------------------- feed_status

def test_synthetic_feed_status_green():
    level, _ = SyntheticProvider(reference_date=REF).feed_status()
    assert level == "green"


def test_yahoo_feed_status_amber_when_reachable():
    from tests.test_yahoo import FakeTicker  # reuse the existing offline fake
    from volfit.data.yahoo import YahooProvider

    provider = YahooProvider(["SPY"], ticker_factory=lambda s: FakeTicker())
    level, detail = provider.feed_status()
    assert level == "amber" and "delayed" in detail


def test_yahoo_feed_status_red_when_unreachable():
    from volfit.data.yahoo import YahooProvider

    def boom(_symbol):
        raise RuntimeError("network down")

    level, _ = YahooProvider(["SPY"], ticker_factory=boom).feed_status()
    assert level == "red"


def test_massive_feed_status_red_without_key():
    level, detail = MassiveProvider(["SPY"], api_key="").feed_status()
    assert level == "red" and "key" in detail


def test_massive_feed_status_amber_with_quotes():
    exp = date.fromordinal(REF.toordinal() + 30).isoformat()
    contracts = {
        "results": [
            {"contract_type": "call", "expiration_date": exp, "strike_price": 500,
             "exercise_style": "american", "ticker": "O:SPY"},
        ],
        "status": "OK",
    }
    snapshot = {
        "results": [
            {"details": {"contract_type": "call", "expiration_date": exp,
                         "strike_price": 500, "exercise_style": "american"},
             "last_quote": {"bid": 1.0, "ask": 1.2}, "day": {"close": 1.1},
             "implied_volatility": 0.2, "open_interest": 3},
        ],
        "status": "OK",
    }

    def http_get(url, params):
        return contracts if "reference" in url else snapshot

    level, detail = MassiveProvider(["SPY"], api_key="k", http_get=http_get).feed_status()
    assert level == "amber" and "delayed" in detail


def test_massive_feed_status_red_on_unauthorized():
    def http_get(url, params):
        return {"status": "NOT_AUTHORIZED", "message": "upgrade your plan"}

    level, _ = MassiveProvider(["SPY"], api_key="k", http_get=http_get).feed_status()
    assert level == "red"


# --------------------------------------------------------------- registry/switch

class _StubProvider(OptionChainProvider):
    """A second source distinct from synthetic, for switch tests."""

    def __init__(self, level: str = "green"):
        self._level = level

    def list_tickers(self):
        return ["SPY"]

    def available_expiries(self, ticker):
        return [date.fromordinal(REF.toordinal() + 30)]

    def fetch_chain(self, ticker, expiries=None):
        return ChainSnapshot(ticker=ticker, spot=100.0, timestamp=None, quotes=[])

    def feed_status(self):
        return (self._level, "stub")


def test_source_id_of():
    assert _source_id_of(SyntheticProvider(reference_date=REF)) == "synthetic"
    assert _source_id_of(MassiveProvider(["SPY"], api_key="k")) == "massive"


def test_set_active_source_switches_and_keeps_watchlist():
    providers = {
        "synthetic": SyntheticProvider(reference_date=REF, tickers=("ALPHA",)),
        "stub": _StubProvider(),
    }
    state = AppState(REF, providers=providers, active_source="synthetic")
    state.snapshot("ALPHA")  # warm a cache entry
    assert "ALPHA" in state._snapshots
    state.set_active_source("stub")
    assert state.active_source == "stub"
    assert state.active_tickers() == ["ALPHA"]  # watchlist kept
    assert state._snapshots == {}  # caches cleared on switch


def test_switch_reresolves_custom_picks_lazily():
    """A switch must acknowledge instantly: it does NO per-ticker fetch, stashing any
    custom expiry picks in _pending_selections. They are re-applied LAZILY on the new
    source the first time the ticker is accessed (intersected with the new ladder)."""
    exp = date.fromordinal(REF.toordinal() + 30)  # the stub's only listed expiry
    state = AppState(REF, providers={"stub": _StubProvider(), "stub2": _StubProvider()},
                     active_source="stub")
    # SPY resolved as a CUSTOM pick on the first source
    state._available["SPY"] = [exp]
    state._selected["SPY"] = [exp]
    state._selection_mode["SPY"] = "custom"

    state.set_active_source("stub2")
    assert not state._available.get("SPY")  # switch did NOT re-resolve eagerly
    assert state._pending_selections.get("SPY") == [exp]  # stashed for lazy re-apply

    # first access resolves on the new source and re-applies the custom pick
    assert state.selected_expiries("SPY") == [exp]
    assert state._selection_mode["SPY"] == "custom"
    assert "SPY" not in state._pending_selections  # consumed


def test_set_active_source_unknown_raises():
    state = AppState(REF, providers={"synthetic": SyntheticProvider(reference_date=REF)})
    with pytest.raises(KeyError):
        state.set_active_source("nope")


def test_set_active_source_noop_when_same():
    state = AppState(REF, providers={"synthetic": SyntheticProvider(reference_date=REF)})
    assert state.set_active_source("synthetic") == "synthetic"


# --------------------------------------------------------------- API

def _multi_app():
    providers = {
        "synthetic": SyntheticProvider(reference_date=REF, tickers=("ALPHA", "BETA")),
        "stub": _StubProvider(level="red"),
    }
    return create_app(reference_date=REF, providers=providers, active_source="synthetic")


def test_get_datasources():
    client = TestClient(_multi_app())
    body = client.get("/datasources").json()
    assert body["active"] == "synthetic"
    by_id = {s["id"]: s for s in body["sources"]}
    assert by_id["synthetic"]["status"] == "green" and by_id["synthetic"]["active"]
    assert by_id["stub"]["status"] == "red" and not by_id["stub"]["active"]


def test_post_datasource_switches():
    client = TestClient(_multi_app())
    body = client.post("/datasource/stub").json()
    assert body["active"] == "stub"
    assert client.get("/datasources").json()["active"] == "stub"


def test_post_datasource_unknown_404():
    client = TestClient(_multi_app())
    assert client.post("/datasource/nope").status_code == 404
