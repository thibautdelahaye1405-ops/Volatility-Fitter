"""Causal temporal state for the dynamic directed-harmonic framework (Phase 1).

Implements Docs/dynamic_directed_harmonic_graph_framework.md §4 (observation
classes and leases), §6.1/§6.3 (residual dynamics and updates), the §10
causal-order guards, and the Phase-0 decision record:

* D2  transition family: ``phi(dt) = 2^(-dt/H)``. Finite half-life H is an
  OU process with ``Q(dt) = v_inf * (1 - phi^2)``; ``H = inf`` is a random
  walk with ``Q(dt) = q_rate * dt``. Both are semigroup-consistent, so
  advancing a state stepwise or in one jump gives identical results — which
  is what lets a snapshot replay reproduce point-formulas exactly.
* D3  hard residual update for CERTIFIED target observations — the diffuse
  prior (K -> 1) limit: mean = e, variance = Var(e) — and a finite-quality
  Kalman update for soft observations.
* D4  leases carry the INNOVATION ``z``, never the level: a carried node's
  mark keeps moving with its transported baseline.
* D5  the full aligned residual ``e = d - beta * m_source`` is attributed to
  the target's idiosyncratic state; source ambiguity enters only variance,
  through the ``beta^2 * V_source`` term of the measurement variance.

Pure state layer: no graph topology and no solver imports (Phase 2 owns the
directed engine, Phase 3 the harmonic solve). Timestamps are any monotone
float clock the caller chooses — only differences enter the math. States are
frozen; every mutation returns a new record, so a solve can never corrupt
persisted state as a side effect.

Exit gate (tests/test_graph_temporal_state.py): the §5 asynchronous A/B
running example reproduced by composing these objects alone, against the
SAME fixture as the Phase-0 goldens (tests/fixtures/graph_dynamic_golden.json).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date
from typing import Callable, Iterable, Mapping

import numpy as np

from volfit.graph.message import N_HANDLES

#: §4.2 observation classes, in decreasing order of boundary authority.
OBSERVATION_CLASSES = ("fresh_certified", "carried", "soft_stale", "unobserved")


class TemporalOrderError(ValueError):
    """A causal-order violation: time moved backwards, an observation from
    the future was used, or an update was applied to an un-advanced state."""


class PersistenceGuardError(RuntimeError):
    """§10 Step 8: only state descended from ACTUAL calibrations persists —
    a graph prediction must never be re-ingested as observed state."""


def _handles(value, name: str, *, minimum: float | None = None) -> np.ndarray:
    """Broadcast a scalar or length-3 sequence to a read-only (3,) array."""
    arr = np.asarray(value, dtype=float)
    if arr.ndim == 0:
        arr = np.full(N_HANDLES, float(arr))
    if arr.shape != (N_HANDLES,):
        raise ValueError(f"{name} must be scalar or length-{N_HANDLES}, got {value!r}")
    arr = arr.copy()
    if minimum is not None and np.any(arr < minimum):
        raise ValueError(f"{name} must be >= {minimum}, got {value!r}")
    arr.setflags(write=False)
    return arr


# ------------------------------------------------------------------- dynamics
@dataclass(frozen=True, eq=False)
class ResidualDynamics:
    """D2 per-handle residual transition. ``half_life = inf`` marks the
    random-walk branch (phi = 1, ``q_rate`` variance per unit time); a finite
    half-life is OU with stationary variance ``v_inf``."""

    half_life: np.ndarray  # (3,) > 0, inf allowed
    v_inf: np.ndarray      # (3,) >= 0 — OU stationary variance
    q_rate: np.ndarray     # (3,) >= 0 — random-walk variance rate

    def phi(self, delta: float) -> np.ndarray:
        if delta < 0.0:
            raise TemporalOrderError(f"negative elapsed time {delta}")
        return np.power(2.0, -delta / self.half_life)

    def process_variance(self, delta: float) -> np.ndarray:
        """``Q(dt)`` — semigroup-consistent for both branches (doc §6.1/D2)."""
        phi2 = self.phi(delta) ** 2
        return np.where(
            np.isinf(self.half_life), self.q_rate * delta, self.v_inf * (1.0 - phi2)
        )


def residual_dynamics(
    half_life: float | Iterable[float] = math.inf,
    v_inf: float | Iterable[float] = 0.0,
    q_rate: float | Iterable[float] = 0.0,
) -> ResidualDynamics:
    """Factory with validation; scalars broadcast to all three handles."""
    h = _handles(half_life, "half_life")
    if np.any(h <= 0.0) or np.any(np.isnan(h)):
        raise ValueError(f"half_life must be > 0 (inf = random walk), got {half_life!r}")
    return ResidualDynamics(h, _handles(v_inf, "v_inf", minimum=0.0),
                            _handles(q_rate, "q_rate", minimum=0.0))


# ----------------------------------------------------------- observation state
@dataclass(frozen=True, eq=False)
class ObservationState:
    """The last ACTUAL calibration of a node, in innovation coordinates (D4).

    ``innovation``/``variance`` are per-handle; ``observation_id`` is the
    provenance of the real calibration this state descends from (§4.4)."""

    innovation: np.ndarray  # z (3,)
    variance: np.ndarray    # calibration variance (3,)
    timestamp: float
    observation_id: str
    certified: bool = True
    config_version: str = ""

    def carried_to(self, t: float, q_rate: float | Iterable[float] = 0.0):
        """Lease propagation (§4.4): the innovation mean is carried FLAT (the
        mark still moves with the transported baseline — D4) while variance
        accumulates ``q_rate * dt``. Returns ``(mean, variance)`` at ``t``."""
        if t < self.timestamp:
            raise TemporalOrderError(
                f"cannot carry observation {self.observation_id!r} "
                f"({self.timestamp}) backwards to {t} — look-ahead"
            )
        grown = self.variance + _handles(q_rate, "q_rate", minimum=0.0) * (
            t - self.timestamp
        )
        grown.setflags(write=False)
        return self.innovation, grown

    def to_record(self) -> dict:
        return {
            "innovation": self.innovation.tolist(),
            "variance": self.variance.tolist(),
            "timestamp": self.timestamp,
            "observationId": self.observation_id,
            "certified": self.certified,
            "configVersion": self.config_version,
        }


def observation_state(
    innovation,
    variance,
    timestamp: float,
    observation_id: str,
    *,
    certified: bool = True,
    config_version: str = "",
) -> ObservationState:
    if not observation_id:
        raise PersistenceGuardError(
            "an observation state requires the provenance id of an actual "
            "calibration (§10 Step 8)"
        )
    return ObservationState(
        _handles(innovation, "innovation"),
        _handles(variance, "variance", minimum=0.0),
        float(timestamp),
        observation_id,
        bool(certified),
        config_version,
    )


def observation_state_from_record(record: Mapping) -> ObservationState:
    return observation_state(
        record["innovation"], record["variance"], record["timestamp"],
        record["observationId"], certified=record.get("certified", True),
        config_version=record.get("configVersion", ""),
    )


# --------------------------------------------------------------- lease policy
@dataclass(frozen=True)
class LeasePolicy:
    """§4.2 observation-class thresholds by age (same clock as the states).
    Certification is an input: freshness alone never grants a hard boundary."""

    fresh_max_age: float
    carried_max_age: float
    soft_max_age: float

    def __post_init__(self):
        if not (0.0 <= self.fresh_max_age <= self.carried_max_age <= self.soft_max_age):
            raise ValueError("require 0 <= fresh <= carried <= soft max ages")

    def classify(self, age: float, certified: bool) -> str:
        if age < 0.0:
            raise TemporalOrderError(f"negative observation age {age} — look-ahead")
        if certified and age <= self.fresh_max_age:
            return "fresh_certified"
        if certified and age <= self.carried_max_age:
            return "carried"
        if age <= self.soft_max_age:
            return "soft_stale"
        return "unobserved"


# -------------------------------------------------------- residual measurement
def residual_measurement(observed_innovation, beta, source_mean) -> np.ndarray:
    """§6.3 / D5: the aligned residual ``e = d - beta * m_source`` against the
    CAUSAL source state (never a future interpolation — golden 15.7)."""
    e = _handles(observed_innovation, "observed_innovation") - _handles(
        beta, "beta"
    ) * _handles(source_mean, "source_mean")
    e.setflags(write=False)
    return e


def residual_measurement_variance(
    observation_variance, beta, source_variance, relation_precision
) -> np.ndarray:
    """§6.3: ``Var(e) = V_obs + beta^2 V_source + 1/p`` — the source's
    unobserved-move ambiguity lives HERE, not in the residual mean (D5)."""
    p = _handles(relation_precision, "relation_precision")
    if np.any(p <= 0.0):
        raise ValueError("relation_precision must be > 0")
    var = (
        _handles(observation_variance, "observation_variance", minimum=0.0)
        + _handles(beta, "beta") ** 2
        * _handles(source_variance, "source_variance", minimum=0.0)
        + 1.0 / p
    )
    var.setflags(write=False)
    return var


# -------------------------------------------------------------- residual state
@dataclass(frozen=True, eq=False)
class ResidualState:
    """Persistent target-specific residual ``u`` (doc §6, §13.5): the state
    object that survives a target going dark. ``observed_at`` is the last
    ACTUAL target observation; ``as_of`` the last advancement."""

    mean: np.ndarray       # u (3,)
    variance: np.ndarray   # V_u (3,)
    observed_at: float | None
    as_of: float
    source_observation_ids: tuple[str, ...]
    baseline_ids: tuple[str, ...]
    config_version: str

    # ------------------------------------------------------------- prediction
    def advance(self, t: float, dynamics: ResidualDynamics) -> "ResidualState":
        """§10 Step 3: ``m -> phi m``, ``V -> phi^2 V + Q`` from ``as_of`` to
        ``t``. A never-touched state just re-stamps its clock."""
        if not math.isfinite(self.as_of):
            return replace(self, as_of=float(t))
        if t < self.as_of:
            raise TemporalOrderError(f"advance {self.as_of} -> {t} moves backwards")
        phi = dynamics.phi(t - self.as_of)
        mean = phi * self.mean
        var = phi**2 * self.variance + dynamics.process_variance(t - self.as_of)
        mean.setflags(write=False)
        var.setflags(write=False)
        return replace(self, mean=mean, variance=var, as_of=float(t))

    # ---------------------------------------------------------------- updates
    def updated_hard(
        self, measurement, measurement_variance, t: float, observation_id: str
    ) -> "ResidualState":
        """D3 certified update — the diffuse-prior (K -> 1) limit: the mean
        takes the full observed dislocation (so ``beta*m_source + u`` equals
        the calibration exactly — the §4.3 clamp identity) and the variance
        is the residual MEASUREMENT variance."""
        if t < self.as_of:
            raise TemporalOrderError(f"update at {t} precedes state as_of {self.as_of}")
        return self._updated(
            _handles(measurement, "measurement"),
            _handles(measurement_variance, "measurement_variance", minimum=0.0),
            t, observation_id,
        )

    def updated_kalman(
        self, measurement, measurement_variance, t: float, observation_id: str
    ) -> "ResidualState":
        """§6.3 finite-quality update, ``K = V / (V + Var(e))`` per handle.
        The state must already be advanced to ``t`` (§10 Step 3 before 4)."""
        if t != self.as_of:
            raise TemporalOrderError(
                f"advance the state to {t} before a Kalman update (as_of {self.as_of})"
            )
        e = _handles(measurement, "measurement")
        r = _handles(measurement_variance, "measurement_variance")
        if np.any(r <= 0.0):
            raise ValueError("Kalman measurement variance must be > 0")
        gain = self.variance / (self.variance + r)
        mean = self.mean + gain * (e - self.mean)
        # gain * r == V*r/(V+r) == (1-K)*V, but stays stable in the diffuse
        # limit where 1-K underflows to cancellation noise.
        var = gain * r
        return self._updated(mean, var, t, observation_id)

    def _updated(self, mean, var, t: float, observation_id: str) -> "ResidualState":
        if not observation_id:
            raise PersistenceGuardError(
                "residual updates require the provenance id of an ACTUAL target "
                "calibration — graph predictions must never update state (§10 Step 8)"
            )
        mean = np.asarray(mean, dtype=float).copy()
        var = np.asarray(var, dtype=float).copy()
        mean.setflags(write=False)
        var.setflags(write=False)
        return replace(
            self, mean=mean, variance=var, observed_at=float(t), as_of=float(t),
            source_observation_ids=self.source_observation_ids + (observation_id,),
        )

    # ------------------------------------------------------------ persistence
    def persistable(self) -> bool:
        """True only for state descended from actual target calibrations."""
        return self.observed_at is not None and bool(self.source_observation_ids)

    def to_record(self) -> dict:
        return {
            "mean": self.mean.tolist(),
            "variance": self.variance.tolist(),
            "observedAt": self.observed_at,
            "asOf": None if not math.isfinite(self.as_of) else self.as_of,
            "sourceObservationIds": list(self.source_observation_ids),
            "baselineIds": list(self.baseline_ids),
            "configVersion": self.config_version,
        }


def empty_residual(
    config_version: str, *, variance: float | Iterable[float] = 0.0
) -> ResidualState:
    """A residual with no target information yet (mean zero). The variance
    seed is the caller's dark-prior convention (Phase 2 decides); it is NOT
    persistable until an actual observation updates it."""
    return ResidualState(
        _handles(0.0, "mean"), _handles(variance, "variance", minimum=0.0),
        None, -math.inf, (), (), config_version,
    )


def residual_from_record(record: Mapping) -> ResidualState:
    state = empty_residual(record.get("configVersion", ""))
    as_of = record.get("asOf")
    return replace(
        state,
        mean=_handles(record["mean"], "mean"),
        variance=_handles(record["variance"], "variance", minimum=0.0),
        observed_at=record.get("observedAt"),
        as_of=-math.inf if as_of is None else float(as_of),
        source_observation_ids=tuple(record.get("sourceObservationIds", ())),
        baseline_ids=tuple(record.get("baselineIds", ())),
    )


def assert_persistable(state: ResidualState) -> None:
    if not state.persistable():
        raise PersistenceGuardError(
            "refusing to persist a residual with no actual-observation "
            "provenance (§10 Step 8: graph output is never observed state)"
        )


def reuse_or_invalidate(
    state: ResidualState, config_version: str
) -> tuple[ResidualState, bool]:
    """Golden 15.13: a residual defined under one relation config must never
    be silently reused under another. Returns ``(state, invalidated)`` — on a
    version mismatch, a fresh empty residual under the NEW version."""
    if state.config_version == config_version:
        return state, False
    return empty_residual(config_version), True


# ------------------------------------------------------------------ migration
def _day_clock(day_iso: str) -> float:
    return float(date.fromisoformat(day_iso).toordinal())


def migrate_atm_floor_history(
    rows: Iterable[tuple[str, str, str, float]],
    *,
    config_version: str,
    clock: Callable[[str], float] = _day_clock,
    uninformative_variance: float = 1.0,
) -> dict[tuple[str, str], ResidualState]:
    """Phase-1 item 7: lift the legacy ATM-only lit-innovation history (the
    ``AppState`` graph-idio store feeding the band floor) into residual
    records. Rows are ``(ticker, expiry, day_iso, atm_innovation)``; the
    LATEST day per node wins. The ATM mean is real observed information;
    skew/curvature get zero mean, and ALL handles get an explicitly wide
    variance because the legacy store kept none (§14.2: prefer wider
    uncertainty over invented precision). Provenance is tagged so
    certification can distinguish migrated state from native records."""
    latest: dict[tuple[str, str], tuple[float, str, float]] = {}
    for ticker, expiry, day_iso, atm in rows:
        t = clock(day_iso)
        key = (ticker, expiry)
        if key not in latest or t > latest[key][0]:
            latest[key] = (t, day_iso, float(atm))
    out: dict[tuple[str, str], ResidualState] = {}
    for (ticker, expiry), (t, day_iso, atm) in latest.items():
        state = empty_residual(config_version)
        out[(ticker, expiry)] = state._updated(
            np.array([atm, 0.0, 0.0]),
            np.full(N_HANDLES, float(uninformative_variance)),
            t,
            f"legacy_atm_floor:{ticker}:{expiry}:{day_iso}",
        )
    return out
