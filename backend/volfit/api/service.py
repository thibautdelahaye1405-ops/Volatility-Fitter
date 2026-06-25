"""Pure service functions behind the volfit API routes (ROADMAP Phase 5).

Each function takes the AppState explicitly and returns pydantic response
models, so routers stay thin and everything here is testable without HTTP. The
surface fit is decomposed into `surface_inputs` + `fit_surface_slice` (the loop
body of volfit.calib.calibrate_surface) so the WebSocket route can emit progress
between expiries. Quote-edit sessions plug in at two seams: fit-cache keys carry
the session version and inputs are rewritten by `edited_fit_inputs`; edit/undo/
redo entry points live in volfit.api.edits.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date

import numpy as np

from volfit.api import history
from volfit.api.fit_models import DisplayFit, _max_iv_error, build_display_fit
from volfit.api.quotes import (
    PreparedQuotes,
    apply_band_edits,
    apply_edits,
    prepare_quotes,
)
from volfit.api.schemas import (
    ModelInfo,
    ModelParam,
    QuoteBand,
    ScenarioRequest,
    ScenarioResponse,
    SmileData,
    SmileDiagnostics,
    SmilePoint,
    SurfaceFitResponse,
    VarSwapInfo,
)
from volfit.api.displayed import (
    displayed_atm_vol,
    displayed_skew,
    displayed_slice,
    displayed_var_swap_w,
)
from volfit.api.state import AppState, FitRecord
from volfit.calib.calendar import (
    calendar_floor_targets,
    calendar_violation,
    variance_floor_grid_from,
    variance_floor_targets,
)
from volfit.api.prior_mode import resolve_prior_mode
from volfit.calib.factors import build_factor_prior
from volfit.calib.operators import (
    OperatorPriorTarget,
    build_operator_prior,
    hybrid_tail_deltas,
)
from volfit.calib.prior import PriorAnchorTarget, build_prior_anchor
from volfit.calib.rms import node_error_terms, rms as rms_of_terms
from volfit.calib.varswap import VarSwapTarget, varswap_total_variance
from volfit.calib.weighted_time import weighted_variance_years
from volfit.calib.weights import resolve_weights
from volfit.data.forwards import ResolvedForward
from volfit.dynamics.ssr import Regime, shifted_smile, ssr_of_regime
from volfit.dynamics.transport import TransportedSlice
from volfit.models.diagnostics import (
    numeric_handles,
    numeric_lee_slopes,
    numeric_var_swap_w,
)
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.basis import endpoint_scales, lee_slopes
from volfit.models.lqd.calibrate import CalibrationResult, calibrate_slice

#: Model-curve sampling: points over the extended (≥[-1,1]) display grid; denser
#: than before to keep ATM resolution across the wider range. K_PAD pads the
#: OBSERVED range used for the brush extent / default window.
N_MODEL_POINTS = 241
K_PAD = 0.02

#: Minimum log-moneyness display range every drawn curve/mesh is extended to
#: (beyond the observed quotes): asymmetric — the downside put wing reaches
#: further (-1.4) than the call wing (+1.0), matching where traders want to see
#: skew. Shared by the smile model curve and the 3D surface / Stacked-IV mesh.
K_DISPLAY_LO = -1.4
K_DISPLAY_HI = 1.0

#: High-order Legendre damping defaults (lam * n^{2r} a_n^2); short-dated slices
#: left with ~as few quotes as params after the wing filter interpolate with
#: wild ATM handles unregularized. Now the defaults of schemas.FitSettings (the
#: hyperparameter panel PUT /settings/fit overrides them per AppState).
REG_LAMBDA = 1e-6
REG_POWER = 1.0

#: Friendly model names for the engine-activity narration (status bar).
_MODEL_LABELS = {"lqd": "LQD", "svi": "SVI-JW", "sigmoid": "Multi-Core SIV"}


def _model_label(model_id: str) -> str:
    return _MODEL_LABELS.get(model_id, model_id.upper())


# --------------------------------------------------------- fit-session edits
def session_version(state: AppState, ticker: str, iso: str) -> int:
    """Current quote-edit session version of a node, 0 when none exists."""
    session = state.session_if_exists((ticker, iso))
    return 0 if session is None else session.version


def varswap_version(state: AppState, ticker: str, iso: str) -> int:
    """Current var-swap quote session version of a node, 0 when none exists."""
    session = state.varswap_session_if_exists((ticker, iso))
    return 0 if session is None else session.version


def fit_key(state: AppState, ticker: str, iso: str, fit_mode: str) -> tuple:
    """Fit-cache key: (ticker, canonical ISO, mode, session version, var-swap
    version, events version, settings version, forwards version, options version)
    — quote edits, var-swap edits, event-calendar edits, hyperparameter,
    forward/market and calendar/var-swap-penalty/event-clock changes each bump a
    version, so affected nodes refit without eviction."""
    return (
        ticker,
        iso,
        fit_mode,
        session_version(state, ticker, iso),
        varswap_version(state, ticker, iso),
        state.events_version(ticker),
        state.settings_version,
        state.forwards_version(ticker),
        state.options_version,
        state.data_version(ticker),  # fresh options fetch -> stale / refit
        state.active_prior_version(ticker),  # a fetched prior re-anchors the fit
    )


def variance_time(state: AppState, ticker: str, expiry, t_cal: float) -> float:
    """Event-weighted variance years for a node (volfit.calib.weighted_time).

    The smile is calibrated/quoted in this clock so an event before the expiry
    lowers every reported vol at fixed price. Reduces to the calendar ``t_cal``
    when the event clock is off (OptionsSettings.eventsEnabled) or the ticker has
    no events. ``expiry`` is accepted for symmetry/future use; the clock depends
    only on the calendar maturity and the ticker's shared event calendar."""
    options = state.options()
    if not options.eventsEnabled:
        return t_cal
    events = state.events(ticker)
    if not events:
        return t_cal
    pairs = [(e.time, e.weight) for e in events]
    return weighted_variance_years(t_cal, pairs, normalize=options.normalizeEvents)


def _cash_digest(cash_divs: tuple | None) -> tuple | None:
    """Stable, hashable digest of a (ex_times, scaled_amounts, rate) schedule.

    Rounds the floats to remove resolution jitter so an unchanged schedule keys
    identically across calls; ``None`` (continuous-yield de-Am) digests to None."""
    if cash_divs is None:
        return None
    times, amounts, rate = cash_divs
    return (
        tuple(np.round(np.asarray(times, dtype=float), 9)),
        tuple(np.round(np.asarray(amounts, dtype=float), 9)),
        round(float(rate), 12),
    )


