"""Massive historical NBBO chains (volfit.data.massive_history).

A past day's close / instant is REAL two-sided bid/ask: one ``/v3/quotes``
request per contract at-or-before the instant, concurrent, budgeted
nearest-the-money first, narrated through the progress hook. An entitlement
or rate-limit gate falls back to aggregate MARKS and is remembered for the
session; the capabilities the as-of picker reads follow the same switch.
"""

from __future__ import annotations

import gzip
import threading
from datetime import date, datetime, timezone

import pytest

from volfit.data import progress
from volfit.data.expiry_time import is_trading_day, session_close_utc
from volfit.data.massive import MassiveProvider
from volfit.data.massive_history import NBBO_MAX_CONTRACTS, budget_contracts
from volfit.data.provider import AsOf

EXP = date(2026, 9, 18)
EXP2 = date(2026, 12, 18)
DAY = date(2026, 6, 12)


def _contracts(strikes, expiries=(EXP,)) -> list[dict]:
    """Reference-endpoint rows: a call and a put per (expiry, strike)."""
    out = []
    for e in expiries:
        for k in strikes:
            for kind, cp in (("call", "C"), ("put", "P")):
                out.append(
                    {"ticker": f"O:SPY{e:%y%m%d}{cp}{int(k * 1000):08d}",
                     "expiration_date": e.isoformat(), "strike_price": float(k),
                     "contract_type": kind, "exercise_style": "american"}
                )
    return out


def _mid(sym: str, spot: float) -> float:
    """A parity-consistent mid: intrinsic + 2, so C − P = S − K exactly."""
    cp, strike = sym[-9], int(sym[-8:]) / 1000.0
    intrinsic = max(spot - strike, 0.0) if cp == "C" else max(strike - spot, 0.0)
    return intrinsic + 2.0


class _Api:
    """A fake Massive REST: the contracts reference, per-contract NBBO (0.2 wide
    around a parity-consistent mid), the stock NBBO / aggregates as configured."""

    def __init__(self, contracts, spot=500.0, stock="quotes", quote_status=None, fail_after=None):
        self.contracts = contracts
        self.spot = spot
        self.stock = stock  # "quotes" | "aggs" | "none"
        self.quote_status = quote_status  # a body every option-quote request answers with
        self.fail_after = fail_after  # a rate-limit ERROR body after this many quote calls
        self.quote_calls: list[tuple[str, dict]] = []
        self._lock = threading.Lock()

    def __call__(self, url, params):
        if "/reference/options/contracts" in url:
            return {"results": self.contracts, "status": "OK"}
        if "/v3/quotes/O:" in url:
            with self._lock:
                self.quote_calls.append((url, dict(params or {})))
                n = len(self.quote_calls)
            if self.quote_status is not None:
                return self.quote_status
            if self.fail_after is not None and n > self.fail_after:
                return {"status": "ERROR", "error": "You've exceeded the maximum requests per minute"}
            mid = _mid(url.rsplit("/", 1)[-1], self.spot)
            return {"results": [{"bid_price": mid - 0.1, "ask_price": mid + 0.1}], "status": "OK"}
        if url.endswith("/v3/quotes/SPY"):
            if self.stock == "quotes":
                return {"results": [{"bid_price": self.spot - 0.5, "ask_price": self.spot + 0.5}], "status": "OK"}
            return {"status": "NOT_AUTHORIZED", "message": "stocks are a separate plan"}
        if "/v2/aggs/ticker/" in url:
            sym = url.split("/v2/aggs/ticker/")[1].split("/")[0]
            if sym.startswith("O:"):
                return {"results": [{"t": 0, "c": _mid(sym, self.spot), "v": 1}], "status": "OK"}
            if self.stock == "aggs":
                return {"results": [{"t": 0, "c": self.spot}], "status": "OK"}
            return {"status": "NOT_AUTHORIZED", "message": "stocks are a separate plan"}
        raise AssertionError(f"unexpected url {url}")


def _provider(api, **kw) -> MassiveProvider:
    return MassiveProvider(["SPY"], api_key="k", http_get=api, **kw)


def _ns(ts: datetime) -> int:
    return int(ts.replace(tzinfo=timezone.utc).timestamp() * 1_000_000_000)


