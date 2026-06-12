"""Pure service functions behind the volfit API routes (ROADMAP Phase 5).

Each function takes the AppState explicitly and returns pydantic response
models, so the routers stay one-line thin and everything here is testable
without HTTP. The surface fit is decomposed into `surface_inputs` +
`fit_surface_slice` — the exact loop body of volfit.calib.calibrate_surface
(warm start from the previous slice, calendar floor from
volfit.calib.calendar) — so the WebSocket route can emit a progress event
between expiries while the POST route reuses the same steps synchronously.
Quote-edit sessions (volfit.api.session) plug in at two seams: fit-cache
keys carry the session version (`fit_key`) and calibration inputs are
rewritten by `edited_fit_inputs`; the edit/undo/redo entry points live in
volfit.api.edits to keep this module under the file-size policy.
"""

from __future__ import annotations

import itertools

import numpy as np

from volfit.api.quotes import PreparedQuotes, apply_edits, fit_weights, prepare_quotes
from volfit.api.schemas import (
    GraphNodeResult,
    GraphObservation,
    GraphSolveRequest,
    GraphSolveResponse,
    QuoteBand,
    ScenarioRequest,
    ScenarioResponse,
    SmileData,
    SmileDiagnostics,
    SmilePoint,
    SurfaceFitResponse,
)
from volfit.api.state import AppState, FitRecord, UnknownNodeError
from volfit.calib.calendar import calendar_floor, calendar_violation
from volfit.dynamics.ssr import Regime, shifted_smile, ssr_of_regime
from volfit.graph import build_increment_prior
from volfit.graph.smile_universe import (
    SmileNode,
    SmileUniverse,
    build_universe,
    propagate_handles,
)
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.basis import endpoint_scales, lee_slopes
from volfit.models.lqd.calibrate import CalibrationResult, calibrate_slice

#: Model-curve sampling: 161 points, padded 0.02 beyond the quoted k range
#: (matches the frontend mock's grid density).
N_MODEL_POINTS = 161
K_PAD = 0.02

#: High-order Legendre damping for every API slice fit (lam * n^{2r} a_n^2).
#: Short-dated slices can have as few quotes as LQD parameters after the wing
#: filter — unregularized they interpolate exactly with wild ATM handles
#: (observed: a 7-quote 1M slice fitting skew +0.78, curvature -40). 1e-6
#: costs only bp-level fit error on liquid slices and restores sane shapes.
#: These are now the *defaults* of schemas.FitSettings — the hyperparameter
#: panel (PUT /settings/fit) overrides them per AppState.
REG_LAMBDA = 1e-6
REG_POWER = 1.0

#: Graph weights: strong calendar chain within a ticker, weaker cross-ticker
#: edges at equal expiry (regime validated in tests/test_smile_universe.py).
SAME_TICKER_WEIGHT = 10.0
CROSS_TICKER_WEIGHT = 2.0

#: Per-handle increment hyperparameters (scale s, eta) with kappa = 1/s^2:
#: ~3 vol pts level, looser skew/curvature — the demo.py regime.
GRAPH_PRIOR_HYPER = ((0.03, 2.0e4), (0.05, 7.0e3), (0.5, 70.0))

#: Baseline/observation precisions per handle coordinate.
GRAPH_PRECISION = np.array([1.0e6, 1.0e6, 1.0e4])


# --------------------------------------------------------- fit-session edits
def session_version(state: AppState, ticker: str, iso: str) -> int:
    """Current quote-edit session version of a node, 0 when none exists."""
    session = state.session_if_exists((ticker, iso))
    return 0 if session is None else session.version


def fit_key(state: AppState, ticker: str, iso: str, fit_mode: str) -> tuple:
    """Fit-cache key: (ticker, canonical ISO, mode, session version, settings
    version, forwards version) — quote edits, hyperparameter changes and
    forward-policy/market-settings changes each bump a version, so affected
    nodes refit without cache eviction."""
    return (
        ticker,
        iso,
        fit_mode,
        session_version(state, ticker, iso),
        state.settings_version,
        state.forwards_version,
    )


