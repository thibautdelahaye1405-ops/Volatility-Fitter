"""In-memory observation-filter history ring (Note 15, V3.9 item 7).

The NodeFilter holder keeps ONE step (each commit overwrites); this module
keeps the last :data:`RING_MAXLEN` committed steps per node as compact scalar
records, so the FilterTimeline UI and the offline replay artifact can show the
filter's evidence over time — prediction/observation/posterior bands, the
standardized innovation ζ, gains and the Q breakdown.

Semantics (all inherited from the app layer, nothing re-decided here):
* ONE step per genuinely committed update — ``record_commit`` is called by
  ``on_fit_commit`` inside its (data_version, session_version) idempotence
  guard, so recalibrating an unchanged snapshot appends nothing;
* seed/reset steps are recorded with their provenance / reset reason and a
  charged dt of 0 (the seed prediction is the seed law itself);
* ADVISORY, the commit_hook discipline: any failure here must never break a
  calibration — ``record_commit`` swallows everything;
* storage is ``AppState._filter_history``, a plain dict BESIDE
  ``_filter_states`` keyed the same (ticker, iso, fit_mode) way: cleared by
  ``_clear_chain_caches`` (source/as-of switch = the strict reset) and listed
  in ``_CHAIN_CACHE_ATTRS`` so transient as-of round-trips restore it. NOT
  workspace-persisted (recorded rider — avoids new workspace round-trip
  locks).

ζ here is the PRE-inflation standardized innovation ν/√(diag(P⁻ + R)) — the
tuning verdict statistic (std(ζ) ≈ 1 iff Q is scaled right, the intraday-sweep
convention). The stored prediction covariance is POST-adaptive-inflation, and
``_inflate_prediction`` records the added variance in the q_breakdown's
"adaptive" component, so the pre-inflation diagonal is recovered exactly by
subtracting it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

#: Ring capacity per node — 64 committed steps covers several intraday
#: sessions at a 30-minute cadence while staying trivially small in memory.
RING_MAXLEN = 64


@dataclass(frozen=True)
class FilterStep:
    """One committed filter step, compact scalars only (no overlay curves —
    those are memoized per committed state on the NodeFilter holder and must
    never be recomputed per history read). Per-handle tuples follow the
    FILTER_HANDLES order (ATM, skew, curvature)."""

    ts: float  # snapshot epoch (seconds) the step committed at
    dt_days: float  # process-noise time the ACTIVE clock charged (0 on seed)
    prediction: tuple[float, ...]  # m^-
    prediction_std: tuple[float, ...]  # sqrt(diag(P^-)), post-inflation
    observation: tuple[float, ...]  # z
    observation_std: tuple[float, ...]  # sqrt(diag(R))
    innovation: tuple[float, ...]  # nu = z - m^-  (MAP: the realized move)
    zeta: tuple[float, ...] | None  # pre-inflation nu / sqrt(diag(P^- + R))
    gain: tuple[float, ...]  # diag(K)
    posterior: tuple[float, ...]  # m^+
    posterior_std: tuple[float, ...]  # sqrt(diag(P^+))
    process_breakdown: dict[str, tuple[float, ...]]  # Q components + adaptive
    transport_distance: float | None
    provenance: str  # "seed:<source>" | "update" | "map"
    reset_reason: str | None
    contaminated: bool


class FilterHistory:
    """Bounded per-node ring of :class:`FilterStep` records, oldest first."""

    __slots__ = ("_steps",)

    def __init__(self, maxlen: int = RING_MAXLEN) -> None:
        self._steps: deque[FilterStep] = deque(maxlen=maxlen)

    def append(self, step: FilterStep) -> None:
        self._steps.append(step)

    def steps(self) -> list[FilterStep]:
        return list(self._steps)

    def __len__(self) -> int:
        return len(self._steps)


# ------------------------------------------------------------------ builders
def zeta_of(holder) -> np.ndarray | None:
    """Per-handle PRE-inflation standardized innovation of a NodeFilter's
    stored step, or None when the holder carries no complete update.

    The stored prediction cov is post-adaptive-inflation; the inflation's
    added variance is exactly the q_breakdown "adaptive" component (see
    ``observation_filter._inflate_prediction``), so subtracting it recovers
    the pre-inflation diag(P^-) that the sweep convention standardizes by."""
    upd, pred, meas = holder.update, holder.prediction, holder.measurement
    if upd is None or pred is None or meas is None:
        return None
    nu = np.asarray(upd.innovation, dtype=float)
    p_diag = np.diag(np.asarray(pred.cov, dtype=float)).copy()
    adaptive = pred.q_breakdown.get("adaptive")
    if adaptive is not None:
        p_diag = p_diag - np.asarray(adaptive, dtype=float)
    r_diag = np.diag(np.asarray(meas.cov, dtype=float))
    s = np.maximum(p_diag + r_diag, 1e-18)
    return nu / np.sqrt(s)


def _vec(v) -> tuple[float, ...]:
    return tuple(float(x) for x in np.asarray(v, dtype=float).ravel())


def _std(cov) -> tuple[float, ...]:
    return _vec(np.sqrt(np.maximum(np.diag(np.asarray(cov, dtype=float)), 0.0)))


def step_from_holder(holder, dt_days: float) -> FilterStep | None:
    """Compact ring record from a committed NodeFilter, or None when the
    holder has no stored prediction/update (nothing to audit)."""
    pred, meas, upd, st = (
        holder.prediction, holder.measurement, holder.update, holder.state,
    )
    if pred is None or upd is None:
        return None
    z = zeta_of(holder)
    return FilterStep(
        ts=float(st.timestamp),
        dt_days=float(dt_days),
        prediction=_vec(pred.mean),
        prediction_std=_std(pred.cov),
        observation=_vec(meas.handles) if meas is not None else (),
        observation_std=_std(meas.cov) if meas is not None else (),
        innovation=_vec(upd.innovation),
        zeta=None if z is None else _vec(z),
        gain=_vec(np.diag(np.asarray(upd.gain, dtype=float))),
        posterior=_vec(upd.mean),
        posterior_std=_std(upd.cov),
        process_breakdown={k: _vec(v) for k, v in pred.q_breakdown.items()},
        transport_distance=float(pred.transport_distance),
        provenance=st.provenance,
        reset_reason=st.reset_reason,
        contaminated=bool(meas.contaminated) if meas is not None else False,
    )


def record_commit(state, key: tuple, holder, prev, ts_now: float) -> None:
    """Append ONE ring step for a just-committed holder (called by
    ``on_fit_commit`` inside its idempotence guard, once per genuinely new
    observation). ``prev`` is the pre-commit holder (None on first seed);
    the charged dt mirrors the prediction law: 0 on any (re)seed, else the
    active clock's ``_filter_dt_days``. ADVISORY — never raises."""
    try:
        if holder.state.reset_reason is not None or prev is None:
            dt_days = 0.0
        else:
            # Lazy import: observation_filter imports this module at top level.
            from volfit.api.observation_filter import _filter_dt_days

            dt_days = _filter_dt_days(
                state.options(), prev.state.timestamp, float(ts_now)
            )
        step = step_from_holder(holder, dt_days)
        if step is None:
            return
        ring = state.filter_history(key)
        if ring is None:
            ring = FilterHistory()
            state.set_filter_history(key, ring)
        ring.append(step)
    except Exception:  # noqa: BLE001 — history must never break a calibration
        pass


