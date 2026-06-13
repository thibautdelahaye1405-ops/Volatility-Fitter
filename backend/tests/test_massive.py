"""Offline tests for the Massive provider (volfit.data.massive).

No network: an injected ``http_get`` returns canned JSON in the *exact shapes*
captured from the live Massive API (2026-06-13) — the reference-contracts list,
the option-chain snapshot (greeks/IV/day, with and without entitled
``last_quote``/spot), and the NOT_AUTHORIZED gate. The fake also exercises
``next_url`` pagination.
"""

from __future__ import annotations

from datetime import date

import pytest

from volfit.data.massive import MassiveProvider

TODAY = date.today()


def _exp(days: int) -> str:
    return date.fromordinal(TODAY.toordinal() + days).isoformat()


class FakeHttp:
    """Maps a (url, params) call to a canned JSON body; supports next_url."""

    def __init__(self, pages: dict[str, dict]):
        self.pages = pages
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, url: str, params: dict | None) -> dict:
        self.calls.append((url, params))
        # Page lookup: the cursor key on next_url, else the bare path of url.
        if "cursor=" in url:
            key = url.split("cursor=")[1]
        else:
            key = url.split("massive.com")[-1].split("?")[0]
        return self.pages[key]


def _contract(strike: float, expiry_days: int, cp: str = "call") -> dict:
    return {
        "contract_type": cp,
        "exercise_style": "american",
        "expiration_date": _exp(expiry_days),
        "strike_price": strike,
        "ticker": f"O:SPY{strike:.0f}{cp[0].upper()}",
        "underlying_ticker": "SPY",
    }


# --------------------------------------------------------------- expiries

def test_available_expiries_paginates_and_filters():
    pages = {
        "/v3/reference/options/contracts": {
            "results": [_contract(500, 30), _contract(505, 30), _contract(520, 120)],
            "status": "OK",
            "next_url": "https://api.massive.com/v3/reference/options/contracts?cursor=PAGE2",
        },
        "PAGE2": {
            "results": [_contract(530, 900)],  # beyond max_days -> filtered
            "status": "OK",
        },
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    expiries = provider.available_expiries("SPY")
    assert expiries == sorted({date.fromisoformat(_exp(30)), date.fromisoformat(_exp(120))})


# --------------------------------------------------------------- chain

def _snap_result(strike, days, cp, *, quote=True, spot=True):
    out = {
        "details": {
            "contract_type": cp,
            "exercise_style": "american",
            "expiration_date": _exp(days),
            "strike_price": strike,
        },
        "day": {"close": 12.5, "volume": 66},
        "greeks": {"delta": 0.5, "gamma": 0.01, "theta": -0.2, "vega": 0.1},
        "implied_volatility": 0.1834,
        "open_interest": 8,
    }
    if quote:
        out["last_quote"] = {"bid": 12.3, "ask": 12.7, "midpoint": 12.5}
    if spot:
        out["underlying_asset"] = {"ticker": "SPY", "price": 741.75}
    else:
        out["underlying_asset"] = {"ticker": "SPY"}
    return out


def test_fetch_chain_full_entitlement():
    pages = {
        "/v3/snapshot/options/SPY": {
            "results": [
                _snap_result(500, 30, "call"),
                _snap_result(500, 30, "put"),
            ],
            "status": "OK",
        }
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    snap = provider.fetch_chain("SPY", [date.fromisoformat(_exp(30))])
    assert snap.spot == 741.75
    assert snap.exercise_style == "american"
    call = next(q for q in snap.quotes if q.call_put == "C")
    assert call.bid == 12.3 and call.ask == 12.7
    assert call.last == 12.5 and call.volume == 66 and call.open_interest == 8


def test_fetch_chain_without_spot_raises_upgrade():
    # Snapshot lacks last_quote + underlying price (the current key's tier);
    # the stock-snapshot fallback answers NOT_AUTHORIZED.
    pages = {
        "/v3/snapshot/options/SPY": {
            "results": [_snap_result(500, 30, "call", quote=False, spot=False)],
            "status": "OK",
        },
        "/v2/snapshot/locale/us/markets/stocks/tickers/SPY": {
            "status": "NOT_AUTHORIZED",
            "message": "You are not entitled to this data. Please upgrade your plan.",
        },
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    with pytest.raises(RuntimeError, match="upgrade"):
        provider.fetch_chain("SPY", [date.fromisoformat(_exp(30))])


def test_paginate_raises_on_not_authorized():
    pages = {
        "/v3/snapshot/options/SPY": {
            "status": "NOT_AUTHORIZED",
            "message": "You are not entitled to this data.",
        }
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    with pytest.raises(RuntimeError, match="Massive"):
        provider.fetch_chain("SPY", [date.fromisoformat(_exp(30))])


# --------------------------------------------------------------- IV overlay

def test_iv_surface():
    pages = {
        "/v3/snapshot/options/SPY": {
            "results": [_snap_result(500, 30, "call", quote=False, spot=False)],
            "status": "OK",
        }
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    rows = provider.iv_surface("SPY", [date.fromisoformat(_exp(30))])
    assert len(rows) == 1
    row = rows[0]
    assert row["iv"] == pytest.approx(0.1834)
    assert row["callPut"] == "C" and row["strike"] == 500.0
    assert row["delta"] == 0.5 and row["openInterest"] == 8


# --------------------------------------------------------------- search

def test_search_symbols_uses_reference_tickers():
    pages = {
        "/v3/reference/tickers": {
            "results": [
                {"ticker": "SPY", "name": "SPDR S&P 500", "type": "ETF",
                 "primary_exchange": "ARCX"},
            ],
            "status": "OK",
        }
    }
    provider = MassiveProvider(["SPY"], api_key="k", http_get=FakeHttp(pages))
    matches = provider.search_symbols("spdr")
    assert matches[0].symbol == "SPY"
    assert matches[0].name == "SPDR S&P 500" and matches[0].type == "ETF"


def test_search_symbols_falls_back_on_failure():
    def boom(url, params):
        raise RuntimeError("network down")

    provider = MassiveProvider(["SPY"], api_key="k", http_get=boom)
    # Base echo search still resolves a plausible bare symbol.
    assert any(m.symbol == "SPY" for m in provider.search_symbols("SPY"))
