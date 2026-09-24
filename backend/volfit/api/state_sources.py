"""Per-ticker data sources — the multi-source engine (2026-09-02h).

The universe fetches from ONE default source (the Data Source selector,
``AppState.active_source``) unless a ticker is PINNED to another registered
source (``set_ticker_source``): a Eurex index on Bloomberg while the rest of
the universe streams from Massive, a snapshot-file name beside live ones.
Every per-ticker provider call routes through ``provider_for(ticker)``; the
pins are workspace-scoped (``Workspace.ticker_sources``), saved with a named
universe, and survive a switch of the default source (only the tickers that
FOLLOW the default refetch then — ``AppState.set_active_source``).

Streaming follows the same map: a streaming-capable provider opens its book
iff ``autoStream`` is on and it serves at least one active ticker, on that
ticker set's contracts; ``is_streaming(ticker)`` answers per ticker, so the
scheduler runs its streaming branch for the streaming tickers and the
Auto-update timer for the rest in the same tick (``streaming_tickers`` /
``request_tickers``). The FOCUS (volfit.api.stream_focus: the nodes with an
open tick-stream SSE) is pushed to each provider on every sync; a provider
re-plans its live set only when its focus changed (``set_stream_focus``
returns whether it did), and ``stream_tier(ticker, expiry)`` says how a node
is served — live socket, the per-minute REST memory, or not at all.

The pin value ``AUTO_SOURCE`` ("auto", volfit.api.source_policy) resolves to
the fastest green source that can serve the ticker; the resolution is
remembered and re-ranked only at Fetch time (``refresh_auto_source``).

Mixed into ``AppState`` (which owns ``_providers``, ``_active_source``,
``_ticker_sources`` [workspace-scoped], ``_active_tickers``, the per-ticker
caches and ``_lock``; ``_require_active`` comes from the universe mixin).
"""

from __future__ import annotations

from datetime import date

from volfit.api.source_policy import AUTO_SOURCE, SourcePolicy
from volfit.api.state_universe import UnknownNodeError
from volfit.api.stream_focus import Node, StreamFocus
from volfit.data.provider import OptionChainProvider


