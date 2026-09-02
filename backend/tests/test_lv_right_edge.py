"""LV display right wing vs the lattice's Dirichlet boundary layer (2026-09-02).

The forward Dupire march closes its strike lattice with C(., x_max) = 0. By
the method of images the marched price near the edge is the free price
times (1 − exp(−2 c (x_max − x))) — a linear-to-zero profile over the last
~1/c of the lattice (node ratios 1/2, 2/3, 3/4, …) whose Black inversion
collapses the implied vol toward the edge, most sharply on short-dated
slices (steep scheme tail, narrow violent layer). The historical display cap
ln(x_max) − ε sat ON the boundary node: the user-visible "smile collapsing
instead of increasing past k ≈ 0.9" (ln 2.5 = 0.916, the default floor).

The reference for "free of the layer" is the SAME operator (same dx, same
time grid, same surface) on a lattice reaching x = 6 — the only difference
between the two marches is where the Dirichlet boundary sits, so their gap
is the layer and nothing else (the scheme's own error cancels).

Locks (api.affine_views_ext):
  * ``clean_right_edge`` finds the layer on a raw march: the inverted vol
    matches the wide reference to < 0.05 vol point up to the clean edge and
    is visibly collapsed at the last interior node;
  * ``extended_model`` never inverts inside the layer — with or without the
    display march — so every point stays on the reference;
  * ``display_lattice`` reuses the calibration lattice (same dx, same nodes)
    and reaches past K_DISPLAY_HI by the buffer; the extension march lets
    the wing reach K_DISPLAY_HI while the core stays bit-identical;
  * the guard is not over-conservative near the money of a long-dated slice
    on a lattice that is honestly wide enough.
"""

import numpy as np
import pytest

from volfit.api import affine_views_ext as ext
from volfit.api.service import K_DISPLAY_HI
from volfit.core.black import implied_total_variance_otm
from volfit.models.localvol.affine import AffineVarianceSurface, solve_affine_dupire
from volfit.models.localvol.reprice import reprice_affine_dupire

VAR = 0.16  # flat 40% local vol: the right tail at k = 1 prices ~1e-4 at T = 0.5
T = 0.5
K_PAD, N_CORE = 0.02, 81
X_WIDE = 6.0  # the reference lattice: its own layer sits far beyond k = 1


def _flat_surface(var: float = VAR) -> AffineVarianceSurface:
    return AffineVarianceSurface(
        t_nodes=np.array([0.0, 2.5]),
        x_nodes=np.array([0.0, 1.0, 2.5]),
        theta=np.full((2, 3), var),
    )


def _lattice(x_max: float = 2.5, dx: float = 0.01) -> np.ndarray:
    n = int(round(x_max / dx))
    return dx * np.arange(n + 1)


def _march(x_grid: np.ndarray, t: float = T, n_t: int = 64):
    t_grid = np.linspace(0.0, t, n_t + 1)
    return solve_affine_dupire(_flat_surface(), x_grid, t_grid, [t]), t_grid


def _vol_at(sol, k: np.ndarray, t: float) -> np.ndarray:
    """Call-side Black inversion of a march at log-moneyness k (k > 0)."""
    with np.errstate(all="ignore"):
        w = implied_total_variance_otm(k, sol.price_at(0, np.exp(k)))
    return np.sqrt(np.maximum(w, 0.0) / t)


@pytest.fixture(scope="module")
def marches():
    narrow, t_grid = _march(_lattice())
    wide, _ = _march(_lattice(X_WIDE))
    return narrow, wide, t_grid


def test_raw_march_collapses_inside_the_layer_and_guard_finds_it(marches):
    narrow, wide, _ = marches
    x = narrow.x_grid
    k_clean = ext.clean_right_edge(x, narrow.prices[0])
    assert 0.4 < k_clean < np.log(x[-1]) - 0.02, k_clean
    k = np.log(x[(x > 1.3) & (np.log(np.maximum(x, 1e-9)) <= k_clean)])
    # Matches the wide reference up to the clean edge …
    gap = np.abs(_vol_at(narrow, k, T) - _vol_at(wide, k, T))
    assert np.max(gap) < 5e-4, np.max(gap)
    # … and visibly collapsed at the last interior node (the linear-to-zero
    # profile: C_{N-1} ≈ C_{N-2} / 2).
    assert narrow.prices[0][-2] / narrow.prices[0][-3] == pytest.approx(0.5, abs=0.03)
    k_last = np.log(x[-2:-1])
    assert _vol_at(narrow, k_last, T)[0] < _vol_at(wide, k_last, T)[0] - 0.01


