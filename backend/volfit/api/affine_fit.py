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

from volfit.api.schemas import QuoteBand, SmilePoint
from volfit.api.schemas_affine import AffineFitRequest, AffineFitResponse, AffineSmile
from volfit.api.state import AppState
from volfit.core.black import black_call, black_vega_sigma, implied_total_variance
from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    calibrate_affine,
)

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
    """Per-expiry (iso, t, edited k, edited w, prepared) nearest first."""
    from volfit.api import service  # local import: service is heavy

    rows = []
    for iso, prepared, weights in service.surface_inputs(state, ticker, fit_mode):
        k, w, _ = service.edited_fit_inputs(state, ticker, iso, prepared, weights)
        if k.size >= 2:  # a slice with <2 live quotes cannot constrain its smile
            rows.append((iso, float(prepared.t), k, w, prepared))
    return rows


def _option_quotes(rows) -> list[OptionQuote]:
    """Normalized forward call quotes with vega-scaled tolerances."""
    options: list[OptionQuote] = []
    for _, t, k, w, _ in rows:
        vol = np.sqrt(np.maximum(w, 1e-12) / t)
        price = black_call(k, w)
        vega = np.maximum(black_vega_sigma(k, vol, t), _VEGA_FLOOR)
        for ki, pi, vi in zip(k, price, vega):
            options.append(
                OptionQuote(t=t, x=float(np.exp(ki)), price=float(pi), tol=float(vi * _VOL_TOL))
            )
    return options


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
    expiries = np.array([t for _, t, _, _, _ in rows])
    k_lo = min(float(k.min()) for _, _, k, _, _ in rows)
    k_hi = max(float(k.max()) for _, _, k, _, _ in rows)

    t_nodes, x_nodes = _vertex_grid(expiries, k_lo, k_hi, request.nTNodes, request.nXNodes)
    x_grid, t_grid = _pde_grids(expiries, k_hi)

    options = _option_quotes(rows)
    # Flat initial guess: the median quoted local variance (= vol^2), clipped.
    all_var = np.concatenate([np.maximum(w, 1e-12) / t for _, t, _, w, _ in rows])
    var0 = float(np.clip(np.median(all_var), request.varLo, request.varHi))
    surface0 = AffineVarianceSurface(
        t_nodes=t_nodes, x_nodes=x_nodes, theta=np.full((t_nodes.size, x_nodes.size), var0)
    )
    cal = calibrate_affine(
        surface0,
        options,
        x_grid,
        t_grid,
        bounds=(request.varLo, request.varHi),
        reg_lambda=request.regLambda,
        reg_rho=request.regRho,
    )

    exp_index = {float(t): i for i, t in enumerate(cal.solution.expiries)}
    smiles: list[AffineSmile] = []
    iv_bp_all: list[float] = []
    for iso, t, k, w, prepared in rows:
        i_exp = exp_index[t]
        klo, khi = float(k.min()), float(k.max())
        errs = _iv_error_bp(cal.solution, i_exp, t, k, w)
        iv_bp_all.extend(errs.tolist())
        smiles.append(
            AffineSmile(
                expiry=iso,
                t=t,
                model=_reconstruct_smile(cal.solution, i_exp, t, klo, khi),
                quotes=_quote_bands(state, ticker, iso, prepared),
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
    key = (
        ticker,
        request.fitMode,
        versions,
        state.settings_version,
        state.forwards_version,
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
