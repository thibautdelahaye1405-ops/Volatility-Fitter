"""One contracts listing per (underlying, ET exchange day), on disk
(volfit.data.massive_listing, 2026-09-24).

A fresh process reads the day's file instead of paginating the reference;
the expiry ladder and the per-expiry contract keys derive from that ONE
listing; another day's file is ignored; a corrupt file is a miss; the write
is atomic; ``refresh_contracts`` drops memory AND the file. An injected fake
HTTP layer never persists unless asked (``listing_cache=True``), so the
offline suites cannot contaminate each other through the cache directory.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from volfit.data.massive import MassiveProvider
from volfit.data.massive_listing import (
    ROW_FIELDS,
    ListingCache,
    exchange_day,
    listing_path,
    load_listing,
    store_listing,
)

TODAY = date.today()


def _row(strike: float, days: int, cp: str = "call") -> dict:
    return {
        "contract_type": cp, "exercise_style": "american",
        "expiration_date": (TODAY + timedelta(days=days)).isoformat(),
        "strike_price": strike, "ticker": f"O:SPY{strike:.0f}{cp[0].upper()}",
        "underlying_ticker": "SPY", "cfi": "OCASPS", "shares_per_contract": 100,  # extra fields dropped
    }


class _Ref:
    def __init__(self, rows):
        self.rows, self.calls = rows, 0

    def __call__(self, url, params):
        assert "/v3/reference/options/contracts" in url
        self.calls += 1
        return {"results": self.rows, "status": "OK"}


def _provider(ref, **kw):
    return MassiveProvider(["SPY"], api_key="k", http_get=ref, listing_cache=True, **kw)


def test_exchange_day_is_new_york_time():
    late = datetime(2026, 9, 24, 3, 30, tzinfo=timezone.utc)  # 23:30 ET on the 23rd
    assert exchange_day(late) == date(2026, 9, 23)
    assert exchange_day(datetime(2026, 9, 24, 14, 0, tzinfo=timezone.utc)) == date(2026, 9, 24)


def test_one_listing_serves_the_ladder_the_keys_and_a_fresh_process(tmp_path, monkeypatch):
    monkeypatch.setenv("VOLFIT_CACHE_DIR", str(tmp_path))
    ref = _Ref([_row(500, 30), _row(500, 30, "put"), _row(520, 120)])
    p = _provider(ref)
    p._note_spot("SPY", 500.0)  # the stream plan is windowed around a centre (2026-09-24)
    exps = p.available_expiries("SPY")
    assert exps == [TODAY + timedelta(days=30), TODAY + timedelta(days=120)]
    keys = p.option_tickers("SPY", exps[:1])
    assert keys == ["O:SPY500C", "O:SPY500P"] and ref.calls == 1  # the keys came off the same listing
    path = listing_path("SPY", exchange_day())
    assert path is not None and path.is_file() and path.parent == tmp_path / "massive"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["underlying"] == "SPY" and payload["day"] == exchange_day().isoformat()
    assert set(payload["rows"][0]) == set(ROW_FIELDS)  # slimmed to what the provider reads

    fresh = _provider(_Ref([]))  # a new process: the fake would answer an EMPTY listing
    fresh._note_spot("SPY", 500.0)
    assert fresh.available_expiries("SPY") == exps  # served from the day's file
    assert fresh.option_tickers("SPY", exps[:1]) == keys and fresh._listings.pulls == 0


def test_another_days_file_is_ignored_and_swept_a_corrupt_one_tolerated(tmp_path, monkeypatch):
    monkeypatch.setenv("VOLFIT_CACHE_DIR", str(tmp_path))
    yesterday = exchange_day() - timedelta(days=1)
    assert store_listing("SPY", yesterday, [_row(400, 5)])
    stale = listing_path("SPY", yesterday)
    assert load_listing("SPY", exchange_day()) is None  # the day is in the name: no match
    ref = _Ref([_row(500, 30)])
    p = _provider(ref)
    assert p.available_expiries("SPY") == [TODAY + timedelta(days=30)] and ref.calls == 1
    assert not stale.exists()  # swept when today's was written
    today_path = listing_path("SPY", exchange_day())
    today_path.write_text("{not json", encoding="utf-8")
    assert load_listing("SPY", exchange_day()) is None
    ref2 = _Ref([_row(510, 30)])
    p2 = _provider(ref2)
    assert p2.available_expiries("SPY") and ref2.calls == 1  # a miss -> pulled, then rewritten
    assert json.loads(today_path.read_text(encoding="utf-8"))["rows"][0]["strike_price"] == 510
    mismatched = {"underlying": "QQQ", "day": exchange_day().isoformat(), "rows": [_row(1, 1)]}
    today_path.write_text(json.dumps(mismatched), encoding="utf-8")
    assert load_listing("SPY", exchange_day()) is None  # the payload must name the same key


def test_refresh_drops_memory_and_the_file_and_refresh_listing_repulls(tmp_path, monkeypatch):
    monkeypatch.setenv("VOLFIT_CACHE_DIR", str(tmp_path))
    ref = _Ref([_row(500, 30)])
    p = _provider(ref)
    p.available_expiries("SPY")
    path = listing_path("SPY", exchange_day())
    assert path.is_file() and ref.calls == 1
    p.refresh_contracts()
    assert not path.exists() and not p._listings.cached("SPY")
    p.available_expiries("SPY")
    assert ref.calls == 2 and path.is_file()
    ref.rows.append(_row(530, 60))  # a new expiry listed mid-session
    assert len(p.available_expiries("SPY")) == 1  # memoised
    p.refresh_listing("SPY")
    assert ref.calls == 3 and len(p.available_expiries("SPY")) == 2


def test_an_injected_fake_never_persists_unless_asked(tmp_path, monkeypatch):
    monkeypatch.setenv("VOLFIT_CACHE_DIR", str(tmp_path))
    ref = _Ref([_row(500, 30)])
    p = MassiveProvider(["SPY"], api_key="k", http_get=ref)  # listing_cache=None -> memory only
    p.available_expiries("SPY")
    assert not (tmp_path / "massive").exists() or not list((tmp_path / "massive").iterdir())
    assert not p._listings.disk
    real = MassiveProvider(["SPY"], api_key="k")
    assert real._listings.disk  # the real HTTP layer persists


def test_empty_pulls_are_never_frozen_and_the_cache_is_thread_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("VOLFIT_CACHE_DIR", str(tmp_path))
    cache = ListingCache(disk=True)
    calls = {"n": 0}

    def pull():
        calls["n"] += 1
        return [] if calls["n"] == 1 else [_row(500, 30)]

    assert cache.get("SPY", pull) == [] and calls["n"] == 1
    assert cache.get("SPY", pull) and calls["n"] == 2  # the empty answer was not memoised
    assert cache.get("SPY", pull) and calls["n"] == 2
    assert cache.get("spy", pull, refresh=True) and calls["n"] == 3  # case-insensitive, explicit re-pull
    import threading

    hits = {"n": 0}

    def slow_pull():
        hits["n"] += 1
        return [_row(1, 1)]

    fresh = ListingCache(disk=False)
    threads = [threading.Thread(target=lambda: fresh.get("QQQ", slow_pull)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert hits["n"] == 1  # one pull under the per-underlying lock
