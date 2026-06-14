"""Direct local-vol-affine surface fit behind POST /fit/affine/{ticker}.

Calibrates the piecewise-affine local-VARIANCE surface of
Docs/piecewise_affine_local_variance_calibration.tex straight to a ticker's
option quotes (volfit.models.localvol.calibrate_affine), as opposed to
GET /localvol/{ticker} which *extracts* a Dupire grid from the already-fitted
LQD smiles. Pipeline:

  1. gather every expiry's edited prepared quotes (the same masked/amended set
     the LQD fit uses), convert mid implied vols to normalized forward call
     prices and vega-scaled tolerances (so the LSQ is ~vol-error weighted);
  2. build a tensor vertex grid (0 + a spread of listed expiries, by a strike
     grid spanning the quoted range with the ATM node x = 1 forced in) and the
     fine PDE x/t grids (t hits every quoted expiry exactly, as the note's
     forward Dupire march requires);
  3. calibrate the nodal local variances (bound-constrained, second-difference
     roughness), then reconstruct each expiry's arbitrage-free smile by
     inverting the Dupire PDE call prices through the Black formula.

Results are cached per (ticker, fit mode, per-expiry session versions, fit
settings, forwards, request hyperparameters). Heavy but explicit: it runs only
on an actual fit request, never on the smile hot path.
"""

from __future__ import annotations

import numpy as np

from volfit.api.schemas import QuoteBand, SmilePoint, VarSwapInfo
from volfit.api.schemas_affine import AffineFitRequest, AffineFitResponse, AffineSmile
from volfit.api.state import AppState
from volfit.calib.weights import resolve_weights
from volfit.core.black import black_call, black_vega_sigma, implied_total_variance
from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    VarSwapQuote,
    calibrate_affine,
    varswap_const,
    varswap_weights,
)

#: Var-swap replication strike floor (matches calibrate_affine's default).
_VARSWAP_K_LO = 0.01

#: PDE strike step and OTM span (x = K/F); the note uses dx = 0.01 to x = 2.2.
_X_DX = 0.01
_X_MAX_MIN = 2.5
_X_HI_PAD = 1.4
#: PDE time step ceiling (each quoted expiry is forced to be a grid node).
_DT_MAX = 0.01
#: Vega-scaled price tolerance: residual (P - y)/(vega * VOL_TOL) ~ vol error
#: in units of VOL_TOL, so a 1% vol miss contributes ~1.
_VOL_TOL = 0.01
_VEGA_FLOOR = 1e-3
#: Reconstructed-smile display grid.
_N_SMILE = 81
_K_PAD = 0.02
_CACHE_ATTR = "_affine_cache"  # AppState attribute, added lazily here


def _pick_spread(values: np.ndarray, n: int) -> np.ndarray:
    """``n`` roughly-even entries of a sorted array, always incl. both ends."""
    values = np.asarray(values, dtype=float)
    if values.size <= n:
        return values
    idx = np.unique(np.round(np.linspace(0, values.size - 1, n)).astype(int))
    return values[idx]


def _vertex_grid(
    expiries: np.ndarray, k_lo: float, k_hi: float, n_t: int, n_x: int
) -> tuple[np.ndarray, np.ndarray]:
    """Tensor vertex set: 0 + a spread of expiries, by strikes incl. x = 1."""
    t_nodes = np.unique(np.concatenate([[0.0], _pick_spread(expiries, n_t - 1)]))
    x_lo, x_hi = float(np.exp(k_lo)), float(np.exp(k_hi))
    x_nodes = np.unique(np.concatenate([np.linspace(x_lo, x_hi, n_x), [1.0]]))
    return t_nodes, x_nodes


def _pde_grids(expiries: np.ndarray, k_hi: float) -> tuple[np.ndarray, np.ndarray]:
    """Fine PDE strike grid (from 0) and time grid hitting every expiry."""
    x_max = max(float(np.exp(k_hi)) * _X_HI_PAD, _X_MAX_MIN)
    x_grid = np.linspace(0.0, x_max, int(round(x_max / _X_DX)) + 1)
    t_pts = [0.0]
    prev = 0.0
    for e in expiries:
        n = max(1, int(np.ceil((e - prev) / _DT_MAX)))
        t_pts.extend(np.linspace(prev, float(e), n + 1)[1:].tolist())
        prev = float(e)
    return x_grid, np.array(t_pts)


