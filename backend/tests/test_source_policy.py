"""The "auto" source pin (volfit.api.source_policy + state_sources).

A ticker pinned to ``auto`` fetches from the fastest registered source whose
cached status is green / amber and that can serve it, ranked by the EWMA of
the measured live chain-fetch wall (seeded Cboe → Massive → Nasdaq → Yahoo →
Bloomberg). The pick is remembered and re-ranked at Fetch time only; a
change drops the ticker's caches like a re-pin and is reported beside the
pin in ``GET /universe``. All offline.
"""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.source_policy import (
    AUTO_SOURCE,
    EWMA_ALPHA,
    SEED_WALL_S,
    SourcePolicy,
    can_serve,
)
from volfit.api.state import AppState, UnknownNodeError
from volfit.data.provider import SyntheticProvider

REF = date(2026, 6, 10)


class Scaled(SyntheticProvider):
    """A synthetic feed whose prices are scaled by ``k`` — tells sources apart."""

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


def _providers():
    return {"bloomberg": Scaled(2.0), "cboe": Scaled(1.0), "yahoo": Scaled(3.0)}


def _state(store_path=None) -> AppState:
    return AppState(REF, providers=_providers(), active_source="yahoo", store_path=store_path)


def _status(state: AppState, **levels: str) -> None:
    """Seed the status CACHE (what an auto pin reads — never a probe)."""
    for sid, level in levels.items():
        state._status_cache[sid] = (time.monotonic(), (level, "seeded"))


# --------------------------------------------------------------- the policy

def test_ranking_follows_status_then_wall_then_registration_order():
    providers = {"yahoo": Scaled(3.0), "cboe": Scaled(1.0), "bloomberg": Scaled(2.0), "synthetic": Scaled(4.0)}
    green = {sid: ("green", "") for sid in providers}
    pol = SourcePolicy()
    # Seeded: Cboe → Yahoo → Bloomberg; the unseeded synthetic source last.
    assert pol.rank(providers, green, "ALPHA") == ["cboe", "yahoo", "bloomberg", "synthetic"]
    # A red source is never picked; amber (a delayed feed, a pending probe) is.
    statuses = dict(green, cboe=("red", "down"), yahoo=("amber", "delayed"))
    assert pol.rank(providers, statuses, "ALPHA") == ["yahoo", "bloomberg", "synthetic"]
    # Measured walls outrank the seed: Bloomberg turns out fastest today.
    for _ in range(20):
        pol.record_wall("bloomberg", 0.2)
    assert pol.rank(providers, green, "ALPHA")[0] == "bloomberg"
    # Nothing eligible: the caller's fallback (the universe's default).
    assert pol.choose(providers, {sid: ("red", "") for sid in providers}, "ALPHA", "yahoo") == "yahoo"
    # Registration order breaks a tie on equal walls.
    tie = SourcePolicy()
    for sid in providers:
        tie.record_wall(sid, 1.0)
        tie._walls[sid] = 1.0
    assert tie.rank(providers, green, "ALPHA") == list(providers)


def test_ewma_starts_from_the_seed_and_ignores_garbage():
    pol = SourcePolicy()
    assert pol.wall("cboe") == SEED_WALL_S["cboe"] and pol.walls() == {}
    pol.record_wall("cboe", 1.0)
    assert pol.wall("cboe") == pytest.approx((1 - EWMA_ALPHA) * SEED_WALL_S["cboe"] + EWMA_ALPHA * 1.0)
    pol.record_wall("cboe", float("nan"))
    pol.record_wall("cboe", -1.0)
    assert pol.walls() == {"cboe": pytest.approx(0.86)}


def test_can_serve_is_a_cheap_capability_check():
    listed = Scaled(1.0, ("ALPHA",))
    assert can_serve("synthetic", listed, "ALPHA")  # listed by the provider
    assert not can_serve("synthetic", listed, "ZZZ")  # a fixed universe: only when listed
    assert not can_serve("eurex", listed, "ZZZ")  # a regional venue: only its listing
    assert can_serve("yahoo", listed, "ZZZ")  # an open-universe live feed takes any symbol
    listed.accepts_any_symbol = True  # a provider may say so itself
    assert can_serve("synthetic", listed, "ZZZ")


# ------------------------------------------------------------- the state

def test_auto_pin_resolves_to_the_fastest_green_source_and_is_reported():
    state = _state()
    _status(state, bloomberg="green", cboe="green", yahoo="green")
    alpha = state.snapshot("ALPHA").spot  # on the default (yahoo, 3x)
    v0 = state.data_version("ALPHA")
    assert state.set_ticker_source("ALPHA", AUTO_SOURCE) == "cboe"  # the seed's fastest
    assert state.ticker_sources() == {"ALPHA": AUTO_SOURCE}
    assert state.source_of("ALPHA") == "cboe" and state.provider_for("ALPHA") is state._providers["cboe"]
    assert state.resolved_sources() == {"ALPHA": "cboe", "BETA": "yahoo"}
    assert state.data_version("ALPHA") == v0 + 1  # re-pinned: its nodes went stale
    assert state.snapshot("ALPHA").spot == pytest.approx(alpha / 3.0)  # served by Cboe (1x)
    assert state.tickers_of("cboe") == ["ALPHA"] and state.tickers_of("yahoo") == ["BETA"]
    with pytest.raises(UnknownNodeError):
        state.set_ticker_source("ALPHA", "nope")  # validation unchanged


