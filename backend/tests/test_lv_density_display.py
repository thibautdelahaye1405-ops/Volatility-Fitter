"""The displayed LV density is the model's own (2026-09-03).

``AffineSmile.densityExt`` — the stacked "Densities" overlay curve — used to
be rebuilt from the 81-point reconstructed IV curve through the implied-vol
Breeden-Litzenberger functional (np.gradient twice on a piecewise-linear
w(k)): a sawtooth on long maturities (92 extrema where the lattice density
has 3) and a smoothed, misplaced curve on short ones. It is now the lattice
density (d2C/dx2 of the Dupire call prices) on the converged-operator
reprice, left-extended to K_DISPLAY_LO and trimmed on the right to the
central mass — affine_fit._extended_density.

Locks:
  * synthetic flat surface: densityExt is unimodal, reaches K_DISPLAY_LO,
    integrates to ~1, and equals ``density`` node-for-node on the shared
    central-mass nodes when both come from the same march;
  * ``density`` (the per-expiry payload) is byte-identical to the historical
    trim/stride of the same arrays;
  * on the wire: every smile carries a finite, sorted, non-negative
    densityExt starting at (or below) K_DISPLAY_LO.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.affine_fit import (
    _DENSITY_MAX_POINTS,
    _DENSITY_U_TRIM,
    _extended_density,
    _lattice_density,
    _price_density,
)
from volfit.api.schemas import DistributionArrays
from volfit.api.service import K_DISPLAY_LO
from volfit.models.localvol.affine import AffineVarianceSurface, solve_affine_dupire

REF_DATE = date(2026, 6, 10)
T = 0.5


def _march():
    surf = AffineVarianceSurface(
        t_nodes=np.array([0.0, 2.5]),
        x_nodes=np.array([0.0, 1.0, 2.5]),
        theta=np.full((2, 3), 0.16),
    )
    x = 0.01 * np.arange(251)
    return solve_affine_dupire(surf, x, np.linspace(0.0, T, 65), [T])


def _extrema(f: np.ndarray) -> int:
    s = np.sign(np.diff(f))
    s = s[s != 0]
    return int(np.sum(s[1:] != s[:-1]))


def test_extended_density_is_the_lattice_density():
    sol = _march()
    ext = _extended_density(sol, 0)
    assert ext is not None and not ext.u and not ext.quantile  # density-only curve
    k = np.array(ext.x)
    f = np.array(ext.density)
    assert np.all(np.diff(k) > 0) and np.all(np.isfinite(f)) and np.all(f >= 0.0)
    assert k[0] <= K_DISPLAY_LO + 1e-12
    assert _extrema(f) == 1  # a flat 40% slice: one mode, no sawtooth
    assert np.trapezoid(f, k) == pytest.approx(1.0, abs=2e-3)
    # Node-for-node the same values as `density` on the shared lattice nodes.
    core = _price_density(sol, 0)
    core_map = dict(zip(core.x, core.density))
    shared = [kk for kk in ext.x if kk in core_map]
    assert len(shared) > 50
    for kk, ff in zip(ext.x, ext.density):
        if kk in core_map:
            assert ff == core_map[kk]


def test_price_density_payload_unchanged_by_the_refactor():
    """The historical trim + stride, reproduced from the shared arrays."""
    sol = _march()
    k, f_x, cdf = _lattice_density(sol, 0)
    keep = np.flatnonzero((cdf >= _DENSITY_U_TRIM) & (cdf <= 1.0 - _DENSITY_U_TRIM))
    stride = max(1, -(-keep.size // _DENSITY_MAX_POINTS))
    idx = keep[::stride]
    expected = DistributionArrays(
        x=k[idx].tolist(), density=f_x[idx].tolist(), u=cdf[idx].tolist(), quantile=k[idx].tolist()
    )
    assert _price_density(sol, 0) == expected


@pytest.fixture(scope="module")
def fitted():
    with TestClient(create_app(reference_date=REF_DATE)) as client:
        ticker = client.get("/universe").json()["tickers"][0]
        resp = client.post(f"/fit/affine/{ticker}", json={})
        assert resp.status_code == 200, resp.text
        yield resp.json()


def test_density_ext_on_the_wire(fitted):
    for smile in fitted["smiles"]:
        ext = smile["densityExt"]
        assert ext is not None
        k = np.array(ext["x"])
        f = np.array(ext["density"])
        assert k.size > 20 and np.all(np.diff(k) > 0)
        assert np.all(np.isfinite(f)) and np.all(f >= 0.0)
        assert k[0] <= K_DISPLAY_LO + 1e-9
        assert f.max() > 0.0
