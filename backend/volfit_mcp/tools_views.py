"""Numeric views: one smile, the parametric surface, the LV sheet, the LV compare.

These are the "give me the numbers" tools. They read the app's cached fits
(no calibration is triggered, except that ``get_lv_surface`` on a ticker
whose LV was never fitted computes it on demand — seconds to a minute) and
return compact, rounded payloads (``volfit_mcp.report``) the model can quote
or reason over. The chart tools in ``tools_charts`` return the same data with
an inline UI attached.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from volfit_mcp import aliases
from volfit_mcp.client import VolfitApi
from volfit_mcp.report import compact_compare, compact_lv, compact_smile, md_table, r, thin

READ_ONLY = ToolAnnotations(read_only_hint=True)
FitMode = Literal["mid", "bidask", "haircut"]


def _result(text: str, structured: dict[str, Any]) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=structured)


def register(mcp: MCPServer, api: VolfitApi) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def get_smile(
        ticker: str, expiry: str, fit_mode: FitMode | None = None, max_points: int = 61
    ) -> CallToolResult:
        """One calibrated smile: the fitted IV curve (log-moneyness k = ln K/F,
        vol), the market quotes as bid/ask/mid IV bands, the saved prior curve
        when one exists, and the slice diagnostics (rms in vol bp, ATM vol,
        skew, curvature, Lee wing slopes, var-swap vol). ``expiry`` is an ISO
        date from ``list_expiries``."""
        res = aliases.resolve(ticker)
        sm = await api.get(f"/smiles/{res.ticker}/{expiry}", fit_mode=fit_mode)
        out = compact_smile(sm, max_points=max_points)
        d = out["diagnostics"]
        text = (
            f"{out['ticker']} {out['expiry']} (T={out['T']}y, F={out['forward']}) — {out['model']}"
            f"{' STALE' if out['stale'] else ''}{'' if out['hasFit'] else ' NOT FITTED'}\n"
            f"rms {d['rmsBp']} bp over {out['nQuotes']} quotes · ATM vol {d['atmVol']} · skew {d['skew']}"
            f" · curvature {d['curvature']} · Lee L/R {d['leeLeft']}/{d['leeRight']} · var-swap {d['varSwapVol']}"
        )
        return _result(text, out)

    @mcp.tool(annotations=READ_ONLY)
    async def get_vol_surface(
        ticker: str, fit_mode: FitMode | None = None, max_k_points: int = 41
    ) -> CallToolResult:
        """The parametric (LQD / SVI / sigmoid) implied-vol surface sampled on a
        shared log-moneyness grid: ``vol[i][j]`` = IV of expiry i at k[j], plus
        the exact ATM vol and forward per expiry (the term structure)."""
        res = aliases.resolve(ticker)
        sf = await api.get(f"/surface/{res.ticker}", fit_mode=fit_mode)
        pts = [{"k": k, "j": j} for j, k in enumerate(sf["k"])]
        keep = [p["j"] for p in thin(pts, max_k_points)]
        out = {
            "ticker": sf["ticker"],
            "expiries": sf["expiries"],
            "t": [r(v) for v in sf["t"]],
            "k": [r(sf["k"][j]) for j in keep],
            "vol": [[r(row[j]) for j in keep] for row in sf["vol"]],
            "atmVol": [r(v) for v in sf["atmVol"]],
            "forward": [r(v) for v in sf["forward"]],
        }
        rows = [{"expiry": e, "t": t, "atmVol": a, "forward": f}
                for e, t, a, f in zip(out["expiries"], out["t"], out["atmVol"], out["forward"])]
        text = f"{out['ticker']} term structure (ATM vol per expiry):\n" + md_table(rows, ["expiry", "t", "atmVol", "forward"])
        return _result(text, out)

    @mcp.tool(annotations=READ_ONLY)
    async def get_lv_surface(
        ticker: str, fit_mode: FitMode | None = None, include_grid: bool = True
    ) -> CallToolResult:
        """The Local-Vol (piecewise-affine local variance) surface calibrated
        straight to the ticker's quotes: the nodal local vol on the (t, x=K/F)
        vertex lattice, the surface-level fit (rms / max IV error in bp, the
        converged-operator rms to judge it by), the no-arbitrage flags
        (calendar violations, worst min density, arbitrageFree) and the
        per-expiry rms. Computes the fit on demand if it was never run."""
        res = aliases.resolve(ticker)
        body = {"fitMode": fit_mode} if fit_mode else {}
        fit = await api.post(f"/fit/affine/{res.ticker}", body)
        out = compact_lv(fit, with_grid=include_grid)
        d = out["diagnostics"]
        text = (
            f"{out['ticker']} Local-Vol surface{' STALE' if d['stale'] else ''}: rms {d['rmsIvErrorBp']} bp "
            f"(converged-operator {d['rmsConvergedBp']} bp, max {d['maxIvErrorBp']} bp), "
            f"{'arbitrage-free' if d['arbitrageFree'] else 'ARB FLAGS'} — calendar violations "
            f"{d['calendarViolations']}, worst min density {d['worstMinDensity']}, "
            f"{d['nTNodes']}x{d['nXNodes']} vertices, {d['nEvals']} PDE solves. {d['message']}\n"
            + md_table(out["expiries"], ["expiry", "t", "nQuotes", "rmsBp", "rmsConvergedBp", "maxIvErrorBp"])
        )
        return _result(text, out)

    @mcp.tool(annotations=READ_ONLY)
    async def get_lv_compare(
        ticker: str,
        fit_mode: FitMode | None = None,
        t_interp: Literal["smooth", "buckets"] = "smooth",
        include_grid: bool = False,
    ) -> CallToolResult:
        """Compare the affine Local-Vol sheet with the Dupire twin extracted
        from the parametric surface (same lattice): per-expiry rms of the
        twin, the parametric fit and the affine fit against the quotes, the
        twin's repair counters (butterfly / calendar / floor / cap clips) and,
        with ``include_grid``, the two surfaces and their signed difference.
        Use ``chart_lv_compare`` for the picture."""
        res = aliases.resolve(ticker)
        body: dict[str, Any] = {"tInterp": t_interp}
        if fit_mode:
            body["fitMode"] = fit_mode
        cmp = await api.post(f"/fit/affine/{res.ticker}/compare", body)
        out = compact_compare(cmp, with_grid=include_grid)
        rows = [
            {"expiry": e["expiry"], "t": e["t"],
             "twinRmsBp": (e["twin"] or {}).get("rmsBp"),
             "parametricRmsBp": (e["parametric"] or {}).get("rmsBp"),
             "affineRmsBp": (e["affine"] or {}).get("rmsBp"),
             "roundTripBp": e["roundTripBp"]}
            for e in out["expiries"]
        ]
        rep = out["twinRepairs"]
        text = (
            f"{out['ticker']} LV compare (t-interp {out['tInterp']}): affine "
            f"{'present' if out['hasAffine'] else 'MISSING'}{' but STALE' if out['affineStale'] else ''}; "
            f"twin repairs {'none' if rep['clean'] else rep}\n"
            + md_table(rows, ["expiry", "t", "twinRmsBp", "parametricRmsBp", "affineRmsBp", "roundTripBp"])
        )
        return _result(text, out)
