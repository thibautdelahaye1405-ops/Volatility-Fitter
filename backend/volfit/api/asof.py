"""As-of (timestamp) service: capabilities + selection.

Backs GET /asof and POST /asof (volfit.api.routers.asof). The as-of selector
under Data Source chooses *when* chains are observed: Live, Previous Close, a
provider EOD trading day, or a captured intraday snapshot replayed from the
VolStore. The active provider declares which historical modes it supports
(volfit.data.provider.historical_modes / available_history); captured intraday
moments come from the store's snapshot history.
"""

from __future__ import annotations

from datetime import date, datetime

from volfit.api.state import AppState, AsOfSelection
from volfit.data.store import VolStore


def _captured_timestamps(state: AppState) -> list[datetime]:
    """Distinct captured snapshot moments (newest first) for the active universe,
    deduped to one per minute (keeping the latest in each minute)."""
    if state.store_path is None:
        return []
    tickers = state.active_tickers()
    if not tickers:
        return []
    try:
        with VolStore(state.store_path) as store:
            rows = store.list_snapshots(tickers)  # newest first
    except Exception:
        return []
    seen: set[datetime] = set()
    out: list[datetime] = []
    for _ticker, _sid, ts in rows:
        bucket = ts.replace(second=0, microsecond=0)
        if bucket in seen:
            continue
        seen.add(bucket)
        out.append(ts)  # the newest capture in this minute
    return out


def asof_payload(state: AppState) -> dict:
    """Current as-of selection plus what the active source/store can offer."""
    modes = state.provider.historical_modes()
    tickers = state.active_tickers()
    history: list[date] = []
    if "eod" in modes and tickers:
        try:
            history = state.provider.available_history(tickers[0])
        except Exception:
            history = []
    sel = state.as_of
    return {
        "mode": sel.mode,
        "on": sel.on.isoformat() if sel.on else None,
        "ts": sel.ts.isoformat() if sel.ts else None,
        "supportedModes": sorted(modes),
        "prevCloseAvailable": "prev_close" in modes,
        "historyDates": [d.isoformat() for d in reversed(history)],  # newest first
        "captured": [ts.isoformat() for ts in _captured_timestamps(state)],
    }


def set_asof(
    state: AppState, mode: str, on: str | None, ts: str | None
) -> dict:
    """Apply an as-of selection (UnknownNodeError -> 404, bad dates -> 422)."""
    selection = AsOfSelection(
        mode=mode,
        on=date.fromisoformat(on) if on else None,
        ts=datetime.fromisoformat(ts) if ts else None,
    )
    state.set_as_of(selection)
    return asof_payload(state)
