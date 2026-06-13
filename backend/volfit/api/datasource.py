"""Data-source registry service: status probing + active-source switching.

Backs GET /datasources and POST /datasource/{id} (volfit.api.routers.
datasource). The selector lets the user switch the active market-data feed
(Yahoo / Bloomberg / Massive / Synthetic) at runtime and shows a status light
per source: green (real-time), amber (delayed), red (unavailable).

Status comes from each provider's `feed_status()` (volfit.data.provider) — a
cheap liveness probe that hits the network / Terminal. Probes run concurrently
and are cached with a short TTL so repeated polls from the UI stay instant.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

#: Human-readable labels for the known source ids.
SOURCE_LABELS = {
    "yahoo": "Yahoo Finance",
    "bloomberg": "Bloomberg",
    "massive": "Massive",
    "synthetic": "Synthetic",
}

#: Seconds a probed status is reused before re-probing.
STATUS_TTL = 30.0

#: Per-probe wall-clock cap so one hung source can't stall the whole response.
_PROBE_TIMEOUT = 8.0


def probe_statuses(
    providers: dict[str, object], cache: dict[str, tuple[float, tuple[str, str]]]
) -> dict[str, tuple[str, str]]:
    """Return ``{id: (level, detail)}`` for every provider, probing concurrently.

    Entries fresher than ``STATUS_TTL`` are served from ``cache``; stale/missing
    ones are re-probed via ``feed_status()`` on a small thread pool. Any probe
    error (or timeout) is recorded as red so the UI always gets a verdict.
    """
    now = time.monotonic()
    todo = [sid for sid in providers if now - cache.get(sid, (0.0, None))[0] > STATUS_TTL]
    if todo:
        with ThreadPoolExecutor(max_workers=min(4, len(todo))) as pool:
            futures = {sid: pool.submit(providers[sid].feed_status) for sid in todo}
            for sid, future in futures.items():
                try:
                    cache[sid] = (now, future.result(timeout=_PROBE_TIMEOUT))
                except Exception:
                    cache[sid] = (now, ("red", "probe failed"))
    return {sid: cache[sid][1] for sid in providers}


def datasources_payload(state, refresh: bool = False) -> dict:
    """The selector payload: every source with its status + the active one."""
    statuses = state.source_statuses(refresh=refresh)
    active = state.active_source
    sources = [
        {
            "id": sid,
            "label": SOURCE_LABELS.get(sid, sid.title()),
            "status": level,
            "detail": detail,
            "active": sid == active,
        }
        for sid, (level, detail) in statuses.items()
    ]
    return {"active": active, "sources": sources}


def switch_source(state, source_id: str) -> dict:
    """Switch the active source (UnknownNodeError -> 404) and return the
    refreshed selector payload (statuses reused from cache)."""
    state.set_active_source(source_id)
    return datasources_payload(state, refresh=False)
