"""Model-agnostic smile diagnostics from the SmileModel interface alone.

LQD slices have exact closed-form ATM handles and var-swap level
(models/lqd/atm.py, LQDSlice.var_swap_strike). The other calibratable
families (SVI, sigmoid) expose only total implied variance w(k), so the API
needs the same headline diagnostics computed numerically from w(k):

  * ATM level / skew / curvature as finite differences of sigma(k) =
    sqrt(w(k)/t) at k = 0;
  * var-swap fair variance by log-contract static replication, the
    model-free integral 2 [ int_0^inf B(k,w) e^{-k} dk
    + int_{-inf}^0 (B(k,w) + e^k - 1) e^{-k} dk ] where B is the normalized
    Black call (matches LQDSlice.var_swap_strike = -2 E[X] to grid accuracy);
  * Lee wing slopes dw/d|k| at the far ends of a wide grid.

These power volfit.api.fit_models for non-LQD display fits; the values are
exact for LQD via the dedicated module, so this stays a fallback path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.core.black import black_call
from volfit.models.base import SmileModel

def _finite(x: float, default: float = 0.0) -> float:
    """``x`` if finite, else ``default`` — keeps a degenerate/transported slice
    (which can be non-finite at the far wings) from emitting NaN diagnostics that
    JSON-serialize to null and break the UI."""
    return float(x) if np.isfinite(x) else default


#: Central-difference step in log-moneyness for the ATM handles.
_ATM_H = 1e-3
#: Replication grid for the var-swap integral; +-6 in k captures the OTM
#: option mass to double precision for any reasonable smile.
_VS_HALF_WIDTH = 6.0
_VS_POINTS = 4001
#: Density grid: log-return support in +-_DENSITY_SD ATM standard deviations,
#: sampled at _DENSITY_POINTS for the risk-neutral pdf / CDF.
_DENSITY_SD = 8.0
_DENSITY_POINTS = 1201
_DENSITY_MIN_HALF = 0.30  # floor on the half-width for very short maturities


@dataclass(frozen=True)
class SliceHandles:
    """Numeric ATM level/skew/curvature of a smile at expiry ``t``."""

    atm_vol: float
    skew: float
    curvature: float


def numeric_handles(slice_: SmileModel, t: float) -> SliceHandles:
    """ATM vol, skew and curvature by central differences of sqrt(w/t)."""
    h = _ATM_H
    ks = np.array([-h, 0.0, h])
    vol = np.sqrt(np.maximum(slice_.implied_w(ks), 1e-12) / t)
    skew = (vol[2] - vol[0]) / (2.0 * h)
    curvature = (vol[2] - 2.0 * vol[1] + vol[0]) / (h * h)
    return SliceHandles(
        atm_vol=_finite(vol[1]), skew=_finite(skew), curvature=_finite(curvature)
    )


def numeric_var_swap_w(slice_: SmileModel) -> float:
    """Var-swap fair total variance by OTM log-contract replication.

    Returns w_varswap (same units as LQDSlice.var_swap_strike); the var-swap
    vol is sqrt(w_varswap / t).
    """
    k = np.linspace(-_VS_HALF_WIDTH, _VS_HALF_WIDTH, _VS_POINTS)
    w = np.maximum(slice_.implied_w(k), 1e-12)
    call = black_call(k, w)  # normalized OTM call price B(k, w)
    # OTM integrand: calls (k >= 0) priced directly, puts (k < 0) by parity.
    integrand = call * np.exp(-k)
    put_side = k < 0.0
    integrand[put_side] += 1.0 - np.exp(-k[put_side])  # (e^k - 1) e^{-k}
    return _finite(2.0 * float(np.trapezoid(integrand, k)))


def weighted_rms_vol(
    slice_: SmileModel,
    k: np.ndarray,
    w: np.ndarray,
    t: float,
    weights: np.ndarray | None = None,
) -> float:
    """Weighted RMS implied-vol error of a slice vs total-variance quotes.

    sqrt(sum_i u_i (sigma_model - sigma_quote)^2 / sum_i u_i) in decimal vol,
    with u_i the per-quote weights (None = equal). sigma = sqrt(w / t).
    """
    k = np.asarray(k, dtype=float)
    if k.size == 0:
        return 0.0
    model_vol = np.sqrt(np.maximum(slice_.implied_w(k), 1e-12) / t)
    quote_vol = np.sqrt(np.maximum(np.asarray(w, dtype=float), 1e-12) / t)
    sq = (model_vol - quote_vol) ** 2
    if weights is None:
        return float(np.sqrt(np.mean(sq)))
    weights = np.asarray(weights, dtype=float)
    return float(np.sqrt(np.sum(weights * sq) / np.sum(weights)))


def numeric_density(
    slice_: SmileModel, half_floor: float = 0.0, return_raw: bool = False
) -> (
    tuple[np.ndarray, np.ndarray, np.ndarray]
    | tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
):
    """Risk-neutral log-return density and CDF of any slice from w(k) alone.

    Breeden-Litzenberger via the Durrleman/Gatheral functional: with total
    variance w(k), k = log(K/F), the density of the log-return X = log(S_T/F)
    (forward measure) is

        p(k) = g(k) / sqrt(2 pi w(k)) * exp(-d_-(k)^2 / 2),
        d_-(k) = -k / sqrt(w) - sqrt(w) / 2,
        g(k) = (1 - k w'/(2w))^2 - (w'/2)^2 (1/w + 1/4) + w''/2,

    matching LQDSlice's exact density on an LQD slice and giving the SVI /
    Multi-Core Sigmoid (MCS) overlays their own density. w', w'' are central differences;
    a non-arbitrage-free overlay can make g (hence p) dip below zero, so the pdf
    is floored at 0 and renormalized. Returns ``(k, pdf, cdf)`` on a shared grid.

    ``half_floor`` widens the (symmetric) grid so it reaches at least ±half_floor —
    used by the stacked-densities view to draw the left tail out to a fixed
    k_min (the density there is ~0 but the curve should reach the display range).

    ``return_raw`` (V3.3 item 11 — sub-zero evidence) additionally returns the
    SIGNED un-clipped pdf: ``(k, pdf, cdf, raw)``, raw scaled by the SAME
    normalization as the clipped pdf (raw == pdf wherever g >= 0, raw < 0
    exactly where g < 0). The default path stays byte-identical."""
    sd = float(np.sqrt(max(float(slice_.implied_w(0.0)), 1e-8)))
    half = max(_DENSITY_SD * sd, _DENSITY_MIN_HALF, half_floor)
    k = np.linspace(-half, half, _DENSITY_POINTS)
    # The model's total variance can be non-finite at the extreme wings (the LQD
    # endpoint scales can overflow far past the data); edge-fill those so the
    # density is well-defined out to a wide half (the deep tail is ~0 anyway).
    w_raw = np.asarray(slice_.implied_w(k), dtype=float)
    bad = ~np.isfinite(w_raw)
    if bad.any():
        good = np.flatnonzero(~bad)
        w_raw[bad] = (
            np.interp(np.flatnonzero(bad), good, w_raw[good]) if good.size else 1e-12
        )
    w = np.maximum(w_raw, 1e-12)
    wk = np.gradient(w, k)
    wkk = np.gradient(wk, k)
    g = (1.0 - k * wk / (2.0 * w)) ** 2 - 0.25 * wk**2 * (1.0 / w + 0.25) + 0.5 * wkk
    sqrt_w = np.sqrt(w)
    d_minus = -k / sqrt_w - 0.5 * sqrt_w
    # Signed pdf first, clip second: max(g,0)/s*e == max(g/s*e, 0) bit-for-bit
    # (identical FP ops in order for g >= 0) — the clipped pdf is byte-identical.
    raw = g / np.sqrt(2.0 * np.pi * w) * np.exp(-0.5 * d_minus**2)
    pdf = np.maximum(raw, 0.0)
    area = float(np.trapezoid(pdf, k))
    if area > 0.0:
        pdf = pdf / area
        raw = raw / area  # same divisor: raw == pdf wherever g >= 0
    cdf = np.concatenate([[0.0], np.cumsum(0.5 * (pdf[1:] + pdf[:-1]) * np.diff(k))])
    if return_raw:
        return k, pdf, np.clip(cdf, 0.0, 1.0), raw
    return k, pdf, np.clip(cdf, 0.0, 1.0)


def numeric_lee_slopes(slice_: SmileModel) -> tuple[float, float]:
    """Left/right total-variance wing slopes dw/d|k| at +-_VS_HALF_WIDTH."""
    edge = _VS_HALF_WIDTH
    dk = 1e-2
    w_rr = float(slice_.implied_w(edge))
    w_r = float(slice_.implied_w(edge - dk))
    w_ll = float(slice_.implied_w(-edge))
    w_l = float(slice_.implied_w(-edge + dk))
    right = (w_rr - w_r) / dk
    left = (w_ll - w_l) / dk  # dw/d(-k): positive when the left wing rises
    return _finite(left), _finite(right)


# ------------------------------------------------------------ belly certificate
#: Certificate grid density over the traded range (dense: the Vogt-type belly
#: dip can be narrow) and the numerical g tolerance — an allowance for the
#: finite-difference stencil on a smooth model curve, orders below any real
#: violation (the Axel Vogt dip is -0.033; the committee boundary example
#: reads -0.0485).
_CERT_POINTS = 801
CERT_G_TOL = 1e-4


@dataclass(frozen=True)
class BellyCertificate:
    """Butterfly certificate of one slice over its TRADED range (committee
    revision R2: the acceptance rule's core object).

    The belly is exactly the region the cheap screens do not reach (the
    floor and the strict Lee cap fence the wings) and the publish-time wing
    projection must never touch (the core stays pinned). ``certified`` means
    Durrleman g >= -CERT_G_TOL at every grid point — computed from the
    MODEL's own curve, never by differencing prices (the arb-metric audit
    rule). An uncertified slice cannot become a mark: the export publish
    gate turns this verdict into a hard blocker."""

    certified: bool
    min_g: float
    argmin_k: float
    #: Fraction of grid points strictly below -tol (dip width, not just depth).
    neg_share: float
    n_grid: int


def belly_certificate(
    slice_: SmileModel, k_lo: float, k_hi: float, g_tol: float = CERT_G_TOL
) -> BellyCertificate | None:
    """Dense-grid butterfly certificate over [k_lo, k_hi] (the quoted range).

    None when the range is degenerate (a single-strike node has no belly to
    certify). Cost is a few dozen microseconds — certification is not
    operationally expensive (the committee's affordability challenge)."""
    k_lo, k_hi = float(k_lo), float(k_hi)
    if not np.isfinite(k_lo) or not np.isfinite(k_hi) or k_hi <= k_lo:
        return None
    k = np.linspace(k_lo, k_hi, _CERT_POINTS)
    g = durrleman_g(slice_, k)
    finite = np.isfinite(g)
    if not finite.any():
        return BellyCertificate(
            certified=False, min_g=float("-inf"), argmin_k=k_lo,
            neg_share=1.0, n_grid=int(k.size),
        )
    g_f, k_f = g[finite], k[finite]
    i = int(np.argmin(g_f))
    min_g = float(g_f[i])
    return BellyCertificate(
        certified=bool(min_g >= -g_tol) and bool(finite.all()),
        min_g=min_g,
        argmin_k=float(k_f[i]),
        neg_share=float(np.mean(g_f < -g_tol)),
        n_grid=int(k.size),
    )


# --------------------------------------------------------------- extrapolated arb
#: How far past the traded edge the extrapolated-region scan may reach (in k).
_EXTRAP_REACH = 4.0
_EXTRAP_POINTS = 241
#: Default "not worthless" floor: OTM option value >= 1 bp of the forward.
EXTRAP_TV_FLOOR = 1e-4


@dataclass(frozen=True)
class ExtrapArb:
    """Extrapolated-region arbitrage measurement of one slice (Notes 09/10,
    Phase 1 of the softer-enforcement design: MEASURED, never enforced).

    The envelope is the strike region beyond the traded range where the
    model's own OTM option value is still >= ``tv_floor`` ("extrapolated but
    not worthless"). ``min_g`` is the worst Durrleman g over both wings of the
    envelope (>= 0 = butterfly-clean); ``cal_bp`` is the worst calendar
    crossing vs the previous expiry over the same envelope, expressed in vol
    bp at this slice's maturity (0 when clean or no previous slice)."""

    k_lo: float  # left envelope outer edge (== traded edge when empty)
    k_hi: float  # right envelope outer edge
    min_g: float | None  # None when the envelope is empty on both sides
    cal_bp: float | None  # None when no previous slice was supplied


def durrleman_g(slice_: SmileModel, k: np.ndarray) -> np.ndarray:
    """Durrleman g(k) of a slice by central differences of its own w(k).

    The derivatives are of the MODEL curve (smooth), not of reconstructed
    prices — the analytic-measurement lesson of the arb-metric audit. Non-
    finite w (overflowing wings) yields non-finite g; callers mask it."""
    w = np.maximum(np.asarray(slice_.implied_w(k), dtype=float), 1e-12)
    wk = np.gradient(w, k)
    wkk = np.gradient(wk, k)
    return (1.0 - k * wk / (2.0 * w)) ** 2 - 0.25 * wk**2 * (1.0 / w + 0.25) + 0.5 * wkk


def _otm_value(slice_: SmileModel, k: np.ndarray) -> np.ndarray:
    """Normalized OTM option value: call for k >= 0, put (by parity) for k < 0."""
    w = np.maximum(np.asarray(slice_.implied_w(k), dtype=float), 1e-12)
    call = black_call(k, w)
    put_side = k < 0.0
    value = call.copy()
    value[put_side] = call[put_side] - (1.0 - np.exp(k[put_side]))
    return value


def _envelope(slice_: SmileModel, edge: float, sign: float, tv_floor: float) -> np.ndarray:
    """Contiguous grid past ``edge`` (direction ``sign``) while the OTM value
    stays >= tv_floor and w stays finite. Empty when worthless at the edge."""
    k = edge + sign * np.linspace(0.0, _EXTRAP_REACH, _EXTRAP_POINTS)[1:]
    value = _otm_value(slice_, k)
    alive = np.isfinite(value) & (value >= tv_floor)
    if not alive[0]:
        return k[:0]
    cut = np.argmin(alive) if not alive.all() else alive.size
    return k[:cut]


def extrapolated_arb(
    slice_: SmileModel,
    k_min_traded: float,
    k_max_traded: float,
    t: float,
    prev_slice: SmileModel | None = None,
    tv_floor: float = EXTRAP_TV_FLOOR,
) -> ExtrapArb:
    """Measure butterfly and calendar arbitrage in the extrapolated region.

    Butterfly (one-curve): min Durrleman g over the envelope of THIS slice.
    Calendar (two-curve): worst sigma_prev - sigma_this crossing (vol bp at
    maturity ``t``) over the same envelope vs ``prev_slice``. Advisory only —
    Phase 1 measures, enforcement (if ever) is a separate, tapered design."""
    left = _envelope(slice_, float(k_min_traded), -1.0, tv_floor)
    right = _envelope(slice_, float(k_max_traded), +1.0, tv_floor)
    k_env = np.concatenate([left[::-1], right])

    min_g: float | None = None
    for wing in (left, right):
        if wing.size < 3:  # need a stencil for the second derivative
            continue
        g = durrleman_g(slice_, wing)
        g = g[np.isfinite(g)]
        if g.size:
            worst = float(g.min())
            min_g = worst if min_g is None else min(min_g, worst)

    cal_bp: float | None = None
    if prev_slice is not None:
        cal_bp = 0.0
        if k_env.size:
            w_this = np.maximum(np.asarray(slice_.implied_w(k_env), float), 1e-12)
            w_prev = np.maximum(np.asarray(prev_slice.implied_w(k_env), float), 1e-12)
            sig_gap = (np.sqrt(w_prev / t) - np.sqrt(w_this / t)) * 1e4
            sig_gap = sig_gap[np.isfinite(sig_gap)]
            if sig_gap.size:
                cal_bp = max(0.0, float(sig_gap.max()))

    return ExtrapArb(
        k_lo=float(left[-1]) if left.size else float(k_min_traded),
        k_hi=float(right[-1]) if right.size else float(k_max_traded),
        min_g=min_g,
        cal_bp=cal_bp,
    )

# --------------------------------------------------- analytic butterfly signal
#: Traded-range scan density (the historical backtest.dispatch grid) + the
#: genuine-arb thresholds for the ANALYTIC signal (no FD noise, so tight); the
#: density bound is float noise (the LQD density is positive by construction).
_AN_BFLY_POINTS = 201
BUTTERFLY_G_TOL = 1e-6
BUTTERFLY_DENSITY_TOL = 1e-9


def butterfly_tolerance(kind: str) -> float:
    """Certification tolerance matching an ``analytic_butterfly`` kind."""
    return BUTTERFLY_DENSITY_TOL if kind == "density" else BUTTERFLY_G_TOL


def analytic_butterfly(
    family: str, slice_: SmileModel, k_lo: float, k_hi: float
) -> tuple[str, float, float]:
    """Static (butterfly) arb from the model's ANALYTIC form — no FD noise.

    ONE protocol, four families (lifted from backtest.dispatch, V3.2 item 12
    — the compare endpoint and the offline sweep read the SAME signal; FD
    reconstruction misreports at range edges, FINDINGS R2). Returns ``(kind,
    min, neg_frac)`` over [k_lo, k_hi]: ``"density"`` — the LQD risk-neutral
    density minimum (f = u(1-u)e^{-g} >= 0 by construction, butterfly arb is
    structurally impossible); ``"g"`` — SVI (closed-form w', w'') / Multi-Core
    SIV and eSSVI (their own ``gatheral_g``) exact Durrleman g, g < 0 => arb;
    ``"recon"`` — no analytic form, the caller keeps its own reconstruction.
    """
    grid = np.linspace(float(k_lo), float(k_hi), _AN_BFLY_POINTS)
    if family == "lqd" and hasattr(slice_, "density"):  # structural positivity
        vals, kind = np.asarray(slice_.density()[1], float), "density"
    elif family in ("sigmoid", "essvi") and hasattr(slice_, "gatheral_g"):  # analytic g
        vals, kind = np.asarray(slice_.gatheral_g(grid), float), "g"
    elif family == "svi" and hasattr(slice_, "sigma"):  # RawSVI closed form
        km = grid - slice_.m
        s = np.sqrt(km * km + slice_.sigma**2)
        w = np.maximum(slice_.a + slice_.b * (slice_.rho * km + s), 1e-12)
        wp = slice_.b * (slice_.rho + km / s)
        wpp = slice_.b * slice_.sigma**2 / s**3
        g = (1.0 - grid * wp / (2.0 * w)) ** 2 - 0.25 * wp**2 * (1.0 / w + 0.25) + 0.5 * wpp
        vals, kind = g, "g"
    else:
        return "recon", 0.0, 0.0
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return kind, 0.0, 0.0
    return kind, float(vals.min()), float(np.mean(vals < 0.0))
