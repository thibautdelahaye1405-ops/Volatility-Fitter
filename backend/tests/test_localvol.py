"""Local-volatility grid model: PDE round trips, Dupire consistency, gates.

Invariants exercised:
1. Flat sigma: the Dupire PDE must reproduce Black prices -- implied vol back
   within 1 vol bp on the liquid range, density nonnegative.
2. Term structure only: total implied variance equals the time integral of
   sigma(t)^2, for both pw_t buckets and a bilinear linear-in-t ramp.
3. Skew round trip (the consistency check): analytic positive sigma_loc(k, t)
   -> PDE prices -> implied w surface -> Dupire extraction recovers the input
   local vol on a central block, with butterfly / calendar residuals at noise
   level.
4. Gates: non-positive node vols are refused at construction; an arbitrage-
   violating implied surface yields nan local variance, never an exception.
5. Convergence: halving the mesh step shrinks the flat-vol error ~4x (O(h^2)
   central differences); >= 2.5x asserted to leave room for the temporal
   error floor shared by both resolutions.
6. Protocol: LocalVolSlice satisfies SmileModel and implied_vol is
   sqrt(implied_w / t) pointwise.
"""

import numpy as np
import pytest

from volfit.core.black import implied_total_variance
from volfit.models.base import SmileModel
from volfit.models.localvol import (
    LocalVolGrid,
    LocalVolModel,
    dupire_local_variance,
    extract_grid,
    solve_dupire,
)


def _flat_grid(vol: float = 0.2) -> LocalVolGrid:
    return LocalVolGrid(
        k=np.array([-1.0, 1.0]),
        t=np.array([0.1, 2.0]),
        sigma=np.full((2, 2), vol),
    )


# ---------------------------------------------------------------------------
# 0. Grid interpolation semantics (cheap unit checks of both interp modes)
# ---------------------------------------------------------------------------


def test_grid_interpolation_modes():
    k = np.array([-1.0, 0.0, 1.0])
    t = np.array([0.5, 1.0])
    sigma = np.array([[0.3, 0.2, 0.1], [0.5, 0.4, 0.3]])

    bil = LocalVolGrid(k=k, t=t, sigma=sigma, interp="bilinear")
    # Affine in t between rows, affine in k between nodes, flat outside.
    assert bil.vol(0.0, 0.75) == pytest.approx(0.3)
    assert bil.vol(0.5, 0.5) == pytest.approx(0.15)
    assert bil.vol(0.0, 0.01) == pytest.approx(0.2)  # flat below t[0]
    assert bil.vol(0.0, 5.0) == pytest.approx(0.4)  # flat above t[-1]
    assert bil.vol(-3.0, 0.5) == pytest.approx(0.3)  # flat left of k[0]

    pwt = LocalVolGrid(k=k, t=t, sigma=sigma, interp="pw_t")
    # Row i applies on [t_i, t_{i+1}); flat outside.
    assert pwt.vol(0.0, 0.5) == pytest.approx(0.2)  # left node of [0.5, 1.0)
    assert pwt.vol(0.0, 0.999) == pytest.approx(0.2)
    assert pwt.vol(0.0, 1.0) == pytest.approx(0.4)
    assert pwt.vol(0.0, 0.1) == pytest.approx(0.2)  # flat below t[0]


# ---------------------------------------------------------------------------
# 1. Flat-vol round trip
# ---------------------------------------------------------------------------


def test_flat_vol_round_trip():
    model = LocalVolModel(_flat_grid(0.2))
    sol = model.solve((0.25, 1.0))
    for i, t_exp in enumerate(sol.expiries):
        # 1 vol bp inside 3 standard deviations: beyond that the option has
        # essentially no vega, so dividing the scheme's tiny absolute price
        # error by it inflates the implied-vol error without meaning (at
        # T = 0.25 a fixed k = 0.5 is already 5 sd out and reads ~160 bp).
        band = np.abs(sol.k_mesh) <= 3.0 * 0.2 * np.sqrt(t_exp)
        w = implied_total_variance(sol.k_mesh[band], sol.prices[i][band])
        vol = np.sqrt(w / t_exp)
        assert np.max(np.abs(vol - 0.2)) <= 1e-4
        assert sol.density(i).min() >= -1e-8