# ------------------------------------------------------------------- payload
def _step_out(step: FilterStep):
    """Wire model of one ring step (schemas.FilterStepOut)."""
    from volfit.api.schemas import FilterStepOut

    return FilterStepOut(
        ts=step.ts,
        dtDays=step.dt_days,
        prediction=list(step.prediction),
        predictionStd=list(step.prediction_std),
        observation=list(step.observation),
        observationStd=list(step.observation_std),
        innovation=list(step.innovation),
        zeta=None if step.zeta is None else list(step.zeta),
        gain=list(step.gain),
        posterior=list(step.posterior),
        posteriorStd=list(step.posterior_std),
        processBreakdown={k: list(v) for k, v in step.process_breakdown.items()},
        transportDistance=step.transport_distance,
        provenance=step.provenance,
        resetReason=step.reset_reason,
        contaminated=step.contaminated,
    )


def step_doc(step: FilterStep) -> dict:
    """JSON-safe dict of one step in the exact wire shape (used by the offline
    replay artifact so its JSON matches the live endpoint byte-for-byte)."""
    return _step_out(step).model_dump()


def history_payload(state, ticker: str, expiry: str, fit_mode: str):
    """The GET /smiles/{t}/{e}/filter/history payload. Read-only and
    POLL-SAFE: reads the ring dict only — never fits, never retargets.
    Advisory — ``active=False`` (empty steps) when off / unresolvable /
    nothing committed yet."""
    from volfit.api.filter_mode import resolve_filter_mode
    from volfit.api.schemas import FilterHistoryResponse

    inactive = FilterHistoryResponse(active=False, steps=[])
    if not resolve_filter_mode(state.options()).enabled:
        return inactive
    try:
        iso = state.resolve_expiry(ticker, expiry).isoformat()
    except Exception:  # noqa: BLE001 — advisory endpoint
        return inactive
    ring = state.filter_history((ticker, iso, fit_mode))
    if ring is None or len(ring) == 0:
        return inactive
    return FilterHistoryResponse(
        active=True, steps=[_step_out(s) for s in ring.steps()]
    )
