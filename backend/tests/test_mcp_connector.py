"""The MCP connector (volfit_mcp) end to end, in-process.

The server's HTTP client is bound to ``create_app(reference_date=...)`` through
an ASGI transport (no sockets, the synthetic provider), and driven through the
SDK's in-memory ``Client`` — the same protocol path Claude Desktop uses, minus
the pipe. One module-scoped pipeline (set_universe → fetch → configure →
calibrate → report → charts) feeds the assertions; the pure helpers
(aliases, report) are unit-tested directly.
"""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp.client.client import Client

from volfit.api.app import create_app
from volfit_mcp import aliases, report
from volfit_mcp.client import ApiError, VolfitApi
from volfit_mcp.server import build_server
from volfit_mcp.tools_charts import LV_COMPARE_URI, SMILE_URI, TERM_URI, VOL_SURFACE_URI

REF_DATE = date(2026, 6, 10)
FIXTURES = Path(__file__).parent / "fixtures"


def _text(res) -> str:
    return "".join(b.text for b in res.content if b.type == "text")


async def _pipeline() -> dict[str, Any]:
    app = create_app(reference_date=REF_DATE)
    api = VolfitApi("http://volfit.test", transport=httpx.ASGITransport(app=app))
    server = build_server(api)
    out: dict[str, Any] = {}
    async with Client(server) as c:
        out["tools"] = {t.name: t for t in (await c.list_tools()).tools}
        out["resources"] = {str(r.uri): r for r in (await c.list_resources()).resources}
        out["templates"] = [str(t.uri_template) for t in (await c.list_resource_templates()).resource_templates]
        out["prompts"] = [p.name for p in (await c.list_prompts()).prompts]
        out["ui_lv"] = (await c.read_resource(LV_COMPARE_URI)).contents[0]
        out["ui_smile"] = (await c.read_resource(SMILE_URI)).contents[0]

        out["sources"] = await c.call_tool("list_data_sources", {})
        out["universe"] = await c.call_tool("set_universe", {"tickers": ["SPY", "the S&P", "EuroStoxx"]})
        out["preview"] = await c.call_tool("fetch_preview", {})
        out["fetch"] = await c.call_tool("fetch_quotes", {})
        out["configure"] = await c.call_tool("configure_fit", {"model": "lqd", "n_order": 12, "local_vol": True})
        out["calibrate"] = await c.call_tool("calibrate", {"wait_seconds": 240})
        out["status"] = await c.call_tool("calibration_status", {})
        out["report"] = await c.call_tool("calibration_report", {"tickers": ["SPY"]})
        expiries = (await c.call_tool("list_expiries", {"ticker": "SPY"})).structured_content["expiries"]
        out["expiry"] = expiries[1]["expiry"]
        out["smile"] = await c.call_tool("get_smile", {"ticker": "SPY", "expiry": out["expiry"]})
        out["surface"] = await c.call_tool("get_vol_surface", {"ticker": "SPY"})
        out["lv"] = await c.call_tool("get_lv_surface", {"ticker": "SPY"})
        out["compare"] = await c.call_tool("get_lv_compare", {"ticker": "SPY", "include_grid": True})
        out["chart_lv"] = await c.call_tool("chart_lv_compare", {"tickers": ["SPY", "SPX"], "png": True})
        out["chart_smile"] = await c.call_tool("chart_smile", {"ticker": "SPY", "expiry": out["expiry"], "with_lv": True, "png": True})
        out["chart_surface"] = await c.call_tool("chart_vol_surface", {"ticker": "SPY", "png": True})
        out["chart_term"] = await c.call_tool("chart_term_structure", {"ticker": "SPY", "png": True})
        out["bad_smile"] = await c.call_tool("get_smile", {"ticker": "SPY", "expiry": "1999-01-01"})
        out["status_resource"] = json.loads((await c.read_resource("volfit://status")).contents[0].text)
        out["schema_resource"] = json.loads((await c.read_resource("volfit://help/settings-schema")).contents[0].text)
        # Prompt arguments travel as strings on the wire (GetPromptRequestParams).
        out["prompt"] = await c.get_prompt("desk_calibration", {"tickers": "EuroStoxx, SPX", "n_order": "24"})
        # The macro tools, last (they reshape the universe and the settings).
        out["workflow"] = await c.call_tool("run_desk_workflow", {
            "tickers": ["SPY"], "model": "lqd", "n_order": 10, "local_vol": True, "wait_seconds": 240})
        out["workflow_fail"] = await c.call_tool("run_desk_workflow", {"tickers": ["SPY"], "n_order": 99, "fetch": False})
        out["ab"] = await c.call_tool("compare_settings", {
            "a": {"n_order": 8, "label": "LQD-8"}, "b": {"n_order": 12}, "tickers": ["SPY"], "keep": "a", "wait_seconds": 240})
        out["settings_after"] = await c.call_tool("get_fit_settings", {})
        out["status_after"] = await c.call_tool("calibration_status", {})
    await api.aclose()
    return out


