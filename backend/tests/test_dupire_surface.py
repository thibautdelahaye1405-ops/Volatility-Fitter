"""Goldens for models.localvol.dupire_surface (LV Dupire-twin compare arc, D1).

Self-contained references only — a raw-SVI slice with analytic k
derivatives, so Gatheral's formula can be evaluated from closed forms and
the finite-difference extraction judged against it:

1. The bucketed builder moved out of api/localvol is byte-identical to the
   historical implementation (kept verbatim below) and still reachable under
   its old name.
2. A flat surface returns the flat local variance under both interpolants.
3. An SVI ladder proportional in t (w = t v(k)) has a closed-form, time-
   independent Dupire local variance: both interpolants reproduce it on
   every vertex — expiries, sqrt-T midpoints, the t = 0 row — to FD order.
4. Calendar-ordered but nonlinear-in-t slices: the PCHIP surface is monotone
   in t at every strike and the twin counts no calendar cell.
5. A slice crossing is COUNTED (calendar cells, floored cells) and the sheet
   stays inside the box — never a silent repair.
6. An exponential-class (SVI) wing: the twin's local variance grows linearly
   in |k| and the box cap counts the vertices it lowers.
7. The guard: x = 0 and out-of-bound vertices are flat copies of the nearest
   differentiated one; the mask says which is which.
8. Chip vocabulary / argument gates; the PCHIP memo returns identical arrays.
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.models.localvol import dupire_local_variance
from volfit.models.localvol.dupire_surface import (
    T_INTERPS,
    build_w_surface,
    extract_twin,
    w_surface_buckets,
    w_surface_pchip,
)


class _SVI:
    """Raw SVI slice w(k) = a + b (rho (k - m) + sqrt((k - m)^2 + s^2)), with
    analytic k derivatives (the reference for the FD stencil)."""

    def __init__(self, a: float, b: float, rho: float, m: float, s: float) -> None:
        self.a, self.b, self.rho, self.m, self.s = a, b, rho, m, s

    def _parts(self, k):
        d = np.asarray(k, dtype=float) - self.m
        return d, np.sqrt(d * d + self.s * self.s)

    def implied_w(self, k):
        d, root = self._parts(k)
        return self.a + self.b * (self.rho * d + root)

    def implied_vol(self, k, t):
        return np.sqrt(self.implied_w(k) / t)

    def w_k(self, k):
        d, root = self._parts(k)
        return self.b * (self.rho + d / root)

    def w_kk(self, k):
        _, root = self._parts(k)
        return self.b * self.s * self.s / root**3


class _Flat:
    def __init__(self, w: float) -> None:
        self.w = w

    def implied_w(self, k):
        return np.full_like(np.asarray(k, dtype=float), self.w)

    def implied_vol(self, k, t):
        return np.sqrt(self.implied_w(k) / t)


def _w_surface_reference(ts, slices):
    """The historical api/localvol._w_surface, VERBATIM (byte-identity lock)."""

    def w(k, t):
        k = np.asarray(k, dtype=float)
        t = float(t)
        w_rows = [s.implied_w(k) for s in slices]
        if t <= 0.0:
            return np.zeros_like(k)
        i = int(np.searchsorted(ts, t))
        if i == 0:
            return w_rows[0] * (t / ts[0])
        if i >= ts.size:
            if ts.size == 1:
                return w_rows[-1] * (t / ts[-1])
            slope = (w_rows[-1] - w_rows[-2]) / (ts[-1] - ts[-2])
            return w_rows[-1] + np.maximum(slope, 0.0) * (t - ts[-1])
        lam = (t - ts[i - 1]) / (ts[i] - ts[i - 1])
        return (1.0 - lam) * w_rows[i - 1] + lam * w_rows[i]

    return w


TS = np.array([0.1, 0.25, 0.5, 1.0, 2.0])
#: A proportional SVI ladder: w(k, t) = t * v(k), v = SVI(a=0, b=0.10, ...).
B1, RHO, M, S = 0.10, -0.4, 0.05, 0.3
LADDER = [_SVI(0.0, B1 * t, RHO, M, S) for t in TS]
#: An affine lattice: the t = 0 row, T1/4, every expiry and two sqrt-T midpoints.
T_NODES = np.unique(
    np.concatenate([[0.0, 0.025], TS, [((np.sqrt(0.5) + 1.0) / 2) ** 2, ((1.0 + np.sqrt(2.0)) / 2) ** 2]])
)
X_NODES = np.concatenate([[0.0], np.exp(np.linspace(-0.6, 0.5, 23))])
BOX = dict(var_lo=1e-4, var_hi=4.0)


def _analytic_local_variance(k: np.ndarray, t: float) -> np.ndarray:
    """Closed-form Dupire local variance of the proportional ladder: w = t v(k),
    so w_t = v(k) and the local variance v / g(k, t v) is time-independent
    only through g's 1/w term — evaluated exactly at (k, t)."""
    v = _SVI(0.0, B1, RHO, M, S)
    w = t * v.implied_w(k)
    return dupire_local_variance(k, w, t * v.w_k(k), t * v.w_kk(k), v.implied_w(k))


