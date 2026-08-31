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

import hashlib
import math
from dataclasses import dataclass, replace
from datetime import date, datetime, time

import numpy as np

from volfit.api import fit_pool, fit_uncertainty, history
from volfit.api.fit_models import DisplayFit, _max_iv_error
from volfit.calib.fit_task import OverlaySettings, SliceFitTask, run_slice_fit
from volfit.models.sigmoid.calibrate import WING_PENALTY_BASE
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
    calendar_grid_nodes,
    calendar_violation_windowed,
    common_support,
    confined_calendar_floor,
    variance_floor_grid_common,
    variance_floor_grid_winged,
    variance_floor_targets,
)
from volfit.api import smile_layers
from volfit.api.prior_mode import resolve_prior_mode
from volfit.api.varswap_split import parametric_varswap_split, split_fields
from volfit.calib.extrap import build_extrap_target
from volfit.calib.factors import build_factor_prior
from volfit.calib.operator_merge import merge_operator_targets
from volfit.calib.operators import (
    WING_OPERATORS,
    OperatorPriorTarget,
    build_operator_prior,
    hybrid_tail_deltas,
)
from volfit.calib.prior import PriorAnchorTarget, build_prior_anchor
from volfit.calib.rms import node_error_terms, rms as rms_of_terms
from volfit.calib.intraday_time import intraday_variance_days
from volfit.calib.varswap import VARSWAP_PIN_MULT, VarSwapTarget, varswap_total_variance
from volfit.calib.weighted_time import DAYS_PER_YEAR, weighted_variance_years
from volfit.calib.weights import resolve_weights
from volfit.data.expiry_time import default_settlement, exact_year_fraction
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
from volfit.models.lqd.calibrate import CalibrationResult

#: Model-curve sampling: points over the extended (≥[-1,1]) display grid; denser
#: than before to keep ATM resolution across the wider range. K_PAD pads the
#: OBSERVED range used for the brush extent / default window.
#: N_CORE_POINTS of the budget are concentrated on the observed quote range —
#: a 1-week smile spans only a few percent of the fixed display range, and a
#: uniform grid drew it with ~10 samples (visibly piecewise-linear at the ATM
#: curvature); the wings beyond the quotes are smooth extrapolation and keep
#: reading fine at the coarser spacing.
N_MODEL_POINTS = 241
N_CORE_POINTS = 121
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

#: Quote-count guard on the LQD order: params N+1 <= quotes/2 (two quotes per
#: parameter). Two measured failure modes above that ratio, both on thin books
#: at the raised default order (16): (a) identification — on a 14-quote chain
#: the delta-method error bars (api.fit_uncertainty) are healthy at params <=
#: quotes - 4 and saturate the 0.1 variance ceiling by params = quotes - 1;
#: (b) LATENCY — on the 19-quote 0DTE book the solver meanders in the
#: ridge-flat valley (params/quotes 0.47 -> 7 evals / 20ms; 0.58 -> 63 evals /
#: 166ms; 0.68 -> 2568 evals / 7.6s), destroying the <50ms warm-slice gate.
LQD_QUOTES_PER_PARAM = 2

#: The guard never caps below the historical default order — sparse books
#: (e.g. a 9-quote weekly) have always fitted at N=6 and the tail-reach /
#: functional-band behavior of those fits is locked by tests and priors.
LQD_ORDER_GUARD_FLOOR = 6