def _prepared_key(
    state: AppState,
    ticker: str,
    iso: str,
    forward: ResolvedForward,
    cash_divs: tuple | None,
    t_cal: float,
    tau: float,
) -> tuple:
    """Content-digest cache key for a node's PreparedQuotes (note Stage 2).

    De-Americanized, inverted quotes depend ONLY on the raw chain snapshot, the
    resolved forward/discount, the maturity / variance clock and the dividend
    schedule — never on quote/var-swap/prior edits, the band or the fit_mode
    (those enter later, in ``edited_fit_inputs`` / ``edited_band`` / the model
    fit). The earlier key carried the broad global version counters
    (``settings``/``options``/``forwards``/``events``), which over-invalidated:
    every LV-hyperparameter tweak re-ran the (seconds-long) de-Am, and the global
    ``forwards_version`` let one ticker's forward edit bust another ticker's
    prepared quotes. We instead fold in the actual RESOLVED inputs the prep
    consumes — so a change re-keys iff it really changes a de-Am input, and the
    key is naturally ticker-scoped:

      - ``data_version``  : raw chain identity (bumped on fetch / chain invalidate)
      - forward, discount : the resolved forward (absorbs forward policy/manual)
      - cash schedule     : discrete-dividend de-Am inputs (absorbs div model/rate)
      - t_cal             : calendar maturity (drives de-Am carry + discounting)
      - tau               : variance clock (absorbs eventsEnabled/normalize/calendar)
      - reference_date    : as-of (belt-and-braces; an as-of switch also re-keys)

    The resolution cost (forward/schedule/tau) is microseconds against the
    seconds of de-Am it gates, so computing it on every call — including hits —
    is a clear win."""
    return (
        ticker,
        iso,
        state.data_version(ticker),
        round(float(forward.forward), 9),
        round(float(forward.discount), 12),
        _cash_digest(cash_divs),
        round(float(t_cal), 12),
        round(float(tau), 12),
        state.reference_date.toordinal(),
    )


def prepared_quotes(state: AppState, ticker: str, expiry: date) -> PreparedQuotes:
    """PreparedQuotes for a node, memoized on a content-digest cache.

    De-Americanization (the per-quote binomial inversion of an American chain) is
    the cost on this path. The same node's quotes are re-derived by many views in
    one refresh fan-out and by every pre-Calibrate display poll of a gated node;
    this caches the result so the de-Am runs once per genuine input change. The
    caller must have ensured the chain (``ensure_chain`` / ``has_quotes``).

    The de-Am inputs are resolved FIRST (forward, cash schedule, clocks) so they
    can be digested into the key — they are cheap to resolve and are exactly what
    ``prepare_quotes`` needs on a miss, so nothing is computed twice."""
    forward = state.resolved_forward(ticker, expiry)  # honours the forward policy
    cash_divs = state.cash_dividend_schedule(ticker, expiry, forward.forward)
    t_cal = state.year_fraction(expiry)
    tau = variance_time(state, ticker, expiry, t_cal)
    key = _prepared_key(state, ticker, expiry.isoformat(), forward, cash_divs, t_cal, tau)
    cached = state.get_prepared(key)
    if cached is not None:
        return cached
    snapshot = state.snapshot(ticker)
    prepared = prepare_quotes(snapshot, expiry, forward, t_cal, cash_divs, tau=tau)
    state.store_prepared(key, prepared)
    return prepared


def varswap_target(
    state: AppState, ticker: str, iso: str, k: np.ndarray, weights: np.ndarray | None, t: float
) -> VarSwapTarget | None:
    """The var-swap penalty target for a node, or None.

    Active only when the feature is enabled (OptionsSettings.varSwapEnabled) and
    the node has an active (non-excluded) var-swap quote. The penalty weight is
    ``varSwapWeightPct`` percent of the summed option-quote weights of the node,
    so the var-swap competes with the option quotes at the chosen relative
    strength regardless of how many quotes the node has."""
    options = state.options()
    if not options.varSwapEnabled:
        return None
    session = state.varswap_session_if_exists((ticker, iso))
    if session is None or not session.state.is_active:
        return None
    sum_w = float(np.sum(weights)) if weights is not None else float(k.size)
    weight = (options.varSwapWeightPct / 100.0) * sum_w
    level = float(session.state.level)
    return VarSwapTarget(total_var=level * level * t, weight=weight, t=t)


@dataclass(frozen=True)
class PriorTargets:
    """Resolved prior-persistence targets for one slice fit, routed by mode.

    At most one of ``prior_anchor`` (strike-gap mode) / ``operator_prior``
    (operator & hybrid modes) is set; ``prior_var_swap`` is the companion var-swap
    level for whichever is active. All None ⇒ no prior penalty (off / overlay /
    graph_only / smile_factor[until Phase 6], or no active prior) ⇒ byte-identical."""

    prior_anchor: PriorAnchorTarget | None = None
    operator_prior: OperatorPriorTarget | None = None
    prior_var_swap: VarSwapTarget | None = None


