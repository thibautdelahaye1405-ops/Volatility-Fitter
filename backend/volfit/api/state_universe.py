"""Universe + per-ticker expiry selection, mixed into AppState.

Split out of volfit.api.state to keep both files under the size policy. The
methods here manage the *active universe* (which tickers the API serves) and
each ticker's *expiry selection* (which of its available expiries are fetched
and fitted). They operate on AppState's lock-guarded caches via ``self``, so
this is a mixin, not a standalone object; AppState owns the attributes.

``UnknownNodeError`` lives here (the universe is what defines a known node) and
is re-exported from volfit.api.state for the many callers that import it there.
"""

from __future__ import annotations

from datetime import date

from volfit.data.expiry_select import default_selection
from volfit.data.file import SOURCE_ID as FILE_SOURCE_ID
from volfit.data.forwards import implied_forwards
from volfit.data.symbols import portable_ticker
from volfit.data.types import ChainSnapshot


class UnknownNodeError(KeyError):
    """Requested (ticker, expiry) does not exist in the active universe."""


def _pins_for(wanted: list[str], sources: dict[str, str] | None, providers: dict) -> dict[str, str]:
    """The saved per-ticker source pins worth keeping: tickers of the universe
    being installed, sources still registered (volfit.api.state_sources)."""
    keep = set(wanted)
    return {
        portable_ticker(t.strip().upper()): s
        for t, s in (sources or {}).items()
        if portable_ticker(t.strip().upper()) in keep and s in providers
    }


