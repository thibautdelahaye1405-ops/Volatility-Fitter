"""Fetch coverage preview (workbench follow-on, 2026-08-27; ROADMAP "As-of →
Fetch ▾" proposal): what the NEXT Fetch would serve per active ticker under
the current global as-of selection and the active provider — shown in the
Fetch menu before the user pulls ("14:30 · 9/12 nodes exact · 3 fall back
to close").

NO network call — cached state only:

* the requested moment comes from ``AppState.as_of`` (+ ``node_asof.
  requested_day`` for the day it asks for);
* whether the source honors it comes from the provider's ADVERTISED
  capabilities (``historical_modes()`` for prev_close / eod,
  ``intraday_capable()`` for an intraday instant; a captured replay is the
  app's own store, honored by construction; live always is) — the same
  reads ``api.asof`` makes for the dropdown;
* once a chain is loaded, the per-node effective as-of (``node_asof``) is
  EVIDENCE that overrides the advertisement: a provider that advertises a
  close but serves a chain stamped off the requested session (the
  ``_IgnoringProvider`` of the tests; a live-only feed behind a wrapper)
  does not honor it, whatever it claims.

The fallback label names what the source serves instead: ``"live"`` when
it ignores the as-of (its latest chain — the stamp sits on the reference
date), ``"close"`` when it serves another session's close. Every node of a
ticker shares one ChainSnapshot, so a ladder is exact or falls back whole.
"""

from __future__ import annotations

from datetime import date

from volfit.api.node_asof import node_effective_asof, requested_day
from volfit.api.schemas_fetch_preview import (
    FetchPreview,
    FetchPreviewTicker,
    FetchPreviewTotals,
)
from volfit.api.state import AppState, AsOfSelection


def _advertised(state: AppState, sel: AsOfSelection) -> bool:
    """Whether the active provider CAN serve the requested selection: the mode
    is supported, an EOD day is in its history, an intraday instant is a PAST
    session (today's would silently be the live chain)."""
    mode = sel.mode
    if mode in ("live", "captured"):
        return True  # live IS the moment; a capture is replayed from the store
    if mode == "intraday":
        if not state.provider.intraday_capable() or sel.ts is None:
            return False
        return sel.ts.date() < state.reference_date
    if mode not in state.provider.historical_modes():
        return False
    if mode == "eod" and sel.on is not None:
        try:
            tickers = state.active_tickers()
            history = state.provider.available_history(tickers[0]) if tickers else []
        except Exception:  # noqa: BLE001 — an unreadable history: trust the mode
            return True
        return not history or sel.on in set(history)
    return True


def _fallback_kind(state: AppState, stamp: str | None) -> str:
    """"live" when the served (or expected) chain is today's, else "close"."""
    if stamp is not None and stamp[:10] != state.reference_date.isoformat():
        return "close"
    return "live"


def _ticker_preview(
    state: AppState, ticker: str, sel: AsOfSelection, day: date | None
) -> FetchPreviewTicker:
    """One ticker's row: ladder size, advertised-vs-evidenced honoring, fallback."""
    try:
        nodes = len(state.selected_expiries(ticker))
    except Exception:  # noqa: BLE001 — an unresolved ladder previews as empty
        nodes = 0
    stamp, _source, exact = node_effective_asof(state, ticker)
    honors = _advertised(state, sel) and exact is not False
    fallback: str | None = None
    if not honors:
        # Advertised-but-inexact: the loaded stamp says what was served; not
        # advertised: the provider ignores the as-of and serves its live chain.
        fallback = _fallback_kind(state, stamp) if exact is False else "live"
    return FetchPreviewTicker(
        ticker=ticker,
        nodes=nodes,
        requestedMode=sel.mode,
        requestedDay=day.isoformat() if day is not None else None,
        providerHonors=honors,
        fallback=fallback,
        currentlyExact=exact,
        effectiveAsOf=stamp,
    )


def _head(state: AppState, sel: AsOfSelection, day: date | None) -> str:
    """The selection's short name: "Live" / "Previous close" / "<day> close"
    / "HH:MM" (UTC; prefixed by the day when it is not the reference date)."""
    if sel.mode == "live":
        return "Live"
    if sel.mode == "prev_close":
        return "Previous close"
    if sel.mode == "eod":
        return f"{day.isoformat()} close" if day is not None else "Close"
    clock = sel.ts.strftime("%H:%M") if sel.ts is not None else "intraday"
    if day is not None and day != state.reference_date:
        return f"{day.isoformat()} {clock}"
    return clock


def _summary(head: str, mode: str, rows: list[FetchPreviewTicker], totals: FetchPreviewTotals) -> str:
    if not rows or totals.nodes == 0:
        return f"{head} · no nodes to fetch"
    if totals.fallback == 0:
        if mode == "live":
            return f"{head} · {totals.exact}/{totals.nodes} nodes"
        return f"{head} · provider serves it · {totals.nodes} nodes"
    kinds = sorted({r.fallback for r in rows if r.fallback}, reverse=True)  # live before close
    return (
        f"{head} · {totals.exact}/{totals.nodes} nodes exact"
        f" · {totals.fallback} fall back to {' or '.join(kinds)}"
    )


def fetch_preview(state: AppState) -> FetchPreview:
    """The coverage preview of the next Fetch under the current selection."""
    sel = state.as_of
    day = requested_day(sel, state.reference_date)
    rows = [_ticker_preview(state, t, sel, day) for t in state.active_tickers()]
    exact = sum(r.nodes for r in rows if r.providerHonors)
    total = sum(r.nodes for r in rows)
    totals = FetchPreviewTotals(nodes=total, exact=exact, fallback=total - exact)
    head = _head(state, sel, day)
    return FetchPreview(
        mode=sel.mode,
        requestedDay=day.isoformat() if day is not None else None,
        dataSource=state.active_source,
        summary=_summary(head, sel.mode, rows, totals),
        totals=totals,
        tickers=rows,
    )
