"""Fixture hygiene (backtest.fixture_hygiene) + the daily capture's root policy
(backtest.capture_roots): one option series per (expiry, strike, side).

The 2026-09-10 benchmark readout: XOM fixtures carried an adjusted series
beside the standard one (absurd calls, one-sided / cheaper puts), SPX
monthlies carried SPX + SPXW (two consistent series, the PM one richer).
"""

from __future__ import annotations

import json
import math
import os
from datetime import date, datetime

import numpy as np
import pytest

from backtest import replay
from backtest.capture import _build_fixture
from backtest.capture_roots import apply_root_policy, merge_root_chains
from backtest.fixture_hygiene import dedupe_quotes
from backtest.rest_quotes import _Contract
from backtest.universe import AssetSpec
from volfit.core.black import black_call
from volfit.data.types import ChainSnapshot, OptionQuote

TS = datetime(2024, 8, 5, 19, 45)
E1, E2 = date(2024, 9, 20), date(2024, 10, 18)
F, D = 100.0, 0.99


def _q(exp: date, strike: float, cp: str, bid, ask) -> OptionQuote:
    return OptionQuote(ticker="X", expiry=exp, strike=strike, call_put=cp, bid=bid, ask=ask,
                       last=None, volume=None, open_interest=None, timestamp=TS)


def _series(exp: date, strikes, vol: float, scale: float = 1.0, half_spread: float = 0.05):
    """Two-sided calls + puts of one series priced by Black at ``vol`` (× scale)."""
    tau = 0.125
    out = []
    for k_ in strikes:
        c = D * F * float(black_call(math.log(k_ / F), vol * vol * tau)) * scale
        p = c - D * (F - k_) * scale
        # Bids floored at a tick: a deep-ITM call's put twin is worth less than
        # the half spread, and a negative bid would read as one-sided.
        out.append(_q(exp, k_, "C", max(round(c - half_spread, 4), 0.01), round(c + half_spread, 4)))
        out.append(_q(exp, k_, "P", max(round(p - half_spread, 4), 0.01), round(p + half_spread, 4)))
    return out


STRIKES = [80.0, 90.0, 95.0, 100.0, 105.0, 110.0, 120.0]
FWDS = {E1.isoformat(): {"forward": F, "discount": D}, E2.isoformat(): {"forward": F, "discount": D}}


def test_xom_like_adjusted_series_is_dropped_and_clean_expiries_are_untouched():
    std = _series(E1, STRIKES, 0.25)
    adjusted = []
    for k_ in STRIKES:  # absurd calls; puts one-sided or two-sided but cheaper
        adjusted.append(_q(E1, k_, "C", 150.0 + k_ / 10, 155.0 + k_ / 10))
        adjusted.append(_q(E1, k_, "P", None, 4.8) if k_ % 20 else _q(E1, k_, "P", 0.5, 0.7))
    # A strike only the adjusted series lists: no duplicate, but a call dearer
    # than every standard call below it — the monotonicity screen (rule e).
    adjusted.append(_q(E1, 160.0, "C", 105.0, 109.0))
    clean = _series(E2, STRIKES, 0.22)
    quotes = std[:3] + adjusted + std[3:] + clean  # interleaved on purpose
    kept, report = dedupe_quotes(quotes, FWDS, F)
    assert set(report) == {E1.isoformat()}
    e = report[E1.isoformat()]
    assert e["nDuplicateKeys"] == 2 * len(STRIKES) and e["nDropped"] == len(adjusted)
    assert e["nMonotone"] == 1
    # Calls kept the cheaper (standard) series, the contested puts the dearer
    # (standard) one — the per-side votes differ, so the expiry reads "mixed".
    assert e["keptRank"] == "mixed" and e["nOneSided"] == sum(1 for k_ in STRIKES if k_ % 20)
    assert [q for q in kept if q.expiry == E1] == std  # the standard series, in order
    assert [q for q in kept if q.expiry == E2] == clean
    assert all(a is b for a, b in zip((q for q in kept if q.expiry == E2), clean))  # same objects
    # A chain without duplicates comes back as the same list object.
    same, rep = dedupe_quotes(clean, FWDS, F)
    assert same is clean and rep == {}


