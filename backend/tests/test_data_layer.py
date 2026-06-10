"""Data layer tests: synthetic chains, parity forwards, SQLite round trips.

No network: everything runs off SyntheticProvider (volfit.data.provider) and
a temporary SQLite file (pytest tmp_path).
"""

from datetime import date, datetime, timedelta

import pytest

from volfit.data import (
    OptionQuote,
    SyntheticProvider,
    Universe,
    VolStore,
    implied_forwards,
    list_universes,
    load_universe,
    save_universe,
)

REF_DATE = date(2025, 3, 21)


@pytest.fixture()
def chain():
    return SyntheticProvider(reference_date=REF_DATE, seed=7).fetch_chain("ALPHA")


# -- synthetic provider ------------------------------------------------------


def test_synthetic_chain_is_well_formed(chain):
    assert chain.ticker == "ALPHA"
    assert chain.spot > 0
    assert len(chain.expiries()) == 4  # ~1M, 3M, 6M, 1Y
    flags = {q.call_put for q in chain.quotes}
    assert flags == {"C", "P"}
    # Every quote is two-sided with a strictly positive spread and a mid.
    for q in chain.quotes:
        assert q.bid is not None and q.ask is not None
        assert q.ask > q.bid
        assert q.bid > 0
        assert q.mid is not None


def test_synthetic_provider_is_deterministic():
    a = SyntheticProvider(reference_date=REF_DATE, seed=7).fetch_chain("ALPHA")
    b = SyntheticProvider(reference_date=REF_DATE, seed=7).fetch_chain("ALPHA")
    assert a == b


# -- implied forwards --------------------------------------------------------


def test_parity_regression_recovers_forward(chain):
    forwards = implied_forwards(chain)
    assert set(forwards) == set(chain.expiries())
    for fwd in forwards.values():
        # Zero rates in the synthetic world: F = spot, D = 1.
        assert fwd.forward == pytest.approx(chain.spot, rel=1e-3)
        assert fwd.discount == pytest.approx(1.0, abs=1e-3)
        assert fwd.n_strikes >= 3
        assert fwd.residual_rms < 1e-6 * chain.spot


def test_forward_skipped_with_too_few_pairs(chain):
    from volfit.data import implied_forward
    from volfit.data.types import ChainSnapshot

    expiry = chain.expiries()[0]
    few = [q for q in chain.quotes_for(expiry)][:4]  # 2 strikes x (C, P)
    small = ChainSnapshot(chain.ticker, chain.spot, chain.timestamp, few)
    assert implied_forward(small, expiry) is None


# -- SQLite store ------------------------------------------------------------


def test_snapshot_round_trip(tmp_path, chain):
    with VolStore(tmp_path / "vol.db") as store:
        sid = store.save_snapshot(chain)
        loaded = store.load_snapshot(sid)
    assert len(loaded.quotes) == len(chain.quotes)
    assert loaded == chain  # exact: floats, ints, dates, timestamps


def test_latest_snapshot(tmp_path, chain):
    later = SyntheticProvider(
        reference_date=REF_DATE + timedelta(days=1), seed=7
    ).fetch_chain("ALPHA")
    with VolStore(tmp_path / "vol.db") as store:
        store.save_snapshot(chain)
        store.save_snapshot(later)
        latest = store.latest_snapshot("ALPHA")
        assert latest is not None
        assert latest.timestamp == later.timestamp
        assert store.latest_snapshot("UNKNOWN") is None


def test_fit_round_trip(tmp_path):
    expiry = REF_DATE + timedelta(days=91)
    params = {"L": -1.2, "R": 0.8, "a": [0.1, -0.02]}
    diags = {"rmse_bp": 1.3, "A_R": 0.92}
    ts = datetime(2025, 3, 21, 17, 0)
    with VolStore(tmp_path / "vol.db") as store:
        fid = store.save_fit("ALPHA", expiry, "lqd", params, diags, created_ts=ts)
        fits = store.load_fits("ALPHA", expiry)
    assert len(fits) == 1
    rec = fits[0]
    assert rec.id == fid
    assert (rec.model, rec.expiry, rec.created_ts) == ("lqd", expiry, ts)
    assert rec.params == params
    assert rec.diagnostics == diags


def test_prior_round_trip_with_label(tmp_path):
    expiry = REF_DATE + timedelta(days=30)
    with VolStore(tmp_path / "vol.db") as store:
        store.save_prior("ALPHA", expiry, "lqd", {"L": -1.0, "R": 0.5}, label="open")
        store.save_prior("ALPHA", expiry, "lqd", {"L": -1.1, "R": 0.6}, label="close")
        priors = store.load_priors("ALPHA", expiry, label="close")
    assert len(priors) == 1
    assert priors[0].label == "close"
    assert priors[0].params == {"L": -1.1, "R": 0.6}


def test_universe_round_trip(tmp_path):
    uni = Universe(name="us-tech", tickers=("ALPHA", "BETA"), min_days=7, max_days=400)
    with VolStore(tmp_path / "vol.db") as store:
        save_universe(store, uni)
        assert list_universes(store) == ["us-tech"]
        assert load_universe(store, "us-tech") == uni
        assert load_universe(store, "missing") is None


def test_universe_expiry_filter():
    uni = Universe(name="u", tickers=("X",), min_days=10, max_days=100)
    expiries = [REF_DATE + timedelta(days=d) for d in (5, 10, 50, 100, 200)]
    kept = uni.filter_expiries(expiries, asof=REF_DATE)
    assert kept == [REF_DATE + timedelta(days=d) for d in (10, 50, 100)]


# -- quote mid semantics -----------------------------------------------------


def test_mid_none_when_missing_or_crossed():
    base = dict(ticker="X", expiry=REF_DATE, strike=100.0, call_put="C")
    assert OptionQuote(**base, bid=None, ask=2.0).mid is None
    assert OptionQuote(**base, bid=2.0, ask=None).mid is None
    assert OptionQuote(**base, bid=2.5, ask=2.0).mid is None  # crossed
    assert OptionQuote(**base, bid=2.0, ask=3.0).mid == pytest.approx(2.5)
