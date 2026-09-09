"""Compaction of API payloads into model-sized tool outputs.

The app's responses are built for a React front-end (dense curves, every
diagnostic, per-quote bands). A chat model needs the numbers that change a
decision — rms in bp per expiry, arbitrage flags, staleness, coverage — plus
grids small enough to ship as ``structuredContent`` for the chart apps.
Everything here is pure: dict in, dict out, floats rounded, nothing fetched.

Units: the app reports slice rms in decimal vol (``rmsError``) and surface
rms in vol basis points (``rmsIvErrorBp``); every ``...Bp`` field emitted
here is in vol bp (1 bp = 0.01 vol point) so tables read uniformly.
"""

from __future__ import annotations

from typing import Any

BP = 1e4  # decimal vol -> vol basis points


def r(x: Any, nd: int = 4) -> Any:
    """Round a float (ints, ``None`` and non-numbers pass through)."""
    return round(x, nd) if isinstance(x, float) else x


def grid(rows: list[list[Any]], nd: int = 4) -> list[list[Any]]:
    return [[r(v, nd) for v in row] for row in rows]


def thin(points: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
    """Keep at most ``max_points`` of a dense (k, vol) curve, endpoints kept."""
    n = len(points)
    if n <= max_points or max_points < 2:
        return points
    step = (n - 1) / (max_points - 1)
    idx = sorted({round(i * step) for i in range(max_points)} | {n - 1})
    return [points[i] for i in idx]


def curve(points: list[dict[str, Any]], max_points: int = 61) -> list[list[float]]:
    """A (k, vol) curve as compact ``[[k, vol], ...]`` pairs."""
    return [[r(p["k"]), r(p["vol"])] for p in thin(points, max_points)]


# ----------------------------------------------------------------- status
def compact_status(st: dict[str, Any]) -> dict[str, Any]:
    act = st.get("activity") or {}
    return {
        "running": st["running"],
        "done": st["done"],
        "total": st["total"],
        "phase": st.get("phase", ""),
        "current": st.get("current", ""),
        "error": st.get("error", ""),
        "cancelled": st.get("cancelled", False),
        "litNodes": st.get("litNodes", 0),
        "staleNodes": st.get("staleNodes", 0),
        "lvStaleTickers": st.get("lvStaleTickers", 0),
        "epoch": st.get("epoch", 0),
        "activity": act.get("message") or act.get("stage") or "",
    }


# --------------------------------------------------------------- universe
def compact_universe(uni: dict[str, Any], lit: dict[str, Any] | None = None) -> dict[str, Any]:
    lit_by: dict[str, list[str]] = {}
    if lit:
        for node in lit.get("nodes", []):
            if node.get("lit"):
                lit_by.setdefault(node["ticker"], []).append(node["expiry"])
    sources = uni.get("tickerSources") or {}
    out = []
    for t in uni.get("tickers", []):
        ladder = [e["expiry"] for e in uni.get("expiries", {}).get(t, [])]
        row: dict[str, Any] = {
            "ticker": t,
            "source": sources.get(t) or uni.get("defaultSource") or "",
            "nExpiries": len(ladder),
            "expiries": ladder,
        }
        if lit is not None:
            row["litExpiries"] = lit_by.get(t, [])
        err = (uni.get("errors") or {}).get(t)
        if err:
            row["error"] = err
        out.append(row)
    return {"asOf": uni.get("asOf"), "defaultSource": uni.get("defaultSource", ""), "tickers": out}


# ---------------------------------------------------------------- quality
_NODE_KEYS = ("expiry", "tau", "hasFit", "stale", "model", "nQuotes", "rmsBp", "maxIvBp",
              "atmVol", "skew", "leeOk", "calendarOk", "ready", "issues", "dataAgeMin")


def quality_summary(q: dict[str, Any], tickers: list[str] | None = None) -> dict[str, Any]:
    """Per-ticker roll-up + per-node rows of ``GET /quality``."""
    want = set(tickers) if tickers else None
    nodes_by: dict[str, list[dict[str, Any]]] = {}
    for n in q.get("nodes", []):
        if want and n["ticker"] not in want:
            continue
        row = {k: r(n.get(k), 4) for k in _NODE_KEYS if k in n}
        nodes_by.setdefault(n["ticker"], []).append(row)
    tick = []
    for t in q.get("tickers", []):
        if want and t["ticker"] not in want:
            continue
        row = {k: r(t.get(k), 2) for k in ("ticker", "nodes", "fitted", "stale", "surfaceRmsBp",
                                            "worstNodeRmsBp", "arbFlags", "extrapFlags", "dataAgeMin")
               if k in t}
        lv = t.get("lv")
        if isinstance(lv, dict):
            row["lv"] = {k: r(lv.get(k), 2) for k in ("hasFit", "stale", "rmsIvErrorBp", "maxIvErrorBp",
                                                      "rmsConvergedBp", "arbitrageFree",
                                                      "calendarViolations", "worstMinDensity")
                         if k in lv}
        row["expiries"] = nodes_by.get(t["ticker"], [])
        tick.append(row)
    return {
        "fitMode": q.get("fitMode"),
        "rmsBudgetBp": q.get("rmsBudgetBp"),
        "summary": q.get("summary"),
        "tickers": tick,
    }


# --------------------------------------------------------------- local vol
def lv_diagnostics(fit: dict[str, Any]) -> dict[str, Any]:
    return {
        "hasFit": fit.get("hasFit", True),
        "stale": fit.get("stale", False),
        "rmsIvErrorBp": r(fit.get("rmsIvErrorBp"), 1),
        "maxIvErrorBp": r(fit.get("maxIvErrorBp"), 1),
        "rmsConvergedBp": r(fit.get("rmsConvergedBp"), 1),
        "arbitrageFree": fit.get("arbitrageFree"),
        "calendarViolations": fit.get("calendarViolations"),
        "worstMinDensity": r(min(fit.get("minDensity") or [0.0]), 5),
        "nEvals": fit.get("nEvals"),
        "message": fit.get("message", ""),
        "nTNodes": len(fit.get("tNodes") or []),
        "nXNodes": len(fit.get("xNodes") or []),
    }


def lv_smile_rows(fit: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "expiry": s["expiry"],
            "t": r(s.get("t"), 4),
            "nQuotes": len(s.get("quotes") or []),
            "rmsBp": r(BP * float(s.get("rmsError", 0.0)), 1),
            "rmsConvergedBp": r(s.get("rmsConvergedBp"), 1),
            "maxIvErrorBp": r(s.get("maxIvErrorBp"), 1),
        }
        for s in fit.get("smiles", [])
    ]