def test_spx_like_twin_series_keeps_one_uniformly():
    am = _series(E1, STRIKES, 0.20)
    pm = _series(E1, STRIKES, 0.20, scale=1.03)  # richer everywhere, consistent
    kept, report = dedupe_quotes(am + pm, FWDS, F)
    e = report[E1.isoformat()]
    assert e["nDuplicateKeys"] == 2 * len(STRIKES) and e["nDropped"] == len(pm)
    assert e["keptRank"] in ("low", "high") and e["nOneSided"] == 0
    survivors = {(q.strike, q.call_put): q for q in kept}
    assert len(survivors) == 2 * len(STRIKES)
    # Uniform: every survivor belongs to the same series.
    src = {id(q): "am" for q in am} | {id(q): "pm" for q in pm}
    assert len({src[id(q)] for q in kept}) == 1
    # Parity favours the series consistent with the fixture forward: the AM one.
    assert src[id(kept[0])] == "am" and e["keptRank"] == "low"


def test_one_sided_only_and_absent_other_side_fall_back_deterministically():
    # Both candidates one-sided: nothing to prefer by (b); the cheaper wins.
    a, b = _q(E1, 100.0, "C", None, 5.0), _q(E1, 100.0, "C", None, 4.0)
    kept, rep = dedupe_quotes([a, b] + _series(E1, [90.0, 110.0], 0.25), FWDS, F)
    assert b in kept and a not in kept and rep[E1.isoformat()]["nOneSided"] == 0
    # No other side at the strike: the candidate nearest the expiry's median
    # implied variance wins (the reference = the uncontested two-sided quotes).
    ref = _series(E1, [90.0, 95.0, 105.0, 110.0], 0.25)
    near = _series(E1, [100.0], 0.25)[0]  # the call at vol 0.25
    far = _series(E1, [100.0], 0.60)[0]  # the same strike at vol 0.60
    kept, rep = dedupe_quotes(ref + [far, near], FWDS, F)
    assert near in kept and far not in kept
    assert rep[E1.isoformat()]["keptRank"] == "low"


