"""Per-application state and caches behind the volfit API (ROADMAP Phase 5).

Everything heavy is computed at most once: chain snapshots, parity-implied
forwards, per-(ticker, expiry, fit-mode, session-version) slice calibrations,
saved priors (display curve + fitted LQD params, so prior densities can be
rebuilt) and the lazily-built graph smile universe. The synthetic
provider is deterministic and quote edits bump their session's version (a new
cache key), so caches never need invalidation. A single lock guards the
mutable dicts because WebSocket surface fits run on worker threads; the
universe build happens outside that lock (it re-enters the fit cache) and is
idempotent, so a rare double build is harmless.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date

from volfit.api.quotes import PreparedQuotes
from volfit.api.schemas import SmilePoint
from volfit.api.session import EditSession
from volfit.data.forwards import ImpliedForward, implied_forwards
from volfit.data.provider import SyntheticProvider
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

    def __init__(self, reference_date: date) -> None:
        self.reference_date = reference_date
        self.provider = SyntheticProvider(reference_date=reference_date)
        self._snapshots: dict[str, ChainSnapshot] = {}
        self._forwards: dict[str, dict[date, ImpliedForward]] = {}
        self._fits: dict[tuple[str, str, str, int], FitRecord] = {}
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

    # ------------------------------------------------------------- fit cache
    def get_fit(self, key: tuple[str, str, str, int]) -> FitRecord | None:
        """Cached fit for (ticker, expiry-ISO, fit-mode, session-version)."""
        with self._lock:
            return self._fits.get(key)

    def store_fit(self, key: tuple[str, str, str, int], record: FitRecord) -> None:
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
