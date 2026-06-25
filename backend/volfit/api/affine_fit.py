"""Direct local-vol-affine surface fit behind POST /fit/affine/{ticker}.

Calibrates the piecewise-affine local-VARIANCE surface of
Docs/piecewise_affine_local_variance_calibration.tex straight to a ticker's
option quotes (volfit.models.localvol.calibrate_affine), as opposed to
GET /localvol/{ticker} which *extracts* a Dupire grid from the already-fitted
LQD smiles. Pipeline:

  1. gather every expiry's edited prepared quotes (the same masked/amended set
     the LQD fit uses), convert mid implied vols to normalized forward call
     prices and vega-scaled tolerances (so the LSQ is ~vol-error weighted);
  2. build a tensor vertex grid (0 + a spread of listed expiries; strikes on the
     symmetric DELTA axis x = exp(±sigma*sqrt(T*)Phi^-1(delta)) clipped to the
     traded range with the ATM node x = 1 forced in — gridStrikeMode "linear"
     keeps the legacy uniform-in-x axis) and the fine PDE x/t grids (t hits every
     quoted expiry exactly, as the note's forward Dupire march requires);
  3. calibrate the nodal local variances (bound-constrained, second-difference
     roughness), then reconstruct each expiry's arbitrage-free smile by
     inverting the Dupire PDE call prices through the Black formula.

Results are cached per (ticker, fit mode, per-expiry session versions, fit
settings, forwards, request hyperparameters). Heavy but explicit: it runs only
on an actual fit request, never on the smile hot path.
"""

from __future__ import annotations

import numpy as np
from scipy.special import ndtri  # inverse standard-normal CDF (delta -> quantile)

from volfit.api.prior_mode import resolve_prior_mode
from volfit.api.schemas import DistributionArrays, QuoteBand, SmilePoint, VarSwapInfo
from volfit.api.schemas_affine import AffineFitRequest, AffineFitResponse, AffineSmile
from volfit.api.state import AppState
from volfit.calib.rms import node_error_terms, rms as rms_of_terms
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


class _InterpSlice:
    """Minimal SmileModel over reconstructed (k, w) points: linear-interpolated
    total variance, flat-extrapolated beyond the range — enough for the
    left-extended stacked density's tail (Breeden-Litzenberger from w(k))."""

    def __init__(self, k: np.ndarray, w: np.ndarray) -> None:
        order = np.argsort(k)
        self._k = np.asarray(k, dtype=float)[order]
        self._w = np.asarray(w, dtype=float)[order]

    def implied_w(self, k):  # noqa: ANN001 - SmileModel duck-type
        return np.interp(np.asarray(k, dtype=float), self._k, self._w)


def _extended_density(model: list[SmilePoint], tau: float) -> DistributionArrays | None:
    """Risk-neutral density of a reconstructed smile, left-extended to the
    display lower bound (k_min = -1.4) for the stacked "Densities" overlay."""
    if len(model) < 2 or tau <= 0.0:
        return None
    from volfit.api.analytics import stacked_density_arrays

    k = np.array([p.k for p in model], dtype=float)
    w = np.array([p.vol * p.vol * tau for p in model], dtype=float)
    x, density = stacked_density_arrays(_InterpSlice(k, w))
    return DistributionArrays(x=x.tolist(), density=density.tolist())

#: PDE strike step and OTM span (x = K/F); the note uses dx = 0.01 to x = 2.2.
_X_DX = 0.01
_X_MAX_MIN = 2.5
_X_HI_PAD = 1.4
#: PDE time step ceiling (each quoted expiry is forced to be a grid node).
#: Backward-Euler is 1st-order, so it needs the fine 0.01 ceiling for ~1bp accuracy.
_DT_MAX = 0.01
#: Coarser ceiling used with the Rannacher (2nd-order CN) scheme (Stage 7): equal
#: accuracy at ~3x fewer steps (validated: rannacher@0.03 ~ implicit@0.01). The march
#: cost is O(N_t), so this is the per-eval speed-up.
_DT_MAX_RANNACHER = 0.03
#: Vega-scaled price tolerance: residual (P - y)/(vega * VOL_TOL) ~ vol error
#: in units of VOL_TOL, so a 1% vol miss contributes ~1.
_VOL_TOL = 0.01
_VEGA_FLOOR = 1e-3
#: Reconstructed-smile display grid.
_N_SMILE = 81
_K_PAD = 0.02
_CACHE_ATTR = "_affine_cache"  # AppState attribute, added lazily here


