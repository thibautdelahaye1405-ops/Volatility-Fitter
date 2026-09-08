"""Total-variance surfaces over slice fits, and the Dupire twin on a lattice.

The LV Dupire-twin compare arc (ROADMAP 2026-09-08) confronts the two
directions of the Dupire equation: the piecewise-affine local variance the
LV workspace FITS to quotes through the forward PDE (Note 04), and the local
variance READ OFF the calibrated parametric surface the classical way —
Gatheral's formula (The Volatility Surface, eq. 1.10; Note 04 appendix D),
in log-moneyness k and total implied variance w(k, t):

    sigma_loc^2 = w_t / g(k, w),
    g = 1 - (k/w) w_k + 1/4 (-1/4 - 1/w + k^2/w^2) w_k^2 + 1/2 w_kk.

The per-expiry slice fits give w(k, t_i) on the listed expiries only; this
module builds the continuous-in-t surface between them, then differentiates
it on the vertices of the affine lattice so the twin is the SAME kind of
object as the fitted sheet (nodal local variances, affine in between).

Two interpolants in t (the arc's "smooth / buckets" chips):

- ``w_surface_buckets`` — linear in t between slices, w = 0 at t = 0, flat
  forward variance beyond the last expiry. Piecewise-linear w in t is the
  market convention of constant forward variance per listed-expiry bucket;
  its Dupire local variance is a staircase in t. MOVED here from
  ``volfit.api.localvol._w_surface`` byte-identically (that module now
  imports it) — it still feeds ``GET /localvol/{ticker}`` and the affine
  calibration's Stage-2b cold seed.
- ``w_surface_pchip`` — monotone C1 in t (Fritsch–Carlson PCHIP through
  w = 0 at t = 0 and every slice value, per strike), so w_t is continuous
  and stays >= 0 wherever the slice values are calendar-ordered at that k;
  the same flat-forward-variance extension beyond the last expiry.

``extract_twin`` differentiates a surface on the affine vertices
``(t_nodes, x_nodes)``: central FD in k (step ``dk``), a stencil in t chosen
per interpolant (backward first-order inside the bucket for the staircase —
exact for piecewise-linear w; central for the smooth surface, one-sided
second-order on the last row), the x = 0 vertex and every vertex outside
``[k_lo, k_hi]`` NOT differentiated but held flat from the nearest
differentiated vertex (the ``LocalVolGrid`` convention), and the result
clipped into the affine variance box ``[var_lo, var_hi]``. Every repair is
COUNTED per row — butterfly cells (g <= 0: the implied surface itself
carries strike arbitrage there), calendar cells (w_t <= 0), floored and
capped cells — and the unrepaired values are returned beside the sheet: a
twin that needs the cap is a finding, never a silent repair.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
from scipy.interpolate import PchipInterpolator

from volfit.models.localvol.dupire import _fill_nearest, dupire_local_variance

#: ``w_surface(k_array, t_scalar) -> w_array`` — the shape every builder returns
#: and ``extract_twin`` consumes (the same protocol as ``dupire.extract_grid``).
WSurface = Callable[[np.ndarray, float], np.ndarray]

#: The arc's t-interpolation chips.
T_INTERPS = ("smooth", "buckets")

#: Default strike step of the k finite differences (the GET /localvol value).
DK_DEFAULT = 2e-3
#: The t-row stencil step is this fraction of the shortest expiry gap, so a
#: backward difference never leaves its bucket.
DT_GAP_FRACTION = 0.2
#: Floor on the t stencil (and on the row time of the t = 0 vertex).
DT_MIN = 1e-4


# --------------------------------------------------------------------------
# Surface builders
# --------------------------------------------------------------------------


def w_surface_buckets(ts: np.ndarray, slices: Sequence) -> WSurface:
    """Total-variance surface w(k, t): linear in t between slices, 0 at t=0.

    Within [0, t_last] this is the standard variance-time interpolation
    (calendar-safe when the slice fits are); beyond t_last the last bucket's
    forward variance is extended flat.
    """

    def w(k: np.ndarray, t: float) -> np.ndarray:
        k = np.asarray(k, dtype=float)
        t = float(t)
        w_rows = [s.implied_w(k) for s in slices]  # lazily small: few expiries
        if t <= 0.0:
            return np.zeros_like(k)
        i = int(np.searchsorted(ts, t))
        if i == 0:
            return w_rows[0] * (t / ts[0])
        if i >= ts.size:  # flat forward variance beyond the last expiry
            if ts.size == 1:
                return w_rows[-1] * (t / ts[-1])
            slope = (w_rows[-1] - w_rows[-2]) / (ts[-1] - ts[-2])
            return w_rows[-1] + np.maximum(slope, 0.0) * (t - ts[-1])
        lam = (t - ts[i - 1]) / (ts[i] - ts[i - 1])
        return (1.0 - lam) * w_rows[i - 1] + lam * w_rows[i]

    return w


def w_surface_pchip(ts: np.ndarray, slices: Sequence) -> WSurface:
    """Total-variance surface w(k, t): monotone C1 (PCHIP) in t through w(0)=0.

    Per strike, the knots are t = 0 (w = 0) and every slice expiry; the
    Fritsch–Carlson derivative estimates keep the interpolant monotone
    wherever the knot values are, so calendar-ordered slices give w_t >= 0 at
    every t. Beyond the last expiry the last bucket's forward variance is
    extended flat, exactly as ``w_surface_buckets`` does. The slice rows and
    the interpolator are memoized on the k array (the FD stencil re-asks the
    same k's for every t row), so a full extraction costs one ``implied_w``
    per slice per distinct k array.
    """
    ts = np.asarray(ts, dtype=float)
    knots = np.concatenate([[0.0], ts])
    memo: dict[bytes, tuple[PchipInterpolator, np.ndarray]] = {}

    def prepared(k: np.ndarray) -> tuple[PchipInterpolator, np.ndarray]:
        key = k.tobytes()
        hit = memo.get(key)
        if hit is None:
            rows = np.vstack([np.zeros_like(k)] + [s.implied_w(k) for s in slices])
            hit = (PchipInterpolator(knots, rows, axis=0, extrapolate=False), rows)
            memo[key] = hit
        return hit

    def w(k: np.ndarray, t: float) -> np.ndarray:
        k = np.asarray(k, dtype=float)
        t = float(t)
        if t <= 0.0:
            return np.zeros_like(k)
        interp, rows = prepared(k)
        if t >= ts[-1]:  # flat forward variance beyond the last expiry
            if ts.size == 1:
                return rows[-1] * (t / ts[-1])
            slope = (rows[-1] - rows[-2]) / (ts[-1] - ts[-2])
            return rows[-1] + np.maximum(slope, 0.0) * (t - ts[-1])
        return np.asarray(interp(t), dtype=float)

    return w


def build_w_surface(t_interp: str, ts: np.ndarray, slices: Sequence) -> WSurface:
    """The builder for a t-interpolation chip (``smooth`` | ``buckets``)."""
    if t_interp == "smooth":
        return w_surface_pchip(ts, slices)
    if t_interp == "buckets":
        return w_surface_buckets(ts, slices)
    raise ValueError(f"t_interp must be one of {T_INTERPS}, got {t_interp!r}")


# --------------------------------------------------------------------------
# The twin on a lattice
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DupireCounters:
    """Per-row repair counts of a twin extraction (one entry per t vertex).

    ``butterfly`` — cells where the Dupire denominator g <= 0 (or w <= 0):
    the implied surface carries strike arbitrage there; filled from the
    nearest differentiated strike. ``calendar`` — finite cells with local
    variance <= 0, i.e. w_t <= 0 (the implied surface decreases in t there).
    ``floored`` — cells raised to ``var_lo`` (calendar cells included);
    ``capped`` — cells lowered to ``var_hi``. Guarded (non-differentiated)
    vertices are never counted: they copy an already-repaired neighbour.
    """

    butterfly: np.ndarray
    calendar: np.ndarray
    floored: np.ndarray
    capped: np.ndarray

    @property
    def total_butterfly(self) -> int:
        return int(self.butterfly.sum())

    @property
    def total_calendar(self) -> int:
        return int(self.calendar.sum())

    @property
    def total_floored(self) -> int:
        return int(self.floored.sum())

    @property
    def total_capped(self) -> int:
        return int(self.capped.sum())

    @property
    def clean(self) -> bool:
        """True when no cell needed any repair."""
        return (
            self.total_butterfly == 0 and self.total_calendar == 0
            and self.total_floored == 0 and self.total_capped == 0
        )


@dataclass(frozen=True)
class TwinExtraction:
    """The Dupire twin on the lattice plus what the extraction had to do.

    ``theta`` is the nodal local VARIANCE inside ``[var_lo, var_hi]`` (strictly
    positive, ready for ``AffineVarianceSurface``); ``raw`` keeps the
    unrepaired Gatheral values on the differentiated vertices (nan where the
    denominator failed, negative where w_t < 0) and nan on guarded vertices;
    ``differentiated`` flags the x vertices that were actually differentiated
    (the others are flat copies of the nearest one).
    """

    theta: np.ndarray  # (n_t, n_x)
    raw: np.ndarray  # (n_t, n_x)
    differentiated: np.ndarray  # (n_x,) bool
    counters: DupireCounters
    t_rows: np.ndarray  # (n_t,) the row times actually differentiated at


def _default_dt(ts: np.ndarray) -> float:
    gaps = np.diff(np.concatenate([[0.0], np.asarray(ts, dtype=float)]))
    return max(DT_GAP_FRACTION * float(gaps.min()), DT_MIN)


def _w_t(
    w: WSurface, k: np.ndarray, t: float, dt: float, t_interp: str, edges: np.ndarray
) -> np.ndarray:
    """The t derivative at row time ``t``, per the interpolant's stencil policy.

    ``buckets`` (piecewise-linear w): a first-order backward difference kept
    INSIDE the bucket the row lies in (``edges`` = 0 and the expiries; a row
    exactly at an expiry reads the bucket ending there — the market's forward
    variance of that bucket) — exact for piecewise-linear w, whatever the
    sqrt-T split depth of the lattice. ``smooth`` (C1 w): second-order
    central, except a one-sided second-order backward stencil on the last
    expiry's row, where the flat-forward extension beyond the last expiry
    would otherwise straddle a kink.
    """
    if t_interp == "buckets":
        start = float(edges[int(np.searchsorted(edges, t, side="left")) - 1])
        h = min(dt, 0.5 * (t - start))
        return (w(k, t) - w(k, t - h)) / h
    if t + dt > float(edges[-1]):
        return (3.0 * w(k, t) - 4.0 * w(k, t - dt) + w(k, t - 2.0 * dt)) / (2.0 * dt)
    return (w(k, t + dt) - w(k, t - dt)) / (2.0 * dt)


def extract_twin(
    w_surface: WSurface,
    ts: np.ndarray,
    x_nodes: np.ndarray,
    t_nodes: np.ndarray,
    *,
    t_interp: str = "smooth",
    var_lo: float,
    var_hi: float,
    k_lo: float | None = None,
    k_hi: float | None = None,
    dk: float = DK_DEFAULT,
    dt: float | None = None,
) -> TwinExtraction:
    """Dupire local variance of ``w_surface`` on the vertices ``(t_nodes, x_nodes)``.

    ``ts`` are the slice expiries the surface was built from (they size the
    default t step and mark the last row). Vertices with ``x <= 0`` or with
    ``k = ln x`` outside ``[k_lo, k_hi]`` (either bound optional) are the
    guarded ones: never differentiated, held flat from the nearest
    differentiated vertex. The t = 0 vertex (and any row closer than one
    step) is differentiated at ``t = dt`` — the short-end limit.
    """
    if t_interp not in T_INTERPS:
        raise ValueError(f"t_interp must be one of {T_INTERPS}, got {t_interp!r}")
    if not (0.0 < var_lo < var_hi):
        raise ValueError("need 0 < var_lo < var_hi")
    ts = np.asarray(ts, dtype=float)
    x = np.asarray(x_nodes, dtype=float)
    t = np.asarray(t_nodes, dtype=float)
    step = float(dt) if dt is not None else _default_dt(ts)
    edges = np.concatenate([[0.0], ts])

    with np.errstate(divide="ignore"):
        k_all = np.where(x > 0.0, np.log(np.where(x > 0.0, x, 1.0)), -np.inf)
    diff_mask = x > 0.0
    if k_lo is not None:
        diff_mask &= k_all >= float(k_lo)
    if k_hi is not None:
        diff_mask &= k_all <= float(k_hi)
    if not diff_mask.any():
        raise ValueError("no vertex inside the differentiation guard")
    k = k_all[diff_mask]
    idx = np.flatnonzero(diff_mask)

    n_t, n_x = t.size, x.size
    theta = np.empty((n_t, n_x))
    raw = np.full((n_t, n_x), np.nan)
    butterfly = np.zeros(n_t, dtype=int)
    calendar = np.zeros(n_t, dtype=int)
    floored = np.zeros(n_t, dtype=int)
    capped = np.zeros(n_t, dtype=int)
    t_rows = np.maximum(t, step)  # the t = 0 vertex: the short-end limit at t = dt

    for i, ti in enumerate(t_rows):
        ti = float(ti)
        w0 = np.asarray(w_surface(k, ti), dtype=float)
        wp = np.asarray(w_surface(k + dk, ti), dtype=float)
        wm = np.asarray(w_surface(k - dk, ti), dtype=float)
        wk = (wp - wm) / (2.0 * dk)
        wkk = (wp - 2.0 * w0 + wm) / (dk * dk)
        wt = np.asarray(_w_t(w_surface, k, ti, step, t_interp, edges), dtype=float)

        var = dupire_local_variance(k, w0, wk, wkk, wt)
        raw[i, idx] = var
        bad = ~np.isfinite(var)
        butterfly[i] = int(bad.sum())
        if bad.any():
            var = _fill_nearest(var, k)
        calendar[i] = int(np.sum(var <= 0.0))
        floored[i] = int(np.sum(var < var_lo))
        capped[i] = int(np.sum(var > var_hi))
        row = np.clip(var, var_lo, var_hi)
        # Guarded vertices: flat from the nearest differentiated vertex in k
        # (np.interp clamps at the ends, affine in between is never used
        # because the differentiated set is contiguous in practice — and if
        # it is not, the affine bridge is still a positive value in the box).
        theta[i] = np.interp(k_all, k, row)

    return TwinExtraction(
        theta=theta,
        raw=raw,
        differentiated=diff_mask,
        counters=DupireCounters(
            butterfly=butterfly, calendar=calendar, floored=floored, capped=capped
        ),
        t_rows=t_rows,
    )
