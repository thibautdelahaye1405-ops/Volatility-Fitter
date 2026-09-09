"""The operations behind the tools, composable: universe, fetch, settings,
calibrate (with progress), report, LV-compare panels.

The single-step tools (``tools_universe`` / ``tools_calibrate`` /
``tools_charts``) are thin wrappers over these coroutines, and the macro tools
(``tools_workflow``: ``run_desk_workflow`` and ``compare_settings``) chain them
— one place for the venue logic, the polling loop and the compaction, so a
desk routine is one tool call and one approval in the chat.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Literal

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from volfit_mcp import aliases
from volfit_mcp.client import VolfitApi
from volfit_mcp.report import compact_compare, compact_status, compact_universe, md_table, quality_summary, r

FitMode = Literal["mid", "bidask", "haircut"]
POLL_S = 0.5

#: Chat-side setting names -> FitSettings fields.
FIT_FIELDS = {"model": "model", "n_order": "nOrder", "weight_scheme": "weightScheme",
              "haircut": "haircut", "reg_lambda": "regLambda", "lqd_coords": "lqdCoords",
              "tail_alpha_left": "tailAlphaLeft", "tail_alpha_right": "tailAlphaRight"}
#: Chat-side setting names -> OptionsSettings fields.
OPT_FIELDS = {"local_vol": "localVolEnabled", "fit_mode": "fitMode",
              "enforce_calendar": "enforceCalendar", "grid_x_nodes": "gridXNodes",
              "grid_t_nodes": "gridTNodes", "grid_reg_lambda": "gridRegLambda",
              "time_scheme": "timeScheme", "lv_lattice": "lvLattice", "lv_solver": "lvSolver",
              "auto_calibrate": "autoCalibrate", "events_enabled": "eventsEnabled"}
ECHO_FIT = ("model", "nOrder", "lqdCoords", "regLambda", "regPower", "weightScheme",
            "haircut", "tailAlphaLeft", "tailAlphaRight")
ECHO_OPT = ("localVolEnabled", "fitMode", "enforceCalendar", "surfaceSolver", "gridXNodes",
            "gridTNodes", "gridRegLambda", "timeScheme", "lvLattice", "lvSolver",
            "autoCalibrate", "eventsEnabled")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def names_of(tickers: list[str] | None) -> list[str] | None:
    return [aliases.resolve(t).ticker for t in tickers] if tickers else None


# --------------------------------------------------------------- universe
async def set_universe(api: VolfitApi, tickers: list[str], replace: bool = True,
                       source: str | None = None) -> dict[str, Any]:
    """Resolve spoken names, pin each ticker to a source that lists it, add /
    re-pin, optionally drop the rest; returns the compact universe + the plan."""
    ds = await api.get("/datasources")
    registered = {s["id"]: s.get("status", "red") for s in ds["sources"]}
    usable = [sid for sid, st in registered.items() if st != "red"]
    resolved = aliases.resolve_many(tickers)
    if not resolved:
        raise ToolError("no tickers given")
    uni = await api.get("/universe")
    present = {t.upper(): t for t in uni.get("tickers", [])}
    pins = {k.upper(): v for k, v in (uni.get("tickerSources") or {}).items()}
    plan: list[dict[str, Any]] = []
    for res in resolved:
        sid = source or res.pick_source(usable) or res.pick_source(list(registered))
        key = res.ticker.upper()
        if key in present:
            if sid and pins.get(key) != sid:
                await api.put(f"/universe/{present[key]}/source", {"source": sid})
                action = "re-pinned"
            else:
                action = "kept"
        else:
            await api.post("/universe/tickers", {"symbol": res.ticker, "source": sid})
            action = "added"
        plan.append({"spoken": res.spoken, "ticker": res.ticker, "kind": res.kind,
                     "source": sid or ds["active"], "action": action})
    if replace:
        keep = {p["ticker"].upper() for p in plan}
        for t in (await api.get("/universe")).get("tickers", []):
            if t.upper() not in keep:
                await api.delete(f"/universe/tickers/{t}")
    out = compact_universe(await api.get("/universe"), await api.get("/universe/lit"))
    out["resolution"] = plan
    out["registeredSources"] = registered
    return out


# ------------------------------------------------------------------ fetch
async def fetch_quotes(api: VolfitApi, tickers: list[str] | None, fit_mode: str | None) -> tuple[str, dict[str, Any]]:
    """POST /fetch/snapshot for the universe (or a subset); text + result."""
    body = {"tickers": names_of(tickers)} if tickers else {}
    res = await api.post("/fetch/snapshot", body, fit_mode=fit_mode)
    errors = (await api.get("/universe")).get("errors") or {}
    ds = await api.get("/datasources")
    lines = [
        f"Fetched {len(res['tickers'])} ticker(s): "
        + ", ".join(f"{t} @ {res['spots'].get(t, float('nan')):.4g}" for t in res["tickers"]),
        f"Background calibration started: {'yes' if res['calibrationStarted'] else 'no'}",
    ]
    if ds.get("dataAge"):
        age = ds["dataAge"]
        lines.append(f"Data age: {age['label']} ({age['level']}, worst {age['worstTicker']})")
    if errors:
        lines.append("Errors: " + md_table([{"ticker": k, "error": v} for k, v in errors.items()], ["ticker", "error"]))
    out = {"tickers": res["tickers"], "spots": res["spots"], "calibrationStarted": res["calibrationStarted"],
           "dataAge": ds.get("dataAge"), "errors": errors}
    return "\n".join(lines), out


# --------------------------------------------------------------- settings
def echo_settings(fit: dict[str, Any], opt: dict[str, Any]) -> dict[str, Any]:
    return {"fit": {k: fit.get(k) for k in ECHO_FIT}, "options": {k: opt.get(k) for k in ECHO_OPT}}


def split_patch(patch: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Chat-side names (``n_order``) -> (FitSettings patch, OptionsSettings patch)."""
    fit = {FIT_FIELDS[k]: v for k, v in patch.items() if k in FIT_FIELDS and v is not None}
    opt = {OPT_FIELDS[k]: v for k, v in patch.items() if k in OPT_FIELDS and v is not None}
    unknown = [k for k, v in patch.items() if v is not None and k not in FIT_FIELDS and k not in OPT_FIELDS]
    if unknown:  # a ToolError reaches the model as readable isError text
        raise ToolError(f"unknown setting(s) {unknown}; known: {sorted(FIT_FIELDS) + sorted(OPT_FIELDS)}")
    return fit, opt


