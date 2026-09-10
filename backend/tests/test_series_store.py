"""SERIES ARC S1 — the series store CRUD (Docs/series_replay_roadmap.md §5).

Locks: create / list / get round-trip the document (spec with lanes, the
frozen base settings, progress, frames) and mirror the lanes; frames upsert
by index and load their chain; fits upsert per (lane, frame, expiry) with
the LV row at expiry None; the lane filter doc round-trips; progress
checkpoints update status + error; delete removes the series-OWNED snapshot
rows (and their quotes) but leaves a referenced capture alone.
"""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta

from volfit.api.schemas import FitSettings, OptionsSettings
from volfit.api.schemas_series import (
    FrameDoc,
    LaneFitDoc,
    LaneSpec,
    SeriesClock,
    SeriesDoc,
    SeriesProgress,
    SeriesSpec,
)
from volfit.api.series_store import SeriesStore, new_series_id
from volfit.data.provider import SyntheticProvider
from volfit.data.store import VolStore

REF = date(2026, 6, 13)


def _chain(minutes: int = 0):
    chain = SyntheticProvider(reference_date=REF, tickers=("ALPHA",)).fetch_chain("ALPHA")
    if minutes:
        chain = dataclasses.replace(chain, timestamp=chain.timestamp + timedelta(minutes=minutes))
    return chain


def _doc(sid: str, frames: list[FrameDoc] | None = None) -> SeriesDoc:
    spec = SeriesSpec(
        name="alpha 1m", ticker="ALPHA", mode="import", source="import:x",
        clock=SeriesClock(step="1m", count=3),
        lanes=[LaneSpec(id="free", name="free", patchOptions={"priorPersistenceMode": "off"}),
               LaneSpec(id="lv", name="lv", family="lv")],
    )
    return SeriesDoc(id=sid, createdTs="2026-09-10T10:00:00", updatedTs="2026-09-10T10:00:00",
                     spec=spec, baseFit=FitSettings(nOrder=12), baseOptions=OptionsSettings(),
                     frames=frames or [])


def test_create_list_get_round_trip(tmp_path):
    with VolStore(tmp_path / "s.sqlite") as store:
        series = SeriesStore(store)
        sid = new_series_id()
        assert len(sid) == 12
        cap = store.save_snapshot(_chain(0), source="cboe")
        frames = [FrameDoc(idx=0, ts=_chain(0).timestamp.isoformat(), snapshotId=cap,
                           spot=100.0, quoteKind="quotes", nQuotes=10,
                           expiries=["2026-07-17"], status="ready")]
        series.create(_doc(sid, frames))

        rows = series.list()
        assert [r.id for r in rows] == [sid]
        assert rows[0].nFrames == 1 and rows[0].nFramesReady == 1 and rows[0].nLanes == 2
        assert series.list("alpha")[0].id == sid and series.list("OTHER") == []

        got = series.get(sid)
        assert got is not None
        assert got.spec == _doc(sid).spec and got.baseFit.nOrder == 12
        assert got.frames == frames and got.progress == SeriesProgress()
        assert [lane.id for lane in series.lanes(sid)] == ["free", "lv"]
        assert series.lanes(sid)[0].production is True  # the first lane by default
        assert series.get("nope") is None and not series.exists("nope")


def test_frames_upsert_and_load_their_chain(tmp_path):
    with VolStore(tmp_path / "f.sqlite") as store:
        series = SeriesStore(store)
        sid = "abc"
        series.create(_doc(sid))
        assert series.frames(sid) == [] and series.frame_chain(sid, 0) is None
        series.put_frame(sid, FrameDoc(idx=1, ts="t1"))
        series.put_frame(sid, FrameDoc(idx=0, ts="t0", status="harvesting"))
        assert [f.idx for f in series.frames(sid)] == [0, 1]
        snap = store.save_snapshot(_chain(0), source="cboe", series_id=sid)
        series.put_frame(sid, FrameDoc(idx=0, ts="t0", snapshotId=snap, status="ready",
                                       expiries=["2026-07-17"], warmup=True))
        f0 = series.frame(sid, 0)
        assert f0 is not None and f0.status == "ready" and f0.warmup and f0.snapshotId == snap
        chain = series.frame_chain(sid, 0)
        assert chain is not None and chain.ticker == "ALPHA" and len(chain.quotes) > 0
        assert series.frame(sid, 7) is None