def _flat_store(tmp_path):
    """A flat-file store over a local gzip CSV: 2026-06-16 closes implying spot 500."""
    pytest.importorskip("duckdb")
    from volfit.data.flatfiles import FlatFileStore, _to_ns

    ns = _to_ns(datetime(2026, 6, 12, 19, 55))
    rows = [("O:SPY260616C00490000", 15), ("O:SPY260616P00490000", 5),
            ("O:SPY260616C00500000", 8), ("O:SPY260616P00500000", 8),
            ("O:SPY260616C00510000", 4), ("O:SPY260616P00510000", 14)]  # three strikes: parity needs them
    path = tmp_path / "2026-06-12.csv.gz"
    with gzip.open(path, "wt", newline="") as fh:
        fh.write("ticker,volume,open,close,high,low,window_start,transactions\n")
        for tk, close in rows:
            fh.write(f"{tk},10,{close},{close},{close},{close},{ns},3\n")
    return FlatFileStore(source_uri=lambda day, freq: str(path))


# ------------------------------------------------------------ the two-sided past

def test_eod_past_day_is_nbbo_at_the_session_close():
    api = _Api(_contracts([480, 490, 500, 510, 520]), stock="none")
    chain = _provider(api).fetch_chain("SPY", [EXP], as_of=AsOf(mode="eod", on=DAY))
    close = session_close_utc(DAY)
    assert chain.timestamp == close and chain.quote_kind == "quotes"
    assert len(chain.quotes) == 10
    assert all(q.ask - q.bid == pytest.approx(0.2) for q in chain.quotes)  # real spreads
    assert all(p["timestamp.lte"] == _ns(close) for _u, p in api.quote_calls)
    assert len(api.quote_calls) == 10  # the probe IS the first contract's quote
    assert chain.spot == pytest.approx(500.0, abs=1e-6)  # parity: an options-only plan


def test_past_instant_is_nbbo_at_the_instant_with_progress():
    api = _Api(_contracts(range(400, 600, 4)))  # 100 contracts: the old path refused > 40
    ts = datetime(2026, 6, 12, 19, 45)
    seen: list = []
    with progress.bind(lambda d, t, label: seen.append((d, t, label))):
        chain = _provider(api).fetch_chain("SPY", [EXP], as_of=AsOf(mode="intraday", ts=ts))
    assert chain.timestamp == ts and chain.quote_kind == "quotes" and len(chain.quotes) == 100
    assert chain.spot == pytest.approx(500.0)  # the underlying's own NBBO mid
    assert all(p["timestamp.lte"] == _ns(ts) for _u, p in api.quote_calls)
    assert seen[-1] == (100, 100, "100 / 100 contracts")
    assert len(api.quote_calls) == 100


def test_contracts_without_a_quote_by_then_are_skipped_not_marked():
    api = _Api(_contracts([500, 510]), stock="aggs")
    empty = {"results": [], "status": "OK"}
    calls = api.__call__

    def http_get(url, params):
        if "/v3/quotes/O:" in url and url.endswith("P00510000"):
            api.quote_calls.append((url, dict(params or {})))
            return empty
        return calls(url, params)

    p = MassiveProvider(["SPY"], api_key="k", http_get=http_get)
    chain = p.fetch_chain("SPY", [EXP], as_of=AsOf(mode="eod", on=DAY))
    assert len(chain.quotes) == 3 and all(q.bid is not None and q.ask is not None for q in chain.quotes)


# -------------------------------------------------------------- the gate

def test_entitlement_gate_falls_back_to_marks_and_is_remembered(tmp_path):
    api = _Api(_contracts([500], expiries=(date(2026, 6, 16),)),
               quote_status={"status": "NOT_AUTHORIZED", "message": "quotes need the Advanced plan"})
    p = _provider(api, flat_store=_flat_store(tmp_path))
    assert p.historical_quote_kind() == "quotes" and p.nbbo_history_gate() is None
    chain = p.fetch_chain("SPY", [date(2026, 6, 16)], as_of=AsOf(mode="eod", on=DAY))
    assert chain.quote_kind == "marks" and all(q.bid == q.ask for q in chain.quotes)  # the flat closes
    assert len(api.quote_calls) == 1  # the probe only — no crawl behind a closed gate
    assert "Advanced plan" in p.nbbo_history_gate() and p.historical_quote_kind() == "marks"
    p.fetch_chain("SPY", [date(2026, 6, 16)], as_of=AsOf(mode="eod", on=DAY))
    assert len(api.quote_calls) == 1  # remembered: not even the probe again
    assert p.intraday_capable() is True  # the aggregate paths still serve an instant