def effective_lqd_order(n_order: int, n_quotes: int) -> int:
    """The slice's usable Legendre order: the configured ``n_order`` capped so
    that params N+1 <= n_quotes / LQD_QUOTES_PER_PARAM. The cap never reduces
    the order below min(n_order, 6) — thin books keep their historical N=6
    fits — so it only moderates the HIGH default/cap (16/24) on chains too
    sparse to identify that many modes quickly (0DTE, thin weeklies; the
    wide-z 100+-quote LEAP surfaces that need the shoulder resolution are
    untouched)."""
    n_order = int(n_order)
    capped = min(n_order, int(n_quotes) // LQD_QUOTES_PER_PARAM - 1)
    return max(min(n_order, LQD_ORDER_GUARD_FLOOR), capped)

#: Friendly model names for the engine-activity narration (status bar).
_MODEL_LABELS = {"lqd": "LQD", "svi": "SVI-JW", "sigmoid": "Multi-Core Sigmoid"}


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


def _base_fit_key(state: AppState, ticker: str, iso: str, fit_mode: str) -> tuple:
    """The NODE-LOCAL fit-cache key: (ticker, canonical ISO, mode, session
    version, var-swap version, events version, settings version, forwards
    version, options version, data version, prior version) — quote edits,
    var-swap edits, event-calendar edits, hyperparameter, forward/market and
    calendar/var-swap-penalty/event-clock changes each bump a version, so
    affected nodes refit without eviction. This is the whole ``fit_key``
    except the calendar-on-refit neighbour fingerprint; it also freshness-
    tests a NEIGHBOUR's committed fit without recursing through *its*
    neighbours (A -> B -> A)."""
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


def fit_key(state: AppState, ticker: str, iso: str, fit_mode: str) -> tuple:
    """Fit-cache key of a node: ``_base_fit_key`` plus — under
    ``calendarOnRefit`` (with ``enforceCalendar``) — a NEIGHBOUR FINGERPRINT.

    With the toggle on, a single-node fit reads the adjacent committed slices
    as its calendar floor/ceiling (``_compute_fit``), so those neighbours are
    genuine fit inputs: the fingerprint (a content digest of each fresh
    neighbour's committed fit, ``_neighbour_fingerprint``) folds them in, and
    a neighbour's changed fit invalidates this node's cached fit for free.
    Toggle off: the historical tuple, byte-identical."""
    key = _base_fit_key(state, ticker, iso, fit_mode)
    options = state.options()
    if options.calendarOnRefit and options.enforceCalendar:
        key = (*key, _neighbour_fingerprint(state, ticker, iso, fit_mode))
    return key


# ----------------------------------- calendar-on-refit neighbour context
#: Fixed log-moneyness sampling of the displayed-overlay part of the
#: neighbour fingerprint: overlay families share no single params-vector
#: layout, so the digest reads the committed CURVE itself (total variance on
#: this grid) — any change of the displayed slice moves it.
_FP_K = np.linspace(-1.5, 1.5, 31)


def _neighbour_isos(state: AppState, ticker: str, iso: str) -> tuple[str | None, str | None]:
    """(previous shorter, next longer) expiry ISO around ``iso`` in the
    ticker's SELECTED ladder; None at a ladder end (or off-ladder node)."""
    try:
        expiry = date.fromisoformat(iso)
    except ValueError:
        return None, None
    ladder = sorted(state.selected_expiries(ticker))
    prevs = [d for d in ladder if d < expiry]
    nexts = [d for d in ladder if d > expiry]
    return (
        prevs[-1].isoformat() if prevs else None,
        nexts[0].isoformat() if nexts else None,
    )


def _committed_fresh(state: AppState, ticker: str, iso: str | None, fit_mode: str):
    """A neighbour's committed FitRecord when FRESH at the base-key level,
    else None. Strictly read-only (compare._committed_slice pattern):
    calibrated pointer + fit cache, NEVER a fit — a missing or stale
    neighbour side is simply skipped. Freshness compares the stored key's
    node-local prefix against the live ``_base_fit_key``, deliberately
    ignoring any fingerprint element the stored key carries: a full-key
    comparison would recurse through the neighbour's own neighbours."""
    if iso is None:
        return None
    ptr = state.get_calibrated_ptr(ticker, iso, fit_mode)
    if ptr is None:
        return None
    base = _base_fit_key(state, ticker, iso, fit_mode)
    if tuple(ptr[0][: len(base)]) != base:
        return None
    return state.get_fit(ptr[0])


def _record_digest(record) -> str:
    """Content fingerprint of a committed fit: the LQD backbone params (+
    tail exponents) and the displayed overlay's curve on ``_FP_K``. Hashing
    VALUES rather than the neighbour's cache key means a re-commit that
    reproduces the identical fit does NOT ripple a spurious invalidation
    through its neighbours (the refit ping-pong terminates at a fixed
    point)."""
    h = hashlib.sha1()
    p = record.result.params
    h.update(np.asarray([p.L, p.R, p.alpha_left, p.alpha_right], dtype=float).tobytes())
    h.update(np.asarray(p.a, dtype=float).tobytes())
    if record.display is not None:
        h.update(record.display.model.encode())
        h.update(np.asarray(record.display.slice.implied_w(_FP_K), dtype=float).tobytes())
    return h.hexdigest()[:16]


def _neighbour_fingerprint(state: AppState, ticker: str, iso: str, fit_mode: str) -> tuple:
    """((iso, digest) | None per side) for the two ladder neighbours — the
    exact context ``_compute_fit`` would thread under ``calendarOnRefit``, so
    the fit key changes exactly when that context changes (a neighbour's fit
    moved, went stale, or appeared)."""
    out = []
    for n_iso in _neighbour_isos(state, ticker, iso):
        record = _committed_fresh(state, ticker, n_iso, fit_mode)
        out.append(None if record is None else (n_iso, _record_digest(record)))
    return tuple(out)


def _neighbour_context(state: AppState, ticker: str, n_iso: str | None, fit_mode: str):
    """(FitRecord, retained k) of a fresh committed neighbour, else None —
    the retained (post-edit) quote support confines the floor exactly as the
    sequential surface pass confines it (calib.surface)."""
    record = _committed_fresh(state, ticker, n_iso, fit_mode)
    if record is None:
        return None
    return record, retained_k(state, ticker, n_iso, record.prepared)


def node_clock(state: AppState, ticker: str, expiry) -> tuple[float, float | None]:
    """The node's calendar clock: (year fraction t, intraday day-base or None).

    Legacy day-granular ``state.year_fraction`` when the 0DTE research clock
    is off (byte-identical). When ``OptionsSettings.intradayClock`` is on:
    exact ACT/365 from the chain snapshot's TIMESTAMP to the expiry's
    settlement instant (the schema-v7 settlement map; the NYSE rule fallback
    for chains that predate it), clamped at 0 past settlement, plus the
    session-weighted day base (volfit.calib.intraday_time) that
    ``variance_time`` accrues tau from. Valuation is always the SNAPSHOT
    timestamp, never wall clock — replay/captured chains price at their own
    moment, and the observation filter's convention is matched."""
    options = state.options()
    if not options.intradayClock:
        return state.year_fraction(expiry), None
    snap = state.snapshot(ticker)
    rec = snap.settlement.get(expiry) if snap.settlement is not None else None
    settle = rec.settle if rec is not None else default_settlement(expiry).settle
    t_exact = exact_year_fraction(snap.timestamp, settle)
    if t_exact <= 0.0:
        return 0.0, 0.0
    base = intraday_variance_days(
        snap.timestamp, settle, options.sessionVarShare, options.nonTradingWeight
    )
    return t_exact, base


def variance_time(
    state: AppState, ticker: str, expiry, t_cal: float, base_days: float | None = None
) -> float:
    """Event-weighted variance years for a node (volfit.calib.weighted_time).

    The smile is calibrated/quoted in this clock so an event before the expiry
    lowers every reported vol at fixed price. Reduces to the calendar ``t_cal``
    when the event clock is off (OptionsSettings.eventsEnabled) or the ticker has
    no events. ``expiry`` is accepted for symmetry/future use; the clock depends
    only on the calendar maturity and the ticker's shared event calendar.

    ``base_days`` is the intraday clock's accrued day-weights (``node_clock``):
    when given it replaces the calendar day base, so tau carries the sub-day
    session profile whether or not the ticker has events; the event CUTOFF
    stays on the calendar maturity."""
    options = state.options()
    events = state.events(ticker) if options.eventsEnabled else []
    if not events:
        return t_cal if base_days is None else base_days / DAYS_PER_YEAR
    pairs = [(e.time, e.weight) for e in events]
    return weighted_variance_years(
        t_cal, pairs, normalize=options.normalizeEvents, base_days=base_days
    )


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
    t_cal, base_days = node_clock(state, ticker, expiry)
    tau = variance_time(state, ticker, expiry, t_cal, base_days)
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
    strength regardless of how many quotes the node has.

    ``varSwapHardPin`` escalates THIS row (the market quote — and only this
    row) to the stiff-row weight VARSWAP_PIN_MULT × Σ quote weights, so the
    fitted var-swap matches the quote to solver tolerance. Prior var-swap
    companion rows are never pinned: pinning a stale prior would silently
    overpower live quotes with yesterday's level."""
    options = state.options()
    if not options.varSwapEnabled:
        return None
    session = state.varswap_session_if_exists((ticker, iso))
    if session is None or not session.state.is_active:
        return None
    sum_w = float(np.sum(weights)) if weights is not None else float(k.size)
    weight = (options.varSwapWeightPct / 100.0) * sum_w
    if options.varSwapHardPin:
        weight = VARSWAP_PIN_MULT * sum_w  # equality-to-solver-tolerance idiom
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
    state: AppState,
    ticker: str,
    iso: str,
    k: np.ndarray,
    weights: np.ndarray | None,
    prepared,
    fit_mode: str = "mid",
) -> PriorTargets:
    """Persistence targets + the observation-filter prediction prior (Note 15).

    The persistence targets come from ``_persistence_targets`` (mode-routed,
    with the active-filter auto-exclusion already applied by
    ``resolve_prior_mode``). In filter mode ``active`` the Kalman prediction
    prior is injected as the operator block (an ungated OperatorPriorTarget,
    eq. active-map) — it is independent of any SAVED persistence prior, so it
    applies even when no prior snapshot is fetched; the surviving deep-tail
    anchor rides alongside it. Under ``wingOperatorsUnderActiveFilter`` (Note
    15 §6.3 carve-out) the persistence block is the WingL/WingR rows alone and
    is MERGED beside the MAP rows (volfit.calib.operator_merge); the default
    leaves it None, so the block is the filter target itself."""
    targets = _persistence_targets(state, ticker, iso, k, weights, prepared)
    if state.options().observationFilterMode == "active":
        from volfit.api import observation_filter as ofilt

        ft = ofilt.active_prediction_target(state, ticker, iso, fit_mode, prepared)
        if ft is not None:
            targets = PriorTargets(
                prior_anchor=targets.prior_anchor,
                # body persistence operators are excluded in active; only the
                # wing rows (flag ON) can sit in targets.operator_prior here
                operator_prior=merge_operator_targets(ft, targets.operator_prior),
                prior_var_swap=targets.prior_var_swap,
            )
    return targets


def _prior_varswap(
    options, moved_w, prior_tau: float, tau: float, total_var: float, weight: float
) -> VarSwapTarget:
    """The PRIOR var-swap companion row under the configured carrier.

    ``priorVarSwapMode == "absolute"`` (default) keeps the historical level row
    — same construction, byte-identical. ``"atm_spread"`` makes it a SPREAD row:
    the prior's ATM total variance rides along (re-expressed at the node ``tau``
    exactly like the var-swap level, ``w(0)·tau/prior_tau`` — the rescale
    cancels in vol space) so each calibrator compares (σ_vs − σ_atm) model vs
    prior. Market var-swap quote rows (``varswap_target``) are ALWAYS absolute:
    a quote is the truth, not a shape."""
    if options.priorVarSwapMode == "atm_spread":
        w_atm = float(
            np.maximum(np.asarray(moved_w(np.array([0.0])), dtype=float), 1e-12)[0]
        ) * (tau / prior_tau)
        return VarSwapTarget(
            total_var=total_var, weight=weight, t=float(tau),
            mode="atm_spread", atm_total_var=w_atm,
        )
    return VarSwapTarget(total_var=total_var, weight=weight, t=float(tau))


