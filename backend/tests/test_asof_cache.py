"""Store-first as-of chains (volfit.api.asof_cache, store schema v12).

An ``eod`` / ``intraday`` as-of read consults the VolStore FIRST — the row at
that exact instant from the ticker's source: a series frame, an earlier
reconstruction — and only rebuilds from the provider on a miss, saving the
result under ``ASOF_CACHE_TAG`` so the next read costs zero provider calls.
The as-of picker keeps listing captures only; a stored ``marks`` frame never
shadows a later attempt at real quotes; a recorded request covers an expiry
the feed had nothing for. All offline.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from volfit.api.asof import asof_payload
from volfit.api.asof_cache import is_final
from volfit.api.state import AppState, AsOfSelection
from volfit.data.expiry_time import session_close_utc
from volfit.data.provider import SyntheticProvider
from volfit.data.store import ASOF_CACHE_TAG, SCHEMA_VERSION, VolStore

REF = date(2026, 6, 13)
DAY = date(2026, 6, 12)  # a Friday: its close is final
TS = datetime(2026, 6, 12, 15, 30)  # an intraday instant on that day (UTC-naive)


class Counting(SyntheticProvider):
    """A history-capable synthetic feed that COUNTS its chain fetches. A past
    instant is stamped at the instant; ``kind`` is what history carries;
    ``drop`` expiries are 'not listed at the instant' (absent from the answer)."""

    def __init__(self, kind: str = "quotes", drop: tuple[date, ...] = ()):
        super().__init__(reference_date=REF, tickers=("ALPHA",))
        self.calls = 0
        self.kind = kind
        self.drop = set(drop)

    def historical_modes(self):
        return {"live", "prev_close", "eod", "intraday"}

    def intraday_capable(self):
        return True

    def historical_quote_kind(self):
        return self.kind

    def fetch_chain(self, ticker, expiries=None, as_of=None):
        self.calls += 1
        snap = super().fetch_chain(ticker, expiries, None)
        if as_of is None or as_of.mode == "live":
            return snap
        stamp = session_close_utc(as_of.on) if as_of.mode == "eod" else as_of.ts
        quotes = [q for q in snap.quotes if q.expiry not in self.drop]
        if self.kind == "marks":
            quotes = [replace(q, bid=q.last, ask=q.last) for q in quotes]
        return replace(snap, timestamp=stamp, quotes=quotes, quote_kind=self.kind)


def _state(db, prov, source="massive") -> AppState:
    return AppState(REF, providers={source: prov}, active_source=source, store_path=None if db is None else str(db))


def _quotes(snap):
    return sorted((q.expiry, q.strike, q.call_put, q.bid, q.ask, q.last) for q in snap.quotes)


def _rows_at(db, ts):
    with VolStore(db) as store:
        return store.conn.execute(
            "SELECT series_id, quote_kind FROM snapshots WHERE ticker = 'ALPHA' AND ts = ?",
            (ts.isoformat(),),
        ).fetchall()


# ------------------------------------------------------------ zero calls

def test_second_eod_read_of_the_same_day_costs_no_provider_call(tmp_path):
    db = tmp_path / "asof.sqlite"
    prov = Counting()
    first = _state(db, prov)
    first.set_as_of(AsOfSelection(mode="eod", on=DAY))
    chain = first.snapshot("ALPHA")
    assert prov.calls == 1 and chain.quotes
    # A fresh process on the same store: the instant is served from the store.
    second = _state(db, prov)
    second.set_as_of(AsOfSelection(mode="eod", on=DAY))
    again = second.snapshot("ALPHA")
    assert prov.calls == 1
    assert _quotes(again) == _quotes(chain)  # byte-identical quotes
    assert again.timestamp == session_close_utc(DAY)  # keyed at the session close
    assert _rows_at(db, session_close_utc(DAY)) == [(ASOF_CACHE_TAG, "quotes")]


def test_second_intraday_read_of_the_same_instant_costs_no_provider_call(tmp_path):
    db = tmp_path / "asof.sqlite"
    prov = Counting()
    first = _state(db, prov)
    first.set_as_of(AsOfSelection(mode="intraday", ts=TS))
    chain = first.snapshot("ALPHA")
    assert prov.calls == 1
    second = _state(db, prov)
    second.set_as_of(AsOfSelection(mode="intraday", ts=TS))
    assert _quotes(second.snapshot("ALPHA")) == _quotes(chain) and prov.calls == 1
    # Another instant is another key: it is fetched.
    second.set_as_of(AsOfSelection(mode="intraday", ts=TS + timedelta(minutes=5)))
    second.snapshot("ALPHA")
    assert prov.calls == 2


def test_a_series_frame_is_reused_by_the_smile_lens_as_of(tmp_path):
    """The Series lens saved the instant as a frame (series_id set): the
    Smile lens's as-of at that instant reads it — no rebuild."""
    db = tmp_path / "asof.sqlite"
    prov = Counting()
    frame = replace(prov.fetch_chain("ALPHA"), timestamp=TS)
    prov.calls = 0
    with VolStore(db) as store:
        store.save_snapshot(frame, source="massive", series_id="series-1")
    state = _state(db, prov)
    state.set_as_of(AsOfSelection(mode="intraday", ts=TS))
    assert _quotes(state.snapshot("ALPHA")) == _quotes(frame) and prov.calls == 0