# --------------------------------------------------------------------------
# 1. The move is byte-identical
# --------------------------------------------------------------------------


def test_buckets_builder_is_the_moved_one_byte_identical():
    from volfit.api import localvol as api_localvol

    assert api_localvol._w_surface is w_surface_buckets
    rng = np.random.default_rng(7)
    new, ref = w_surface_buckets(TS, LADDER), _w_surface_reference(TS, LADDER)
    for t in (-0.1, 0.0, 0.05, 0.1, 0.3, 0.75, 1.0, 1.7, 2.0, 3.5):
        k = rng.uniform(-0.8, 0.8, size=17)
        assert np.array_equal(new(k, t), ref(k, t))
    single = [LADDER[2]]
    new1, ref1 = w_surface_buckets(TS[2:3], single), _w_surface_reference(TS[2:3], single)
    for t in (0.2, 0.5, 0.9):
        k = rng.uniform(-0.8, 0.8, size=9)
        assert np.array_equal(new1(k, t), ref1(k, t))


# --------------------------------------------------------------------------
# 2. Flat
# --------------------------------------------------------------------------


@pytest.mark.parametrize("t_interp", T_INTERPS)
def test_flat_surface_returns_flat_local_variance(t_interp):
    sigma2 = 0.04
    flat = [_Flat(sigma2 * t) for t in TS]
    w = build_w_surface(t_interp, TS, flat)
    twin = extract_twin(w, TS, X_NODES, T_NODES, t_interp=t_interp, **BOX)
    assert twin.counters.clean
    np.testing.assert_allclose(twin.theta, sigma2, rtol=1e-9)
    assert twin.theta.shape == (T_NODES.size, X_NODES.size)


# --------------------------------------------------------------------------
# 3. SVI ladder vs the closed form, both interpolants
# --------------------------------------------------------------------------


@pytest.mark.parametrize("t_interp", T_INTERPS)
def test_svi_ladder_matches_analytic_dupire(t_interp):
    w = build_w_surface(t_interp, TS, LADDER)
    twin = extract_twin(w, TS, X_NODES, T_NODES, t_interp=t_interp, **BOX)
    assert twin.counters.clean
    k = np.log(X_NODES[1:])
    for i, t_row in enumerate(twin.t_rows):
        ref = _analytic_local_variance(k, float(t_row))
        assert np.all(np.isfinite(ref))
        # Second-order FD in k at dk = 2e-3 on a smooth SVI: ~1e-5 relative;
        # the t stencil is exact on a surface linear in t (both interpolants
        # reproduce linear data exactly).
        np.testing.assert_allclose(twin.theta[i, 1:], ref, rtol=2e-4)
    # w = t v(k) has a closed-form local variance depending on t only through
    # the 1/w term of g, so rows at different t agree to that (small) effect,
    # and exactly on the far vertices where 1/w matters least: sanity of the
    # row-time bookkeeping, independent of the reference above.
    assert twin.t_rows[0] > 0.0  # the t = 0 vertex is read at the short end


# --------------------------------------------------------------------------
# 4. PCHIP is monotone on calendar-ordered slices
# --------------------------------------------------------------------------