def edited_fit_inputs(
    state: AppState, ticker: str, iso: str, prepared: PreparedQuotes, weights: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Calibration inputs after the node's quote edits (quotes.apply_edits):
    excluded strikes masked out, amended mids re-leveled to w = mid_iv^2 t."""
    session = state.session_if_exists((ticker, iso))
    return apply_edits(prepared, {} if session is None else session.edits, weights)


# ------------------------------------------------------------- slice fitting
def fit_or_get(state: AppState, ticker: str, expiry_iso: str, fit_mode: str) -> FitRecord:
    """Return the cached slice fit for (ticker, expiry, mode), fitting once
    per quote-edit session version (edits change the calibration inputs)."""
    expiry = state.resolve_expiry(ticker, expiry_iso)
    iso = expiry.isoformat()  # canonical ISO cache/session key
    key = fit_key(state, ticker, iso, fit_mode)
    record = state.get_fit(key)
    if record is not None:
        return record

    snapshot = state.snapshot(ticker)
    forward = state.resolved_forward(ticker, expiry)  # honours the forward policy
    prepared = prepare_quotes(snapshot, expiry, forward, state.year_fraction(expiry))
    k, w, weights = edited_fit_inputs(
        state, ticker, iso, prepared, fit_weights(prepared, fit_mode)
    )
    settings = state.fit_settings()
    result = calibrate_slice(
        k,
        w,
        t=prepared.t,
        n_order=settings.nOrder,
        weights=weights,
        reg_lambda=settings.regLambda,
        reg_power=settings.regPower,
    )
    record = FitRecord(prepared=prepared, result=result)
    state.store_fit(key, record)
    return record


def model_curve(record: FitRecord) -> list[SmilePoint]:
    """Sample the fitted slice's IV curve on the padded display grid."""
    grid = np.linspace(
        float(record.prepared.k.min()) - K_PAD,
        float(record.prepared.k.max()) + K_PAD,
        N_MODEL_POINTS,
    )
    vols = np.sqrt(record.result.slice.implied_w(grid) / record.prepared.t)
    return [SmilePoint(k=float(k), vol=float(v)) for k, v in zip(grid, vols)]


def smile_payload(state: AppState, ticker: str, expiry_iso: str, fit_mode: str) -> SmileData:
    """Assemble the full SmileData payload for one (ticker, expiry) node."""
    record = fit_or_get(state, ticker, expiry_iso, fit_mode)
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()  # session key
    session = state.session_if_exists((ticker, iso))
    prepared, slice_ = record.prepared, record.result.slice
    model = model_curve(record)

    saved = state.get_prior((ticker, expiry_iso))  # saved prior, else current fit
    prior = list(saved.curve) if saved is not None else list(model)

    handles = atm_handles(slice_, prepared.t)
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
        varSwapVol=float(np.sqrt(slice_.var_swap_strike() / prepared.t)),
    )
    # Every prepared quote is listed (excluded ones dimmed by the UI); an
    # amended quote shows its overridden mid, bid/ask stay the market band.
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
        quotes=quotes,
        kMin=model[0].k,
        kMax=model[-1].k,
        diagnostics=diagnostics,
        canUndo=session.can_undo if session is not None else False,
        canRedo=session.can_redo if session is not None else False,
    )


# -------------------------------------------------------------- surface fit
def surface_inputs(
    state: AppState, ticker: str, fit_mode: str
) -> list[tuple[str, PreparedQuotes, np.ndarray | None]]:
    """(expiry-ISO, prepared quotes, weights) per expiry, nearest first."""
    snapshot = state.snapshot(ticker)
    forwards = state.forwards(ticker)  # gates the expiry universe
    plan = []
    for expiry in sorted(forwards):
        forward = state.resolved_forward(ticker, expiry)  # honours the policy
        prepared = prepare_quotes(snapshot, expiry, forward, state.year_fraction(expiry))
        plan.append((expiry.isoformat(), prepared, fit_weights(prepared, fit_mode)))
    return plan


def fit_surface_slice(
    state: AppState,
    ticker: str,
    iso: str,
    prepared: PreparedQuotes,
    weights: np.ndarray | None,
    prev: CalibrationResult | None,
    enforce_calendar: bool,
) -> CalibrationResult:
    """One step of the calibrate_surface loop: warm start + calendar floor.

    Quote-edit sessions apply here too (state/ticker/iso resolve them), so a
    surface fit honours the user's excluded/amended quotes on every expiry.
    The calendar floor indexes the quadrature grid, not the quote array, so
    masking quotes leaves the constraint untouched.
    """
    cal_idx = cal_floor = None
    if enforce_calendar and prev is not None:
        cal_idx, cal_floor = calendar_floor(prev.slice)
    k, w, weights = edited_fit_inputs(state, ticker, iso, prepared, weights)
    settings = state.fit_settings()
    return calibrate_slice(
        k,
        w,
        t=prepared.t,
        n_order=settings.nOrder,
        weights=weights,
        reg_lambda=settings.regLambda,
        reg_power=settings.regPower,
        init=prev.params if prev is not None else None,
        calendar_indices=cal_idx,
        calendar_floor=cal_floor,
    )


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
    plan = surface_inputs(state, ticker, fit_mode)
    prev: CalibrationResult | None = None
    residuals: list[float] = []
    fitted: list[tuple[str, CalibrationResult]] = []
    for index, (iso, prepared, weights) in enumerate(plan):
        result = fit_surface_slice(state, ticker, iso, prepared, weights, prev, enforce_calendar)
        residuals.append(0.0 if prev is None else calendar_violation(prev.slice, result.slice))
        record = FitRecord(prepared=prepared, result=result)
        state.store_fit(fit_key(state, ticker, iso, fit_mode), record)
        fitted.append((iso, result))
        if progress is not None:
            progress(iso, index, len(plan), result.max_iv_error * 1e4)
        prev = result
    return assemble_surface_response(state, ticker, fit_mode, fitted, residuals)


