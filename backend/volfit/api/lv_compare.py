"""The Dupire twin beside the affine sheet — POST /fit/affine/{ticker}/compare.

LV Dupire-twin compare arc (ROADMAP 2026-09-08), phase D2. The Local Vol
lens's Compare tab confronts the two directions of the Dupire equation:

* the AFFINE sheet — the piecewise-affine local variance the LV workspace
  fits to quotes through the forward PDE (volfit.api.affine_fit, Note 04);
* the Dupire TWIN — the local variance read off the calibrated PARAMETRIC
  surface the classical way (Gatheral's formula: differentiate the implied
  total variance, then divide — models.localvol.dupire_surface).

What this module does, in order:

1. gathers the live rows exactly as the affine fit does (``_gather``: the
   edited quotes, the fit-target band, the τ clock) and keeps the expiries
   that have a calibrated parametric fit (``service.displayed_base`` — the
   overlay when active, else LQD, at the ANCHOR spot the fits were
   calibrated at; a read never calibrates in the gated workflow, so a
   missing fit is reported in ``skippedExpiries`` and fewer than two is a
   404). The whole comparison is ANCHORED: the affine sheet and curves come
   from the calibration cache (not the spot-transported display payload),
   so a spot tick never rebuilds the twin — the response carries the active
   ``spotShift`` and the lens says the comparison sits at the calibration
   spot (transporting the twin like the affine sheet is a recorded rider);
2. builds the affine VERTEX lattice and variance box from those rows
   (``_resolve_grid`` / ``_lv_bounds`` — the same functions the fit uses, so
   the twin lands on the fit's own vertices and inside its own box);
3. builds the total-variance surface for the chip (``smooth`` PCHIP in τ or
   the ``buckets`` staircase), differentiates it on the vertices
   (``extract_twin``: the display-range guard, the box clip, the per-row
   repair counters) and holds the result as an ``AffineVarianceSurface`` —
   the fitted sheet's own finite-element object (its Delaunay triangulation,
   a flat left wing), so the nodal DIFFERENCE is the whole difference;
4. reprices the SMOOTH twin (``DupireTwinSurface``: the same local variance
   evaluated where the march asks) through the twin's DISPLAY operator — the
   fit's own lattice (``_pde_grids`` with its dx / dt rule / right-edge
   floor) refined by ``TWIN_DX_FACTOR`` / ``TWIN_DT_FACTOR`` and marched with
   the second-order ``TWIN_SCHEME`` — the value-only call + put marches (the
   OTM inversion of wrap 2026-08-31b) and the buffered right-wing display
   lattice (wrap 2026-09-02i). Two controls ride the same operator: a FLAT
   surface (its error is the operator's floor — reported as ``operatorBp``)
   and the nodal sheet itself (``sheetRoundTripBp``: what the coarse lattice
   loses against the smooth twin). Never the k-space CN pricer of
   models.localvol.pde. Chosen 2026-09-08 after the first look: the nodal
   sheet marched on the calibration operator read 136 bp on the one-month
   front against a 154 bp FLAT control — the first-order operator, not the
   twin;
5. scores every expiry three ways on the fit target (the ``AffineSmile``
   basis) — twin, parametric source, affine sheet (from the displayed LV
   payload) — and closes the round trip: the twin repriced back against its
   parametric source at the quoted strikes.

Read-only: the twin is never a fit, a prior, a seed or a θ_ref. Cached per
the affine key + the chips + the displayed LV pointer (no spot version: the
comparison is anchored, so a live feed's ticks hit the cache).
"""

from __future__ import annotations

import numpy as np

from volfit.api import affine_fit, affine_views_ext
from volfit.api.displayed import displayed_slice, displayed_var_swap_w
from volfit.api.schemas import SmilePoint
from volfit.api.schemas_affine import (
    AffineFitRequest,
    AffineFitResponse,
    DupireCountersOut,
    LvCompareRequest,
    LvCompareResponse,
    LvCompareScore,
    LvCompareSmile,
)
from volfit.api.state import AppState
from volfit.calib.rms import node_error_terms, quote_errors, rms as rms_of_terms
from volfit.calib.weights import resolve_weights
from volfit.models.localvol import (
    TWIN_DT_FACTOR,
    TWIN_DX_FACTOR,
    TWIN_SCHEME,
    AffineVarianceSurface,
    DupireTwinSurface,
    FlatSurface,
    build_w_surface,
    extract_twin,
)
from volfit.models.localvol.reprice import refined_grids, reprice_affine_dupire

