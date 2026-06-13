"""Yahoo provider, snapshot CLI and provider plumbing tests.

Offline and deterministic: `FakeTicker` mimics the yfinance Ticker surface
the provider relies on (fast_info, history, options, option_chain) with
hand-built pandas DataFrames, so the Yahoo field conventions (0.0 bid means
no quote, NaN volume means missing) are exercised without any network.
The one live test is skipped unless VOLFIT_LIVE is set; the lead runs it
manually.
"""

import importlib.util
import os
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.data import SyntheticProvider, VolStore, YahooProvider

# snapshot.py is a script in backend/, not part of the volfit package: load it
# by path so the test is independent of how pytest set up sys.path.
_SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "snapshot.py"
_spec = importlib.util.spec_from_file_location("snapshot_cli", _SNAPSHOT_PATH)
snapshot_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snapshot_cli)

TODAY = date.today()
NEAR = (TODAY + timedelta(days=30)).isoformat()      # inside max_days
MID = (TODAY + timedelta(days=200)).isoformat()      # inside max_days
FAR = (TODAY + timedelta(days=900)).isoformat()      # beyond default 550
PAST = (TODAY - timedelta(days=5)).isoformat()       # already expired

#: Calls frame: a zero bid (-> None), a zero lastPrice + NaN volume (-> None)
#: and a fully normal row, in Yahoo's column naming.
CALLS = pd.DataFrame(
    {
        "strike": [100.0, 105.0, 110.0],
        "bid": [0.0, 1.0, 0.8],
        "ask": [1.5, 1.4, 1.0],
        "lastPrice": [1.2, 0.0, 0.9],
        "volume": [10.0, float("nan"), 3.0],
        "openInterest": [100.0, 50.0, float("nan")],
    }
)
PUTS = pd.DataFrame(
    {
        "strike": [100.0],
        "bid": [2.0],
        "ask": [2.2],
        "lastPrice": [2.1],
        "volume": [7.0],
        "openInterest": [70.0],
    }
)


class FakeTicker:
    """Offline stand-in for yfinance.Ticker (only the surface volfit uses)."""

    def __init__(
        self,
        fast_info=None,
        options=(NEAR, MID, FAR, PAST),
        history_df=None,
        fail_expiries=(),
    ):
        self.fast_info = {"last_price": 432.10} if fast_info is None else fast_info
        self.options = tuple(options)
        self._history_df = history_df if history_df is not None else pd.DataFrame()
        self._fail_expiries = set(fail_expiries)

    def history(self, period="5d"):
        return self._history_df

    def option_chain(self, expiry):
        if expiry in self._fail_expiries:
            raise RuntimeError(f"boom for {expiry}")
        return SimpleNamespace(calls=CALLS.copy(), puts=PUTS.copy())


def make_provider(ticker=None, **kwargs):
    """YahooProvider over a single shared FakeTicker instance."""
    fake = ticker if ticker is not None else FakeTicker()
    return YahooProvider(["SPY"], ticker_factory=lambda symbol: fake, **kwargs)


# -- field mapping -------------------------------------------------------------


def test_quote_field_mapping():
    chain = make_provider().fetch_chain("SPY")
    assert chain.ticker == "SPY"
    assert chain.spot == pytest.approx(432.10)

    expiry = chain.expiries()[0]
    calls = {q.strike: q for q in chain.quotes_for(expiry) if q.call_put == "C"}
    puts = {q.strike: q for q in chain.quotes_for(expiry) if q.call_put == "P"}

    assert calls[100.0].bid is None          # Yahoo 0.0 bid means no quote
    assert calls[100.0].ask == pytest.approx(1.5)
    assert calls[100.0].volume == 10 and calls[100.0].open_interest == 100
    assert calls[105.0].last is None         # lastPrice 0.0 -> None
    assert calls[105.0].volume is None       # NaN volume -> None
    assert calls[110.0].open_interest is None  # NaN OI -> None
    assert puts[100.0].mid == pytest.approx(2.1)
    assert all(q.timestamp == chain.timestamp for q in chain.quotes)


def test_spot_falls_back_to_history_close():
    hist = pd.DataFrame({"Close": [430.0, 431.5]})
    fake = FakeTicker(fast_info={}, history_df=hist)  # fast_info lookup fails
    chain = make_provider(ticker=fake).fetch_chain("SPY")
    assert chain.spot == pytest.approx(431.5)


def test_spot_unavailable_raises():
    fake = FakeTicker(fast_info={})  # and history is an empty DataFrame
    with pytest.raises(ValueError, match="spot"):
        make_provider(ticker=fake).fetch_chain("SPY")


# -- expiry windowing ----------------------------------------------------------


