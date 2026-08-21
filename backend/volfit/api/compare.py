"""Side-by-side model comparison of one smile node (V3.2 item 12).

Backs GET /smiles/{ticker}/{expiry}/compare: the node's quotes are prepared
ONCE through the exact edited-inputs path the production fit consumes
(prepare_slice + edited_fit_inputs + resolve_weights + edited_band), then
every requested family (LQD / SVI-JW / Multi-Core Sigmoid) is fitted to those
same inputs at the LIVE hyperparameters and reported with the uniform metric
set of the offline adjudication instrument (backtest.dispatch.fit_node) —
including the per-family ANALYTIC butterfly validity signal
(volfit.models.diagnostics.analytic_butterfly, one protocol for both).

STRICTLY READ-ONLY relative to the committed record (the quality.py
doctrine): never ``fit_or_get``, never a calibrated-pointer move, no spot
mutation, no state version bumps. The ACTIVE displayed family's committed
record is REUSED (read-only) when fresh — its fit_key matches the live key;
the other families fit ad hoc as pure function calls whose results land in
the endpoint's own bounded FIFO side cache on the AppState, keyed
(fit_key, model) so any input change invalidates for free. The ad-hoc fits
carry no var-swap / prior / calendar targets — a like-for-like fit of each
family to the same quotes (the dispatch.fit_node semantics); the reused
committed row is the production fit as displayed.
"""

from __future__ import annotations

import time
from collections import OrderedDict

import numpy as np

from volfit.api.schemas import SmilePoint
from volfit.api.schemas_compare import CompareModelFit, CompareResponse, CompareValidity
from volfit.api.service import (
    K_DISPLAY_HI,
    K_DISPLAY_LO,
    K_PAD,
    _display_grid,
    _overlay_settings,
    alpha_law_wings,
    edited_band,
    edited_fit_inputs,
    effective_lqd_order,
    fill_nonfinite,
    fit_key,
    prepare_slice,
)
from volfit.api.state import AppState
from volfit.calib.rms import max_quote_error, node_error_terms, rms
from volfit.calib.weights import resolve_weights
from volfit.models.diagnostics import (
    analytic_butterfly,
    butterfly_tolerance,
    numeric_handles,
    numeric_lee_slopes,
    numeric_var_swap_w,
)
from volfit.models.display import build_display_fit
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.basis import lee_slopes
from volfit.models.lqd.calibrate import calibrate_slice

#: The comparable families, in book order (palette: green / blue / violet).
COMPARE_MODELS = ("lqd", "svi", "sigmoid")
_LABELS = {"lqd": "LQD", "svi": "SVI-JW", "sigmoid": "MCS"}
#: FIFO bound on the side cache (a handful of nodes x 3 families in practice).
_CACHE_MAX = 64


class CompareCache:
    """Bounded FIFO side map of computed compare rows, keyed (fit_key, model).

    Lives as a lazily-created plain attribute on the AppState — NEVER
    persisted, never part of the fit cache; invalidation is the key change
    itself (fit_key already carries every input version). ``hits`` counts
    served entries (testability: a second identical call must not refit)."""

    def __init__(self, max_entries: int = _CACHE_MAX) -> None:
        self.entries: OrderedDict[tuple, CompareModelFit] = OrderedDict()
        self.max_entries = max_entries
        self.hits = 0

    def get(self, key: tuple) -> CompareModelFit | None:
        row = self.entries.get(key)
        if row is not None:
            self.hits += 1
        return row

    def put(self, key: tuple, row: CompareModelFit) -> None:
        self.entries[key] = row
        while len(self.entries) > self.max_entries:
            self.entries.popitem(last=False)  # FIFO: evict the oldest entry


def compare_cache(state: AppState) -> CompareCache:
    """The state's compare side cache, created lazily on first use."""
    cache = getattr(state, "_compare_cache", None)
    if cache is None:
        cache = CompareCache()
        state._compare_cache = cache
    return cache


def _finite_or_none(x) -> float | None:
    """float(x) when finite, else None — optional-friendly wire values."""
    if x is None:
        return None
    x = float(x)
    return x if np.isfinite(x) else None