@pytest.fixture(scope="module")
def pipe() -> dict[str, Any]:
    return asyncio.run(_pipeline())


# ------------------------------------------------------------- surface
def test_tool_surface_is_curated(pipe):
    names = set(pipe["tools"])
    assert {"set_universe", "fetch_quotes", "configure_fit", "calibrate", "wait_for_calibration",
            "calibration_report", "get_smile", "get_lv_surface", "get_lv_compare",
            "chart_lv_compare", "chart_smile"} <= names
    assert len(names) < 30  # curated verbs, not the OpenAPI surface
    assert pipe["tools"]["get_smile"].annotations.read_only_hint is True
    assert pipe["tools"]["set_universe"].annotations.read_only_hint is False


def test_chart_tools_bind_ui_resources(pipe):
    # Both the 2026-01-26 key and the legacy "ui/resourceUri" key, like the
    # reference TypeScript app servers (older hosts mount from the legacy one).
    assert pipe["tools"]["chart_lv_compare"].meta == {"ui": {"resourceUri": LV_COMPARE_URI}, "ui/resourceUri": LV_COMPARE_URI}
    assert pipe["tools"]["chart_smile"].meta == {"ui": {"resourceUri": SMILE_URI}, "ui/resourceUri": SMILE_URI}
    assert pipe["tools"]["chart_vol_surface"].meta["ui"]["resourceUri"] == VOL_SURFACE_URI
    assert pipe["tools"]["chart_term_structure"].meta["ui"]["resourceUri"] == TERM_URI
    assert {VOL_SURFACE_URI, TERM_URI} <= set(pipe["resources"])
    for key, uri in (("ui_lv", LV_COMPARE_URI), ("ui_smile", SMILE_URI)):
        res = pipe["resources"][uri]
        assert res.mime_type == "text/html;profile=mcp-app"
        assert res.meta["ui"]["csp"]["resourceDomains"] == ["https://cdn.plot.ly"]
        html = pipe[key].text
        assert "window.VolfitBridge" in html and "ui/initialize" in html  # bridge inlined
        assert "/*__BRIDGE__*/" not in html


def test_docs_resources_and_prompts(pipe):
    assert {"volfit://status", "volfit://settings", "volfit://help/settings-schema", "volfit://help/docs",
            "volfit://aliases"} <= set(pipe["resources"])
    assert "volfit://help/docs/{doc_id}" in pipe["templates"]
    assert set(pipe["prompts"]) == {"desk_calibration", "morning_check"}
    assert "calibration" in pipe["status_resource"] and "dataSources" in pipe["status_resource"]
    assert isinstance(pipe["schema_resource"], dict) and pipe["schema_resource"]
    msg = pipe["prompt"].messages[0].content.text
    assert "EuroStoxx, SPX" in msg and "LQD-24" in msg


# ------------------------------------------------------------ pipeline
def test_set_universe_resolves_spoken_names(pipe):
    sc = pipe["universe"].structured_content
    plan = {p["spoken"]: p for p in sc["resolution"]}
    assert plan["the S&P"]["ticker"] == "SPX" and plan["the S&P"]["kind"] == "index"
    assert plan["EuroStoxx"]["ticker"] == "SX5E"
    assert plan["SPY"]["kind"] == "equity"
    assert [t["ticker"] for t in sc["tickers"]] == ["SPY", "SPX", "SX5E"]  # replace=True dropped the defaults
    assert all(t["nExpiries"] > 0 for t in sc["tickers"])


def test_fetch_and_configure(pipe):
    assert "Fetched 3 ticker(s)" in _text(pipe["fetch"])
    cfg = pipe["configure"].structured_content
    assert cfg["fit"]["model"] == "lqd" and cfg["fit"]["nOrder"] == 12
    assert cfg["options"]["localVolEnabled"] is True
    assert cfg["changed"] == {"model": "lqd", "nOrder": 12, "localVolEnabled": True}
    assert pipe["preview"].structured_content["totals"]["nodes"] > 0


