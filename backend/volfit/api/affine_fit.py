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

from volfit.api.schemas import DistributionArrays, QuoteBand, SmilePoint, VarSwapInfo
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
    expiries: np.ndarray, x_lo_vertex: float, k_hi: float, n_t_cap: int, n_x: int
) -> tuple[np.ndarray, np.ndarray]:
    """Tensor vertex set (note convention): time vertices at the OBSERVED expiries
    (0 + each), strikes from ``x_lo_vertex`` to the top observed strike incl. x = 1.

    ``n_t_cap`` <= 0 places one time vertex per observed expiry (the recommended
    data-driven default); > 0 subsamples the expiries to that many. ``x_lo_vertex``
    is the lowest strike vertex, placed by the caller strictly between the lowest
    and second-lowest observed strike so no vertex sits below the data.
    """
    if n_t_cap and n_t_cap >= 1:
        picked = _pick_spread(expiries, max(1, n_t_cap - 1))
    else:
        picked = expiries  # auto: one vertex per observed expiry
    t_nodes = np.unique(np.concatenate([[0.0], picked]))
    x_hi = float(np.exp(k_hi))
    x_nodes = np.unique(np.concatenate([np.linspace(x_lo_vertex, x_hi, n_x), [1.0]]))
    return t_nodes, x_nodes


def _lowest_vertex_x(rows) -> tuple[float, float]:
    """(x_lo_vertex, k_hi) for the strike grid: the lowest strike vertex sits
    strictly between the lowest and second-lowest OBSERVED normalized strike
    x = K/F (across all expiries), so no vertex lies below the data and the
    lowest quote anchors the flat boundary below it (the user's grid rule)."""
    all_k = np.sort(np.concatenate([k for _, _, k, _, _, _ in rows]))
    k_hi = float(all_k[-1])
    x_obs = np.unique(np.exp(all_k))
    x_lo1 = float(x_obs[0])
    x_lo2 = float(x_obs[1]) if x_obs.size >= 2 else x_lo1 * 1.01
    return 0.5 * (x_lo1 + x_lo2), k_hi


def _pde_grids(expiries: np.ndarray, k_hi: float) -> tuple[np.ndarray, np.ndarray]:
    """Fine PDE strike grid (from 0) and time grid hitting every expiry.

    The strike grid is a UNIFORM lattice of step ``_X_DX`` from 0, so the
    var-swap anchor ``x = 1`` is always exactly a node (1.0 = 100 * 0.01) — the
    log-contract replication (affine_calib.varswap_weights) rejects a grid that
    misses it. ``np.linspace(0, x_max, ...)`` to an arbitrary ``x_max`` (e.g. a
    real ticker's wide strike range, > the 2.5 floor and off the 0.01 lattice)
    would land x = 1 between nodes and 422 every fit; the synthetic range floors
    at 2.5 which aligns, which is why this only bit live data.
    """
    x_max = max(float(np.exp(k_hi)) * _X_HI_PAD, _X_MAX_MIN)
    n = int(np.ceil(round(x_max / _X_DX, 6)))  # steps to cover x_max
    x_grid = _X_DX * np.arange(n + 1)  # 0, dx, 2dx, ... ; 1.0 = node 100
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


#: Density chart sizing: keep the central probability mass, strided to <= this.
_DENSITY_U_TRIM = 1e-3
_DENSITY_MAX_POINTS = 241