#: Per-side delta locations for the delta-spaced strike axis (50Δ = ATM). The
#: deep 1/2Δ nodes are usually clipped to the traded range; they only survive
#: for names quoted that far out (where the convex-wing constraint can then bite).
_DELTA_SET = (0.01, 0.02, 0.05, 0.10, 0.25, 0.40, 0.50)
#: The delta defining the 'convex vol below ...Δ' wing region.
_CONVEX_WING_DELTA = 0.05
#: Absolute ceiling on the adaptive nodal local-vol cap (variance) = (400% vol)²;
#: a safety bound for extreme names, not a real fit cap.
_LV_VAR_CEILING = 16.0
#: Upper bound on the free left-wing slope multiple ``a`` (× the first-cell slope).
_LEFT_A_MAX = 20.0
#: Stage 8 early-stop: terminate the cold fit once the best OPTION-BLOCK misfit has
#: not improved by ``_STALL_RTOL`` (relative) over ``_STALL_WINDOW`` objective evals.
#: Tuned on the SPY/NVDA benchmark: fast-converging names (NVDA, a clear knee) get
#: ~3.3x at +0.25 bp RMS; slow-converging names with no knee (SPY) get ~1.45x at
#: +0.10 bp — adaptive by design (stop when converged, keep going while improving).
#: Warm-started recalibrations converge before the window, so they are unaffected.
_STALL_WINDOW = 12
_STALL_RTOL = 5e-3
#: GN solver (lvSolver="gn") tuning — hardened on the SPY/NVDA benchmark. GN's
#: option-block-misfit trajectory is noisier than trf's monotone trust region, so it
#: gets a MORE CONSERVATIVE early-stop (larger window, smaller rtol) to keep the
#: surface close to trf; the inner lsmr is loosened to 1e-6 (the cheap Numba march
#: makes extra outer evals affordable, and 1e-10 over-solves while 1e-4 misfires).
_GN_STALL_WINDOW = 18
_GN_STALL_RTOL = 3e-3
_GN_LSMR_TOL = 1e-6


def _lv_bounds(rows, opts, var_lo_req: float, var_hi_req: float) -> tuple[float, float]:
    """Nodal local-VARIANCE box bounds for the calibration.

    The fixed request cap (60% vol) clamps the deep-put LOCAL vol of high-vol
    names (e.g. NVDA), starving the put wing — local variance in the wing runs
    well above implied. The cap is therefore ADAPTIVE: at least the request cap,
    and at least ``lvVolCapMult`` x the highest observed implied vol across the
    surface, capped at ``_LV_VAR_CEILING`` (400% vol). The floor stays at the
    request value (a low-vol name is unaffected). Returns ``(var_lo, var_hi)``.
    """
    all_iv = np.concatenate(
        [np.sqrt(np.maximum(w, 1e-12) / t) for _, t, _, w, _, _ in rows]
    )
    sigma_max = float(all_iv.max())
    cap_vol = max(float(np.sqrt(var_hi_req)), float(opts.lvVolCapMult) * sigma_max)
    return float(var_lo_req), float(min(cap_vol * cap_vol, _LV_VAR_CEILING))


def _seed_theta(
    prev, t_nodes: np.ndarray, x_nodes: np.ndarray,
    var0: float, var_lo: float, var_hi: float,
) -> tuple[np.ndarray, str]:
    """Warm-start nodal variances (Stage 2) from the previous calibrated surface.

    Reuses the previous surface's theta when the vertex grid is unchanged (the
    common intraday recalibration), else linearly interpolates it onto the new
    grid; clipped to the box either way. Flat ``var0`` when no usable previous
    surface exists. Returns ``(theta0_grid, seed_source)``.

    The caller keeps ``theta_ref`` at the flat ``var0`` regardless, so a flat seed
    is byte-identical to the legacy start and a warm seed changes only the
    starting point — not the regularization or the converged optimum (refinement
    2 of the roadmap: seed != temporal prior).
    """
    flat = np.full((t_nodes.size, x_nodes.size), var0)
    if prev is None or not getattr(prev, "tNodes", None) or not getattr(prev, "localVol", None):
        return flat, "flat"
    pt = np.asarray(prev.tNodes, dtype=float)
    px = np.asarray(prev.xNodes, dtype=float)
    pth = np.asarray(prev.localVol, dtype=float) ** 2  # localVol = sqrt(nodal variance)
    if pth.shape != (pt.size, px.size) or pt.size < 2 or px.size < 2:
        return flat, "flat"
    if (
        pt.shape == t_nodes.shape and px.shape == x_nodes.shape
        and np.allclose(pt, t_nodes) and np.allclose(px, x_nodes)
    ):
        return np.clip(pth, var_lo, var_hi), "prev-affine"
    from scipy.interpolate import RegularGridInterpolator

    interp = RegularGridInterpolator(
        (pt, px), pth, method="linear", bounds_error=False, fill_value=None
    )
    tt, xx = np.meshgrid(t_nodes, x_nodes, indexing="ij")
    seed = interp(np.column_stack([tt.ravel(), xx.ravel()])).reshape(tt.shape)
    return np.clip(seed, var_lo, var_hi), "prev-affine-interp"


