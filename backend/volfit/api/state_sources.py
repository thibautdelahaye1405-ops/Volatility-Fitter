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
``request_tickers``).

The pin value ``AUTO_SOURCE`` ("auto", volfit.api.source_policy) resolves to
the fastest green source that can serve the ticker; the resolution is
remembered and re-ranked only at Fetch time (``refresh_auto_source``).

Mixed into ``AppState`` (which owns ``_providers``, ``_active_source``,
``_ticker_sources`` [workspace-scoped], ``_active_tickers``, the per-ticker
caches and ``_lock``; ``_require_active`` comes from the universe mixin).
"""

from __future__ import annotations

from volfit.api.source_policy import AUTO_SOURCE, SourcePolicy
from volfit.api.state_universe import UnknownNodeError
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
            if not streaming:
                prov.start_streaming(desired)
            else:
                # Resubscribe only if the provider can report its current
                # subscription (else we can't diff and must not thrash-restart).
                # A provider that can edit its live subscription in place
                # (``update_streaming`` — Bloomberg) gets the incremental path:
                # only the new/gone contracts move, the rest keep ticking with no
                # warming gap; otherwise the stream is restarted on the new set.
                probe = getattr(prov, "streaming_contracts", None)
                if probe is not None and set(desired) != set(probe()):
                    updater = getattr(prov, "update_streaming", None)
                    (updater or prov.start_streaming)(desired)  # universe changed

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
        """With a ticker: its provider has a live real-time book. Without one:
        any active ticker streams (the status-bar / scheduler summary)."""
        if ticker is None:
            return any(self.is_streaming(t) for t in self.active_tickers())
        probe = getattr(self.provider_for(ticker), "is_streaming", None)
        return bool(probe is not None and probe())

    def streaming_tickers(self) -> list[str]:
        """The active tickers served from a live book right now."""
        return [t for t in self.active_tickers() if self.is_streaming(t)]

    def request_tickers(self) -> list[str]:
        """The active tickers on the request path (no live book) — the ones
        the Auto-update timer serves."""
        return [t for t in self.active_tickers() if not self.is_streaming(t)]
