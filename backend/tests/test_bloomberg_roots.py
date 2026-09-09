"""One option root per expiry date on Bloomberg chains (volfit.data.bloomberg_roots).

The live finding (2026-09-09, SX5E on the Terminal): Bloomberg lists Friday
2026-09-11 under the weekly ``WSX5EB`` AND the daily ``SX5EODJ``; the provider
deduped by security string, both survived, and the slice carried two smiles
2.4 vol points apart (125 bp rms, an "ATM discontinuity"). Offline here with a
``FakeBlp`` in the exact long/tidy shapes of tests/test_bloomberg.py.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from volfit.data.bloomberg import BloombergProvider
from volfit.data.bloomberg_parse import ParsedOption
from volfit.data.bloomberg_roots import one_root_per_date, parent_root, representative, root_of

TODAY = date.today()


def _friday(weeks_ahead: int) -> date:
    d = TODAY + timedelta(days=(4 - TODAY.weekday()) % 7 + 7 * weeks_ahead)
    return d if d > TODAY + timedelta(days=6) else d + timedelta(days=7)


def _mmddyy(d: date) -> str:
    return f"{d.month:02d}/{d.day:02d}/{d.year % 100:02d}"


def _frame(field: str, column: str, securities: list[str], underlying: str) -> pd.DataFrame:
    return pd.DataFrame({"ticker": [underlying] * len(securities), "field": [field] * len(securities),
                         column: securities})


def _bdp_long(values: dict[str, dict[str, object]]) -> pd.DataFrame:
    rows = [{"ticker": s, "field": f, "value": v} for s, fv in values.items() for f, v in fv.items()]
    return pd.DataFrame(rows, columns=["ticker", "field", "value"])


class FakeBlp:
    """OPT_CHAIN + one CHAIN_TICKERS ("W") frame, canned bdp values, every bdp
    call recorded as (securities, fields) so a test can say what was SENT."""

    def __init__(self, opt_chain: list[str], weekly: list[str], bdp_values: dict, underlying: str,
                 refuse_open_interest: bool = False):
        self._opt = _frame("OPT_CHAIN", "Security Description", opt_chain, underlying)
        self._weekly = _frame("CHAIN_TICKERS", "Ticker", weekly, underlying)
        self._values = bdp_values
        self._refuse = refuse_open_interest
        self.bdp_calls: list[tuple[list[str], list[str]]] = []

    def is_connected(self) -> bool:
        return True

    def bds(self, security, field, **kwargs):
        if field == "OPT_CHAIN":
            return self._opt
        if field == "CHAIN_TICKERS":
            return self._weekly if kwargs.get("overrides", {}).get("CHAIN_PERIODICITY_OVRD") == "W" else self._weekly.iloc[:0]
        raise AssertionError(field)

    def bdp(self, securities, fields, **_):
        secs = [securities] if isinstance(securities, str) else list(securities)
        flds = [fields] if isinstance(fields, str) else list(fields)
        self.bdp_calls.append((secs, flds))
        if self._refuse and flds == ["OPEN_INT"]:
            raise RuntimeError("field not entitled")
        return _bdp_long({s: {f: self._values.get(s, {}).get(f) for f in flds
                              if self._values.get(s, {}).get(f) is not None} for s in secs})


def _quote(bid: float, ask: float, oi: int = 0) -> dict:
    return {"BID": str(bid), "ASK": str(ask), "LAST_PRICE": str((bid + ask) / 2), "VOLUME": "10",
            "OPEN_INT": str(oi), "OPT_EXER_TYP": "European"}


# ------------------------------------------------------------- pure rule

def _po(security: str, d: date, strike: float, cp: str) -> ParsedOption:
    return ParsedOption(security=security, expiry=d, strike=strike, call_put=cp)


def test_root_tokens():
    assert root_of("WSX5EB 09/11/26 C5725 Index") == "WSX5EB"
    assert root_of("SPY US 09/18/26 C500 Equity") == "SPY"
    assert parent_root("SX5E Index") == "SX5E" and parent_root("SAP GY Equity") == "SAP"


def test_rule_parent_wins_then_open_interest_then_strike_count():
    d1, d2, d3 = _friday(1), _friday(2), _friday(3)
    chain = []
    for k in (100.0, 110.0, 120.0):  # d1: two siblings, three strikes each
        chain += [_po(f"WEEK {_mmddyy(d1)} C{k:g} Index", d1, k, "C"), _po(f"DAY {_mmddyy(d1)} C{k:g} Index", d1, k, "C")]
    for k in (100.0, 110.0):  # d2: parent + a daily
        chain += [_po(f"IDX {_mmddyy(d2)} C{k:g} Index", d2, k, "C"), _po(f"DAY {_mmddyy(d2)} C{k:g} Index", d2, k, "C")]
    chain += [_po(f"DAY {_mmddyy(d3)} C100 Index", d3, 100.0, "C")]  # d3: one root
    probes: list[list[str]] = []

    def probe(secs):
        probes.append(list(secs))
        return {f"DAY {_mmddyy(d1)} C110 Index": 1546, f"WEEK {_mmddyy(d1)} C110 Index": 7624}

    sel = one_root_per_date(chain, "IDX", probe)
    assert sel.roots == {d1: "WEEK", d2: "IDX", d3: "DAY"}
    assert probes == [[f"WEEK {_mmddyy(d1)} C110 Index", f"DAY {_mmddyy(d1)} C110 Index"]]  # d2 never probed
    assert {root_of(c.security) for c in sel.contracts if c.expiry == d1} == {"WEEK"}
    assert {root_of(c.security) for c in sel.contracts if c.expiry == d2} == {"IDX"}
    assert len(sel.dropped) == 2 and sel.dropped[0].startswith(d1.isoformat())
    # Same chain, the probe refused -> the root with more strikes wins the tie.
    chain2 = chain + [_po(f"DAY {_mmddyy(d1)} C130 Index", d1, 130.0, "C")]
    sel2 = one_root_per_date(chain2, "IDX", lambda secs: (_ for _ in ()).throw(RuntimeError("no")))
    assert sel2.roots[d1] == "DAY"
    # No probe at all and equal strikes -> the first listed root.
    assert one_root_per_date(chain, "IDX", None).roots[d1] == "WEEK"
    # The representative is the median-strike call.
    assert representative([c for c in chain if root_of(c.security) == "WEEK"]).strike == 110.0


# ---------------------------------------------------------- the provider

def _sx5e_blp(refuse: bool = False):
    """The live shape: the monthly SX5E on d3 beside the daily SX5EODO; the
    weekly WSX5EB and the daily SX5EODJ on d2 (three strikes each)."""
    d2, d3 = _friday(2), _friday(3)
    weekly = [f"{root} {_mmddyy(d2)} C{k}" for root in ("SX5EODJ", "WSX5EB") for k in (6250, 6300, 6350)]
    weekly += [f"SX5EODO {_mmddyy(d3)} C{k}" for k in (6250, 6300, 6350)]
    monthly = [f"SX5E {_mmddyy(d3)} {cp}{k} Index" for k in (6250, 6300, 6350) for cp in ("C", "P")]
    values = {"SX5E Index": {"PX_LAST": "6311.56"}}
    for s in weekly:
        root, k = s.split(" ")[0], s.rsplit("C", 1)[1]
        oi = {"WSX5EB": 7624, "SX5EODJ": 1546, "SX5EODO": 200}[root]
        px = 31.35 if root == "WSX5EB" else 33.75
        values[f"{s} Index"] = _quote(px - 1, px + 1, oi)
        values[f"{root} {s.split(' ')[1]} P{k} Index"] = _quote(px - 1, px + 1, oi)
    for s in monthly:
        values[s] = _quote(61.7, 63.7, 108431)
    return FakeBlp(monthly, weekly, values, "SX5E Index", refuse_open_interest=refuse), d2, d3


def test_weekly_beats_daily_by_open_interest_and_the_parent_needs_no_probe():
    blp, d2, d3 = _sx5e_blp()
    provider = BloombergProvider(["SX5E INDEX"], blp_module=blp)
    chain = provider._chain("SX5E INDEX")
    assert provider._roots_cache["SX5E INDEX"] == {d2: "WSX5EB", d3: "SX5E"}
    assert {root_of(c.security) for c in chain if c.expiry == d2} == {"WSX5EB"}
    assert {root_of(c.security) for c in chain if c.expiry == d3} == {"SX5E"}
    # ONE probe, over the two contested representatives only (d3 has its parent).
    probes = [c for c in blp.bdp_calls if c[1] == ["OPEN_INT"]]
    assert probes == [([f"SX5EODJ {_mmddyy(d2)} C6300 Index", f"WSX5EB {_mmddyy(d2)} C6300 Index"], ["OPEN_INT"])]
    assert provider.available_expiries("SX5E INDEX") == [d2, d3]  # each date once


def test_the_dropped_root_is_never_quoted_and_the_slice_has_one_smile():
    blp, d2, _ = _sx5e_blp()
    provider = BloombergProvider(["SX5E INDEX"], blp_module=blp)
    snap = provider.fetch_chain("SX5E INDEX", [d2])
    quoted = [c for c in blp.bdp_calls if "BID" in c[1]][0][0]
    assert all(s.startswith("WSX5EB ") for s in quoted) and len(quoted) == 6
    assert len(snap.quotes) == 6 and {q.bid for q in snap.quotes} == {30.35}
    assert snap.settlement[d2].style == "pm"


def test_a_refused_probe_falls_back_to_the_listing_rule():
    blp, d2, d3 = _sx5e_blp(refuse=True)
    provider = BloombergProvider(["SX5E INDEX"], blp_module=blp)
    chain = provider._chain("SX5E INDEX")  # no exception; equal strikes -> first listed
    assert provider._roots_cache["SX5E INDEX"][d2] == "SX5EODJ"
    assert provider._roots_cache["SX5E INDEX"][d3] == "SX5E"
    assert len({c.security for c in chain if c.expiry == d2}) == 6


def test_spx_parent_wins_and_the_settlement_follows_the_kept_root():
    d1, d3 = _friday(1), _friday(3)
    monthly = [f"{root} {_mmddyy(d3)} {cp}{k} Index" for root in ("SPXW", "SPX") for k in (6400, 6500) for cp in ("C", "P")]
    weekly = [f"SPXW {_mmddyy(d1)} C{k}" for k in (6400, 6500)]
    values = {"SPX Index": {"PX_LAST": "6450.0"}}
    for s in monthly:
        values[s] = _quote(50.0, 52.0, 1000)
    for s in weekly:
        values[f"{s} Index"] = _quote(20.0, 22.0, 500)
        values[f"{s.replace(' C', ' P')} Index"] = _quote(20.0, 22.0, 500)
    blp = FakeBlp(monthly, weekly, values, "SPX Index")
    provider = BloombergProvider(["SPX"], yellow_key="Index", blp_module=blp)
    snap = provider.fetch_chain("SPX", [d1, d3])
    assert provider._roots_cache["SPX"] == {d1: "SPXW", d3: "SPX"}
    assert not [c for c in blp.bdp_calls if c[1] == ["OPEN_INT"]]  # the parent decided, no probe
    assert snap.settlement[d3].style == "am" and snap.settlement[d1].style == "pm"
    assert {root_of(c.security) for c in provider._chain("SPX") if c.expiry == d3} == {"SPX"}


@pytest.mark.parametrize("ticker", ["SX5E INDEX"])
def test_the_selection_is_cached_with_the_chain(ticker):
    blp, _, _ = _sx5e_blp()
    provider = BloombergProvider([ticker], blp_module=blp)
    provider._chain(ticker)
    provider._chain(ticker)
    assert len([c for c in blp.bdp_calls if c[1] == ["OPEN_INT"]]) == 1