def test_fits_upsert_per_lane_frame_expiry_with_the_lv_row(tmp_path):
    with VolStore(tmp_path / "fits.sqlite") as store:
        series = SeriesStore(store)
        sid = "abc"
        series.create(_doc(sid))
        series.save_fit(sid, LaneFitDoc(laneId="free", idx=0, expiry="2026-07-17", model="lqd",
                                        params={"a": [1.0]}, metrics={"rmsBp": 3.0}, fitMs=12.5))
        series.save_fit(sid, LaneFitDoc(laneId="lv", idx=0, model="affine",
                                        params={"grid": [[0.04]]}, display=None))
        series.save_fit(sid, LaneFitDoc(laneId="free", idx=0, expiry="2026-07-17", model="lqd",
                                        params={"a": [2.0]}, metrics={"rmsBp": 2.0}))  # upsert
        fits = series.fits(sid, idx=0)
        assert len(fits) == 2
        free = next(f for f in fits if f.laneId == "free")
        assert free.params == {"a": [2.0]} and free.metrics == {"rmsBp": 2.0}
        lv = next(f for f in fits if f.laneId == "lv")
        assert lv.expiry is None and lv.display is None and lv.status == "done"
        assert series.fits(sid, lane_id="lv") == [lv]
        assert series.count_fits(sid) == 2 and series.count_fits(sid, status="failed") == 0
        series.save_fit(sid, LaneFitDoc(laneId="free", idx=1, expiry="2026-07-17", model="lqd",
                                        status="failed", error="boom"))
        assert series.count_fits(sid, status="failed") == 1


def test_lane_filter_and_progress_checkpoints(tmp_path):
    with VolStore(tmp_path / "p.sqlite") as store:
        series = SeriesStore(store)
        sid = "abc"
        series.create(_doc(sid))
        assert series.lane_filter(sid, "free") is None
        series.set_lane_filter(sid, "free", {"2026-07-17": [{"ts": 1.0}]})
        assert series.lane_filter(sid, "free") == {"2026-07-17": [{"ts": 1.0}]}
        series.set_lane_filter(sid, "free", None)
        assert series.lane_filter(sid, "free") is None

        series.set_progress(sid, SeriesProgress(status="calibrating", fitsTotal=6, fitsDone=2))
        got = series.get(sid)
        assert got is not None and got.progress.status == "calibrating"
        assert got.progress.fitsDone == 2 and got.progress.updatedTs is not None
        assert series.list()[0].status == "calibrating"
        series.set_progress(sid, SeriesProgress(status="failed"), error="boom")
        assert store.conn.execute("SELECT error FROM series WHERE id = ?", (sid,)).fetchone()[0] == "boom"


def test_delete_removes_owned_snapshots_but_keeps_referenced_captures(tmp_path):
    with VolStore(tmp_path / "d.sqlite") as store:
        series = SeriesStore(store)
        sid = "abc"
        cap = store.save_snapshot(_chain(0), source="cboe")  # a capture, referenced
        series.create(_doc(sid, [FrameDoc(idx=0, ts="t0", snapshotId=cap, status="ready")]))
        owned = store.save_snapshot(_chain(1), source="import:x", series_id=sid)
        series.put_frame(sid, FrameDoc(idx=1, ts="t1", snapshotId=owned, status="ready"))
        series.save_fit(sid, LaneFitDoc(laneId="free", idx=0, expiry="2026-07-17", model="lqd"))
        n_quotes_before = store.conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
        n_owned_quotes = store.conn.execute(
            "SELECT COUNT(*) FROM quotes WHERE snapshot_id = ?", (owned,)
        ).fetchone()[0]
        assert n_owned_quotes > 0

        assert series.delete(sid) is True
        assert series.delete(sid) is False
        assert series.get(sid) is None
        for t in ("series_lanes", "series_frames", "series_fits"):
            assert store.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
        ids = {r[0] for r in store.conn.execute("SELECT id FROM snapshots")}
        assert ids == {cap}  # the owned row is gone, the capture stays
        assert store.conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0] == (
            n_quotes_before - n_owned_quotes
        )
        assert store.load_snapshot(cap).ticker == "ALPHA"