def prior_targets(
    state: AppState, ticker: str, iso: str, k: np.ndarray, weights: np.ndarray | None, prepared
) -> PriorTargets:
    """Resolve the active prior-persistence targets for a node (design note §10).

    Routed by ``OptionsSettings.priorPersistenceMode`` (volfit.api.prior_mode):
    ``strike_gap`` builds the legacy data-gap strike anchor (volfit.calib.prior);
    ``quote_operator`` / ``hybrid`` build the signed quote-operator prior
    (volfit.calib.operators) — the SAME object every parametric model and the LV
    surface consume. ``off`` / ``overlay`` / ``graph_only`` (and ``smile_factor``
    until Phase 6) add no calibration penalty.

    Gated by ``autoLoadPrior`` (the transition master enable; Phase 8 retires it in
    favour of the mode) AND an active, fetched prior — either off ⇒ empty targets ⇒
    byte-identical. The prior's LQD backbone is transported to the node's forward
    under the dynamics regime so it is spot-consistent with the live quotes."""
    options = state.options()
    plan = resolve_prior_mode(options)
    if not options.autoLoadPrior or not plan.any_calibration_prior:
        return PriorTargets()
    from volfit.api import prior_transport

    node = prior_transport.prior_node(state.active_prior(ticker), iso)
    if node is None:
        return PriorTargets()
    moved = prior_transport.transported_prior_slice(
        node, float(prepared.forward), state.dynamics_regime()
    )
    sum_w = float(np.sum(weights)) if weights is not None else float(k.size)

    if plan.strike_anchor:
        budget = (options.priorAnchorWeightPct / 100.0) * sum_w
        anchor, unmet = build_prior_anchor(
            moved.implied_w, node.tau, k, prepared.tau, budget,
            scheme=state.fit_settings().weightScheme,
            deltas=tuple(options.priorAnchorDeltas),
        )
        pvs: VarSwapTarget | None = None
        if budget > 0.0 and unmet > 0.0:
            # Prior's fair var-swap (model-free replication on the transported curve),
            # re-expressed at the current variance time; weight fades with coverage.
            w_vs = varswap_total_variance(moved.implied_w) * (prepared.tau / node.tau)
            pvs = VarSwapTarget(total_var=float(w_vs), weight=budget * unmet, t=float(prepared.tau))
        return PriorTargets(prior_anchor=anchor, prior_var_swap=pvs)

    if plan.factors:
        # smile_factor: ATM-local level/skew/curvature distance to the prior (§6).
        budget = (options.priorFactorStrengthPct / 100.0) * sum_w
        target, vs = build_factor_prior(
            moved.implied_w, node.tau, prepared.tau, k, weights, budget,
            factor_set=list(options.priorFactorSet),
            step=options.priorOperatorBandwidth,
            required_precision=options.priorOperatorRequiredPrecision,
            gap_exponent=options.priorOperatorGapExponent,
            bandwidth=options.priorOperatorBandwidth,
        )
        pvs = None
        if vs.active and vs.weight > 0.0:
            pvs = VarSwapTarget(total_var=vs.prior_total_var, weight=vs.weight, t=float(prepared.tau))
        return PriorTargets(operator_prior=target, prior_var_swap=pvs)

    # operator / hybrid: the signed quote-operator prior (ATM/RR/BF; design note §5).
    budget = (options.priorOperatorStrengthPct / 100.0) * sum_w
    target, vs = build_operator_prior(
        moved.implied_w, node.tau, prepared.tau, k, weights, budget,
        op_set=list(options.priorOperatorSet),
        collar_sign=options.collarSign,
        required_precision=options.priorOperatorRequiredPrecision,
        gap_exponent=options.priorOperatorGapExponent,
        bandwidth=options.priorOperatorBandwidth,
    )
    pvs = None
    if vs.active and vs.weight > 0.0:
        pvs = VarSwapTarget(total_var=vs.prior_total_var, weight=vs.weight, t=float(prepared.tau))
    anchor = None
    if plan.tail_anchor:
        # hybrid (design note §7): a residual deep-tail strike anchor only where no
        # operator/quote reaches (the deltas below the shallowest wing operator).
        tail_deltas = hybrid_tail_deltas(options.priorOperatorSet, options.priorAnchorDeltas)
        tail_budget = (options.priorTailAnchorStrengthPct / 100.0) * sum_w
        if tail_budget > 0.0:
            anchor, _unmet = build_prior_anchor(
                moved.implied_w, node.tau, k, prepared.tau, tail_budget,
                scheme=state.fit_settings().weightScheme, deltas=tail_deltas,
            )
    return PriorTargets(prior_anchor=anchor, operator_prior=target, prior_var_swap=pvs)