def test_rate_limit_mid_chain_aborts_to_aggregate_marks_without_a_store():
    api = _Api(_contracts(range(450, 550, 2)), fail_after=10)  # the 11th answer is a 429 body
    p = _provider(api)
    ts = datetime(2026, 6, 12, 19, 45)
    chain = p.fetch_chain("SPY", [EXP], as_of=AsOf(mode="intraday", ts=ts))
    assert chain.quote_kind == "marks" and all(q.bid == q.ask for q in chain.quotes)  # minute bars
    assert len(chain.quotes) == 100 and chain.timestamp == ts
    assert "maximum requests" in p.nbbo_history_gate()
    assert len(api.quote_calls) < 100  # aborted, not crawled to the end


def test_eod_without_a_store_and_a_closed_gate_is_the_aggregate_close():
    api = _Api(_contracts([490, 500, 510]), stock="aggs",
               quote_status={"status": "NOT_AUTHORIZED", "message": "no"})
    chain = _provider(api).fetch_chain("SPY", [EXP], as_of=AsOf(mode="eod", on=DAY))
    assert chain.quote_kind == "marks" and chain.timestamp == session_close_utc(DAY)
    assert chain.spot == pytest.approx(500.0)


# ------------------------------------------------------------- the budget

def test_budget_keeps_every_expiry_belly_nearest_the_money_first():
    contracts = [
        {"ticker": f"O:{e:%y%m%d}{cp}{k}", "expiry": e, "strike": float(k), "call_put": cp, "style": "american"}
        for e in (EXP, EXP2) for k in range(200, 800) for cp in ("C", "P")
    ]  # 2 × 600 × 2 = 2400 > the cap
    kept = budget_contracts(contracts, 500.0, DAY, NBBO_MAX_CONTRACTS)
    assert len(kept) == NBBO_MAX_CONTRACTS
    near = [c for c in kept if c["expiry"] == EXP]
    far = [c for c in kept if c["expiry"] == EXP2]
    for group in (near, far):
        assert {498.0, 500.0, 502.0} <= {c["strike"] for c in group}  # every belly survives
    # A shorter expiry keeps a tighter window (|ln K/S| / sqrt T), the longer a wider one.
    assert max(abs(c["strike"] - 500) for c in near) < max(abs(c["strike"] - 500) for c in far)
    assert kept == sorted(kept, key=lambda c: (c["expiry"], c["strike"], c["call_put"]))
    # Under the cap: untouched. No spot: the nearest expiry's median strike stands in.
    assert budget_contracts(contracts[:10], None, DAY, NBBO_MAX_CONTRACTS) == contracts[:10]
    blind = budget_contracts(contracts, None, DAY, NBBO_MAX_CONTRACTS)
    assert len(blind) == NBBO_MAX_CONTRACTS and {500.0, 502.0} <= {c["strike"] for c in blind}


def test_a_large_selection_is_capped_at_the_budget():
    api = _Api(_contracts(range(100, 900), expiries=(EXP, EXP2)))  # 3200 contracts
    chain = _provider(api).fetch_chain("SPY", [EXP, EXP2], as_of=AsOf(mode="eod", on=DAY))
    assert len(chain.quotes) == NBBO_MAX_CONTRACTS
    assert len(api.quote_calls) <= NBBO_MAX_CONTRACTS + 1  # the budget (+ at most the probe)
    assert {(EXP, 500.0), (EXP2, 500.0)} <= {(q.expiry, q.strike) for q in chain.quotes}


# ------------------------------------------------------- capabilities / switch

def test_capabilities_with_a_key_and_the_off_switch():
    p = _provider(_Api([]))
    assert "eod" in p.historical_modes() and p.intraday_capable() and p.historical_quote_kind() == "quotes"
    hist = p.available_history("SPY")
    assert len(hist) == 20 and all(is_trading_day(d) for d in hist) and hist == sorted(hist)
    off = _provider(_Api([]), hist_nbbo=False)
    assert off.historical_quote_kind() == "marks" and "disabled" in off.nbbo_history_gate()
    assert "eod" in off.historical_modes() and off.intraday_capable()  # aggregate marks still serve
    none = MassiveProvider(["SPY"], api_key="")
    assert none.available_history("SPY") == [] and not none.intraday_capable()
    assert "eod" not in none.historical_modes()


def test_off_switch_never_touches_the_quote_history(tmp_path):
    api = _Api(_contracts([500], expiries=(date(2026, 6, 16),)))
    p = _provider(api, flat_store=_flat_store(tmp_path), hist_nbbo=False)
    chain = p.fetch_chain("SPY", [date(2026, 6, 16)], as_of=AsOf(mode="eod", on=DAY))
    assert chain.quote_kind == "marks" and api.quote_calls == []