def test_a_red_source_is_skipped_and_nothing_eligible_falls_back_to_the_default():
    state = _state()
    _status(state, bloomberg="green", cboe="red", yahoo="amber")
    assert state.set_ticker_source("ALPHA", AUTO_SOURCE) == "yahoo"  # 2.7 s beats Bloomberg's 6 s
    _status(state, bloomberg="red", cboe="red", yahoo="red")
    state.set_ticker_source("BETA", AUTO_SOURCE)
    assert state.source_of("BETA") == "yahoo"  # the universe's default, never no source


def test_re_resolution_happens_at_fetch_time_only_and_bumps_the_version():
    state = _state()
    _status(state, bloomberg="green", cboe="green", yahoo="green")
    state.set_ticker_source("ALPHA", AUTO_SOURCE)
    assert state.source_of("ALPHA") == "cboe"
    spot_cboe = state.snapshot("ALPHA").spot
    # Cboe turns slow: a READ keeps the remembered pick (stability) ...
    for _ in range(20):
        state.source_policy.record_wall("cboe", 30.0)
    assert state.source_of("ALPHA") == "cboe" and state.resolved_sources()["ALPHA"] == "cboe"
    assert state.snapshot("ALPHA").spot == spot_cboe
    v0 = state.data_version("ALPHA")
    # ... the Fetch re-ranks: Yahoo (2.7 s) is now the fastest green source.
    spot = state.refresh_chain("ALPHA")
    assert state.source_of("ALPHA") == "yahoo"
    assert spot == pytest.approx(3.0 * spot_cboe)  # pulled from the new source
    assert state.data_version("ALPHA") == v0 + 2  # the Fetch's bump + the re-pin's
    # A Fetch with the same answer changes nothing beyond the Fetch itself.
    v1 = state.data_version("ALPHA")
    state.refresh_chain("ALPHA")
    assert state.source_of("ALPHA") == "yahoo" and state.data_version("ALPHA") == v1 + 1
    # An explicit pin ends the auto pick; unpinning follows the default again.
    assert state.set_ticker_source("ALPHA", "bloomberg") == "bloomberg"
    assert state.set_ticker_source("ALPHA", None) == "yahoo" and state.ticker_sources() == {}


def test_a_live_fetch_feeds_the_sources_ewma_but_history_does_not():
    state = _state()
    assert state.source_policy.walls() == {}
    state.snapshot("ALPHA")  # a live pull on yahoo
    walls = state.source_policy.walls()
    assert set(walls) == {"yahoo"} and walls["yahoo"] < SEED_WALL_S["yahoo"]  # synthetic is instant


def test_the_auto_pin_survives_the_workspace_and_a_saved_universe(tmp_path):
    from volfit.api import universe_service as svc

    state = _state()
    state.set_ticker_source("ALPHA", AUTO_SOURCE)
    doc = state.workspace_doc()
    assert doc["tickerSources"] == {"ALPHA": AUTO_SOURCE}
    other = _state()
    _status(other, bloomberg="green", cboe="green", yahoo="green")
    other.restore_workspace(doc)
    assert other.ticker_sources() == {"ALPHA": AUTO_SOURCE} and other.source_of("ALPHA") == "cboe"
    db = tmp_path / "u.sqlite"
    saved = _state(store_path=str(db))
    saved.set_ticker_source("BETA", AUTO_SOURCE)
    svc.save_current(saved, "auto")
    fresh = _state(store_path=str(db))
    svc.load_saved(fresh, "auto")
    assert fresh.ticker_sources() == {"BETA": AUTO_SOURCE}
    restored = _state()
    restored.restore_universe(["ALPHA"], None, {"ALPHA": AUTO_SOURCE, "BETA": AUTO_SOURCE})
    assert restored.ticker_sources() == {"ALPHA": AUTO_SOURCE}


def test_a_default_source_switch_keeps_an_auto_pinned_tickers_feed_and_caches():
    """An auto pin is a pin: on a switch of the universe's default source the
    ticker keeps its remembered feed and its chain caches (no refetch), exactly
    like an explicit pin; only the FOLLOWERS refetch on the new default."""
    state = _state()
    _status(state, bloomberg="green", cboe="green", yahoo="green")
    state.set_ticker_source("ALPHA", AUTO_SOURCE)
    assert state.source_of("ALPHA") == "cboe"
    state.snapshot("ALPHA"); state.snapshot("BETA")
    v_alpha, v_beta = state.data_version("ALPHA"), state.data_version("BETA")
    state.set_active_source("bloomberg")
    assert state.source_of("ALPHA") == "cboe"  # the pin held
    assert state.data_version("ALPHA") == v_alpha  # caches kept, nothing to refetch
    assert state.data_version("BETA") > v_beta  # the follower moved to the new default


# ------------------------------------------------------------------ API

def test_api_accepts_the_auto_pin_and_reports_the_resolution():
    app = create_app(reference_date=REF, providers=_providers(), active_source="yahoo")
    with TestClient(app) as c:
        state = app.state.volfit
        _status(state, bloomberg="green", cboe="green", yahoo="green")
        r = c.put("/universe/ALPHA/source", json={"source": AUTO_SOURCE})
        assert r.status_code == 200
        body = r.json()
        assert body["tickerSources"] == {"ALPHA": AUTO_SOURCE}
        assert body["resolvedSources"] == {"ALPHA": "cboe", "BETA": "yahoo"}  # never silent
        u = c.get("/universe").json()
        assert u["resolvedSources"]["ALPHA"] == "cboe" and u["defaultSource"] == "yahoo"
        served = {s["id"]: s["tickers"] for s in c.get("/datasources").json()["sources"]}
        assert served["cboe"] == ["ALPHA"] and served["yahoo"] == ["BETA"]
        assert c.put("/universe/ALPHA/source", json={"source": None}).json()["resolvedSources"]["ALPHA"] == "yahoo"
