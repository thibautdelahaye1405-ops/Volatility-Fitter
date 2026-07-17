"""Functional posterior for a parametric slice (roadmap R3 item 12).

Delta method on the ATM-orthogonal slice map (Note 01 secs. 6.2-6.3, Note 14
sec. "Reconstruction and comparison"): given the 3x3 posterior covariance
Sigma of the trader handles h = (sigma0, skew, curvature) and the chart at a
node's reference slice, every displayed functional F of the slice inherits

    Var[F] = (dF/dh)^T  Sigma  (dF/dh)          (first order)

with dF/dh computed by central differences along the chart's exact retarget
map — the SAME map production uses to reconstruct the smile, so the band is
the pushforward of the handle posterior through the reconstruction itself.
Six perturbed slices (2 per handle) price every functional at once:

  - IV(k) on the display grid  -> per-strike smile credible band,
  - var-swap vol sqrt(-2 E[X]/tau)               (Note 08),
  - risk-neutral density f_X on a common x-grid   (Note 01 eq. density),
  - tail mass P(X <= k_lo), P(X >= k_hi)  (exact: CDF(k) = u(z_k)).

The handle posterior sources are the graph field's marginal sds (diagonal
Sigma, volfit/graph) and the observation filter's full 3x3 state covariance
(Note 15). Band-only by construction: nothing here ever moves a posterior
mean, and callers keep their legacy band as an escape hatch.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import expit

from volfit.models.lqd.ortho import ATMCoordinates
from volfit.models.lqd.quadrature import LQDSlice, build_slice

#: Central-difference steps per handle: 1e-2 x the natural move scales the
#: graph hyper-parameters use (0.03 vol, 0.05 skew, 0.5 curvature) — large
#: enough to dominate the retarget tolerance (1e-12), small enough that the
#: O(step^2) truncation is invisible next to posterior sds.
FD_STEPS = (3.0e-4, 5.0e-4, 5.0e-3)

#: Reachability floor for a perturbed ATM-vol target (the band-leg lesson of
#: graph_reconstruct: a non-positive sigma0 target squares into a wrong HIGH
#: w0 target instead of failing).
_ATM_FLOOR = 1.0e-4


@dataclass(frozen=True)
class FunctionalBand:
    """First-order posterior sds of the displayed slice functionals.

    ``iv_sd`` rides the caller's strike grid; the density band rides its own
    ``density_x`` grid (the same strike grid, kept explicit so consumers never
    have to guess). ``exact_legs`` counts the FD legs whose exact retarget
    converged (out of 6) — fewer means the missing directions fell back to the
    parallel-shift derivative (ATM) or were dropped (skew/curvature), so the
    band UNDER-states in those directions rather than inventing curvature.
    """

    iv_sd: np.ndarray  # (n_k,) per-strike IV standard deviation
    var_swap_vol: float
    var_swap_vol_sd: float
    tail_mass_left: float  # P(X <= k_lo) at the reference slice
    tail_mass_right: float  # P(X >= k_hi)
    tail_mass_left_sd: float
    tail_mass_right_sd: float
    density_x: np.ndarray
    density: np.ndarray
    density_sd: np.ndarray
    exact_legs: int


def psd_covariance(cov: np.ndarray) -> np.ndarray:
    """Symmetrize and clip a 3x3 covariance onto the PSD cone.

    The filter's stored covariance is PSD up to roundoff; the graph field
    supplies a diagonal. Clipping (eigenvalue floor 0) guarantees the
    quadratic forms below can never report a negative variance.
    """
    sym = 0.5 * (np.asarray(cov, dtype=float) + np.asarray(cov, dtype=float).T)
    vals, vecs = np.linalg.eigh(sym)
    return (vecs * np.maximum(vals, 0.0)) @ vecs.T


def _slice_at(chart: ATMCoordinates, handles: np.ndarray, tau: float) -> LQDSlice | None:
    """Exact retarget to (sigma0, skew, curvature), or None on Newton failure."""
    s0 = max(float(handles[0]), _ATM_FLOOR)
    target = np.array([s0 * s0 * tau, float(handles[1]), float(handles[2])])
    try:
        return build_slice(chart.retarget(target))
    except (RuntimeError, ValueError):
        return None


def _iv(slice_: LQDSlice, k: np.ndarray, tau: float) -> np.ndarray:
    """IV on the grid, non-finite wings edge-extended (the display convention:
    the drawn curve edge-extends failed deep-wing inversions, so the band must
    difference the SAME extension or its width collapses to zero at the edge)."""
    w = np.asarray(slice_.implied_w(k), dtype=float)
    iv = np.sqrt(np.maximum(w, 0.0) / tau)
    bad = ~np.isfinite(iv)
    if bad.any() and not bad.all():
        idx = np.arange(iv.size)
        iv[bad] = np.interp(idx[bad], idx[~bad], iv[~bad])  # nearest-edge extend
    return iv


def _tails(slice_: LQDSlice, k_lo: float, k_hi: float) -> tuple[float, float]:
    """Exact tail masses: CDF(k) = u(z_k) since X = Q(z) with u = logistic(z)."""
    z = slice_.strike_to_z(np.array([k_lo, k_hi]))
    return float(expit(z[0])), float(expit(-z[1]))


def _density_on(slice_: LQDSlice, x: np.ndarray) -> np.ndarray:
    """Risk-neutral density interpolated onto a shared x-grid (Q is monotone)."""
    q, pdf = slice_.density()
    return np.interp(x, q, pdf)


@dataclass(frozen=True)
class _Legs:
    """One handle direction's functional values at h +/- step."""

    iv: tuple[np.ndarray, np.ndarray] | None
    vs: tuple[float, float] | None
    tails: tuple[tuple[float, float], tuple[float, float]] | None
    pdf: tuple[np.ndarray, np.ndarray] | None
    exact: int  # how many of the two retargets converged


