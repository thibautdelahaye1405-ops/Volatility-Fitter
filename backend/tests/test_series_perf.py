"""SERIES ARC S7 — the series perf rails (``pytest -m perf -s``).

Budgets are loose multiples (~3×) of the dev-box timings noted beside each,
the test_perf convention: they catch an order-of-magnitude blow-up (a lost
memo, an O(frames × fits) loop turning quadratic), never micro-speed.

* the filmstrip + the evidence over the DESIGN POINT (390 frames × 3 lanes
  × 2 expiries, filled straight into the store — no calibration);
* a warm frame payload (the memo) after one cold build;
* the free-lane calibration of a synthetic 20-frame series — the runner's
  own overhead over the fits (the real-data numbers live in the roadmap:
  free lane 391 ms per frame on the 0DTE store).
"""

from __future__ import annotations

import dataclasses
import time
from datetime import date, datetime, timedelta

import pytest

from volfit.api.schemas import FitSettings, OptionsSettings
from volfit.api.schemas_series import (
    FrameDoc,
    LaneFitDoc,
    LaneSpec,
    SeriesClock,
    SeriesDoc,
    SeriesLadder,
    SeriesProgress,
    SeriesSpec,
)
from volfit.api.series_evidence import evidence_payload
from volfit.api.series_import import ImportSource, SeriesImportRequest, import_series
from volfit.api.series_jobs import SeriesJobs
from volfit.api.series_payload import frame_payload, strip_payload
from volfit.api.series_store import SeriesStore
from volfit.api.state import AppState
from volfit.data.provider import SyntheticProvider
from volfit.data.store import VolStore

pytestmark = pytest.mark.perf

REF = date(2026, 6, 13)
T0 = datetime(2026, 6, 12, 14, 0)

#: Wall-clock ceilings (ms) — dev-box timings in the comments.
BUDGET_MS = {
    "series_strip_390x3": 300.0,  # 90 ms: 390 frames × 3 lanes × 2 expiries
    "series_evidence_390x3": 400.0,  # 120 ms: the strip + the per-lane means
    "series_frame_payload_warm": 50.0,  # 3 ms: the memo hit + one count query
    "series_calibrate_free_20": 5_000.0,  # 1.05 s: 20 synthetic frames × 2 expiries, one free lane (53 ms per frame)
}