class SourcesMixin:
    """Per-ticker source resolution, pinning and the per-provider streaming sync."""

    # ------------------------------------------------------------ resolution
    @property
    def source_policy(self) -> SourcePolicy:
        """The process-scoped fetch walls + auto resolutions, created on first
        use (never workspace state: a restore keeps the pins, not the picks).
        ``__dict__.setdefault`` keeps the creation atomic without the state
        lock — ``source_of`` runs under it in places."""
        pol = self.__dict__.get("_source_policy")
        if pol is None:
            pol = self.__dict__.setdefault("_source_policy", SourcePolicy())
        return pol

    def source_of(self, ticker: str) -> str:
        """The source id ``ticker`` fetches from: its pin when it names a
        registered source, the REMEMBERED resolution of an auto pin (resolved
        on first use, re-ranked only at Fetch time), else the universe's
        default (active) source."""
        sym = ticker.strip().upper()
        pinned = self._ticker_sources.get(sym)
        if pinned == AUTO_SOURCE:
            return self.source_policy.resolved(sym) or self._resolve_auto(sym)
        if pinned is not None and pinned in self._providers:
            return pinned
        return self._active_source

    def _choose_auto(self, sym: str) -> str:
        """Rank now, from the status CACHE only (never a probe — a read must
        not wait on a feed); the universe's default when nothing qualifies."""
        statuses = self.source_statuses(probe=False)
        return self.source_policy.choose(self._providers, statuses, sym, self._active_source)

    def _resolve_auto(self, sym: str) -> str:
        """First resolution of an auto pin (a fresh pin, a restored one):
        pick and remember. Never re-ranks a remembered pick — stability."""
        best = self._choose_auto(sym)
        self.source_policy.remember(sym, best)
        return best

    def refresh_auto_source(self, ticker: str) -> bool:
        """Fetch-time re-resolution of an auto pin: re-rank and, when the
        fastest source moved, forget the ticker's chain caches exactly like a
        re-pin (``_drop_ticker_chain_caches``: its data version bumps, its
        nodes read stale, the pull that follows uses the new source). Returns
        whether the resolution CHANGED. A no-op for every other pin — and never
        called from a tick or a read, so a ticker cannot hop between feeds
        between two Fetches."""
        sym = ticker.strip().upper()
        if self._ticker_sources.get(sym) != AUTO_SOURCE:
            return False
        best = self._choose_auto(sym)
        with self._lock:
            before = self.source_policy.resolved(sym)
            self.source_policy.remember(sym, best)
            if before is None or before == best:
                return False
            self._drop_ticker_chain_caches(sym)
        return True

    def resolved_sources(self) -> dict[str, str]:
        """ticker -> the source it fetches from NOW, every active ticker (the
        auto pins' resolutions made visible: ``UniverseResponse.resolvedSources``)."""
        return {t: self.source_of(t) for t in self.active_tickers()}

    def provider_for(self, ticker: str) -> OptionChainProvider:
        """The provider that serves ``ticker`` (see ``source_of``)."""
        return self._providers[self.source_of(ticker)]

    def ticker_sources(self) -> dict[str, str]:
        """The explicit pins (ticker -> source id or ``AUTO_SOURCE``),
        registered sources only."""
        with self._lock:
            return {
                t: s for t, s in self._ticker_sources.items()
                if s in self._providers or s == AUTO_SOURCE
            }

    def tickers_of(self, source_id: str) -> list[str]:
        """The active tickers ``source_id`` serves now — pinned to it, or
        following it as the default."""
        return [t for t in self.active_tickers() if self.source_of(t) == source_id]

    # --------------------------------------------------------------- pinning
    def set_ticker_source(self, ticker: str, source_id: str | None) -> str:
        """Pin ``ticker`` to a registered source (None = follow the universe
        source). A change drops the ticker's chain-derived caches — it refetches
        on the new feed, a custom expiry pick is re-applied lazily, saved priors
        and the lit map are kept — and bumps its data version so its nodes read
        STALE until the next Fetch / Calibrate. Returns the effective source —
        for ``AUTO_SOURCE`` the source it resolved to right now."""
        sym = ticker.strip().upper()
        self._require_active(sym)
        if source_id is not None and source_id != AUTO_SOURCE and source_id not in self._providers:
            raise UnknownNodeError(f"unknown data source {source_id!r}")
        with self._lock:
            before = self.source_of(sym)
            if source_id is None:
                self._ticker_sources.pop(sym, None)
            else:
                self._ticker_sources[sym] = source_id
            if source_id != AUTO_SOURCE:
                self.source_policy.forget(sym)  # an explicit pin / unpin ends the auto pick
            after = self.source_of(sym)  # an auto pin resolves (and is remembered) here
            if after != before:
                self._drop_ticker_chain_caches(sym)
        return after

    def _drop_ticker_chain_caches(self, sym: str) -> None:
        """Forget ONE ticker's chain-derived state (call under the lock): the
        per-ticker counterpart of ``_clear_chain_caches``. A custom expiry pick
        is stashed for the lazy re-resolution on the new feed; the data version
        bumps (every node of the ticker goes stale)."""
        if self._selection_mode.get(sym) == "custom" and sym in self._selected:
            self._pending_selections[sym] = list(self._selected[sym])
        for name in self._CHAIN_CACHE_ATTRS:
            cache = getattr(self, name)
            gone = [k for k in cache if k == sym or (isinstance(k, tuple) and k and k[0] == sym)]
            for key in gone:
                cache.pop(key, None)
        for name in ("_joint_carry", "_available", "_selected", "_selection_mode", "_ticker_errors"):
            getattr(self, name).pop(sym, None)
        self._data_version[sym] = self._data_version.get(sym, 0) + 1

    # ------------------------------------------------------------- streaming
    def sync_streaming(self) -> None:
        """Start/stop/resubscribe each provider's real-time stream to match
        ``autoStream``, the per-ticker source map AND the current universe.
        Idempotent and cheap (a no-op once in the right state, thanks to the
        provider's contract-listing cache), so the scheduler can call it every
        tick. A provider streams iff it exposes ``start_streaming`` (Massive /
        Bloomberg), ``autoStream`` is on — the one switch that opens a book —
        and it serves at least one active ticker (pinned to it, or following it
        as the default); every other streaming provider is stopped so it does
        not leak a background socket. When a provider's desired contract set
        changes (a ticker added / removed / re-pinned or its expiry selection
        edited) the stream is restarted or edited in place on the new set."""
        with self._lock:
            auto = self._options.autoStream
            providers = dict(self._providers)
        focus = self.stream_focus()
        for sid, prov in providers.items():
            if not hasattr(prov, "start_streaming"):
                continue
            streaming = prov.is_streaming()
            mine = self.tickers_of(sid) if auto else []
            if not mine:
                if streaming:
                    prov.stop_streaming()  # nothing of the universe wants this book
                continue
            desired = self._desired_stream_contracts(prov, mine)
            if not desired:
                continue  # nothing fittable yet; leave any warm stream as-is
            # The focus (the nodes on screen) is handed over BEFORE the plan so
            # a fresh start honours it; a provider answers whether its focus
            # changed — that, and only that, makes an unchanged universe re-plan.
            set_focus = getattr(prov, "set_stream_focus", None)
            refocused = bool(set_focus({n for n in focus if n[0] in mine})) if set_focus is not None else False
            if not streaming:
                prov.start_streaming(desired)
                continue
            # Resubscribe only if the provider can report its current
            # subscription (else we can't diff and must not thrash-restart).
            # A provider that can edit its live subscription in place
            # (``update_streaming`` — Bloomberg, Massive) gets the incremental
            # path: only the new/gone contracts move, the rest keep ticking with
            # no warming gap; otherwise the stream is restarted on the new set.
            # A focus change alone never restarts a stream: it re-plans in place.
            probe = getattr(prov, "streaming_contracts", None)
            if probe is None:
                continue
            updater = getattr(prov, "update_streaming", None)
            if set(desired) != set(probe()):
                (updater or prov.start_streaming)(desired)  # universe changed
            elif refocused and updater is not None:
                updater(desired)  # same universe, new focus: re-allocate the live set

    def _desired_stream_contracts(self, prov, tickers: list[str]) -> list[str]:
        """The option tickers ``prov`` should stream for ``tickers`` (cheap once
        the provider's contract listing is cached). A bad ticker never blocks
        the rest."""
        contracts: list[str] = []
        for ticker in tickers:
            try:
                contracts += prov.option_tickers(ticker, self.selected_expiries(ticker))
            except Exception:  # noqa: BLE001 — a bad ticker never blocks streaming
                continue
        return contracts

    def is_streaming(self, ticker: str | None = None) -> bool:
        """With a ticker: its provider SERVES it from a live book — a provider
        that answers per ticker (``is_streaming_ticker``: Massive since
        2026-09-24 — socket up, the ticker's contracts acknowledged, a quote
        booked) is asked that way, so an unserved ticker stays on the request
        path (Auto-update keeps working, the SSE says not streaming); else the
        provider-level "a book is open". Without one: any active ticker
        streams (the status-bar / scheduler summary)."""
        if ticker is None:
            return any(self.is_streaming(t) for t in self.active_tickers())
        prov = self.provider_for(ticker)
        per_ticker = getattr(prov, "is_streaming_ticker", None)
        if per_ticker is not None:
            return bool(per_ticker(ticker))
        probe = getattr(prov, "is_streaming", None)
        return bool(probe is not None and probe())

    def refresh_provider_contracts(self) -> list[str]:
        """The exchange-day roll: every provider that keeps a contracts listing
        (``refresh_contracts`` — Massive, Bloomberg) drops it so the ladder and
        the stream plan re-derive on the new day; the next ``sync_streaming``
        re-plans (expired rungs unsubscribed, the new one subscribed). Returns
        the source ids refreshed; a failing provider never blocks the rest."""
        with self._lock:
            providers = dict(self._providers)
        done: list[str] = []
        for sid, prov in providers.items():
            refresh = getattr(prov, "refresh_contracts", None)
            if refresh is None:
                continue
            try:
                refresh()
                done.append(sid)
            except Exception:  # noqa: BLE001 — a bad provider never blocks the roll
                continue
        return done

    def refresh_stream_rest(self, tickers: list[str]) -> None:
        """The streaming branch's REST memory: for each streaming ticker whose
        provider merges a REST snapshot behind its live book
        (``refresh_stream_rest`` — Massive), ask for a refresh; the provider
        throttles it to one windowed snapshot per ticker per minute."""
        for ticker in tickers:
            prov = self.provider_for(ticker)
            refresh = getattr(prov, "refresh_stream_rest", None)
            if refresh is None:
                continue
            try:
                refresh(ticker, self.selected_expiries(ticker))
            except Exception:  # noqa: BLE001 — the memory keeps its last snapshot
                continue

    def stream_tier(self, ticker: str, expiry: date) -> str:
        """How the node is served: ``"live"`` (its whole planned rung is on
        the socket — the focus, or a universe that fits the budget),
        ``"rest"`` (served with the provider's REST memory behind the belly:
        Massive's per-minute snapshot), ``"none"`` (not streaming). A
        provider without a tier reading (Bloomberg, the synthetic fakes) is
        live whenever it streams."""
        if not self.is_streaming(ticker):
            return "none"
        tier = getattr(self.provider_for(ticker), "stream_tier", None)
        return str(tier(ticker, expiry)) if tier is not None else "live"

    def stream_rest_seconds(self, ticker: str) -> float | None:
        """The REST cadence behind the ticker's live book (None when the
        provider has none) — the per-node SSE says it in its badge."""
        value = getattr(self.provider_for(ticker), "rest_seconds", None)
        return float(value) if value is not None else None

    # ---------------------------------------------------------------- focus
    @property
    def _focus_registry(self) -> StreamFocus:
        """Process-scoped like ``source_policy`` (never workspace state);
        created atomically on first use so ``AppState.__init__`` is untouched."""
        reg = self.__dict__.get("_stream_focus_registry")
        if reg is None:
            reg = self.__dict__.setdefault("_stream_focus_registry", StreamFocus())
        return reg

    def stream_focus(self) -> set[Node]:
        """The ``(TICKER, expiry ISO)`` nodes with an open tick-stream SSE."""
        return self._focus_registry.nodes()

    def focus_node(self, ticker: str, expiry_iso: str) -> Node:
        """The registry key of a node: the upper-cased ticker and the expiry
        resolved against its selection when it resolves (so ``2026-10-16``
        matches the plan's date however the URL spelt it), else as given."""
        sym = ticker.strip().upper()
        try:
            iso = self.resolve_expiry(sym, expiry_iso).isoformat()
        except Exception:  # noqa: BLE001 — an unknown node still gets a key (the SSE errors out)
            iso = expiry_iso.strip()
        return (sym, iso)

    def focus_open(self, ticker: str, expiry_iso: str) -> Node:
        """A tick stream opened on the node (reference-counted). Returns the
        key ``focus_close`` must be given back."""
        node = self.focus_node(ticker, expiry_iso)
        self._focus_registry.open(node)
        return node

    def focus_close(self, node: Node) -> None:
        self._focus_registry.close(node)

    def streaming_tickers(self) -> list[str]:
        """The active tickers served from a live book right now."""
        return [t for t in self.active_tickers() if self.is_streaming(t)]

    def request_tickers(self) -> list[str]:
        """The active tickers on the request path (no live book) — the ones
        the Auto-update timer serves."""
        return [t for t in self.active_tickers() if not self.is_streaming(t)]
