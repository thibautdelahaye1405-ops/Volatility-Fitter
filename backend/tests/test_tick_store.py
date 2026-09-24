"""The tick store (volfit.data.tick_store): changed ticks only, the latest
table, the book at an instant, the meta / heartbeat readers, the daily file.
All offline (a temp SQLite file)."""

from __future__ import annotations

from datetime import date, datetime

from volfit.data.tick_store import TickStore, daily_path, ns_of, to_ns

T1 = datetime(2026, 9, 18, 15, 45, 0)
T2 = datetime(2026, 9, 18, 15, 45, 30)
T3 = datetime(2026, 9, 18, 15, 46, 10)


def test_to_ns_infers_the_unit_and_ns_of_is_exact():
    from datetime import timezone

    s = int(T1.replace(tzinfo=timezone.utc).timestamp())  # 2026-09-18T15:45:00Z in seconds
    assert to_ns(s) == s * 10**9
    assert to_ns(s * 10**3) == s * 10**9  # milliseconds
    assert to_ns(s * 10**6) == s * 10**9  # microseconds
    assert to_ns(s * 10**9 + 7) == s * 10**9 + 7  # nanoseconds pass through exactly
    assert to_ns(None) is None and to_ns("x") is None
    assert ns_of(T1) == s * 10**9


def test_fold_appends_only_changed_ticks_and_upserts_latest(tmp_path):
    with TickStore(tmp_path / "t.sqlite") as ts:
        assert ts.fold([("O:A", 1.0, 1.2, ns_of(T1)), ("O:B", 2.0, 2.2, ns_of(T1))], seen_at=100.0) == 2
        assert ts.fold([("O:A", 1.0, 1.2, ns_of(T1)), ("O:B", 2.0, 2.2, ns_of(T1))], seen_at=101.0) == 0  # unchanged
        assert ts.fold([("O:A", 1.1, 1.2, ns_of(T2))], seen_at=102.0) == 1  # a new bid
        assert ts.tick_count() == 3 and ts.latest_count() == 2
        assert ts.latest_book() == {"O:A": (1.1, 1.2, ns_of(T2)), "O:B": (2.0, 2.2, ns_of(T1))}
        assert ts.newest_ts_ns() == ns_of(T2)
        # a stampless tick is keyed at the wall clock of the fold
        assert ts.fold([("O:C", None, 0.5, None)], seen_at=103.0) == 1
        assert ts.latest_book()["O:C"] == (None, 0.5, 103 * 10**9)


def test_reopen_keeps_the_dedupe_memory(tmp_path):
    path = tmp_path / "t.sqlite"
    with TickStore(path) as ts:
        ts.fold([("O:A", 1.0, 1.2, ns_of(T1))])
    with TickStore(path) as ts:  # a restarted recorder does not re-append its book
        assert ts.fold([("O:A", 1.0, 1.2, ns_of(T1))]) == 0
        assert ts.fold([("O:A", 1.0, 1.3, ns_of(T2))]) == 1
        assert ts.tick_count() == 2


def test_book_at_is_the_last_tick_at_or_before_the_instant_per_contract(tmp_path):
    with TickStore(tmp_path / "t.sqlite") as ts:
        ts.fold([("O:A", 1.0, 1.2, ns_of(T1)), ("O:B", 2.0, 2.2, ns_of(T2))])
        ts.fold([("O:A", 1.5, 1.7, ns_of(T3))])
        assert ts.book_at(datetime(2026, 9, 18, 15, 44)) == {}
        assert ts.book_at(T1) == {"O:A": (1.0, 1.2, ns_of(T1))}
        assert ts.book_at(T2) == {"O:A": (1.0, 1.2, ns_of(T1)), "O:B": (2.0, 2.2, ns_of(T2))}
        assert ts.book_at(T3) == {"O:A": (1.5, 1.7, ns_of(T3)), "O:B": (2.0, 2.2, ns_of(T2))}
        assert ts.book_at(ns_of(T3) - 1)["O:A"] == (1.0, 1.2, ns_of(T1))  # epoch ns accepted


def test_meta_stats_and_heartbeat(tmp_path):
    with TickStore(tmp_path / "t.sqlite") as ts:
        assert ts.heartbeat_age_s(now=1000.0) is None and ts.stats() is None and ts.plan() is None
        ts.heartbeat(now=1000.0)
        assert ts.heartbeat_age_s(now=1012.0) == 12.0
        ts.set_meta("stats", {"acknowledged": 6, "ackedByTicker": {"SPY": 6}})
        ts.set_meta("plan", {"tickers": ["SPY"]})
        ts.set_meta("pid", "123")
        assert ts.stats() == {"acknowledged": 6, "ackedByTicker": {"SPY": 6}}
        assert ts.plan() == {"tickers": ["SPY"]}
        assert ts.get_meta("pid") == "123" and ts.get_meta("nope", "d") == "d"
        ts.set_meta("stats", "not json")
        assert ts.stats() is None
        ts.delete_meta("pid")
        assert "pid" not in ts.meta()


def test_daily_path_names_the_exchange_day(tmp_path):
    assert daily_path(tmp_path, date(2026, 9, 24)) == tmp_path / "ticks_2026-09-24.sqlite"
    assert daily_path(tmp_path).name.startswith("ticks_") and daily_path(tmp_path).suffix == ".sqlite"
