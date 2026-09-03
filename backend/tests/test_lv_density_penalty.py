"""Density-smoothness penalty rows in the affine LV calibration (2026-09-03).

The affine local-variance fit rings at the vertex scale (local vol dipping to
the floor between neighbouring strike vertices) and every dip is a spike in
the Breeden-Litzenberger density d2C/dx2. The penalty adds third differences
of the lattice call prices — the density's slope — inside each expiry's
quoted window, scaled so a Gaussian slice contributes O(weight); a lattice
price is a linear functional the march already differentiates, so the
Jacobian is the same stencil on the sensitivity block (affine_calib.
density_smoothness_rows / _density_block). Measured on the SPY weekly fixture
at weight 1: converged rms 20.2 -> 18.5 bp, nfev 62 -> 43.

Locks:
  * weight 0 is byte-identical (no rows, same theta as the pre-penalty call);
  * the stencil annihilates a quadratic price profile (a constant density
    contributes nothing) and its Jacobian rows are the stencil on ``sens``;
  * the scale is maturity/lattice-invariant: a Gaussian slice costs the same
    O(1) at a 1-week and a 6-month maturity on different lattice steps;
  * the rows shrink the fitted density's slope roughness on the golden
    3-expiry problem at a sub-percent price cost, on both TRF and GN;
  * on the wire: default weight 1, LV-only cache key, fits stay arb-free and
    within 1 bp of the weight-0 fit on the clean synthetic universe.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.affine_fit import affine_key, calibrate_affine_surface
from volfit.api.schemas_affine import AffineFitRequest
from volfit.core.black import black_call
from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    calibrate_affine,
)
from volfit.models.localvol.affine_calib import _density_block, density_smoothness_rows

TAU = np.array([0.0, 0.5, 1.0])
XI = np.array([0.0, 0.70, 0.90, 1.00, 1.10, 1.30, 2.20])
X_GRID = 0.01 * np.arange(221)
T_GRID = 0.005 * np.arange(201)
QUOTE_TABLE = [
    (0.25, 0.80, 0.200277), (0.25, 0.90, 0.105645), (0.25, 1.00, 0.036544),
    (0.25, 1.10, 0.007310), (0.25, 1.20, 0.000861),
    (0.50, 0.80, 0.202596), (0.50, 0.90, 0.115765), (0.50, 1.00, 0.053085),
    (0.50, 1.10, 0.019104), (0.50, 1.20, 0.005456),
    (1.00, 0.80, 0.211163), (1.00, 0.90, 0.133968), (1.00, 1.00, 0.076657),
    (1.00, 1.10, 0.039690), (1.00, 1.20, 0.018833),
]
STD = {0.25: 0.1, 0.5: 0.14, 1.0: 0.2}  # ATM std in x (~20% vol)
REF_DATE = date(2026, 6, 10)


def _inputs():
    options = [OptionQuote(t=t, x=x, price=p, tol=2e-4) for t, x, p in QUOTE_TABLE]
    flat = AffineVarianceSurface(t_nodes=TAU, x_nodes=XI, theta=np.full((3, 7), 0.04))
    return flat, options


class _Sol:
    """Duck-typed march result for _density_block (prices + sens + expiries)."""

    def __init__(self, x, prices, sens, expiries):
        self.x_grid, self.prices, self.sens, self.expiries = x, prices, sens, expiries


def _slope_roughness(cal, i_exp: int) -> float:
    """Sum of squared third differences of the lattice prices (density slope
    energy) inside the quoted window of expiry i."""
    c = cal.solution.prices[i_exp]
    x = cal.solution.x_grid
    j = np.flatnonzero((x >= 0.75) & (x <= 1.25))
    d3 = -c[j] + 3.0 * c[j + 1] - 3.0 * c[j + 2] + c[j + 3]
    return float(np.sum(d3**2))


def test_weight_zero_is_byte_identical():
    flat, options = _inputs()
    assert density_smoothness_rows(X_GRID, options, STD, 0.0) == []
    base = calibrate_affine(flat, options, X_GRID, T_GRID, reg_lambda=50.0)
    off = calibrate_affine(
        flat, options, X_GRID, T_GRID, reg_lambda=50.0, density_weight=0.0, density_std=STD
    )
    assert np.array_equal(base.surface.theta, off.surface.theta)


def test_stencil_annihilates_quadratic_prices_and_rides_sens():
    x = X_GRID
    prices = (0.5 * (1.4 - x) ** 2)[None, :]  # constant density: quadratic in x
    sens = np.random.default_rng(3).standard_normal((1, x.size, 5))
    sol = _Sol(x, prices, sens, np.array([0.5]))
    options = [OptionQuote(t=0.5, x=xx, price=0.0) for xx in (0.8, 1.0, 1.2)]
    spec = density_smoothness_rows(x, options, STD, 1.0)
    assert len(spec) == 1 and spec[0][0] == 0.5 and spec[0][1].size > 10
    res, jac = _density_block(sol, spec, True)
    assert res.shape == (spec[0][1].size,) and jac.shape == (res.size, 5)
    assert np.max(np.abs(res)) < 1e-9 * spec[0][2]
    j = spec[0][1]
    expected = spec[0][2] * (-sens[0, j] + 3 * sens[0, j + 1] - 3 * sens[0, j + 2] + sens[0, j + 3])
    np.testing.assert_allclose(jac, expected, rtol=0, atol=1e-12 * spec[0][2])
    # Window: strictly inside the lattice, never the x = 0 boundary node.
    assert j.min() >= 1 and j.max() + 3 < x.size


@pytest.mark.parametrize("t, dx", [(1.0 / 52.0, 0.0025), (0.5, 0.01)])
def test_gaussian_slice_costs_order_one_at_any_maturity(t, dx):
    """The same Black slice priced at two maturities on two lattice steps: the
    rows' ½‖r‖² is O(1) both times (scale = √(μ·stride)·s^1.5/dx^2.5)."""
    sigma = 0.2
    x = dx * np.arange(int(round(2.5 / dx)) + 1)
    w = sigma * sigma * t
    prices = black_call(np.log(np.maximum(x, 1e-12)), w)[None, :]
    s = sigma * np.sqrt(t)
    options = [OptionQuote(t=t, x=xx, price=0.0) for xx in (1.0 - 2 * s, 1.0, 1.0 + 2 * s)]
    spec = density_smoothness_rows(x, options, {t: s}, 1.0)
    res, _ = _density_block(_Sol(x, prices, None, np.array([t])), spec, False)
    energy = 0.5 * float(res @ res)
    assert 0.01 < energy < 1.0, energy