def _parametric_seed(
    state: AppState, ticker: str, fit_mode: str,
    t_nodes: np.ndarray, x_nodes: np.ndarray, var_lo: float, var_hi: float,
) -> np.ndarray | None:
    """Cold-start nodal variances from the PARAMETRIC surface's Dupire local
    variance (Stage 2b) — a far better start than flat for the first fit.

    Reuses the Dupire extraction the GET /localvol path runs: build the displayed
    parametric (LQD/SVI/sigmoid) total-variance surface w(k, t) and read its
    Gatheral local variance at the affine vertices (k = log x, t = the τ vertices).
    Dupire-from-implied is noisy, so this is a SEED ONLY: ``theta_ref`` stays flat,
    so it changes the starting point, never the regularization or the converged
    optimum. Uses ONLY already-calibrated parametric slices (cached-lookup, never
    triggers a parametric fit — the app calibrates parametric before LV, so they are
    warm); returns None (→ flat fallback) when fewer than two are calibrated yet, or
    on any extraction failure — best-effort by construction.
    """
    try:
        from volfit.api import service
        from volfit.api.localvol import _w_surface
        from volfit.models.localvol import extract_grid

        records = []  # cached-only: the parametric fits the Calibrate job already made
        for iso in (e.isoformat() for e in sorted(state.forwards(ticker))):
            ptr = state.get_calibrated_ptr(ticker, iso, fit_mode)  # (fit-key, cal-spot)
            rec = state.get_fit(ptr[0]) if ptr is not None else None
            if rec is not None:
                records.append((iso, rec))
        if len(records) < 2:
            return None
        # τ clock, to match the affine vertices (built from prepared.tau)
        ts = np.array([float(rec.prepared.tau) for _, rec in records])
        order = np.argsort(ts)
        ts = ts[order]
        slices = [service.displayed_slice(records[i][1]) for i in order]
        if np.any(np.diff(ts) <= 0):
            return None
        k_nodes = np.log(np.clip(np.asarray(x_nodes, dtype=float), 1e-6, None))
        t_eval = np.maximum(np.asarray(t_nodes, dtype=float), 1e-4)  # avoid t = 0 exactly
        dt = 0.2 * float(min(ts[0], np.min(np.diff(ts)) if ts.size > 1 else ts[0]))
        ext = extract_grid(_w_surface(ts, slices), k_nodes, t_eval, dk=2e-3, dt=max(dt, 1e-4))
        theta = ext.grid.sigma ** 2  # (n_t, n_x) local variance
        if theta.shape != (t_nodes.size, x_nodes.size) or not np.all(np.isfinite(theta)):
            return None
        return np.clip(theta, var_lo, var_hi)
    except Exception:
        return None


#: AppState side-dict (ticker -> AffineFitDiagnostics) for the last affine fit.
#: Kept OFF the wire response (wall times are non-deterministic), but available
#: to the perf rails and a future "warm-started / N evals" UI cue.
_LAST_DIAG_ATTR = "_affine_last_diag"


def _record_diagnostics(state: AppState, ticker: str, diag) -> None:
    cache = getattr(state, _LAST_DIAG_ATTR, None)
    if cache is None:
        cache = {}
        setattr(state, _LAST_DIAG_ATTR, cache)
    cache[ticker] = diag


def last_affine_diagnostics(state: AppState, ticker: str):
    """Diagnostics of the ticker's most recent affine fit, or None if never fit
    this session (Stage-0 counters + the Stage-2 ``seed_source``)."""
    return getattr(state, _LAST_DIAG_ATTR, {}).get(ticker)


def _pick_spread(values: np.ndarray, n: int) -> np.ndarray:
    """``n`` roughly-even entries of a sorted array, always incl. both ends."""
    values = np.asarray(values, dtype=float)
    if values.size <= n:
        return values
    idx = np.unique(np.round(np.linspace(0, values.size - 1, n)).astype(int))
    return values[idx]


def _time_nodes(expiries: np.ndarray, n_t_floor: int) -> np.ndarray:
    """Time vertices (Stage 3): 0 + a short-end node before the first expiry +
    every listed lit expiry, densified in sqrt(T) up to a floor count.

    The base set always carries a knee at each observed expiry (where the data
    constrains the surface) plus one node at the sqrt-T midpoint between 0 and the
    first expiry (= T1/4) — this resolves the steep short-end term structure and
    decouples the unconstrained t = 0 row from the first, most-curved smile.
    ``n_t_floor`` > 0 is a FLOOR on the number of POSITIVE time vertices: the
    widest sqrt(T) gaps are split (one midpoint at a time) until at least that
    many exist, giving "some sqrt(T) density up to the last expiry"; it NEVER
    drops an expiry. ``n_t_floor`` <= 0 yields just the base set.
    """
    exps = np.unique(np.asarray(expiries, dtype=float))
    exps = exps[exps > 0.0]
    if exps.size == 0:
        return np.array([0.0])
    pre = 0.25 * float(exps[0])  # sqrt-T midpoint of [0, T1]: ((0 + sqrt(T1)) / 2)^2
    nodes = np.unique(np.concatenate([[pre], exps]))
    floor = int(n_t_floor)
    while nodes.size < floor and nodes.size < 500:  # split the widest sqrt(T) gap
        s = np.sqrt(nodes)
        i = int(np.argmax(np.diff(s)))
        mid = (0.5 * (s[i] + s[i + 1])) ** 2
        nodes = np.unique(np.concatenate([nodes, [mid]]))
    return np.unique(np.concatenate([[0.0], nodes]))