def _persistence_targets(
    state: AppState, ticker: str, iso: str, k: np.ndarray, weights: np.ndarray | None, prepared
) -> PriorTargets:
    """Resolve the active prior-persistence targets for a node (design note §10).

    Routed by ``OptionsSettings.priorPersistenceMode`` (volfit.api.prior_mode):
    ``strike_gap`` builds the legacy data-gap strike anchor (volfit.calib.prior);
    ``quote_operator`` / ``hybrid`` build the signed quote-operator prior
    (volfit.calib.operators) — the SAME object every parametric model and the LV
    surface consume. ``off`` / ``overlay`` / ``graph_only`` (and ``smile_factor``
    until Phase 6) add no calibration penalty.

    The MODE is the single source of truth (Phase 8 retired the ``autoLoadPrior``
    master): a non-penalty mode (off / overlay / graph_only) or no active fetched
    prior ⇒ empty targets ⇒ byte-identical. Existing desks are preserved by the
    store-load migration (legacy ``autoLoadPrior`` off → mode ``off``). The prior's
    LQD backbone is transported to the node's forward under the dynamics regime so it
    is spot-consistent with the live quotes."""
    options = state.options()
    plan = resolve_prior_mode(options)
    if not plan.any_calibration_prior:
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
            # Carrier (absolute level vs ATM spread) via priorVarSwapMode.
            w_vs = varswap_total_variance(moved.implied_w) * (prepared.tau / node.tau)
            pvs = _prior_varswap(
                options, moved.implied_w, node.tau, prepared.tau, float(w_vs), budget * unmet
            )
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
            pvs = _prior_varswap(
                options, moved.implied_w, node.tau, prepared.tau, vs.prior_total_var, vs.weight
            )
        return PriorTargets(operator_prior=target, prior_var_swap=pvs)

    # operator / hybrid: the signed quote-operator prior (ATM/RR/BF, plus the
    # WingL/WingR deep-wing slope rows when in the set; design note §5).
    # Guarded: under the active-filter auto-exclusion only the tail anchor
    # survives — unless wingOperatorsUnderActiveFilter (Note 15 §6.3 carve-out):
    # then the WingL/WingR rows ALONE persist (disjoint from the filtered
    # handles; VarSwap stays with the body switch) and ``prior_targets`` merges
    # them beside the MAP rows.
    target = None
    pvs = None
    if plan.operators or plan.wing_operators:
        op_set = list(options.priorOperatorSet)
        if not plan.operators:
            op_set = [n for n in op_set if n in WING_OPERATORS]
        budget = (options.priorOperatorStrengthPct / 100.0) * sum_w
        target, vs = build_operator_prior(
            moved.implied_w, node.tau, prepared.tau, k, weights, budget,
            op_set=op_set,
            collar_sign=options.collarSign,
            required_precision=options.priorOperatorRequiredPrecision,
            gap_exponent=options.priorOperatorGapExponent,
            bandwidth=options.priorOperatorBandwidth,
            anchor_deltas=tuple(options.priorAnchorDeltas),
            wing_scale=options.priorWingSlopeScale,
        )
        if vs.active and vs.weight > 0.0:
            pvs = _prior_varswap(
                options, moved.implied_w, node.tau, prepared.tau, vs.prior_total_var, vs.weight
            )
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


