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
    adaptive_inflation,
    build_filter_prior,
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
from volfit.models.lqd.calibrate import OPT_N_POINTS
from volfit.models.lqd.quadrature import build_slice

#: v1 runs the update DIAGONALLY — per-handle scalar gains, the Note 14 graph
#: convention ("production runs handle-by-handle"). Measured reason (Phase-5
#: backtest, EEM/EFA spike day): the Jacobian R carries strong level-curvature
#: correlations, and on a coarse-strike chain a junk curvature innovation then
#: drags the ATM level through the OFF-DIAGONAL gain terms — posterior errors
#: of 3-28 vol points, worse than BOTH baselines (impossible for scalar
#: updates; filterMaxGain caps own-gains only, so it cannot prevent this).
#: The full-covariance update stays available for later study.
DIAGONAL_UPDATE = True


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
    #: Memoized overlay curves (post, band_lo, band_hi, pred) — the retarget
    #: Newton solves are expensive and the live UI polls the payload per
    #: refresh signal, so they are computed once per committed state, not per
    #: GET (measured live: per-GET retargets made the app feel frozen).
    curves: tuple | None = None


def _backbone_handles(result, tau: float) -> np.ndarray:
    """The LQD backbone's exact ATM handles (the filter's measurement carrier)."""
    h = atm_handles(result.slice, tau)
    return np.array([h.sigma0, h.skew, h.curvature])


#: Short-dated noise reference (FINDINGS F3): below ~30 DTE the thinned-vs-full
#: ATM discrepancy runs 2-3x the stated half-spread (short-end quote/de-Am
#: noise, the LV short-dated diagnosis), so the stated noise is scaled by
#: sqrt(REF/DTE) — ~1.4x at 15 DTE, ~2x at 7 DTE, never below 1.
SHORT_DATED_REF_DAYS = 30.0


def _maturity_noise_mult(tau: float) -> float:
    days = max(float(tau) * 365.0, 1.0)
    return max(1.0, float(np.sqrt(SHORT_DATED_REF_DAYS / days)))


def _noise_from_band(band, n_quotes: int, n_fit_rows: int, tau: float):
    """Per-row stated noise std = the bid-ask half-spread, floored at RMS_FLOOR
    and scaled by the short-dated multiplier (F3).

    ``band`` is the edited BID-ASK band (built regardless of the fit mode — the
    spread is the market's stated uncertainty even for a mid fit). Band-mode
    fits have 2 rows per quote (hinge + anchor), so the vector is tiled."""
    mult = _maturity_noise_mult(tau)
    if band is None:
        return mult * 10.0 * RMS_FLOOR  # no band info: assume a 10 bp noise scalar
    half = mult * np.maximum(
        (np.asarray(band.iv_hi) - np.asarray(band.iv_lo)) / 2.0, RMS_FLOOR
    )
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
            # the coarse opt-grid slice: plenty for a covariance derivative,
            # ~4x cheaper than the full display quadrature (14 builds per node)
            slice_ = build_slice(LQDParams.from_vector(theta), n_points=OPT_N_POINTS)
            h = atm_handles(slice_, prepared.tau)
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
                band, solver_diag["n_quotes"], solver_diag["n_fit_rows"],
                prepared.tau,
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


def _typical_noise(state: AppState, ticker: str, iso: str, prepared) -> float:
    """The node's typical stated per-quote noise (median bid-ask half-spread,
    floored) — the s_q that expresses the MAP prior in the fit's weighting
    convention AND unwhitens the posterior information (one consistent value
    for both, or the MAP algebra breaks)."""
    from volfit.api import service

    band = service.edited_band(state, ticker, iso, prepared, "bidask")
    mult = _maturity_noise_mult(prepared.tau)
    if band is None:
        return mult * 10.0 * RMS_FLOOR
    half = np.maximum(
        (np.asarray(band.iv_hi) - np.asarray(band.iv_lo)) / 2.0, RMS_FLOOR
    )
    return mult * float(np.median(half)) if half.size else mult * 10.0 * RMS_FLOOR


