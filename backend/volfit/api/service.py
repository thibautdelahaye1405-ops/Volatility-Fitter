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

import numpy as np

from volfit.api import history
from volfit.api.fit_models import build_display_fit
from volfit.api.quotes import (
    PreparedQuotes,
    apply_band_edits,
    apply_edits,
    prepare_quotes,
)
from volfit.api.schemas import (
    QuoteBand,
    ScenarioRequest,
    ScenarioResponse,
    SmileData,
    SmileDiagnostics,
    SmilePoint,
    SurfaceFitResponse,
)
from volfit.api.displayed import displayed_skew, displayed_slice
from volfit.api.state import AppState, FitRecord
from volfit.calib.calendar import calendar_floor, calendar_violation
from volfit.calib.weights import resolve_weights
from volfit.dynamics.ssr import Regime, shifted_smile, ssr_of_regime
from volfit.models.diagnostics import weighted_rms_vol
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.basis import endpoint_scales, lee_slopes
from volfit.models.lqd.calibrate import CalibrationResult, calibrate_slice

#: Model-curve sampling: 161 points, padded 0.02 beyond the quoted k range
#: (matches the frontend mock's grid density).
N_MODEL_POINTS = 161
K_PAD = 0.02

#: High-order Legendre damping defaults (lam * n^{2r} a_n^2); short-dated slices
#: left with ~as few quotes as params after the wing filter interpolate with
#: wild ATM handles unregularized. Now the defaults of schemas.FitSettings (the
#: hyperparameter panel PUT /settings/fit overrides them per AppState).
REG_LAMBDA = 1e-6
REG_POWER = 1.0


# --------------------------------------------------------- fit-session edits
def session_version(state: AppState, ticker: str, iso: str) -> int:
    """Current quote-edit session version of a node, 0 when none exists."""
    session = state.session_if_exists((ticker, iso))
    return 0 if session is None else session.version


def fit_key(state: AppState, ticker: str, iso: str, fit_mode: str) -> tuple:
    """Fit-cache key: (ticker, canonical ISO, mode, session version, settings
    version, forwards version, options version) — edits, hyperparameter,
    forward/market and calendar-penalty changes each bump a version, so affected
    nodes refit without eviction."""
    return (
        ticker,
        iso,
        fit_mode,
        session_version(state, ticker, iso),
        state.settings_version,
        state.forwards_version,
        state.options_version,
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
):
    """The non-LQD display overlay for a node (None for LQD), fit to the same
    edited quotes, band and weights the LQD calibration uses."""
    settings = state.fit_settings()
    if settings.model == "lqd":
        return None
    k, w, _ = edited_fit_inputs(state, ticker, iso, prepared, None)
    weights = resolve_weights(settings.weightScheme, k, w)
    band = edited_band(state, ticker, iso, prepared, fit_mode)
    return build_display_fit(
        settings.model, k, w, prepared.t, weights, n_cores=settings.nCores, band=band
    )


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
    cash_divs = state.cash_dividend_schedule(ticker, expiry, forward.forward)
    prepared = prepare_quotes(
        snapshot, expiry, forward, state.year_fraction(expiry), cash_divs
    )
    k, w, _ = edited_fit_inputs(state, ticker, iso, prepared, None)
    settings = state.fit_settings()
    weights = resolve_weights(settings.weightScheme, k, w)
    band = edited_band(state, ticker, iso, prepared, fit_mode)
    result = calibrate_slice(
        k,
        w,
        t=prepared.t,
        n_order=settings.nOrder,
        weights=weights,
        reg_lambda=settings.regLambda,
        reg_power=settings.regPower,
        band=band,
    )
    # LQD is always fitted (the analytic backbone); a non-LQD model choice adds
    # a display overlay on the same edited quotes + band (volfit.api.fit_models).
    display = build_display_fit(
        settings.model, k, w, prepared.t, weights, n_cores=settings.nCores, band=band
    )
    record = FitRecord(prepared=prepared, result=result, display=display)
    state.store_fit(key, record)
    history.persist_fit(state, ticker, iso, fit_mode, record)  # opt-in, never raises
    return record


