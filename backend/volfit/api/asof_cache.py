"""Store-first as-of chains (2026-09-24).

WHY: an ``eod`` / ``intraday`` as-of used to go straight to the provider on
every read. On Massive a past instant is REBUILT from up to 1,500 per-contract
NBBO calls (~12.7 s per ticker), and the same instant was rebuilt again on the
next Fetch, on a second lens, on a Calibrate-after-Fetch — while the VolStore
already held that very chain: the Series lens saves every harvested frame as a
snapshot row, and the previous as-of read could have saved its own result.

THE RULE: for ``eod`` (instant = the session close of the day) and ``intraday``
(instant = the picked timestamp) the store is consulted FIRST — the ticker's
row AT that exact instant, from the ticker's own source (or a legacy untagged
row), series frames and earlier reconstructions included — and served when it
covers the selection asked for; otherwise the provider is asked and the
result SAVED under ``ASOF_CACHE_TAG`` so the next read costs zero calls. A
save never fails a fetch. ``live`` / ``prev_close`` / ``captured`` are untouched
(a live chain is a capture, a prev-close rolls with the session, a captured
replay is already a store read).

MARKS NEVER SHADOW QUOTES: a stored ``marks`` frame (one close per contract,
bid = ask — Massive's aggregate fallback when the NBBO history was gated at
the time) must not pre-empt a later attempt at the real two-sided market. A
stored row is reused only when its kind is "quotes", or when the provider's
own ``historical_quote_kind()`` is "marks" (it cannot do better anyway). A
pre-v12 row of unknown kind counts as marks. Conversely a fetched marks
chain is never saved OVER an existing row at the instant (it would only
duplicate the row it failed to improve on).

COVERAGE: a reconstruction records the ladder it was fetched for
(``request_json``), so "this expiry was asked for and the feed had nothing"
(a weekly listed after the instant) still covers a later request for it — a
content-only test would refetch that instant forever. Captures and series
frames carry no request: they cover a selection when their expiries do.

FINALITY: only an instant at or before the latest COMPLETED session's close
is cached — today's intraday instant is served live by Massive and must not
be frozen under a past-instant key.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from volfit.data.expiry_time import latest_completed_session, session_close_utc
from volfit.data.provider import AsOf
from volfit.data.store import ASOF_CACHE_TAG, SnapshotMeta, VolStore
from volfit.data.types import ChainSnapshot


def instant_of(sel) -> datetime | None:
    """The store key of an as-of selection: the session close for ``eod``,
    the picked timestamp for ``intraday``; None for every other mode."""
    if sel.mode == "eod" and sel.on is not None:
        return session_close_utc(sel.on)
    if sel.mode == "intraday" and sel.ts is not None:
        return sel.ts
    return None


def is_final(instant: datetime, now_utc: datetime | None = None) -> bool:
    """Whether history at ``instant`` can no longer change: the session that
    holds it has closed (at or before the latest completed session's close)."""
    now = now_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    return instant <= session_close_utc(latest_completed_session(now))


def reusable(meta: SnapshotMeta, provider_kind: str) -> bool:
    """The marks-never-shadow-quotes rule (module docstring)."""
    return meta.quote_kind == "quotes" or provider_kind == "marks"


def covers(meta: SnapshotMeta, chain: ChainSnapshot, chosen) -> bool:
    """Whether the stored row answers a request for ``chosen``: by the ladder
    it was fetched for when recorded, else by the expiries it holds."""
    have = set(meta.request) if meta.request is not None else set(chain.expiries())
    return set(chosen) <= have


def crop(chain: ChainSnapshot, chosen) -> ChainSnapshot:
    """The stored chain restricted to ``chosen`` — what the provider would
    have returned for that request (a per-expiry independent rebuild)."""
    want = set(chosen)
    kept = [q for q in chain.quotes if q.expiry in want]
    settlement = None
    if chain.settlement:
        settlement = {e: s for e, s in chain.settlement.items() if e in want}
    return replace(chain, quotes=kept, settlement=settlement)


def _provider_asof(sel) -> AsOf:
    return AsOf(mode=sel.mode, on=sel.on) if sel.mode == "eod" else AsOf(mode="intraday", ts=sel.ts)


def fetch_asof_chain(state, prov, ticker: str, chosen, sel) -> ChainSnapshot:
    """The ``eod`` / ``intraday`` chain of ``ticker`` for ``chosen``: the store
    first, the provider on a miss (then saved). ``state`` supplies the store
    path and the ticker's source id; ``prov`` is the ticker's provider."""
    instant = instant_of(sel)
    asof = _provider_asof(sel)
    if state.store_path is None or instant is None or not is_final(instant):
        return prov.fetch_chain(ticker, chosen, as_of=asof)
    sid = state.source_of(ticker)
    existing: SnapshotMeta | None = None
    try:
        with VolStore(state.store_path) as store:
            existing = store.snapshot_meta_at(ticker, instant, source=sid, include_series=True, exact=True)
            if existing is not None and reusable(existing, prov.historical_quote_kind()):
                stored = store.load_snapshot(existing.id)
                if stored.quotes and covers(existing, stored, chosen):
                    return crop(stored, chosen)
    except Exception:  # noqa: BLE001 — the store is a cache; the provider is the truth
        existing = None
    chain = prov.fetch_chain(ticker, chosen, as_of=asof)
    _save(state.store_path, chain, sid, instant, chosen, existing)
    return chain


def _save(store_path, chain: ChainSnapshot, sid: str, instant: datetime, chosen, existing) -> None:
    """Best-effort: persist a reconstruction keyed at ``instant`` (the row's
    stamp IS the key; the served chain keeps the provider's own stamp) with
    the ladder it was fetched for. An empty chain is never saved (nothing to
    reuse) and marks never overwrite an existing row (see the module)."""
    if not chain.quotes or (existing is not None and chain.quote_kind != "quotes"):
        return
    try:
        with VolStore(store_path) as store:
            store.save_snapshot(
                replace(chain, timestamp=instant), source=sid, series_id=ASOF_CACHE_TAG,
                request=list(chosen),
            )
    except Exception:  # noqa: BLE001 — never fail a fetch on a save
        pass
