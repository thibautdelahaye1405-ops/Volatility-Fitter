"""Regression: the affine PDE strike grid keeps the var-swap anchor x = 1.

A real ticker's strike range pushes the fine grid's x_max above the 2.5 floor and
off the 0.01 lattice; a linspace there lands x = 1 between nodes and
affine_calib.varswap_weights (called for EVERY smile via _model_varswap_vol)
422s the whole fit. The grid must be a uniform 0.01 lattice from 0 so 1.0 is
always node 100. (Synthetic's range floors at 2.5, which aligned — hence the
original miss.)

V3.3 rider — the lattice right-edge FLOOR is the Options setting ``lvXMaxMin``
(``_pde_grids(..., x_max_min=)``): 2.5 is byte-identical to the historical
constant; a wider floor extends the lattice (x = 1 still a node, same step,
same time grid), re-keys the LV cache WITHOUT bumping the options version
(parametric caches stay warm), and widens ``modelExt``'s right edge on the
wire while ``model`` (the quoted-range curve) is unchanged.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.affine_fit import _pde_grids, affine_key
from volfit.api.schemas import OptionsSettings
from volfit.api.schemas_affine import AffineFitRequest
from volfit.api.service import K_DISPLAY_HI, fit_key
from volfit.api.state import AppState
from volfit.models.localvol.affine_calib import varswap_const, varswap_weights

REF_DATE = date(2026, 6, 10)


@pytest.mark.parametrize("k_hi", [0.0, 0.336, 0.6, 0.8, 1.0, 1.25])
def test_pde_grid_keeps_x1_node_and_uniform(k_hi):
    x_grid, _ = _pde_grids(np.array([0.1, 0.5]), k_hi)
    assert np.any(x_grid == 1.0)  # exact float node (searchsorted equality)
    step = x_grid[1] - x_grid[0]
    assert np.allclose(np.diff(x_grid), step)  # uniform spacing for the PDE
    assert step == pytest.approx(0.01)
    # The var-swap replication must accept the grid (this raised the 422 live).
    varswap_weights(x_grid, 0.01)
    varswap_const(x_grid, 0.01)


def test_wide_range_grid_does_not_reject():
    """A SPY-like wide range (x_max well above 2.5, off the lattice) is fine."""
    x_grid, _ = _pde_grids(np.array([0.25, 1.0]), k_hi=0.95)
    assert x_grid[-1] > 2.5
    i = int(np.searchsorted(x_grid, 1.0))
    assert x_grid[i] == 1.0


# -- lvXMaxMin: the lattice right-edge floor (V3.3 rider) ---------------------

EXPIRIES = np.array([0.1, 0.5])


@pytest.mark.parametrize("k_hi", [0.0, 0.336, 0.6, 0.95, 1.25])
def test_pde_grid_default_floor_is_byte_identical(k_hi):
    """Passing the default floor explicitly changes nothing (both grids)."""
    x0, t0 = _pde_grids(EXPIRIES, k_hi)
    x1, t1 = _pde_grids(EXPIRIES, k_hi, x_max_min=2.5)
    assert np.array_equal(x0, x1)
    assert np.array_equal(t0, t1)


def test_pde_grid_wider_floor_extends_lattice_and_keeps_x1():
    x_grid, t_grid = _pde_grids(EXPIRIES, 0.336, x_max_min=4.0)
    assert x_grid[-1] >= 4.0 - 1e-9
    assert x_grid[1] - x_grid[0] == pytest.approx(0.01)
    assert np.allclose(np.diff(x_grid), 0.01)  # still the uniform dx lattice
    assert np.any(x_grid == 1.0)  # exact var-swap anchor node
    varswap_weights(x_grid, 0.01)
    varswap_const(x_grid, 0.01)
    # The time grid does not depend on the strike floor.
    _, t_default = _pde_grids(EXPIRIES, 0.336)
    assert np.array_equal(t_grid, t_default)
    # A quoted range already wider than the floor is untouched by it
    # (exp(1.25) * 1.4 ≈ 4.89 > 4.0: the pad wins, as before).
    wide, _ = _pde_grids(EXPIRIES, 1.25)
    wide_floor, _ = _pde_grids(EXPIRIES, 1.25, x_max_min=4.0)
    assert np.array_equal(wide, wide_floor)


def test_lv_x_max_min_rekeys_affine_without_options_version_bump():
    """The floor is LV-only: it re-keys the affine cache (a Calibrate rebuilds
    the surface) but neither bumps the options version nor the parametric
    slice key (test_api_options.test_only_calendar_weight_bumps_version)."""
    state = AppState(reference_date=REF_DATE)
    iso = sorted(state.forwards("ALPHA"))[1].isoformat()
    v0 = state.options_version
    req = AffineFitRequest()
    affine_before = affine_key(state, "ALPHA", req)
    slice_before = fit_key(state, "ALPHA", iso, "mid")

    state.set_options(OptionsSettings(lvXMaxMin=4.0))
    assert state.options_version == v0
    assert affine_key(state, "ALPHA", req) != affine_before
    assert fit_key(state, "ALPHA", iso, "mid") == slice_before

    state.set_options(OptionsSettings(lvXMaxMin=2.5))  # back to the default
    assert state.options_version == v0
    assert affine_key(state, "ALPHA", req) == affine_before


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _lv_fit(client, ticker: str) -> dict:
    """Rebuild (the read path is frozen) and read the ticker's LV surface."""
    assert client.post(f"/calibrate/{ticker}").status_code == 200
    resp = client.post(f"/fit/affine/{ticker}", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_lv_x_max_min_widens_model_ext_right_edge_on_the_wire(client):
    """PUT lvXMaxMin=4.0 -> modelExt's right edge reaches min(K_DISPLAY_HI,
    ln 4) (the synthetic quoted range is capped at ln 2.5 ≈ 0.92 by default),
    the vertex grid is untouched and ``model`` keeps its grid exactly with the
    same values (the wider lattice only moves the far boundary)."""
    ticker = client.get("/universe").json()["tickers"][0]
    base = _lv_fit(client, ticker)
    opts = client.get("/settings/options").json()
    assert opts["lvXMaxMin"] == 2.5
    assert client.put("/settings/options", json={**opts, "lvXMaxMin": 4.0}).status_code == 200
    try:
        wide = _lv_fit(client, ticker)
    finally:
        assert client.put("/settings/options", json=opts).status_code == 200

    target = min(K_DISPLAY_HI, float(np.log(4.0))) - 0.02
    assert wide["xNodes"] == base["xNodes"] and wide["tNodes"] == base["tNodes"]
    assert len(wide["smiles"]) == len(base["smiles"]) >= 2
    for b, w in zip(base["smiles"], wide["smiles"]):
        assert w["expiry"] == b["expiry"]
        b_right = b["modelExt"][-1]["k"]
        w_right = w["modelExt"][-1]["k"]
        assert b_right <= float(np.log(2.5)) + 1e-9  # the default cap binds
        assert w_right >= target
        assert w_right > b_right + 0.05  # visibly wider than the default
        # `model` (quoted range ± pad): identical grid, identical values.
        assert [p["k"] for p in w["model"]] == [p["k"] for p in b["model"]]
        for pb, pw in zip(b["model"], w["model"]):
            assert pw["vol"] == pytest.approx(pb["vol"], abs=1e-3)