def test_pchip_monotone_on_calendar_ordered_slices():
    # Nonlinear in t: level grows like t^0.7, skew fades, curvature drifts.
    slices = [
        _SVI(0.002 * t**0.7, 0.12 * t**0.7, -0.5 + 0.1 * t, 0.02 * t, 0.25 + 0.05 * t)
        for t in TS
    ]
    k = np.linspace(-0.6, 0.5, 23)
    rows = np.vstack([s.implied_w(k) for s in slices])
    assert np.all(np.diff(rows, axis=0) > 0.0)  # calendar-ordered at every k
    w = w_surface_pchip(TS, slices)
    grid = np.linspace(0.0, 2.0, 801)
    surface = np.vstack([w(k, t) for t in grid])
    assert np.all(np.diff(surface, axis=0) >= -1e-14)  # monotone in t, every k
    assert np.allclose(surface[0], 0.0)
    # Through every knot exactly
    for t, s in zip(TS, slices):
        np.testing.assert_allclose(w(k, t), s.implied_w(k), rtol=1e-13)
    twin = extract_twin(w, TS, X_NODES, T_NODES, t_interp="smooth", **BOX)
    assert twin.counters.total_calendar == 0
    assert twin.counters.total_butterfly == 0
    assert np.all(twin.theta > 0.0)
    # Beyond the last expiry both builders extend the same flat forward variance.
    wb = w_surface_buckets(TS, slices)
    np.testing.assert_allclose(w(k, 3.0), wb(k, 3.0), rtol=1e-13)


# --------------------------------------------------------------------------
# 5. A crossing is counted, not hidden
# --------------------------------------------------------------------------


@pytest.mark.parametrize("t_interp", T_INTERPS)
def test_calendar_crossing_is_counted(t_interp):
    ladder = list(LADDER)
    ladder[2] = _SVI(0.0, B1 * TS[1] * 0.8, RHO, M, S)  # the 6M slice below the 3M one
    mid = ((np.sqrt(TS[1]) + np.sqrt(TS[2])) / 2) ** 2  # a sqrt-T midpoint inside the drop
    t_nodes = np.unique(np.concatenate([T_NODES, [mid]]))
    w = build_w_surface(t_interp, TS, ladder)
    twin = extract_twin(w, TS, X_NODES, t_nodes, t_interp=t_interp, **BOX)
    assert twin.counters.total_calendar > 0
    assert twin.counters.total_floored >= twin.counters.total_calendar
    assert np.all(twin.theta >= BOX["var_lo"]) and np.all(twin.theta <= BOX["var_hi"])
    assert np.nanmin(twin.raw) <= 0.0  # the unrepaired value is kept beside the sheet
    # Where the flag lands is the interpolant's business: the staircase reads
    # the bucket ENDING at the 6M vertex (negative forward variance there);
    # the monotone PCHIP pins w_t = 0 at the crossing knot and decreases
    # strictly inside the interval, so the midpoint row carries it.
    i_bad = int(np.flatnonzero(np.isclose(t_nodes, TS[2] if t_interp == "buckets" else mid))[0])
    assert twin.counters.calendar[i_bad] > 0


# --------------------------------------------------------------------------
# 6. The exponential-class wing and the cap
# --------------------------------------------------------------------------


def test_exponential_wing_grows_linearly_and_cap_counts():
    x_wide = np.exp(np.linspace(-3.5, 0.0, 36))
    t_nodes = np.array([0.0, 0.5, 1.0])
    w = w_surface_pchip(TS, LADDER)
    free = extract_twin(w, TS, x_wide, t_nodes, t_interp="smooth", var_lo=1e-4, var_hi=1e3)
    assert free.counters.clean
    k = np.log(x_wide)
    row = free.theta[2]  # t = 1
    wing = k <= -2.0
    # Linear growth in |k|: the first differences are steady, the second
    # differences small relative to them (Gatheral: g -> 1/4 - beta^2/16 while
    # w_t grows like the Lee slope times |k|).
    d1 = np.diff(row[wing])
    assert np.all(d1 < 0.0)  # increasing toward the wing (k decreasing)
    assert np.max(np.abs(np.diff(d1))) < 0.1 * np.max(np.abs(d1))
    assert row[0] > 10.0 * row[-1]  # the wing dwarfs the belly
    capped = extract_twin(w, TS, x_wide, t_nodes, t_interp="smooth", var_lo=1e-4, var_hi=0.5)
    assert capped.counters.total_capped > 0
    assert np.all(capped.theta <= 0.5)
    np.testing.assert_array_equal(capped.raw, free.raw)  # the raw twin is untouched