def _slice_curve(prepared, slice_) -> list[SmilePoint]:
    """The slice's IV curve on the SAME display grid as service.model_curve
    (dense over the observed quote range, extended wings, LQD alpha-law
    remote wings) — so the compare overlay aligns with the smile chart."""
    k_obs_lo = float(prepared.k.min()) - K_PAD
    k_obs_hi = float(prepared.k.max()) + K_PAD
    grid = _display_grid(
        min(K_DISPLAY_LO, k_obs_lo), max(K_DISPLAY_HI, k_obs_hi), k_obs_lo, k_obs_hi
    )
    w = np.maximum(slice_.implied_w(grid), 0.0)
    p = getattr(slice_, "params", None)
    if p is not None and (
        getattr(p, "alpha_left", 0.0) > 0.0 or getattr(p, "alpha_right", 0.0) > 0.0
    ):
        w = alpha_law_wings(slice_, grid, w)
    vols = fill_nonfinite(np.sqrt(w / prepared.tau))
    return [SmilePoint(k=float(kk), vol=float(v)) for kk, v in zip(grid, vols)]


def _n_params(family: str, slice_) -> int | None:
    """Free parameter count of a fitted slice (the flexibility column)."""
    if family == "lqd":
        return int(slice_.params.to_vector().size)
    if family == "sigmoid":
        return int(slice_.to_vector().size)
    return 5  # RawSVI: (a, b, rho, m, sigma)


def _validity(family: str, slice_, k: np.ndarray) -> CompareValidity | None:
    """The family's analytic butterfly signal over the traded range."""
    if k.size < 2:
        return None
    kind, min_v, _neg = analytic_butterfly(family, slice_, float(k.min()), float(k.max()))
    certified = None if kind == "recon" else bool(min_v >= -butterfly_tolerance(kind))
    return CompareValidity(kind=kind, minValue=_finite_or_none(min_v), certified=certified)


def _fit_family(family: str, k, w, tau, weights, band, settings, ticker: str):
    """Ad-hoc fit of one family at the LIVE hyperparameters — a pure function
    call (mirrors service._slice_task's settings threading: LQD order guard,
    coords + per-underlier tail alphas; the overlays via the same
    OverlaySettings the fit-pool workers read, incl. sviChart / mcsChart /
    leeSlopeMax / bellyRepair). No var-swap / prior / calendar targets."""
    if family == "lqd":
        alpha_left, alpha_right = settings.tail_alphas(ticker)
        result = calibrate_slice(
            k, w, t=tau, n_order=effective_lqd_order(settings.nOrder, k.size),
            weights=weights, band=band,
            reg_lambda=settings.regLambda, reg_power=settings.regPower,
            barrier_center=settings.barrierCenter, barrier_scale=settings.barrierScale,
            mid_anchor_weight=settings.midAnchorWeight, coords=settings.lqdCoords,
            alpha_left=alpha_left, alpha_right=alpha_right,
        )
        return result.slice
    display = build_display_fit(family, k, w, tau, weights, _overlay_settings(settings), band=band)
    return display.slice


def _committed_slice(state: AppState, ticker: str, iso: str, fit_mode: str, key: tuple, family: str):
    """The ACTIVE displayed family's committed slice when FRESH, else None.

    Read-only: calibrated pointer + fit cache only (never fit_or_get). Fresh
    means the pointer's fit_key equals the live key, so the committed fit was
    produced from exactly today's inputs/settings — reusable as this family's
    row. Only the DISPLAYED family reuses (the record's LQD backbone under a
    non-LQD display carries production var-swap/prior targets the ad-hoc
    compare fits deliberately omit — mixing would skew the comparison)."""
    ptr = state.get_calibrated_ptr(ticker, iso, fit_mode)
    if ptr is None or ptr[0] != key:
        return None
    record = state.get_fit(ptr[0])
    if record is None:
        return None
    if record.display is not None:
        return record.display.slice if record.display.model == family else None
    return record.result.slice if family == "lqd" else None


