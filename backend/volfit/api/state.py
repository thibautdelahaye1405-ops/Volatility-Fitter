"""Per-application state and caches behind the volfit API (ROADMAP Phase 5).

Everything heavy is computed at most once: chain snapshots, parity-implied
forwards, per-(ticker, expiry, fit-mode, session-version) slice calibrations,
saved priors (display curve + fitted LQD params, so prior densities can be
rebuilt) and the lazily-built graph smile universe. Chains are fetched once
per process (live providers included — a snapshot is one observation) and
quote edits bump their session's version (a new cache key), so caches never
need invalidation. A single lock guards the
mutable dicts because WebSocket surface fits run on worker threads; the
universe build happens outside that lock (it re-enters the fit cache) and is
idempotent, so a rare double build is harmless.
"""

from __future__ import annotations

import math
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime

from volfit.api.fit_models import DisplayFit
from volfit.api.quotes import PreparedQuotes
from volfit.api.schemas import (
    EventSpec,
    FitSettings,
    ForwardPolicy,
    MarketSettings,
    OptionsSettings,
    SmilePoint,
)
from volfit.api.session import EditSession
from volfit.api.varswap_session import VarSwapSession
from volfit.data.dividends import (
    Dividend,
    DividendModel,
    forward_consistent_cash_schedule,
    theoretical_forward,
)
from volfit.api.state_universe import UniverseMixin, UnknownNodeError  # noqa: F401 (re-export)
from volfit.data.expiry_select import default_selection
from volfit.data.forwards import ImpliedForward, ResolvedForward, implied_forwards
from volfit.data.provider import AsOf, OptionChainProvider, SyntheticProvider
from volfit.data.store import VolStore
from volfit.data.types import ChainSnapshot
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import CalibrationResult

#: Year-fraction day count used across the API (ACT/365 fixed).
DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class FitRecord:
    """One cached slice calibration plus the inputs it was fitted to.

    ``result`` is always the LQD fit (the analytic backbone). ``display`` is
    the chosen non-LQD overlay fit when the hyperparameter panel selects
    SVI/sigmoid (volfit.api.fit_models); None means the LQD fit is displayed.
    """

    prepared: PreparedQuotes
    result: CalibrationResult
    display: DisplayFit | None = None


@dataclass(frozen=True)
class PriorRecord:
    """A saved prior: the display curve the Smile Viewer charts plus the
    fitted LQD parameters (and expiry year fraction) that produced it, so
    the prior's density/quantile function can be rebuilt via build_slice."""

    curve: list[SmilePoint]
    params: LQDParams
    t: float


@dataclass(frozen=True)
class AsOfSelection:
    """Which point in time the app serves chains as-of (global).

    - ``"live"``       latest from the active provider (default);
    - ``"prev_close"`` the provider's prior-session close;
    - ``"eod"``        the provider's close for the trading day ``on``;
    - ``"captured"``   replay the stored snapshot nearest at-or-before ``ts``
                       (any provider, from the VolStore capture history).
    """

    mode: str = "live"
    on: date | None = None  # eod
    ts: datetime | None = None  # captured