def edited_fit_inputs(
    state: AppState, ticker: str, iso: str, prepared: PreparedQuotes, weights: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Calibration inputs after edits: excluded strikes masked, amended mids
    re-leveled to w = mid_iv^2 t (quotes.apply_edits)."""
    session = state.session_if_exists((ticker, iso))
    return apply_edits(prepared, {} if session is None else session.edits, weights)


def edited_band(
    state: AppState, ticker: str, iso: str, prepared: PreparedQuotes, fit_mode: str
):
    """Band target after quote edits (None for "mid"); aligned with
    edited_fit_inputs. Haircut comes from fit settings (refits via version)."""
    session = state.session_if_exists((ticker, iso))
    edits = {} if session is None else session.edits
    return apply_band_edits(prepared, edits, fit_mode, state.fit_settings().haircut)


def display_overlay(
    state: AppState,
    ticker: str,
    iso: str,
    prepared: PreparedQuotes,
    fit_mode: str,
    prev_display: DisplayFit | None = None,
    enforce_calendar: bool = False,
):
    """The non-LQD display overlay for a node (None for LQD), fit to the same
    edited quotes, band and weights the LQD calibration uses.

    ``prev_display`` is the previous (shorter-T) expiry's overlay, threaded by the
    calendar-coupled surface loop; with ``enforce_calendar`` it supplies a
    model-agnostic total-variance floor (volfit.calib.calendar) so the SVI /
    sigmoid overlay respects calendar order just as the LQD backbone does. Both
    omitted (the single-node path) leaves the overlay byte-identical."""
    settings = state.fit_settings()
    if settings.model == "lqd":
        return None
    k, w, _ = edited_fit_inputs(state, ticker, iso, prepared, None)
    weights = resolve_weights(settings.weightScheme, k, w)
    band = edited_band(state, ticker, iso, prepared, fit_mode)
    vs = varswap_target(state, ticker, iso, k, weights, prepared.tau)
    pt = prior_targets(state, ticker, iso, k, weights, prepared)
    cal_floor = None
    if enforce_calendar and prev_display is not None:
        # Confine the floor to THIS expiry's traded log-moneyness range: outside
        # the quotes both slices are pure extrapolation and an SVI wing mismatch
        # there is a phantom violation, not real calendar arb.
        cal_floor = variance_floor_targets(prev_display.slice, variance_floor_grid_from(k))
    return build_display_fit(
        settings.model, k, w, prepared.tau, weights, settings, band=band, var_swap=vs,
        calendar_floor=cal_floor, calendar_weight=state.options().calendarWeight,
        prior_anchor=pt.prior_anchor, operator_prior=pt.operator_prior,
        prior_var_swap=pt.prior_var_swap,
    )


# ------------------------------------------------------------- slice fitting
def _compute_fit(
    state: AppState, ticker: str, expiry_iso: str, fit_mode: str, init=None
) -> FitRecord:
    """Calibrate one slice and mark the node CALIBRATED at the current key/spot.

    ``init`` is an optional LQD warm-start (the previous, shorter-T expiry's params
    during a surface fan-out). It is left None on the single-node display / undo /
    explicit-Calibrate path so that path stays cold-started and therefore
    path-INDEPENDENT (an undo back to a prior edit state reproduces the original fit
    bit-for-bit); the seed only enters the deterministic surface sweep.

    The anchor a spot move is transported from. Cached in ``_fits`` by the full
    fit key; the calibrated pointer (``set_calibrated_ptr``) records that this key
    is the displayed one, so a later input change goes *stale* (frozen) under
    autoCalibrate OFF until the next explicit Calibrate re-points here."""
    expiry = state.resolve_expiry(ticker, expiry_iso)
    iso = expiry.isoformat()  # canonical ISO cache/session key
    key = fit_key(state, ticker, iso, fit_mode)
    snapshot = state.ensure_chain(ticker)  # Calibrate auto-fetches the chain if absent
    cached = state.get_fit(key)
    if cached is not None:
        state.set_calibrated_ptr(ticker, iso, fit_mode, key, float(snapshot.spot))
        return cached

    settings = state.fit_settings()
    # Narrate this node's calibration to the bottom status bar (coarse boundary
    # only — the scipy inner loop is never touched).
    activity = state.activity.activity(
        "calibrate", f"Calibrating {ticker} {iso} ({_model_label(settings.model)})"
    )
    with activity as act:
        if snapshot.exercise_style == "american" and state.year_fraction(expiry) > 0.0:
            act.detail("de-americanizing quotes")
        prepared = prepared_quotes(state, ticker, expiry)  # de-Am memoized per node
        k, w, _ = edited_fit_inputs(state, ticker, iso, prepared, None)
        weights = resolve_weights(settings.weightScheme, k, w)
        band = edited_band(state, ticker, iso, prepared, fit_mode)
        vs = varswap_target(state, ticker, iso, k, weights, prepared.tau)
        pt = prior_targets(state, ticker, iso, k, weights, prepared)
        # Two-pass "don't damp the signal" (opt-in, design note §5.4): fit data-only
        # first so the data-fitted level/shape is the seed, then refit with the gated
        # prior initialized from it. Single-node path only (init is None); the
        # warm-started surface sweep keeps its previous-expiry seed.
        seed = init
        if (
            state.options().priorDataOnlyPrepass
            and init is None
            and (pt.operator_prior is not None or pt.prior_anchor is not None)
        ):
            act.detail("data-only prepass")
            seed = calibrate_slice(
                k, w, t=prepared.tau, n_order=settings.nOrder, weights=weights,
                reg_lambda=settings.regLambda, reg_power=settings.regPower,
                band=band, barrier_center=settings.barrierCenter,
                barrier_scale=settings.barrierScale, mid_anchor_weight=settings.midAnchorWeight,
                var_swap=vs,
            ).params
        act.detail(f"fitting {_model_label(settings.model)} smile")
        result = calibrate_slice(
            k,
            w,
            t=prepared.tau,
            n_order=settings.nOrder,
            weights=weights,
            reg_lambda=settings.regLambda,
            reg_power=settings.regPower,
            # Warm start only when handed a same-order seed (the surface sweep's
            # previous expiry, or the two-pass data-only fit); a mismatched order
            # would be the wrong vector length.
            init=seed if getattr(seed, "order", None) == settings.nOrder else None,
            band=band,
            barrier_center=settings.barrierCenter,
            barrier_scale=settings.barrierScale,
            mid_anchor_weight=settings.midAnchorWeight,
            var_swap=vs,
            prior_anchor=pt.prior_anchor,
            prior_var_swap=pt.prior_var_swap,
            operator_prior=pt.operator_prior,
        )
        # LQD is always fitted (the analytic backbone); a non-LQD model choice adds
        # a display overlay on the same edited quotes + band (volfit.api.fit_models),
        # now carrying the SAME prior so SVI/SIV match the backbone (Phase 3/5).
        display = build_display_fit(
            settings.model, k, w, prepared.tau, weights, settings, band=band, var_swap=vs,
            prior_anchor=pt.prior_anchor, operator_prior=pt.operator_prior,
            prior_var_swap=pt.prior_var_swap,
        )
    record = FitRecord(prepared=prepared, result=result, display=display)
    state.store_fit(key, record)
    state.set_calibrated_ptr(ticker, iso, fit_mode, key, float(snapshot.spot))
    history.persist_fit(state, ticker, iso, fit_mode, record)  # opt-in, never raises
    return record


# --------------------------------------------------- fast spot-move transport
#: Dividend modes whose forward shifts ADDITIVELY with spot (discrete cash legs:
#: Delta F_T = Delta S * e^{r t}); the rest scale multiplicatively (F ~ S).
_CASH_DIV_MODES = ("discrete_absolute", "mixed")


def spot_forward_shift(
    state: AppState, ticker: str, expiry: date, f0: float, discount: float, t: float
) -> tuple[float, float]:
    """(F_T^1, h_T) for the active spot shift: the new forward and its log-ratio.

    Per Docs/spot_move_vol_surface_note_updated.tex, ``h`` must come from the
    forward, not the raw spot ratio. Continuous-yield / proportional dividends
    give the multiplicative ``F_T^1 = F_T^0 (1 + shift)``; discrete CASH dividends
    give the additive ``Delta F_T = Delta S e^{r t}`` (so ``h_T`` differs per
    expiry). Returns ``(f0, 0.0)`` when no shift is active. Shared by the
    parametric slice transport and the affine LV-surface transport.
    """
    shift = state.spot_shift(ticker)
    if shift == 0.0 or f0 <= 0.0:
        return f0, 0.0
    spot0 = float(state.anchor_spot(ticker))  # the CALIBRATION spot, not live snapshot
    ds = spot0 * shift
    mode = state.market_settings(ticker).dividendMode
    cash = mode in _CASH_DIV_MODES and any(
        0.0 < state.year_fraction(date.fromisoformat(d.exDate)) <= t
        for d in state.market_settings(ticker).dividends
    )
    if cash and t > 0.0 and 0.0 < discount <= 1.0:
        r = -math.log(discount) / t
        f1 = f0 + ds * math.exp(r * t)
    else:
        f1 = f0 * (1.0 + shift)
    h = math.log(f1 / f0) if f1 > 0.0 else 0.0
    return f1, h


def _spot_transport_forward(state: AppState, ticker: str, expiry: date, prepared) -> tuple[float, float]:
    """(F_T^1, h_T) for a prepared slice — thin wrapper over spot_forward_shift."""
    return spot_forward_shift(
        state, ticker, expiry, float(prepared.forward), float(prepared.discount), float(prepared.t)
    )


def _transported_display(slice_: TransportedSlice, prepared) -> DisplayFit:
    """A DisplayFit overlay wrapping a transported slice, so every view reads the
    moved smile through the standard displayed-fit path (numeric diagnostics)."""
    k, w, tau = prepared.k, prepared.w_mid, prepared.tau
    lee_left, lee_right = numeric_lee_slopes(slice_)
    return DisplayFit(
        model="transport",
        slice=slice_,
        handles=numeric_handles(slice_, tau),
        var_swap_w=numeric_var_swap_w(slice_),
        lee_left=lee_left,
        lee_right=lee_right,
        max_iv_error=_max_iv_error(slice_, k, w, tau),
    )


def transport_record(state: AppState, ticker: str, iso: str, record: FitRecord) -> FitRecord:
    """Transport an anchor fit for the ticker's active spot shift (no refit).

    Returns ``record`` unchanged when no shift is active. Otherwise the displayed
    smile is moved per the Options dynamics regime (volfit.dynamics.transport):
    the new forward F^1 and re-indexed quotes (fixed strikes -> new moneyness
    k - h) go on the prepared inputs, and the transported slice is attached as a
    DisplayFit so the chart, diagnostics, surface, term, density, var-swap and the
    Dupire local-vol extraction all follow it. ``result`` (the LQD anchor) is kept
    intact so the graph universe still reads exact LQD coordinates.
    """
    shift = state.spot_shift(ticker)
    if shift == 0.0:
        return record
    expiry = date.fromisoformat(iso)
    f1, h = _spot_transport_forward(state, ticker, expiry, record.prepared)
    if h == 0.0:
        return record
    regime = state.dynamics_regime()
    base = displayed_slice(record)  # the anchor's displayed model (LQD or overlay)
    tau = record.prepared.tau
    moved = TransportedSlice(
        base, h, regime,
        sigma0=displayed_atm_vol(record), kappa=displayed_skew(record), tau=tau,
    )
    new_prepared = replace(record.prepared, forward=f1, k=record.prepared.k - h)
    return FitRecord(
        prepared=new_prepared,
        result=record.result,
        display=_transported_display(moved, new_prepared),
    )


def node_dirty(state: AppState, ticker: str, iso: str, fit_mode: str) -> bool:
    """Whether a node's displayed fit is STALE: it has been calibrated before, but
    the current inputs (quotes, settings, forwards, events, fresh data) have
    drifted from the calibrated key. False when never calibrated (it will
    bootstrap) or up to date."""
    ptr = state.get_calibrated_ptr(ticker, iso, fit_mode)
    if ptr is None:
        return False
    return ptr[0] != fit_key(state, ticker, iso, fit_mode)


def calibrate_node(
    state: AppState, ticker: str, expiry_iso: str, fit_mode: str, init=None
) -> FitRecord:
    """Explicitly (re)calibrate one node at the live snapshot spot, re-anchoring
    it: the transient spot shift is cleared so the fit uses the spot synchronous
    to the fetched options chain, and the calibrated pointer moves to now.

    ``init`` threads an LQD warm-start (the surface sweep's previous expiry); it is
    None for a lone single-node Calibrate."""
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()
    state.set_spot_shift(ticker, 0.0)  # re-anchor: calibrate at the chain's spot
    return _compute_fit(state, ticker, iso, fit_mode, init=init)


def displayed_base(
    state: AppState, ticker: str, expiry_iso: str, fit_mode: str
) -> FitRecord | None:
    """The calibrated record to display, BEFORE the spot-move transport.

    Calibration is trigger-gated (ROADMAP workflow): autoCalibrate ON and inputs
    changed -> refit; otherwise the FROZEN calibrated fit (``node_dirty`` reports
    staleness), recomputed only on an explicit Calibrate (``calibrate_node``).
    Also the "previous calibration" the Smile Viewer overlays dimmed under a
    transported smile.

    Never calibrated yet: in the **gated** workflow (the live server) this returns
    ``None`` — no fit is bootstrapped on a mere read, so opening the app / picking
    the universe never calibrates; the node stays "no fit" until the Calibrate
    button. Ungated (the test app) bootstraps one fit, the historical behaviour."""
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()
    ptr = state.get_calibrated_ptr(ticker, iso, fit_mode)
    key = fit_key(state, ticker, iso, fit_mode)
    if ptr is None:
        return None if state._gated else _compute_fit(state, ticker, iso, fit_mode)
    if state.options().autoCalibrate and ptr[0] != key:
        return _compute_fit(state, ticker, iso, fit_mode)
    record = state.get_fit(ptr[0])
    if record is None:  # pointer outlived its cache entry (defensive)
        return None if state._gated else _compute_fit(state, ticker, iso, fit_mode)
    return record


def fit_or_get(
    state: AppState, ticker: str, expiry_iso: str, fit_mode: str
) -> FitRecord | None:
    """Displayed slice fit for (ticker, expiry, mode): the calibrated anchor
    (``displayed_base``) with the no-recal spot-move transport applied on top.
    ``None`` when the node has no fit yet (gated workflow, before Calibrate)."""
    record = displayed_base(state, ticker, expiry_iso, fit_mode)
    if record is None:
        return None
    if state.spot_shift(ticker) == 0.0:
        return record
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()
    return transport_record(state, ticker, iso, record)


def fill_nonfinite(vols: np.ndarray) -> np.ndarray:
    """Edge-extend any non-finite vols (the model is undefined at the extreme
    wings) so the curve/mesh stays a clean finite array — a NaN would serialize
    to JSON null and break the chart's numeric arrays."""
    out = np.asarray(vols, dtype=float)
    bad = ~np.isfinite(out)
    if bad.any():
        good = np.where(~bad)[0]
        out[bad] = np.interp(np.where(bad)[0], good, out[good]) if good.size else 0.0
    return out


def model_curve(record: FitRecord) -> list[SmilePoint]:
    """Sample the displayed slice's IV curve, extended to at least
    k ∈ [-1.4, 1] so the model wings are drawn well beyond the observed quotes
    (the put wing reaches further). The smile's brush still defaults to the
    observed range (SmileData.kMin/kMax); zooming or panning out reveals the
    extension."""
    k_lo = min(K_DISPLAY_LO, float(record.prepared.k.min()) - K_PAD)
    k_hi = max(K_DISPLAY_HI, float(record.prepared.k.max()) + K_PAD)
    grid = np.linspace(k_lo, k_hi, N_MODEL_POINTS)
    w = np.maximum(displayed_slice(record).implied_w(grid), 0.0)
    vols = fill_nonfinite(np.sqrt(w / record.prepared.tau))
    return [SmilePoint(k=float(k), vol=float(v)) for k, v in zip(grid, vols)]


def _varswap_rms_term(
    state: AppState, ticker: str, iso: str, record: FitRecord,
    k: np.ndarray, weights: np.ndarray | None, tau: float,
) -> tuple[float, float, float] | None:
    """``(model_vol, quote_vol, weight)`` of the var-swap RMS term, or None.

    Active only when var-swap is enabled and the node has a live quote — the same
    gate + penalty weight (``varSwapWeightPct`` % of the summed quote weights) the
    calibration uses, so the reported RMS counts the var-swap exactly as the fit."""
    target = varswap_target(state, ticker, iso, k, weights, tau)
    if target is None or tau <= 0.0:
        return None
    quote_vol = float(np.sqrt(max(target.total_var, 0.0) / tau))
    model_vol = float(np.sqrt(max(displayed_var_swap_w(record), 0.0) / tau))
    return model_vol, quote_vol, float(target.weight)


def _node_rms_terms(
    state: AppState, ticker: str, iso: str, record: FitRecord, fit_mode: str
) -> tuple[float, float]:
    """``(sum_weighted_sq, sum_weight)`` of the displayed fit's RMS vol error for
    one node, consistent with the calibration: distance to the chosen fit target
    (mid / bid-ask / haircut band), the active weighting scheme, and the var-swap
    quote (volfit.calib.rms)."""
    prepared = record.prepared
    k, w, _ = edited_fit_inputs(state, ticker, iso, prepared, None)
    weights = resolve_weights(state.fit_settings().weightScheme, k, w)
    band = edited_band(state, ticker, iso, prepared, fit_mode)
    tau = prepared.tau
    model_iv = np.sqrt(np.maximum(displayed_slice(record).implied_w(k), 1e-12) / tau)
    mid_iv = np.sqrt(np.maximum(w, 1e-12) / tau)
    vs = _varswap_rms_term(state, ticker, iso, record, k, weights, tau)
    return node_error_terms(model_iv, mid_iv, weights, band, vs)


def weighted_rms_error(
    state: AppState, ticker: str, iso: str, record: FitRecord, fit_mode: str = "mid"
) -> float:
    """Weighted RMS vol error of the displayed fit, scored against its OWN
    calibration objective: distance to the chosen fit target (mid / bid-ask /
    haircut band), the active weighting scheme, and any var-swap quote. Decimal
    vol (the UI renders it as a percentage)."""
    return rms_of_terms(*_node_rms_terms(state, ticker, iso, record, fit_mode))


def surface_rms_error(state: AppState, ticker: str, fit_mode: str) -> float:
    """Whole-surface weighted RMS vol error of a ticker: the per-node fit-target
    errors of every expiry pooled (quote-weighted) into one number, on the SAME
    calibration-consistent basis as ``weighted_rms_error``. Reads the displayed
    fit of each expiry (cached; no refit). 0 when the ticker has no fittable
    slices."""
    try:
        forwards = state.forwards(ticker)
    except Exception:
        return 0.0
    num = den = 0.0
    for expiry in sorted(forwards):
        iso = expiry.isoformat()
        try:
            record = fit_or_get(state, ticker, iso, fit_mode)
        except Exception:
            continue  # a slice that can't fit (too few quotes) just doesn't score
        if record is None:
            continue  # uncalibrated node (gated, pre-Calibrate): contributes nothing
        n, d = _node_rms_terms(state, ticker, iso, record, fit_mode)
        num += n
        den += d
    return rms_of_terms(num, den)


def _prior_overlay(
    state: AppState, ticker: str, iso: str, record: FitRecord, model: list[SmilePoint]
) -> tuple[list[SmilePoint], bool]:
    """The prior curve to overlay + whether it is the active fetched prior.

    Precedence: the ACTIVE fetched prior (transported to the current forward under
    the dynamics regime, drawn dotted) -> a saved per-node prior -> the current fit
    (so the chart always carries a prior line). The transported prior is sampled on
    the model curve's own k grid so the dotted line aligns with the smile."""
    from volfit.api import prior_transport

    node = prior_transport.prior_node(state.active_prior(ticker), iso)
    if node is not None:
        grid = np.array([p.k for p in model], dtype=float)
        points = prior_transport.transported_prior_points(
            node, float(record.prepared.forward), state.dynamics_regime(), grid
        )
        return points, True
    saved = state.get_prior((ticker, iso))
    return (list(saved.curve) if saved is not None else list(model)), False


def varswap_info(state: AppState, ticker: str, iso: str, record: FitRecord) -> VarSwapInfo:
    """Var-swap quote state + the model's own fair var-swap vol for a node."""
    session = state.varswap_session_if_exists((ticker, iso))
    model_vol = float(np.sqrt(displayed_var_swap_w(record) / record.prepared.tau))
    enabled = state.options().varSwapEnabled
    if session is None:
        return VarSwapInfo(
            level=None, excluded=False, modelVol=model_vol,
            enabled=enabled, canUndo=False, canRedo=False,
        )
    return VarSwapInfo(
        level=session.state.level,
        excluded=session.state.excluded,
        modelVol=model_vol,
        enabled=enabled,
        canUndo=session.can_undo,
        canRedo=session.can_redo,
    )


def model_info(record: FitRecord) -> ModelInfo:
    """The model family + hyperparameters that produced the DISPLAYED fit.

    Read off the actual displayed slice — LQD when there is no overlay (degree N
    from the fitted Legendre params), else the overlay family (Multi-Core SIV
    reports its fitted core count R; SVI-JW has no hyperparameter). This reflects
    what is drawn even for a frozen/stale node, so the diagnostics panel always
    names the model the chart actually shows, not the (possibly newer) settings."""
    display = record.display
    if display is None:  # the analytic LQD backbone is displayed
        return ModelInfo(
            id="lqd",
            label="LQD",
            params=[ModelParam(label="Degree N", value=str(record.result.params.order))],
        )
    if display.model == "sigmoid":
        return ModelInfo(
            id="sigmoid",
            label="Multi-Core SIV",
            params=[ModelParam(label="Cores R", value=str(len(display.slice.cores)))],
        )
    return ModelInfo(id="svi", label="SVI-JW")  # 5 raw params, no hyperparameter


def prepare_slice(state: AppState, ticker: str, expiry_iso: str):
    """Prepare one expiry's quotes in IV space WITHOUT calibrating — for the
    pre-Calibrate display (quote bands + the implied forward). ``None`` when no
    chain has been fetched or the expiry has no implied forward yet."""
    if not state.has_quotes(ticker):
        return None
    expiry = state.resolve_expiry(ticker, expiry_iso)
    try:
        return prepared_quotes(state, ticker, expiry)  # de-Am memoized per node
    except Exception:
        return None  # no forward for this expiry yet / degenerate slice


def _no_fit_prior(
    state: AppState, ticker: str, iso: str, forward: float
) -> tuple[list[SmilePoint], bool]:
    """The dotted ACTIVE prior on a default grid (transported to ``forward`` under
    the dynamics regime), or ``([], False)`` when none exists / no forward yet."""
    if forward <= 0.0:
        return [], False
    from volfit.api import prior_transport

    node = prior_transport.prior_node(state.active_prior(ticker), iso)
    if node is None:
        return [], False
    grid = np.linspace(K_DISPLAY_LO, K_DISPLAY_HI, 81)
    points = prior_transport.transported_prior_points(
        node, forward, state.dynamics_regime(), grid
    )
    return points, True


def _no_fit_smile_payload(
    state: AppState, ticker: str, expiry_iso: str, fit_mode: str
) -> SmileData:
    """SmileData for a node with no calibrated fit yet (gated workflow, before the
    Calibrate button): quote bands if a chain was fetched, the dotted active prior
    if one exists, an EMPTY model curve, and ``hasFit=False`` so the viewer shows
    a 'No fit yet — Calibrate' cue instead of charting a phantom fit."""
    expiry = state.resolve_expiry(ticker, expiry_iso)
    iso = expiry.isoformat()
    prepared = prepare_slice(state, ticker, iso)
    session = state.session_if_exists((ticker, iso))
    quotes: list[QuoteBand] = []
    if prepared is not None:
        for i, (k, b, a, m) in enumerate(
            zip(prepared.k, prepared.iv_bid, prepared.iv_ask, prepared.iv_mid)
        ):
            edit = session.edits.get(i) if session is not None else None
            amended = edit is not None and edit.amended_iv is not None
            quotes.append(
                QuoteBand(
                    k=float(k), bid=float(b), ask=float(a),
                    mid=edit.amended_iv if amended else float(m), index=i,
                    excluded=edit is not None and edit.excluded, amended=amended,
                )
            )
    forward = float(prepared.forward) if prepared is not None else 0.0
    prior, prior_transported = _no_fit_prior(state, ticker, iso, forward)
    if prepared is not None:
        k_min = float(prepared.k.min()) - K_PAD
        k_max = float(prepared.k.max()) + K_PAD
    else:
        k_min, k_max = K_DISPLAY_LO, K_DISPLAY_HI
    vs = state.varswap_session_if_exists((ticker, iso))
    settings = state.fit_settings()
    return SmileData(
        ticker=ticker,
        expiry=expiry_iso,
        T=state.year_fraction(expiry),
        forward=forward,
        model=[],
        prior=prior,
        priorTransported=prior_transported,
        quotes=quotes,
        kMin=k_min,
        kMax=k_max,
        diagnostics=SmileDiagnostics(
            atmVol=0.0, skew=0.0, curvature=0.0, aLeft=0.0, aRight=0.0,
            leeLeft=0.0, leeRight=0.0, varSwapVol=0.0, rmsError=0.0,
        ),
        modelInfo=ModelInfo(id=settings.model, label=_model_label(settings.model)),
        varSwap=VarSwapInfo(
            level=vs.state.level if vs is not None else None,
            excluded=vs.state.excluded if vs is not None else False,
            modelVol=0.0, enabled=state.options().varSwapEnabled,
            canUndo=vs.can_undo if vs is not None else False,
            canRedo=vs.can_redo if vs is not None else False,
        ),
        canUndo=session.can_undo if session is not None else False,
        canRedo=session.can_redo if session is not None else False,
        hasFit=False,
        stale=False,
        anchorModel=None,
        surfaceRmsError=0.0,
    )


def smile_payload(state: AppState, ticker: str, expiry_iso: str, fit_mode: str) -> SmileData:
    """Assemble the full SmileData payload for one (ticker, expiry) node."""
    record = fit_or_get(state, ticker, expiry_iso, fit_mode)
    if record is None:  # gated workflow, never calibrated -> quotes/prior, no curve
        return _no_fit_smile_payload(state, ticker, expiry_iso, fit_mode)
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()  # session key
    session = state.session_if_exists((ticker, iso))
    prepared, slice_ = record.prepared, record.result.slice
    model = model_curve(record)
    rms_error = weighted_rms_error(state, ticker, iso, record, fit_mode)
    surface_rms = surface_rms_error(state, ticker, fit_mode)

    # Prior overlay: prefer the ACTIVE fetched prior (dotted, spot-updated to the
    # current forward under the dynamics regime); else a saved per-node prior; else
    # the current fit (so the chart always has a "prior" line).
    prior, prior_transported = _prior_overlay(state, ticker, iso, record, model)

    # While a spot move is active, also expose the pre-transport calibration so
    # the viewer overlays it dimmed (the original fit vs the transported smile).
    anchor_base = (
        displayed_base(state, ticker, iso, fit_mode)
        if state.spot_shift(ticker) != 0.0
        else None
    )
    anchor_model = model_curve(anchor_base) if anchor_base is not None else None

    if record.display is not None:
        # Non-LQD overlay: numeric handles/var-swap/Lee; A_L/A_R have no analogue.
        d = record.display
        diagnostics = SmileDiagnostics(
            atmVol=d.handles.atm_vol,
            skew=d.handles.skew,
            curvature=d.handles.curvature,
            aLeft=0.0,
            aRight=0.0,
            leeLeft=d.lee_left,
            leeRight=d.lee_right,
            varSwapVol=float(np.sqrt(d.var_swap_w / prepared.tau)),
            rmsError=rms_error,
        )
    else:
        handles = atm_handles(slice_, prepared.tau)
        a_left, a_right = endpoint_scales(record.result.params)
        lee_left, lee_right = lee_slopes(record.result.params)
        diagnostics = SmileDiagnostics(
            atmVol=handles.sigma0,
            skew=handles.skew,
            curvature=handles.curvature,
            aLeft=a_left,
            aRight=a_right,
            leeLeft=lee_left,
            leeRight=lee_right,
            varSwapVol=float(np.sqrt(slice_.var_swap_strike() / prepared.tau)),
            rmsError=rms_error,
        )
    # Every prepared quote is listed (excluded dimmed by the UI); an amended
    # quote shows its overridden mid, bid/ask stay the market band.
    quotes = []
    for i, (k, b, a, m) in enumerate(
        zip(prepared.k, prepared.iv_bid, prepared.iv_ask, prepared.iv_mid)
    ):
        edit = session.edits.get(i) if session is not None else None
        amended = edit is not None and edit.amended_iv is not None
        quotes.append(
            QuoteBand(
                k=float(k),
                bid=float(b),
                ask=float(a),
                mid=edit.amended_iv if amended else float(m),
                index=i,
                excluded=edit is not None and edit.excluded,
                amended=amended,
            )
        )
    return SmileData(
        ticker=ticker,
        expiry=expiry_iso,
        T=prepared.t,
        forward=prepared.forward,
        model=model,
        prior=prior,
        priorTransported=prior_transported,
        quotes=quotes,
        # Brush extent / default window stay the OBSERVED range, even though the
        # model curve above is sampled out to ±1 (revealed by zoom / pan).
        kMin=float(prepared.k.min()) - K_PAD,
        kMax=float(prepared.k.max()) + K_PAD,
        diagnostics=diagnostics,
        modelInfo=model_info(record),
        varSwap=varswap_info(state, ticker, iso, record),
        canUndo=session.can_undo if session is not None else False,
        canRedo=session.can_redo if session is not None else False,
        stale=node_dirty(state, ticker, iso, fit_mode),
        anchorModel=anchor_model,
        surfaceRmsError=surface_rms,
    )


# -------------------------------------------------------------- surface fit
def surface_inputs(
    state: AppState, ticker: str, fit_mode: str
) -> list[tuple[str, PreparedQuotes]]:
    """(expiry-ISO, prepared quotes) per expiry, nearest first.

    Weights and band are derived per slice at fit time (they depend on the
    edited quotes), so the plan only carries the prepared quotes.
    """
    snapshot = state.ensure_chain(ticker)  # calibrate path: fetch the chain if absent
    forwards = state.forwards(ticker)  # gates the expiry universe
    american = snapshot.exercise_style == "american"
    plan = []
    msg = f"Preparing {ticker} quotes"
    detail = "de-americanizing" if american else ""
    with state.activity.activity("calibrate", msg, detail):
        for expiry in sorted(forwards):
            plan.append((expiry.isoformat(), prepared_quotes(state, ticker, expiry)))
    return plan


def fit_surface_slice(
    state: AppState,
    ticker: str,
    iso: str,
    prepared: PreparedQuotes,
    prev: CalibrationResult | None,
    enforce_calendar: bool,
    fit_mode: str = "mid",
) -> CalibrationResult:
    """One step of the calibrate_surface loop: warm start + calendar floor.

    Quote-edit sessions apply here too (state/ticker/iso resolve them), so a
    surface fit honours the user's excluded/amended quotes on every expiry. The
    calendar floor is keyed on quadrature z-values, not the quote array, so
    masking quotes leaves it untouched. ``fit_mode`` selects the band objective;
    the weight scheme follows the fit settings (volfit.calib.weights).
    """
    cal_z = cal_floor = None
    if enforce_calendar and prev is not None:
        cal_z, cal_floor = calendar_floor_targets(prev.slice)
    k, w, _ = edited_fit_inputs(state, ticker, iso, prepared, None)
    settings = state.fit_settings()
    weights = resolve_weights(settings.weightScheme, k, w)
    band = edited_band(state, ticker, iso, prepared, fit_mode)
    vs = varswap_target(state, ticker, iso, k, weights, prepared.tau)
    pt = prior_targets(state, ticker, iso, k, weights, prepared)
    return calibrate_slice(
        k,
        w,
        t=prepared.tau,
        n_order=settings.nOrder,
        weights=weights,
        reg_lambda=settings.regLambda,
        reg_power=settings.regPower,
        init=prev.params if prev is not None else None,
        band=band,
        calendar_z=cal_z,
        calendar_floor=cal_floor,
        calendar_weight=state.options().calendarWeight,
        barrier_center=settings.barrierCenter,
        barrier_scale=settings.barrierScale,
        mid_anchor_weight=settings.midAnchorWeight,
        var_swap=vs,
        prior_anchor=pt.prior_anchor,
        prior_var_swap=pt.prior_var_swap,
        operator_prior=pt.operator_prior,
    )


def fit_and_commit_slice(
    state: AppState,
    ticker: str,
    iso: str,
    prepared: PreparedQuotes,
    prev: CalibrationResult | None,
    enforce_calendar: bool,
    fit_mode: str = "mid",
    prev_display: DisplayFit | None = None,
) -> FitRecord:
    """Calendar-coupled slice fit (``fit_surface_slice``) PLUS the calibration
    bookkeeping: build the display overlay, cache the record under the canonical
    key, re-point the calibrated pointer (a surface/coupled fit IS a calibration)
    and persist it. Returns the committed FitRecord (its ``.result`` is the
    ``prev`` to thread into the next, longer expiry, and ``.display`` the
    ``prev_display`` for the overlay's calendar floor).

    Shared by the surface-fit endpoint (``fit_surface`` / the WS route) and the
    calendar-coupled branch of the background Calibrate job, so the coupling
    recipe lives in exactly one place. Both the LQD backbone (``fit_surface_slice``)
    and the SVI/sigmoid overlay (``display_overlay``) honour ``enforce_calendar``.
    """
    model = _model_label(state.fit_settings().model)
    with state.activity.activity("calibrate", f"Calibrating {ticker} {iso} ({model})"):
        result = fit_surface_slice(state, ticker, iso, prepared, prev, enforce_calendar, fit_mode)
        overlay = display_overlay(
            state, ticker, iso, prepared, fit_mode, prev_display, enforce_calendar
        )
    record = FitRecord(prepared=prepared, result=result, display=overlay)
    key = fit_key(state, ticker, iso, fit_mode)
    state.store_fit(key, record)
    state.set_calibrated_ptr(ticker, iso, fit_mode, key, float(state.snapshot(ticker).spot))
    history.persist_fit(state, ticker, iso, fit_mode, record)  # opt-in, never raises
    return record


def assemble_surface_response(
    state: AppState,
    ticker: str,
    fit_mode: str,
    fitted: list[tuple[str, CalibrationResult]],
    residuals: list[float],
) -> SurfaceFitResponse:
    """Build the response from fitted slices already stored in the cache."""
    return SurfaceFitResponse(
        ticker=ticker,
        expiries=[iso for iso, _ in fitted],
        calendarResiduals=residuals,
        maxIvErrorBp=[result.max_iv_error * 1e4 for _, result in fitted],
        smiles=[smile_payload(state, ticker, iso, fit_mode) for iso, _ in fitted],
    )


def fit_surface(
    state: AppState,
    ticker: str,
    fit_mode: str,
    enforce_calendar: bool,
    progress=None,
) -> SurfaceFitResponse:
    """Fit all expiries sequentially; cache each so GET /smiles serves them.

    ``progress(expiry_iso, index, total, max_iv_error_bp)`` is invoked after
    each expiry fit (the WebSocket route runs this loop itself instead, so
    its progress events can be awaited between slices).
    """
    state.set_spot_shift(ticker, 0.0)  # re-anchor: fit at the chain's own spot
    plan = surface_inputs(state, ticker, fit_mode)
    prev: CalibrationResult | None = None
    prev_display: DisplayFit | None = None
    residuals: list[float] = []
    fitted: list[tuple[str, CalibrationResult]] = []
    for index, (iso, prepared) in enumerate(plan):
        record = fit_and_commit_slice(
            state, ticker, iso, prepared, prev, enforce_calendar, fit_mode, prev_display
        )
        result = record.result
        residuals.append(0.0 if prev is None else calendar_violation(prev.slice, result.slice))
        fitted.append((iso, result))
        if progress is not None:
            progress(iso, index, len(plan), result.max_iv_error * 1e4)
        prev = result
        prev_display = record.display
    return assemble_surface_response(state, ticker, fit_mode, fitted, residuals)


# ----------------------------------------------------------------- scenario
def run_scenario(state: AppState, request: ScenarioRequest) -> ScenarioResponse:
    """Shift one fitted smile for a spot move under the requested regime."""
    if request.regime == Regime.STICKY_LOCAL_VOL_GRID:
        # Exact dynamics: fixed-strike LV grid + Dupire reprice (api.localvol;
        # imported lazily — that module reuses this one's slice-fit cache).
        from volfit.api.localvol import scenario_sticky_grid

        return scenario_sticky_grid(state, request)
    record = fit_or_get(state, request.ticker, request.expiry, request.fitMode)
    if record is None:  # gated, never calibrated: nothing to transport yet
        regime = request.regime
        return ScenarioResponse(
            k=[], baseVol=[], shiftedVol=[], ssr=ssr_of_regime(regime),
            regime=regime.value if isinstance(regime, Regime) else f"{regime:g}",
        )
    t, slice_ = record.prepared.tau, displayed_slice(record)
    grid = np.linspace(
        min(K_DISPLAY_LO, float(record.prepared.k.min()) - K_PAD),
        max(K_DISPLAY_HI, float(record.prepared.k.max()) + K_PAD),
        N_MODEL_POINTS,
    )

    def vol_curve(k: np.ndarray) -> np.ndarray:
        return np.sqrt(slice_.implied_w(k) / t)

    base = vol_curve(grid)
    skew = displayed_skew(record)
    shifted = shifted_smile(grid, vol_curve, skew, request.spotReturn, request.regime)
    regime = request.regime
    return ScenarioResponse(
        k=grid.tolist(),
        baseVol=base.tolist(),
        shiftedVol=shifted.tolist(),
        ssr=ssr_of_regime(regime),
        regime=regime.value if isinstance(regime, Regime) else f"{regime:g}",
    )