def _price_density(solution, i_exp: int) -> DistributionArrays:
    """Risk-neutral density of one expiry, straight from the Dupire call prices.

    Breeden-Litzenberger: the density of y = S_T/F is f_y(x) = d2C/dx2 of the
    undiscounted normalized call C(x), x = K/F (the affine PDE solves for C on a
    uniform x grid). This is smooth and >= 0 by construction (the arb-free PDE
    surface is convex in strike), so it avoids the implied-vol Breeden-
    Litzenberger formula's small-w blow-up that clamps the short-dated density to
    zero. Mapped to the log-return X = log(S_T/F) the chart uses:
    f_X(k) = f_y(e^k) e^k, on k = log(x). Trimmed to the central mass + strided.
    """
    x = np.asarray(solution.x_grid, dtype=float)
    c = np.asarray(solution.prices[i_exp], dtype=float)
    dx = float(x[1] - x[0])  # uniform grid (see _pde_grids)
    d2 = np.zeros_like(c)
    d2[1:-1] = (c[2:] - 2.0 * c[1:-1] + c[:-2]) / (dx * dx)
    f_y = np.maximum(d2, 0.0)

    pos = x > 1e-6  # log-return needs x > 0 (x = 0 is the C(.,0) = 1 boundary)
    k = np.log(x[pos])
    f_x = f_y[pos] * x[pos]  # density of X = log(S/F): f_X(k) = f_y(e^k) e^k
    area = float(np.trapezoid(f_x, k))
    if area > 0.0:
        f_x = f_x / area
    cdf = np.concatenate([[0.0], np.cumsum(0.5 * (f_x[1:] + f_x[:-1]) * np.diff(k))])
    cdf = np.clip(cdf, 0.0, 1.0)

    keep = np.flatnonzero((cdf >= _DENSITY_U_TRIM) & (cdf <= 1.0 - _DENSITY_U_TRIM))
    if keep.size == 0:
        keep = np.arange(k.size)
    stride = max(1, -(-keep.size // _DENSITY_MAX_POINTS))
    idx = keep[::stride]
    return DistributionArrays(
        x=k[idx].tolist(),
        density=f_x[idx].tolist(),
        u=cdf[idx].tolist(),
        quantile=k[idx].tolist(),
    )


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


def _prior_anchor_quotes(
    state: AppState, ticker: str, rows
) -> tuple[list[OptionQuote], list[VarSwapQuote]]:
    """Extra anchor quotes pulling the LV surface toward the (transported) prior.

    The same data-gap framework as the parametric anchor (volfit.calib.prior),
    expressed as the affine fit's own currency: per expiry with an active-prior
    node, the prior's LQD backbone is transported to the node's forward, anchored
    at delta-locations whose weight follows the observed-vs-desired quote density,
    and emitted as OptionQuotes (price = prior price, tol = vega·VOL_TOL/√weight —
    higher weight ⇒ tighter) plus a companion var-swap quote scaled by how
    unobserved the smile is. Empty unless ``autoLoadPrior`` is on and a prior is
    active."""
    opts = state.options()
    if not opts.autoLoadPrior or opts.priorAnchorWeightPct <= 0.0:
        return [], []
    active = state.active_prior(ticker)
    if active is None:
        return [], []
    from volfit.api import prior_transport
    from volfit.calib.prior import build_prior_anchor
    from volfit.calib.varswap import varswap_total_variance

    regime = state.dynamics_regime()
    scheme = state.fit_settings().weightScheme
    extra_opts: list[OptionQuote] = []
    extra_vs: list[VarSwapQuote] = []
    for iso, tau, k, w, prepared, _band in rows:
        node = prior_transport.prior_node(active, iso)
        if node is None:
            continue
        moved = prior_transport.transported_prior_slice(node, float(prepared.forward), regime)
        qw = resolve_weights(scheme, k, w)
        sum_w = float(np.sum(qw)) if qw is not None else float(k.size)
        budget = (opts.priorAnchorWeightPct / 100.0) * sum_w
        target, unmet = build_prior_anchor(
            moved.implied_w, node.tau, k, tau, budget, scheme=scheme,
            deltas=tuple(opts.priorAnchorDeltas),
        )
        if target is not None:
            tol = _VOL_TOL / (target.inv_vega * np.sqrt(np.maximum(target.weights, 1e-12)))
            for kj, pj, tj in zip(target.k, target.target_price, tol):
                extra_opts.append(
                    OptionQuote(t=tau, x=float(np.exp(kj)), price=float(pj), tol=float(tj))
                )
        if budget > 0.0 and unmet > 0.0:
            w_vs = varswap_total_variance(moved.implied_w) * (tau / node.tau)
            u = budget * unmet
            sigma_vs = float(np.sqrt(max(w_vs, 1e-12) / tau))
            zeta = 2.0 * sigma_vs * tau * _VOL_TOL / np.sqrt(u)
            extra_vs.append(VarSwapQuote(t=tau, total_var=float(w_vs), tol=float(zeta)))
    return extra_opts, extra_vs


def _fit(state: AppState, ticker: str, request: AffineFitRequest) -> AffineFitResponse:
    """Run the calibration and assemble the response (uncached inner step)."""
    rows = _gather(state, ticker, request.fitMode)
    if len(rows) < 2:
        raise ValueError("affine surface fit needs at least two expiries with quotes")
    opts = state.options()  # grid size + roughness are global hyperparameters now
    expiries = np.array([t for _, t, _, _, _, _ in rows])
    x_lo_vertex, k_hi = _lowest_vertex_x(rows)

    t_nodes, x_nodes = _vertex_grid(expiries, x_lo_vertex, k_hi, opts.gridTNodes, opts.gridXNodes)
    x_grid, t_grid = _pde_grids(expiries, k_hi)

    options = _option_quotes(rows, state.fit_settings().weightScheme)
    prior_opts, prior_vs = _prior_anchor_quotes(state, ticker, rows)
    options = options + prior_opts
    # Flat initial guess: the median quoted local variance (= vol^2), clipped.
    all_var = np.concatenate([np.maximum(w, 1e-12) / t for _, t, _, w, _, _ in rows])
    var0 = float(np.clip(np.median(all_var), request.varLo, request.varHi))
    surface0 = AffineVarianceSurface(
        t_nodes=t_nodes, x_nodes=x_nodes, theta=np.full((t_nodes.size, x_nodes.size), var0)
    )
    varswaps = _varswap_quotes(state, ticker, rows, state.fit_settings().weightScheme) + prior_vs
    cal = calibrate_affine(
        surface0,
        options,
        x_grid,
        t_grid,
        varswaps=varswaps,
        varswap_k_lo=_VARSWAP_K_LO,
        bounds=(request.varLo, request.varHi),
        reg_lambda=opts.gridRegLambda,
        reg_rho=opts.gridRegRho,
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
                density=_price_density(cal.solution, i_exp),
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


#: Upper bound on total affine vertices (gridXNodes * #expiries) for the
#: "Optimal size" suggestion: the calibration's cost scales with the vertex
#: count (the multi-RHS Dupire sensitivities), so ~#quotes vertices would be
#: minutes-slow. This keeps the suggested grid calibratable in seconds; the
#: user can still set a larger grid by hand (it runs in the background job).
_OPTIMAL_MAX_VERTICES = 160


def optimal_grid_size(state: AppState, ticker: str, fit_mode: str = "mid"):
    """Suggested grid size ~ the observed quote count (the 'Optimal size' button).

    Time vertices auto (one per observed expiry); strike vertices ~ the average
    quotes per expiry, so total vertices approximate the total observed quotes —
    capped at ``_OPTIMAL_MAX_VERTICES`` so the heavy affine LSQ stays tractable.
    """
    from volfit.api.schemas_affine import OptimalGridSize

    rows = _gather(state, ticker, fit_mode)  # raises UnknownNodeError on bad ticker
    n_exp = len(rows)
    n_quotes = sum(int(k.size) for _, _, k, _, _, _ in rows)
    if not n_exp:
        return OptimalGridSize(
            gridXNodes=state.options().gridXNodes, gridTNodes=0, nQuotes=0, nExpiries=0
        )
    target = round(n_quotes / n_exp)  # avg quotes per expiry
    cap = max(3, _OPTIMAL_MAX_VERTICES // (n_exp + 1))  # +1: the t = 0 vertex row
    n_x = int(max(3, min(target, cap, 60)))
    return OptimalGridSize(gridXNodes=n_x, gridTNodes=0, nQuotes=n_quotes, nExpiries=n_exp)


def affine_key(state: AppState, ticker: str, request: AffineFitRequest) -> tuple:
    """Affine surface cache key (no spot shift — that is transported on read).

    Includes the Options vertex grid + roughness (the single source of truth) so a
    grid change re-fits; the rest mirrors the slice fit key (quote/var-swap/event/
    settings/forward/options/data versions)."""
    from volfit.api import service

    isos = [e.isoformat() for e in sorted(state.forwards(ticker))]  # raises if unknown
    versions = tuple(service.session_version(state, ticker, iso) for iso in isos)
    vs_versions = tuple(service.varswap_version(state, ticker, iso) for iso in isos)
    opts = state.options()
    return (
        ticker,
        request.fitMode,
        versions,
        vs_versions,
        state.events_version,
        state.settings_version,
        state.forwards_version,
        state.options_version,
        state.data_version(ticker),
        state.active_prior_version(ticker),  # a fetched prior re-anchors the LV fit
        opts.gridXNodes, opts.gridTNodes, opts.gridRegLambda, opts.gridRegRho,
        request.model_dump_json(),
    )


def _cache(state: AppState) -> dict:
    cache = getattr(state, _CACHE_ATTR, None)
    if cache is None:
        cache = {}
        setattr(state, _CACHE_ATTR, cache)
    return cache


def affine_dirty(state: AppState, ticker: str, request: AffineFitRequest) -> bool:
    """Whether the ticker's LV surface is STALE (calibrated before, inputs drifted)."""
    ptr = state.get_affine_ptr(ticker)
    return ptr is not None and ptr != affine_key(state, ticker, request)


def calibrate_affine_surface(
    state: AppState, ticker: str, request: AffineFitRequest
) -> AffineFitResponse:
    """Force-(re)calibrate the LV surface and mark it calibrated (the explicit
    Calibrate / background job path), regardless of autoCalibrate."""
    key = affine_key(state, ticker, request)
    hit = _fit(state, ticker, request)
    _cache(state)[key] = hit
    state.set_affine_ptr(ticker, key)
    return hit


def affine_payload(state: AppState, ticker: str, request: AffineFitRequest) -> AffineFitResponse:
    """Displayed LV surface for the Local-Vol workspace, served FROZEN.

    The affine least-squares is heavy (it scales with the vertex count), so the
    read path NEVER recalibrates synchronously — that would freeze the LV tab.
    The (re)calibration runs in the background Calibrate job (or fetch-driven
    auto-calibrate), exactly like the user's workflow; here we only:

    * bootstrap ONCE if the ticker has never been calibrated (so the first open
      shows a surface), then
    * serve the frozen calibrated surface, with ``stale`` flagging that the inputs
      (quotes / grid / data) have drifted since — press Calibrate to rebuild.

    A spot move is transported on read (affine_transport), no refit.
    """
    key = affine_key(state, ticker, request)
    ptr = state.get_affine_ptr(ticker)
    cache = _cache(state)
    if ptr is None:  # one-time bootstrap so the LV view is never empty
        hit = _fit(state, ticker, request)
        cache[key] = hit
        state.set_affine_ptr(ticker, key)
    else:
        hit = cache.get(ptr)
        if hit is None:  # pointer outlived its cache entry (defensive)
            hit = _fit(state, ticker, request)
            cache[key] = hit
            state.set_affine_ptr(ticker, key)
    stale = state.get_affine_ptr(ticker) != key
    from volfit.api.affine_transport import attach_affine_priors, transport_affine_response

    moved = transport_affine_response(state, ticker, hit)
    with_prior = attach_affine_priors(state, ticker, moved)
    return with_prior.model_copy(update={"stale": stale})