def _axis_scale(rows) -> tuple[float, float]:
    """(sigma_star, t_star) sizing the standardized-moneyness strike axis: the
    ATM vol of the LONGEST-dated row (the widest smile sets the axis reach) and
    the max event-variance maturity tau across the lit expiries."""
    t_star = max(t for _, t, _, _, _, _ in rows)
    sigma_star = 0.20
    for _, t, k, w, _, _ in rows:
        if t == t_star and t > 0.0:
            order = np.argsort(k)
            w_atm = float(np.interp(0.0, k[order], np.asarray(w)[order]))
            sigma_star = float(np.sqrt(max(w_atm, 1e-8) / t))
            break
    return sigma_star, float(t_star)


def _delta_strike_nodes(
    sigma_star: float, t_star: float, k_lo_obs: float, k_hi_obs: float, n_floor: int
) -> np.ndarray:
    """Strike vertices x = K/F on the symmetric delta axis, clipped to the data.

    Each delta d maps to a standardized log-moneyness k = ±sigma*·sqrt(T*)·Φ⁻¹(d)
    (put side k <= 0, call side k >= 0; 50Δ -> ATM), giving dense near-ATM nodes
    that reach the wings at controlled deltas. The set is clipped to the OBSERVED
    [k_lo, k_hi] (no vertex past the data — the note: wings beyond quotes are set
    by regularization, not vertices) with x = 1 forced in. ``n_floor``
    (gridXNodes) is a minimum: the single WIDEST gap is split one node at a time
    until exactly that many strike vertices exist.

    The widest-gap refinement (the same incremental scheme as ``_time_nodes`` on
    the time axis) lands the count ON the floor, regardless of how many delta
    nodes survived clipping. The previous refine inserted a midpoint into EVERY
    gap each pass (doubling, n -> 2n-1), so the result overshot the floor
    non-monotonically: a base count just below half the floor doubled twice while
    one just above it doubled once — giving wildly different resolutions to two
    similar names (e.g. NVDA 10 -> 19 -> 37 vs SPY 11 -> 21 at the same floor),
    with the SPARSER base ending up FINER. One-at-a-time splitting removes that.
    """
    scale = max(sigma_star * np.sqrt(max(t_star, 1e-8)), 1e-6)
    ks = [0.0]
    for d in _DELTA_SET:
        q = float(ndtri(d))  # <= 0 for d <= 0.5, exactly 0 at 0.5
        ks.append(scale * q)  # put side (k <= 0)
        ks.append(-scale * q)  # call side (k >= 0)
    k = np.unique(np.clip(np.array(ks), k_lo_obs, k_hi_obs))
    floor = max(int(n_floor), 2)
    while k.size < floor and k.size >= 2:  # split the single widest gap, one node at a time
        i = int(np.argmax(np.diff(k)))
        k = np.insert(k, i + 1, 0.5 * (k[i] + k[i + 1]))
    return np.unique(np.concatenate([np.exp(k), [1.0]]))


def _vertex_grid(
    expiries: np.ndarray, x_lo_vertex: float, k_hi: float, n_t_floor: int, n_x: int
) -> tuple[np.ndarray, np.ndarray]:
    """Legacy LINEAR-in-x tensor vertex set (gridStrikeMode == "linear").

    Strikes uniformly spaced in x from ``x_lo_vertex`` to the top observed strike,
    incl. x = 1 (kept for reproducibility; the delta-spaced axis is the default);
    time vertices use the shared sqrt(T) axis (_time_nodes), so the Stage-3 time
    improvement applies in both strike modes.
    """
    t_nodes = _time_nodes(expiries, n_t_floor)
    x_hi = float(np.exp(k_hi))
    x_nodes = np.unique(np.concatenate([np.linspace(x_lo_vertex, x_hi, n_x), [1.0]]))
    return t_nodes, x_nodes


