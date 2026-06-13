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
from datetime import date

from volfit.api.fit_models import DisplayFit
from volfit.api.quotes import PreparedQuotes
from volfit.api.schemas import FitSettings, ForwardPolicy, MarketSettings, SmilePoint
from volfit.api.session import EditSession
from volfit.data.dividends import (
    Dividend,
    DividendModel,
    forward_consistent_cash_schedule,
    theoretical_forward,
)
from volfit.api.state_universe import UniverseMixin, UnknownNodeError  # noqa: F401 (re-export)
from volfit.data.forwards import ImpliedForward, ResolvedForward, implied_forwards
from volfit.data.provider import OptionChainProvider, SyntheticProvider
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
    ) -> None:
        self.reference_date = reference_date
        self.provider = provider or SyntheticProvider(reference_date=reference_date)
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
        self._market_settings: dict[str, MarketSettings] = {}
        self._forward_policies: dict[tuple[str, str], ForwardPolicy] = {}
        self._forwards_version = 0  # bumped on change; part of fit-cache keys
        self._fits: dict[tuple, FitRecord] = {}
        self._priors: dict[tuple[str, str], PriorRecord] = {}
        self._sessions: dict[tuple[str, str], EditSession] = {}
        self._universe = None  # volfit.graph.smile_universe.SmileUniverse
        self._lock = threading.Lock()

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
        snap = self.provider.fetch_chain(ticker, chosen)  # outside lock (network)
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

    # ----------------------------------------------------------------- priors
    def get_prior(self, key: tuple[str, str]) -> PriorRecord | None:
        with self._lock:
            return self._priors.get(key)

    def save_prior(self, key: tuple[str, str], record: PriorRecord) -> None:
        with self._lock:
            self._priors[key] = record

    # --------------------------------------------------------------- universe
    @property
    def universe(self):
        return self._universe

    @universe.setter
    def universe(self, value) -> None:
        self._universe = value