@pytest.mark.parametrize("gn", [False, True])
def test_rows_smooth_the_fitted_density_at_sub_percent_price_cost(gn):
    flat, options = _inputs()
    kw = dict(reg_lambda=50.0, gn=gn, engine="banded")
    base = calibrate_affine(flat, options, X_GRID, T_GRID, **kw)
    pen = calibrate_affine(
        flat, options, X_GRID, T_GRID, density_weight=1.0, density_std=STD, **kw
    )
    rough_base = sum(_slope_roughness(base, i) for i in range(3))
    rough_pen = sum(_slope_roughness(pen, i) for i in range(3))
    assert rough_pen < rough_base
    assert pen.rms_price_error < 5e-3
    assert pen.diagnostics.residual_count > base.diagnostics.residual_count


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def test_default_weight_and_lv_only_cache_key(client):
    opts = client.get("/settings/options").json()
    assert opts["densitySmoothWeight"] == 1.0
    state = client.app.state.volfit
    ticker = client.get("/universe").json()["tickers"][0]
    v0 = state.options_version
    k0 = affine_key(state, ticker, AffineFitRequest())
    state.set_options(state.options().model_copy(update={"densitySmoothWeight": 0.0}))
    try:
        assert state.options_version == v0  # LV-only: no parametric refit
        assert affine_key(state, ticker, AffineFitRequest()) != k0
    finally:
        state.set_options(state.options().model_copy(update={"densitySmoothWeight": 1.0}))


def test_penalised_fit_stays_arb_free_and_close_on_the_wire(client):
    state = client.app.state.volfit
    ticker = client.get("/universe").json()["tickers"][0]
    state.set_options(state.options().model_copy(update={"densitySmoothWeight": 0.0}))
    off = calibrate_affine_surface(state, ticker, AffineFitRequest())
    state.set_options(state.options().model_copy(update={"densitySmoothWeight": 1.0}))
    on = calibrate_affine_surface(state, ticker, AffineFitRequest())
    assert on.arbitrageFree is True and on.calendarViolations == 0
    assert abs(on.surfaceRmsError - off.surfaceRmsError) * 1e4 < 1.0  # < 1 bp
    for a, b in zip(on.smiles, off.smiles):
        assert a.densityExt is not None and len(a.densityExt.x) == len(b.densityExt.x)
