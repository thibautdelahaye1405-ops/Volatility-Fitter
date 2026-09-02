"""Per-ticker data sources — the multi-source engine (volfit.api.state_sources).

A ticker pinned to a registered source fetches, streams, captures and reports
from THAT source while the rest of the universe follows the default; pins are
workspace-scoped, saved with a named universe, and survive a switch of the
default source. The scheduler serves the streaming tickers from their books
and the others from the Auto-update timer in the same tick.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.datasource import SOURCE_LABELS
from volfit.api.scheduler import Scheduler
from volfit.api.state import AppState, UnknownNodeError
from volfit.data.provider import SyntheticProvider
from volfit.data.store import VolStore

REF = date(2026, 6, 10)


class Scaled(SyntheticProvider):
    """A synthetic feed whose prices are scaled by ``k`` (spot, strikes, quotes
    together — homogeneous, so parity still implies the forward): two of them
    tell apart which source served a chain."""

    def __init__(self, k: float, tickers=("ALPHA", "BETA")):
        super().__init__(reference_date=REF, tickers=tuple(tickers))
        self.k = k

    def fetch_chain(self, ticker, expiries=None, as_of=None):
        snap = super().fetch_chain(ticker, expiries, as_of)
        k = self.k
        quotes = [
            replace(q, strike=q.strike * k,
                    bid=None if q.bid is None else q.bid * k,
                    ask=None if q.ask is None else q.ask * k,
                    last=None if q.last is None else q.last * k)
            for q in snap.quotes
        ]
        return replace(snap, spot=snap.spot * k, quotes=quotes)


class Streaming(Scaled):
    """A streaming-capable feed (the Massive / Bloomberg contract surface)."""

    def __init__(self, k: float, tickers=("ALPHA", "BETA")):
        super().__init__(k, tickers)
        self.streaming = False
        self.subscribed: list[str] = []

    def option_tickers(self, ticker, expiries):
        return [f"O:{ticker}:{self.k:g}"]

    def start_streaming(self, contracts):
        self.streaming = True
        self.subscribed = list(contracts)

    def stop_streaming(self):
        self.streaming = False
        self.subscribed = []

    def is_streaming(self):
        return self.streaming

    def streaming_contracts(self):
        return set(self.subscribed)


def _state(store_path=None, **providers) -> AppState:
    provs = providers or {"cboe": Scaled(1.0), "bloomberg": Scaled(2.0, ("ALPHA", "BETA", "GAMMA"))}
    return AppState(REF, providers=provs, active_source="cboe", store_path=store_path)


def _app(tmp_path=None):
    return create_app(
        reference_date=REF,
        providers={"cboe": Scaled(1.0), "bloomberg": Scaled(2.0, ("ALPHA", "BETA", "GAMMA"))},
        active_source="cboe",
        store_path=str(tmp_path / "u.sqlite") if tmp_path is not None else None,
    )


# --------------------------------------------------------------- resolution

def test_pin_routes_the_ticker_to_its_source():
    state = _state()
    alpha, beta = state.snapshot("ALPHA").spot, state.snapshot("BETA").spot
    assert state.source_of("ALPHA") == "cboe" and state.tickers_of("cboe") == ["ALPHA", "BETA"]
    v0 = state.data_version("ALPHA")
    assert state.set_ticker_source("ALPHA", "bloomberg") == "bloomberg"
    assert state.snapshot("ALPHA").spot == pytest.approx(2.0 * alpha)  # served by the pin
    assert state.snapshot("BETA").spot == pytest.approx(beta)  # the follower stays
    assert state.data_version("ALPHA") == v0 + 1  # its nodes went stale
    assert state.ticker_sources() == {"ALPHA": "bloomberg"}
    assert state.tickers_of("bloomberg") == ["ALPHA"] and state.tickers_of("cboe") == ["BETA"]
    # Back to the default: the chain refetches from it.
    assert state.set_ticker_source("ALPHA", None) == "cboe"
    assert state.snapshot("ALPHA").spot == pytest.approx(alpha)
    assert state.ticker_sources() == {}


def test_pin_validation():
    state = _state()
    with pytest.raises(UnknownNodeError):
        state.set_ticker_source("ALPHA", "nope")
    with pytest.raises(UnknownNodeError):
        state.set_ticker_source("ZZZ", "bloomberg")
    v0 = state.data_version("ALPHA")
    state.set_ticker_source("ALPHA", "cboe")  # pinning to the default changes nothing
    assert state.source_of("ALPHA") == "cboe" and state.data_version("ALPHA") == v0


def test_switching_the_default_source_keeps_the_pins():
    state = AppState(
        REF,
        providers={"cboe": Scaled(1.0), "bloomberg": Scaled(2.0), "yahoo": Scaled(3.0)},
        active_source="cboe",
    )
    alpha, beta = state.snapshot("ALPHA").spot, state.snapshot("BETA").spot  # both on Cboe (1x)
    state.set_ticker_source("ALPHA", "bloomberg")
    state.snapshot("ALPHA")
    va = state.data_version("ALPHA")
    state.set_active_source("yahoo")
    assert state.source_of("ALPHA") == "bloomberg" and state.data_version("ALPHA") == va  # untouched
    assert state.snapshot("ALPHA").spot == pytest.approx(2.0 * alpha)
    assert state.source_of("BETA") == "yahoo"
    assert state.snapshot("BETA").spot == pytest.approx(3.0 * beta)  # the follower moved


def test_remove_ticker_clears_the_pin():
    state = _state()
    state.set_ticker_source("ALPHA", "bloomberg")
    state.remove_ticker("ALPHA")
    assert state.ticker_sources() == {}


def test_captures_are_tagged_with_the_tickers_source(tmp_path):
    db = tmp_path / "cap.sqlite"
    state = AppState(
        REF, providers={"cboe": Scaled(1.0), "yahoo": Scaled(2.0)}, active_source="cboe",
        store_path=str(db),
    )
    state.set_ticker_source("ALPHA", "yahoo")
    state.snapshot("ALPHA")  # a live fetch under the pin: captured as yahoo's
    state.snapshot("BETA")
    with VolStore(db) as store:
        assert [t for t, _i, _ts in store.list_snapshots(source="yahoo")] == ["ALPHA"]
        assert [t for t, _i, _ts in store.list_snapshots(source="cboe")] == ["BETA"]


# ---------------------------------------------------------------- streaming

def test_streaming_follows_the_per_ticker_map():
    cboe, bbg = Streaming(1.0), Streaming(2.0)
    state = AppState(REF, providers={"cboe": cboe, "bloomberg": bbg}, active_source="cboe")
    state.set_ticker_source("ALPHA", "bloomberg")
    state.sync_streaming()
    assert cboe.subscribed == ["O:BETA:1"] and bbg.subscribed == ["O:ALPHA:2"]
    assert state.is_streaming("ALPHA") and state.is_streaming("BETA") and state.is_streaming()
    assert state.streaming_tickers() == ["ALPHA", "BETA"] and state.request_tickers() == []
    state.set_ticker_source("ALPHA", None)  # every ticker back on Cboe: Bloomberg's book closes
    state.sync_streaming()
    assert bbg.streaming is False and set(cboe.subscribed) == {"O:ALPHA:1", "O:BETA:1"}
    state.set_options(state.options().model_copy(update={"autoStream": False}))
    state.sync_streaming()
    assert cboe.streaming is False and not state.is_streaming()


def test_a_book_beside_the_request_path():
    """A pinned streaming name and a request-path name share the universe."""
    state = AppState(REF, providers={"cboe": Scaled(1.0), "bloomberg": Streaming(2.0)}, active_source="cboe")
    state.set_ticker_source("ALPHA", "bloomberg")
    state.sync_streaming()
    assert state.streaming_tickers() == ["ALPHA"] and state.request_tickers() == ["BETA"]
    assert state.is_streaming("ALPHA") and not state.is_streaming("BETA") and state.is_streaming()


def test_scheduler_serves_books_and_the_timer_in_one_tick(monkeypatch):
    from volfit.api import workflow, workflow_fetch

    state = AppState(REF, providers={"cboe": Scaled(1.0), "bloomberg": Streaming(2.0)}, active_source="cboe")
    state.set_ticker_source("ALPHA", "bloomberg")
    state.set_options(state.options().model_copy(update={"autoUpdate": "spot", "autoUpdateSeconds": 5.0, "autoCalibrate": True, "streamRefitSeconds": 2.0}))
    seen: dict[str, list] = {"sync": [], "refit": [], "spots": [], "snapshot": []}
    monkeypatch.setattr(workflow, "sync_market_shifts", lambda s, t=None, *a, **k: seen["sync"].append(t))
    monkeypatch.setattr(workflow, "stream_refit", lambda s, m, t=None, *a, **k: seen["refit"].append(t))
    monkeypatch.setattr(workflow, "fetch_spots", lambda s, t=None, *a, **k: seen["spots"].append(t))
    monkeypatch.setattr(workflow_fetch, "fetch_snapshot", lambda s, t=None, *a, **k: seen["snapshot"].append(t))
    sched = Scheduler(state)
    sched.tick(now=100.0)
    assert seen["sync"] == [["ALPHA"]] and seen["refit"] == [["ALPHA"]]  # the book side
    assert seen["spots"] == [["BETA"]] and seen["snapshot"] == []  # the timer side
    assert sched.seconds_to_next_update(now=100.0) == 5.0 and sched.seconds_to_next_refit(now=100.0) == 2.0
    state.set_options(state.options().model_copy(update={"autoUpdate": "snapshot", "autoUpdateSeconds": 15.0}))
    sched.tick(now=200.0)
    assert seen["snapshot"] == [["BETA"]]


# --------------------------------------------------------------- persistence

def test_workspace_round_trip_keeps_the_pins():
    state = _state()
    state.set_ticker_source("ALPHA", "bloomberg")
    doc = state.workspace_doc()
    assert doc["tickerSources"] == {"ALPHA": "bloomberg"}
    other = _state()
    other.restore_workspace(doc)
    assert other.source_of("ALPHA") == "bloomberg" and other.source_of("BETA") == "cboe"


def test_saved_universe_round_trip_keeps_the_pins(tmp_path):
    from volfit.api import universe_service as svc

    db = tmp_path / "u.sqlite"
    state = _state(store_path=str(db))
    state.add_ticker("GAMMA", "bloomberg")  # only Bloomberg lists it: added AND pinned there
    assert state.ticker_sources() == {"GAMMA": "bloomberg"}
    svc.save_current(state, "mixed")
    fresh = _state(store_path=str(db))
    svc.load_saved(fresh, "mixed")
    assert fresh.active_tickers() == ["ALPHA", "BETA", "GAMMA"]
    assert fresh.ticker_sources() == {"GAMMA": "bloomberg"}
    assert fresh.snapshot("GAMMA").spot > 0.0
    restored = _state(store_path=str(db))
    restored.restore_universe(["ALPHA", "GAMMA"], None, {"GAMMA": "bloomberg", "ALPHA": "gone"})
    assert restored.ticker_sources() == {"GAMMA": "bloomberg"}  # an unregistered source is dropped


# ---------------------------------------------------------------------- API

def test_api_pins_adds_and_searches_per_source(tmp_path):
    with TestClient(_app(tmp_path)) as c:
        u = c.get("/universe").json()
        assert u["defaultSource"] == "cboe" and u["tickerSources"] == {}
        r = c.put("/universe/ALPHA/source", json={"source": "bloomberg"})
        assert r.status_code == 200 and r.json()["tickerSources"] == {"ALPHA": "bloomberg"}
        assert c.put("/universe/ALPHA/source", json={"source": "nope"}).status_code == 404
        assert c.put("/universe/ZZZ/source", json={"source": "bloomberg"}).status_code == 404
        # The selector payload says what each source serves now.
        served = {s["id"]: s["tickers"] for s in c.get("/datasources").json()["sources"]}
        assert served == {"cboe": ["BETA"], "bloomberg": ["ALPHA"]}
        # Search one source's catalogue; add on that source = pinned there.
        hits = c.get("/universe/search", params={"q": "GAMMA", "source": "bloomberg"}).json()["matches"]
        assert [m["symbol"] for m in hits] == ["GAMMA"]
        assert c.get("/universe/search", params={"q": "GAMMA", "source": "nope"}).status_code == 404
        assert c.post("/universe/tickers", json={"symbol": "GAMMA", "source": "nope"}).status_code == 404
        r = c.post("/universe/tickers", json={"symbol": "GAMMA", "source": "bloomberg"})
        assert r.status_code == 200 and r.json()["tickerSources"]["GAMMA"] == "bloomberg"
        assert c.get("/universe").json()["tickerSources"] == {"ALPHA": "bloomberg", "GAMMA": "bloomberg"}
        # The Spot card names the ticker's own source.
        assert c.get("/spot/GAMMA").json()["sourceLabel"] == SOURCE_LABELS.get("bloomberg", "Bloomberg")
        assert c.get("/spot/BETA").json()["sourceLabel"] == SOURCE_LABELS.get("cboe", "Cboe")
        # Unpin through the API.
        assert c.put("/universe/ALPHA/source", json={"source": None}).json()["tickerSources"] == {"GAMMA": "bloomberg"}