async def read_settings(api: VolfitApi) -> tuple[dict[str, Any], dict[str, Any]]:
    return await api.get("/settings/fit"), await api.get("/settings/options")


async def configure(api: VolfitApi, patch: dict[str, Any],
                    base: tuple[dict[str, Any], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Apply a partial settings change on top of ``base`` (default: the live
    settings); PUTs only what changed. Returns the echo + ``changed``."""
    fit_patch, opt_patch = split_patch(patch)
    fit, opt = base if base is not None else await read_settings(api)
    if fit_patch or base is not None:
        fit = await api.put("/settings/fit", {**fit, **fit_patch})
    if opt_patch or base is not None:
        opt = await api.put("/settings/options", {**opt, **opt_patch})
    out = echo_settings(fit, opt)
    out["changed"] = {**fit_patch, **opt_patch}
    return out


# -------------------------------------------------------------- calibrate
async def progress(ctx: Context | None, done: float, total: float, msg: str) -> None:
    if ctx is None:
        return
    try:
        await ctx.report_progress(done, max(total, 1.0), msg)
    except Exception:  # a client without progress support
        pass


async def wait_idle(api: VolfitApi, ctx: Context | None, wait_seconds: float,
                    fit_mode: str | None, prefix: str = "") -> dict[str, Any]:
    """Poll /calibration/status until idle or the budget is spent; progress forwarded."""
    t0 = monotonic()
    st = await api.get("/calibration/status", fit_mode=fit_mode)
    while st["running"] and monotonic() - t0 < wait_seconds:
        act = (st.get("activity") or {}).get("message") or ""
        await progress(ctx, float(st["done"]), float(st["total"]),
                       f"{prefix}{st.get('phase') or 'Calibrating'} {st.get('current') or ''} {act}".strip())
        await asyncio.sleep(POLL_S)
        st = await api.get("/calibration/status", fit_mode=fit_mode)
    out = compact_status(st)
    out["finished"] = not st["running"]
    out["waitedSeconds"] = round(monotonic() - t0, 1)
    return out


async def calibrate(api: VolfitApi, ctx: Context | None, *, tickers: list[str] | None = None,
                    stage: str = "all", fit_mode: str | None = None, wait_seconds: float = 90.0,
                    prefix: str = "") -> dict[str, Any]:
    """Run the calibration: all lit nodes in the background (waited on with
    progress) or the given tickers synchronously, one at a time."""
    if tickers:
        names = names_of(tickers) or []
        last: dict[str, Any] = {}
        for i, t in enumerate(names):
            await progress(ctx, float(i), float(len(names)), f"{prefix}Calibrating {t}")
            last = await api.post(f"/calibrate/{t}", fit_mode=fit_mode)
        out = compact_status(last)
        out["finished"] = not last["running"]
        out["tickers"] = names
        return out
    path = {"all": "/calibrate", "parametric": "/calibrate/parametric", "lv": "/calibrate/lv"}[stage]
    st = await api.post(path, fit_mode=fit_mode)
    if not st["running"] and st.get("litNodes", 0) == 0:
        return {**compact_status(st), "finished": True,
                "note": "no lit nodes to calibrate — fetch quotes first (fetch_quotes)"}
    return await wait_idle(api, ctx, wait_seconds, fit_mode, prefix)


# ----------------------------------------------------------------- report
async def report(api: VolfitApi, tickers: list[str] | None, fit_mode: str | None,
                 rms_budget_bp: float | None = None) -> tuple[str, dict[str, Any]]:
    """GET /quality compacted; text = the roll-up + per-expiry tables."""
    q = await api.get("/quality", fit_mode=fit_mode, rms_budget_bp=rms_budget_bp)
    out = quality_summary(q, names_of(tickers))
    s = out.get("summary") or {}
    tick_rows = [{k: t.get(k) for k in ("ticker", "nodes", "fitted", "stale", "surfaceRmsBp",
                                         "worstNodeRmsBp", "arbFlags", "dataAgeMin")} for t in out["tickers"]]
    text = [f"Fit quality (target {out['fitMode']}, readiness budget {out['rmsBudgetBp']} bp): "
            f"{s.get('readyNodes')}/{s.get('litNodes')} lit nodes ready, {s.get('stale')} stale, "
            f"{s.get('arbFlags')} arb flags, median rms {r(s.get('medianRmsBp'), 1)} bp, worst {r(s.get('worstRmsBp'), 1)} bp",
            md_table(tick_rows, ["ticker", "nodes", "fitted", "stale", "surfaceRmsBp", "worstNodeRmsBp", "arbFlags", "dataAgeMin"])]
    for t in out["tickers"]:
        lv = t.get("lv")
        if lv:
            text.append(f"{t['ticker']} Local-Vol: rms {lv.get('rmsIvErrorBp')} bp, converged {lv.get('rmsConvergedBp')} bp, "
                        f"max {lv.get('maxIvErrorBp')} bp, {'arb-free' if lv.get('arbitrageFree') else 'ARB FLAGS'}"
                        f"{' (stale)' if lv.get('stale') else ''}")
        text.append(f"{t['ticker']} expiries:\n" + md_table(
            t["expiries"], ["expiry", "nQuotes", "rmsBp", "maxIvBp", "atmVol", "skew", "leeOk", "calendarOk", "ready", "issues"]))
    return "\n".join(text), out


# ------------------------------------------------------------- LV panels
async def lv_panels(api: VolfitApi, names: list[str], fit_mode: str | None,
                    t_interp: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """The ``chart_lv_compare`` structured panels (one per ticker) + the skipped."""
    panels: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for t in names:
        body: dict[str, Any] = {"tInterp": t_interp}
        if fit_mode:
            body["fitMode"] = fit_mode
        try:
            cmp = compact_compare(await api.post(f"/fit/affine/{t}/compare", body), with_grid=True)
        except Exception as exc:  # one ticker without a fit must not sink the chart
            skipped.append({"ticker": t, "reason": str(exc)[:300]})
            continue
        panels.append({
            "ticker": cmp["ticker"], "hasAffine": cmp["hasAffine"], "affineStale": cmp["affineStale"],
            "tNodes": cmp["tNodes"], "xNodes": cmp["xNodes"],
            "affine": cmp["localVolAffine"], "twin": cmp["localVolTwin"], "diff": cmp["diffLocalVol"],
            "twinRepairs": cmp["twinRepairs"],
            "expiries": [
                {"expiry": e["expiry"], "t": e["t"],
                 "affineRmsBp": (e["affine"] or {}).get("rmsBp"),
                 "twinRmsBp": (e["twin"] or {}).get("rmsBp"),
                 "parametricRmsBp": (e["parametric"] or {}).get("rmsBp"),
                 "roundTripBp": e["roundTripBp"]}
                for e in cmp["expiries"]
            ],
        })
    return panels, skipped


def lv_panels_text(panels: list[dict[str, Any]], skipped: list[dict[str, str]]) -> list[str]:
    lines = []
    for p in panels:
        lines.append(f"{p['ticker']}: affine {'present' if p['hasAffine'] else 'MISSING'}"
                     f"{' (stale)' if p['affineStale'] else ''}, twin repairs "
                     f"{'none' if p['twinRepairs'].get('clean') else p['twinRepairs']}")
        lines.append(md_table(p["expiries"], ["expiry", "t", "affineRmsBp", "twinRmsBp", "parametricRmsBp", "roundTripBp"]))
    for s in skipped:
        lines.append(f"{s['ticker']}: skipped — {s['reason']}")
    return lines
