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
from volfit.data.forwards import implied_forwards


class UnknownNodeError(KeyError):
    """Requested (ticker, expiry) does not exist in the active universe."""


class UniverseMixin:
    """Active-ticker set and per-ticker expiry selection (see module docstring)."""

    # ------------------------------------------------------------ universe
    def active_tickers(self) -> list[str]:
        """The curated universe the API serves (a copy)."""
        with self._lock:
            return list(self._active_tickers)

    def add_ticker(self, symbol: str) -> str:
        """Add a ticker to the universe, validating it has fittable expiries.

        Fetches the chain outside the lock (network); raises UnknownNodeError
        if the symbol cannot be fetched or carries no parity-implyable expiry.
        Idempotent. Pre-caches the snapshot/forwards and resets the graph
        universe so it rebuilds over the new node set.
        """
        sym = symbol.strip().upper()
        if not sym:
            raise UnknownNodeError("empty ticker symbol")
        with self._lock:
            if sym in self._active_tickers:
                return sym
        try:
            available = self.provider.available_expiries(sym)
            chosen = default_selection(available, self.reference_date)
            snap = self.provider.fetch_chain(sym, chosen)
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
                self._universe = None
        return sym

    def _drop_ticker_caches(self, sym: str) -> None:
        """Forget every cache entry of a ticker (call under the lock)."""
        self._snapshots.pop(sym, None)
        self._forwards.pop(sym, None)
        self._available.pop(sym, None)
        self._selected.pop(sym, None)
        self._selection_mode.pop(sym, None)
        self._fits = {k: v for k, v in self._fits.items() if k[0] != sym}
        self._sessions = {k: v for k, v in self._sessions.items() if k[0] != sym}
        self._priors = {k: v for k, v in self._priors.items() if k[0] != sym}

    def remove_ticker(self, symbol: str) -> None:
        """Remove a ticker from the universe (never the last one)."""
        sym = symbol.strip().upper()
        with self._lock:
            if sym not in self._active_tickers:
                raise UnknownNodeError(f"unknown ticker {sym!r}")
            if len(self._active_tickers) <= 1:
                raise ValueError("cannot remove the last ticker in the universe")
            self._active_tickers.remove(sym)
            self._drop_ticker_caches(sym)
            self._universe = None

    def set_active_tickers(self, symbols: list[str]) -> list[str]:
        """Replace the universe (loading a saved one); unfetchable symbols are
        skipped. Each ticker starts on the default selection (callers re-apply
        any saved custom picks). Raises ValueError if nothing usable survives."""
        wanted = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        validated: list[str] = []
        fetched: dict[str, tuple] = {}
        for sym in wanted:
            try:
                with self._lock:
                    have = sym in self._snapshots and sym in self._available
                if have:
                    validated.append(sym)
                    continue
                available = self.provider.available_expiries(sym)
                chosen = default_selection(available, self.reference_date)
                snap = self.provider.fetch_chain(sym, chosen)
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
            available = self.provider.available_expiries(ticker)  # network, no lock
        except Exception:
            available = []  # treat a provider error as a transient miss -> retry
        if not available:
            return  # leave unresolved so a later call re-probes the provider
        chosen = default_selection(available, self.reference_date)
        with self._lock:
            if self._available.get(ticker):  # another thread resolved it first
                return
            self._available[ticker] = available
            self._selected[ticker] = chosen
            self._selection_mode[ticker] = "auto"

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
        self._universe = None

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
            self._invalidate_ticker(ticker)
            return list(chosen)

    def reset_expiries(self, ticker: str) -> list[date]:
        """Re-apply the default selection rule to a ticker (auto mode)."""
        self._require_active(ticker)
        self._ensure_selection(ticker)
        with self._lock:
            chosen = default_selection(self._available[ticker], self.reference_date)
            self._selected[ticker] = chosen
            self._selection_mode[ticker] = "auto"
            self._invalidate_ticker(ticker)
            return list(chosen)