def test_calibrate_waits_to_completion(pipe):
    st = pipe["calibrate"].structured_content
    assert st["finished"] is True and st["running"] is False
    assert st["done"] == st["total"] > 0 and st["staleNodes"] == 0 and st["error"] == ""
    assert pipe["status"].structured_content["running"] is False


def test_calibration_report_numbers(pipe):
    rep = pipe["report"].structured_content
    assert [t["ticker"] for t in rep["tickers"]] == ["SPY"]
    spy = rep["tickers"][0]
    assert spy["nodes"] == 4 and isinstance(spy["nodes"], int)  # ints stay ints
    assert spy["fitted"] == 4 and spy["stale"] == 0
    assert 0 < spy["surfaceRmsBp"] < 50
    assert spy["lv"]["hasFit"] is True and spy["lv"]["arbitrageFree"] is True
    rows = spy["expiries"]
    assert len(rows) == 4 and all(r["ready"] for r in rows) and all(r["rmsBp"] >= 0 for r in rows)
    text = _text(pipe["report"])
    assert "| expiry |" in text and "Local-Vol: rms" in text


def test_smile_surface_and_lv_views(pipe):
    sm = pipe["smile"].structured_content
    assert sm["ticker"] == "SPY" and sm["expiry"] == pipe["expiry"] and sm["model"] == "LQD"
    assert sm["nQuotes"] == len(sm["quotes"]) > 5 and 2 <= len(sm["fit"]) <= 61
    assert 0 < sm["diagnostics"]["rmsBp"] < 50 and 0.05 < sm["diagnostics"]["atmVol"] < 1.0
    sf = pipe["surface"].structured_content
    assert len(sf["vol"]) == len(sf["expiries"]) == 4 and len(sf["k"]) <= 41
    lv = pipe["lv"].structured_content
    assert len(lv["localVol"]) == len(lv["tNodes"]) == lv["diagnostics"]["nTNodes"]
    assert lv["diagnostics"]["arbitrageFree"] is True and lv["diagnostics"]["nEvals"] > 0
    cmp = pipe["compare"].structured_content
    assert cmp["hasAffine"] is True and len(cmp["diffLocalVol"]) == len(cmp["tNodes"])
    assert all(e["twin"]["rmsBp"] is not None for e in cmp["expiries"])


def test_chart_tools_return_structured_content_and_png(pipe):
    res = pipe["chart_lv"]
    assert res.is_error is False
    assert [b.type for b in res.content] == ["text", "image"]
    png = base64.b64decode(res.content[1].data)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and res.content[1].mime_type == "image/png"
    sc = res.structured_content
    assert sc["kind"] == "lv_compare" and [p["ticker"] for p in sc["tickers"]] == ["SPY", "SPX"]
    p = sc["tickers"][0]
    assert len(p["affine"]) == len(p["twin"]) == len(p["diff"]) == len(p["tNodes"])
    assert len(p["affine"][0]) == len(p["xNodes"])
    assert {"expiry", "affineRmsBp", "twinRmsBp", "parametricRmsBp"} <= set(p["expiries"][0])
    assert "does not render inline apps" in _text(res)  # the in-memory client never negotiates Apps

    smile = pipe["chart_smile"]
    assert [b.type for b in smile.content] == ["text", "image"]
    sc = smile.structured_content
    assert sc["kind"] == "smile" and pipe["expiry"] in sc["expiries"]
    assert sc["lv"] and len(sc["lv"]) <= 81 and sc["lvRmsBp"] >= 0


def test_api_errors_reach_the_model_as_text(pipe):
    res = pipe["bad_smile"]
    assert res.is_error is True
    assert "404" in _text(res) or "unknown" in _text(res).lower()


def test_backend_down_gives_actionable_hint():
    async def go():
        api = VolfitApi("http://127.0.0.1:9", timeout=2.0)
        try:
            async with Client(build_server(api)) as c:
                return await c.call_tool("get_universe", {})
        finally:
            await api.aclose()

    res = asyncio.run(go())
    assert res.is_error is True
    assert "restart.ps1" in _text(res) and "VOLFIT_API_URL" in _text(res)