class AppState(UniverseMixin):
    """Provider handle plus all caches; one instance per FastAPI app.

    Universe management and per-ticker expiry selection are provided by
    UniverseMixin (volfit.api.state_universe); this class owns the caches the
    mixin operates on, plus market data, fit settings, forwards and sessions.
    """

    def __init__(
        self,
        reference_date: date,
        provider: OptionChainProvider | None = None,
        store_path: str | os.PathLike | None = None,
        providers: dict[str, OptionChainProvider] | None = None,
        active_source: str | None = None,
    ) -> None:
        self.reference_date = reference_date
        #: Available market-data sources keyed by id ("yahoo"/"bloomberg"/
        #: "massive"/"synthetic"). `self.provider` is the *active* one; the Data
        #: Source selector switches `_active_source` at runtime.
        if providers:
            self._providers = dict(providers)
            self._active_source = active_source or next(iter(self._providers))
        else:
            one = provider or SyntheticProvider(reference_date=reference_date)
            self._providers = {_source_id_of(one): one}
            self._active_source = next(iter(self._providers))
        #: Cached (monotonic_ts, (level, detail)) feed status per source.
        self._status_cache: dict[str, tuple[float, tuple[str, str]]] = {}
        #: Global as-of selection (live by default); historical/captured chains
        #: flow through snapshot() exactly like live ones.
        self._asof = AsOfSelection()
        #: SQLite path for fit-history persistence (volfit.api.history);
        #: None (the default) keeps the API side-effect free.
        self.store_path = store_path
        #: The curated universe (mutable): starts as the provider's watchlist,
        #: the user adds/removes tickers via the universe-management API.
        self._active_tickers: list[str] = list(self.provider.list_tickers())
        #: Per-ticker expiry selection: all the provider lists (``_available``),
        #: the subset actually fetched/fitted (``_selected``), and whether that
        #: subset follows the default rule ("auto") or the user's picks ("custom").
        self._available: dict[str, list[date]] = {}
        self._selected: dict[str, list[date]] = {}
        self._selection_mode: dict[str, str] = {}
        self._snapshots: dict[str, ChainSnapshot] = {}
        self._forwards: dict[str, dict[date, ImpliedForward]] = {}
        self._fit_settings = FitSettings()
        self._settings_version = 0  # bumped on change; part of fit-cache keys
        #: Global meta / UX settings + engine defaults (the Options workspace).
        self._options = OptionsSettings()
        self._options_version = 0  # bumped only when a fit-affecting field changes
        self._market_settings: dict[str, MarketSettings] = {}
        #: Per-ticker event calendar (shared across workspaces). Events now drive
        #: the event-weighted variance clock used by every fit (volfit.calib.
        #: weighted_time), so a calendar change must refit: the events version is
        #: folded into the fit-cache key.
        self._events: dict[str, list[EventSpec]] = {}
        self._events_version = 0  # bumped on any event-calendar change
        self._forward_policies: dict[tuple[str, str], ForwardPolicy] = {}
        self._forwards_version = 0  # bumped on change; part of fit-cache keys
        self._fits: dict[tuple, FitRecord] = {}
        self._priors: dict[tuple[str, str], PriorRecord] = {}
        self._sessions: dict[tuple[str, str], EditSession] = {}
        #: Per-node variance-swap quote sessions (one var-swap per node, shared
        #: by the Parametric and Local-Vol fits; separate undo/redo history).
        self._varswap_sessions: dict[tuple[str, str], VarSwapSession] = {}
        #: Explicitly darkened (ticker, ISO) nodes; every node is LIT by default.
        #: Lit = an observed source for the graph solver, dark = extrapolated.
        self._dark_nodes: set[tuple[str, str]] = set()
        self._universe = None  # volfit.graph.smile_universe.SmileUniverse
        self._lock = threading.Lock()

    # ------------------------------------------------------------ data sources
    @property
    def provider(self) -> OptionChainProvider:
        """The currently active market-data provider."""
        return self._providers[self._active_source]

    @property
    def active_source(self) -> str:
        """Id of the active data source (e.g. "yahoo", "bloomberg")."""
        return self._active_source

    def source_ids(self) -> list[str]:
        """All configured data-source ids, in registration order."""
        return list(self._providers)

    def source_statuses(self, refresh: bool = False) -> dict[str, tuple[str, str]]:
        """Per-source (level, detail) feed status, cached with a short TTL."""
        from volfit.api.datasource import probe_statuses

        if refresh:
            self._status_cache.clear()
        return probe_statuses(self._providers, self._status_cache)

    def set_active_source(self, source_id: str) -> str:
        """Switch the active source: keep the watchlist + custom expiry picks,
        clear all data caches, and refetch on the new feed (auto selections
        re-resolve lazily; custom picks intersect the new available list)."""
        if source_id not in self._providers:
            raise UnknownNodeError(f"unknown data source {source_id!r}")
        with self._lock:
            if source_id == self._active_source:
                return self._active_source
            custom = {
                t: list(self._selected[t])
                for t, mode in self._selection_mode.items()
                if mode == "custom" and t in self._selected
            }
            self._active_source = source_id
            self._asof = AsOfSelection()  # a new feed starts live
            self._available.clear()
            self._selected.clear()
            self._selection_mode.clear()
            self._clear_chain_caches()
        # Re-apply custom expiry picks against the new source (network, no lock).
        for ticker, dates in custom.items():
            try:
                available = self.provider.available_expiries(ticker)
            except Exception:
                continue  # ticker unavailable on the new source; lazy path 404s
            keep = [d for d in dates if d in set(available)]
            chosen = keep or default_selection(available, self.reference_date)
            with self._lock:
                self._available[ticker] = available
                self._selected[ticker] = chosen
                self._selection_mode[ticker] = "custom" if keep else "auto"
        return self._active_source

    def _clear_chain_caches(self) -> None:
        """Drop per-ticker chain-derived caches (call under the lock). Keeps the
        watchlist + expiry selection; used on source switch and as-of change."""
        self._snapshots.clear()
        self._forwards.clear()
        self._fits.clear()
        self._sessions.clear()
        self._varswap_sessions.clear()
        self._universe = None

    # ------------------------------------------------------------ as-of
    @property
    def as_of(self) -> AsOfSelection:
        """The active global as-of selection."""
        return self._asof

    def set_as_of(self, selection: AsOfSelection) -> AsOfSelection:
        """Set the as-of point; validate against the active provider, then drop
        chain caches so the whole stack re-prices on the new observation."""
        if selection.mode not in ("live", "prev_close", "eod", "captured"):
            raise UnknownNodeError(f"unknown as-of mode {selection.mode!r}")
        if selection.mode in ("prev_close", "eod"):
            if selection.mode not in self.provider.historical_modes():
                raise UnknownNodeError(
                    f"{self._active_source!r} has no {selection.mode!r} history"
                )
            if selection.mode == "eod" and selection.on is None:
                raise UnknownNodeError("eod as-of requires a date")
        if selection.mode == "captured" and selection.ts is None:
            raise UnknownNodeError("captured as-of requires a timestamp")
        with self._lock:
            if selection != self._asof:
                self._asof = selection
                self._clear_chain_caches()
            return self._asof

    def _fetch_asof(self, ticker: str, chosen: list[date]) -> ChainSnapshot:
        """Fetch a chain for the current as-of: live (+capture) / provider EOD /
        captured replay from the store."""
        sel = self._asof
        if sel.mode == "captured":
            snap = self._load_captured(ticker, sel.ts)
            if snap is None:
                raise UnknownNodeError(
                    f"no captured snapshot for {ticker!r} at {sel.ts}"
                )
            return snap
        if sel.mode in ("prev_close", "eod"):
            return self.provider.fetch_chain(
                ticker, chosen, as_of=AsOf(mode=sel.mode, on=sel.on)
            )
        snap = self.provider.fetch_chain(ticker, chosen)  # live
        self._persist_capture(snap)
        return snap

    def _load_captured(self, ticker: str, ts: datetime | None) -> ChainSnapshot | None:
        if self.store_path is None or ts is None:
            return None
        with VolStore(self.store_path) as store:
            return store.snapshot_at(ticker, ts)

    def _persist_capture(self, snap: ChainSnapshot) -> None:
        """Best-effort: save a live chain to the store for later replay, deduped
        to one capture per ~60 s per ticker. Never fails a fetch."""
        if self.store_path is None:
            return
        try:
            with VolStore(self.store_path) as store:
                last = store.last_snapshot_ts(snap.ticker)
                if last is not None and abs((snap.timestamp - last).total_seconds()) < 60:
                    return
                store.save_snapshot(snap)
        except Exception:
            pass

    # ------------------------------------------------------------ market data
    def snapshot(self, ticker: str) -> ChainSnapshot:
        """Fetch-once chain snapshot of the ticker's SELECTED expiries;
        UnknownNodeError for tickers not in the active universe."""
        self._require_active(ticker)
        self._ensure_selection(ticker)
        with self._lock:
            if ticker in self._snapshots:
                return self._snapshots[ticker]
            chosen = list(self._selected[ticker])
        snap = self._fetch_asof(ticker, chosen)  # outside lock (network)
        with self._lock:
            self._snapshots.setdefault(ticker, snap)
            return self._snapshots[ticker]

    def forwards(self, ticker: str) -> dict[date, ImpliedForward]:
        """Parity-implied forwards per expiry, cached per ticker."""
        snapshot = self.snapshot(ticker)
        with self._lock:
            if ticker not in self._forwards:
                # Pass the reference date so American chains are de-biased
                # (parity from de-Americanized mids; see data.forwards).
                self._forwards[ticker] = implied_forwards(snapshot, self.reference_date)
            return self._forwards[ticker]

    def resolve_expiry(self, ticker: str, expiry_iso: str) -> date:
        """Parse and validate an ISO expiry against the ticker's ladder."""
        try:
            expiry = date.fromisoformat(expiry_iso)
        except ValueError:
            raise UnknownNodeError(f"malformed expiry {expiry_iso!r}") from None
        if expiry not in self.forwards(ticker):
            raise UnknownNodeError(f"unknown expiry {expiry_iso!r} for {ticker!r}")
        return expiry

    def year_fraction(self, expiry: date) -> float:
        """t = days to expiry / 365 (matches the provider's expiry ladder)."""
        return (expiry - self.reference_date).days / DAYS_PER_YEAR

    # ---------------------------------------------------------- fit settings
    @property
    def settings_version(self) -> int:
        """Monotone counter folded into fit keys; bumps on settings change."""
        with self._lock:
            return self._settings_version

    def fit_settings(self) -> FitSettings:
        with self._lock:
            return self._fit_settings

    def set_fit_settings(self, settings: FitSettings) -> FitSettings:
        """Apply new hyperparameters; identical settings don't bump the
        version, so a redundant PUT never invalidates warm fit caches."""
        with self._lock:
            if settings != self._fit_settings:
                self._fit_settings = settings
                self._settings_version += 1
            return self._fit_settings

    # ----------------------------------------------------- options (meta) settings
    @property
    def options_version(self) -> int:
        """Monotone counter folded into fit keys; bumps only when a
        fit-affecting Options field (calendarWeight) changes, so toggling a
        pure-UI option (spot mode, auto-calibrate) never busts warm fits."""
        with self._lock:
            return self._options_version

    def options(self) -> OptionsSettings:
        with self._lock:
            return self._options

    def set_options(self, options: OptionsSettings) -> OptionsSettings:
        """Apply new meta settings. Calibration-affecting fields bump the options
        version (``calendarWeight`` and the var-swap penalty knobs ``varSwapEnabled``
        / ``varSwapWeightPct``); the rest are global defaults / display toggles read
        live and need no cache invalidation."""
        with self._lock:
            if options != self._options:
                affects_fit = (
                    options.calendarWeight != self._options.calendarWeight
                    or options.varSwapEnabled != self._options.varSwapEnabled
                    or options.varSwapWeightPct != self._options.varSwapWeightPct
                    or options.eventsEnabled != self._options.eventsEnabled
                    or options.normalizeEvents != self._options.normalizeEvents
                )
                if affects_fit:
                    self._options_version += 1
                self._options = options
            return self._options

    # ------------------------------------ market settings and forward policy
    @property
    def forwards_version(self) -> int:
        """Monotone counter folded into fit keys; bumps whenever a market
        setting or forward policy changes (any ticker — forwards feed every
        prepared-quote array, so a global bust is the simple safe choice)."""
        with self._lock:
            return self._forwards_version

    def market_settings(self, ticker: str) -> MarketSettings:
        """The ticker's rate/dividend settings (defaults when never set)."""
        with self._lock:
            return self._market_settings.get(ticker) or MarketSettings()

    def set_market_settings(self, ticker: str, settings: MarketSettings) -> MarketSettings:
        """Apply new market settings; identical settings don't bump the
        forwards version, so a redundant PUT never invalidates warm fits."""
        with self._lock:
            if settings != self._market_settings.get(ticker, MarketSettings()):
                self._market_settings[ticker] = settings
                self._forwards_version += 1
            return self._market_settings.get(ticker) or MarketSettings()

    def forward_policy(self, ticker: str, expiry_iso: str) -> ForwardPolicy:
        """The node's forward policy ("parity" default when never set)."""
        with self._lock:
            return self._forward_policies.get((ticker, expiry_iso)) or ForwardPolicy()

    def set_forward_policy(
        self, ticker: str, expiry_iso: str, policy: ForwardPolicy
    ) -> ForwardPolicy:
        """Store one node's forward policy; UnknownNodeError on bad nodes
        (validated *before* storing), version bumped only on a real change."""
        iso = self.resolve_expiry(ticker, expiry_iso).isoformat()  # may raise
        with self._lock:
            if policy != self._forward_policies.get((ticker, iso), ForwardPolicy()):
                self._forward_policies[(ticker, iso)] = policy
                self._forwards_version += 1
            return self._forward_policies.get((ticker, iso)) or ForwardPolicy()

    # ------------------------------------------------------ event calendar
    @property
    def events_version(self) -> int:
        """Monotone counter folded into fit keys; bumps on calendar changes
        (events drive the variance clock, so a change must refit)."""
        with self._lock:
            return self._events_version

    def events(self, ticker: str) -> list[EventSpec]:
        """The ticker's persisted event calendar (empty when never set)."""
        with self._lock:
            return list(self._events.get(ticker, []))

    def set_events(self, ticker: str, events: list[EventSpec]) -> list[EventSpec]:
        """Replace the ticker's event calendar; bump the version only on a real
        change so a redundant PUT never invalidates warm fit caches."""
        with self._lock:
            if events != self._events.get(ticker, []):
                self._events[ticker] = list(events)
                self._events_version += 1
            return list(self._events.get(ticker, []))

    def dividend_model(self, ticker: str) -> DividendModel:
        """The ticker's MarketSettings translated to a data-layer model."""
        settings = self.market_settings(ticker)
        return DividendModel(
            mode=settings.dividendMode,
            yield_=settings.dividendYield,
            dividends=tuple(
                Dividend(date.fromisoformat(d.exDate), d.amount)
                for d in settings.dividends
            ),
            switch_years=settings.switchYears,
        )

    def theoretical_forward_for(self, ticker: str, expiry: date) -> tuple[float, float]:
        """(forward, discount) from the dividend model and flat rate."""
        spot = self.snapshot(ticker).spot
        rate = self.market_settings(ticker).rate
        t = self.year_fraction(expiry)
        forward = theoretical_forward(
            spot, rate, t, self.dividend_model(ticker), self.reference_date
        )
        return forward, math.exp(-rate * t)

    def cash_dividend_schedule(self, ticker: str, expiry: date, forward: float):
        """Forward-consistent discrete CASH schedule for de-Americanizing the
        chain, or None to keep the continuous-yield de-Am (volfit.data.dividends).

        Returns ``(ex_times, scaled_amounts, rate)``: the discrete-dividend tree
        uses the ticker's physical ``rate`` and the schedule's ex-date timing,
        the amounts scaled so the escrowed forward reproduces ``forward`` — so
        the smile joins smoothly across a cash ex-date with no level shift.
        """
        rate = self.market_settings(ticker).rate
        schedule = forward_consistent_cash_schedule(
            self.snapshot(ticker).spot,
            forward,
            rate,
            self.year_fraction(expiry),
            self.dividend_model(ticker),
            self.reference_date,
        )
        if schedule is None:
            return None
        times, amounts = schedule
        return times, amounts, rate

    def resolved_forward(self, ticker: str, expiry: date) -> ResolvedForward:
        """The forward calibration uses for one expiry, per its policy.

        "parity" reads the regression (always present: the expiry universe
        is gated on parity fits, see resolve_expiry); "theoretical" prices
        the dividend model; "manual" takes the user's forward with the
        parity discount (falling back to exp(-rate t) defensively).
        """
        policy = self.forward_policy(ticker, expiry.isoformat())
        parity = self.forwards(ticker).get(expiry)
        if policy.mode == "theoretical":
            forward, discount = self.theoretical_forward_for(ticker, expiry)
            return ResolvedForward(expiry, forward, discount, "theoretical")
        if policy.mode == "manual":
            if parity is not None:
                discount = parity.discount
            else:
                rate = self.market_settings(ticker).rate
                discount = math.exp(-rate * self.year_fraction(expiry))
            return ResolvedForward(expiry, float(policy.manualForward), discount, "manual")
        return ResolvedForward(expiry, parity.forward, parity.discount, "parity")

    # ------------------------------------------------------------- fit cache
    def get_fit(self, key: tuple) -> FitRecord | None:
        """Cached fit, keyed (ticker, ISO, mode, session-v, settings-v)."""
        with self._lock:
            return self._fits.get(key)

    def store_fit(self, key: tuple, record: FitRecord) -> None:
        with self._lock:
            self._fits[key] = record

    # --------------------------------------------------------- edit sessions
    def session(self, key: tuple[str, str]) -> EditSession:
        """The node's edit session, created on first use (lock-guarded)."""
        with self._lock:
            if key not in self._sessions:
                self._sessions[key] = EditSession()
            return self._sessions[key]

    def session_if_exists(self, key: tuple[str, str]) -> EditSession | None:
        """The node's edit session if one was ever created, else None."""
        with self._lock:
            return self._sessions.get(key)

    # ------------------------------------------------- var-swap quote sessions
    def varswap_session(self, key: tuple[str, str]) -> VarSwapSession:
        """The node's var-swap session, created on first use (lock-guarded)."""
        with self._lock:
            if key not in self._varswap_sessions:
                self._varswap_sessions[key] = VarSwapSession()
            return self._varswap_sessions[key]

    def varswap_session_if_exists(self, key: tuple[str, str]) -> VarSwapSession | None:
        """The node's var-swap session if one was ever created, else None."""
        with self._lock:
            return self._varswap_sessions.get(key)

    # ----------------------------------------------------------------- priors
    def get_prior(self, key: tuple[str, str]) -> PriorRecord | None:
        with self._lock:
            return self._priors.get(key)

    def save_prior(self, key: tuple[str, str], record: PriorRecord) -> None:
        with self._lock:
            self._priors[key] = record

    # ------------------------------------------------------------- lit / dark
    def node_lit(self, ticker: str, iso: str) -> bool:
        """Whether a node is lit (observed); lit by default, dark when darkened."""
        with self._lock:
            return (ticker, iso) not in self._dark_nodes

    def set_node_lit(self, ticker: str, iso: str, lit: bool) -> None:
        """Mark a node lit (observed source) or dark (extrapolation target)."""
        with self._lock:
            if lit:
                self._dark_nodes.discard((ticker, iso))
            else:
                self._dark_nodes.add((ticker, iso))

    # --------------------------------------------------------------- universe
    @property
    def universe(self):
        return self._universe

    @universe.setter
    def universe(self, value) -> None:
        self._universe = value


def _source_id_of(provider: OptionChainProvider) -> str:
    """Stable data-source id for a provider instance (used when AppState is
    built around a single provider, e.g. in tests)."""
    name = type(provider).__name__.lower()
    for sid in ("yahoo", "bloomberg", "massive", "synthetic"):
        if sid in name:
            return sid
    return "synthetic"  # unknown/custom providers behave like the offline source