# ---------------------------------------------------------------------------
# 2. Pure term structure
# ---------------------------------------------------------------------------


def test_pw_t_forward_variance_buckets():
    # sigma = 0.3 on [0, 0.5), 0.1 on [0.5, 1]: row 0 extends flat below
    # t[0] = 0.01 and row 1 (left node t = 0.5) covers [0.5, 1].
    grid = LocalVolGrid(
        k=np.array([-1.0, 1.0]),
        t=np.array([0.01, 0.5]),
        sigma=np.array([[0.3, 0.3], [0.1, 0.1]]),
        interp="pw_t",
    )
    # dt_max = 1/200 places a step boundary exactly at t = 0.5, so midpoint
    # sampling integrates each bucket's variance exactly.
    sol = solve_dupire(grid, (1.0,))
    i0 = sol.k_mesh.size // 2  # k = 0 on the symmetric odd mesh
    w = float(implied_total_variance(0.0, sol.prices[0][i0]))
    # w(0, 1) = 0.09 * 0.5 + 0.01 * 0.5 = 0.05.
    assert abs(np.sqrt(w) - np.sqrt(0.05)) <= 2e-4


def test_bilinear_time_ramp():
    # sigma(t) = 0.15 + 0.1 t, k-independent: exactly representable by a
    # bilinear grid with nodes at t = 1e-4 and t = 1 (flat-extrapolation bias
    # below 1e-4 is O(1e-6) in w, far under tolerance).
    t_nodes = np.array([1e-4, 1.0])
    sig = 0.15 + 0.1 * t_nodes
    grid = LocalVolGrid(
        k=np.array([-1.0, 1.0]),
        t=t_nodes,
        sigma=np.column_stack([sig, sig]),
    )
    sol = solve_dupire(grid, (1.0,))
    i0 = sol.k_mesh.size // 2
    w = float(implied_total_variance(0.0, sol.prices[0][i0]))
    # w(0, 1) = int_0^1 (0.15 + 0.1 t)^2 dt = 0.0225 + 0.015 + 0.01/3.
    w_true = 0.0225 + 0.015 + 0.01 / 3.0
    assert abs(np.sqrt(w) - np.sqrt(w_true)) <= 2e-4


# ---------------------------------------------------------------------------
# 3. Skew round trip through Dupire extraction
# ---------------------------------------------------------------------------


def _sigma_true(k, t):
    """Analytic strictly positive local vol with skew and a time decay."""
    return 0.2 - 0.12 * np.tanh(2.0 * k) + 0.04 * np.exp(-t)


def test_skew_dupire_round_trip():
    k_nodes = np.linspace(-1.2, 1.2, 81)
    t_nodes = np.linspace(0.05, 1.1, 25)
    grid = LocalVolGrid(
        k=k_nodes,
        t=t_nodes,
        sigma=_sigma_true(k_nodes[None, :], t_nodes[:, None]),
    )
    model = LocalVolModel(grid)
    exps = np.linspace(0.3, 0.9, 7)
    sol = model.solve(exps)

    # Invert PDE prices to total variance on a central strike band.
    # |k| <= 0.5 keeps the inversion well-conditioned: the right wing has
    # sigma_loc ~ 0.1, so for k >= 0.6 at T = 0.3 prices sit 8+ sd out
    # (~1e-15) where roundoff swamps the Brent inversion.  The band still
    # covers every extraction query below (max |k| = 0.4 + dk = 0.45).
    band = np.abs(sol.k_mesh) <= 0.5 + 1e-12
    k_sub = sol.k_mesh[band]
    w_grid = np.array(
        [implied_total_variance(k_sub, sol.prices[i][band]) for i in range(exps.size)]
    )
    assert np.isfinite(w_grid).all()

    def w_surface(k_arr, t):
        """Bilinear interpolation of the inverted w grid in (k, t)."""
        t = float(t)
        j = int(np.searchsorted(exps, t))
        if j <= 0:
            row = w_grid[0]
        elif j >= exps.size:
            row = w_grid[-1]
        else:
            wgt = (t - exps[j - 1]) / (exps[j] - exps[j - 1])
            row = (1.0 - wgt) * w_grid[j - 1] + wgt * w_grid[j]
        return np.interp(np.asarray(k_arr, dtype=float), k_sub, row)

    # FD steps: dk = dt = 0.05.  The surface is piecewise linear (k mesh
    # spacing 0.01, expiry spacing 0.1), so steps must straddle whole
    # interpolation cells -- with dk = 1e-3 the w_kk stencil would measure
    # the interpolant's kinks, not the surface curvature (dupire.py docs).
    k_ext = np.linspace(-0.4, 0.4, 9)
    t_ext = np.linspace(0.4, 0.8, 5)
    res = extract_grid(w_surface, k_ext, t_ext, dk=0.05, dt=0.05)
    assert res.n_nan == 0
    assert res.n_clipped == 0

    sig_true = _sigma_true(k_ext[None, :], t_ext[:, None])
    rel_err = np.abs(res.grid.sigma - sig_true) / sig_true
    # 3%: budget for PDE O(h^2, dt^2) error, bilinear w interpolation, and
    # second-order FD truncation at dk = dt = 0.05.
    assert rel_err.max() <= 0.03

    diag = model.diagnostics(exps)  # reuses the cached solve
    assert diag.min_density.min() >= -1e-8
    assert diag.calendar_violation.max() <= 1e-8
    assert diag.arbitrage_free