def test_extended_model_without_display_march_never_collapses(marches):
    narrow, wide, _ = marches
    x = narrow.x_grid
    pts = ext.extended_model(narrow, 0, T, -0.2, 0.2, x, K_PAD, N_CORE)
    ks = np.array([p.k for p in pts])
    vols = np.array([p.vol for p in pts])
    assert ks[-1] == pytest.approx(np.log(x[-1]) - ext._EDGE_EPS)
    k_clean = ext.clean_right_edge(x, narrow.prices[0])
    ref = _vol_at(wide, ks, T)
    # On the reference up to the clean edge …
    inside = (ks > 0.0) & (ks <= k_clean)
    assert np.max(np.abs(vols[inside] - ref[inside])) < 2e-3
    # … then FLAT at the clean-edge level (the no-information doctrine) and
    # within half a vol point of the reference's own drift — the old cap put
    # the last point on the boundary node, a cliff of several vol points.
    beyond = ks > k_clean
    assert np.any(beyond)
    assert np.ptp(vols[beyond]) < 1e-12
    assert np.max(np.abs(vols[beyond] - ref[beyond])) < 5e-3


def test_display_lattice_extends_the_calibration_lattice_in_place():
    x = _lattice()
    x_disp = ext.display_lattice(x, 0.22, w_tail=VAR * T)
    assert x_disp is not None
    assert x_disp.size > x.size
    np.testing.assert_array_equal(x_disp[: x.size], x)  # same dx, same nodes
    assert x_disp[-1] >= np.exp(K_DISPLAY_HI + ext._EXT_DK_MIN) - 1e-9
    assert x_disp[-1] <= ext._EXT_X_MULT_MAX * x[-1] + 1e-9
    # A lattice already reaching past the cap + buffer needs no march.
    assert ext.display_lattice(_lattice(x_max=X_WIDE), 0.22, w_tail=VAR * T) is None


def test_display_march_reaches_display_cap_and_keeps_the_core(marches):
    narrow, wide, t_grid = marches
    x = narrow.x_grid
    x_disp = ext.display_lattice(x, 0.22, w_tail=VAR * T)
    ext_sol = reprice_affine_dupire(_flat_surface(), x_disp, t_grid, [T])
    base = ext.extended_model(narrow, 0, T, -0.2, 0.2, x, K_PAD, N_CORE)
    full = ext.extended_model(
        narrow, 0, T, -0.2, 0.2, x, K_PAD, N_CORE, ext_call_solution=ext_sol
    )
    ks = np.array([p.k for p in full])
    vols = np.array([p.vol for p in full])
    assert ks[-1] == pytest.approx(K_DISPLAY_HI)
    right = ks > 0.0
    gap = np.abs(vols[right] - _vol_at(wide, ks[right], T))
    assert np.max(gap) < 2e-3, np.max(gap)
    # The core (quoted range ± pad) is the calibrated march's own inversion,
    # bit-identical with or without the display march.
    core = {p.k: p.vol for p in base if abs(p.k) <= 0.2 + K_PAD + 1e-12}
    assert len(core) == N_CORE
    for p in full:
        if p.k in core:
            assert p.vol == core[p.k]


def test_guard_is_not_over_conservative_near_the_money_long_dated():
    """A 2-year 40% slice (w = 0.32) on a lattice reaching x = 6: the
    local-rate bound alone would flag the near-the-money region (its rate
    under-estimates the Gaussian tail's decay outward); the Black mirror
    estimate keeps everything up to and past k = 1."""
    x = _lattice(X_WIDE)
    sol, _ = _march(x, t=2.0, n_t=200)
    k_clean = ext.clean_right_edge(x, sol.prices[0])
    assert k_clean > K_DISPLAY_HI, k_clean