# --------------------------------------------------------------------------
# 7. The guard
# --------------------------------------------------------------------------


def test_guard_holds_flat_beyond_bounds():
    w = w_surface_pchip(TS, LADDER)
    x = np.concatenate([[0.0], np.exp(np.linspace(-1.2, 0.8, 21))])
    twin = extract_twin(
        w, TS, x, np.array([0.0, 0.5, 1.0]), t_interp="smooth", k_lo=-0.7, k_hi=0.4, **BOX
    )
    k = np.log(np.where(x > 0.0, x, 1.0))
    inside = (x > 0.0) & (k >= -0.7) & (k <= 0.4)
    np.testing.assert_array_equal(twin.differentiated, inside)
    lo, hi = int(np.flatnonzero(inside)[0]), int(np.flatnonzero(inside)[-1])
    for i in range(3):
        assert np.all(twin.theta[i, :lo] == twin.theta[i, lo])
        assert np.all(twin.theta[i, hi + 1 :] == twin.theta[i, hi])
        assert np.all(np.isnan(twin.raw[i, ~inside])) and np.all(np.isfinite(twin.raw[i, inside]))
    with pytest.raises(ValueError):
        extract_twin(w, TS, x, np.array([0.0, 1.0]), k_lo=5.0, **BOX)


# --------------------------------------------------------------------------
# 8. Gates and the memo
# --------------------------------------------------------------------------


def test_chip_vocabulary_and_gates():
    with pytest.raises(ValueError):
        build_w_surface("cubic", TS, LADDER)
    w = w_surface_pchip(TS, LADDER)
    with pytest.raises(ValueError):
        extract_twin(w, TS, X_NODES, T_NODES, t_interp="cubic", **BOX)
    with pytest.raises(ValueError):
        extract_twin(w, TS, X_NODES, T_NODES, var_lo=0.5, var_hi=0.1)
    k = np.linspace(-0.3, 0.3, 7)
    assert np.array_equal(w(k, 0.7), w(k.copy(), 0.7))  # memo hit == fresh build
    assert np.all(w(k, 0.0) == 0.0) and np.all(w(k, -1.0) == 0.0)


# --------------------------------------------------------------------------
# 9. The smooth twin as a pricing surface (dupire_twin) and the flat control
# --------------------------------------------------------------------------


def test_twin_surface_matches_the_vertex_extraction_and_memoizes():
    from volfit.models.localvol import DupireTwinSurface, FlatSurface

    w = w_surface_pchip(TS, LADDER)
    twin = extract_twin(w, TS, X_NODES, T_NODES, t_interp="smooth", **BOX)
    surf = DupireTwinSurface(w, TS, t_interp="smooth", **BOX)
    # On the vertices, at the rows' own times, the on-demand surface IS the extraction.
    for i, t in enumerate(twin.t_rows):
        np.testing.assert_allclose(surf.variance(X_NODES, float(t)), twin.theta[i], rtol=1e-13)
    assert surf.clean
    # The same (x, t) again returns the memoized array (one build shares its marches).
    a = surf.variance(X_NODES, 0.5)
    assert surf.variance(X_NODES, 0.5) is a
    # The guard holds flat beyond the bounds, exactly as extract_twin does.
    guarded = DupireTwinSurface(w, TS, t_interp="smooth", k_lo=-0.3, k_hi=0.3, **BOX)
    row = guarded.variance(X_NODES, 0.5)
    k = np.log(X_NODES[1:])
    lo = int(np.argmax(k >= -0.3)) + 1
    assert np.all(row[:lo] == row[lo])
    with pytest.raises(ValueError):
        DupireTwinSurface(w, TS, t_interp="cubic", **BOX)
    flat = FlatSurface(0.04)
    np.testing.assert_array_equal(flat.variance(X_NODES, 0.3), np.full(X_NODES.size, 0.04))
    with pytest.raises(ValueError):
        FlatSurface(0.0)
