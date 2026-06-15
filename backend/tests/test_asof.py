"""Tests for the as-of (timestamp) selector: provider history, AppState
routing, capture/replay, and the /asof API. All offline."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from datetime import datetime

from volfit.api import asof as asof_svc
from volfit.api.app import create_app
from volfit.api.state import AppState, AsOfSelection
from volfit.data.massive import MassiveProvider
from volfit.data.provider import AsOf, SyntheticProvider
from volfit.data.store import VolStore
from volfit.data.types import ChainSnapshot, OptionQuote

REF = date(2026, 6, 13)


def _exp(days: int) -> str:
    return date.fromordinal(REF.toordinal() + days).isoformat()


# --------------------------------------------------------------- Massive prev_close

def test_massive_prev_close_prices_from_day_close():
    exp = _exp(30)
    snapshot = {
        "results": [
            {
                "details": {"contract_type": "call", "expiration_date": exp,
                            "strike_price": 500, "exercise_style": "american"},
                "day": {"close": 12.5, "volume": 66},
                "last_quote": {"bid": 99.0, "ask": 101.0},  # ignored under prev_close
                "open_interest": 8,
                "underlying_asset": {"ticker": "SPY", "price": 741.75},
            }
        ],
        "status": "OK",
    }

    def http_get(url, params):
        return snapshot

    provider = MassiveProvider(["SPY"], api_key="k", http_get=http_get)
    assert provider.historical_modes() == {"live", "prev_close"}
    chain = provider.fetch_chain(
        "SPY", [date.fromisoformat(exp)], as_of=AsOf(mode="prev_close")
    )
    q = chain.quotes[0]
    assert q.bid == 12.5 and q.ask == 12.5 and q.last == 12.5  # zero-spread close
    assert chain.spot == 741.75


def test_massive_intraday_reconstructs_chain_at_instant():
    """AsOf(mode='intraday', ts=...) pulls each contract's historical NBBO quote
    at-or-before the instant (Polygon /v3/quotes) and the underlying mid."""
    exp = date(2026, 9, 18)
    opt = "O:SPY260918C00500000"

    def http_get(url, params):
        if "/reference/options/contracts" in url:
            return {"results": [{"ticker": opt, "expiration_date": exp.isoformat(),
                                 "strike_price": 500, "contract_type": "call",
                                 "exercise_style": "american"}], "status": "OK"}
        if url.endswith(f"/v3/quotes/{opt}"):
            return {"results": [{"bid_price": 9.8, "ask_price": 10.2}], "status": "OK"}
        if url.endswith("/v3/quotes/SPY"):
            return {"results": [{"bid_price": 740.0, "ask_price": 742.0}], "status": "OK"}
        raise AssertionError(f"unexpected url {url}")

    provider = MassiveProvider(["SPY"], api_key="k", http_get=http_get)
    assert provider.intraday_capable() is True
    ts = datetime(2026, 6, 12, 19, 45)
    chain = provider.fetch_chain("SPY", [exp], as_of=AsOf(mode="intraday", ts=ts))
    assert chain.timestamp == ts
    assert chain.spot == 741.0  # (740 + 742) / 2
    q = chain.quotes[0]
    assert q.bid == 9.8 and q.ask == 10.2 and q.strike == 500.0 and q.call_put == "C"


# --------------------------------------------------------------- Bloomberg EOD

class _FakeBlpHistory:
    """Minimal blp with bds(OPT_CHAIN) + bdh(historical) for one option + spot."""

    def __init__(self, on: date):
        self._on = on
        self._sec = "SPY US 06/18/26 C500 Equity"

    def bds(self, security, field, **_):
        return pd.DataFrame(
            {
                "ticker": ["SPY US Equity"],
                "field": ["OPT_CHAIN"],
                "Security Description": [self._sec],
            }
        )

    def bdh(self, securities, fields, start, end, **_):
        secs = [securities] if isinstance(securities, str) else list(securities)
        flds = [fields] if isinstance(fields, str) else list(fields)
        values = {"PX_BID": 10.0, "PX_ASK": 10.4, "PX_LAST": 10.2,
                  "PX_VOLUME": 5.0, "OPEN_INT": 20.0}
        rows = []
        for sec in secs:
            for fld in flds:
                val = 741.0 if (sec == "SPY US Equity" and fld == "PX_LAST") else values.get(fld)
                rows.append({"ticker": sec, "date": self._on, "field": fld, "value": val})
        return pd.DataFrame(rows, columns=["ticker", "date", "field", "value"])


def test_bloomberg_eod_fetch():
    from volfit.data.bloomberg import BloombergProvider

    on = date(2026, 6, 12)
    provider = BloombergProvider(["SPY"], blp_module=_FakeBlpHistory(on))
    assert "eod" in provider.historical_modes()
    chain = provider.fetch_chain(
        "SPY", [date(2026, 6, 18)], as_of=AsOf(mode="eod", on=on)
    )
    assert chain.spot == 741.0
    assert chain.timestamp.date() == on
    q = chain.quotes[0]
    assert q.bid == 10.0 and q.ask == 10.4 and q.open_interest == 20


# --------------------------------------------------------------- AppState routing

def test_set_as_of_validates_and_clears(tmp_path):
    provider = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    state = AppState(REF, providers={"synthetic": provider}, active_source="synthetic")
    state.snapshot("ALPHA")
    assert "ALPHA" in state._snapshots
    # Synthetic supports only live -> prev_close is rejected.
    with pytest.raises(KeyError):
        state.set_as_of(AsOfSelection(mode="prev_close"))
    # Captured needs a store + timestamp.
    with pytest.raises(KeyError):
        state.set_as_of(AsOfSelection(mode="captured"))


def test_no_auto_capture_for_bloomberg_massive(tmp_path):
    """Live fetches under Massive/Bloomberg are NOT auto-captured to the store
    (they have their own history channels); other sources still capture."""
    db = tmp_path / "nocap.sqlite"
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    # Register the offline provider under a 'bloomberg' id to exercise the guard.
    state = AppState(REF, providers={"bloomberg": prov}, active_source="bloomberg",
                     store_path=str(db))
    state.snapshot("ALPHA")  # live fetch
    with VolStore(db) as store:
        assert store.list_snapshots(["ALPHA"]) == []  # nothing persisted

    # The same provider under 'yahoo' DOES capture.
    state2 = AppState(REF, providers={"yahoo": prov}, active_source="yahoo",
                      store_path=str(db))
    state2.snapshot("ALPHA")
    with VolStore(db) as store:
        assert len(store.list_snapshots(["ALPHA"])) == 1


def test_live_capture_and_captured_replay(tmp_path):
    db = tmp_path / "cap.sqlite"
    provider = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    state = AppState(
        REF, providers={"synthetic": provider}, active_source="synthetic",
        store_path=str(db),
    )
    chain = state.snapshot("ALPHA")  # live fetch -> auto-captured
    with VolStore(db) as store:
        rows = store.list_snapshots(["ALPHA"])
    assert len(rows) == 1  # one capture persisted
    captured_ts = rows[0][2]
    # Replay that captured moment.
    state.set_as_of(AsOfSelection(mode="captured", ts=captured_ts))
    replay = state.snapshot("ALPHA")
    assert replay.spot == chain.spot
    assert len(replay.quotes) == len(chain.quotes)


# --------------------------------------------------------------- API

def _app(tmp_path):
    provider = SyntheticProvider(reference_date=REF, tickers=("ALPHA", "BETA"))
    return create_app(
        reference_date=REF, providers={"synthetic": provider},
        active_source="synthetic", store_path=str(tmp_path / "api.sqlite"),
    )


def test_get_asof(tmp_path):
    client = TestClient(_app(tmp_path))
    body = client.get("/asof").json()
    assert body["mode"] == "live"
    assert body["supportedModes"] == ["live"]  # synthetic is live-only
    assert body["intradayCapable"] is False
    assert body["closeOffsets"] == [15, 30, 60]
    assert isinstance(body["days"], list)


def test_post_asof_unsupported_mode_404(tmp_path):
    client = TestClient(_app(tmp_path))
    assert client.post("/asof", json={"mode": "prev_close"}).status_code == 404


def test_post_asof_moment_latest_resolves_to_capture(tmp_path):
    client = TestClient(_app(tmp_path))
    client.get("/smiles/ALPHA/" + _exp(91))  # trigger a live fetch -> capture
    # The capture lands on the wall-clock day; find it in the grouped day list.
    days = client.get("/asof").json()["days"]
    cap_day = next(d["date"] for d in days if d["hasCaptures"])
    resp = client.post(
        "/asof", json={"mode": "moment", "on": cap_day, "moment": "latest"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "captured"
    assert body["moment"] == "latest" and body["day"] == cap_day


def test_post_asof_legacy_captured_still_works(tmp_path):
    """The low-level {mode:'captured', ts} form remains supported."""
    client = TestClient(_app(tmp_path))
    client.get("/smiles/ALPHA/" + _exp(91))  # capture
    # Resolve a capture via the moment form to obtain its ts, then re-apply raw.
    days = client.get("/asof").json()["days"]
    cap_day = next(d["date"] for d in days if d["hasCaptures"])
    ts = client.post(
        "/asof", json={"mode": "moment", "on": cap_day, "moment": "latest"}
    ).json()["ts"]
    resp = client.post("/asof", json={"mode": "captured", "ts": ts})
    assert resp.status_code == 200 and resp.json()["mode"] == "captured"


# --------------------------------------------------------------- moment resolution

def test_market_close_utc_handles_dst():
    """16:00 ET -> 20:00 UTC in summer (EDT), 21:00 UTC in winter (EST)."""
    assert asof_svc.market_close_utc(date(2026, 6, 15)) == datetime(2026, 6, 15, 20, 0)
    assert asof_svc.market_close_utc(date(2026, 1, 15)) == datetime(2026, 1, 15, 21, 0)


def _save_capture(db, ticker: str, ts: datetime) -> None:
    snap = ChainSnapshot(
        ticker=ticker, spot=100.0, timestamp=ts,
        quotes=[OptionQuote(ticker=ticker, expiry=date(2026, 9, 18), strike=100.0,
                            call_put="C", bid=1.0, ask=1.2, last=1.1, volume=1,
                            open_interest=1, timestamp=ts)],
    )
    with VolStore(db) as store:
        store.save_snapshot(snap)


def test_before_close_picks_nearest_capture_at_or_before(tmp_path):
    """before_close(N) resolves to the captured snapshot nearest to (16:00 ET − N)
    without going past it; latest picks the newest of the day."""
    db = tmp_path / "moments.sqlite"
    provider = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    state = AppState(REF, providers={"synthetic": provider},
                     active_source="synthetic", store_path=str(db))
    day = date(2026, 6, 12)  # a summer trading day -> close 20:00 UTC
    for hhmm in ((19, 0), (19, 45), (19, 55)):  # 15:00, 15:45, 15:55 ET
        _save_capture(str(db), "ALPHA", datetime(2026, 6, 12, *hhmm))

    # −15m: target 19:45 -> exact capture 19:45.
    sel = asof_svc._resolve_moment(state, day, "before_close", 15)
    assert sel.mode == "captured" and sel.ts == datetime(2026, 6, 12, 19, 45)
    # −60m: target 19:00 -> exact capture 19:00 (19:45/19:55 are after it).
    sel = asof_svc._resolve_moment(state, day, "before_close", 60)
    assert sel.ts == datetime(2026, 6, 12, 19, 0)
    # latest: newest capture of the day.
    sel = asof_svc._resolve_moment(state, day, "latest", None)
    assert sel.moment == "latest" and sel.ts == datetime(2026, 6, 12, 19, 55)


class _EodProvider(SyntheticProvider):
    """Synthetic chains but advertising EOD + prev_close history for two days."""

    def historical_modes(self):
        return {"live", "eod", "prev_close"}

    def available_history(self, ticker):
        return [date(2026, 6, 11), date(2026, 6, 12)]


def test_close_moment_resolves_eod_and_prev_close():
    state = AppState(REF, providers={"synthetic": _EodProvider(reference_date=REF, tickers=("ALPHA",))},
                     active_source="synthetic")
    # A listed EOD day -> eod close.
    sel = asof_svc._resolve_moment(state, date(2026, 6, 12), "close", None)
    assert sel.mode == "eod" and sel.on == date(2026, 6, 12) and sel.moment == "close"
    # The newest EOD day is also the prev_close session (resolves either way here).
    # A day with no close raises (so the dropdown never offers it).
    with pytest.raises(ValueError):
        asof_svc._resolve_moment(state, date(2026, 6, 1), "close", None)
