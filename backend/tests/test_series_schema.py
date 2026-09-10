"""SERIES ARC S0 — the schema contract (Docs/series_replay_roadmap.md §3, §5).

Locks: a spec round-trips through JSON; lane patches are validated against
the settings models (an unknown key or a family / model mismatch is
refused); exactly one production lane (the first by default); the floors
and seed rules of the spec validator; every preset resolves against a base;
the re-export surface in ``volfit.api.schemas``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from volfit.api import schemas
from volfit.api.schemas import FitSettings, OptionsSettings
from volfit.api.schemas_series import (
    FrameDoc,
    LaneFitDoc,
    LaneSpec,
    SeriesClock,
    SeriesDoc,
    SeriesSpec,
)
from volfit.api.series_presets import LANE_PRESET_IDS, lane_preset


def _spec(**over) -> SeriesSpec:
    base = dict(
        name="SPY 15-min",
        ticker="SPY",
        clock=SeriesClock(step="15m", count=20),
        lanes=[
            LaneSpec(id="free", name="LQD-16 free", family="lqd",
                     patchOptions={"priorPersistenceMode": "off"}),
            LaneSpec(id="pf", name="LQD-16 + prior + filter", family="lqd",
                     patchOptions={"priorPersistenceMode": "hybrid",
                                   "observationFilterMode": "active"}),
            LaneSpec(id="lv", name="LV + prior", family="lv",
                     patchOptions={"priorPersistenceMode": "hybrid"}),
        ],
    )
    base.update(over)
    return SeriesSpec(**base)


# ------------------------------------------------------------- round trips

def test_spec_round_trips_through_json():
    spec = _spec()
    again = SeriesSpec.model_validate_json(spec.model_dump_json())
    assert again == spec
    assert again.tickers == ["SPY"]  # the D2 seam is filled in
    assert [lane.production for lane in again.lanes] == [True, False, False]


def test_series_doc_round_trips_with_frozen_base_settings():
    doc = SeriesDoc(
        id="s1", createdTs="2026-09-10T10:00:00", updatedTs="2026-09-10T10:00:00",
        spec=_spec(), baseFit=FitSettings(), baseOptions=OptionsSettings(),
        frames=[FrameDoc(idx=0, ts="2026-09-08T15:45:00-04:00", status="ready",
                         snapshotId=7, quoteKind="quotes", nQuotes=124)],
    )
    again = SeriesDoc.model_validate_json(doc.model_dump_json())
    assert again == doc
    assert again.frames[0].snapshotId == 7 and again.progress.status == "draft"


def test_lane_fit_doc_lv_surface_row_has_no_expiry():
    fit = LaneFitDoc(laneId="lv", idx=3, model="affine", params={"grid": []})
    assert fit.expiry is None and fit.status == "done"
    assert LaneFitDoc.model_validate_json(fit.model_dump_json()) == fit


# ---------------------------------------------------------- lane validation

def test_lane_patch_keys_are_validated_against_the_settings_models():
    with pytest.raises(ValidationError, match="unknown patch keys"):
        LaneSpec(id="x", name="x", patchFit={"nOrdre": 16})
    with pytest.raises(ValidationError, match="unknown patch keys"):
        LaneSpec(id="x", name="x", patchOptions={"kalman": True})
    ok = LaneSpec(id="x", name="x", patchFit={"nOrder": 24},
                  patchOptions={"observationFilterMode": "overlay"})
    assert ok.patchFit == {"nOrder": 24, "model": "lqd"}  # the family pins the model


def test_lane_family_and_model_must_agree():
    with pytest.raises(ValidationError, match="family svi but patchFit.model"):
        LaneSpec(id="x", name="x", family="svi", patchFit={"model": "lqd"})
    svi = LaneSpec(id="x", name="x", family="svi")
    assert svi.patchFit["model"] == "svi"
    lv = LaneSpec(id="y", name="y", family="lv")
    assert lv.patchOptions["localVolEnabled"] is True
    with pytest.raises(ValidationError, match="cannot disable localVolEnabled"):
        LaneSpec(id="y", name="y", family="lv", patchOptions={"localVolEnabled": False})


def test_lane_temporal_flag_reads_the_prior_and_filter_patches():
    assert LaneSpec(id="a", name="a").temporal is False  # inherits the base: unknown → free
    assert LaneSpec(id="b", name="b", patchOptions={"priorPersistenceMode": "off"}).temporal is False
    assert LaneSpec(id="c", name="c", patchOptions={"priorPersistenceMode": "hybrid"}).temporal
    assert LaneSpec(id="d", name="d", patchOptions={"observationFilterMode": "overlay"}).temporal


def test_lane_id_pattern_and_bounds():
    with pytest.raises(ValidationError):
        LaneSpec(id="has space", name="x")
    with pytest.raises(ValidationError):
        LaneSpec(id="", name="x")


# ---------------------------------------------------------- spec validation

def test_spec_needs_unique_lane_ids_and_at_most_one_production_lane():
    dup = [LaneSpec(id="a", name="a"), LaneSpec(id="a", name="b")]
    with pytest.raises(ValidationError, match="unique"):
        _spec(lanes=dup)
    two = [LaneSpec(id="a", name="a", production=True),
           LaneSpec(id="b", name="b", production=True)]
    with pytest.raises(ValidationError, match="at most one production"):
        _spec(lanes=two)
    starred = _spec(lanes=[LaneSpec(id="a", name="a"),
                           LaneSpec(id="b", name="b", production=True)])
    assert starred.production_lane.id == "b"


def test_spec_is_single_ticker_in_v1():
    with pytest.raises(ValidationError, match="exactly one ticker"):
        _spec(tickers=["SPY", "QQQ"])


def test_clock_needs_count_or_end_and_orders_them():
    with pytest.raises(ValidationError, match="count or an end"):
        SeriesClock(step="15m")
    from datetime import datetime
    with pytest.raises(ValidationError, match="end instant must follow"):
        SeriesClock(step="15m", start=datetime(2026, 9, 8, 15), end=datetime(2026, 9, 8, 14))
    with pytest.raises(ValidationError, match="HH:MM"):
        SeriesClock(step="daily", count=5, timeOfDay="25:00")
    assert SeriesClock(step="daily", count=5).step_seconds is None
    assert SeriesClock(step="5m", count=5).step_seconds == 300


def test_step_floors_by_mode():
    # The step vocabulary starts at 1m = 60 s, which meets both floors (live
    # 15 s, historical 60 s), so every step is accepted in every mode; the
    # constants stay the contract the instant resolver (S2) enforces.
    from volfit.api.schemas_series import HISTORICAL_FLOOR_SECONDS, LIVE_FLOOR_SECONDS
    assert LIVE_FLOOR_SECONDS == 15 and HISTORICAL_FLOOR_SECONDS == 60
    hist = _spec(mode="historical", clock=SeriesClock(step="1m", count=3))
    live = _spec(mode="live", clock=SeriesClock(step="1m", count=3))
    assert hist.clock.step_seconds == live.clock.step_seconds == 60


def test_seed_rules():
    with pytest.raises(ValidationError, match="needs a live series"):
        _spec(lanes=[LaneSpec(id="a", name="a", seed="live_prior")])
    with pytest.raises(ValidationError, match="needs clock.warmupFrames"):
        _spec(lanes=[LaneSpec(id="a", name="a", seed="warmup")])
    ok = _spec(lanes=[LaneSpec(id="a", name="a", seed="warmup")],
               clock=SeriesClock(step="15m", count=4, warmupFrames=2))
    assert ok.clock.warmupFrames == 2


# ----------------------------------------------------------------- presets

def test_every_preset_resolves_against_a_base():
    base = FitSettings(nOrder=16)
    for pid in LANE_PRESET_IDS:
        lane = lane_preset(pid, base)
        assert lane.id == pid and lane.name
        if pid.startswith("lqd"):
            assert lane.family == "lqd" and lane.patchFit["nOrder"] == 16
            assert "16" in lane.name
        if pid.startswith("lv"):
            assert lane.family == "lv" and lane.patchOptions["localVolEnabled"] is True
    assert lane_preset("lqd_prior", base, n_order=24).patchFit["nOrder"] == 24
    assert lane_preset("lqd_prior_filter", base).temporal
    assert not lane_preset("svi_free", base).temporal
    cur = lane_preset("current", FitSettings(model="svi"))
    assert cur.family == "svi" and cur.patchOptions == {}
    with pytest.raises(KeyError):
        lane_preset("nope", base)


def test_presets_compose_into_a_valid_spec():
    base = FitSettings()
    lanes = [lane_preset(p, base) for p in ("lqd_free", "lqd_prior_filter", "lv_prior")]
    spec = _spec(lanes=lanes)
    assert spec.production_lane.id == "lqd_free"
    assert [lane.temporal for lane in spec.lanes] == [False, True, True]


# --------------------------------------------------------------- re-exports

def test_schemas_module_re_exports_the_series_shapes():
    for name in ("SeriesSpec", "LaneSpec", "SeriesDoc", "FrameDoc", "LaneFitDoc",
                 "FramePayload", "StripPayload", "SeriesEstimate", "SeriesSummary"):
        assert hasattr(schemas, name), name