def _quote_bands(state: AppState, ticker: str, iso: str, prepared) -> list[QuoteBand]:
    """All prepared quotes as display bands (excluded dimmed, amended amber)."""
    session = state.session_if_exists((ticker, iso))
    bands = []
    for i, (k, b, a, m) in enumerate(
        zip(prepared.k, prepared.iv_bid, prepared.iv_ask, prepared.iv_mid)
    ):
        edit = session.edits.get(i) if session is not None else None
        amended = edit is not None and edit.amended_iv is not None
        bands.append(
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
    return bands


def _gather(state: AppState, ticker: str, fit_mode: str):
    """Per-expiry (iso, t, edited k, edited w, prepared, band) nearest first.

    ``band`` is the bid-ask / haircut band target aligned to the edited k
    (None for "mid"), so the surface fit honours the chosen fit mode too.
    """
    from volfit.api import service  # local import: service is heavy

    rows = []
    for iso, prepared in service.surface_inputs(state, ticker, fit_mode):
        k, w, _ = service.edited_fit_inputs(state, ticker, iso, prepared, None)
        if k.size >= 2:  # a slice with <2 live quotes cannot constrain its smile
            band = service.edited_band(state, ticker, iso, prepared, fit_mode)
            # The diffusion time is the event-WEIGHTED variance years (prepared.tau);
            # the calendar maturity (prepared.t) is kept for display only. The PDE
            # marches and the smiles reconstruct in tau, so an event before an
            # expiry lowers its reconstructed IVs, consistent with the Parametric fit.
            rows.append((iso, float(prepared.tau), k, w, prepared, band))
    return rows


def _option_quotes(rows, weight_scheme: str = "equal") -> list[OptionQuote]:
    """Normalized forward call quotes with vega-scaled tolerances.

    With a band (bid-ask / haircut mode) each quote also carries the call-price
    band edges at the band vols, so calibrate_affine fits the band objective. The
    quote weight scheme (volfit.calib.weights) is folded into the tolerance:
    tol = vega * VOL_TOL / sqrt(w_i), so the squared residual carries w_i — the
    same effect as multiplying every other model's residual by sqrt(w_i).
    """
    options: list[OptionQuote] = []
    for _, t, k, w, _, band in rows:
        vol = np.sqrt(np.maximum(w, 1e-12) / t)
        price = black_call(k, w)
        vega = np.maximum(black_vega_sigma(k, vol, t), _VEGA_FLOOR)
        qw = resolve_weights(weight_scheme, k, w)
        scale = np.ones_like(k) if qw is None else np.sqrt(np.maximum(qw, 1e-12))
        p_lo = p_hi = [None] * k.size
        if band is not None:
            p_lo = black_call(k, band.iv_lo**2 * t)
            p_hi = black_call(k, band.iv_hi**2 * t)
        for ki, pi, vi, si, lo, hi in zip(k, price, vega, scale, p_lo, p_hi):
            options.append(
                OptionQuote(
                    t=t,
                    x=float(np.exp(ki)),
                    price=float(pi),
                    tol=float(vi * _VOL_TOL / si),
                    price_lo=None if lo is None else float(lo),
                    price_hi=None if hi is None else float(hi),
                )
            )
    return options


def _varswap_quotes(state: AppState, ticker: str, rows, weight_scheme: str) -> list[VarSwapQuote]:
    """Active var-swap quotes per expiry as affine VarSwapQuote targets.

    Mirrors the parametric weighting (volfit.api.service.varswap_target): the
    var-swap competes with the expiry's option quotes at ``varSwapWeightPct`` of
    their summed weight. The affine objective measures the var-swap residual in
    TOTAL variance ((z - z_mkt)/zeta), while the option residuals are in
    vega-scaled price ((P - y)/tol) ~ vol error in units of VOL_TOL; equating the
    two squared weightings gives zeta = 2 sigma_vs t VOL_TOL / sqrt(u_vs), with
    u_vs = pct% * sum_i w_i (the same w_i that scale the option tolerances).
    """
    options = state.options()
    if not options.varSwapEnabled or options.varSwapWeightPct <= 0.0:
        return []
    quotes: list[VarSwapQuote] = []
    for iso, t, k, w, _, _ in rows:
        session = state.varswap_session_if_exists((ticker, iso))
        if session is None or not session.state.is_active:
            continue
        qw = resolve_weights(weight_scheme, k, w)
        sum_w = float(np.sum(qw)) if qw is not None else float(k.size)
        u_vs = (options.varSwapWeightPct / 100.0) * sum_w
        if u_vs <= 0.0:
            continue
        sigma_vs = float(session.state.level)
        zeta = 2.0 * sigma_vs * t * _VOL_TOL / np.sqrt(u_vs)
        quotes.append(VarSwapQuote(t=t, total_var=sigma_vs * sigma_vs * t, tol=float(zeta)))
    return quotes


def _affine_varswap_info(
    state: AppState, ticker: str, iso: str, model_vol: float
) -> VarSwapInfo:
    """VarSwapInfo for one Local-Vol expiry: the shared quote + the model level."""
    session = state.varswap_session_if_exists((ticker, iso))
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


def _model_varswap_vol(solution, i_exp: int, t: float, x_grid: np.ndarray) -> float:
    """Model fair var-swap vol of an expiry by log-contract replication on the
    PDE grid (the same construction the affine var-swap residual uses)."""
    q_w = varswap_weights(x_grid, _VARSWAP_K_LO)
    q_c = varswap_const(x_grid, _VARSWAP_K_LO)
    w_vs = float(q_w @ solution.prices[i_exp] + q_c)
    return float(np.sqrt(max(w_vs, 0.0) / t))


def _reconstruct_smile(solution, i_exp: int, t: float, k_lo: float, k_hi: float):
    """Reconstructed IV curve: Dupire PDE call prices inverted through Black."""
    grid = np.linspace(k_lo - _K_PAD, k_hi + _K_PAD, _N_SMILE)
    price = solution.price_at(i_exp, np.exp(grid))
    w = implied_total_variance(grid, price)
    vol = np.sqrt(np.maximum(w, 0.0) / t)
    pts = [
        SmilePoint(k=float(k), vol=float(v))
        for k, v in zip(grid, vol)
        if np.isfinite(v)
    ]
    return pts


def _iv_error_bp(solution, i_exp: int, t: float, k: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Per-quote |model - quote| implied vol at the calibrated surface, bp."""
    price = solution.price_at(i_exp, np.exp(k))
    model_w = implied_total_variance(k, price)
    model_vol = np.sqrt(np.maximum(model_w, 0.0) / t)
    quote_vol = np.sqrt(np.maximum(w, 0.0) / t)
    return np.abs(model_vol - quote_vol) * 1e4


def _diagnostics(solution, x_grid: np.ndarray) -> tuple[list[float], int, bool]:
    """Butterfly (min 2nd diff in x) per expiry, calendar violations, arb flag."""
    prices = solution.prices  # (n_exp, n_x)
    dx = float(x_grid[1] - x_grid[0])
    d2 = (prices[:, 2:] - 2.0 * prices[:, 1:-1] + prices[:, :-2]) / (dx * dx)
    min_density = [float(row.min()) for row in d2]
    calendar = int(np.sum(np.diff(prices, axis=0) < -1e-9)) if prices.shape[0] > 1 else 0
    bounded = bool(prices.min() >= -1e-9 and prices.max() <= 1.0 + 1e-9)
    arb_free = bounded and calendar == 0 and min(min_density, default=0.0) >= -1e-6
    return min_density, calendar, arb_free


def _fit(state: AppState, ticker: str, request: AffineFitRequest) -> AffineFitResponse:
    """Run the calibration and assemble the response (uncached inner step)."""
    rows = _gather(state, ticker, request.fitMode)
    if len(rows) < 2:
        raise ValueError("affine surface fit needs at least two expiries with quotes")
    expiries = np.array([t for _, t, _, _, _, _ in rows])
    k_lo = min(float(k.min()) for _, _, k, _, _, _ in rows)
    k_hi = max(float(k.max()) for _, _, k, _, _, _ in rows)

    t_nodes, x_nodes = _vertex_grid(expiries, k_lo, k_hi, request.nTNodes, request.nXNodes)
    x_grid, t_grid = _pde_grids(expiries, k_hi)

    options = _option_quotes(rows, state.fit_settings().weightScheme)
    # Flat initial guess: the median quoted local variance (= vol^2), clipped.
    all_var = np.concatenate([np.maximum(w, 1e-12) / t for _, t, _, w, _, _ in rows])
    var0 = float(np.clip(np.median(all_var), request.varLo, request.varHi))
    surface0 = AffineVarianceSurface(
        t_nodes=t_nodes, x_nodes=x_nodes, theta=np.full((t_nodes.size, x_nodes.size), var0)
    )
    varswaps = _varswap_quotes(state, ticker, rows, state.fit_settings().weightScheme)
    cal = calibrate_affine(
        surface0,
        options,
        x_grid,
        t_grid,
        varswaps=varswaps,
        varswap_k_lo=_VARSWAP_K_LO,
        bounds=(request.varLo, request.varHi),
        reg_lambda=request.regLambda,
        reg_rho=request.regRho,
        mid_anchor_weight=state.fit_settings().midAnchorWeight,
    )

    exp_index = {float(t): i for i, t in enumerate(cal.solution.expiries)}
    smiles: list[AffineSmile] = []
    iv_bp_all: list[float] = []
    for iso, t, k, w, prepared, _ in rows:
        i_exp = exp_index[t]
        klo, khi = float(k.min()), float(k.max())
        errs = _iv_error_bp(cal.solution, i_exp, t, k, w)
        iv_bp_all.extend(errs.tolist())
        model_vs_vol = _model_varswap_vol(cal.solution, i_exp, t, x_grid)
        smiles.append(
            AffineSmile(
                expiry=iso,
                t=prepared.t,  # calendar maturity (axis); t above is the tau clock
                tau=t,
                model=_reconstruct_smile(cal.solution, i_exp, t, klo, khi),
                quotes=_quote_bands(state, ticker, iso, prepared),
                varSwap=_affine_varswap_info(state, ticker, iso, model_vs_vol),
                maxIvErrorBp=float(errs.max()) if errs.size else 0.0,
            )
        )

    min_density, calendar, arb_free = _diagnostics(cal.solution, x_grid)
    iv_arr = np.array(iv_bp_all) if iv_bp_all else np.zeros(1)
    return AffineFitResponse(
        ticker=ticker,
        tNodes=[float(v) for v in t_nodes],
        xNodes=[float(v) for v in x_nodes],
        localVol=[[float(np.sqrt(v)) for v in row] for row in cal.surface.theta],
        smiles=smiles,
        rmsPriceError=cal.rms_price_error,
        maxPriceError=cal.max_price_error,
        rmsIvErrorBp=float(np.sqrt(np.mean(iv_arr**2))),
        maxIvErrorBp=float(iv_arr.max()),
        minDensity=min_density,
        calendarViolations=calendar,
        arbitrageFree=arb_free,
        nEvals=cal.n_evals,
        message=cal.message,
    )


def affine_payload(state: AppState, ticker: str, request: AffineFitRequest) -> AffineFitResponse:
    """Cached entry point for POST /fit/affine/{ticker}."""
    from volfit.api import service

    isos = [e.isoformat() for e in sorted(state.forwards(ticker))]  # raises if unknown
    versions = tuple(service.session_version(state, ticker, iso) for iso in isos)
    vs_versions = tuple(service.varswap_version(state, ticker, iso) for iso in isos)
    key = (
        ticker,
        request.fitMode,
        versions,
        vs_versions,
        state.events_version,  # event calendar drives the variance clock
        state.settings_version,
        state.forwards_version,
        state.options_version,  # var-swap + event-clock toggles live here
        request.model_dump_json(),
    )
    cache = getattr(state, _CACHE_ATTR, None)
    if cache is None:
        cache = {}
        setattr(state, _CACHE_ATTR, cache)
    hit = cache.get(key)
    if hit is None:
        hit = _fit(state, ticker, request)
        cache[key] = hit
    return hit