_CACHE_ATTR = "_lv_compare_cache"  # AppState side-dict (affine_fit._side_dict)


class ParametricFitMissing(LookupError):
    """Fewer than two expiries carry a displayed parametric fit (404 on the wire)."""


def _parametric_rows(state: AppState, ticker: str, rows, fit_mode: str):
    """``(rows, records, skipped)``: the affine rows that have a calibrated
    parametric fit at the ANCHOR spot (``displayed_base`` — before any spot
    transport), their FitRecords, and the ISOs that have none."""
    from volfit.api import service  # heavy module: lazy, as affine_fit does

    kept, records, skipped = [], [], []
    for row in rows:
        rec = service.displayed_base(state, ticker, row[0], fit_mode)
        if rec is None:
            skipped.append(row[0])
            continue
        kept.append(row)
        records.append(rec)
    return kept, records, skipped


def _march_scheme(state: AppState, ticker: str, rows, opts) -> tuple[str, float]:
    """``(time_scheme, dt_max)`` exactly as the affine fit picks them: a var-swap
    quote (market or prior) makes the left slope free and pins implicit Euler,
    otherwise the Options scheme with its own dt ceiling."""
    from volfit.api.affine_varswap import market_varswap_quotes

    _, _, prior_vs = affine_fit._prior_lv_targets(state, ticker, rows)
    scheme_weights = state.fit_settings().weightScheme
    varswaps = market_varswap_quotes(state, ticker, rows, scheme_weights) + prior_vs
    scheme = "implicit" if varswaps else opts.timeScheme
    dt_max = affine_fit._DT_MAX_RANNACHER if scheme == "rannacher" else affine_fit._DT_MAX
    return scheme, dt_max


def _points(grid: np.ndarray, vol: np.ndarray) -> list[SmilePoint]:
    return [SmilePoint(k=float(k), vol=float(v)) for k, v in zip(grid, vol) if np.isfinite(v)]


def _bp(err: np.ndarray) -> tuple[float, float]:
    """``(rms, max)`` of an absolute bp residual vector (0, 0 when empty)."""
    err = err[np.isfinite(err)]
    if err.size == 0:
        return 0.0, 0.0
    return float(np.sqrt(np.mean(err**2))), float(err.max())


def _affine_score(smile) -> LvCompareScore:
    return LvCompareScore(
        rmsError=float(smile.rmsError),
        maxBp=float(smile.maxIvErrorBp),
        rmsBp=None,
        convergedBp=float(smile.rmsConvergedBp),
    )


def _lattice_matches(affine: AffineFitResponse, t_nodes, x_nodes) -> bool:
    if not affine.hasFit or not affine.tNodes or not affine.xNodes:
        return False
    at, ax = np.asarray(affine.tNodes, dtype=float), np.asarray(affine.xNodes, dtype=float)
    return (
        at.shape == t_nodes.shape and ax.shape == x_nodes.shape
        and bool(np.allclose(at, t_nodes)) and bool(np.allclose(ax, x_nodes))
    )


def _affine_request(request: LvCompareRequest) -> AffineFitRequest:
    return AffineFitRequest(fitMode=request.fitMode, varLo=request.varLo, varHi=request.varHi)


