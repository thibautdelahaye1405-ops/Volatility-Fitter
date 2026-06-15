"""Offline tests for the Bloomberg provider (volfit.data.bloomberg).

No network / no Terminal: a `FakeBlp` stands in for `xbbg.blp`, returning
DataFrames in the *exact long/tidy shape* the live xbbg build produces
(confirmed against an open Terminal 2026-06-13):

- ``bds(sec, "OPT_CHAIN")`` -> columns ['ticker','field','Security Description'],
  one row per contract, descriptor like 'SPY US 06/18/26 C245 Equity';
- ``bdp(secs, fields)`` -> long columns ['ticker','field','value'], values as
  strings;
- ``bds(sec, "DVD_HIST_ALL")`` -> dividend rows with 'Ex-Date' / 'Dividend
  Amount' / 'Dividend Frequency' / 'Dividend Type'.

pandas is used to build the fixtures (the production code reads frames purely
through column access, so a pandas frame exercises the same path a narwhals
frame would).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from volfit.data.bloomberg import BloombergProvider
from volfit.data.bloomberg_parse import (
    normalize_security,
    parse_descriptor,
    project_dividends,
    session_connected,
    short_blp_reason,
)

TODAY = date.today()


def _opt_chain_frame(descriptors: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["SPY US Equity"] * len(descriptors),
            "field": ["OPT_CHAIN"] * len(descriptors),
            "Security Description": descriptors,
        }
    )


def _bdp_long(values: dict[str, dict[str, object]]) -> pd.DataFrame:
    """Build a long ticker/field/value frame from {security: {field: value}}."""
    rows = []
    for sec, fields in values.items():
        for fld, val in fields.items():
            rows.append({"ticker": sec, "field": fld, "value": val})
    return pd.DataFrame(rows, columns=["ticker", "field", "value"])


class FakeBlp:
    """Minimal xbbg.blp stand-in: records calls, returns canned frames."""

    def __init__(self, chain, bdp_values, dvd=None):
        self._chain = chain
        self._bdp_values = bdp_values
        self._dvd = dvd
        self.bdp_securities: list = []

    def is_connected(self) -> bool:
        return True  # a live Terminal session

    def bds(self, security, field, **_):
        if field == "OPT_CHAIN":
            return self._chain
        if field == "DVD_HIST_ALL":
            if self._dvd is None:
                raise RuntimeError("no dividend entitlement")
            return self._dvd
        raise AssertionError(f"unexpected bds field {field!r}")

    def bdp(self, securities, fields, **_):
        secs = [securities] if isinstance(securities, str) else list(securities)
        self.bdp_securities = secs
        flds = [fields] if isinstance(fields, str) else list(fields)
        wanted = {s: {f: self._bdp_values.get(s, {}).get(f) for f in flds} for s in secs}
        # Drop None cells (a real bdp omits absent fields), mirror long format.
        clean = {
            s: {f: v for f, v in fv.items() if v is not None} for s, fv in wanted.items()
        }
        return _bdp_long(clean)


def _future(days: int) -> str:
    d = date.fromordinal(TODAY.toordinal() + days)
    return f"{d.month:02d}/{d.day:02d}/{d.year % 100:02d}"


def _make_provider(**kwargs):
    near, far = _future(30), _future(120)
    descriptors = [
        f"SPY US {near} C500 Equity",
        f"SPY US {near} P500 Equity",
        f"SPY US {far} C520 Equity",
        "SPY US 01/01/20 C400 Equity",  # already expired -> filtered out
    ]
    bdp_values = {
        "SPY US Equity": {"PX_LAST": 741.75},
        f"SPY US {near} C500 Equity": {
            "BID": "246.10", "ASK": "248.90", "LAST_PRICE": "247.0",
            "VOLUME": "12.0", "OPEN_INT": "340", "OPT_EXER_TYP": "American",
        },
        f"SPY US {near} P500 Equity": {
            "BID": "0.0", "ASK": "0.5", "LAST_PRICE": "0.0",  # 0 bid -> None
            "VOLUME": "nan", "OPEN_INT": "5", "OPT_EXER_TYP": "American",
        },
        f"SPY US {far} C520 Equity": {
            "BID": "230.0", "ASK": "232.0", "LAST_PRICE": "231.0",
            "VOLUME": "3", "OPEN_INT": "10", "OPT_EXER_TYP": "American",
        },
    }
    blp = FakeBlp(_opt_chain_frame(descriptors), bdp_values, kwargs.pop("dvd", None))
    provider = BloombergProvider(["SPY"], blp_module=blp, **kwargs)
    return provider, blp


# --------------------------------------------------------------- descriptor

def test_parse_descriptor():
    p = parse_descriptor("SPY US 06/18/26 C245 Equity")
    assert p is not None
    assert p.expiry == date(2026, 6, 18)
    assert p.strike == 245.0
    assert p.call_put == "C"
    assert parse_descriptor("SPY US 06/18/26 P500.5 Equity").strike == 500.5
    assert parse_descriptor("not an option") is None


# --------------------------------------------------------------- expiries

def test_available_expiries_parses_and_filters():
    provider, _ = _make_provider()
    expiries = provider.available_expiries("SPY")
    assert date(2020, 1, 1) not in expiries  # expired dropped
    assert len(expiries) == 2  # near + far
    assert expiries == sorted(expiries)


def test_available_expiries_respects_max_days():
    provider, _ = _make_provider(max_days=60)  # far (120d) excluded
    assert len(provider.available_expiries("SPY")) == 1


# --------------------------------------------------------------- chain

def test_fetch_chain_builds_quotes_and_spot():
    provider, _ = _make_provider()
    snap = provider.fetch_chain("SPY")
    assert snap.spot == 741.75
    assert snap.exercise_style == "american"  # from OPT_EXER_TYP
    by_strike = {(q.strike, q.call_put): q for q in snap.quotes}
    near_call = by_strike[(500.0, "C")]
    assert near_call.bid == 246.10 and near_call.ask == 248.90
    assert near_call.volume == 12 and near_call.open_interest == 340
    # 0-bid put: bid -> None, NaN volume -> None, ask kept.
    near_put = by_strike[(500.0, "P")]
    assert near_put.bid is None and near_put.ask == 0.5 and near_put.volume is None


def test_fetch_chain_only_bdps_selected_expiries():
    provider, blp = _make_provider()
    near = provider.available_expiries("SPY")[0]
    snap = provider.fetch_chain("SPY", [near])
    # Only the two near contracts were priced (not the far one).
    assert len(blp.bdp_securities) == 2
    assert {q.expiry for q in snap.quotes} == {near}


def test_fetch_chain_no_contracts_raises():
    provider, _ = _make_provider()
    with pytest.raises(ValueError):
        provider.fetch_chain("SPY", [date(2099, 1, 1)])


# --------------------------------------------------------------- dividends

def _dvd_frame(rows: list[tuple[date, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["SPY US Equity"] * len(rows),
            "field": ["DVD_HIST_ALL"] * len(rows),
            "Ex-Date": [r[0] for r in rows],
            "Dividend Amount": [r[1] for r in rows],
            "Dividend Frequency": [r[2] for r in rows],
            "Dividend Type": ["Income"] * len(rows),
        }
    )


def test_dividend_schedule_prefers_future_declared():
    fut = date.fromordinal(TODAY.toordinal() + 40)
    dvd = _dvd_frame([(fut, 1.85, "Quarter"), (date(2025, 3, 20), 1.79, "Quarter")])
    provider, _ = _make_provider(dvd=dvd)
    schedule = provider.dividend_schedule("SPY", TODAY)
    assert [d.ex_date for d in schedule] == [fut]
    assert schedule[0].amount == 1.85


def test_dividend_schedule_projects_when_none_future():
    past = date.fromordinal(TODAY.toordinal() - 20)
    dvd = _dvd_frame([(past, 1.80, "Quarter")])
    provider, _ = _make_provider(dvd=dvd, max_days=400)
    schedule = provider.dividend_schedule("SPY", TODAY)
    assert len(schedule) >= 1  # rolled forward quarterly
    assert all(d.ex_date > TODAY for d in schedule)
    assert all(d.amount == 1.80 for d in schedule)


def test_dividend_schedule_best_effort_on_failure():
    provider, _ = _make_provider(dvd=None)  # bds DVD_HIST_ALL raises
    with pytest.warns(UserWarning):
        assert provider.dividend_schedule("SPY", TODAY) == ()


def test_project_dividends_empty_history():
    assert project_dividends([], TODAY, 365) == ()


# --------------------------------------------------------------- feed status

#: A Bloomberg responseError exactly as the pyo3 xbbg raises when the session is
#: up but the request is gated by an account-side workflow review.
_WORKFLOW_ERROR = (
    "Request failed on //blp/refdata::ReferenceDataRequest - Bloomberg "
    "responseError: source=rsfrdsvc2; category=LIMIT; code=-4002; "
    "subcategory=WORKFLOW_REVIEW_NEEDED; message=Workflow review needed."
)


class _RefusingBlp:
    """xbbg stub whose data requests fail; ``connected`` toggles whether a
    blpapi session exists (connected-but-refused vs. no-Terminal)."""

    def __init__(self, connected: bool):
        self._connected = connected

    def is_connected(self) -> bool:
        return self._connected

    def bds(self, *_a, **_k):
        raise RuntimeError(_WORKFLOW_ERROR)  # a fully-gated account refuses bds too

    def bdp(self, *_a, **_k):
        raise RuntimeError(_WORKFLOW_ERROR)


def test_feed_status_green_when_connected_no_billable_probe():
    """A connected session reads green WITHOUT issuing any billable bdp/bds — the
    30 s status poll must never consume the Bloomberg daily quota (the bug that
    drained the cap)."""
    provider, blp = _make_provider()
    assert provider.feed_status() == ("green", "real-time (Terminal)")
    assert blp.bdp_securities == []  # feed_status made NO reference-data request


def test_feed_status_surfaces_refusal_from_last_fetch():
    """The refusal reason is surfaced from the last ON-DEMAND fetch, not from a
    status probe: a connected-but-ungated session reads green until a real fetch
    is refused, then the light goes red with the real Bloomberg reason."""
    provider = BloombergProvider(["SPY"], blp_module=_RefusingBlp(connected=True))
    # No fetch yet -> connected session reads green (and issued no probe).
    assert provider.feed_status() == ("green", "real-time (Terminal)")
    # An on-demand fetch is refused -> the reason is cached onto the light.
    with pytest.raises(Exception):
        provider.fetch_chain("SPY")
    assert provider.feed_status() == ("red", "workflow review needed")


def test_feed_status_no_session_reports_no_terminal():
    provider = BloombergProvider(["SPY"], blp_module=_RefusingBlp(connected=False))
    assert provider.feed_status() == ("red", "no Terminal")


def test_successful_fetch_clears_cached_refusal():
    """A later successful on-demand fetch clears a stale refusal so the light
    recovers to green (e.g. once the daily cap resets)."""
    provider, _ = _make_provider()
    provider._last_error = "daily capacity reached"  # a stale refusal on the light
    provider.fetch_chain("SPY")  # a successful on-demand fetch
    assert provider.feed_status() == ("green", "real-time (Terminal)")


def test_short_blp_reason_maps_subcategory():
    assert short_blp_reason(RuntimeError(_WORKFLOW_ERROR)) == "workflow review needed"
    assert short_blp_reason(RuntimeError("subcategory=NOT_ENTITLED;")) == "not entitled"
    # Unknown subcategory -> humanized token; no subcategory -> trimmed message.
    assert short_blp_reason(RuntimeError("subcategory=SOME_NEW_STATE;")) == "some new state"
    assert short_blp_reason(RuntimeError("boom")) == "boom"


def test_session_connected_guards_missing_probe():
    assert session_connected(object()) is False  # stub without is_connected()
    assert session_connected(_RefusingBlp(connected=True)) is True


# --------------------------------------------------------------- symbol search

def test_normalize_security():
    assert normalize_security("NVDA US<equity>") == "NVDA US Equity"
    assert normalize_security("SPX<index>") == "SPX Index"
    assert normalize_security("NVDA US Equity") == "NVDA US Equity"  # already clean


def test_search_symbols_falls_back_without_blpapi(monkeypatch):
    """No instruments service available -> base substring/echo search."""
    provider, _ = _make_provider()
    # Force the live path to fail fast so the base fallback is exercised.
    monkeypatch.setattr(
        BloombergProvider, "_instrument_search",
        lambda self, blpapi, q, limit: (_ for _ in ()).throw(RuntimeError("no Terminal")),
    )
    matches = provider.search_symbols("NVDA")
    assert any(m.symbol == "NVDA" for m in matches)  # echo fallback still resolves