def _prediction_from(
    state: AppState, prev: "NodeFilter", f_now: float, ts_now: float
) -> tuple[FilterPrediction, float]:
    """The transported prediction law (m^-, P^-) from a previous holder —
    shared by the overlay update and the active-MAP prior so both anchor to
    the SAME prediction."""
    opts = state.options()
    h = (
        float(np.log(f_now / prev.forward))
        if prev.forward > 0.0 and f_now > 0.0
        else 0.0
    )
    ssr = ssr_of_regime(state.dynamics_regime())
    base_mean = transport_handles(prev.state.mean, h, ssr)
    dt_days = max(ts_now - prev.state.timestamp, 0.0) / 86400.0
    q_diag, q_breakdown = process_noise(
        dt_days,
        h,
        vol_bp_sqrt_day=opts.filterProcessVolBpSqrtDay,
        skew_sqrt_day=opts.filterProcessSkewSqrtDay,
        curv_sqrt_day=opts.filterProcessCurvSqrtDay,
        transport_scale=opts.filterTransportNoiseScale,
    )
    return predict(base_mean, prev.state.cov, q_diag, abs(h), q_breakdown), h


def active_prediction_target(
    state: AppState, ticker: str, iso: str, fit_mode: str, prepared
):
    """The Kalman prediction prior for the ACTIVE one-stage MAP fit (note eq.
    active-map), or None — mode not active, no previous state, or a reset is
    due (the fit then runs data-only and the commit reseeds). Consumed by
    ``service.prior_targets`` as the operator block, so it reaches every
    parametric model with no new wiring."""
    plan = resolve_filter_mode(state.options())
    if not plan.active:
        return None
    prev: NodeFilter | None = state.filter_node((ticker, iso, fit_mode))
    if prev is None:
        return None
    from volfit.api import service

    ts_now = float(state.snapshot(ticker).timestamp.timestamp())
    dt_hours = max(ts_now - prev.state.timestamp, 0.0) / 3600.0
    sv = service.session_version(state, ticker, iso)
    if should_reset(
        dt_hours,
        state.options().filterResetHours,
        quotes_edited=prev.session_version != sv,
    ):
        return None
    pred, _h = _prediction_from(state, prev, float(prepared.forward), ts_now)
    return build_filter_prior(
        pred.mean,
        np.diag(pred.cov),
        prepared.tau,
        quote_noise=_typical_noise(state, ticker, iso, prepared),
    )