def _twin_record(
    state: AppState, ticker: str, request: LvCompareRequest, affine: AffineFitResponse | None = None
) -> LvCompareResponse:
    """The uncached build (module docstring, steps 1–5). ``affine`` is the
    displayed LV payload (what the lens shows: transported, stale-flagged);
    the cached entry point passes it in AFTER it settled the LV pointer, so
    the cache key and the sheet agree on which fit was displayed."""
    from volfit.api import service
    from volfit.api.service import K_DISPLAY_HI, K_DISPLAY_LO

    rows = affine_fit._gather(state, ticker, request.fitMode)
    rows, records, skipped = _parametric_rows(state, ticker, rows, request.fitMode)
    if len(rows) < 2:
        raise ParametricFitMissing(
            f"{ticker}: the Dupire twin needs at least two expiries with a parametric fit "
            f"(found {len(rows)}; Calibrate first)"
        )
    opts = state.options()
    ts = np.array([t for _, t, _, _, _, _ in rows])
    if np.any(np.diff(ts) <= 0.0):
        raise ValueError("expiry clocks must increase strictly for the twin")
    t_nodes, x_nodes, k_hi, _ = affine_fit._resolve_grid(rows, opts)
    var_lo, var_hi = affine_fit._lv_bounds(rows, opts, request.varLo, request.varHi)

    # 3. the twin on the vertices
    slices = [displayed_slice(rec) for rec in records]
    w_surface = build_w_surface(request.tInterp, ts, slices)
    twin = extract_twin(
        w_surface, ts, x_nodes, t_nodes, t_interp=request.tInterp,
        var_lo=var_lo, var_hi=var_hi, k_lo=K_DISPLAY_LO, k_hi=K_DISPLAY_HI,
    )
    surface = AffineVarianceSurface(t_nodes=t_nodes, x_nodes=x_nodes, theta=twin.theta)

    # 4. the twin's DISPLAY operator: the fit's own lattice (its dx / dt rule,
    #    the virtual-front node, the right-edge floor) refined by the
    #    dupire_twin factors and marched with the second-order Rannacher
    #    scheme — where the flat control's front-expiry error is ~2 bp. The
    #    SMOOTH twin is marched (evaluated where the march asks); the nodal
    #    sheet's own march on the same operator says what the lattice loses.
    _, dt_max = _march_scheme(state, ticker, rows, opts)
    march_exps = ts
    virtual_rows = affine_fit._virtual_front_rows(rows)
    if virtual_rows:
        march_exps = np.sort(np.append(ts, [r[1] for r in virtual_rows]))
    x_grid, t_grid = affine_fit._pde_grids(
        march_exps, k_hi, dt_max, affine_fit._pde_dx(rows), x_max_min=opts.lvXMaxMin
    )
    x_fine, t_fine = refined_grids(x_grid, t_grid, TWIN_DX_FACTOR, TWIN_DT_FACTOR)
    smooth = DupireTwinSurface(
        w_surface, ts, t_interp=request.tInterp, var_lo=var_lo, var_hi=var_hi,
        k_lo=K_DISPLAY_LO, k_hi=K_DISPLAY_HI,
    )

    def march(surf, x, payoff: str = "call"):
        return reprice_affine_dupire(
            surf, x, t_fine, expiries=ts, payoff=payoff, time_scheme=TWIN_SCHEME
        )

    sol = march(smooth, x_fine)
    put_sol = march(smooth, x_fine, "put")
    x_disp = affine_views_ext.display_lattice(
        x_fine, k_hi + affine_fit._K_PAD, affine_fit._tail_total_variance(surface, x_nodes, ts)
    )
    ext = march(smooth, x_disp) if x_disp is not None else None
    # The operator's floor: a FLAT surface at the ladder's median implied
    # variance, whose exact reprice is known — its error is the operator's own.
    flat_var = float(np.median(np.concatenate([np.maximum(w, 1e-12) / t for _, t, _, w, _, _ in rows])))
    flat_vol = float(np.sqrt(flat_var))
    flat_sol = march(FlatSurface(flat_var), x_fine)
    sheet_sol = march(surface, x_fine)  # the nodal sheet on the same operator
    exp_index = {float(e): i for i, e in enumerate(sol.expiries)}

    if affine is None:  # the displayed LV payload (settles the pointer; stale flag)
        affine = affine_fit.affine_payload(state, ticker, _affine_request(request))
    # The ANCHOR sheet: the calibration cache entry behind the displayed
    # pointer, before the spot transport relabels its lattice — the twin is
    # built from the anchor parametric records, so this is the like-for-like.
    ptr = state.get_affine_ptr(ticker)
    anchor = affine_fit._cache(state).get(ptr) if ptr is not None else None
    if anchor is not None and not anchor.hasFit:
        anchor = None
    affine_by_iso = {s.expiry: s for s in anchor.smiles} if anchor is not None else {}
    lattice_ok = anchor is not None and _lattice_matches(anchor, t_nodes, x_nodes)

    # 5. per-expiry smiles and scores
    weight_scheme = state.fit_settings().weightScheme
    smiles: list[LvCompareSmile] = []
    twin_bp, param_bp, rt_bp, sheet_bp, op_bp = [], [], [], [], []
    twin_num = twin_den = param_num = param_den = 0.0
    for (iso, t, k, w, prepared, band), rec, slice_ in zip(rows, records, slices):
        i_exp = exp_index[t]
        klo, khi = float(k.min()), float(k.max())
        grid = np.linspace(klo - affine_fit._K_PAD, khi + affine_fit._K_PAD, affine_fit._N_SMILE)
        quote_vol = np.sqrt(np.maximum(w, 1e-12) / t)
        twin_iv = affine_fit._model_vol_at(sol, i_exp, t, k)
        sheet_iv = affine_fit._model_vol_at(sheet_sol, i_exp, t, k)
        flat_iv = affine_fit._model_vol_at(flat_sol, i_exp, t, k)
        param_iv = np.sqrt(np.maximum(np.asarray(slice_.implied_w(k), dtype=float), 0.0) / t)
        e_twin = np.abs(quote_errors(twin_iv, quote_vol, band)) * 1e4
        e_param = np.abs(quote_errors(param_iv, quote_vol, band)) * 1e4
        e_rt = np.abs(twin_iv - param_iv) * 1e4
        e_sheet = np.abs(sheet_iv - param_iv) * 1e4
        e_op = np.abs(flat_iv - flat_vol) * 1e4
        twin_bp.extend(e_twin.tolist())
        param_bp.extend(e_param.tolist())
        rt_bp.extend(e_rt.tolist())
        sheet_bp.extend(e_sheet.tolist())
        op_bp.extend(e_op.tolist())
        # the calibration-consistent weighted basis (var-swap term included)
        weights = resolve_weights(weight_scheme, k, w)
        target = service.varswap_target(state, ticker, iso, k, weights, t)
        vs_quote = float(np.sqrt(max(target.total_var, 0.0) / t)) if target is not None else None
        # The twin's fair var-swap: the static log-contract replication on its
        # marched prices (model-agnostic; the source PDE needs the hat basis).
        twin_vs = affine_fit._model_varswap_vol(sol, i_exp, t, x_fine, method="static")
        param_vs = float(np.sqrt(max(displayed_var_swap_w(rec), 0.0) / t))
        vs_twin = (twin_vs, vs_quote, float(target.weight)) if target is not None else None
        vs_param = (param_vs, vs_quote, float(target.weight)) if target is not None else None
        n_t, d_t = node_error_terms(twin_iv, quote_vol, weights, band, vs_twin)
        n_p, d_p = node_error_terms(param_iv, quote_vol, weights, band, vs_param)
        twin_num, twin_den = twin_num + n_t, twin_den + d_t
        param_num, param_den = param_num + n_p, param_den + d_p
        aff = affine_by_iso.get(iso)
        smiles.append(
            LvCompareSmile(
                expiry=iso,
                t=float(prepared.t),
                tau=float(t),
                forward=float(prepared.forward),
                twin=affine_fit._reconstruct_smile(sol, i_exp, t, klo, khi, put_sol),
                twinExt=affine_views_ext.extended_model(
                    sol, i_exp, t, klo, khi, x_fine, affine_fit._K_PAD, affine_fit._N_SMILE,
                    put_solution=put_sol, ext_call_solution=ext,
                ),
                parametric=_points(
                    grid, np.sqrt(np.maximum(np.asarray(slice_.implied_w(grid), dtype=float), 0.0) / t)
                ),
                quotes=affine_fit._quote_bands(state, ticker, iso, prepared, request.fitMode),
                affine=list(aff.model) if aff is not None else [],
                twinScore=LvCompareScore(
                    rmsError=rms_of_terms(n_t, d_t), maxBp=_bp(e_twin)[1], rmsBp=_bp(e_twin)[0]
                ),
                parametricScore=LvCompareScore(
                    rmsError=rms_of_terms(n_p, d_p), maxBp=_bp(e_param)[1], rmsBp=_bp(e_param)[0]
                ),
                affineScore=_affine_score(aff) if aff is not None else None,
                roundTripBp=_bp(e_rt)[0],
                roundTripMaxBp=_bp(e_rt)[1],
                sheetRoundTripBp=_bp(e_sheet)[0],
                operatorBp=_bp(e_op)[0],
            )
        )

    theta = twin.theta
    local_vol = np.sqrt(theta)
    raw = twin.raw
    affine_sheet: list[list[float]] = []
    diff: list[list[float]] = []
    if lattice_ok and anchor is not None:
        affine_sheet = anchor.localVol
        diff = (local_vol - np.asarray(anchor.localVol, dtype=float)).tolist()
    c = twin.counters
    n_diff = int(twin.differentiated.sum())
    message = (
        f"{request.tInterp} twin on {t_nodes.size} x {x_nodes.size} vertices "
        f"({n_diff} strikes differentiated); repairs: butterfly {c.total_butterfly}, "
        f"calendar {c.total_calendar}, floored {c.total_floored}, capped {c.total_capped}"
        f"; smile on the {TWIN_SCHEME} operator dt/{TWIN_DT_FACTOR} dx/{TWIN_DX_FACTOR}"
    )
    if skipped:
        message += f"; no parametric fit on {len(skipped)} expiries (skipped)"
    if anchor is not None and not lattice_ok:
        message += "; the displayed LV fit is on another lattice (no difference sheet)"
    return LvCompareResponse(
        ticker=ticker,
        tInterp=request.tInterp,
        tails=request.tails,
        tNodes=[float(v) for v in t_nodes],
        xNodes=[float(v) for v in x_nodes],
        localVolTwin=local_vol.tolist(),
        cellDiagMain=[[bool(v) for v in row] for row in surface.cell_diag_main()],
        rawLocalVariance=[[None if not np.isfinite(v) else float(v) for v in row] for row in raw],
        differentiated=[bool(v) for v in twin.differentiated],
        counters=DupireCountersOut(
            butterfly=c.butterfly.tolist(), calendar=c.calendar.tolist(),
            floored=c.floored.tolist(), capped=c.capped.tolist(), clean=c.clean,
        ),
        varLo=float(var_lo),
        varHi=float(var_hi),
        localVolAffine=affine_sheet,
        diffLocalVol=diff,
        hasAffine=anchor is not None,
        affineStale=bool(affine.stale),
        affineLatticeMatches=lattice_ok,
        smiles=smiles,
        skippedExpiries=skipped,
        twinScore=LvCompareScore(
            rmsError=rms_of_terms(twin_num, twin_den),
            maxBp=_bp(np.array(twin_bp))[1],
            rmsBp=_bp(np.array(twin_bp))[0],
        ),
        parametricScore=LvCompareScore(
            rmsError=rms_of_terms(param_num, param_den),
            maxBp=_bp(np.array(param_bp))[1],
            rmsBp=_bp(np.array(param_bp))[0],
        ),
        affineScore=(
            LvCompareScore(
                rmsError=float(anchor.surfaceRmsError), maxBp=float(anchor.maxIvErrorBp),
                rmsBp=float(anchor.rmsIvErrorBp), convergedBp=float(anchor.rmsConvergedBp),
            )
            if anchor is not None else None
        ),
        roundTripBp=_bp(np.array(rt_bp))[0],
        roundTripMaxBp=_bp(np.array(rt_bp))[1],
        sheetRoundTripBp=_bp(np.array(sheet_bp))[0],
        operatorBp=_bp(np.array(op_bp))[0],
        twinRepairs=(smooth.n_butterfly, smooth.n_calendar, smooth.n_floored, smooth.n_capped),
        message=message,
    )