def model_curve(record: FitRecord) -> list[SmilePoint]:
    """Sample the displayed slice's IV curve on the padded display grid."""
    grid = np.linspace(
        float(record.prepared.k.min()) - K_PAD,
        float(record.prepared.k.max()) + K_PAD,
        N_MODEL_POINTS,
    )
    vols = np.sqrt(displayed_slice(record).implied_w(grid) / record.prepared.t)
    return [SmilePoint(k=float(k), vol=float(v)) for k, v in zip(grid, vols)]


def weighted_rms_error(state: AppState, ticker: str, iso: str, record: FitRecord) -> float:
    """Weighted RMS vol error of the displayed fit vs the mid quotes, using the
    SAME weights as the calibration (active weightScheme, over the edited set);
    decimal vol (the UI renders it as a percentage)."""
    k, w, _ = edited_fit_inputs(state, ticker, iso, record.prepared, None)
    weights = resolve_weights(state.fit_settings().weightScheme, k, w)
    return weighted_rms_vol(displayed_slice(record), k, w, record.prepared.t, weights)


def smile_payload(state: AppState, ticker: str, expiry_iso: str, fit_mode: str) -> SmileData:
    """Assemble the full SmileData payload for one (ticker, expiry) node."""
    record = fit_or_get(state, ticker, expiry_iso, fit_mode)
    iso = state.resolve_expiry(ticker, expiry_iso).isoformat()  # session key
    session = state.session_if_exists((ticker, iso))
    prepared, slice_ = record.prepared, record.result.slice
    model = model_curve(record)
    rms_error = weighted_rms_error(state, ticker, iso, record)

    saved = state.get_prior((ticker, expiry_iso))  # saved prior, else current fit
    prior = list(saved.curve) if saved is not None else list(model)

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
            varSwapVol=float(np.sqrt(d.var_swap_w / prepared.t)),
            rmsError=rms_error,
        )
    else:
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
) -> list[tuple[str, PreparedQuotes]]:
    """(expiry-ISO, prepared quotes) per expiry, nearest first.

    Weights and band are derived per slice at fit time (they depend on the
    edited quotes), so the plan only carries the prepared quotes.
    """
    snapshot = state.snapshot(ticker)
    forwards = state.forwards(ticker)  # gates the expiry universe
    plan = []
    for expiry in sorted(forwards):
        forward = state.resolved_forward(ticker, expiry)  # honours the policy
        cash_divs = state.cash_dividend_schedule(ticker, expiry, forward.forward)
        prepared = prepare_quotes(
            snapshot, expiry, forward, state.year_fraction(expiry), cash_divs
        )
        plan.append((expiry.isoformat(), prepared))
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
    calendar floor indexes the quadrature grid, not the quote array, so masking
    quotes leaves it untouched. ``fit_mode`` selects the band objective; the
    weight scheme follows the fit settings (volfit.calib.weights).
    """
    cal_idx = cal_floor = None
    if enforce_calendar and prev is not None:
        cal_idx, cal_floor = calendar_floor(prev.slice)
    k, w, _ = edited_fit_inputs(state, ticker, iso, prepared, None)
    settings = state.fit_settings()
    weights = resolve_weights(settings.weightScheme, k, w)
    band = edited_band(state, ticker, iso, prepared, fit_mode)
    return calibrate_slice(
        k,
        w,
        t=prepared.t,
        n_order=settings.nOrder,
        weights=weights,
        reg_lambda=settings.regLambda,
        reg_power=settings.regPower,
        init=prev.params if prev is not None else None,
        band=band,
        calendar_indices=cal_idx,
        calendar_floor=cal_floor,
        calendar_weight=state.options().calendarWeight,
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
    for index, (iso, prepared) in enumerate(plan):
        result = fit_surface_slice(
            state, ticker, iso, prepared, prev, enforce_calendar, fit_mode
        )
        residuals.append(0.0 if prev is None else calendar_violation(prev.slice, result.slice))
        overlay = display_overlay(state, ticker, iso, prepared, fit_mode)
        record = FitRecord(prepared=prepared, result=result, display=overlay)
        state.store_fit(fit_key(state, ticker, iso, fit_mode), record)
        history.persist_fit(state, ticker, iso, fit_mode, record)  # opt-in, never raises
        fitted.append((iso, result))
        if progress is not None:
            progress(iso, index, len(plan), result.max_iv_error * 1e4)
        prev = result
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
    t, slice_ = record.prepared.t, displayed_slice(record)
    grid = np.linspace(
        float(record.prepared.k.min()) - K_PAD,
        float(record.prepared.k.max()) + K_PAD,
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