def test_expiry_window_and_cap():
    chain = make_provider().fetch_chain("SPY")
    isos = [e.isoformat() for e in chain.expiries()]
    assert isos == [NEAR, MID]  # past and beyond-max_days excluded

    capped = make_provider(max_expiries=1).fetch_chain("SPY")
    assert [e.isoformat() for e in capped.expiries()] == [NEAR]

    tight = make_provider(max_days=100).fetch_chain("SPY")
    assert [e.isoformat() for e in tight.expiries()] == [NEAR]


def test_expiry_thinning_spreads_across_window():
    # 12 weekly expiries: first-N would stay inside ~1 month; sqrt-days
    # thinning must keep the nearest and farthest and spread in between.
    weeklies = tuple((TODAY + timedelta(days=7 * i)).isoformat() for i in range(1, 13))
    fake = FakeTicker(options=weeklies)
    chain = make_provider(ticker=fake, max_expiries=4).fetch_chain("SPY")
    isos = [e.isoformat() for e in chain.expiries()]
    assert len(isos) == 4
    assert isos[0] == weeklies[0] and isos[-1] == weeklies[-1]
    spans = [(date.fromisoformat(b) - date.fromisoformat(a)).days
             for a, b in zip(isos[:-1], isos[1:])]
    assert spans[-1] > spans[0]  # denser short end, wider far end


def test_no_listed_options_raises():
    fake = FakeTicker(options=())
    with pytest.raises(ValueError, match="no listed options"):
        make_provider(ticker=fake).fetch_chain("SPY")
    only_far = FakeTicker(options=(FAR, PAST))  # listed but outside the window
    with pytest.raises(ValueError, match="no listed options"):
        make_provider(ticker=only_far).fetch_chain("SPY")


# -- per-expiry failure handling -------------------------------------------------


def test_failing_expiry_is_skipped_with_warning():
    fake = FakeTicker(fail_expiries={MID})
    with pytest.warns(UserWarning, match=MID):
        chain = make_provider(ticker=fake).fetch_chain("SPY")
    assert [e.isoformat() for e in chain.expiries()] == [NEAR]
    assert len(chain.quotes) == len(CALLS) + len(PUTS)


def test_all_expiries_failing_raises():
    fake = FakeTicker(fail_expiries={NEAR, MID})
    with pytest.warns(UserWarning):
        with pytest.raises(ValueError, match="all 2 expiries failed"):
            make_provider(ticker=fake).fetch_chain("SPY")


def test_list_tickers_is_the_watchlist():
    provider = YahooProvider(["SPY", "QQQ"], ticker_factory=lambda symbol: FakeTicker())
    assert provider.list_tickers() == ["SPY", "QQQ"]


# -- snapshot CLI ----------------------------------------------------------------


def test_snapshot_cli_synthetic_round_trip(tmp_path, capsys):
    db = tmp_path / "nested" / "snapshots.sqlite"  # CLI must create parent dirs
    code = snapshot_cli.main(
        ["ALPHA", "BETA", "--provider", "synthetic", "--db", str(db)]
    )
    assert code == 0
    assert "ALPHA: spot" in capsys.readouterr().out

    expected = SyntheticProvider(reference_date=TODAY).fetch_chain("ALPHA")
    with VolStore(db) as store:
        chain = store.latest_snapshot("ALPHA")
        assert chain is not None
        assert len(chain.quotes) == len(expected.quotes)
        assert store.latest_snapshot("BETA") is not None


def test_snapshot_cli_exit_1_when_all_fail(tmp_path, monkeypatch, capsys):
    fake = FakeTicker(options=())  # every fetch_chain raises ValueError

    def broken_provider(name, tickers, max_expiries):
        return YahooProvider(tickers, ticker_factory=lambda symbol: fake)

    monkeypatch.setattr(snapshot_cli, "build_provider", broken_provider)
    code = snapshot_cli.main(["SPY", "QQQ", "--db", str(tmp_path / "x.sqlite")])
    assert code == 1
    assert "ERROR" in capsys.readouterr().err


# -- provider plumbing through the API --------------------------------------------


def test_create_app_honors_injected_provider():
    ref = date(2026, 6, 10)
    provider = SyntheticProvider(reference_date=ref, tickers=("X1", "X2"))
    with TestClient(create_app(reference_date=ref, provider=provider)) as client:
        data = client.get("/universe").json()
    assert data["tickers"] == ["X1", "X2"]
    assert set(data["expiries"]) == {"X1", "X2"}


# -- live (manual) -----------------------------------------------------------------


@pytest.mark.live
@pytest.mark.skipif(
    not os.environ.get("VOLFIT_LIVE"), reason="set VOLFIT_LIVE=1 for live Yahoo test"
)
def test_live_yahoo_spy_chain():
    provider = YahooProvider(["SPY"], max_expiries=2)
    chain = provider.fetch_chain("SPY")
    assert chain.spot > 100
    assert len(chain.quotes) > 50
    expiries = chain.expiries()
    assert 1 <= len(expiries) <= 2
    for expiry in expiries:
        assert 0 < (expiry - TODAY).days <= 550