def compact_lv(fit: dict[str, Any], *, with_grid: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ticker": fit["ticker"],
        "diagnostics": lv_diagnostics(fit),
        "expiries": lv_smile_rows(fit),
    }
    if with_grid:
        out["tNodes"] = [r(v) for v in fit.get("tNodes", [])]
        out["xNodes"] = [r(v) for v in fit.get("xNodes", [])]
        out["localVol"] = grid(fit.get("localVol", []))
    return out


def _score(s: dict[str, Any] | None) -> dict[str, Any] | None:
    if not s:
        return None
    rms_bp = s.get("rmsBp")
    if rms_bp is None:
        rms_bp = BP * float(s.get("rmsError", 0.0))
    return {"rmsBp": r(rms_bp, 1), "maxBp": r(s.get("maxBp"), 1), "convergedBp": r(s.get("convergedBp"), 1)}


def compact_compare(cmp: dict[str, Any], *, with_grid: bool = True) -> dict[str, Any]:
    """The Local Vol lens's Compare payload: the affine sheet vs the Dupire
    twin of the parametric surface, with per-expiry scores."""
    counters = cmp.get("counters") or {}
    out: dict[str, Any] = {
        "ticker": cmp["ticker"],
        "tInterp": cmp.get("tInterp"),
        "hasAffine": cmp.get("hasAffine"),
        "affineStale": cmp.get("affineStale"),
        "twinRepairs": {
            "clean": counters.get("clean"),
            "butterfly": sum(counters.get("butterfly") or []),
            "calendar": sum(counters.get("calendar") or []),
            "floored": sum(counters.get("floored") or []),
            "capped": sum(counters.get("capped") or []),
        },
        "expiries": [
            {
                "expiry": s["expiry"],
                "t": r(s.get("t"), 4),
                "twin": _score(s.get("twinScore")),
                "parametric": _score(s.get("parametricScore")),
                "affine": _score(s.get("affineScore")),
                "roundTripBp": r(s.get("roundTripBp"), 1),
            }
            for s in cmp.get("smiles", [])
        ],
    }
    if with_grid:
        out["tNodes"] = [r(v) for v in cmp.get("tNodes", [])]
        out["xNodes"] = [r(v) for v in cmp.get("xNodes", [])]
        out["localVolTwin"] = grid(cmp.get("localVolTwin", []))
        out["localVolAffine"] = grid(cmp.get("localVolAffine", []))
        out["diffLocalVol"] = grid(cmp.get("diffLocalVol", []))
    return out


# ------------------------------------------------------------------ smile
def compact_smile(sm: dict[str, Any], *, max_points: int = 61) -> dict[str, Any]:
    d = sm.get("diagnostics") or {}
    info = sm.get("modelInfo") or {}
    out: dict[str, Any] = {
        "ticker": sm["ticker"],
        "expiry": sm["expiry"],
        "T": r(sm.get("T")),
        "forward": r(sm.get("forward")),
        "hasFit": sm.get("hasFit", True),
        "stale": sm.get("stale", False),
        "model": info.get("label") or info.get("id"),
        "modelParams": {p["label"]: p["value"] for p in info.get("params", [])},
        "diagnostics": {
            "rmsBp": r(BP * float(d.get("rmsError", 0.0)), 1),
            "atmVol": r(d.get("atmVol")),
            "skew": r(d.get("skew")),
            "curvature": r(d.get("curvature")),
            "leeLeft": r(d.get("leeLeft")),
            "leeRight": r(d.get("leeRight")),
            "varSwapVol": r(d.get("varSwapVol")),
        },
        "nQuotes": len(sm.get("quotes") or []),
        "quotes": [
            {"k": r(q["k"]), "bid": r(q["bid"]), "ask": r(q["ask"]), "mid": r(q["mid"]),
             **({"excluded": True} if q.get("excluded") else {})}
            for q in sm.get("quotes") or []
        ],
        "fit": curve(sm.get("model") or [], max_points),
    }
    if sm.get("prior"):
        out["prior"] = curve(sm["prior"], max_points)
    if sm.get("degraded"):
        out["degraded"] = sm["degraded"]
    return out


# ------------------------------------------------------------------ text
def md_table(rows: list[dict[str, Any]], cols: list[str]) -> str:
    """A small Markdown table (the text half of a tool result)."""
    if not rows:
        return "(none)"
    head = "| " + " | ".join(cols) + " |\n|" + "|".join("---" for _ in cols) + "|\n"
    body = "\n".join("| " + " | ".join(_cell(row.get(c)) for c in cols) + " |" for row in rows)
    return head + body


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.4g}" if abs(v) < 1e-2 or abs(v) >= 1e4 else f"{v:.2f}".rstrip("0").rstrip(".")
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v)
