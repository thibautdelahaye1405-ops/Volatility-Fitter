"""The Bloomberg chain listing cached per exchange day ON DISK
(volfit.data.bloomberg_listing) — under a tmp ``VOLFIT_CACHE_DIR``.

A restart inside the day must not re-list (three metered bds per ticker; on
a monthly unique-securities budget every listing re-touches thousands of
securities), a new day must, a corrupt or foreign file must be tolerated,
``refresh_contracts`` must drop memory AND the file, and a test fake must
never touch the shared cache directory.
"""

from __future__ import annotations

from datetime import date, timedelta

from tests.test_bloomberg import FakeBlp, _make_provider, _opt_chain_frame
from tests.test_bloomberg_roots import _sx5e_blp
from volfit.data.bloomberg import BloombergProvider
from volfit.data.bloomberg_listing import Listing, drop_listings, listing_path, load_listing, save_listing
from volfit.data.bloomberg_parse import ParsedOption
from volfit.data.cache_dir import cache_dir

DAY = date(2026, 9, 24)


class RefusingBlp:
    """A connected Terminal that refuses everything — a listing served from the
    file must never ask it."""

    def is_connected(self) -> bool:
        return True

    def bds(self, *_a, **_k):
        raise AssertionError("bds must not be called: the listing is on disk")

    def bdp(self, *_a, **_k):
        raise AssertionError("bdp must not be called")


def _dir(monkeypatch, tmp_path):
    monkeypatch.setenv("VOLFIT_CACHE_DIR", str(tmp_path))
    directory = cache_dir("bloomberg")
    assert directory == tmp_path / "bloomberg"
    return directory


def test_listing_persists_per_exchange_day_and_serves_a_restart_without_bds(monkeypatch, tmp_path):
    directory = _dir(monkeypatch, tmp_path)
    provider, blp = _make_provider(listing_dir=directory, exchange_day=lambda: DAY)
    expiries = provider.available_expiries("SPY")
    path = listing_path(directory, "SPY", DAY)
    assert path.name == "SPY_2026-09-24.json" and path.exists()
    assert sum(1 for c in blp.bds_calls if c[1] == "OPT_CHAIN") == 1
    # a fresh provider (a restart) the same day: served from the file, no bds at all
    again = BloombergProvider(["SPY"], blp_module=RefusingBlp(), listing_dir=directory, exchange_day=lambda: DAY)
    assert again.available_expiries("SPY") == expiries
    assert [c.security for c in again._chain("SPY")] == [c.security for c in provider._chain("SPY")]
    assert again.feed_status()[0] == "green"  # a disk hit neither records nor clears anything
    # the next exchange day ignores yesterday's file and re-lists (a new file)
    later, blp2 = _make_provider(listing_dir=directory, exchange_day=lambda: DAY + timedelta(days=1))
    later.available_expiries("SPY")
    assert sum(1 for c in blp2.bds_calls if c[1] == "OPT_CHAIN") == 1
    assert listing_path(directory, "SPY", DAY + timedelta(days=1)).exists() and path.exists()


def test_the_kept_roots_survive_the_round_trip(monkeypatch, tmp_path):
    directory = _dir(monkeypatch, tmp_path)
    blp, d2, d3 = _sx5e_blp()
    provider = BloombergProvider(["SX5E INDEX"], blp_module=blp, listing_dir=directory, exchange_day=lambda: DAY)
    provider._chain("SX5E INDEX")
    assert listing_path(directory, "SX5E INDEX", DAY).name == "SX5E_INDEX_2026-09-24.json"
    again = BloombergProvider(["SX5E INDEX"], blp_module=RefusingBlp(), listing_dir=directory, exchange_day=lambda: DAY)
    again._chain("SX5E INDEX")
    assert again._roots_cache["SX5E INDEX"] == {d2: "WSX5EB", d3: "SX5E"}
    assert again._settlement("SX5E INDEX", [d2])[d2].style == "pm"  # read off the restored root


def test_corrupt_or_foreign_files_are_ignored_and_rewritten(monkeypatch, tmp_path):
    directory = _dir(monkeypatch, tmp_path)
    path = listing_path(directory, "SPY", DAY)
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    provider, blp = _make_provider(listing_dir=directory, exchange_day=lambda: DAY)
    provider.available_expiries("SPY")
    assert sum(1 for c in blp.bds_calls if c[1] == "OPT_CHAIN") == 1  # re-listed
    assert load_listing(directory, "SPY", DAY) is not None  # and rewritten, readable
    path.write_text('{"format": 999, "day": "2026-09-24", "contracts": []}', encoding="utf-8")
    assert load_listing(directory, "SPY", DAY) is None  # a foreign format reads as missing
    assert load_listing(directory, "SPY", DAY + timedelta(days=1)) is None  # another day: missing
    assert load_listing(None, "SPY", DAY) is None and save_listing(None, "SPY", Listing(DAY, [], {})) is None


def test_refresh_drops_memory_and_the_files(monkeypatch, tmp_path):
    directory = _dir(monkeypatch, tmp_path)
    provider, blp = _make_provider(listing_dir=directory, exchange_day=lambda: DAY)
    provider.available_expiries("SPY")
    other = Listing(DAY, [ParsedOption("SPY US 10/16/26 C500 Equity", date(2026, 10, 16), 500.0, "C")], {})
    save_listing(directory, "SPY US", other)  # a sibling stem must survive a per-ticker drop
    provider.refresh_chain_cache("SPY")
    assert not listing_path(directory, "SPY", DAY).exists()
    assert listing_path(directory, "SPY US", DAY).exists()
    provider.available_expiries("SPY")  # re-listed (memory + file gone)
    assert sum(1 for c in blp.bds_calls if c[1] == "OPT_CHAIN") == 2
    provider.refresh_contracts()  # the day-roll hook: everything, memory and disk
    assert list(directory.glob("*.json")) == []
    assert drop_listings(directory) == 0 and drop_listings(None) == 0


def test_a_fake_module_never_touches_the_shared_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("VOLFIT_CACHE_DIR", str(tmp_path))
    provider = BloombergProvider(["SPY"], blp_module=FakeBlp(_opt_chain_frame([]), {}))
    assert provider._listing_dir is None  # "auto" persists only with the real xbbg
    provider.available_expiries("SPY")
    assert list(tmp_path.rglob("*.json")) == []
    assert BloombergProvider(["SPY"], blp_module=RefusingBlp(), listing_dir=None)._listing_dir is None
