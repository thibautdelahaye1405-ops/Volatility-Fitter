"""Uniform model fit + metrics for the compute phase (Phase 2).

For one node (asset, expiry) the production de-Americanization + inversion is run
ONCE (``prepared_quotes``, memoized), then each model in the sweep is calibrated
DIRECTLY (not via the always-LQD service overlay) so per-model speed is attributed
cleanly. Every slice exposes ``SmileModel.implied_w(k)``, so precision (in- and
out-of-sample RMS vol), worst error, and the no-butterfly check are computed
uniformly across LQD / SVI-JW / Multi-Core SIV.

"Precision" is reported honestly as three numbers — in-sample RMS, leave-every-3rd-
strike-out RMS (penalises over-fitting), and a no-arb measure — not a single fit
error that more degrees of freedom would always win.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from volfit.api.service import prepared_quotes
from volfit.api.state import AppState
from volfit.calib.band import BandTarget
from volfit.calib.rms import node_error_terms, rms
from volfit.calib.weights import resolve_weights
from volfit.models.base import SmileModel
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.sigmoid import calibrate_sigmoid
from volfit.models.svi_jw import calibrate_svi

# Production-default hyperparameters (volfit.api.schemas.FitSettings).
_LQD = dict(reg_lambda=1e-6, reg_power=1.0, barrier_center=0.90, barrier_scale=50.0,
            mid_anchor_weight=0.05)
_SVI = dict(penalty_weight=1e3, lee_slope_max=2.0, mid_anchor_weight=0.05)
_SIG = dict(ridge=1e-2, mid_anchor_weight=0.05)


@dataclass(frozen=True)
class ModelSpec:
    """One sweep point: a model family + the hyperparameters that vary."""

    family: str  # "lqd" | "svi" | "sigmoid"
    label: str
    params: dict = field(default_factory=dict)


#: The model sweep — SVI-JW baseline + the flexibility knob per family across the
#: ranges in the spec (LQD order 6-12, Multi-Core SIV 0-3 cores; SIV-0 = base SIV).
#: SIV-4 was dropped (pathologically slow, ~8.6 s/fit, with no precision gain).
DEFAULT_SWEEP: tuple[ModelSpec, ...] = (
    ModelSpec("svi", "SVI-JW"),  # the baseline
    ModelSpec("lqd", "LQD-6", {"n_order": 6}),
    ModelSpec("lqd", "LQD-8", {"n_order": 8}),
    ModelSpec("lqd", "LQD-10", {"n_order": 10}),
    ModelSpec("lqd", "LQD-12", {"n_order": 12}),
    ModelSpec("sigmoid", "SIV-0", {"n_cores": 0}),
    ModelSpec("sigmoid", "SIV-1", {"n_cores": 1}),
    ModelSpec("sigmoid", "SIV-2", {"n_cores": 2}),
    ModelSpec("sigmoid", "SIV-3", {"n_cores": 3}),
)


def _haircut_band(prepared, frac: float) -> BandTarget:
    """A fractional-haircut band: each side moved ``frac`` of the way from the
    quote (bid/ask) toward mid — the standard "haircut 0.5" meaning, per-quote and
    spread-aware (vs the app's absolute vol-point haircut)."""
    bid, mid, ask = prepared.iv_bid, prepared.iv_mid, prepared.iv_ask
    return BandTarget(
        iv_lo=mid - frac * (mid - bid),
        iv_mid=mid,
        iv_hi=mid + frac * (ask - mid),
    )


def _fit_slice(spec: ModelSpec, k, w, weights, tau, band=None) -> tuple[SmileModel, int | None]:
    """Calibrate one model at production defaults; return (slice, n_evaluations).

    ``band`` (a BandTarget) switches the calibrators to the band objective."""
    if spec.family == "lqd":
        r = calibrate_slice(k, w, t=tau, n_order=spec.params.get("n_order", 6),
                            weights=weights, band=band, **_LQD)
        return r.slice, getattr(r, "n_evaluations", None)
    if spec.family == "svi":
        c = calibrate_svi(k, w, tau, weights=weights, band=band, **_SVI)
        return c.raw, getattr(c, "n_evaluations", None)
    s = calibrate_sigmoid(k, w, tau, weights=weights, band=band,
                          n_cores=spec.params.get("n_cores", 2), **_SIG)
    return s, None


def _rms_bp(slice_: SmileModel, k, w, tau, weights=None, band=None) -> float:
    """Calibration-consistent RMS vol error (bp): distance to mid (band None) or
    band violation (band given), weighted by the scheme — via the production
    ``node_error_terms`` so it matches what the calibrator minimizes."""
    if k.size == 0:
        return 0.0
    model_iv = np.sqrt(np.maximum(slice_.implied_w(k), 1e-12) / tau)
    quote_iv = np.sqrt(np.maximum(np.asarray(w, float), 1e-12) / tau)
    num, den = node_error_terms(model_iv, quote_iv, weights=weights, band=band)
    return rms(num, den) * 1e4


def _band_subset(band, mask):
    """Slice a BandTarget to a strike subset (for the OOS refit), or None."""
    if band is None:
        return None
    return BandTarget(iv_lo=band.iv_lo[mask], iv_mid=band.iv_mid[mask], iv_hi=band.iv_hi[mask])


def _oos_rms_bp(spec: ModelSpec, k, w, weights, tau, band=None) -> float | None:
    """Leave-every-3rd-strike-out RMS on the held strikes (None if too few),
    scored consistently with the fit objective (band-aware) on the held set."""
    n = k.size
    if n < 9:
        return None
    held = np.arange(n) % 3 == 0
    kept = ~held
    wk = None if weights is None else np.asarray(weights)[kept]
    wh = None if weights is None else np.asarray(weights)[held]
    try:
        slice_, _ = _fit_slice(spec, k[kept], w[kept], wk, tau, _band_subset(band, kept))
    except Exception:  # noqa: BLE001 - a failed OOS refit is a metric, not a crash
        return None
    return _rms_bp(slice_, k[held], w[held], tau, wh, _band_subset(band, held))


def _butterfly(slice_: SmileModel, k_lo: float, k_hi: float) -> tuple[float, float]:
    """Durrleman g(k) no-butterfly measure: (min g, fraction of grid with g<0).

    g(k) = (1 - k w'/(2w))^2 - (w'/2)^2 (1/w + 1/4) + w''/2 ; g>=0 ⇔ no butterfly
    arbitrage. Computed on a fine grid spanning the traded log-moneyness range.
    """
    g = np.linspace(k_lo, k_hi, 201)
    w = np.maximum(np.asarray(slice_.implied_w(g), float), 1e-12)
    dk = g[1] - g[0]
    wp = np.gradient(w, dk)
    wpp = np.gradient(wp, dk)
    val = (1.0 - g * wp / (2.0 * w)) ** 2 - (wp / 2.0) ** 2 * (1.0 / w + 0.25) + wpp / 2.0
    finite = val[np.isfinite(val)]
    if finite.size == 0:
        return 0.0, 0.0
    return float(finite.min()), float(np.mean(finite < 0.0))


def fit_node(
    state: AppState, ticker: str, expiry: date, regime: str, sector: str,
    exercise_style: str, specs: tuple[ModelSpec, ...] = DEFAULT_SWEEP,
    fit_mode: str = "mid", weight_scheme: str = "equal", haircut_frac: float = 0.5,
) -> list[dict]:
    """De-Am + prep the node once, then fit every model; one metric row per model.

    ``weight_scheme`` ("equal" | "tv_density") sets the per-quote weights (production
    ``resolve_weights``); ``fit_mode`` ("mid" | "haircut") sets the objective — mid
    fits to mid, haircut fits inside a band shrunk ``haircut_frac`` toward mid. RMS
    is reported consistently with the objective (model−mid for mid; band violation
    for haircut), so each is the number the calibrator actually minimized."""
    t0 = time.perf_counter()
    prepared = prepared_quotes(state, ticker, expiry)
    prep_ms = (time.perf_counter() - t0) * 1e3
    k, w, tau = prepared.k, prepared.w_mid, prepared.tau
    weights = resolve_weights(weight_scheme, k, w)
    band = _haircut_band(prepared, haircut_frac) if fit_mode == "haircut" else None
    k_lo, k_hi = (float(k.min()), float(k.max())) if k.size else (0.0, 0.0)

    rows: list[dict] = []
    for spec in specs:
        base = dict(
            asset=ticker, as_of=state.reference_date.isoformat(), regime=regime,
            sector=sector, exercise_style=exercise_style,
            expiry=expiry.isoformat(), t=round(float(prepared.t), 5),
            n_quotes=int(k.size), n_deam=int(prepared.n_deamericanized),
            model=spec.label, family=spec.family, params=spec.params,
            weight_scheme=weight_scheme, fit_target=fit_mode, prep_ms=round(prep_ms, 2),
        )
        try:
            t1 = time.perf_counter()
            slice_, n_eval = _fit_slice(spec, k, w, weights, tau, band)
            fit_ms = (time.perf_counter() - t1) * 1e3
            min_g, neg_frac = _butterfly(slice_, k_lo, k_hi)
            # LQD exposes an exact martingale (density-mass) check; |dev| from 1 is
            # the arb signal. Other families have no closed form (butterfly only).
            mart = None
            if hasattr(slice_, "martingale_check"):
                mart = round(abs(float(slice_.martingale_check()) - 1.0), 6)
            base.update(
                ok=True, fit_ms=round(fit_ms, 2), n_eval=n_eval,
                in_rmse_bp=round(_rms_bp(slice_, k, w, tau, weights, band), 2),
                oos_rmse_bp=_round(_oos_rms_bp(spec, k, w, weights, tau, band)),
                bfly_min_g=round(min_g, 5), bfly_neg_frac=round(neg_frac, 4),
                lqd_martingale_dev=mart,
            )
        except Exception as exc:  # noqa: BLE001 - a fit break is a result we record
            base.update(ok=False, error=type(exc).__name__ + ": " + str(exc)[:120])
        rows.append(base)
    return rows


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 2)