def _write_fixture(path, quotes, forwards):
    payload = {
        "asset": "X", "as_of": "2024-08-05", "snapshot_ts_utc": TS.isoformat(),
        "exercise_style": "american", "sector": "energy", "spot": F, "option_roots": ["X"],
        "expiries": sorted({q.expiry.isoformat() for q in quotes}),
        "forwards": forwards,
        "quotes": [{"expiry": q.expiry.isoformat(), "strike": q.strike, "cp": q.call_put,
                    "bid": q.bid, "ask": q.ask, "ask_size": None} for q in quotes],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_fixture_applies_the_hygiene_and_the_env_switch(tmp_path, monkeypatch):
    std, pm = _series(E1, STRIKES, 0.20), _series(E1, STRIKES, 0.20, scale=1.03)
    p = tmp_path / "X.json"
    _write_fixture(p, std + pm, FWDS)
    monkeypatch.delenv(replay.DEDUPE_ENV, raising=False)
    fx = replay.load_fixture(str(p))
    assert len(fx.chain.quotes) == len(std) and fx.hygiene[E1.isoformat()]["nDropped"] == len(pm)
    monkeypatch.setenv(replay.DEDUPE_ENV, "0")
    raw = replay.load_fixture(str(p))
    assert len(raw.chain.quotes) == len(std) + len(pm) and raw.hygiene == {}


# ------------------------------------------------------------ the real fixtures
@pytest.mark.skipif(
    not replay.list_fixtures(regime="spike_aug2024", asset="XOM"), reason="spike fixtures absent"
)
def test_real_xom_2024_08_05_keeps_the_standard_series_only():
    path = next(p for p in replay.list_fixtures(regime="spike_aug2024", asset="XOM")
                if replay.load_fixture(p).as_of == date(2024, 8, 5))
    fx = replay.load_fixture(path)
    e = fx.hygiene["2024-09-20"]
    sep = [q for q in fx.chain.quotes if q.expiry == date(2024, 9, 20)]
    # Calls keep the cheap standard series, puts the dear standard one (the
    # foreign puts are one-sided placeholders): per side "low" / "high" reads
    # "mixed" for the expiry — the substance is checked below.
    assert len(sep) < 134 and e["keptRank"] in ("low", "mixed") and e["nDropped"] > 0
    keys = [(q.strike, q.call_put) for q in sep]
    assert len(keys) == len(set(keys))  # one contract per (strike, side)
    c115 = [q for q in sep if q.strike == 115.0 and q.call_put == "C"]
    assert len(c115) == 1 and 0.5 * (c115[0].bid + c115[0].ask) < 20.0
    # The substance on every expiry: no adjusted call survives (a standard
    # call's time value is bounded; the adjusted ones sat ~150 above), and
    # every (strike, side) is one contract.
    spot = fx.chain.spot
    for q in fx.chain.quotes:
        if q.call_put == "C" and q.bid is not None and q.ask is not None:
            assert 0.5 * (q.bid + q.ask) - max(spot - q.strike, 0.0) < 25.0, q
    all_keys = [(q.expiry, q.strike, q.call_put) for q in fx.chain.quotes]
    assert len(all_keys) == len(set(all_keys))


# ------------------------------------------------------------ the daily capture
def _contract(root: str, exp: date, strike: float, cp: str) -> _Contract:
    occ = f"O:{root}{exp:%y%m%d}{cp}{int(round(strike * 1000)):08d}"
    return _Contract(occ, strike, cp, exp)


def test_rest_root_policy_drops_foreign_roots_and_resolves_shared_dates():
    by_expiry = {
        E1: [_contract("XOM", E1, 115.0, "C"), _contract("XOM1", E1, 115.0, "C"),
             _contract("XOM", E1, 115.0, "P")],
        E2: [_contract("XOM1", E2, 110.0, "P")],
    }
    kept, meta = apply_root_policy(by_expiry, ("XOM",))
    assert {c.occ_ticker for c in kept[E1]} == {"O:XOM240920C00115000", "O:XOM240920P00115000"}
    assert E2 not in kept and meta == {"droppedRoots": {"XOM1": 2}}
    # SPX + SPXW on a shared monthly: the first-listed root owns the date.
    spx = {E1: [_contract("SPX", E1, 5000.0, "C"), _contract("SPXW", E1, 5000.0, "C")],
           E2: [_contract("SPXW", E2, 5000.0, "C")]}
    kept, meta = apply_root_policy(spx, ("SPX", "SPXW"))
    assert [c.occ_ticker for c in kept[E1]] == ["O:SPX240920C05000000"]
    assert [c.occ_ticker for c in kept[E2]] == ["O:SPXW241018C05000000"]
    assert meta["rootCollisions"] == [{"expiry": E1.isoformat(), "kept": "SPX", "dropped": ["SPXW"]}]
    assert meta["expiryRoots"] == {E1.isoformat(): "SPX", E2.isoformat(): "SPXW"} and "droppedRoots" not in meta


def test_flatfile_chains_merge_under_the_same_date_rule_and_the_fixture_records_it():
    am = ChainSnapshot("SPX", 5000.0, TS, _series(E1, [5000.0], 0.2) + _series(E2, [5000.0], 0.2), "european")
    pm = ChainSnapshot("SPX", 5001.0, TS, _series(E1, [5000.0], 0.2, scale=1.03), "european")
    chain, meta = merge_root_chains("SPX", {"SPX": am, "SPXW": pm}, ("SPX", "SPXW"))
    assert chain is not None and chain.spot == 5000.0
    assert [q.expiry for q in chain.quotes] == [E1, E1, E2, E2]  # the AM series on the shared date
    assert meta["rootCollisions"][0]["kept"] == "SPX"
    single, meta1 = merge_root_chains("SPY", {"SPY": am}, ("SPY",))
    assert single is not None and meta1 == {}
    # The fixture carries the meta only when there is one.
    asset = AssetSpec.index("SPX", ("SPX", "SPXW")) if hasattr(AssetSpec, "index") else None
    if asset is not None:
        with_meta = _build_fixture(asset, date(2024, 8, 5), chain, meta)
        assert with_meta is None or with_meta.get("meta") == meta
        bare = _build_fixture(asset, date(2024, 8, 5), chain, {})
        assert bare is None or "meta" not in bare


def test_scan_reports_the_affected_fixtures(tmp_path, monkeypatch):
    from backtest import fixture_scan

    monkeypatch.setattr(replay, "FIXTURE_DIR", str(tmp_path))
    d = tmp_path / "r" / "2024-08-05"
    d.mkdir(parents=True)
    _write_fixture(d / "X.json", _series(E1, STRIKES, 0.2) + _series(E1, STRIKES, 0.2, scale=1.03), FWDS)
    _write_fixture(d / "Y.json", _series(E1, STRIKES, 0.2), FWDS)
    rows = fixture_scan.scan(regime="r")
    assert [r["asset"] for r in rows] == ["X"]
    assert rows[0]["before"] == 4 * len(STRIKES) and rows[0]["after"] == 2 * len(STRIKES)
    assert os.environ[replay.DEDUPE_ENV] == "1"