def _resolve_grid(rows, opts):
    """The vertex grid + PDE x_max + convex-wing columns for the CURRENT options.

    Single source of truth shared by the calibration (``_fit``) and the read-only
    grid summary (``grid_info``), so the Options panel always reports exactly the
    grid the fit will build. Returns ``(t_nodes, x_nodes, k_hi, convex_cols)``.
    """
    expiries = np.array([t for _, t, _, _, _, _ in rows])
    all_k = np.sort(np.concatenate([k for _, _, k, _, _, _ in rows]))
    k_lo_obs, k_hi = float(all_k[0]), float(all_k[-1])
    sigma_star, t_star = _axis_scale(rows)  # sizes the delta axis + the 5Δ boundary

    if opts.gridStrikeMode == "delta":
        t_nodes = _time_nodes(expiries, opts.gridTNodes)
        x_nodes = _delta_strike_nodes(sigma_star, t_star, k_lo_obs, k_hi, opts.gridXNodes)
    else:  # legacy linear-in-x
        x_lo_vertex, k_hi = _lowest_vertex_x(rows)
        t_nodes, x_nodes = _vertex_grid(
            expiries, x_lo_vertex, k_hi, opts.gridTNodes, opts.gridXNodes
        )

    convex_cols = None
    if opts.convexWing:
        k_wing = sigma_star * np.sqrt(max(t_star, 1e-8)) * float(ndtri(_CONVEX_WING_DELTA))
        # Confine the convex-wing constraint to the true EXTRAPOLATION wing:
        # vertices at/below the 5Δ-put strike AND strictly below the deepest
        # observed quote, so it shapes only the unquoted tail and never overrides
        # dense quoted data (the same principle as the calendar-arb traded-range
        # fix). Without the data bound, a fine strike grid (large gridXNodes) stacks
        # convexity constraints onto quoted strikes and distorts the put wing —
        # badly for low-vol names where the wing is naturally near-linear (SPY at
        # gridXNodes=20 read 26bp instead of 3bp), while a high-vol name's
        # already-convex wing hid it. Empty (no unquoted wing vertex) ⇒ no
        # constraint, which is correct: dense data fully determines the wing.
        in_wing = x_nodes <= np.exp(k_wing) * (1.0 + 1e-9)
        beyond_data = x_nodes < np.exp(k_lo_obs)
        cols = np.flatnonzero(in_wing & beyond_data)
        convex_cols = cols if cols.size else None
    return t_nodes, x_nodes, k_hi, convex_cols


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


def _pde_grids(
    expiries: np.ndarray, k_hi: float, dt_max: float = _DT_MAX
) -> tuple[np.ndarray, np.ndarray]:
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
        n = max(1, int(np.ceil((e - prev) / dt_max)))
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


def _model_varswap_vol(
    solution, i_exp: int, t: float, x_grid: np.ndarray,
    surface=None, t_grid: np.ndarray | None = None, method: str = "static",
) -> float:
    """Model fair var-swap vol of an expiry — the SAME construction the var-swap
    residual uses, so the displayed level matches what was calibrated. "static"
    is the log-contract replication on the PDE grid; "source_pde" runs the backward
    source PDE on the calibrated ``surface`` up to ``t`` (volfit.models.localvol
    .varswap_pde)."""
    if method == "source_pde" and surface is not None and t_grid is not None:
        from volfit.models.localvol import solve_varswap_source

        pos = int(np.searchsorted(t_grid, t))
        w_vs, _ = solve_varswap_source(surface, x_grid, t_grid[: pos + 1])
        return float(np.sqrt(max(w_vs, 0.0) / t))
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


def _model_vol_at(solution, i_exp: int, t: float, k: np.ndarray) -> np.ndarray:
    """Reconstructed implied vol of the calibrated surface at log-moneyness k."""
    price = solution.price_at(i_exp, np.exp(k))
    model_w = implied_total_variance(k, price)
    return np.sqrt(np.maximum(model_w, 0.0) / t)


