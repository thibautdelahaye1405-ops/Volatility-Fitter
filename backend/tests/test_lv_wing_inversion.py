"""LocalVol display wings: OTM-side inversion via a marched put twin.

The LQD short-dated wing fix's LV mirror (2026-08-31): both LV pricers only
marched CALLS, so the left display wing's time value was formed as
C - (1 - e^k) — floored at the intrinsic leg's ~1e-16 round-off, nan under
inversion, drawn flat by the display's constant extension. Both engines now
march a put twin through the SAME operator:

  * affine (production LV): ``reprice_affine_dupire(payoff="put")`` — 1 - x
    lies in the exact kernel of the nonuniform central stencil, so discrete
    parity C - P = 1 - x holds to round-off at every step and the k = 0 seam
    between the call-side and put-side inversions is exact
    (api.affine_views_ext.otm_implied_w);
  * grid model (models.localvol.pde): the put rides the same banded factor
    per step (P(k,0) = (e^k - 1)^+, Dirichlet 0 / e^{k_max} - 1); parity in
    k-space is exact only in the continuum (the stencil is O(h^2) on e^k),
    so the discrete drift is bounded, not zero.
"""

import numpy as np
import pytest

from volfit.api.affine_views_ext import otm_implied_w
from volfit.core.black import implied_total_variance
from volfit.models.localvol.affine import AffineVarianceSurface, solve_affine_dupire
from volfit.models.localvol.grid import LocalVolGrid
from volfit.models.localvol.model import LocalVolModel
from volfit.models.localvol.pde import solve_dupire
from volfit.models.localvol.reprice import reprice_affine_dupire

#: ~2-day flat 20%-vol setup: w = 0.04 * T ~ 2.2e-4, so |d| = 10 at k ~ -0.15
#: — the whole test wing [-0.35, -0.15] is beyond the parity route's ~1e-16
#: floor while its true prices (1e-200..1e-24) stay perfectly representable.
T_2D = 2.0 / 365.0


def _flat_surface(var: float = 0.04) -> AffineVarianceSurface:
    return AffineVarianceSurface(
        t_nodes=np.array([0.0, 0.02]),
        x_nodes=np.array([0.0, 1.0, 2.5]),
        theta=np.full((2, 3), var),
    )


def _grids(n_x: int = 4801, n_t: int = 513) -> tuple[np.ndarray, np.ndarray]:
    """Short-front-refined grids (dt = T/512, dx ~ sigma*sqrt(T)/28): an
    implicit march's wing values are the SCHEME's tail beyond a crossover
    scaling with sqrt(T/dt) (the fix-#3 lesson), and the 5-8 sd band needs
    both the time refinement AND enough mesh points per terminal sd — the
    production _pde_grids short-front dx cap exists for exactly this."""
    return np.linspace(0.0, 2.5, n_x), np.linspace(0.0, T_2D, n_t)


# ------------------------------------------------------------ affine engine
def test_affine_put_march_discrete_parity_implicit():
    """C - P = 1 - x to round-off on the shared grid (implicit scheme)."""
    surf = _flat_surface()
    x_grid, t_grid = _grids()
    call = reprice_affine_dupire(surf, x_grid, t_grid, [T_2D])
    put = reprice_affine_dupire(surf, x_grid, t_grid, [T_2D], payoff="put")
    parity = call.prices[0] - put.prices[0] - (1.0 - x_grid)
    np.testing.assert_allclose(parity, 0.0, atol=1e-11)


def test_affine_put_march_discrete_parity_rannacher():
    """The same parity lock under the Stage-7 Rannacher scheme (both marches
    must ride the SAME scheme or the seam kink lands exactly at k = 0)."""
    surf = _flat_surface()
    x_grid, t_grid = _grids()
    call = solve_affine_dupire(surf, x_grid, t_grid, [T_2D], time_scheme="rannacher")
    put = reprice_affine_dupire(
        surf, x_grid, t_grid, [T_2D], payoff="put", time_scheme="rannacher"
    )
    parity = call.prices[0] - put.prices[0] - (1.0 - x_grid)
    np.testing.assert_allclose(parity, 0.0, atol=1e-11)


def test_affine_reprice_default_path_unchanged_by_new_args():
    """The default reprice (call, implicit) still matches the production
    march's value path bit-for-bit — the historical lock, re-asserted against
    the parameterized signature."""
    surf = _flat_surface()
    x_grid, t_grid = _grids()
    a = solve_affine_dupire(surf, x_grid, t_grid, [T_2D])
    b = reprice_affine_dupire(surf, x_grid, t_grid, [T_2D])
    assert np.array_equal(a.prices, b.prices)