def test_the_picker_still_lists_no_reconstructed_frame(tmp_path):
    db = tmp_path / "asof.sqlite"
    prov = Counting()
    state = _state(db, prov)
    state.set_as_of(AsOfSelection(mode="eod", on=DAY))
    state.snapshot("ALPHA")
    instant = session_close_utc(DAY)
    with VolStore(db) as store:
        assert store.list_snapshots(["ALPHA"], source="massive") == []  # not a capture
        assert store.snapshot_at("ALPHA", instant, source="massive") is None  # a replay never lands on it
        assert store.snapshot_at("ALPHA", instant, source="massive", include_series=True) is not None
    state.set_as_of(AsOfSelection())
    assert [d for d in asof_payload(state)["days"] if d["hasCaptures"]] == []


# --------------------------------------------------------------- coverage

def test_a_partial_store_row_triggers_a_fetch_then_serves(tmp_path):
    db = tmp_path / "asof.sqlite"
    prov = Counting()
    full = replace(prov.fetch_chain("ALPHA"), timestamp=TS)
    prov.calls = 0
    keep = sorted(full.expiries())[:2]  # a frame holding two of the four rungs
    partial = replace(full, quotes=[q for q in full.quotes if q.expiry in keep])
    with VolStore(db) as store:
        store.save_snapshot(partial, source="massive", series_id="series-1")
    state = _state(db, prov)
    state.set_as_of(AsOfSelection(mode="intraday", ts=TS))
    chain = state.snapshot("ALPHA")
    assert prov.calls == 1 and len(chain.expiries()) == 4  # the frame did not cover: fetched
    again = _state(db, prov)
    again.set_as_of(AsOfSelection(mode="intraday", ts=TS))
    assert _quotes(again.snapshot("ALPHA")) == _quotes(chain) and prov.calls == 1


def test_a_recorded_request_covers_an_expiry_the_feed_had_nothing_for(tmp_path):
    """A weekly listed after the instant is absent from the rebuilt chain; the
    saved request says it WAS asked for, so the next read does not refetch."""
    db = tmp_path / "asof.sqlite"
    probe = Counting()
    missing = sorted(probe.fetch_chain("ALPHA").expiries())[-1]
    prov = Counting(drop=(missing,))
    state = _state(db, prov)
    state.set_as_of(AsOfSelection(mode="intraday", ts=TS))
    chain = state.snapshot("ALPHA")
    assert prov.calls == 1 and missing not in chain.expiries()
    again = _state(db, prov)
    again.set_as_of(AsOfSelection(mode="intraday", ts=TS))
    assert _quotes(again.snapshot("ALPHA")) == _quotes(chain) and prov.calls == 1
    with VolStore(db) as store:
        meta = store.snapshot_meta_at("ALPHA", TS, source="massive", include_series=True, exact=True)
        assert meta is not None and meta.request is not None and missing in meta.request


# ------------------------------------------------------------- quote kind

def test_marks_never_shadow_quotes(tmp_path):
    db = tmp_path / "asof.sqlite"
    marks = Counting(kind="marks")
    state = _state(db, marks)
    state.set_as_of(AsOfSelection(mode="intraday", ts=TS))
    state.snapshot("ALPHA")
    assert marks.calls == 1 and _rows_at(db, TS) == [(ASOF_CACHE_TAG, "marks")]
    # A marks-only provider reuses its marks row (it cannot do better).
    again = _state(db, marks)
    again.set_as_of(AsOfSelection(mode="intraday", ts=TS))
    again.snapshot("ALPHA")
    assert marks.calls == 1
    # The NBBO history is back: the stored marks must not pre-empt real quotes.
    quotes = Counting(kind="quotes")
    third = _state(db, quotes)
    third.set_as_of(AsOfSelection(mode="intraday", ts=TS))
    chain = third.snapshot("ALPHA")
    assert quotes.calls == 1 and chain.quote_kind == "quotes"
    assert sorted(_rows_at(db, TS)) == [(ASOF_CACHE_TAG, "marks"), (ASOF_CACHE_TAG, "quotes")]
    # From now on the quotes row wins, whichever provider kind asks.
    fourth = _state(db, quotes)
    fourth.set_as_of(AsOfSelection(mode="intraday", ts=TS))
    assert fourth.snapshot("ALPHA").quote_kind == "quotes" and quotes.calls == 1


