"""Universe + data tools: what to fetch, from where, and the fetch itself.

``set_universe`` is the one tool with venue logic: spoken names resolve
through ``volfit_mcp.aliases`` and every ticker is pinned to the first
registered source that carries it and is not red (Bloomberg for SX5E when the
Terminal is up, else Eurex; Cboe / Massive / Yahoo for SPX ...), so a mixed
EU / US universe just works. Everything else is a straight pass-through with
compact output (``volfit_mcp.report``).
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from volfit_mcp import aliases
from volfit_mcp.client import VolfitApi
from volfit_mcp.report import compact_universe, md_table

READ_ONLY = ToolAnnotations(read_only_hint=True)
MUTATING = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True)


def register(mcp: MCPServer, api: VolfitApi) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def list_data_sources(refresh: bool = False) -> dict[str, Any]:
        """List the registered market-data sources with their status light
        (green = real-time, amber = delayed, red = unreachable), which one is
        the universe default, which tickers each serves now, and the age of the
        loaded data. ``refresh=True`` re-probes every source (slow-ish)."""
        ds = await api.get("/datasources", refresh=True if refresh else None)
        return {
            "active": ds["active"],
            "dataAge": ds.get("dataAge"),
            "sources": [
                {k: s.get(k) for k in ("id", "label", "status", "detail", "active", "tickers")}
                for s in ds["sources"]
            ],
        }

    @mcp.tool(annotations=MUTATING)
    async def set_universe(
        tickers: list[str], replace: bool = True, source: str | None = None
    ) -> dict[str, Any]:
        """Choose the tickers to work on. Spoken names are accepted ("EuroStoxx",
        "SPX", "the Dax", "AAPL"); each resolves to the app's ticker and is
        pinned to the best registered source that lists it (``source`` forces
        one for all). ``replace=True`` (default) drops every other ticker from
        the universe; ``replace=False`` adds to it. Returns the universe with
        each ticker's expiry ladder and any "not listed on <source>" error.
        Follow with ``fetch_preview`` / ``fetch_quotes``."""
        ds = await api.get("/datasources")
        registered = {s["id"]: s.get("status", "red") for s in ds["sources"]}
        usable = [sid for sid, st in registered.items() if st != "red"]
        resolved = aliases.resolve_many(tickers)
        if not resolved:
            raise ValueError("no tickers given")
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
            uni = await api.get("/universe")
            for t in uni.get("tickers", []):
                if t.upper() not in keep:
                    await api.delete(f"/universe/tickers/{t}")
        uni = await api.get("/universe")
        lit = await api.get("/universe/lit")
        out = compact_universe(uni, lit)
        out["resolution"] = plan
        out["registeredSources"] = registered
        return out

    @mcp.tool(annotations=READ_ONLY)
    async def get_universe() -> dict[str, Any]:
        """The current universe: tickers, their data source, expiry ladders and
        which expiries are lit (calibrated) vs dark (graph-inferred only)."""
        uni = await api.get("/universe")
        lit = await api.get("/universe/lit")
        return compact_universe(uni, lit)

    @mcp.tool(annotations=READ_ONLY)
    async def list_expiries(ticker: str) -> dict[str, Any]:
        """The expiry picker of one ticker: every listed expiry with its bucket
        (0dte / weekly / monthly / quarterly), days to expiry and whether it is
        selected in the fitted ladder."""
        res = aliases.resolve(ticker)
        pick = await api.get(f"/universe/{res.ticker}/expiries")
        rows = [{k: e.get(k) for k in ("expiry", "days", "bucket", "selected")} for e in pick["expiries"]]
        return {"ticker": pick["ticker"], "asOf": pick["asOf"], "mode": pick["mode"], "expiries": rows}

    @mcp.tool(annotations=READ_ONLY)
    async def fetch_preview() -> dict[str, Any]:
        """Dry-run of the next fetch: how many nodes each source honours at
        the requested moment (live vs previous close) and the effective as-of
        per ticker. Read this before ``fetch_quotes`` when the data source or
        as-of matters."""
        return await api.get("/fetch/preview")

    @mcp.tool(annotations=MUTATING)
    async def fetch_quotes(
        tickers: list[str] | None = None, fit_mode: str | None = None
    ) -> str:
        """Fetch option chains (bid/ask/mid) + spots for the universe (or the
        given tickers) from each ticker's pinned source, transport the existing
        fits to the new spot and, when auto-calibrate is on, start a background
        calibration. ``fit_mode`` = mid | bidask | haircut (default: the app's
        current target). Returns the spots and whether a calibration started;
        call ``calibrate`` next if it did not."""
        body = {"tickers": [aliases.resolve(t).ticker for t in tickers]} if tickers else {}
        res = await api.post("/fetch/snapshot", body, fit_mode=fit_mode)
        uni = await api.get("/universe")
        errors = uni.get("errors") or {}
        ds = await api.get("/datasources")
        lines = [
            f"Fetched {len(res['tickers'])} ticker(s): "
            + ", ".join(f"{t} @ {res['spots'].get(t, float('nan')):.4g}" for t in res["tickers"]),
            f"Background calibration started: {'yes' if res['calibrationStarted'] else 'no'}",
        ]
        if ds.get("dataAge"):
            lines.append(f"Data age: {ds['dataAge']['label']} ({ds['dataAge']['level']}, worst {ds['dataAge']['worstTicker']})")
        if errors:
            lines.append("Errors: " + md_table([{"ticker": k, "error": v} for k, v in errors.items()], ["ticker", "error"]))
        return "\n".join(lines)
