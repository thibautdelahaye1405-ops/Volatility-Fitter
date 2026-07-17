"""Posterior smile + credible band for the graph node drill-in (R3 item 12).

Two band constructions share this module:

  - ``functional`` (default): the delta-method pushforward of the FULL
    3-handle posterior covariance through the slice map
    (volfit.models.lqd.band) — skew/curvature uncertainty widens the wings,
    the ATM level widens the money, and the same six perturbed slices price
    the var-swap / tail-mass sds the payload now carries.
  - ``level`` (escape hatch, ``GraphExtrapolateRequest.functionalBand=false``):
    the legacy ATM-level band — retarget sigma0 +/- 1.96 sd with skew/curv
    frozen — byte-identical to the pre-item-12 payload.

Band-only by construction: the posterior curve itself is built identically on
both paths, and nothing here reads or moves a posterior mean.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.api.schemas import SmilePoint
from volfit.api.service import fill_nonfinite
from volfit.models.lqd.band import FunctionalBand, functional_band
from volfit.models.lqd.quadrature import build_slice

Z_95 = 1.96


def curve_points(slice_, tau: float, grid: np.ndarray) -> list[SmilePoint]:
    """IV curve of a slice on the display grid (wings edge-extended)."""
    w = np.maximum(slice_.implied_w(grid), 0.0)
    vols = fill_nonfinite(np.sqrt(np.maximum(w, 0.0) / tau))
    return [SmilePoint(k=float(k), vol=float(v)) for k, v in zip(grid, vols)]


def retarget_slice(chart, handles, tau: float):
    """The exact arb-free LQD slice at target ATM ``handles`` (w0 = sigma0^2 tau),
    or None on a Newton failure at extreme handles (a very wide band edge)."""
    target = np.array([handles[0] * handles[0] * tau, handles[1], handles[2]])
    try:
        return build_slice(chart.retarget(target))
    except RuntimeError:
        return None


def _shift_band(native_post, lqd_post, lqd_band) -> list[SmilePoint]:
    """Carry the LQD level-uncertainty band onto the native posterior curve: at each
    k, native_post + (lqd_band - lqd_post). Grids are aligned (same display grid)."""
    if not native_post or len(native_post) != len(lqd_post) or len(lqd_band) != len(lqd_post):
        return []
    return [
        SmilePoint(k=p.k, vol=float(p.vol + (b.vol - q.vol)))
        for p, q, b in zip(native_post, lqd_post, lqd_band)
    ]


@dataclass(frozen=True)
class PosteriorBand:
    """The reconstructed posterior smile plus its credible band + functionals."""

    post_slice: object | None  # the displayed-model slice (native or LQD)
    post: list[SmilePoint]
    band_lo: list[SmilePoint]
    band_hi: list[SmilePoint]
    functional: FunctionalBand | None  # None on the legacy level path
    kind: str  # "functional" | "level" | "" (no curve)


_EMPTY = PosteriorBand(None, [], [], [], None, "")


def build_band(
    native_slice_of,
    chart,
    post_h: np.ndarray,
    sd3: np.ndarray,
    tau: float,
    grid: np.ndarray,
    functional: bool,
) -> PosteriorBand:
    """Reconstruct the posterior smile and its 95% credible band.

    ``native_slice_of(lqd_slice)`` refits the displayed family to the LQD
    target (None keeps LQD); ``sd3`` is the node's per-handle marginal
    posterior sd (ATM already idio-floored by the solve).
    """
    if chart is None:
        return _EMPTY
    lqd_post = retarget_slice(chart, post_h, tau)
    if lqd_post is None:
        return _EMPTY
    native = native_slice_of(lqd_post)
    post_slice = native if native is not None else lqd_post
    post_curve = curve_points(post_slice, tau, grid)

    if functional:
        fb = functional_band(
            chart, post_h, np.diag(np.asarray(sd3, dtype=float) ** 2), tau, grid,
            reference=lqd_post,
        )
        if fb is not None:
            half = Z_95 * fb.iv_sd
            lo = [
                SmilePoint(k=p.k, vol=float(max(p.vol - h, 0.0)))
                for p, h in zip(post_curve, half)
            ]
            hi = [
                SmilePoint(k=p.k, vol=float(p.vol + h))
                for p, h in zip(post_curve, half)
            ]
            return PosteriorBand(post_slice, post_curve, lo, hi, fb, "functional")
        # unreachable in practice (the reference slice exists) — fall through
        # to the level band rather than dropping the band entirely.

    sd = float(sd3[0])
    half = Z_95 * sd
    lqd_post_curve = curve_points(lqd_post, tau, grid)
    # The lowered leg must stay a REACHABLE ATM target: a wide band can
    # push sigma0 - 1.96 sd negative, and handles[0]^2 tau would silently
    # square it into a wrong HIGH target — floor it near zero instead.
    lo_atm = max(post_h[0] - half, 0.05 * max(post_h[0], 1e-6), 1e-4)
    lqd_lo = retarget_slice(chart, [lo_atm, post_h[1], post_h[2]], tau)
    lqd_hi = retarget_slice(chart, [post_h[0] + half, post_h[1], post_h[2]], tau)
    lo_c = curve_points(lqd_lo, tau, grid) if lqd_lo is not None else []
    hi_c = curve_points(lqd_hi, tau, grid) if lqd_hi is not None else []
    # A leg's Newton can still fail at an extreme band edge (seen on
    # CI/Linux only: the platform's fit trajectory landed a wider sd
    # and the payload silently DROPPED the band). The band is a
    # LEVEL-uncertainty object, so the honest fallback is the same
    # first-order thing: a parallel vol shift of the posterior.
    if not lo_c:
        lo_c = [SmilePoint(k=p.k, vol=max(p.vol - half, 0.0)) for p in lqd_post_curve]
    if not hi_c:
        hi_c = [SmilePoint(k=p.k, vol=p.vol + half) for p in lqd_post_curve]
    if native is not None:
        band_lo = _shift_band(post_curve, lqd_post_curve, lo_c)
        band_hi = _shift_band(post_curve, lqd_post_curve, hi_c)
    else:
        band_lo, band_hi = lo_c, hi_c
    return PosteriorBand(post_slice, post_curve, band_lo, band_hi, None, "level")
