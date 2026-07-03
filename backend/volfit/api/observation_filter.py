"""App layer of the observation Kalman filter (Note 15 §7.2, Phase 3).

Owns everything the pure cores (calib/observation_filter.py numerics,
calib/observation_measurement.py z/R builders) deliberately do not: node keys,
the AppState store, snapshot timestamps, transport, seeding, reset policy and
the diagnostics payload.

Semantics locked here:
* One update per genuinely NEW observation — ``on_fit_commit`` is idempotent
  per (node, data_version, session_version); recalibrating an unchanged
  snapshot re-reads the stored state.
* Node key = (ticker, iso, fit_mode). Source / as-of changes do not need to be
  in the key: ``AppState._clear_chain_caches`` wipes the store on those (the
  note's strict SOURCE_RESET_POLICY), while transient as-of round-trips
  restore it (``_CHAIN_CACHE_ATTRS``) and ``recalibrate`` keeps it (a refetch
  is a new observation, not a reset).
* A quote edit moves the session version -> reset (the edited chain
  invalidates the measurement the state was built on); a calendar gap beyond
  ``filterResetHours`` -> reset "stale"; a reset re-seeds from the transported
  active prior (graph_nodes.resolve_node_prior provenance hierarchy).
* The measurement is the LQD BACKBONE's handles (always fitted, model-
  agnostic carrier — the graph layer's convention), with the Jacobian R_t of
  calib/observation_measurement when the calibrator retained ``solver_diag``,
  else the factors fallback. ``contaminated`` flags a persistence-anchored
  fit (Note 13's gate keeps the overlap ~0 where quotes are dense).
* ``dt`` comes from SNAPSHOT timestamps, never wall clock.

Everything here is advisory: ``on_fit_commit`` is wrapped by its callers so a
filter failure can never break a calibration.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from volfit.api.filter_mode import FILTER_HANDLES, resolve_filter_mode
from volfit.api.graph_nodes import resolve_node_prior
from volfit.api.prior_mode import resolve_prior_mode
from volfit.api.state import AppState
from volfit.calib.observation_filter import (
    FilterMeasurement,
    FilterPrediction,
    FilterState,
    FilterUpdate,
    kalman_update,
    predict,
    process_noise,
    should_reset,
    transport_handles,
)
from volfit.calib.observation_measurement import (
    handle_jacobian_fd,
    measurement_from_factors,
    measurement_from_jacobian,
)
from volfit.calib.precision import RMS_FLOOR
from volfit.dynamics.ssr import ssr_of_regime
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.quadrature import build_slice


@dataclass
class NodeFilter:
    """Everything stored per node: the posterior state plus the last step's
    audit trail (prediction / measurement / update) for the diagnostics
    endpoint, and the idempotency marks."""

    state: FilterState
    prediction: FilterPrediction | None
    measurement: FilterMeasurement | None
    update: FilterUpdate | None
    data_version: int
    session_version: int
    forward: float  # the prepared forward the state was committed at


def _backbone_handles(result, tau: float) -> np.ndarray:
    """The LQD backbone's exact ATM handles (the filter's measurement carrier)."""
    h = atm_handles(result.slice, tau)
    return np.array([h.sigma0, h.skew, h.curvature])


def _noise_from_band(band, n_quotes: int, n_fit_rows: int):
    """Per-row stated noise std = the bid-ask half-spread, floored at RMS_FLOOR.

    ``band`` is the edited BID-ASK band (built regardless of the fit mode — the
    spread is the market's stated uncertainty even for a mid fit). Band-mode
    fits have 2 rows per quote (hinge + anchor), so the vector is tiled."""
    if band is None:
        return 10.0 * RMS_FLOOR  # no band info: assume a 10 bp noise scalar
    half = np.maximum((np.asarray(band.iv_hi) - np.asarray(band.iv_lo)) / 2.0, RMS_FLOOR)
    if half.size != n_quotes:  # edits changed alignment — degrade to the median
        return float(np.median(half))
    return np.concatenate([half, half]) if n_fit_rows == 2 * n_quotes else half


def _measurement(
    state: AppState, ticker: str, iso: str, record, solver_diag: dict | None
) -> FilterMeasurement:
    """(z, R) from the committed fit; Jacobian route when the solver Jacobian
    was retained, else the factors fallback (filterCovarianceMode aside, a
    missing Jacobian always falls back)."""
    from volfit.api import service  # local: service imports this module's hook

    prepared = record.prepared
    z = _backbone_handles(record.result, prepared.tau)
    # Contaminated = the committed fit actually received persistence targets:
    # a calibration-prior mode AND an active prior snapshot to anchor to
    # (hybrid with nothing fetched passes no targets, so z is market-pure).
    plan = resolve_prior_mode(state.options())
    contaminated = plan.any_calibration_prior and state.active_prior(ticker) is not None
    use_jac = (
        state.options().filterCovarianceMode == "jacobian"
        and solver_diag is not None
        and "jac" in solver_diag
    )
    if use_jac:
        band = service.edited_band(state, ticker, iso, prepared, "bidask")

        def handle_fn(theta):
            h = atm_handles(build_slice(LQDParams.from_vector(theta)), prepared.tau)
            return np.array([h.sigma0, h.skew, h.curvature])

        g = handle_jacobian_fd(handle_fn, solver_diag["theta"])
        return measurement_from_jacobian(
            z,
            solver_diag["jac"],
            g,
            solver_diag["residual"],
            solver_diag["n_fit_rows"],
            solver_diag["n_quotes"],
            noise_scale=_noise_from_band(
                band, solver_diag["n_quotes"], solver_diag["n_fit_rows"]
            ),
            inflate=state.options().filterResidualInflation,
            contaminated=contaminated,
        )
    # factors fallback: coverage stats straight off the prepared chain
    k = np.asarray(prepared.k, dtype=float)
    atm_win = max(float(z[0]) * np.sqrt(max(prepared.tau, 1e-8)), 0.02)
    n_atm = int(np.sum(np.abs(k) <= atm_win))
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = (np.asarray(prepared.iv_ask) - np.asarray(prepared.iv_bid)) / np.maximum(
            np.asarray(prepared.iv_mid), 1e-8
        )
    rel_spread = float(np.median(rel[np.isfinite(rel)])) if k.size else 0.05
    rms = max(float(record.result.max_iv_error), RMS_FLOOR)
    return measurement_from_factors(z, rms, n_atm, rel_spread, contaminated=contaminated)


def _seed(
    state: AppState, ticker: str, iso: str, key: tuple, ts: float, reason: str
) -> FilterState:
    """(Re)seed from the transported active prior (note §6.3: persistence 'may
    provide the initial saved prior from which the first filtered state is
    seeded'); P0 = the provenance-tier baseline covariance."""
    prior = resolve_node_prior(state, ticker, iso)
    cov = np.diag(1.0 / np.maximum(np.asarray(prior.precision, dtype=float), 1e-12))
    return FilterState(
        node_key=key,
        handle_names=FILTER_HANDLES,
        mean=np.asarray(prior.handles, dtype=float),
        cov=cov,
        timestamp=ts,
        provenance=f"seed:{prior.source}",
        reset_reason=reason,
    )


def on_fit_commit(
    state: AppState,
    ticker: str,
    iso: str,
    fit_mode: str,
    record,
    solver_diag: dict | None = None,
) -> NodeFilter | None:
    """Predict/update the node's filter state on a committed fit (note §6.1).

    Idempotent per (data_version, session_version); returns the stored holder.
    Callers must treat this as advisory (wrap in try/except)."""
    from volfit.api import service  # local: avoids a module-level cycle

    plan = resolve_filter_mode(state.options())
    if not plan.enabled:
        return None
    key = (ticker, iso, fit_mode)
    dv = state.data_version(ticker)
    sv = service.session_version(state, ticker, iso)
    prev: NodeFilter | None = state.filter_node(key)
    if prev is not None and prev.data_version == dv and prev.session_version == sv:
        return prev  # same snapshot, same edits: not a new observation

    ts_now = float(state.snapshot(ticker).timestamp.timestamp())
    f_now = float(record.prepared.forward)
    opts = state.options()

    reason: str | None
    if prev is None:
        reason = "first"
    else:
        dt_hours = max(ts_now - prev.state.timestamp, 0.0) / 3600.0
        reason = should_reset(
            dt_hours, opts.filterResetHours, quotes_edited=prev.session_version != sv
        )

    if reason is not None:
        seeded = _seed(state, ticker, iso, key, ts_now, reason)
        h = 0.0  # the prior machinery already transported to the current forward
        base_mean, base_cov, prev_ts = seeded.mean, seeded.cov, ts_now
        provenance = seeded.provenance
    else:
        h = float(np.log(f_now / prev.forward)) if prev.forward > 0.0 and f_now > 0.0 else 0.0
        ssr = ssr_of_regime(state.dynamics_regime())
        base_mean = transport_handles(prev.state.mean, h, ssr)
        base_cov, prev_ts = prev.state.cov, prev.state.timestamp
        provenance = "update"

    dt_days = max(ts_now - prev_ts, 0.0) / 86400.0
    q_diag, q_breakdown = process_noise(
        dt_days,
        h,
        vol_bp_sqrt_day=opts.filterProcessVolBpSqrtDay,
        skew_sqrt_day=opts.filterProcessSkewSqrtDay,
        curv_sqrt_day=opts.filterProcessCurvSqrtDay,
        transport_scale=opts.filterTransportNoiseScale,
    )
    prediction = predict(base_mean, base_cov, q_diag, abs(h), q_breakdown)
    measurement = _measurement(state, ticker, iso, record, solver_diag)
    upd = kalman_update(
        prediction.mean,
        prediction.cov,
        measurement.handles,
        measurement.cov,
        max_gain=opts.filterMaxGain,
    )
    new_state = FilterState(
        node_key=key,
        handle_names=FILTER_HANDLES,
        mean=upd.mean,
        cov=upd.cov,
        timestamp=ts_now,
        provenance=provenance,
        reset_reason=reason,
    )
    holder = NodeFilter(
        state=new_state,
        prediction=prediction,
        measurement=measurement,
        update=upd,
        data_version=dv,
        session_version=sv,
        forward=f_now,
    )
    state.set_filter_node(key, holder)
    return holder


def commit_hook(state: AppState, ticker: str, iso: str, fit_mode: str, record, solver_diag):
    """The advisory wrapper the fit paths call: never raises."""
    try:
        on_fit_commit(state, ticker, iso, fit_mode, record, solver_diag)
    except Exception:  # noqa: BLE001 — the filter must never break a calibration
        pass


# ------------------------------------------------------------- the payload
def filter_diagnostics(state: AppState, ticker: str, expiry: str, fit_mode: str):
    """The GET /smiles/{t}/{e}/filter payload (note invariant 5: every filtered
    output reports prediction, observation, innovation, gain and posterior).
    Advisory — never raises; ``active=False`` when off / no state yet."""
    from volfit.api.schemas import FilterDiagnostics

    plan = resolve_filter_mode(state.options())
    inactive = FilterDiagnostics(active=False, mode=plan.mode)
    if not plan.enabled:
        return inactive
    try:
        iso = state.resolve_expiry(ticker, expiry).isoformat()
    except Exception:  # noqa: BLE001 — advisory endpoint
        return inactive
    holder: NodeFilter | None = state.filter_node((ticker, iso, fit_mode))
    if holder is None or holder.update is None:
        return inactive

    def _std(cov: np.ndarray) -> list[float]:
        return [float(v) for v in np.sqrt(np.maximum(np.diag(cov), 0.0))]

    pred, meas, upd = holder.prediction, holder.measurement, holder.update
    return FilterDiagnostics(
        active=True,
        mode=plan.mode,
        handleNames=list(FILTER_HANDLES),
        provenance=holder.state.provenance,
        resetReason=holder.state.reset_reason,
        contaminated=meas.contaminated,
        transportDistance=pred.transport_distance,
        prediction=[float(v) for v in pred.mean],
        predictionStd=_std(pred.cov),
        observation=[float(v) for v in meas.handles],
        observationStd=_std(meas.cov),
        innovation=[float(v) for v in upd.innovation],
        gain=[float(v) for v in np.diag(upd.gain)],
        posterior=[float(v) for v in upd.mean],
        posteriorStd=_std(upd.cov),
        measurementBreakdown={k: float(v) for k, v in meas.breakdown.items()},
        processBreakdown={
            k: [float(x) for x in v] for k, v in pred.q_breakdown.items()
        },
    )


def reset_node(state: AppState, ticker: str, iso: str, fit_mode: str) -> None:
    """Drop one node's filter state (e.g. after a destructive edit) so the next
    commit reseeds from the prior."""
    holder = state.filter_node((ticker, iso, fit_mode))
    if holder is not None:
        state.set_filter_node(
            (ticker, iso, fit_mode), replace(holder, session_version=-1)
        )