def _direction_legs(
    chart: ATMCoordinates,
    handles: np.ndarray,
    j: int,
    tau: float,
    k: np.ndarray,
    ref: _RefValues,
) -> _Legs:
    """Central (or one-sided, on a failed leg) differences for handle ``j``.

    Both legs failing is the honest degenerate case: the ATM direction falls
    back to the exact-at-ATM parallel shift dIV/dsigma0 = 1 (the graph band's
    CI-hardened fallback), skew/curvature contribute nothing (band-only, so
    under-stating beats fabricating).
    """
    step = FD_STEPS[j]
    up_h, dn_h = handles.copy(), handles.copy()
    up_h[j] += step
    dn_h[j] -= step
    up = _slice_at(chart, up_h, tau)
    dn = _slice_at(chart, dn_h, tau)
    exact = int(up is not None) + int(dn is not None)
    if up is None and dn is None:
        if j == 0:  # parallel-shift fallback on the level direction only
            ones = np.ones_like(k)
            return _Legs(
                iv=(ref.iv + step * ones, ref.iv - step * ones),
                vs=(ref.vs + step, ref.vs - step),
                tails=None,
                pdf=None,
                exact=0,
            )
        return _Legs(iv=None, vs=None, tails=None, pdf=None, exact=0)

    # A single failed leg degrades to a one-sided difference through the
    # reference values (still first-order exact; the caller divides by the
    # single-step span when exact == 1).
    up_v = _FuncValues.of(up, k, tau, ref) if up is not None else ref.as_values()
    dn_v = _FuncValues.of(dn, k, tau, ref) if dn is not None else ref.as_values()
    return _Legs(
        iv=(up_v.iv, dn_v.iv),
        vs=(up_v.vs, dn_v.vs),
        tails=(up_v.tails, dn_v.tails),
        pdf=(up_v.pdf, dn_v.pdf),
        exact=exact,
    )


@dataclass(frozen=True)
class _RefValues:
    """Reference-slice functionals shared by every direction's fallbacks."""

    iv: np.ndarray
    vs: float
    tails: tuple[float, float]
    pdf: np.ndarray
    k_lo: float
    k_hi: float

    def as_values(self) -> "_FuncValues":
        return _FuncValues(iv=self.iv, vs=self.vs, tails=self.tails, pdf=self.pdf)