def test_a_marks_fetch_never_duplicates_an_existing_row(tmp_path):
    """The provider CLAIMS quotes but the gate flips at call time and it
    returns marks: fetched (the claim was worth a try), not saved again."""
    db = tmp_path / "asof.sqlite"
    with VolStore(db) as store:
        store.save_snapshot(replace(Counting(kind="marks").fetch_chain("ALPHA"), timestamp=TS, quote_kind="marks"),
                            source="massive", series_id="series-1")
    liar = Counting(kind="marks")
    liar.historical_quote_kind = lambda: "quotes"  # type: ignore[method-assign]
    state = _state(db, liar)
    state.set_as_of(AsOfSelection(mode="intraday", ts=TS))
    state.snapshot("ALPHA")
    assert liar.calls == 1 and _rows_at(db, TS) == [("series-1", "marks")]


# ---------------------------------------------------------------- bounds

def test_no_store_and_a_live_instant_go_straight_to_the_provider(tmp_path):
    prov = Counting()
    state = _state(None, prov)
    state.set_as_of(AsOfSelection(mode="eod", on=DAY))
    state.snapshot("ALPHA")
    state.set_as_of(AsOfSelection())
    state.set_as_of(AsOfSelection(mode="eod", on=DAY))
    state.snapshot("ALPHA")
    assert prov.calls == 2  # nothing to cache in
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert not is_final(now)  # today's instant is served live, never frozen
    assert is_final(TS) and is_final(session_close_utc(DAY))


def test_a_save_failure_never_fails_the_fetch(tmp_path, monkeypatch):
    def boom(self, *a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(VolStore, "save_snapshot", boom)
    prov = Counting()
    state = _state(tmp_path / "asof.sqlite", prov)
    state.set_as_of(AsOfSelection(mode="eod", on=DAY))
    assert state.snapshot("ALPHA").quotes and prov.calls == 1
    assert _rows_at(tmp_path / "asof.sqlite", session_close_utc(DAY)) == []  # nothing saved, chain served


# ---------------------------------------------------------------- schema

def test_store_v12_adds_the_kind_and_request_and_backfills_series_frames(tmp_path):
    assert SCHEMA_VERSION == 12
    fresh = tmp_path / "fresh.sqlite"
    with VolStore(fresh) as store:
        cols = {r[1] for r in store.conn.execute("PRAGMA table_info(snapshots)")}
        assert {"quote_kind", "request_json"} <= cols
        marks = replace(Counting(kind="marks").fetch_chain("ALPHA"), quote_kind="marks")
        sid = store.save_snapshot(marks, source="massive")
        assert store.load_snapshot(sid).quote_kind == "marks"  # the kind round-trips
        assert store.snapshot_meta_at("ALPHA", marks.timestamp, exact=True).quote_kind == "marks"

    # A v11 file: a capture and a series frame whose kind lives on the frame.
    old = tmp_path / "v11.sqlite"
    conn = sqlite3.connect(old)
    conn.executescript(
        """
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL, spot REAL NOT NULL,
            ts TEXT NOT NULL, exercise_style TEXT NOT NULL DEFAULT 'european',
            zero_carry INTEGER NOT NULL DEFAULT 0, tick_size REAL, settlement_json TEXT,
            source TEXT, series_id TEXT
        );
        INSERT INTO snapshots (ticker, spot, ts, source) VALUES ('ALPHA', 100.0, '2026-06-12T15:00:00', 'cboe');
        INSERT INTO snapshots (ticker, spot, ts, source, series_id)
            VALUES ('ALPHA', 100.0, '2026-06-12T15:30:00', 'massive', 'series-1');
        CREATE TABLE series_frames (
            series_id TEXT NOT NULL, idx INTEGER NOT NULL, ts TEXT NOT NULL, snapshot_id INTEGER,
            spot REAL, quote_kind TEXT, n_quotes INTEGER, expiries_json TEXT, status TEXT NOT NULL,
            error TEXT, harvested_ts TEXT, PRIMARY KEY (series_id, idx)
        );
        INSERT INTO series_frames (series_id, idx, ts, snapshot_id, quote_kind, status)
            VALUES ('series-1', 0, '2026-06-12T15:30:00', 2, 'quotes', 'ready');
        PRAGMA user_version = 11;
        """
    )
    conn.commit()
    conn.close()
    with VolStore(old) as store:
        assert store.conn.execute("PRAGMA user_version").fetchone()[0] == 12
        kinds = dict(store.conn.execute("SELECT id, quote_kind FROM snapshots ORDER BY id"))
        assert kinds == {1: None, 2: "quotes"}  # the capture unknown, the frame backfilled
        assert store.load_snapshot(1).quote_kind == "quotes"  # NULL still reads as before
