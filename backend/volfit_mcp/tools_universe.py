"""Universe + data tools: what to fetch, from where, and the fetch itself.

Thin wrappers over ``volfit_mcp.ops`` (the venue logic lives there, shared
with the macro tools): spoken names resolve through ``aliases`` and every
ticker is pinned to the first registered source that carries it and is not
red (Bloomberg for SX5E when the Terminal is up, else Eurex; Cboe / Massive /
Yahoo for SPX ...), so a mixed EU / US universe just works.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from volfit_mcp import aliases, ops
from volfit_mcp.client import VolfitApi
from volfit_mcp.report import compact_universe

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
        Follow with ``fetch_preview`` / ``fetch_quotes`` — or use
        ``run_desk_workflow`` to do the whole routine in one call."""
        return await ops.set_universe(api, tickers, replace, source)

    @mcp.tool(annotations=READ_ONLY)
    async def get_universe() -> dict[str, Any]:
        """The current universe: tickers, their data source, expiry ladders and
        which expiries are lit (calibrated) vs dark (graph-inferred only)."""
        return compact_universe(await api.get("/universe"), await api.get("/universe/lit"))

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
        tickers: list[str] | None = None, fit_mode: str | None = None, max_age_seconds: float | None = None
    ) -> str:
        """Fetch option chains (bid/ask/mid) + spots for the universe (or the
        given tickers) from each ticker's pinned source, transport the existing
        fits to the new spot and, when auto-calibrate is on, start a background
        calibration. ``fit_mode`` = mid | bidask | haircut (default: the app's
        current target). ``max_age_seconds`` leaves chains younger than that
        alone (no re-quote). Returns the spots and whether a calibration started;
        call ``calibrate`` next if it did not."""
        text, _ = await ops.fetch_quotes(api, tickers, fit_mode, max_age_seconds)
        return text