@dataclass(frozen=True)
class _FuncValues:
    iv: np.ndarray
    vs: float
    tails: tuple[float, float]
    pdf: np.ndarray

    @staticmethod
    def of(slice_: LQDSlice, k: np.ndarray, tau: float, ref: _RefValues) -> "_FuncValues":
        return _FuncValues(
            iv=_iv(slice_, k, tau),
            vs=float(np.sqrt(max(slice_.var_swap_strike(), 0.0) / tau)),
            tails=_tails(slice_, ref.k_lo, ref.k_hi),
            pdf=_density_on(slice_, k),
        )


def functional_band(
    chart: ATMCoordinates,
    handles: np.ndarray,
    cov: np.ndarray,
    tau: float,
    k_grid: np.ndarray,
    reference: LQDSlice | None = None,
) -> FunctionalBand | None:
    """Push the 3x3 handle covariance through the slice map (delta method).

    ``handles`` is the posterior mean (sigma0, skew, curvature); ``reference``
    is the already-retargeted posterior slice when the caller has one (saves a
    Newton solve). Returns None when even the reference slice is unreachable —
    the caller keeps whatever fallback band it already had.
    """
    if tau <= 0.0 or k_grid.size == 0:
        return None
    handles = np.asarray(handles, dtype=float)
    sigma = psd_covariance(cov)
    ref_slice = reference if reference is not None else _slice_at(chart, handles, tau)
    if ref_slice is None:
        return None

    k = np.asarray(k_grid, dtype=float)
    k_lo, k_hi = float(k[0]), float(k[-1])
    tails_ref = _tails(ref_slice, k_lo, k_hi)
    ref = _RefValues(
        iv=_iv(ref_slice, k, tau),
        vs=float(np.sqrt(max(ref_slice.var_swap_strike(), 0.0) / tau)),
        tails=tails_ref,
        pdf=_density_on(ref_slice, k),
        k_lo=k_lo,
        k_hi=k_hi,
    )

    # Jacobian columns dF/dh_j from the direction legs. A one-sided pair spans
    # a single step; a full central pair spans two.
    g_iv = np.zeros((k.size, 3))
    g_vs = np.zeros(3)
    g_tl = np.zeros(3)
    g_tr = np.zeros(3)
    g_pdf = np.zeros((k.size, 3))
    exact_legs = 0
    for j in range(3):
        legs = _direction_legs(chart, handles, j, tau, k, ref)
        exact_legs += legs.exact
        span = FD_STEPS[j] * (2.0 if legs.exact != 1 else 1.0)
        if legs.iv is not None:
            diff = legs.iv[0] - legs.iv[1]
            g_iv[:, j] = np.where(np.isfinite(diff), diff, 0.0) / span
        if legs.vs is not None:
            g_vs[j] = (legs.vs[0] - legs.vs[1]) / span
        if legs.tails is not None:
            g_tl[j] = (legs.tails[0][0] - legs.tails[1][0]) / span
            g_tr[j] = (legs.tails[0][1] - legs.tails[1][1]) / span
        if legs.pdf is not None:
            g_pdf[:, j] = (legs.pdf[0] - legs.pdf[1]) / span

    def _sd_curve(g: np.ndarray) -> np.ndarray:
        return np.sqrt(np.maximum(np.einsum("kj,jl,kl->k", g, sigma, g), 0.0))

    def _sd(g: np.ndarray) -> float:
        return float(np.sqrt(max(g @ sigma @ g, 0.0)))

    return FunctionalBand(
        iv_sd=_sd_curve(g_iv),
        var_swap_vol=ref.vs,
        var_swap_vol_sd=_sd(g_vs),
        tail_mass_left=tails_ref[0],
        tail_mass_right=tails_ref[1],
        tail_mass_left_sd=_sd(g_tl),
        tail_mass_right_sd=_sd(g_tr),
        density_x=k,
        density=ref.pdf,
        density_sd=_sd_curve(g_pdf),
        exact_legs=exact_legs,
    )