# ---------------------------------------------------------------------------
# 4. Gates
# ---------------------------------------------------------------------------


def test_nonpositive_sigma_rejected():
    sigma = np.full((2, 2), 0.2)
    for bad in (0.0, -0.1):
        sigma_bad = sigma.copy()
        sigma_bad[1, 0] = bad
        with pytest.raises(ValueError):
            LocalVolGrid(k=np.array([-1.0, 1.0]), t=np.array([0.1, 1.0]), sigma=sigma_bad)


def test_dupire_arbitrage_returns_nan():
    # Absurd wkk = -10 drives the butterfly denominator negative: nan, no raise.
    v = dupire_local_variance(k=0.1, w=0.04, wk=0.0, wkk=-10.0, wt=0.04)
    assert np.isnan(v)
    # Sane inputs next to it still come back finite (flat surface: sigma^2 = wt).
    v_ok = dupire_local_variance(k=0.0, w=0.04, wk=0.0, wkk=0.0, wt=0.04)
    assert float(v_ok) == pytest.approx(0.04)


# ---------------------------------------------------------------------------
# 5. Spatial convergence
# ---------------------------------------------------------------------------


def test_spatial_convergence():
    grid = _flat_grid(0.2)

    def max_vol_err(n_k: int) -> float:
        # dt_max = 1/500 keeps the temporal error well below the spatial one,
        # so the n_k = 251 -> 501 comparison isolates the O(h^2) term.
        sol = solve_dupire(grid, (0.5,), n_k=n_k, dt_max=1.0 / 500.0)
        band = np.abs(sol.k_mesh) <= 3.0 * 0.2 * np.sqrt(0.5)  # vega-meaningful 3 sd
        w = implied_total_variance(sol.k_mesh[band], sol.prices[0][band])
        return float(np.max(np.abs(np.sqrt(w / 0.5) - 0.2)))

    err_coarse = max_vol_err(251)
    err_fine = max_vol_err(501)
    assert err_coarse >= 2.5 * err_fine


# ---------------------------------------------------------------------------
# 6. SmileModel protocol
# ---------------------------------------------------------------------------


def test_slice_satisfies_smile_model_protocol():
    model = LocalVolModel(_flat_grid(0.25))
    sl = model.slice_at(0.5)
    assert isinstance(sl, SmileModel)
    k = np.linspace(-0.3, 0.3, 7)
    np.testing.assert_allclose(
        sl.implied_vol(k, 0.5), np.sqrt(sl.implied_w(k) / 0.5), rtol=0, atol=1e-14
    )
    # slice_at must reuse the cached solve for an already-solved expiry set.
    sol = model.solve((0.5,))
    sl2 = model.slice_at(0.5)
    assert sl2.prices is sol.prices[0] or np.array_equal(sl2.prices, sol.prices[0])
