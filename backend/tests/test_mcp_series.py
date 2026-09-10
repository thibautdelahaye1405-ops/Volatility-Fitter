"""The connector's SERIES tools (SERIES ARC S6) end to end, in-process.

The synthetic app runs WITH a store (series are persistent objects: the
routes answer 409 without one). A LIVE series whose instants all lie in the
past harvests every frame at once through the app's refresh (the synthetic
source needs no history for that), so the whole pipeline — create → wait →
report → frame → chart → list → control → delete — takes a few seconds.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp.client.client import Client

from volfit.api.app import create_app
from volfit_mcp.client import VolfitApi
from volfit_mcp.server import build_server
from volfit_mcp.tools_charts import SERIES_URI

SERIES_TOOLS = {"list_series", "create_series", "import_series", "wait_for_series", "series_report",
                "series_control", "series_frame", "chart_series_frame"}


def _text(res) -> str:
    return "".join(b.text for b in res.content if b.type == "text")


async def _pipeline(db: Path) -> dict[str, Any]:
    # Today's reference date: a live frame is stamped now, and the synthetic
    # ladder (~1M, 3M, 6M, 1Y from the reference date) must be alive at it.
    app = create_app(reference_date=date.today(), store_path=str(db))
    api = VolfitApi("http://volfit.test", transport=httpx.ASGITransport(app=app))
    out: dict[str, Any] = {}
    async with Client(build_server(api)) as c:
        out["tools"] = {t.name: t for t in (await c.list_tools()).tools}
        out["ui"] = (await c.read_resource(SERIES_URI)).contents[0]
        await c.call_tool("set_universe", {"tickers": ["SPY"]})
        out["empty"] = await c.call_tool("list_series", {})
        start = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
        out["create"] = await c.call_tool("create_series", {
            "ticker": "SPY", "mode": "live", "step": "1m", "count": 6, "start": start,
            "session_only": False, "max_expiries": 2, "presets": ["lqd_free", "lqd_prior"]})
        sid = out["create"].structured_content["id"]
        out["wait"] = await c.call_tool("wait_for_series", {"id": sid, "wait_seconds": 120})
        out["report"] = await c.call_tool("series_report", {"id": sid})
        out["frame"] = await c.call_tool("series_frame", {"id": sid, "frame": 2})
        expiries = out["frame"].structured_content["frame"]["expiries"]
        out["frame_last"] = await c.call_tool("series_frame", {"id": sid, "frame": -1, "expiry": expiries[-1], "lanes": ["lqd_free"]})
        out["frame_bad"] = await c.call_tool("series_frame", {"id": sid, "frame": 0, "expiry": "1999-01-01"})
        out["chart"] = await c.call_tool("chart_series_frame", {"id": sid, "frame": 0, "png": True})
        out["list"] = await c.call_tool("list_series", {"ticker": "SPY"})
        out["cancel"] = await c.call_tool("series_control", {"id": sid, "action": "cancel"})
        out["bad_ticker"] = await c.call_tool("create_series", {"ticker": "ZZZQ", "mode": "live", "step": "1m", "count": 2, "session_only": False})
        out["bad_preset"] = await c.call_tool("create_series", {"ticker": "SPY", "presets": ["nope"]})
        out["draft"] = await c.call_tool("create_series", {
            "ticker": "SPY", "mode": "live", "step": "1m", "count": 2, "start": start, "session_only": False,
            "presets": ["lqd_free"], "start_job": False})
        did = out["draft"].structured_content["id"]
        out["draft_wait"] = await c.call_tool("wait_for_series", {"id": did, "wait_seconds": 5})
        out["delete"] = await c.call_tool("series_control", {"id": sid, "action": "delete"})
        out["delete_draft"] = await c.call_tool("series_control", {"id": did, "action": "delete"})
        out["list_after"] = await c.call_tool("list_series", {})
    await api.aclose()
    out["id"] = sid
    return out


@pytest.fixture(scope="module")
def pipe(tmp_path_factory) -> dict[str, Any]:
    return asyncio.run(_pipeline(tmp_path_factory.mktemp("mcp_series") / "app.sqlite"))


def test_series_tools_and_app_are_registered(pipe):
    assert SERIES_TOOLS <= set(pipe["tools"])
    assert pipe["tools"]["chart_series_frame"].meta == {"ui": {"resourceUri": SERIES_URI}, "ui/resourceUri": SERIES_URI}
    assert pipe["tools"]["series_frame"].annotations.read_only_hint is True
    assert pipe["tools"]["create_series"].annotations.read_only_hint is False
    assert pipe["tools"]["series_control"].annotations.destructive_hint is True
    html = pipe["ui"].text
    assert "window.VolfitBridge" in html and "/*__BRIDGE__*/" not in html
    assert 'callTool("series_frame"' in html and "volfit-series" in html
    assert pipe["empty"].structured_content["series"] == []


def test_create_series_live_in_the_past(pipe):
    res = pipe["create"]
    assert res.is_error is False, _text(res)
    sc = res.structured_content
    assert sc["kind"] == "series_created" and sc["ticker"] == "SPY" and sc["mode"] == "live"
    assert sc["step"] == "1m" and sc["count"] == 6 and sc["fitMode"] == "mid"
    assert [ln["id"] for ln in sc["lanes"]] == ["lqd_free", "lqd_prior"]
    assert sc["lanes"][0]["prior"] == "off" and sc["lanes"][1]["prior"] == "hybrid" and sc["lanes"][0]["production"]
    est = sc["estimate"]
    assert est["nFrames"] == 6 and est["servable"] == 6 and est["harvestSeconds"] >= 0
    assert sc["frames"]["total"] == 6 and sc["frames"]["skipped"] == 0
    assert sc["status"] in ("queued", "harvesting", "calibrating", "done")
    assert sc["workbenchUrl"].startswith("http://localhost:5173/?node=SPY%7C") and "activity=series&series=" in sc["workbenchUrl"]
    assert "wait_for_series" in _text(res) and sc["id"] in _text(res)


def test_wait_for_series_returns_done(pipe):
    res = pipe["wait"]
    assert res.is_error is False, _text(res)
    sc = res.structured_content
    assert sc["outcome"] == "done" and sc["status"] == "done" and sc["finished"] is True
    p = sc["progress"]
    assert p["framesReady"] == p["framesTotal"] == 6
    assert p["fitsDone"] == p["fitsTotal"] > 0 and p["error"] is None
    assert sc["running"] is None and _text(res).startswith(f"Series {pipe['id']} done")
    # A never-started series is a terminal outcome too (draft), never an error.
    d = pipe["draft_wait"]
    assert d.is_error is False and d.structured_content["outcome"] == "draft"
    assert "series_control" in _text(d) and d.structured_content["waitedSeconds"] < 5


def test_series_report_has_lane_rows_and_the_roughness_column(pipe):
    res = pipe["report"]
    assert res.is_error is False, _text(res)
    sc = res.structured_content
    assert sc["kind"] == "series_report" and sc["status"] == "done" and sc["frames"]["ready"] == 6
    rows = {row["lane"]: row for row in sc["lanes"]}
    assert set(rows) == {"lqd_free", "lqd_prior"}
    for row in rows.values():
        assert row["frames"] == 6 and row["failed"] == 0
        assert row["meanRmsBp"] > 0 and row["meanMaxBp"] >= row["meanRmsBp"]
        assert row["worstFrame"].startswith("#") and row["roughnessAtmBp"] is not None
    assert rows["lqd_free"]["meanAbsPullAtmBp"] is None  # a free lane has no pull
    assert rows["lqd_prior"]["meanAbsPullAtmBp"] is not None  # measured against the free lane
    assert sc["evidence"]["lanes"]["lqd_prior"]["nFrames"] == 6 and sc["expiry"]
    text = _text(res)
    assert "| lane |" in text and "| roughnessAtmBp |" in text and "| lqd_prior |" in text
    assert "what a prior or a filter damps" in text and "Smoothest ATM path" in text
    assert f"series={pipe['id']}" in sc["workbenchUrl"]


def test_series_frame_returns_one_expiry_with_curves(pipe):
    res = pipe["frame"]
    assert res.is_error is False, _text(res)
    sc = res.structured_content
    assert sc["kind"] == "series_frame" and sc["nFrames"] == 6 and sc["seriesId"] == pipe["id"]
    f, sh = sc["frame"], sc["shown"]
    assert f["idx"] == 2 and f["status"] == "ready" and len(f["expiries"]) == 2 and f["spot"] > 0
    assert sh["expiry"] == f["expiries"][0] and len(sh["quotes"]) > 5 and sh["forward"] > 0
    assert {"k", "bid", "ask", "mid", "strike"} <= set(sh["quotes"][0])
    assert set(sh["curves"]) == {"lqd_free", "lqd_prior"} == set(sc["laneOrder"])
    for c in sh["curves"].values():
        assert 2 < len(c["k"]) == len(c["iv"]) <= 81 and c["rmsBp"] >= 0 and 0.02 < c["atmVol"] < 1.5
    assert set(sc["lanes"]["lqd_free"]["slices"]) == set(f["expiries"])
    assert "frame=2" in sc["workbenchUrl"] and "| lane | expiry | atmVol | rmsBp |" in _text(res)
    # Negative frames count from the end; a requested expiry and lane subset are honoured.
    last = pipe["frame_last"].structured_content
    assert last["frame"]["idx"] == 5 and last["shown"]["expiry"] == f["expiries"][-1]
    assert list(last["shown"]["curves"]) == ["lqd_free"] and last["laneOrder"] == ["lqd_free"]
    bad = pipe["frame_bad"]
    assert bad.is_error is True and "1999-01-01" in _text(bad)


def test_chart_series_frame_is_an_app_with_png_fallback(pipe):
    res = pipe["chart"]
    assert res.is_error is False, _text(res)
    assert [b.type for b in res.content] == ["text", "image"] and res.content[1].mime_type == "image/png"
    sc = res.structured_content
    assert sc["kind"] == "series_frame" and sc["frame"]["idx"] == 0 and sc["shown"]["curves"]
    assert "does not render inline apps" in _text(res)  # the in-memory client never negotiates Apps
    assert sc["workbenchUrl"].endswith("&frame=0")


def test_list_and_control(pipe):
    rows = pipe["list"].structured_content["series"]
    assert [s["id"] for s in rows] == [pipe["id"]]
    assert rows[0]["status"] == "done" and rows[0]["frames"] == "6/6" and rows[0]["nLanes"] == 2
    cancel = pipe["cancel"].structured_content
    assert cancel["changed"] is False and "nothing to cancel" in cancel["message"] and cancel["status"] == "done"
    assert pipe["delete"].structured_content["deleted"] is True
    assert pipe["delete_draft"].structured_content["deleted"] is True
    assert pipe["list_after"].structured_content["series"] == []


def test_refusals_reach_the_model_as_tool_errors(pipe):
    bad = pipe["bad_ticker"]
    assert bad.is_error is True and "not in the universe" in _text(bad)
    preset = pipe["bad_preset"]
    assert preset.is_error is True and "unknown lane preset" in _text(preset) and "lqd_free" in _text(preset)