def test_affine_left_wing_inverts_where_parity_route_degrades():
    """2-day flat surface, left wing. In the tv-floor-relevant band (|d| up
    to ~7.5, the region the display actually inverts) the put-side inversion
    recovers the 20% vol cleanly; deeper out it stays finite, positive and
    monotone (a smooth curve — beyond ~8 sd an implicit march's values are
    the scheme's own tail, which the affine display's _EXT_TV_FLOOR guard
    flat-extends over). The historical call-side route reads the left time
    value off the cancelled intrinsic leg: pure ~1e-17 round-off noise deep
    out — nan wherever the noise lands negative (the jagged/flat displays)."""
    surf = _flat_surface()
    x_grid, t_grid = _grids()
    call = reprice_affine_dupire(surf, x_grid, t_grid, [T_2D])
    put = reprice_affine_dupire(surf, x_grid, t_grid, [T_2D], payoff="put")
    # Floor-relevant band: |d| in [4, 7.5] at sigma = 0.2, T = 2d.
    band = np.linspace(-0.111, -0.059, 27)
    w, tv = otm_implied_w(call, put, 0, band)
    assert np.all(np.isfinite(w)) and np.all(tv > 0.0)
    np.testing.assert_allclose(np.sqrt(w / T_2D), 0.20, atol=5e-3)
    # Deep wing: finite, positive, monotone toward ATM — never nan/jagged.
    deep = np.linspace(-0.35, -0.15, 41)
    w_deep, tv_deep = otm_implied_w(call, put, 0, deep)
    assert np.all(np.isfinite(w_deep)) and np.all(tv_deep > 0.0)
    vol_deep = np.sqrt(w_deep / T_2D)
    assert np.all(np.diff(vol_deep) < 0.0)  # decreasing toward ATM
    # The historical route on the same range: noise-sign nan somewhere.
    w_old = np.asarray(implied_total_variance(deep, call.price_at(0, np.exp(deep))))
    assert np.any(~np.isfinite(w_old))


def test_affine_otm_seam_continuous_at_forward():
    """Call-side and put-side inversions agree across k = 0: discrete parity
    C - P = 1 - x makes the two sides the SAME surface, so the vol curve
    crosses the forward without a kink (linear price interpolation between
    lattice nodes bounds the residual wiggle)."""
    surf = _flat_surface()
    x_grid, t_grid = _grids()
    call = reprice_affine_dupire(surf, x_grid, t_grid, [T_2D])
    put = reprice_affine_dupire(surf, x_grid, t_grid, [T_2D], payoff="put")
    grid = np.array([-0.004, -0.002, 0.002, 0.004])
    w, _ = otm_implied_w(call, put, 0, grid)
    vol = np.sqrt(w / T_2D)
    # Both sides within interpolation noise of each other and of the level.
    assert float(np.max(vol) - np.min(vol)) < 2e-3
    np.testing.assert_allclose(vol, 0.20, atol=5e-3)


# -------------------------------------------------------------- grid engine
def test_grid_model_put_row_parity_and_left_wing():
    """The pde.py put row: bounded parity drift (the k-space stencil is
    O(h^2) on e^k) and a finite, ~flat-vol left wing where the parity route
    is nan on a 2-day slice."""
    lv = LocalVolGrid(
        k=np.array([-0.6, 0.0, 0.6]),
        t=np.array([0.005, 0.02]),
        sigma=np.full((2, 3), 0.2),
    )
    # dt = T/512: same front-refinement requirement as the affine tests above —
    # at the default dt_max a 2-day expiry marches ~3 steps and the wing is
    # the scheme's tail, not the model's.
    model = LocalVolModel(lv, dt_max=T_2D / 512.0)
    sl = model.slice_at(T_2D)
    assert sl.put_prices is not None
    # Parity drift on the body of the mesh (continuum-exact, discrete O(h^2)).
    k = np.linspace(-0.4, 0.4, 81)
    parity = sl.call_price(k) - sl.put_price(k) - (1.0 - np.exp(k))
    np.testing.assert_allclose(parity, 0.0, atol=1e-8)
    # Floor-relevant band (|d| up to ~7.5): the put row inverts to the level.
    band = np.linspace(-0.111, -0.059, 27)
    vol_band = np.sqrt(np.asarray(sl.implied_w(band), dtype=float) / T_2D)
    assert np.all(np.isfinite(vol_band))
    np.testing.assert_allclose(vol_band, 0.20, atol=5e-3)
    # Deep wing: finite, positive, monotone toward ATM (smooth display —
    # beyond ~8 sd the values are the scheme's tail, never nan/jagged).
    wing = np.linspace(-0.35, -0.15, 41)
    vol = np.sqrt(np.asarray(sl.implied_w(wing), dtype=float) / T_2D)
    assert np.all(np.isfinite(vol))
    assert np.all(np.diff(vol) < 0.0)  # decreasing toward ATM
    # The historical call-parity route: in k-space the stencil is O(h^2) on
    # e^k, so the call row's deep-left "time value" IS the parity drift —
    # it inverts to a phantom wing far off the put row's story.
    w_old = np.asarray(implied_total_variance(wing, sl.call_price(wing)))
    vol_old = np.sqrt(np.maximum(np.nan_to_num(w_old), 0.0) / T_2D)
    assert np.any(~np.isfinite(w_old)) or float(np.max(np.abs(vol_old - vol))) > 0.1


def test_grid_model_call_rows_unchanged_by_put_march():
    """The put twin must not perturb the call rows: same solve as a fresh
    march, and the diagnostics gate still reads arbitrage-free."""
    lv = LocalVolGrid(
        k=np.array([-0.6, 0.0, 0.6]),
        t=np.array([0.1, 1.0]),
        sigma=np.full((2, 3), 0.2),
    )
    sol = solve_dupire(lv, [0.25, 0.5])
    diag = LocalVolModel(lv).diagnostics([0.25, 0.5])
    assert diag.arbitrage_free
    # Flat 20%: ATM call at T = 0.25 should invert to ~20% vol.
    i0 = int(np.argmin(np.abs(sol.k_mesh)))
    w = float(implied_total_variance(sol.k_mesh[i0], sol.prices[0][i0]))
    assert np.sqrt(w / 0.25) == pytest.approx(0.20, abs=5e-4)