class UniverseMixin:
    """Active-ticker set and per-ticker expiry selection (see module docstring)."""

    # ------------------------------------------------------------ universe
    def active_tickers(self) -> list[str]:
        """The curated universe the API serves (a copy)."""
        with self._lock:
            return list(self._active_tickers)

    def known_ticker(self, ticker: str) -> bool:
        """Whether a ticker is valid for read endpoints: in the ACTIVE universe
        (so a user-added symbol like NVDA counts) or the provider's watchlist.
        Read-path guards must use this, not ``provider.list_tickers()`` alone,
        which would 404 a ticker the user added at runtime."""
        with self._lock:
            if ticker in self._active_tickers:
                return True
        return ticker in self.provider.list_tickers()

    def add_ticker(self, symbol: str, source: str | None = None) -> str:
        """Add a ticker to the universe, validating it has fittable expiries.

        Fetches the chain outside the lock (network); raises UnknownNodeError
        if the symbol cannot be fetched or carries no parity-implyable expiry.
        Idempotent. Pre-caches the snapshot/forwards and resets the graph
        universe so it rebuilds over the new node set. ``source`` resolves and
        fetches the name on THAT registered source and pins it there (the
        multi-source engine, volfit.api.state_sources); None = the default.
        """
        sym = portable_ticker(symbol.strip().upper())  # portable across sources
        if not sym:
            raise UnknownNodeError("empty ticker symbol")
        sym = self._resolve_file_alias(sym, source)
        with self._lock:
            if sym in self._active_tickers:
                return sym
        sid = source or self._active_source
        if sid not in self._providers:
            raise UnknownNodeError(f"unknown data source {sid!r}")
        prov = self._providers[sid]
        try:
            available = prov.available_expiries(sym)
            chosen = default_selection(available, self.reference_date)
            snap = prov.fetch_chain(sym, chosen)
        except Exception as exc:  # bad symbol, no data, network — all 404 here
            raise UnknownNodeError(f"could not add {sym!r}: {exc}") from None
        fwds = implied_forwards(snap, self.reference_date)
        if not fwds:
            raise UnknownNodeError(f"{sym!r} has no usable option expiries")
        with self._lock:
            if sym not in self._active_tickers:
                self._available[sym] = available
                self._selected[sym] = chosen
                self._selection_mode[sym] = "auto"
                self._snapshots[sym] = snap
                self._forwards[sym] = fwds
                self._active_tickers.append(sym)
                if source is not None:
                    self._ticker_sources[sym] = source
                self._universe = None
        return sym

    def _resolve_file_alias(self, sym: str, source: str | None = None) -> str:
        """Index-root discovery for snapshot files (volfit.data.roots): under
        the FILE source a typed parent / sibling root that is not itself a
        bundle ticker (``SPX`` for a file keyed ``SPXW``) resolves to the
        bundle ticker it aliases, so the add lands on the node the file
        carries. Every other source returns the symbol unchanged."""
        sid = source or self.active_source
        if sid != FILE_SOURCE_ID:
            return sym
        resolve = getattr(self._providers[sid], "resolve_alias", None)
        if resolve is None:
            return sym
        return resolve(sym) or sym

    def _drop_ticker_caches(self, sym: str) -> None:
        """Forget every cache entry of a ticker (call under the lock)."""
        self._snapshots.pop(sym, None)
        self._forwards.pop(sym, None)
        self._joint_carry.pop(sym, None)
        self._available.pop(sym, None)
        self._selected.pop(sym, None)
        self._selection_mode.pop(sym, None)
        self._fits = {k: v for k, v in self._fits.items() if k[0] != sym}
        self._sessions = {k: v for k, v in self._sessions.items() if k[0] != sym}
        self._priors = {k: v for k, v in self._priors.items() if k[0] != sym}

    def remove_ticker(self, symbol: str) -> None:
        """Remove a ticker from the universe (never the last one)."""
        sym = portable_ticker(symbol.strip().upper())
        with self._lock:
            if sym not in self._active_tickers:
                raise UnknownNodeError(f"unknown ticker {sym!r}")
            if len(self._active_tickers) <= 1:
                raise ValueError("cannot remove the last ticker in the universe")
            self._active_tickers.remove(sym)
            self._drop_ticker_caches(sym)
            self._ticker_sources.pop(sym, None)  # a pin dies with its ticker
            self._universe = None

    def set_active_tickers(
        self, symbols: list[str], sources: dict[str, str] | None = None
    ) -> list[str]:
        """Replace the universe (loading a saved one); unfetchable symbols are
        skipped. Each ticker starts on the default selection (callers re-apply
        any saved custom picks). ``sources`` = the saved per-ticker pins, set
        FIRST so each ticker resolves on its own feed. Raises ValueError if
        nothing usable survives."""
        wanted = list(
            dict.fromkeys(portable_ticker(s.strip().upper()) for s in symbols if s.strip())
        )
        with self._lock:
            self._ticker_sources = _pins_for(wanted, sources, self._providers)
        validated: list[str] = []
        fetched: dict[str, tuple] = {}
        for sym in wanted:
            try:
                with self._lock:
                    have = sym in self._snapshots and sym in self._available
                if have:
                    validated.append(sym)
                    continue
                prov = self.provider_for(sym)  # its pin, else the default source
                available = prov.available_expiries(sym)
                chosen = default_selection(available, self.reference_date)
                snap = prov.fetch_chain(sym, chosen)
                fwds = implied_forwards(snap, self.reference_date)
                if not fwds:
                    continue
                fetched[sym] = (available, chosen, snap, fwds)
                validated.append(sym)
            except Exception:
                continue  # skip a ticker a saved universe can no longer fetch
        if not validated:
            raise ValueError("no usable tickers in the universe")
        with self._lock:
            for sym, (available, chosen, snap, fwds) in fetched.items():
                self._available[sym] = available
                self._selected[sym] = chosen
                self._selection_mode[sym] = "auto"
                self._snapshots[sym] = snap
                self._forwards[sym] = fwds
            self._active_tickers = validated
            self._universe = None
        return validated

    def restore_universe(
        self,
        tickers: list[str],
        selections: dict[str, list[str] | None] | None = None,
        sources: dict[str, str] | None = None,
    ) -> None:
        """Set the active ticker list (+ custom expiry picks) WITHOUT fetching.

        Used at startup to restore the last saved universe as cheaply as the
        default watchlist: the tickers resolve their ladders lazily on first use,
        and any custom picks are stashed in ``_pending_selections`` for
        ``_ensure_selection`` to apply once each ladder loads. Tickers a provider
        can no longer serve simply resolve to no data (handled downstream), exactly
        as an unreachable default-watchlist ticker would."""
        wanted = list(
            dict.fromkeys(portable_ticker(t.strip().upper()) for t in tickers if t.strip())
        )
        if not wanted:
            return
        with self._lock:
            self._active_tickers = wanted
            self._ticker_sources = _pins_for(wanted, sources, self._providers)
            self._pending_selections = {}
            for ticker, picks in (selections or {}).items():
                sym = portable_ticker(ticker.strip().upper())
                if not picks:
                    continue  # auto: the default rule applies lazily
                try:
                    self._pending_selections[sym] = [date.fromisoformat(s) for s in picks]
                except (ValueError, TypeError):
                    pass  # malformed pick -> fall back to auto for that ticker
            self._universe = None

    def _require_active(self, ticker: str) -> None:
        with self._lock:
            if ticker not in self._active_tickers:
                raise UnknownNodeError(f"unknown ticker {ticker!r}")

    # ----------------------------------------------------- expiry selection
    def _ensure_selection(self, ticker: str) -> None:
        """Populate a ticker's available/selected expiries on first use — the
        initial watchlist tickers are not added through add_ticker, so they pick
        up their default selection lazily here.

        A *transient* provider miss (Yahoo throttling ``Ticker.options`` to an
        empty tuple, a momentarily unreachable feed, or a raised error) must NOT
        be frozen: caching an empty ladder here would leave that ticker showing
        zero expiries for the whole process even after the feed recovers. So we
        only cache a non-empty resolution and otherwise leave the ticker
        unresolved, to be retried on the next access.
        """
        with self._lock:
            if self._available.get(ticker):  # already resolved with a real ladder
                return
        try:
            available = self.provider_for(ticker).available_expiries(ticker)  # network, no lock
            reason = "" if available else f"{self.source_of(ticker)} lists no expiries for {ticker!r}"
        except Exception as exc:  # a provider error is a transient miss -> retry
            available = []
            text = str(exc).strip()
            reason = text.splitlines()[-1][:120] if text else "expiry listing failed"
        if not available:
            # Leave unresolved so a later call re-probes the provider, but
            # REMEMBER why (the universe payload names it — a venue that does
            # not list the symbol, a throttled feed — instead of a silent
            # empty node the user cannot tell from a fetch that never ran).
            with self._lock:
                self._ticker_errors[ticker] = reason
            return
        with self._lock:
            self._ticker_errors.pop(ticker, None)
        chosen = default_selection(available, self.reference_date)
        with self._lock:
            if self._available.get(ticker):  # another thread resolved it first
                return
            self._available[ticker] = available
            # A restored universe's custom picks (intersected with the live ladder)
            # take precedence over the default rule the first time it resolves.
            pending = self._pending_selections.pop(ticker, None)
            custom = [d for d in pending if d in available] if pending else []
            if custom:
                self._selected[ticker] = custom
                self._selection_mode[ticker] = "custom"
            else:
                self._selected[ticker] = chosen
                self._selection_mode[ticker] = "auto"

    def ticker_error(self, ticker: str) -> str | None:
        """Why ``ticker`` has no ladder / no chain on the active source (the
        provider's own reason when it keeps one, else the last listing miss);
        None when it resolves fine."""
        own = getattr(self.provider_for(ticker), "ticker_error", None)
        reason = own(ticker) if own is not None else None
        if reason:
            return reason
        with self._lock:
            return self._ticker_errors.get(ticker)

    def available_expiries(self, ticker: str) -> list[date]:
        """Every expiry the provider lists for the ticker (the picker's list);
        empty when the feed hasn't resolved a ladder yet (transient miss)."""
        self._require_active(ticker)
        self._ensure_selection(ticker)
        with self._lock:
            return list(self._available.get(ticker, []))

    def selected_expiries(self, ticker: str) -> list[date]:
        """The expiries actually fetched and fitted for the ticker (empty until
        the ladder resolves)."""
        self._require_active(ticker)
        self._ensure_selection(ticker)
        with self._lock:
            return list(self._selected.get(ticker, []))

    def selection_mode(self, ticker: str) -> str:
        """"auto" (default rule) or "custom" (user picks)."""
        self._require_active(ticker)
        self._ensure_selection(ticker)
        with self._lock:
            return self._selection_mode.get(ticker, "auto")

    def _invalidate_ticker(self, ticker: str) -> None:
        """Drop the cached snapshot/forwards of a ticker (under the lock) so the
        next access refetches its selected expiries; rebuild the graph."""
        self._snapshots.pop(ticker, None)
        self._forwards.pop(ticker, None)
        self._joint_carry.pop(ticker, None)
        self._universe = None

    def _reconcile_chain_selection(self, ticker: str, new_expiries: list[date]) -> None:
        """Reconcile the cached chain with a changed expiry selection (ROADMAP perf
        #3B). Assumes the lock is held.

        A per-ticker ``ChainSnapshot`` is one atomic observation (a single
        spot/instant across its expiries). So: if the cached chain already covers
        the new selection (a deselect, or re-selecting a subset), PRUNE the snapshot
        + forwards to it IN PLACE — no re-fetch, and every surviving node keeps its
        warm fit (the per-node fit keys are unchanged). Only a genuinely NEW expiry
        (absent from the cached chain) forces a full atomic re-fetch, so the chain
        never mixes instants. The LV/term views still re-derive for the new set,
        since the pruned forwards change their (per-iso) cache keys."""
        self._universe = None  # ladder changed -> rebuild the graph topology
        snap = self._snapshots.get(ticker)
        want = set(new_expiries)
        if snap is None or not want.issubset(set(snap.expiries())):
            self._snapshots.pop(ticker, None)  # full atomic re-fetch next access
            self._forwards.pop(ticker, None)
            self._joint_carry.pop(ticker, None)
            return
        kept = [q for q in snap.quotes if q.expiry in want]
        # Carry ALL chain-level metadata through the prune: dropping zero_carry
        # would un-pin an IV-synthesized chain's parity forward, dropping
        # tick_size would disable the tick-noise screen, and the settlement
        # map is filtered to the surviving expiries.
        self._snapshots[ticker] = ChainSnapshot(
            ticker=snap.ticker, spot=snap.spot, timestamp=snap.timestamp,
            quotes=kept, exercise_style=snap.exercise_style,
            zero_carry=snap.zero_carry, tick_size=snap.tick_size,
            settlement=(
                {e: s for e, s in snap.settlement.items() if e in want}
                if snap.settlement is not None
                else None
            ),
        )
        fwds = self._forwards.get(ticker)
        if fwds is not None:
            self._forwards[ticker] = {e: f for e, f in fwds.items() if e in want}
        joint = self._joint_carry.get(ticker)
        if joint is not None:
            self._joint_carry[ticker] = {e: j for e, j in joint.items() if e in want}

    def set_expiries(self, ticker: str, expiries: list[date]) -> list[date]:
        """Replace a ticker's selected expiries (custom mode). Dates outside the
        available list are dropped; an empty result is rejected."""
        self._require_active(ticker)
        self._ensure_selection(ticker)
        with self._lock:
            allowed = set(self._available[ticker])
            chosen = sorted({e for e in expiries if e in allowed})
            if not chosen:
                raise ValueError("selection must keep at least one expiry")
            self._selected[ticker] = chosen
            self._selection_mode[ticker] = "custom"
            self._reconcile_chain_selection(ticker, chosen)
            return list(chosen)

    def reset_expiries(self, ticker: str) -> list[date]:
        """Re-apply the default selection rule to a ticker (auto mode)."""
        self._require_active(ticker)
        self._ensure_selection(ticker)
        with self._lock:
            chosen = default_selection(self._available[ticker], self.reference_date)
            self._selected[ticker] = chosen
            self._selection_mode[ticker] = "auto"
            self._reconcile_chain_selection(ticker, chosen)
            return list(chosen)