def prior_diagnostics(state: AppState, ticker: str, iso: str, fit_mode: str = "mid"):
    """Per-node prior-persistence diagnostics (design note §9.4): which operators /
    factors the prior is persisting, their observation vs required precision, the
    activation gap and the final weight — so the prior is auditable, not a hidden
    stabilizer. Best-effort: an inactive payload when the node has no chain / prior."""
    from volfit.api.schemas import PriorDiagnostics, PriorOperatorDiag

    mode = state.options().priorPersistenceMode
    try:
        expiry = state.resolve_expiry(ticker, iso)
        iso = expiry.isoformat()
        prepared = prepared_quotes(state, ticker, expiry)
        k, w, _ = edited_fit_inputs(state, ticker, iso, prepared, None)
        weights = resolve_weights(state.fit_settings().weightScheme, k, w)
        pt = prior_targets(state, ticker, iso, k, weights, prepared, fit_mode)
    except Exception:  # noqa: BLE001 — diagnostics are advisory, must never 500
        return PriorDiagnostics(mode=mode, active=False)
    ops = [
        PriorOperatorDiag(**d)
        for d in (pt.operator_prior.diagnostics if pt.operator_prior is not None else [])
    ]
    vs_vol = vs_w = None
    if pt.prior_var_swap is not None and prepared.tau > 0.0:
        vs_vol = float(math.sqrt(max(pt.prior_var_swap.total_var, 0.0) / prepared.tau))
        vs_w = float(pt.prior_var_swap.weight)
    anchor_n = int(pt.prior_anchor.k.size) if pt.prior_anchor is not None else None
    active = bool(ops) or pt.prior_var_swap is not None or pt.prior_anchor is not None
    return PriorDiagnostics(
        mode=mode, active=active, operators=ops,
        varSwapPriorVol=vs_vol, varSwapWeight=vs_w, strikeAnchorCount=anchor_n,
    )


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
    edited_fit_inputs. Haircut and the tick-width floor come from fit
    settings (refits via the settings version)."""
    session = state.session_if_exists((ticker, iso))
    edits = {} if session is None else session.edits
    settings = state.fit_settings()
    return apply_band_edits(
        prepared, edits, fit_mode, settings.haircut,
        tick_floor_ticks=settings.bandTickFloorTicks,
    )


def edited_band_full(
    state: AppState, ticker: str, iso: str, prepared: PreparedQuotes, fit_mode: str
):
    """The per-quote fit-target band in FULL prepared index space (V3.4 item 4).

    Exactly the ``apply_band_edits``/``resolve_band`` path the fit consumes
    (amended-mid recentering + the haircut collapse clamp included), but with
    excluded rows kept so every QuoteBand can carry its would-be target
    (``targetLo``/``targetHi``; the UI dims excluded quotes). None for "mid"."""
    session = state.session_if_exists((ticker, iso))
    edits = {} if session is None else session.edits
    settings = state.fit_settings()
    return apply_band_edits(
        prepared, edits, fit_mode, settings.haircut, include_excluded=True,
        tick_floor_ticks=settings.bandTickFloorTicks,
    )


def _overlay_settings(settings) -> OverlaySettings:
    """The picklable FitSettings subset the overlay fit reads (fit_task)."""
    return OverlaySettings(
        sviPenaltyWeight=settings.sviPenaltyWeight,
        leeSlopeMax=settings.leeSlopeMax,
        midAnchorWeight=settings.midAnchorWeight,
        nCores=settings.nCores,
        sigmoidRidge=settings.sigmoidRidge,
        sviChart=settings.sviChart,
        bellyRepair=settings.bellyRepair,
        mcsChart=settings.mcsChart,
        midAnchorTauRef=settings.midAnchorTauRef,
        robustLoss=settings.robustLoss,
        robustFScale=settings.robustFScale,
        overlayPriceResiduals=settings.overlayPriceResiduals,
    )


def _slice_task(
    state: AppState,
    ticker: str,
    iso: str,
    prepared: PreparedQuotes,
    fit_mode: str,
    *,
    init=None,
    prev: CalibrationResult | None = None,
    prev_display: DisplayFit | None = None,
    prev_k: np.ndarray | None = None,
    next_display: DisplayFit | None = None,
    next_k: np.ndarray | None = None,
    enforce_calendar: bool = False,
    allow_prepass: bool = False,
    with_fit: bool = True,
    with_overlay: bool = True,
) -> SliceFitTask:
    """Assemble one node's slice-fit work as a pure, picklable task.

    Every state read (edited quotes, weights, band, var-swap quote, prior /
    filter targets, hyperparameters) happens HERE on the calling thread; the
    returned task can then run inline or in a fit-pool worker with identical
    results (volfit.calib.fit_task.run_slice_fit is the single code path).

    ``init`` is the LQD warm start (the surface sweep's previous expiry);
    ``prev``/``prev_display`` supply the calendar floors under
    ``enforce_calendar`` — BOTH confined to the common quote support of the
    two expiries (outside the intersection of the retained spans either slice
    is pure extrapolation and a wing mismatch is a phantom violation; the
    published wings are governed by the Notes 09/10 extrap machinery instead).
    ``prev_k`` is the previous expiry's retained (edited) log-moneyness array
    for that intersection; None falls back to confining by THIS expiry's span
    alone (legacy callers). ``next_display``/``next_k`` (symmetric overlay
    repair, phase B only) supply the NEXT, longer expiry's displayed slice as
    a confined variance CEILING for the overlay — the two-sided target that
    splits a violating pair's correction instead of pushing it all one way.
    ``allow_prepass`` opts the single-node path into the two-pass
    priorDataOnlyPrepass; ``with_fit=False`` builds an overlay-only task
    (display_overlay), ``with_overlay=False`` an LQD-only task."""
    settings = state.fit_settings()
    k, w, _ = edited_fit_inputs(state, ticker, iso, prepared, None)
    weights = resolve_weights(settings.weightScheme, k, w)
    band = edited_band(state, ticker, iso, prepared, fit_mode)
    vs = varswap_target(state, ticker, iso, k, weights, prepared.tau)
    pt = prior_targets(state, ticker, iso, k, weights, prepared, fit_mode)

    calibrate = prepass = None
    if with_fit:
        n_order = effective_lqd_order(settings.nOrder, k.size)
        cal_k = cal_pfloor = cal_taper = None
        if enforce_calendar and prev is not None:
            window = common_support(prev_k if prev_k is not None else k, k)
            confined = (
                confined_calendar_floor(
                    prev.slice, window, n=calendar_grid_nodes(settings.nOrder)
                )
                if window is not None
                else None
            )
            if confined is not None:
                cal_k, cal_pfloor, cal_taper = confined
        base = dict(
            k=k, w_quotes=w, t=prepared.tau, n_order=n_order,
            weights=weights, reg_lambda=settings.regLambda,
            reg_power=settings.regPower, band=band,
            barrier_center=settings.barrierCenter,
            barrier_scale=settings.barrierScale,
            mid_anchor_weight=settings.midAnchorWeight, var_swap=vs,
            # Short-dated objective knobs (defaults byte-identical): the tau
            # anchor ref rides prepare_residual_args (so the joint symmetric
            # stack sees the same attenuated anchor); the robust IRLS pair is
            # solve orchestration in calibrate_slice (prepare accepts and
            # ignores it when the joint stack forwards these kwargs).
            mid_anchor_tau_ref=settings.midAnchorTauRef,
            robust_loss=settings.robustLoss,
            robust_f_scale=settings.robustFScale,
            coords=settings.lqdCoords,
            # Generalized tails (arc Phases 2-3): the fixed per-side
            # exponents ride every LQD fit — per-underlier override first,
            # global pair otherwise (the ratified per-underlier alpha scope);
            # the settings version already keys the fit cache, so changing a
            # tail scenario refits cleanly everywhere.
            alpha_left=settings.tail_alphas(ticker)[0],
            alpha_right=settings.tail_alphas(ticker)[1],
        )
        # Two-pass "don't damp the signal" (opt-in, design note §5.4): fit
        # data-only first so the data-fitted level/shape is the seed, then refit
        # with the gated prior initialized from it. Single-node path only; the
        # warm-started surface sweep keeps its previous-expiry seed.
        if (
            allow_prepass
            and init is None
            and state.options().priorDataOnlyPrepass
            and (pt.operator_prior is not None or pt.prior_anchor is not None)
        ):
            prepass = dict(base)
        calibrate = dict(
            base,
            # Warm start only from a same-order seed (a mismatched order would
            # be the wrong vector length); the prepass seed always matches.
            init=init if getattr(init, "order", None) == n_order else None,
            calendar_k=cal_k, calendar_price_floor=cal_pfloor,
            calendar_weight=state.options().calendarWeight,
            calendar_taper=cal_taper,
            prior_anchor=pt.prior_anchor, prior_var_swap=pt.prior_var_swap,
            operator_prior=pt.operator_prior,
        )

    overlay = None
    if with_overlay and settings.model != "lqd":
        o_floor = o_ceil = None
        # Confined to the COMMON quote support (empty intersection => no
        # pointwise floor): the later expiry's own span alone still lets a
        # wider far slice sample the near wing's extrapolation. The sigmoid
        # family extends the confined grid by the wing pad (V3.1 leg 4a,
        # calib.calendar.variance_floor_grid_winged): its zero-wing kernels
        # make the extension safe, and wing crossings are exactly what the
        # confined grid misses. Same node budget either way.
        # OptionsSettings.calendarFloorPadZ (the short-dated wing-crossing
        # knob) overrides the scope for BOTH families: floor AND ceiling grids
        # winged at the user's pad; None keeps the per-family branches below
        # byte-identical.
        pad_z = state.options().calendarFloorPadZ
        if pad_z is not None:
            def _o_grid(k_other):
                return variance_floor_grid_winged(k_other, k, w, prepared.tau, pad_z=pad_z)
        elif settings.model == "sigmoid":
            def _o_grid(k_other):
                return variance_floor_grid_winged(k_other, k, w, prepared.tau)
        else:
            def _o_grid(k_other):
                return variance_floor_grid_common(k_other, k)
        if enforce_calendar and prev_display is not None:
            o_grid = _o_grid(prev_k if prev_k is not None else k)
            if o_grid is not None:
                o_floor = variance_floor_targets(prev_display.slice, o_grid)
        if enforce_calendar and next_display is not None:
            c_grid = _o_grid(next_k if next_k is not None else k)
            if c_grid is not None:
                o_ceil = variance_floor_targets(next_display.slice, c_grid)
        # Tapered extrapolated-region enforcement (Notes 09/10 Phase 2): the
        # envelope geometry is built ONCE from the quotes (+ the previous
        # displayed slice for the calendar floor / slope order); OFF ⇒ None ⇒
        # byte-identical overlay fits.
        o_extrap = None
        if state.options().extrapEnforce:
            o_extrap = build_extrap_target(
                k, w,
                prev_slice=prev_display.slice if prev_display is not None else None,
                prev_lee=(
                    (prev_display.lee_left, prev_display.lee_right)
                    if prev_display is not None
                    else None
                ),
            )
        overlay = dict(
            model=settings.model, k=k, w=w, t=prepared.tau, weights=weights,
            settings=_overlay_settings(settings), band=band, var_swap=vs,
            calendar_floor=o_floor, calendar_ceiling=o_ceil,
            calendar_weight=state.options().calendarWeight,
            prior_anchor=pt.prior_anchor, operator_prior=pt.operator_prior,
            prior_var_swap=pt.prior_var_swap,
            wing_penalty=(state.options().sivWingPenaltyPct / 100.0) * WING_PENALTY_BASE,
            extrap=o_extrap,
        )

    # Retain the solver's solution Jacobian / residual on EVERY fit (pure
    # side-channel, the fit itself is byte-identical): it feeds the quote-
    # derived error bars (api/fit_uncertainty) always, and the observation
    # filter's commit hook when the filter is on (which self-gates on mode).
    return SliceFitTask(calibrate=calibrate, prepass=prepass, overlay=overlay, want_diag=with_fit)


def retained_k(
    state: AppState, ticker: str, iso: str, prepared: PreparedQuotes
) -> np.ndarray:
    """The log-moneyness array a fit of this node actually retains (after quote
    edits) — the quote-support side of the calendar confinement window."""
    k, _, _ = edited_fit_inputs(state, ticker, iso, prepared, None)
    return k


def display_overlay(
    state: AppState,
    ticker: str,
    iso: str,
    prepared: PreparedQuotes,
    fit_mode: str,
    prev_display: DisplayFit | None = None,
    enforce_calendar: bool = False,
    prev_k: np.ndarray | None = None,
):
    """The non-LQD display overlay for a node (None for LQD), fit to the same
    edited quotes, band and weights the LQD calibration uses.

    ``prev_display`` is the previous (shorter-T) expiry's overlay, threaded by the
    calendar-coupled surface loop; with ``enforce_calendar`` it supplies a
    model-agnostic total-variance floor (volfit.calib.calendar) so the SVI /
    sigmoid overlay respects calendar order just as the LQD backbone does. Both
    omitted (the single-node path) leaves the overlay byte-identical."""
    task = _slice_task(
        state, ticker, iso, prepared, fit_mode,
        prev_display=prev_display, prev_k=prev_k,
        enforce_calendar=enforce_calendar, with_fit=False,
    )
    return run_slice_fit(task).display


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

    Under ``OptionsSettings.calendarOnRefit`` (with ``enforceCalendar``) this
    lone fit keeps the surface pass's cross-expiry coupling: the FRESH
    committed neighbour slices in the selected ladder become its confined
    calendar floor (previous expiry: LQD price floor from the committed
    backbone + overlay variance floor from the displayed slice) and ceiling
    (next expiry, overlay) — exactly the sequential-pass construction,
    read-only (a stale/missing side is skipped, never refit). The neighbours
    are then genuine fit inputs, fingerprinted into ``fit_key``. The warm
    start stays None: the path remains cold-started and path-independent.

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
        # Calendar-on-refit: thread the fresh committed neighbours (docstring).
        # OFF (the default), or no usable neighbour: every extra argument below
        # is None/False — the historical task, byte-identical.
        prev_ctx = next_ctx = None
        options = state.options()
        if options.calendarOnRefit and options.enforceCalendar:
            prev_iso, next_iso = _neighbour_isos(state, ticker, iso)
            prev_ctx = _neighbour_context(state, ticker, prev_iso, fit_mode)
            next_ctx = _neighbour_context(state, ticker, next_iso, fit_mode)
            if prev_ctx is not None or next_ctx is not None:
                act.detail("calendar context from committed neighbours")
        # The LQD backbone fit + the non-LQD display overlay (same edited quotes,
        # band and prior — Phase 3/5) as ONE pure task: a background Calibrate
        # thunk routes it to the fit process pool (volfit.api.fit_pool), an
        # interactive call runs it inline — byte-identical either way.
        task = _slice_task(
            state, ticker, iso, prepared, fit_mode, init=init, allow_prepass=True,
            prev=prev_ctx[0].result if prev_ctx is not None else None,
            prev_display=prev_ctx[0].display if prev_ctx is not None else None,
            prev_k=prev_ctx[1] if prev_ctx is not None else None,
            next_display=next_ctx[0].display if next_ctx is not None else None,
            next_k=next_ctx[1] if next_ctx is not None else None,
            enforce_calendar=prev_ctx is not None or next_ctx is not None,
        )
        if task.prepass is not None:
            act.detail("data-only prepass")
        act.detail(f"fitting {_model_label(settings.model)} smile")
        outcome = fit_pool.execute(task)
    record = FitRecord(prepared=prepared, result=outcome.result, display=outcome.display)
    return commit_record(state, ticker, iso, fit_mode, record, outcome.solver_diag)


# --------------------------------------------------- fast spot-move transport
#: Dividend modes whose forward shifts ADDITIVELY with spot (discrete cash legs:
#: Delta F_T = Delta S * e^{r t}); the rest scale multiplicatively (F ~ S).
_CASH_DIV_MODES = ("discrete_absolute", "mixed")


def spot_forward_shift(
    state: AppState,
    ticker: str,
    expiry: date,
    f0: float,
    discount: float,
    t: float,
    shift: float | None = None,
) -> tuple[float, float]:
    """(F_T^1, h_T) for the active spot shift: the new forward and its log-ratio.

    Per Docs/spot_move_vol_surface_note_updated.tex, ``h`` must come from the
    forward, not the raw spot ratio. Continuous-yield / proportional dividends
    give the multiplicative ``F_T^1 = F_T^0 (1 + shift)``; discrete CASH dividends
    give the additive ``Delta F_T = Delta S e^{r t}`` (so ``h_T`` differs per
    expiry). Returns ``(f0, 0.0)`` when no shift is active. Shared by the
    parametric slice transport and the affine LV-surface transport. ``shift``
    overrides the ACTIVE shift (the live quote-table stream passes the streamed
    spot's return so live IVs invert at the live forward); None = the active one.
    """
    shift = state.spot_shift(ticker) if shift is None else shift
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


def _spot_transport_forward(
    state: AppState, ticker: str, expiry: date, prepared, shift: float | None = None
) -> tuple[float, float]:
    """(F_T^1, h_T) for a prepared slice — thin wrapper over spot_forward_shift."""
    return spot_forward_shift(
        state, ticker, expiry, float(prepared.forward), float(prepared.discount), float(prepared.t),
        shift=shift,
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


def transport_record(
    state: AppState, ticker: str, iso: str, record: FitRecord, shift: float | None = None
) -> FitRecord:
    """Transport an anchor fit for the ticker's active spot shift (no refit).

    Returns ``record`` unchanged when no shift is active. Otherwise the displayed
    smile is moved per the Options dynamics regime (volfit.dynamics.transport):
    the new forward F^1 and re-indexed quotes (fixed strikes -> new moneyness
    k - h) go on the prepared inputs, and the transported slice is attached as a
    DisplayFit so the chart, diagnostics, surface, term, density, var-swap and the
    Dupire local-vol extraction all follow it. ``result`` (the LQD anchor) is kept
    intact so the graph universe still reads exact LQD coordinates. ``shift``
    overrides the ACTIVE shift (the Smile Viewer's prevailing-spot layer and the
    live tick stream roll the fit to THEIR spot); None = the active one.
    """
    shift = state.spot_shift(ticker) if shift is None else float(shift)
    if shift == 0.0:
        return record
    expiry = date.fromisoformat(iso)
    f1, h = _spot_transport_forward(state, ticker, expiry, record.prepared, shift)
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


def _display_grid(k_lo: float, k_hi: float, core_lo: float, core_hi: float) -> np.ndarray:
    """N_MODEL_POINTS display abscissae: N_CORE_POINTS dense over the observed
    quote range [core_lo, core_hi], the rest split over the extrapolation wings
    proportionally to their width. On a short-dated slice the quotes cover a few
    percent of the display range — uniform sampling rendered the whole smile
    with ~10 segments (kinked to the eye) while wasting the budget on the wings."""
    core_lo, core_hi = max(k_lo, core_lo), min(k_hi, core_hi)
    n_wings = N_MODEL_POINTS - N_CORE_POINTS
    left, right = core_lo - k_lo, k_hi - core_hi
    if left + right <= 0.0:  # quotes span the whole display range: plain uniform
        return np.linspace(k_lo, k_hi, N_MODEL_POINTS)
    n_left = int(round(n_wings * left / (left + right)))
    n_right = n_wings - n_left
    return np.concatenate([
        np.linspace(k_lo, core_lo, n_left, endpoint=False),
        np.linspace(core_lo, core_hi, N_CORE_POINTS, endpoint=(n_right == 0)),
        np.linspace(core_hi, k_hi, n_right + 1)[1:] if n_right else np.empty(0),
    ])


#: Normalized time-value floor below which a Black inversion is numerically
#: meaningless (the publication-chart rule of book ch. 2: remote wings are
#: evaluated from the wing law, never from inverting prices this small).
_WING_TV_FLOOR = 1e-14


def alpha_law_wings(slice_, grid: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Publication-chart rule for light tails (arc Phase 3): on a side with
    alpha > 0, replace the implied variance BEYOND the outermost reliably
    priced strike with the alpha-aware wing law (eq. rightsublinearwing),
    matched additively to the central inversion at that seam — the curve
    stays continuous and shows the certified asymptote instead of the noise
    of inverting underflowed prices. alpha = 0 sides are untouched (their
    exponential tails invert cleanly — the historical, byte-identical path).
    """
    from volfit.models.lqd.basis import wing_law

    params = slice_.params
    law_l, law_r = wing_law(params)
    w = np.asarray(w, dtype=float).copy()
    c = np.asarray(slice_.call_price(grid), dtype=float)
    # OTM time value, the put side priced directly (models.lqd.putside): the
    # parity subtraction c - (1 - e^k) floors the left tv at ~1e-16 absolute,
    # which marked the whole short-dated lower wing unreliable regardless of
    # its true (representable) time value.
    tv = np.where(grid > 0.0, c, np.asarray(slice_.put_price(grid), dtype=float))
    unreliable = (tv < _WING_TV_FLOOR) | ~np.isfinite(w) | (w <= 0.0)

    if params.alpha_right > 0.0:
        bad_r = unreliable & (grid > 0.0)
        if bad_r.any():
            first_bad = int(np.argmax(bad_r))
            if first_bad > 0:
                seam_k, seam_w = float(grid[first_bad - 1]), float(w[first_bad - 1])
                patch = grid >= grid[first_bad]
                w[patch] = seam_w + law_r.coeff * (
                    np.abs(grid[patch]) ** law_r.exponent - abs(seam_k) ** law_r.exponent
                )
    if params.alpha_left > 0.0:
        bad_l = unreliable & (grid < 0.0)
        if bad_l.any():
            last_bad = int(len(grid) - 1 - np.argmax(bad_l[::-1]))
            if last_bad < len(grid) - 1:
                seam_k, seam_w = float(grid[last_bad + 1]), float(w[last_bad + 1])
                patch = grid <= grid[last_bad]
                w[patch] = seam_w + law_l.coeff * (
                    np.abs(grid[patch]) ** law_l.exponent - abs(seam_k) ** law_l.exponent
                )
    return w


def model_curve(record: FitRecord) -> list[SmilePoint]:
    """Sample the displayed slice's IV curve, extended to at least
    k ∈ [-1.4, 1] so the model wings are drawn well beyond the observed quotes
    (the put wing reaches further). The smile's brush still defaults to the
    observed range (SmileData.kMin/kMax); zooming or panning out reveals the
    extension. The grid is denser inside the observed range (``_display_grid``).
    Slices with a positive tail exponent get their remote wings from the
    alpha-aware wing law instead of underflowed-price inversion
    (``alpha_law_wings`` — the book's publication-chart rule)."""
    k_obs_lo = float(record.prepared.k.min()) - K_PAD
    k_obs_hi = float(record.prepared.k.max()) + K_PAD
    k_lo = min(K_DISPLAY_LO, k_obs_lo)
    k_hi = max(K_DISPLAY_HI, k_obs_hi)
    grid = _display_grid(k_lo, k_hi, k_obs_lo, k_obs_hi)
    sl = displayed_slice(record)
    w = np.maximum(sl.implied_w(grid), 0.0)
    p = getattr(sl, "params", None)
    if p is not None and (
        getattr(p, "alpha_left", 0.0) > 0.0 or getattr(p, "alpha_right", 0.0) > 0.0
    ):
        w = alpha_law_wings(sl, grid, w)
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
    the model curve's own k grid so the dotted line aligns with the smile.

    In persistence mode ``off`` (``draw_overlay`` False) no prior is drawn at all —
    the viewer shows the pure current-market fit (design note §10)."""
    from volfit.api import prior_transport

    if not resolve_prior_mode(state.options()).draw_overlay:
        return [], False
    node = prior_transport.prior_node(state.active_prior(ticker), iso)
    if node is not None:
        grid = np.array([p.k for p in model], dtype=float)
        points = prior_transport.transported_prior_points(
            node, float(record.prepared.forward), state.dynamics_regime(), grid
        )
        return points, True
    saved = state.get_prior((ticker, iso))
    return (list(saved.curve) if saved is not None else list(model)), False


def varswap_info(
    state: AppState, ticker: str, iso: str, record: FitRecord, fit_mode: str = "mid"
) -> VarSwapInfo:
    """Var-swap quote state + the model's own fair var-swap vol for a node.

    V3.6 optional readouts ride along: ``basisBp`` = (quote − model) · 1e4 vol
    bp (sign: positive ⇒ quote above model); ``weightPct`` echoes the Options
    percentage while the feature is on; ``weightAbs`` is the RESOLVED absolute
    penalty weight from ``varswap_target`` (pct/100 · Σ quote weights, None
    when no active target); ``stale`` mirrors SmileData.stale for this node;
    ``rmsShare`` is the var-swap term's fraction of the node's total weighted
    squared vol error (the node_error_terms decomposition, in [0, 1]).

    Strip-vs-tails split (V3.6 rider, volfit.api.varswap_split): the displayed
    slice's replication on the standard ±6 grid, partitioned over the INCLUDED
    quotes' k span — ``stripVarShare`` / ``tailVarShareLeft`` /
    ``tailVarShareRight`` / ``stripKLo`` / ``stripKHi``. Read-only display."""
    session = state.varswap_session_if_exists((ticker, iso))
    model_vol = float(np.sqrt(displayed_var_swap_w(record) / record.prepared.tau))
    options = state.options()
    enabled = options.varSwapEnabled
    level = session.state.level if session is not None else None
    basis_bp = None if level is None else (float(level) - model_vol) * 1e4
    weight_abs = rms_share = None
    prepared = record.prepared
    k, w, _ = edited_fit_inputs(state, ticker, iso, prepared, None)
    weights = resolve_weights(state.fit_settings().weightScheme, k, w)
    target = varswap_target(state, ticker, iso, k, weights, prepared.tau)
    if target is not None:
        weight_abs = float(target.weight)
        # Share of the node's total weighted squared error carried by the
        # var-swap term — the same (model, quote, weight) triple the RMS uses.
        vs = _varswap_rms_term(state, ticker, iso, record, k, weights, prepared.tau)
        num, _den = _node_rms_terms(state, ticker, iso, record, fit_mode)
        if vs is not None and num > 0.0:
            m_vol, q_vol, wgt = vs
            rms_share = float(min(1.0, max(0.0, wgt * (m_vol - q_vol) ** 2 / num)))
    return VarSwapInfo(
        level=level,
        excluded=session.state.excluded if session is not None else False,
        modelVol=model_vol,
        enabled=enabled,
        canUndo=session.can_undo if session is not None else False,
        canRedo=session.can_redo if session is not None else False,
        basisBp=basis_bp,
        weightPct=options.varSwapWeightPct if enabled else None,
        weightAbs=weight_abs,
        stale=node_dirty(state, ticker, iso, fit_mode),
        rmsShare=rms_share,
        # Hard-pin echo: True only when the pin actually escalates an ACTIVE
        # market row on this node (varswap_target applies it); None when off.
        pinned=(bool(options.varSwapHardPin) and target is not None) if enabled else None,
        # Strip-vs-tails split of the displayed model's replication over the
        # included quotes' k span (all None when there is nothing to split).
        **split_fields(parametric_varswap_split(record, k)),
    )


def model_info(record: FitRecord) -> ModelInfo:
    """The model family + hyperparameters that produced the DISPLAYED fit.

    Read off the actual displayed slice — LQD when there is no overlay (degree N
    from the fitted Legendre params), else the overlay family (Multi-Core Sigmoid
    reports its fitted core count R; SVI-JW has no hyperparameter). This reflects
    what is drawn even for a frozen/stale node, so the diagnostics panel always
    names the model the chart actually shows, not the (possibly newer) settings."""
    display = record.display
    provenance = getattr(record, "provenance", "fit")
    if display is None:  # the analytic LQD backbone is displayed
        return ModelInfo(
            id="lqd",
            label="LQD",
            params=[ModelParam(label="Degree N", value=str(record.result.params.order))],
            provenance=provenance,
        )
    if display.model == "sigmoid":
        return ModelInfo(
            id="sigmoid",
            label="Multi-Core Sigmoid",
            params=[ModelParam(label="Cores R", value=str(len(display.slice.cores)))],
            provenance=provenance,
        )
    return ModelInfo(id="svi", label="SVI-JW", provenance=provenance)  # 5 raw params, no hyperparameter


def prepare_slice(state: AppState, ticker: str, expiry_iso: str):
    """Prepare one expiry's quotes in IV space WITHOUT calibrating — for the
    pre-Calibrate display (quote bands + the implied forward). ``None`` when no
    chain has been fetched or the expiry has no implied forward yet."""
    prepared, _reason = prepare_slice_or_reason(state, ticker, expiry_iso)
    return prepared


#: The named degraded-market conditions (R2 item 10 degraded mode v1): a node
#: whose preparation fails for one of these is UNFITTABLE DATA — the viewer
#: serves the transported active prior (the existing dotted overlay) labeled
#: with the reason, instead of the misleading "no fit yet" cue. Substrings of
#: the calm errors raised by state.resolved_forward / prepare_quotes.
_DEGRADED_CONDITIONS = (
    ("no parity forward", "no_parity_forward"),
    ("no two-sided OTM quotes", "no_fittable_market"),
)


def prepare_slice_or_reason(state: AppState, ticker: str, expiry_iso: str):
    """``(prepared, degraded_reason)`` — exactly one of the two is non-None,
    except the plain not-ready cases (no chain fetched / transient failure)
    where both are None. The reason is one of the NAMED unfittable-market
    conditions; anything unnamed stays a legacy silent None (no false
    "degraded" labels on transient feed misses)."""
    if not state.has_quotes(ticker):
        return None, None
    expiry = state.resolve_expiry(ticker, expiry_iso)
    try:
        return prepared_quotes(state, ticker, expiry), None  # de-Am memoized
    except Exception as exc:  # noqa: BLE001 — classify the calm named cases
        msg = str(exc)
        for needle, reason in _DEGRADED_CONDITIONS:
            if needle in msg:
                return None, reason
        return None, None  # no forward yet / degenerate slice: legacy behavior


def _no_fit_prior(
    state: AppState, ticker: str, iso: str, forward: float
) -> tuple[list[SmilePoint], bool]:
    """The dotted ACTIVE prior on a default grid (transported to ``forward`` under
    the dynamics regime), or ``([], False)`` when none exists / no forward yet.

    Suppressed in persistence mode ``off`` (``draw_overlay`` False), like the
    post-fit overlay, so a gated node shows no prior either."""
    if forward <= 0.0 or not resolve_prior_mode(state.options()).draw_overlay:
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
    prepared, degraded = prepare_slice_or_reason(state, ticker, iso)
    session = state.session_if_exists((ticker, iso))
    quotes: list[QuoteBand] = []
    if prepared is not None:
        band = edited_band_full(state, ticker, iso, prepared, fit_mode)
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
                    strike=float(prepared.forward) * math.exp(float(k)),
                    targetLo=float(band.iv_lo[i]) if band is not None else None,
                    targetHi=float(band.iv_hi[i]) if band is not None else None,
                )
            )
    forward = float(prepared.forward) if prepared is not None else 0.0
    # No fit: the market frame still carries the prevailing quotes + target (no
    # rolled curve); no calibration frame.
    market = smile_layers.market_layer(state, ticker, iso, fit_mode, None, quotes, prepared)
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
        degraded=degraded,
        market=market,
        calib=None,
    )


def smile_payload(state: AppState, ticker: str, expiry_iso: str, fit_mode: str) -> SmileData:
    """Assemble the full SmileData payload for one (ticker, expiry) node."""
    try:
        record = fit_or_get(state, ticker, expiry_iso, fit_mode)
    except Exception as exc:  # noqa: BLE001 — absorb ONLY the named conditions
        # Degraded mode v1: in the ungated workflow an unfittable chain used to
        # escape as a raw error (an HTTP 500 on the very nodes a 0DTE desk
        # watches into the close). The NAMED degraded-market conditions fall
        # through to the no-fit payload, which serves the dotted transported
        # prior and labels the reason; anything unnamed keeps raising.
        if not any(needle in str(exc) for needle, _ in _DEGRADED_CONDITIONS):
            raise
        record = None
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

    # Quote-derived error bars of the DISPLAYED (frozen) calibration —
    # (σ_atm, σ_skew, σ_curv) from the fit's own Jacobian + bid-ask noise
    # (api/fit_uncertainty; advisory, None when unavailable).
    stds = fit_uncertainty.handle_stds(state, ticker, iso, fit_mode)
    atm_std, skew_std, curv_std = stds if stds is not None else (None, None, None)

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
            atmVolStd=atm_std,
            skewStd=skew_std,
            curvStd=curv_std,
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
            atmVolStd=atm_std,
            skewStd=skew_std,
            curvStd=curv_std,
        )
    # Every prepared quote is listed (excluded dimmed by the UI); an amended
    # quote shows its overridden mid, bid/ask stay the market band. The
    # fit-target edges ride along (None in "mid" mode), resolved by the same
    # band path the fit itself uses (edited_band_full).
    band = edited_band_full(state, ticker, iso, prepared, fit_mode)
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
                strike=float(prepared.forward) * math.exp(float(k)),
                targetLo=float(band.iv_lo[i]) if band is not None else None,
                targetHi=float(band.iv_hi[i]) if band is not None else None,
            )
        )
    # The two comparable frames (api/smile_layers): the calibration frame is
    # the UN-transported base (the fit on its own spot); the market frame is
    # the latest fetched chain + the fit rolled to the prevailing spot.
    base = displayed_base(state, ticker, iso, fit_mode)
    market = smile_layers.market_layer(
        state, ticker, iso, fit_mode, base, quotes, prepare_slice(state, ticker, iso), model
    )
    return SmileData(
        ticker=ticker,
        expiry=expiry_iso,
        T=prepared.t,
        forward=prepared.forward,
        model=model,
        market=market,
        calib=smile_layers.calib_layer(base),
        prior=prior,
        priorTransported=prior_transported,
        quotes=quotes,
        # Brush extent / default window stay the OBSERVED range, even though the
        # model curve above is sampled out to ±1 (revealed by zoom / pan).
        kMin=float(prepared.k.min()) - K_PAD,
        kMax=float(prepared.k.max()) + K_PAD,
        diagnostics=diagnostics,
        modelInfo=model_info(record),
        varSwap=varswap_info(state, ticker, iso, record, fit_mode),
        canUndo=session.can_undo if session is not None else False,
        canRedo=session.can_redo if session is not None else False,
        stale=node_dirty(state, ticker, iso, fit_mode),
        anchorModel=anchor_model,
        surfaceRmsError=surface_rms,
    )


# -------------------------------------------------------------- surface fit
def ordered_expiries(state: AppState, ticker: str, expiries) -> list[date]:
    """Ascending-maturity order for the calendar-coupling chains (R2 item 10:
    absolute-timestamp calendar constraints for adjacent dailies).

    Ordered by the schema-v7 settlement INSTANT when the chain carries one —
    an AM-settled index expiry (09:30 ET) precedes a PM daily (16:00 ET) on
    the SAME date — falling back to end-of-day for expiries without a
    settlement record, which reproduces plain date order exactly (settlement
    instants never cross calendar dates), so every current chain is
    BYTE-IDENTICAL under this key.

    Known model limit, documented rather than hidden: chains key expiries by
    DATE, so a genuine same-date AM/PM PAIR (an SPX quarterly colliding with
    an SPXW EOM) still collapses to one node at ingestion; this seam orders
    whatever nodes exist, and splitting the pair needs an expiry-key
    redesign (ROADMAP note)."""
    snap = state.loaded_snapshot(ticker)
    settlement = (snap.settlement if snap is not None else None) or {}

    def key(e: date) -> datetime:
        s = settlement.get(e)
        return s.settle if s is not None else datetime.combine(e, time.max)

    return sorted(expiries, key=key)


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
        for expiry in ordered_expiries(state, ticker, forwards):
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
    solver_diag: dict | None = None,
    prev_k: np.ndarray | None = None,
) -> CalibrationResult:
    """One step of the calibrate_surface loop: warm start + calendar floor.

    Quote-edit sessions apply here too (state/ticker/iso resolve them), so a
    surface fit honours the user's excluded/amended quotes on every expiry.
    ``prev_k`` (the previous expiry's retained quote support) confines the
    floor to the common support of the two expiries; the floor stays keyed on
    quadrature z-values, so masking quotes leaves the constraint machinery
    untouched. ``fit_mode`` selects the band objective; the weight scheme
    follows the fit settings (volfit.calib.weights).
    """
    task = _slice_task(
        state, ticker, iso, prepared, fit_mode,
        init=prev.params if prev is not None else None,
        prev=prev, prev_k=prev_k,
        enforce_calendar=enforce_calendar, with_overlay=False,
    )
    if solver_diag is not None:  # honour a caller-provided side-channel dict
        task = replace(task, want_diag=True)
    outcome = run_slice_fit(task)
    if solver_diag is not None and outcome.solver_diag:
        solver_diag.update(outcome.solver_diag)
    return outcome.result


def fit_and_commit_slice(
    state: AppState,
    ticker: str,
    iso: str,
    prepared: PreparedQuotes,
    prev: CalibrationResult | None,
    enforce_calendar: bool,
    fit_mode: str = "mid",
    prev_display: DisplayFit | None = None,
    prev_k: np.ndarray | None = None,
) -> FitRecord:
    """Calendar-coupled slice fit (``fit_surface_slice``) PLUS the calibration
    bookkeeping: build the display overlay, cache the record under the canonical
    key, re-point the calibrated pointer (a surface/coupled fit IS a calibration)
    and persist it. Returns the committed FitRecord (its ``.result`` is the
    ``prev`` to thread into the next, longer expiry, and ``.display`` the
    ``prev_display`` for the overlay's calendar floor).

    Shared by the surface-fit endpoint (``fit_surface`` / the WS route) and the
    calendar-coupled branch of the background Calibrate job, so the coupling
    recipe lives in exactly one place. Both the LQD backbone and the SVI/sigmoid
    overlay honour ``enforce_calendar`` (they share one ``_slice_task``).
    """
    model = _model_label(state.fit_settings().model)
    with state.activity.activity("calibrate", f"Calibrating {ticker} {iso} ({model})"):
        # LQD backbone (warm start + calendar floor) + overlay as ONE pure task;
        # the background Calibrate thunk routes it to the fit process pool
        # (volfit.api.fit_pool), the sync surface fit runs it inline.
        task = _slice_task(
            state, ticker, iso, prepared, fit_mode,
            init=prev.params if prev is not None else None,
            prev=prev, prev_display=prev_display, prev_k=prev_k,
            enforce_calendar=enforce_calendar,
        )
        outcome = fit_pool.execute(task)
    record = FitRecord(prepared=prepared, result=outcome.result, display=outcome.display)
    return commit_record(state, ticker, iso, fit_mode, record, outcome.solver_diag)


def commit_record(
    state: AppState,
    ticker: str,
    iso: str,
    fit_mode: str,
    record: FitRecord,
    solver_diag: dict | None,
) -> FitRecord:
    """The calibration bookkeeping shared by every surface path: cache the
    record under the canonical key, re-point the calibrated pointer, persist,
    store the fit-uncertainty side channel and run the observation-filter
    commit hook. Re-committing the same key (the symmetric repair overwriting
    a phase-A fit) is an ordinary overwrite."""
    key = fit_key(state, ticker, iso, fit_mode)
    state.store_fit(key, record)
    state.set_calibrated_ptr(ticker, iso, fit_mode, key, float(state.snapshot(ticker).spot))
    history.persist_fit(state, ticker, iso, fit_mode, record)  # opt-in, never raises
    fit_uncertainty.store(state, ticker, iso, fit_mode, key, record, solver_diag)
    if solver_diag is not None:  # observation filter (Note 15) — advisory,
        from volfit.api import observation_filter  # self-gates on the filter mode

        observation_filter.commit_hook(state, ticker, iso, fit_mode, record, solver_diag)
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
    """Fit all expiries and cache each so GET /smiles serves them.

    With ``enforce_calendar`` and the "symmetric" surface solver (the default,
    OptionsSettings.surfaceSolver) this routes to the independent-fits +
    screen + component-repair pipeline (volfit.api.surface_symmetric);
    otherwise the historical sequential nearest-to-farthest loop below runs.

    ``progress(expiry_iso, index, total, max_iv_error_bp)`` is invoked after
    each expiry fit (the WebSocket route threads its frames through it).
    """
    if enforce_calendar and state.options().surfaceSolver == "symmetric":
        from volfit.api import surface_symmetric

        return surface_symmetric.fit_surface_symmetric(
            state, ticker, fit_mode, progress
        )
    state.set_spot_shift(ticker, 0.0)  # re-anchor: fit at the chain's own spot
    plan = surface_inputs(state, ticker, fit_mode)
    prev: CalibrationResult | None = None
    prev_display: DisplayFit | None = None
    prev_k: np.ndarray | None = None
    residuals: list[float] = []
    fitted: list[tuple[str, CalibrationResult]] = []
    for index, (iso, prepared) in enumerate(plan):
        record = fit_and_commit_slice(
            state, ticker, iso, prepared, prev, enforce_calendar, fit_mode,
            prev_display, prev_k,
        )
        result = record.result
        cur_k = retained_k(state, ticker, iso, prepared)
        residuals.append(
            0.0
            if prev is None
            else calendar_violation_windowed(
                prev.slice, result.slice, common_support(prev_k, cur_k)
            )
        )
        fitted.append((iso, result))
        if progress is not None:
            progress(iso, index, len(plan), result.max_iv_error * 1e4)
        prev = result
        prev_display = record.display
        prev_k = cur_k
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