# -------------------------------------------------------------- graph solve
def ensure_universe(state: AppState) -> SmileUniverse:
    """Build (once) the smile universe over all tickers x expiries, mid fits.

    Node names are (ticker, expiry-ISO). The build is deterministic and the
    underlying slice fits are themselves cached, so a concurrent double build
    only costs time, never consistency. Slice fits flow through fit_or_get,
    so quote edits made *before* the first graph solve shape the universe
    naturally; the universe is built once and not invalidated by later edits
    (acceptable: graph handles are slow-moving levels, not live fit state).
    """
    if state.universe is not None:
        return state.universe

    tickers = state.provider.list_tickers()
    smiles: list[SmileNode] = []
    weights: dict[tuple, float] = {}
    ladders: dict[str, list[str]] = {}
    for ticker in tickers:
        isos = [e.isoformat() for e in sorted(state.forwards(ticker))]
        ladders[ticker] = isos
        for iso in isos:
            record = fit_or_get(state, ticker, iso, "mid")
            smiles.append(
                SmileNode(name=(ticker, iso), t=record.prepared.t, params=record.result.params)
            )
        for near, far in zip(isos[:-1], isos[1:]):  # calendar chain
            weights[((ticker, near), (ticker, far))] = SAME_TICKER_WEIGHT
            weights[((ticker, far), (ticker, near))] = SAME_TICKER_WEIGHT
    for a, b in itertools.combinations(tickers, 2):  # equal-expiry cross edges
        for iso in sorted(set(ladders[a]) & set(ladders[b])):
            weights[((a, iso), (b, iso))] = CROSS_TICKER_WEIGHT
            weights[((b, iso), (a, iso))] = CROSS_TICKER_WEIGHT

    universe = build_universe(smiles, weights)
    state.universe = universe
    return universe


def _observed_handles(
    universe: SmileUniverse, observations: list[GraphObservation]
) -> dict[tuple, np.ndarray]:
    """Map handle *shifts* to absolute observed handles, validating nodes."""
    observed: dict[tuple, np.ndarray] = {}
    for obs in observations:
        name = (obs.ticker, obs.expiry)
        try:
            index = universe.node_index(name)
        except KeyError:
            raise UnknownNodeError(f"unknown node {name!r}") from None
        observed[name] = universe.handles[index] + np.array([obs.dAtmVol, obs.dSkew, obs.dCurv])
    return observed


def solve_graph(state: AppState, request: GraphSolveRequest) -> GraphSolveResponse:
    """Propagate sparse handle observations to every node of the universe."""
    universe = ensure_universe(state)
    priors = [
        build_increment_prior(universe.graph, kappa=1.0 / s**2, eta=eta * request.etaScale)
        for s, eta in GRAPH_PRIOR_HYPER
    ]
    observed = _observed_handles(universe, request.observations)
    field = propagate_handles(
        universe,
        priors,
        observed,
        baseline_precision=GRAPH_PRECISION,
        observation_precision=GRAPH_PRECISION,
    )
    band_lo, band_hi = field.atm_vol_band()

    nodes = []
    for j, smile in enumerate(universe.smiles):
        ticker, expiry_iso = smile.name
        base, post = float(universe.handles[j, 0]), float(field.mean[j, 0])
        nodes.append(
            GraphNodeResult(
                ticker=ticker,
                expiry=expiry_iso,
                t=smile.t,
                baseAtmVol=base,
                postAtmVol=post,
                shiftBp=(post - base) * 1e4,
                sd=float(field.sd[j, 0]),
                bandLo=float(band_lo[j]),
                bandHi=float(band_hi[j]),
                observed=smile.name in observed,
            )
        )
    return GraphSolveResponse(nodes=nodes)


# ----------------------------------------------------------------- scenario
def run_scenario(state: AppState, request: ScenarioRequest) -> ScenarioResponse:
    """Shift one fitted smile for a spot move under the requested regime."""
    if request.regime == Regime.STICKY_LOCAL_VOL_GRID:
        # Exact dynamics: fixed-strike LV grid + Dupire reprice (api.localvol;
        # imported lazily — that module reuses this one's slice-fit cache).
        from volfit.api.localvol import scenario_sticky_grid

        return scenario_sticky_grid(state, request)
    record = fit_or_get(state, request.ticker, request.expiry, request.fitMode)
    t, slice_ = record.prepared.t, record.result.slice
    grid = np.linspace(
        float(record.prepared.k.min()) - K_PAD,
        float(record.prepared.k.max()) + K_PAD,
        N_MODEL_POINTS,
    )

    def vol_curve(k: np.ndarray) -> np.ndarray:
        return np.sqrt(slice_.implied_w(k) / t)

    base = vol_curve(grid)
    skew = atm_handles(slice_, t).skew
    shifted = shifted_smile(grid, vol_curve, skew, request.spotReturn, request.regime)
    regime = request.regime
    return ScenarioResponse(
        k=grid.tolist(),
        baseVol=base.tolist(),
        shiftedVol=shifted.tolist(),
        ssr=ssr_of_regime(regime),
        regime=regime.value if isinstance(regime, Regime) else f"{regime:g}",
    )
