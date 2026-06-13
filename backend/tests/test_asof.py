"""Tests for the as-of (timestamp) selector: provider history, AppState
routing, capture/replay, and the /asof API. All offline."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from volfit.api.app import create_app
from volfit.api.state import AppState, AsOfSelection
from volfit.data.massive import MassiveProvider
from volfit.data.provider import AsOf, SyntheticProvider
from volfit.data.store import VolStore

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
    assert body["prevCloseAvailable"] is False


def test_post_asof_unsupported_mode_404(tmp_path):
    client = TestClient(_app(tmp_path))
    assert client.post("/asof", json={"mode": "prev_close"}).status_code == 404


def test_post_asof_captured_roundtrip(tmp_path):
    client = TestClient(_app(tmp_path))
    client.get("/smiles/ALPHA/" + _exp(91))  # trigger a live fetch -> capture
    captured = client.get("/asof").json()["captured"]
    assert captured  # at least one captured moment
    resp = client.post("/asof", json={"mode": "captured", "ts": captured[0]})
    assert resp.status_code == 200 and resp.json()["mode"] == "captured"