def _iv_error_bp(solution, i_exp: int, t: float, k: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Per-quote |model - quote| implied vol at the calibrated surface, bp."""
    model_vol = _model_vol_at(solution, i_exp, t, k)
    quote_vol = np.sqrt(np.maximum(w, 0.0) / t)
    return np.abs(model_vol - quote_vol) * 1e4


def _node_rms_terms(
    state: AppState, ticker: str, iso: str, tau: float, k: np.ndarray, w: np.ndarray,
    band, model_vs_vol: float, model_iv: np.ndarray,
) -> tuple[float, float]:
    """``(sum_weighted_sq, sum_weight)`` of one reconstructed LV smile's RMS vol
    error, on the same calibration-consistent basis as the Parametric workspace:
    distance to the chosen fit-target band, the active weighting scheme, and the
    var-swap quote (volfit.calib.rms)."""
    from volfit.api import service  # local import: service is heavy

    weights = resolve_weights(state.fit_settings().weightScheme, k, w)
    mid_iv = np.sqrt(np.maximum(w, 1e-12) / tau)
    target = service.varswap_target(state, ticker, iso, k, weights, tau)
    vs = None
    if target is not None and tau > 0.0:
        quote_vol = float(np.sqrt(max(target.total_var, 0.0) / tau))
        vs = (float(model_vs_vol), quote_vol, float(target.weight))
    return node_error_terms(model_iv, mid_iv, weights, band, vs)


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


def _prior_lv_targets(state: AppState, ticker: str, rows):
    """Per-mode LV prior targets: ``(extra option quotes, baskets, extra var-swaps)``.

    Routes ``OptionsSettings.priorPersistenceMode`` (volfit.api.prior_mode) for the
    LV surface: ``strike_gap`` -> the legacy data-gap synthetic option quotes (the
    ``_prior_anchor_quotes`` path); ``quote_operator`` / ``hybrid`` -> signed-basket
    operator targets (volfit.api.prior_lv) that KEEP the RR/BF coupling; ``off`` /
    ``overlay`` / ``graph_only`` / ``smile_factor`` (until Phase 6) -> none. Gated by
    ``autoLoadPrior`` (the transition master) + an active prior, mirroring
    ``service.prior_targets`` so the LV surface and the parametric smile agree."""
    opts = state.options()
    plan = resolve_prior_mode(opts)
    if not opts.autoLoadPrior or not plan.any_calibration_prior:
        return [], [], []
    if plan.strike_anchor:
        prior_opts, prior_vs = _prior_anchor_quotes(state, ticker, rows)
        return prior_opts, [], prior_vs
    if plan.operators:
        active = state.active_prior(ticker)
        if active is None:
            return [], [], []
        from volfit.api import prior_transport
        from volfit.api.prior_lv import build_operator_lv_targets

        regime = state.dynamics_regime()
        scheme = state.fit_settings().weightScheme
        baskets: list = []
        vs_quotes: list = []
        for iso, tau, k, w, prepared, _band in rows:
            node = prior_transport.prior_node(active, iso)
            if node is None:
                continue
            moved = prior_transport.transported_prior_slice(node, float(prepared.forward), regime)
            qw = resolve_weights(scheme, k, w)
            b, v = build_operator_lv_targets(moved.implied_w, node.tau, tau, k, qw, opts)
            baskets.extend(b)
            vs_quotes.extend(v)
        return [], baskets, vs_quotes
    return [], [], []


def _fit(
    state: AppState, ticker: str, request: AffineFitRequest, rows=None
) -> AffineFitResponse:
    """Run the calibration and assemble the response (uncached inner step).

    ``rows`` defaults to the live chain (``_gather``); a caller may inject its own
    ``(iso, tau, k, w, prepared, band)`` rows — e.g. the graph-extrapolation LV
    projection (``graph_lv``), which swaps the target total variance ``w`` for the
    graph-reconstructed smile so the LV surface is fitted to the extrapolation."""
    if rows is None:
        rows = _gather(state, ticker, request.fitMode)
    if len(rows) < 2:
        raise ValueError("affine surface fit needs at least two expiries with quotes")
    opts = state.options()  # grid size + roughness are global hyperparameters now
    expiries = np.array([t for _, t, _, _, _, _ in rows])
    t_nodes, x_nodes, k_hi, convex_cols = _resolve_grid(rows, opts)

    options = _option_quotes(rows, state.fit_settings().weightScheme)
    # Prior persistence (mode-routed): strike-gap synthetic quotes OR signed-basket
    # operator targets that keep the RR/BF coupling; empty unless a prior is active.
    prior_opts, prior_baskets, prior_vs = _prior_lv_targets(state, ticker, rows)
    options = options + prior_opts
    # Adaptive local-vol box bounds: the cap scales with the name's observed IV
    # (the fixed 60% cap starved high-vol put wings); floor stays at the request.
    var_lo, var_hi = _lv_bounds(rows, opts, request.varLo, request.varHi)
    varswaps = _varswap_quotes(state, ticker, rows, state.fit_settings().weightScheme) + prior_vs
    # Left-wing (x < x_min) linear extrapolation slope multiple ``a``:
    #  - var-swap present  -> ``a`` is a FREE calibration variable (the deep-put
    #    tail steepness is set to hit the var-swap), init = leftWingSlopeMult;
    #  - else convex wing  -> fixed a = leftWingSlopeMult (steeper rising wing);
    #  - else              -> a = 0 (flat clamp, the historical behavior).
    fit_left_a = len(varswaps) > 0
    # Stage 7 — time discretisation: Rannacher (2nd order) lets the PDE march on a
    # several-fold COARSER time grid at equal accuracy, the per-eval speed-up. It does
    # not apply with a free left slope (var-swap fits keep implicit Euler), so those
    # keep the fine dt. The PDE time grid is built with the matching step ceiling.
    time_scheme = "implicit" if fit_left_a else opts.timeScheme
    dt_max = _DT_MAX_RANNACHER if time_scheme == "rannacher" else _DT_MAX
    x_grid, t_grid = _pde_grids(expiries, k_hi, dt_max)
    # Stage 6′: the Numba vectorized-Thomas march (~6× the banded path) drives the
    # hot path when enabled + importable; it self-restricts to the implicit /
    # no-left-slope case inside solve_affine_dupire and falls back to banded.
    from volfit.models.localvol.affine_march import numba_available

    engine = "numba" if (opts.lvFastKernel and numba_available()) else "banded"
    # Stage 5 (revisited): matrix-free Gauss-Newton avoids trf's dense SVD — now that
    # the Numba march makes each eval cheap, GN's no-SVD evals win ~1.3-1.65x. Opt-in
    # (var-swap fits keep trf — GN doesn't carry the free-left-slope column). GN gets a
    # more conservative early-stop + a looser lsmr (hardened on the benchmark).
    # GN engages only for the smooth MID objective with the Numba march active (its
    # win depends on the cheap eval). The bid-ask / haircut band objective is
    # non-smooth (zero gradient inside the band) — fragile for GN's smooth LM — so those
    # keep trf's robust trust region, as do var-swap fits and the banded-march fallback.
    gn = (
        opts.lvSolver == "gn"
        and not fit_left_a
        and engine == "numba"
        and request.fitMode == "mid"
    )
    if gn:
        stall_window = _GN_STALL_WINDOW if opts.lvEarlyStop else 0
        stall_rtol, gn_lsmr_tol = _GN_STALL_RTOL, _GN_LSMR_TOL
    else:
        stall_window = _STALL_WINDOW if opts.lvEarlyStop else 0
        stall_rtol, gn_lsmr_tol = _STALL_RTOL, 1e-10
    a_init = opts.leftWingSlopeMult if (opts.convexWing or fit_left_a) else 0.0
    # Flat reference: the median quoted local variance (= vol^2), clipped. This is
    # ``theta_ref`` (the roughness anchor) AND the flat-fallback seed.
    all_var = np.concatenate([np.maximum(w, 1e-12) / t for _, t, _, w, _, _ in rows])
    var0 = float(np.clip(np.median(all_var), var_lo, var_hi))
    # Warm start (Stage 2): seed theta0 from the previous calibrated surface when
    # one exists; theta_ref stays the flat var0 so the regularization is unchanged
    # (a flat seed is byte-identical to the legacy start).
    prev = _cache(state).get(state.get_affine_ptr(ticker))
    theta0, seed_source = _seed_theta(prev, t_nodes, x_nodes, var0, var_lo, var_hi)
    if seed_source == "flat":  # Stage 2b: cold start -> the parametric Dupire seed
        pseed = _parametric_seed(state, ticker, request.fitMode, t_nodes, x_nodes, var_lo, var_hi)
        if pseed is not None:
            theta0, seed_source = pseed, "parametric"
    surface0 = AffineVarianceSurface(
        t_nodes=t_nodes, x_nodes=x_nodes, theta=theta0, left_extrap_a=a_init,
    )
    cal = calibrate_affine(
        surface0,
        options,
        x_grid,
        t_grid,
        varswaps=varswaps,
        baskets=prior_baskets,
        varswap_k_lo=_VARSWAP_K_LO,
        varswap_method=opts.varSwapMethod,
        bounds=(var_lo, var_hi),
        reg_lambda=opts.gridRegLambda,
        reg_rho=opts.gridRegRho,
        reg_nodes=(t_nodes, x_nodes),  # spacing-aware roughness on the real grid
        convex_cols=convex_cols,
        convex_weight=opts.convexWingWeight if opts.convexWing else 0.0,
        front_tie_weight=opts.frontTieWeight if opts.frontTie else 0.0,
        fit_left_a=fit_left_a,
        left_a_bounds=(0.0, _LEFT_A_MAX),
        theta_ref=np.full(t_nodes.size * x_nodes.size, var0),
        seed_source=seed_source,
        mid_anchor_weight=state.fit_settings().midAnchorWeight,
        time_scheme=time_scheme,  # Stage 7: Rannacher coarse-dt march when applicable
        # Stage 8: early-stop the cold fit once cost improvement stalls (warm recals
        # converge before the window, so they are byte-identical either way). The TRF
        # and GN solvers carry their own hardened window/rtol (set above).
        stall_window=stall_window,
        stall_rtol=stall_rtol,
        engine=engine,  # Stage 6′: Numba vectorized-Thomas march when available
        gn=gn,  # Stage 5 (revisited): matrix-free GN (opt-in, default trf)
        gn_lsmr_tol=gn_lsmr_tol,
    )
    _record_diagnostics(state, ticker, cal.diagnostics)

    exp_index = {float(t): i for i, t in enumerate(cal.solution.expiries)}
    smiles: list[AffineSmile] = []
    iv_bp_all: list[float] = []
    rms_num = rms_den = 0.0  # pooled across expiries -> whole-surface RMS
    for iso, t, k, w, prepared, band in rows:
        i_exp = exp_index[t]
        klo, khi = float(k.min()), float(k.max())
        errs = _iv_error_bp(cal.solution, i_exp, t, k, w)
        iv_bp_all.extend(errs.tolist())
        model_vs_vol = _model_varswap_vol(
            cal.solution, i_exp, t, x_grid,
            surface=cal.surface, t_grid=t_grid, method=opts.varSwapMethod,
        )
        model = _reconstruct_smile(cal.solution, i_exp, t, klo, khi)
        # Calibration-consistent RMS (distance to the chosen fit target band, the
        # active weighting scheme, the var-swap quote) — identical basis to the
        # Parametric workspace's RMS, on the reconstructed surface's own IVs.
        num, den = _node_rms_terms(state, ticker, iso, t, k, w, band, model_vs_vol,
                                   _model_vol_at(cal.solution, i_exp, t, k))
        rms_num += num
        rms_den += den
        smiles.append(
            AffineSmile(
                expiry=iso,
                t=prepared.t,  # calendar maturity (axis); t above is the tau clock
                tau=t,
                forward=float(prepared.forward),  # for the strike / %ATM axis modes
                model=model,
                quotes=_quote_bands(state, ticker, iso, prepared),
                varSwap=_affine_varswap_info(state, ticker, iso, model_vs_vol),
                maxIvErrorBp=float(errs.max()) if errs.size else 0.0,
                rmsError=rms_of_terms(num, den),
                density=_price_density(cal.solution, i_exp),
                densityExt=_extended_density(model, t),  # left-extended to k_min=-1.4
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
        surfaceRmsError=rms_of_terms(rms_num, rms_den),
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


def grid_info(state: AppState, ticker: str, fit_mode: str = "mid"):
    """The ACTUAL vertex grid the current Options produce for ``ticker``.

    Builds the same ``_resolve_grid`` the fit uses (so the Options panel reports
    exactly what will be calibrated, honouring the floor / delta / convex-wing
    semantics), without running the heavy LSQ. Empty (zeros) when the ticker has
    fewer than two quotable expiries."""
    from volfit.api.schemas_affine import GridInfo

    opts = state.options()
    req = AffineFitRequest()
    rows = _gather(state, ticker, fit_mode)  # raises UnknownNodeError on bad ticker
    if len(rows) < 2:
        return GridInfo(
            nTNodes=0, nXNodes=0, nVertices=0, convexWingNodes=0,
            strikeMode=opts.gridStrikeMode, nExpiries=len(rows),
            capVol=0.0, floorVol=0.0,
        )
    t_nodes, x_nodes, _, convex_cols = _resolve_grid(rows, opts)
    var_lo, var_hi = _lv_bounds(rows, opts, req.varLo, req.varHi)
    return GridInfo(
        nTNodes=int(t_nodes.size),
        nXNodes=int(x_nodes.size),
        nVertices=int(t_nodes.size * x_nodes.size),
        convexWingNodes=int(0 if convex_cols is None else convex_cols.size),
        strikeMode=opts.gridStrikeMode,
        nExpiries=len(rows),
        capVol=float(np.sqrt(var_hi)),
        floorVol=float(np.sqrt(var_lo)),
    )


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
        state.events_version(ticker),
        state.settings_version,
        state.forwards_version(ticker),
        state.options_version,
        state.data_version(ticker),
        state.active_prior_version(ticker),  # a fetched prior re-anchors the LV fit
        opts.gridXNodes, opts.gridTNodes, opts.gridRegLambda, opts.gridRegRho,
        opts.gridStrikeMode, opts.convexWing, opts.convexWingWeight,
        opts.frontTie, opts.frontTieWeight, opts.lvVolCapMult, opts.leftWingSlopeMult,
        opts.varSwapMethod, opts.timeScheme, opts.lvEarlyStop, opts.lvFastKernel,
        opts.lvSolver,
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


def _empty_affine_response(ticker: str) -> AffineFitResponse:
    """An empty LV surface for a never-calibrated ticker (gated, pre-Calibrate)."""
    return AffineFitResponse(
        ticker=ticker, tNodes=[], xNodes=[], localVol=[], smiles=[],
        rmsPriceError=0.0, maxPriceError=0.0, rmsIvErrorBp=0.0, maxIvErrorBp=0.0,
        surfaceRmsError=0.0, minDensity=[], calendarViolations=0, arbitrageFree=True,
        nEvals=0, message="no fit yet — press Calibrate", stale=False, hasFit=False,
    )


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
    # Gated workflow: never calibrated yet -> serve an EMPTY surface (no fetch, no
    # heavy LV calibration) until the explicit Calibrate button, like the smile.
    if state._gated and state.get_affine_ptr(ticker) is None:
        return _empty_affine_response(ticker)
    key = affine_key(state, ticker, request)
    ptr = state.get_affine_ptr(ticker)
    cache = _cache(state)
    if ptr is None:  # one-time bootstrap so the LV view is never empty (ungated)
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