def _model_row(
    family: str, slice_, prepared, k, w, weights, band,
    fit_ms: float | None, reused: bool,
) -> CompareModelFit:
    """Uniform metrics of one fitted slice (the dispatch.fit_node columns)."""
    tau = prepared.tau
    rms_bp = max_bp = None
    if k.size:
        model_iv = np.sqrt(np.maximum(slice_.implied_w(k), 1e-12) / tau)
        mid_iv = np.sqrt(np.maximum(np.asarray(w, float), 1e-12) / tau)
        num, den = node_error_terms(model_iv, mid_iv, weights=weights, band=band)
        rms_bp = rms(num, den) * 1e4
        max_bp = max_quote_error(model_iv, mid_iv, band) * 1e4  # same target as rms_bp
    if family == "lqd":  # exact closed forms (the analytic backbone)
        h = atm_handles(slice_, tau)
        atm, skew = h.sigma0, h.skew
        lee_l, lee_r = lee_slopes(slice_.params)
        vs_w = slice_.var_swap_strike()
    else:
        h = numeric_handles(slice_, tau)
        atm, skew = h.atm_vol, h.skew
        # V3.1: MCS ships analytic k-space Lee slopes; SVI stays numeric.
        lee_l, lee_r = slice_.lee_slopes() if family == "sigmoid" else numeric_lee_slopes(slice_)
        vs_w = numeric_var_swap_w(slice_)
    vs_vol = float(np.sqrt(max(float(vs_w), 0.0) / tau)) if tau > 0.0 else None
    return CompareModelFit(
        model=family, label=_LABELS[family],
        curve=_slice_curve(prepared, slice_),
        rmsBp=_finite_or_none(rms_bp), maxIvBp=_finite_or_none(max_bp),
        atmVol=_finite_or_none(atm), skew=_finite_or_none(skew),
        leeLeft=_finite_or_none(lee_l), leeRight=_finite_or_none(lee_r),
        varSwapVol=_finite_or_none(vs_vol),
        validity=_validity(family, slice_, k),
        nParams=_n_params(family, slice_),
        fitMs=None if fit_ms is None else round(fit_ms, 2),
        reused=reused,
    )


def compare_payload(
    state: AppState, ticker: str, expiry_iso: str,
    models: tuple[str, ...] = COMPARE_MODELS, fit_mode: str = "mid",
) -> CompareResponse:
    """Fit every requested family to one node's prepared quotes; one row each.

    Raises UnknownNodeError (-> 404) for an unknown node. A node with no
    chain / no forward yet yields an empty, honest ``models`` list. A single
    family's fit failure is recorded on its row (ok=False), never a 500."""
    expiry = state.resolve_expiry(ticker, expiry_iso)  # UnknownNodeError -> 404
    iso = expiry.isoformat()
    settings = state.fit_settings()
    response = CompareResponse(
        ticker=ticker, expiry=expiry_iso, fitMode=fit_mode, activeModel=settings.model
    )
    prepared = prepare_slice(state, ticker, iso)
    if prepared is None:
        return response

    # The production fit's own post-edit inputs, resolved ONCE for every family.
    k, w, _ = edited_fit_inputs(state, ticker, iso, prepared, None)
    weights = resolve_weights(settings.weightScheme, k, w)
    band = edited_band(state, ticker, iso, prepared, fit_mode)
    key = fit_key(state, ticker, iso, fit_mode)
    cache = compare_cache(state)

    for family in models:
        row = cache.get((key, family))
        if row is None:
            try:
                committed = _committed_slice(state, ticker, iso, fit_mode, key, family)
                if committed is not None:
                    row = _model_row(family, committed, prepared, k, w, weights, band,
                                     fit_ms=None, reused=True)
                else:
                    t0 = time.perf_counter()
                    slice_ = _fit_family(family, k, w, prepared.tau, weights, band,
                                         settings, ticker)
                    fit_ms = (time.perf_counter() - t0) * 1e3
                    row = _model_row(family, slice_, prepared, k, w, weights, band,
                                     fit_ms=fit_ms, reused=False)
            except Exception as exc:  # noqa: BLE001 - a fit break is a row, not a 500
                row = CompareModelFit(
                    model=family, label=_LABELS[family], ok=False,
                    error=type(exc).__name__ + ": " + str(exc)[:160],
                )
            cache.put((key, family), row)
        response.models.append(row)
    return response