def _seed(
    state: AppState, ticker: str, iso: str, key: tuple, ts: float, reason: str,
    record,
) -> FilterState:
    """(Re)seed the filter state (note §6.3: persistence 'may provide the
    initial saved prior from which the first filtered state is seeded').

    With a saved prior snapshot: the transported prior via the provenance
    hierarchy (bootstrap DISABLED — its fit_or_get(mid) branch silently runs a
    FULL extra mid calibration per node, which made switching the filter on
    crawl on a live universe). Without one: the committed fit's own backbone
    handles at bootstrap-tier precision — the same information the bootstrap
    branch would have fetched, for free."""
    if state.active_prior(ticker) is not None:
        prior = resolve_node_prior(state, ticker, iso, allow_bootstrap=False)
        if prior.source in ("active_transported", "nearest_expiry_transported"):
            cov = np.diag(
                1.0 / np.maximum(np.asarray(prior.precision, dtype=float), 1e-12)
            )
            return FilterState(
                node_key=key,
                handle_names=FILTER_HANDLES,
                mean=np.asarray(prior.handles, dtype=float),
                cov=cov,
                timestamp=ts,
                provenance=f"seed:{prior.source}",
                reset_reason=reason,
            )
    from volfit.api.graph_nodes import PRIOR_SOURCE_PRECISION_SCALE
    from volfit.api.graph_service import GRAPH_PRECISION

    precision = GRAPH_PRECISION * PRIOR_SOURCE_PRECISION_SCALE["today_bootstrap"]
    return FilterState(
        node_key=key,
        handle_names=FILTER_HANDLES,
        mean=_backbone_handles(record.result, record.prepared.tau),
        cov=np.diag(1.0 / np.maximum(precision, 1e-12)),
        timestamp=ts,
        provenance="seed:today_fit",
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
        # A (re)seed: the prior machinery already transported to the current
        # forward, so the prediction is the seed law itself (dt = 0, h = 0).
        seeded = _seed(state, ticker, iso, key, ts_now, reason, record)
        q_diag, q_breakdown = process_noise(
            0.0, 0.0,
            vol_bp_sqrt_day=opts.filterProcessVolBpSqrtDay,
            skew_sqrt_day=opts.filterProcessSkewSqrtDay,
            curv_sqrt_day=opts.filterProcessCurvSqrtDay,
            transport_scale=opts.filterTransportNoiseScale,
        )
        prediction = predict(seeded.mean, seeded.cov, q_diag, 0.0, q_breakdown)
        provenance = seeded.provenance
    else:
        prediction, _h = _prediction_from(state, prev, f_now, ts_now)
        provenance = "update"

    if plan.active and reason is None:
        # One-stage MAP (note eq. active-map): the committed fit already
        # carried the prediction prior as residual rows — applying a second
        # Kalman update against the same quotes would double-count them.
        holder = _map_bookkeeping(
            state, ticker, iso, key, record, solver_diag, prediction,
            ts_now, f_now, dv, sv,
        )
        if holder is None:
            return prev  # no solver Jacobian retained (cached path): keep state
        state.set_filter_node(key, holder)
        return holder

    measurement = _measurement(state, ticker, iso, record, solver_diag)
    if reason is None and opts.filterAdaptiveSigma > 0.0:
        # Innovation-gated Q widening (FINDINGS F4): a genuine large move
        # reads as ~gate sigmas instead of lagging; seeds are excluded (their
        # innovation is not a prediction surprise).
        factors = adaptive_inflation(
            measurement.handles - prediction.mean,
            np.diag(prediction.cov),
            np.diag(measurement.cov),
            opts.filterAdaptiveSigma,
        )
        if np.any(factors > 1.0):
            scale = np.sqrt(factors)
            prediction = replace(
                prediction,
                cov=prediction.cov * np.outer(scale, scale),
                q_breakdown={
                    **prediction.q_breakdown,
                    "adaptive": (factors - 1.0) * np.diag(prediction.cov),
                },
            )
    pred_cov, meas_cov = prediction.cov, measurement.cov
    if DIAGONAL_UPDATE:  # per-handle scalar gains (see the constant's docstring)
        pred_cov = np.diag(np.diag(pred_cov))
        meas_cov = np.diag(np.diag(meas_cov))
    upd = kalman_update(
        prediction.mean,
        pred_cov,
        measurement.handles,
        meas_cov,
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


def _map_bookkeeping(
    state: AppState, ticker: str, iso: str, key: tuple, record,
    solver_diag: dict | None, prediction: FilterPrediction,
    ts_now: float, f_now: float, dv: int, sv: int,
) -> NodeFilter | None:
    """Active-mode posterior bookkeeping (note eq. active-map).

    The committed fit IS the one-stage MAP solution, so ``m+`` is simply its
    backbone handles. ``P+`` comes from the FULL solver information: the
    retained Jacobian contains the data rows PLUS the whitened prediction-
    prior rows (weighted s_q^2/P^- in the fit's convention), and unwhitening
    ALL rows by the same s_q lands the information at data/s_q^2 + (P^-)^{-1}
    — exactly the posterior information (Prop. nodouble). The reported "gain"
    is the implied per-handle information ratio 1 - P+/P-. Returns None when
    no solver Jacobian was retained (a cached fit): the caller keeps the
    previous state rather than double-updating."""
    if not solver_diag or "jac" not in solver_diag:
        return None
    prepared = record.prepared
    noise = _typical_noise(state, ticker, iso, prepared)

    def handle_fn(theta):
        # coarse opt-grid slice — a covariance derivative, not a display curve
        slice_ = build_slice(LQDParams.from_vector(theta), n_points=OPT_N_POINTS)
        h = atm_handles(slice_, prepared.tau)
        return np.array([h.sigma0, h.skew, h.curvature])

    g = handle_jacobian_fd(handle_fn, solver_diag["theta"])
    z = _backbone_handles(record.result, prepared.tau)
    meas = measurement_from_jacobian(
        z,
        solver_diag["jac"],
        g,
        solver_diag["residual"],
        solver_diag["n_fit_rows"],
        solver_diag["n_quotes"],
        noise_scale=noise,
        scale_rows=int(np.asarray(solver_diag["residual"]).size),
        inflate=state.options().filterResidualInflation,
    )
    meas.breakdown["map"] = 1.0
    p_pred = np.maximum(np.diag(prediction.cov), 1e-18)
    p_post = np.maximum(np.diag(meas.cov), 1e-18)
    # A posterior can never be LESS certain than its prediction: information
    # only adds, and inconsistent data (rho > 1) should drive P+ toward P-,
    # not beyond it. Cap per handle, rescaling rows/cols so correlations
    # survive (the rho inflation + FD-stencil approximation can otherwise
    # push the unwhitened information slightly past the prior).
    capped = np.minimum(p_post, p_pred)
    scale = np.sqrt(capped / p_post)
    cov_post = meas.cov * np.outer(scale, scale)
    np.fill_diagonal(cov_post, capped)
    gain = np.clip(1.0 - capped / p_pred, 0.0, 1.0)
    upd = FilterUpdate(
        innovation=z - prediction.mean,  # the realized state move m+ - m-
        innovation_cov=np.diag(p_pred),  # display-only approximation
        gain=np.diag(gain),
        mean=z,
        cov=cov_post,
    )
    new_state = FilterState(
        node_key=key, handle_names=FILTER_HANDLES, mean=z, cov=cov_post,
        timestamp=ts_now, provenance="map", reset_reason=None,
    )
    return NodeFilter(
        state=new_state, prediction=prediction, measurement=meas, update=upd,
        data_version=dv, session_version=sv, forward=f_now,
    )


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
    if holder.curves is None:  # once per committed state, not per GET
        holder.curves = _overlay_curves(state, ticker, iso, fit_mode, holder)
    post, band_lo, band_hi, pred_curve = holder.curves
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
        post=post,
        postBandLo=band_lo,
        postBandHi=band_hi,
        predCurve=pred_curve,
    )


def _overlay_curves(state, ticker: str, iso: str, fit_mode: str, holder: NodeFilter):
    """Drawable overlay: the node's LQD backbone retargeted to the posterior m+
    (exact handles, arb-free — the graph_reconstruct seam), a level credible
    band at m+ ± 1.96 sd(ATM), and the transported prediction m-. Empty lists
    on any failure (the payload is advisory)."""
    from volfit.api import service
    from volfit.models.lqd.ortho import build_atm_coordinates
    from volfit.models.lqd.quadrature import build_slice as _build

    empty: list = []
    try:
        record = service.fit_or_get(state, ticker, iso, fit_mode)
        if record is None:
            return empty, empty, empty, empty
        tau = float(record.prepared.tau)
        chart = build_atm_coordinates(record.result.params, tau)
        grid = np.linspace(service.K_DISPLAY_LO, service.K_DISPLAY_HI, service.N_MODEL_POINTS)

        def _curve(handles):
            target = np.array(
                [handles[0] * handles[0] * tau, handles[1], handles[2]]
            )
            try:
                slice_ = _build(chart.retarget(target))
            except RuntimeError:  # Newton failure at extreme handles
                return empty
            w = np.maximum(np.asarray(slice_.implied_w(grid), dtype=float), 0.0)
            vols = service.fill_nonfinite(np.sqrt(w / tau))
            from volfit.api.schemas import SmilePoint

            return [SmilePoint(k=float(k), vol=float(v)) for k, v in zip(grid, vols)]

        m_post = holder.state.mean
        sd_atm = float(np.sqrt(max(holder.state.cov[0, 0], 0.0)))
        lo = np.array([max(m_post[0] - 1.96 * sd_atm, 1e-4), m_post[1], m_post[2]])
        hi = np.array([m_post[0] + 1.96 * sd_atm, m_post[1], m_post[2]])
        pred_c = _curve(holder.prediction.mean) if holder.prediction is not None else empty
        return _curve(m_post), _curve(lo), _curve(hi), pred_c
    except Exception:  # noqa: BLE001 — advisory payload, never raises
        return empty, empty, empty, empty


def reset_node(state: AppState, ticker: str, iso: str, fit_mode: str) -> None:
    """Drop one node's filter state (e.g. after a destructive edit) so the next
    commit reseeds from the prior."""
    holder = state.filter_node((ticker, iso, fit_mode))
    if holder is not None:
        state.set_filter_node(
            (ticker, iso, fit_mode), replace(holder, session_version=-1)
        )