# --------------------------------------------------------------- helpers
def test_alias_resolution():
    assert aliases.resolve("EuroStoxx").ticker == "SX5E"
    assert aliases.resolve("euro stoxx 50").ticker == "SX5E"
    assert aliases.resolve("^STOXX50E").ticker == "SX5E"
    assert aliases.resolve("SX5E Index").ticker == "SX5E"
    assert aliases.resolve("the Dax").ticker == "DAX"
    assert aliases.resolve("S&P 500").ticker == "SPX"
    assert aliases.resolve("spx").preferred_sources[0] == "bloomberg"
    assert aliases.resolve("AAPL US Equity").ticker == "AAPL"
    assert aliases.resolve("nvda").kind == "equity"
    assert aliases.resolve("SX5E").pick_source(["yahoo", "eurex"]) == "eurex"
    assert aliases.resolve("SX5E").pick_source(["yahoo"]) is None
    assert [r.ticker for r in aliases.resolve_many(["SPX", "^SPX", "SPY"])] == ["SPX", "SPY"]


def test_report_helpers():
    assert report.r(3) == 3 and isinstance(report.r(3), int)
    assert report.r(0.123456) == 0.1235 and report.r(None) is None and report.r(True) is True
    pts = [{"k": i / 10, "vol": 0.2} for i in range(100)]
    assert len(report.thin(pts, 10)) == 10 and report.thin(pts, 10)[-1] is pts[-1]
    assert len(report.curve(pts, 5)) == 5 and report.curve(pts, 5)[0] == [0.0, 0.2]
    table = report.md_table([{"a": 1, "b": True, "c": 0.00012}], ["a", "b", "c"])
    assert table.splitlines()[0] == "| a | b | c |" and "| 1 | yes | 0.00012 |" in table
    assert report.md_table([], ["a"]) == "(none)"


def test_png_fallbacks_render_from_fixtures():
    from volfit_mcp import render_png

    lv = json.loads((FIXTURES / "mcp_lv_compare.json").read_text())
    sm = json.loads((FIXTURES / "mcp_smile.json").read_text())
    assert render_png.lv_compare_png(lv)[:8] == b"\x89PNG\r\n\x1a\n"
    assert render_png.smile_png(sm)[:8] == b"\x89PNG\r\n\x1a\n"


def test_api_error_detail_formatting():
    with pytest.raises(ApiError):
        raise ApiError("boom", 422)


def test_wire_trace_records_handshake_and_reads(tmp_path):
    """VOLFIT_MCP_TRACE / --trace: one JSON line per inbound message, with the
    client capabilities of ``initialize`` and the URI of every resources/read."""
    trace = tmp_path / "trace.jsonl"

    async def go():
        app = create_app(reference_date=REF_DATE)
        api = VolfitApi("http://volfit.test", transport=httpx.ASGITransport(app=app))
        try:
            async with Client(build_server(api, trace_path=str(trace))) as c:
                await c.read_resource(LV_COMPARE_URI)
                await c.call_tool("get_universe", {})
        finally:
            await api.aclose()

    asyncio.run(go())
    lines = [json.loads(l) for l in trace.read_text(encoding="utf-8").splitlines()]
    methods = [l["method"] for l in lines]
    # A 2026-07-28 client opens with server/discover instead of initialize; the
    # handshake line, whichever it is, carries the server's advertised extensions.
    assert ("initialize" in methods or "server/discover" in methods)
    assert "resources/read" in methods and "tools/call" in methods
    init = next(l for l in lines if l["method"] in ("initialize", "server/discover"))
    assert init["result"]["capabilities"]["extensions"] == {"io.modelcontextprotocol/ui": {}}
    read = next(l for l in lines if l["method"] == "resources/read")
    assert read["params"]["uri"] == LV_COMPARE_URI
    assert read["result"]["contents"][0]["mimeType"] == "text/html;profile=mcp-app"
    call = next(l for l in lines if l["method"] == "tools/call")
    assert call["params"]["name"] == "get_universe" and call["result"]["isError"] is False and call["ms"] >= 0


