"""LV var-swap rows (volfit.models.localvol.varswap_rows / volfit.api.affine_varswap):
the ATM-spread carrier for the PRIOR companion row (priorVarSwapMode="atm_spread"),
shipped for the LV surface 2026-08-27 (the "nodal-variance linearization" rider).

Locks:
* the spread row's closed-form Jacobian (dσ_vs/dθ − dσ_atm/dθ through the ATM
  Black inversion) matches finite differences of the row value under nodal bumps;
* absolute rows are EXACTLY the historical expressions (byte-identical), and the
  spread row vanishes when the model reproduces the prior's spread;
* the weight builders: ``prior_varswap_quote`` (absolute tol ζ = 2σ_vs τ VOL_TOL/√u
  unchanged; spread tol ζ_σ = VOL_TOL/√u, ``atm_spread`` = σ_vs − σ_atm), the
  prior_lv operator builder routes ``priorVarSwapMode``, and — API level — the
  LV prior targets carry the spread under the option and not otherwise.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.affine_varswap import VOL_TOL, prior_varswap_quote, prior_varswap_quote_from_smile
from volfit.api.prior_lv import build_operator_lv_targets
from volfit.api.schemas import OptionsSettings
from volfit.calib.operators import VarSwapPriorRec
from volfit.calib.varswap import varswap_total_variance
from volfit.models.localvol import AffineVarianceSurface, VarSwapQuote, solve_affine_dupire
from volfit.models.localvol.varswap_rows import (
    atm_index,
    spread_row_values,
    varswap_const,
    varswap_residual_rows,
    varswap_weights,
)

REF_DATE = date(2026, 6, 10)

# --- the note's 3x7 surface (test_localvol_affine) ---------------------------
TAU = np.array([0.0, 0.5, 1.0])
XI = np.array([0.0, 0.70, 0.90, 1.00, 1.10, 1.30, 2.20])
X_GRID = 0.01 * np.arange(221)
T_GRID = 0.005 * np.arange(201)
EXPIRIES = [0.5, 1.0]


def _true_variance(t, x):
    return (
        0.032 + 0.006 * t + 0.030 * (1.0 - x) ** 2 + 0.012 * (1.0 - x)
        + 0.004 * np.sin(np.pi * t) * np.exp(-(((x - 1.0) / 0.35) ** 2))
    )


def _surface():
    return AffineVarianceSurface(
        t_nodes=TAU, x_nodes=XI, theta=_true_variance(TAU[:, None], XI[None, :])
    )


def _block(surf, theta_flat, quotes, z_mkt, zeta):
    """Var-swap residual block (values + Jacobian) at ``theta_flat``."""
    sol = solve_affine_dupire(surf.with_theta(theta_flat), X_GRID, T_GRID, EXPIRIES, sensitivities=True)
    idx = {float(t): i for i, t in enumerate(sol.expiries)}
    q, c = varswap_weights(X_GRID, 0.01), varswap_const(X_GRID, 0.01)
    z = np.array([q @ sol.prices[idx[v.t]] + c for v in quotes])
    jz = np.vstack([q @ sol.sens[idx[v.t]] for v in quotes])
    res, jac = varswap_residual_rows(quotes, z, jz, z_mkt, zeta, sol, atm_index(X_GRID))
    return res, jac, z, jz


def test_spread_row_jacobian_matches_finite_differences():
    """Row 0 is a SPREAD row (t = 1), row 1 an ABSOLUTE row (t = 0.5): the block's
    analytic Jacobian matches central differences of the block values."""
    surf = _surface()
    quotes = [
        VarSwapQuote(t=1.0, total_var=0.0375, tol=0.01, atm_spread=0.002),
        VarSwapQuote(t=0.5, total_var=0.0179, tol=2e-4),
    ]
    z_mkt = np.array([v.total_var for v in quotes])
    zeta = np.array([v.tol for v in quotes])
    th0 = surf.theta.ravel()
    res0, jac0, z0, jz0 = _block(surf, th0, quotes, z_mkt, zeta)
    assert res0.shape == (2,) and jac0.shape == (2, th0.size)
    # the absolute row is exactly the historical expression (byte-identical)
    assert res0[1] == (z0[1] - z_mkt[1]) / zeta[1]
    assert np.array_equal(jac0[1], jz0[1] / zeta[1])
    rng = np.random.default_rng(3)
    # Central differences of the Dupire march: the FD error is round-off
    # dominated below ~1e-5 (measured 1.6e-5 rel at 1e-4, 8e-4 at 1e-6, 1.8e-3
    # at 1e-7 — identical on the raw march sensitivity jz, so it is the FD,
    # not the row), hence the coarse step.
    eps = 1e-4
    for node in rng.choice(th0.size, size=4, replace=False):
        up, dn = th0.copy(), th0.copy()
        up[node] += eps
        dn[node] -= eps
        fd = (_block(surf, up, quotes, z_mkt, zeta)[0] - _block(surf, dn, quotes, z_mkt, zeta)[0]) / (2 * eps)
        assert jac0[:, node] == pytest.approx(fd, rel=1e-4, abs=1e-6), int(node)


def test_spread_row_vanishes_when_model_reproduces_the_prior_spread():
    """With ``atm_spread`` = the surface's own σ_vs − σ_atm the spread row is zero
    even though the absolute level target is deliberately wrong."""
    surf = _surface()
    sol = solve_affine_dupire(surf, X_GRID, T_GRID, EXPIRIES, sensitivities=True)
    i_atm, e = atm_index(X_GRID), 1  # t = 1.0
    q, c = varswap_weights(X_GRID, 0.01), varswap_const(X_GRID, 0.01)
    z = float(q @ sol.prices[e] + c)
    from volfit.core.black import atm_total_variance

    sigma_vs = np.sqrt(z / 1.0)
    sigma_atm = np.sqrt(atm_total_variance(float(sol.prices[e][i_atm])) / 1.0)
    value, row = spread_row_values(
        z, q @ sol.sens[e], float(sol.prices[e][i_atm]), sol.sens[e][i_atm], 1.0,
        float(sigma_vs - sigma_atm), 0.01,
    )
    assert value == pytest.approx(0.0, abs=1e-12)
    assert np.all(np.isfinite(row)) and np.any(row != 0.0)
    # the same quote with a wrong LEVEL still has a zero spread residual
    quotes = [VarSwapQuote(t=1.0, total_var=9.0 * z, tol=0.01, atm_spread=float(sigma_vs - sigma_atm))]
    res, _ = varswap_residual_rows(
        quotes, np.array([z]), (q @ sol.sens[e])[None, :], np.array([9.0 * z]),
        np.array([0.01]), sol, i_atm,
    )
    assert res[0] == pytest.approx(0.0, abs=1e-12)


# ------------------------------------------------------------ the builders
T = 0.5


def prior_w(k):
    k = np.asarray(k, dtype=float)
    sig = 0.25 - 0.45 * k
    return sig * sig * T


def test_prior_varswap_quote_carriers():
    w_vs, u = 0.032, 7.0
    sigma_vs = np.sqrt(w_vs / T)
    absolute = prior_varswap_quote(w_vs, T, u)
    assert absolute.atm_spread is None
    assert absolute.tol == 2.0 * sigma_vs * T * VOL_TOL / np.sqrt(u)  # the historical ζ
    w_atm = 0.5 * 0.25 * 0.25  # σ_atm = 25 %
    spread = prior_varswap_quote(w_vs, T, u, w_atm)
    assert spread.total_var == absolute.total_var and spread.t == T
    assert spread.tol == pytest.approx(VOL_TOL / np.sqrt(u))
    assert spread.atm_spread == pytest.approx(sigma_vs - 0.25)


def test_prior_varswap_quote_from_smile_rescales_like_the_level():
    tau, u = 0.8, 3.0
    absolute = prior_varswap_quote_from_smile(prior_w, T, tau, u, "absolute")
    spread = prior_varswap_quote_from_smile(prior_w, T, tau, u, "atm_spread")
    w_vs = varswap_total_variance(prior_w) * (tau / T)
    assert absolute.total_var == w_vs and absolute.atm_spread is None
    assert spread.total_var == w_vs
    # the rescale cancels in vol space: σ_atm at tau equals the prior's own ATM vol
    sigma_atm = np.sqrt(prior_w(np.array([0.0]))[0] / T)
    assert spread.atm_spread == pytest.approx(np.sqrt(w_vs / tau) - sigma_atm)


def test_operator_lv_builder_routes_the_carrier_option():
    """ATM-only quotes leave the var-swap operator under-observed (active rec);
    the LV quote is absolute by default and the spread carrier under the option."""
    k = np.array([-0.01, 0.0, 0.01])
    opts = OptionsSettings(priorOperatorBandwidth=0.03)
    _, vs_abs = build_operator_lv_targets(prior_w, T, T, k, None, opts)
    _, vs_spr = build_operator_lv_targets(
        prior_w, T, T, k, None, opts.model_copy(update={"priorVarSwapMode": "atm_spread"})
    )
    assert len(vs_abs) == 1 and vs_abs[0].atm_spread is None
    assert len(vs_spr) == 1 and vs_spr[0].atm_spread is not None
    assert vs_spr[0].total_var == vs_abs[0].total_var
    sigma_vs = np.sqrt(vs_abs[0].total_var / T)
    sigma_atm = np.sqrt(prior_w(np.array([0.0]))[0] / T)
    assert vs_spr[0].atm_spread == pytest.approx(sigma_vs - sigma_atm)
    # same weight u under both carriers: ζ_σ = ζ / (2 σ_vs τ)
    assert vs_spr[0].tol == pytest.approx(vs_abs[0].tol / (2.0 * sigma_vs * T))


# ------------------------------------------------------------------ API
def _put_options(client, **updates):
    options = client.get("/settings/options").json()
    options.update(updates)
    assert client.put("/settings/options", json=options).status_code == 200
    return options


def test_api_lv_prior_varswap_row_carries_the_spread(monkeypatch):
    """With a fetched prior and priorVarSwapMode="atm_spread", the LV prior
    targets' var-swap rows carry ``atm_spread``; back to "absolute" they do not.
    The var-swap rec is forced ACTIVE (the carrier, not the coverage gate, is
    under test — a densely quoted synthetic chain may observe the level)."""
    import volfit.api.prior_lv as prior_lv

    real = prior_lv.build_operator_prior

    def forced(prior_w_, prior_tau, tau, *args, **kwargs):
        target, vs = real(prior_w_, prior_tau, tau, *args, **kwargs)
        if not vs.active:
            w_vs = varswap_total_variance(prior_w_) * (tau / prior_tau)
            vs = VarSwapPriorRec(active=True, prior_total_var=w_vs, weight=5.0, gap=1.0)
        return target, vs

    monkeypatch.setattr(prior_lv, "build_operator_prior", forced)
    app = create_app(reference_date=REF_DATE)
    with TestClient(app) as client:
        ticker = client.get("/universe").json()["tickers"][0]
        expiry = client.get(f"/forwards/{ticker}").json()["entries"][1]["expiry"]
        client.get(f"/smiles/{ticker}/{expiry}")  # ensure a calibrated node
        assert client.post("/priors/save-all").status_code == 200
        assert client.post("/priors/fetch").status_code == 200
        _put_options(
            client,
            priorPersistenceMode="quote_operator",
            priorOperatorSet=["ATM", "RR25", "BF25", "VarSwap"],
            priorVarSwapMode="atm_spread",
        )
        from volfit.api import affine_fit

        state = app.state.volfit
        rows = affine_fit._gather(state, ticker, "mid")
        _, _, vs_spread = affine_fit._prior_lv_targets(state, ticker, rows)
        assert vs_spread, "the forced-active var-swap rec must reach the LV targets"
        assert all(v.atm_spread is not None and v.tol > 0.0 for v in vs_spread)

        _put_options(client, priorVarSwapMode="absolute")
        _, _, vs_abs = affine_fit._prior_lv_targets(state, ticker, rows)
        assert vs_abs and all(v.atm_spread is None for v in vs_abs)
        assert [v.total_var for v in vs_abs] == [v.total_var for v in vs_spread]