def _median_ms(fn, repeat: int = 5, warmup: int = 1) -> float:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    samples.sort()
    return samples[len(samples) // 2]


def _check(name: str, measured: float) -> None:
    print(f"\n[perf] {name}: {measured:.1f} ms (budget {BUDGET_MS[name]:.0f} ms)")
    assert measured <= BUDGET_MS[name], f"{name}: {measured:.1f} ms exceeds {BUDGET_MS[name]:.0f} ms"


def _state(db) -> AppState:
    prov = SyntheticProvider(reference_date=REF, tickers=("ALPHA",))
    return AppState(REF, providers={"cboe": prov}, active_source="cboe", store_path=str(db))


# ----------------------------------------------------- the design point

def _fill_design_point(state, n_frames=390, lanes=("free", "prior", "filt"), expiries=("2026-07-17", "2026-08-21")):
    spec = SeriesSpec(
        name="rail", ticker="ALPHA", mode="import", source="import:rail",
        clock=SeriesClock(step="1m", count=n_frames, sessionOnly=False),
        ladder=SeriesLadder(expiries=list(expiries)), fitMode="mid",
        lanes=[LaneSpec(id=lane, name=lane) for lane in lanes],
    )
    frames = [FrameDoc(idx=i, ts=(T0 + timedelta(minutes=i)).isoformat(), spot=100.0 + 0.01 * i,
                       quoteKind="quotes", nQuotes=80, expiries=list(expiries), status="ready")
              for i in range(n_frames)]
    doc = SeriesDoc(id="rail", createdTs="t", updatedTs="t", spec=spec, baseFit=FitSettings(),
                    baseOptions=OptionsSettings(), frames=frames,
                    progress=SeriesProgress(status="done", framesTotal=n_frames, framesReady=n_frames))
    with VolStore(state.store_path) as store:
        series = SeriesStore(store)
        series.create(doc)
        fits = []
        for i in range(n_frames):
            for j, lane in enumerate(lanes):
                for e in expiries:
                    fits.append(LaneFitDoc(
                        laneId=lane, idx=i, expiry=e, model="lqd",
                        params={"L": 1.0, "R": 1.0, "a": [0.1, 0.2], "alphaL": 0.0, "alphaR": 0.0},
                        diagnostics={"curvature": 0.5 + 0.001 * i},
                        metrics={"rmsBp": 3.0 + 0.01 * i + j, "maxIvBp": 10.0 + j, "atmVol": 0.2 + 1e-4 * i,
                                 "skew": -0.1 - 1e-4 * i, "pullAtmBp": None if j == 0 else 1.5,
                                 "zeta": [0.9, 0.1, 0.0] if lane == "filt" else None},
                        fitMs=12.0,
                    ))
        series.save_fits("rail", fits)
    return doc


def test_perf_series_strip_and_evidence_design_point(tmp_path):
    state = _state(tmp_path / "rail.sqlite")
    t0 = time.perf_counter()
    _fill_design_point(state)
    print(f"\n[perf] fill 390 × 3 × 2 = 2,340 fits in one transaction: {(time.perf_counter() - t0) * 1000:.0f} ms")
    strip = strip_payload(state, "rail")
    assert len(strip.idx) == 390 and set(strip.lanes) == {"free", "prior", "filt"}
    _check("series_strip_390x3", _median_ms(lambda: strip_payload(state, "rail"), repeat=5))
    ev = evidence_payload(state, "rail")
    assert ev.lanes["free"].nFrames == 390 and ev.lanes["filt"].zetaAtmStd is not None
    _check("series_evidence_390x3", _median_ms(lambda: evidence_payload(state, "rail"), repeat=5))


# ---------------------------------------------------------- frame memo

def _chain(minutes: int = 0):
    chain = SyntheticProvider(reference_date=REF, tickers=("ALPHA",)).fetch_chain("ALPHA")
    return dataclasses.replace(chain, timestamp=T0 + timedelta(minutes=minutes))


def _campaign(path, n: int, step_min: int = 15) -> str:
    with VolStore(path) as vs:
        for i in range(n):
            vs.save_snapshot(_chain(i * step_min))
    return str(path)


def test_perf_series_frame_payload_warm(tmp_path):
    campaign = _campaign(tmp_path / "c.sqlite", 2)
    state = _state(tmp_path / "app.sqlite")
    doc = import_series(state, SeriesImportRequest(
        name="s", ticker="ALPHA", source=ImportSource(kind="store", path=campaign),
        presets=["lqd_free", "lqd_prior"], ladder=SeriesLadder(maxExpiries=2),
    ))
    jobs = SeriesJobs(state)
    jobs.start(doc.id)
    jobs.join(120)
    t0 = time.perf_counter()
    cold = frame_payload(state, doc.id, 1)
    print(f"\n[perf] frame payload cold: {(time.perf_counter() - t0) * 1000:.0f} ms")
    assert cold.lanes and cold.market
    _check("series_frame_payload_warm", _median_ms(lambda: frame_payload(state, doc.id, 1), repeat=9))


# ----------------------------------------------------- the runner rail

def test_perf_series_calibrate_free_lane_synthetic(tmp_path):
    campaign = _campaign(tmp_path / "c.sqlite", 20)
    state = _state(tmp_path / "app.sqlite")
    doc = import_series(state, SeriesImportRequest(
        name="s", ticker="ALPHA", source=ImportSource(kind="store", path=campaign),
        presets=["lqd_free"], ladder=SeriesLadder(maxExpiries=2),
    ))
    jobs = SeriesJobs(state)
    t0 = time.perf_counter()
    assert jobs.start(doc.id) == "started"
    jobs.join(300)
    wall = (time.perf_counter() - t0) * 1000.0
    with VolStore(state.store_path) as store:
        got = SeriesStore(store).get(doc.id)
    assert got is not None and got.progress.status == "done" and got.progress.fitsDone == 40
    print(f"\n[perf] 20 frames × 1 free lane × 2 expiries: {wall:.0f} ms ({wall / 20:.0f} ms per frame)")
    _check("series_calibrate_free_20", wall)
