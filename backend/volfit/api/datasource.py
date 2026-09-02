"""Data-source registry service: status probing + active-source switching.

Backs GET /datasources and POST /datasource/{id} (volfit.api.routers.
datasource). The selector lets the user switch the active market-data feed
(Yahoo / Bloomberg / Massive / Synthetic) at runtime and shows a status light
per source: green (real-time), amber (delayed), red (unavailable).

Status comes from each provider's `feed_status()` (volfit.data.provider) — a
cheap liveness probe that hits the network / Terminal. Probes run concurrently
on a long-lived pool the request thread never JOINS (a hung venue probe used
to block the whole /datasources answer — and the source SWITCH after it —
until the socket gave up), are capped per probe, and are cached with a short
TTL so repeated polls from the UI stay instant. A switch never probes: it
answers from the cache so changing source is always instant.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

#: Human-readable labels for the known source ids.
SOURCE_LABELS = {
    "yahoo": "Yahoo Finance",
    "bloomberg": "Bloomberg",
    "massive": "Massive",
    "cboe": "Cboe (delayed)",
    "nasdaq": "Nasdaq (delayed)",
    "asx": "ASX (delayed)",
    "hkex": "HKEX (delayed)",
    "sgx": "SGX (delayed)",
    "eurex": "Eurex (delayed / EOD)",
    "synthetic": "Synthetic",
    "file": "File",
}


def source_label(sid: str, provider: object | None = None) -> str:
    """Selector label: a provider's own ``label`` (the file source names its
    loaded files) wins over the static table."""
    own = getattr(provider, "label", None) if provider is not None else None
    return own if isinstance(own, str) and own else SOURCE_LABELS.get(sid, sid.title())

#: Seconds a probed status is reused before re-probing.
STATUS_TTL = 30.0

#: Per-probe wall-clock cap so one hung source can't stall the whole response.
_PROBE_TIMEOUT = 8.0

#: Long-lived probe pool (never joined by a request) + the probes still in
#: flight per source, so a hung probe is awaited again on the next poll rather
#: than re-submitted every 30 s until the pool is full of stuck sockets.
_PROBE_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="volfit-probe")
_INFLIGHT: dict[int, Future] = {}
_INFLIGHT_LOCK = threading.Lock()

#: The verdict while a source's probe is still running / not yet run.
PENDING_STATUS = ("amber", "status pending")


def probe_statuses(
    providers: dict[str, object],
    cache: dict[str, tuple[float, tuple[str, str]]],
    probe: bool = True,
) -> dict[str, tuple[str, str]]:
    """Return ``{id: (level, detail)}`` for every provider.

    Entries fresher than ``STATUS_TTL`` are served from ``cache``; stale/missing
    ones are re-probed via ``feed_status()`` on the shared pool and awaited up
    to ``_PROBE_TIMEOUT`` each — a probe that outlives the cap is recorded red
    ("probe timed out") and left running; the next poll collects it instead of
    stacking another. ``probe=False`` (the source switch) never probes: it
    answers from the cache, ``PENDING_STATUS`` for what was never probed.
    """
    now = time.monotonic()
    todo = [sid for sid in providers if now - cache.get(sid, (0.0, None))[0] > STATUS_TTL]
    if todo and probe:
        futures: dict[str, Future] = {}
        with _INFLIGHT_LOCK:
            for sid in todo:
                key = id(providers[sid])
                fut = _INFLIGHT.get(key)
                if fut is None or fut.done():
                    fut = _PROBE_POOL.submit(providers[sid].feed_status)
                    _INFLIGHT[key] = fut
                futures[sid] = fut
        deadline = time.monotonic() + _PROBE_TIMEOUT
        for sid, future in futures.items():
            try:
                cache[sid] = (now, future.result(timeout=max(0.0, deadline - time.monotonic())))
            except TimeoutError:
                cache[sid] = (now, ("red", f"probe timed out ({_PROBE_TIMEOUT:.0f} s)"))
            except Exception as exc:  # noqa: BLE001 — a failed probe is a verdict, not an error
                cache[sid] = (now, ("red", f"probe failed: {exc}"[:120]))
    return {sid: cache.get(sid, (0.0, PENDING_STATUS))[1] for sid in providers}


def datasources_payload(state, refresh: bool = False, probe: bool = True) -> dict:
    """The selector payload: every source with its status + the active one,
    plus the worst loaded-chain data age (volfit.api.data_age; None when not
    live / nothing fetched) — the TopBar market pill and the Calibrate
    stale-data hint both read it off this poll. ``probe=False`` answers from
    the status cache only (the switch must never wait on a feed)."""
    from volfit.api.data_age import universe_age

    statuses = state.source_statuses(refresh=refresh, probe=probe)
    active = state.active_source
    providers = {sid: state._providers.get(sid) for sid in statuses}
    sources = [
        {
            "id": sid,
            "label": source_label(sid, providers.get(sid)),
            "status": level,
            "detail": detail,
            "active": sid == active,
        }
        for sid, (level, detail) in statuses.items()
    ]
    return {"active": active, "sources": sources, "dataAge": universe_age(state)}


def switch_source(state, source_id: str) -> dict:
    """Switch the active source (UnknownNodeError -> 404) and return the
    selector payload from the status CACHE — never a probe, so a switch away
    from a hung feed is instant (the next /datasources poll re-probes)."""
    state.set_active_source(source_id)
    return datasources_payload(state, refresh=False, probe=False)
