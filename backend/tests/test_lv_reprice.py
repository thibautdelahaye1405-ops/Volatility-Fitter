"""Converged-operator LV reprice (models.localvol.reprice) — the honest metric.

R0 item 2 of the forward roadmap (the fix-#3 lesson): in-operator residuals are
blind to time-discretization error because the optimizer bends theta to cancel
it, so the quality metric must reprice the CALIBRATED surface on a refined
operator. Contracts locked here:

  * on the SAME grid the value-only reprice reproduces solve_affine_dupire's
    implicit value march bit-for-bit (flat and left-sloped surfaces);
  * refined_grids subdivides every calibration step and keeps every quoted
    expiry exactly on a time node (and x = 1 on the strike lattice);
  * on a flat surface the refined march approaches the analytic Black value
    while a 1-step march is off by hundreds of bp (the fix-#3 mechanism);
  * _fit reports rmsConvergedBp ≈ in-operator rms when the operator is
    converged, and EXPOSES the compensation when the operator is artificially
    coarsened — in-operator rms stays flattering, the converged rms does not.
"""

from datetime import date

import numpy as np
import pytest

from volfit.core.black import implied_total_variance
from volfit.models.localvol.affine import (
    AffineVarianceSurface,
    solve_affine_dupire,
)
from volfit.models.localvol.reprice import refined_grids, reprice_affine_dupire

REF_DATE = date(2026, 6, 10)


def _surface(a: float = 0.0) -> AffineVarianceSurface:
    t_nodes = np.array([0.02, 0.5, 1.0])
    x_nodes = np.array([0.6, 0.9, 1.0, 1.1, 1.6])
    theta = 0.04 * (1.0 + 0.3 * np.linspace(-1, 1, 5))[None, :] * np.array(
        [1.2, 1.0, 0.9]
    )[:, None]
    return AffineVarianceSurface(
        t_nodes=t_nodes, x_nodes=x_nodes, theta=theta, left_extrap_a=a
    )


def _grids(expiries, dt: float = 0.01, dx: float = 0.01):
    x = dx * np.arange(int(np.ceil(2.5 / dx)) + 1)
    pts, prev = [0.0], 0.0
    for e in expiries:
        n = max(1, int(np.ceil((e - prev) / dt)))
        pts.extend(np.linspace(prev, e, n + 1)[1:].tolist())
        prev = e
    return x, np.array(pts)


# ----------------------------------------------------------------- parity
@pytest.mark.parametrize("left_a", [0.0, 1.3])
def test_reprice_matches_solver_value_path_bitwise(left_a):
    surface = _surface(left_a)
    exps = [0.25, 1.0]
    x, t = _grids(exps)
    ref = solve_affine_dupire(surface, x, t, exps, sensitivities=False)
    got = reprice_affine_dupire(surface, x, t, exps)
    assert np.array_equal(got.prices, ref.prices)
    assert np.array_equal(got.expiries, ref.expiries)


# ----------------------------------------------------------------- grids
def test_refined_grids_subdivide_every_step_and_keep_nodes():
    exps = [7.0 / 365.0, 0.25]
    x, t = _grids(exps)
    x_f, t_f = refined_grids(x, t)
    assert x_f.size == 2 * (x.size - 1) + 1
    assert t_f.size == 4 * (t.size - 1) + 1
    assert np.isclose(x_f, 1.0).any()  # x = 1 stays on the lattice
    for e in exps:  # every quoted expiry stays a time node
        assert np.isclose(t_f, e).any()
    # every original node survives (pure subdivision, no re-gridding)
    assert np.allclose(t_f[::4], t)


# ----------------------------------------------------- operator convergence
def test_refined_march_approaches_black_where_coarse_is_way_off():
    """Flat variance: the PDE truth is Black. One implicit step to a weekly
    mis-prices the ATM by hundreds of bp of IV; the refined march closes in."""
    sigma2 = 0.13**2
    t1 = 7.0 / 365.0
    surface = AffineVarianceSurface(
        t_nodes=np.array([0.001, 1.0]),
        x_nodes=np.array([0.5, 1.5]),
        theta=np.full((2, 2), sigma2),
    )
    x, _ = _grids([t1], dx=0.005)
    t_coarse = np.array([0.0, t1])  # ONE implicit-Euler step

    def atm_iv(sol) -> float:
        k = np.array([0.0])
        w = implied_total_variance(k, sol.price_at(0, np.exp(k)))
        return float(np.sqrt(w[0] / t1))

    iv_coarse = atm_iv(reprice_affine_dupire(surface, x, t_coarse, [t1]))
    x_f, t_f = refined_grids(x, t_coarse, dt_factor=64)
    iv_conv = atm_iv(reprice_affine_dupire(surface, x_f, t_f, [t1]))
    truth = np.sqrt(sigma2)
    assert abs(iv_coarse - truth) * 1e4 > 100.0  # the fix-#3 pathology
    assert abs(iv_conv - truth) * 1e4 < 10.0  # refined march ~ Black


# ------------------------------------------------------------- fit metric
def test_fit_reports_converged_metric_and_reveals_front_operator_error():
    from volfit.api import affine_fit
    from volfit.api.schemas_affine import AffineFitRequest
    from volfit.api.state import AppState

    state = AppState(REF_DATE)
    resp = affine_fit._fit(state, "ALPHA", AffineFitRequest())
    assert resp.rmsConvergedBp > 0.0
    assert resp.maxConvergedBp >= resp.rmsConvergedBp
    assert all(s.rmsConvergedBp >= 0.0 for s in resp.smiles)
    # The metric's FIRST CATCH (2026-07-10): even the post-fix-#3 calibration
    # operator leaves ~100 bp of dt error at a ~30d front expiry (9 steps just
    # clears the gate of 8; decomposition: dt x4 alone = 93 of the 103 bp,
    # dx x2 alone = 7 bp) which the optimizer absorbs into theta — the
    # in-operator rms reads ~0.01 bp. The honest reprice reveals it, front-
    # loaded and decaying with maturity. Tightening the operator (raising the
    # fix-#3 gate / extending refinement past the first expiry) is the
    # follow-up; THIS metric is its acceptance criterion.
    assert resp.rmsConvergedBp > resp.rmsIvErrorBp
    assert resp.smiles[0].rmsConvergedBp > 5.0 * resp.smiles[-1].rmsConvergedBp


def test_fit_exposes_operator_compensation_on_coarse_march(monkeypatch):
    """THE blindness test: force a 1-step-per-interval calibration march (fix #3
    gated off). The optimizer compensates, so the in-operator rms stays
    flattering — the converged reprice reveals the real error."""
    from volfit.api import affine_fit
    from volfit.api.schemas_affine import AffineFitRequest
    from volfit.api.state import AppState

    monkeypatch.setattr(affine_fit, "_DT_MAX", 10.0)  # 1 implicit step / interval
    monkeypatch.setattr(affine_fit, "_PDE_NT_FIRST_GATE", 0)  # fix #3 off
    state = AppState(REF_DATE)
    resp = affine_fit._fit(state, "ALPHA", AffineFitRequest())
    assert resp.rmsConvergedBp > 2.0 * resp.rmsIvErrorBp
    assert resp.rmsConvergedBp > 20.0  # material hidden error, in bp