def lv_compare_key(state: AppState, ticker: str, request: LvCompareRequest) -> tuple:
    """The affine key (quote / var-swap / event / settings / forward / options /
    data / prior versions + every LV option) + the chips and the displayed LV
    pointer (a fresh LV fit refreshes the affine columns). NO spot version:
    the comparison is anchored at the calibration spot, so a live feed's
    ticks are cache hits — the first live use showed a twin rebuilt on every
    tick (2026-09-08)."""
    base = affine_fit.affine_key(state, ticker, _affine_request(request))
    return base + ("lv_compare", request.tInterp, request.tails, state.get_affine_ptr(ticker))


def lv_compare_payload(state: AppState, ticker: str, request: LvCompareRequest) -> LvCompareResponse:
    """The cached Compare-tab payload (module docstring).

    The displayed LV payload is read FIRST: on a never-calibrated ticker the
    ungated read bootstraps the LV fit and sets its pointer, which the cache
    key carries — keying before that read would file the first build under
    "no fit" and miss on every later call (test-locked)."""
    affine = affine_fit.affine_payload(state, ticker, _affine_request(request))
    key = lv_compare_key(state, ticker, request)
    cache = affine_fit._side_dict(state, _CACHE_ATTR)
    hit = cache.get(key)
    if hit is None:
        hit = _twin_record(state, ticker, request, affine)
        cache[key] = hit
    # The active spot shift is a READ-time attribute (the anchored record is
    # served whole from the cache): attach it, and say so in the message.
    shift = float(state.spot_shift(ticker))
    if shift == 0.0:
        return hit
    return hit.model_copy(
        update={
            "spotShift": shift,
            "message": f"{hit.message}; spot moved {shift:+.2%} — compared at the calibration spot",
        }
    )