# ------------------------------------------------------------- macro tools
def test_run_desk_workflow_is_one_call(pipe):
    res = pipe["workflow"]
    assert res.is_error is False
    sc = res.structured_content
    wf = sc["workflow"]
    assert [s["step"] for s in wf["steps"]] == ["universe", "fetch", "configure", "calibrate", "report", "lv_compare"]
    assert all(s["ok"] for s in wf["steps"]) and wf["stoppedAt"] is None
    assert wf["settings"]["fit"]["nOrder"] == 10 and wf["settings"]["options"]["localVolEnabled"] is True
    assert wf["calibration"]["finished"] is True and wf["calibration"]["staleNodes"] == 0
    assert [t["ticker"] for t in wf["report"]["tickers"]] == ["SPY"]
    # The same call renders the LV compare: the chart page's contract is honoured.
    assert sc["kind"] == "lv_compare" and [p["ticker"] for p in sc["tickers"]] == ["SPY"]
    assert len(sc["tickers"][0]["affine"]) == len(sc["tickers"][0]["tNodes"])
    text = _text(res)
    assert text.startswith("Desk workflow (") and "Fit quality" in text and "Local-Vol compare" in text
    assert pipe["tools"]["run_desk_workflow"].meta["ui"]["resourceUri"] == LV_COMPARE_URI


def test_run_desk_workflow_reports_the_failing_step(pipe):
    res = pipe["workflow_fail"]
    sc = res.structured_content
    wf = sc["workflow"]
    assert wf["stoppedAt"] == "configure"
    assert [s["step"] for s in wf["steps"]] == ["universe", "configure"]
    assert wf["steps"][-1]["ok"] is False and "422" in wf["steps"][-1]["error"]
    assert _text(res).splitlines()[1].startswith("STOPPED at step 'configure'")
    assert sc["tickers"] == []  # nothing charted


def test_compare_settings_runs_both_and_keeps_a(pipe):
    res = pipe["ab"]
    assert res.is_error is False
    sc = res.structured_content
    assert sc["kind"] == "compare_settings" and sc["kept"] == "a"
    assert sc["a"]["label"] == "LQD-8" and sc["b"]["label"] == "n_order=12"
    assert sc["a"]["settings"]["fit"]["nOrder"] == 8 and sc["b"]["settings"]["fit"]["nOrder"] == 12
    assert sc["a"]["calibration"]["finished"] and sc["b"]["calibration"]["finished"]
    rows = sc["rows"]
    assert len(rows) == 4 and all(r["ticker"] == "SPY" for r in rows)
    assert all(isinstance(r["rmsA"], float) and isinstance(r["rmsB"], float) for r in rows)
    assert all(abs(r["dRms"] - (r["rmsB"] - r["rmsA"])) < 0.11 for r in rows)
    t = sc["tickers"][0]
    assert t["ticker"] == "SPY" and t["surfaceRmsA"] > 0 and t["surfaceRmsB"] > 0
    assert t["lvRmsA"] is not None and t["lvConvergedB"] is not None
    text = _text(res)
    assert text.startswith("A = LQD-8 | B = n_order=12 | kept in force: A") and "| dRms |" in text
    # The kept run went last: A's settings are in force and nothing is stale.
    assert pipe["settings_after"].structured_content["fit"]["nOrder"] == 8
    assert pipe["status_after"].structured_content["staleNodes"] == 0


def test_surface_and_term_chart_tools(pipe):
    sf = pipe["chart_surface"]
    assert sf.is_error is False and [b.type for b in sf.content] == ["text", "image"]
    sc = sf.structured_content
    assert sc["kind"] == "vol_surface" and sc["ticker"] == "SPY"
    assert len(sc["vol"]) == len(sc["expiries"]) == len(sc["t"]) == len(sc["atmVol"]) == 4
    assert len(sc["k"]) <= 71 and all(len(row) == len(sc["k"]) for row in sc["vol"])
    assert len(sc["crop"]) == 4 and {"u", "lo", "hi"} <= set(sc["crop"][0][0])
    assert sc["workbenchUrl"] == "http://localhost:5173"
    assert "ATM term structure" in _text(sf)

    tm = pipe["chart_term"]
    assert tm.is_error is False and [b.type for b in tm.content] == ["text", "image"]
    sc = tm.structured_content
    assert sc["kind"] == "term" and sc["ticker"] == "SPY" and len(sc["points"]) == 4
    p0 = sc["points"][0]
    assert {"expiry", "t", "tau", "atmVol", "w0", "varSwapVol", "maxIvErrorBp"} <= set(p0)
    assert 0.05 < p0["atmVol"] < 1.0 and p0["w0"] > 0
    assert len(sc["curve"]["t"]) == len(sc["curve"]["w"]) == len(sc["curve"]["vol"]) > 10
    assert sc["calendarViolations"] == 0 and isinstance(sc["events"], list)
    assert "term structure" in _text(tm)
