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

import threading
from dataclasses import dataclass
from datetime import date

from volfit.api.quotes import PreparedQuotes
from volfit.api.schemas import FitSettings, SmilePoint
from volfit.api.session import EditSession
from volfit.data.forwards import ImpliedForward, implied_forwards
from volfit.data.provider import OptionChainProvider, SyntheticProvider
from volfit.data.types import ChainSnapshot
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import CalibrationResult

#: Year-fraction day count used across the API (ACT/365 fixed).
DAYS_PER_YEAR = 365.0


class UnknownNodeError(KeyError):
    """Requested (ticker, expiry) does not exist in the provider universe."""


@dataclass(frozen=True)
class FitRecord:
    """One cached slice calibration plus the inputs it was fitted to."""

    prepared: PreparedQuotes
    result: CalibrationResult


@dataclass(frozen=True)
class PriorRecord:
    """A saved prior: the display curve the Smile Viewer charts plus the
    fitted LQD parameters (and expiry year fraction) that produced it, so
    the prior's density/quantile function can be rebuilt via build_slice."""

    curve: list[SmilePoint]
    params: LQDParams
    t: float


class AppState:
    """Provider handle plus all caches; one instance per FastAPI app."""

    def __init__(
        self, reference_date: date, provider: OptionChainProvider | None = None
    ) -> None:
        self.reference_date = reference_date
        self.provider = provider or SyntheticProvider(reference_date=reference_date)
        self._snapshots: dict[str, ChainSnapshot] = {}
        self._forwards: dict[str, dict[date, ImpliedForward]] = {}
        self._fit_settings = FitSettings()
        self._settings_version = 0  # bumped on change; part of fit-cache keys
        self._fits: dict[tuple, FitRecord] = {}
        self._priors: dict[tuple[str, str], PriorRecord] = {}
        self._sessions: dict[tuple[str, str], EditSession] = {}
        self._universe = None  # volfit.graph.smile_universe.SmileUniverse
        self._lock = threading.Lock()

    # ------------------------------------------------------------ market data
    def snapshot(self, ticker: str) -> ChainSnapshot:
        """Fetch-once chain snapshot; UnknownNodeError for unknown tickers."""
        if ticker not in self.provider.list_tickers():
            raise UnknownNodeError(f"unknown ticker {ticker!r}")
        with self._lock:
            if ticker not in self._snapshots:
                self._snapshots[ticker] = self.provider.fetch_chain(ticker)
            return self._snapshots[ticker]

    def forwards(self, ticker: str) -> dict[date, ImpliedForward]:
        """Parity-implied forwards per expiry, cached per ticker."""
        snapshot = self.snapshot(ticker)
        with self._lock:
            if ticker not in self._forwards:
                self._forwards[ticker] = implied_forwards(snapshot)
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
