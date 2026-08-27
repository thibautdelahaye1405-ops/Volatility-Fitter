"""LV-affine robust IRLS (volfit.models.localvol.affine_robust) — the original LV
fix-order #3, shipped 2026-08-27: FitSettings.robustLoss huber|cauchy for the
local-vol surface, as two warm-started re-solves with the quote tolerances
scaled by 1/sqrt(m_i) (m_i from calib.band.robust_multipliers on the per-quote
UNWEIGHTED vol-unit magnitude).

Locks:
* ``robust_loss="off"`` is byte-identical to a direct ``calibrate_affine`` call;
* one +10 vol-pt outlier: huber IRLS lowers the RMS on the CLEAN quotes vs the
  plain fit and leaves the outlier's own residual larger (it is down-weighted,
  not fitted); the pass count shows in ``n_evals``;
* the multiplier helper reuses the parametric formulas; the magnitude scale is
  the quote's own 1/vega (vol units).
"""

import numpy as np
import pytest

from volfit.calib.band import robust_multipliers
from volfit.core.black import black_call, black_vega_sigma, implied_total_variance
from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    calibrate_affine,
    solve_affine_dupire,
)
from volfit.models.localvol.affine_robust import (
    calibrate_affine_robust,
    irls_multipliers,
    option_block_magnitudes,
    quote_inv_vega,
    reweighted_quotes,
)

VOL_TOL = 0.01
T_NODES = np.linspace(0.0, 1.0, 5)
X_NODES = np.linspace(0.7, 1.3, 9)
X_GRID = 0.01 * np.arange(221)
T_GRID = 0.01 * np.arange(101)
EXPIRIES = [0.25, 0.5, 0.75, 1.0]
STRIKES = np.linspace(0.8, 1.2, 9)
OUTLIER = (0.5, 1.05)  # (t, x) of the quote bumped by +10 vol points
REF = np.full(T_NODES.size * X_NODES.size, 0.04)


def _case():
    """Vega-scaled quotes (tol = vega·VOL_TOL, the API convention) from a smooth
    surface, with ONE quote's implied vol bumped by +10 vol points."""
    tt, xx = np.meshgrid(T_NODES, X_NODES, indexing="ij")
    theta = 0.04 + 0.01 * tt + 0.03 * (1.0 - xx) ** 2 + 0.01 * (1.0 - xx)
    surf = AffineVarianceSurface(t_nodes=T_NODES, x_nodes=X_NODES, theta=theta)
    sol = solve_affine_dupire(surf, X_GRID, T_GRID, EXPIRIES)
    idx = {float(e): i for i, e in enumerate(sol.expiries)}
    options, clean_prices, i_out = [], [], None
    for e in EXPIRIES:
        for x in STRIKES:
            k = float(np.log(x))
            p_clean = float(sol.price_at(idx[float(e)], x))
            w = float(implied_total_variance(k, p_clean))
            sigma = np.sqrt(w / e)
            p = p_clean
            if (float(e), float(x)) == OUTLIER:
                i_out = len(options)
                sigma = sigma + 0.10
                p = float(black_call(k, sigma * sigma * e))
            vega = float(black_vega_sigma(k, sigma, e))
            options.append(OptionQuote(t=float(e), x=float(x), price=p, tol=vega * VOL_TOL))
            clean_prices.append(p_clean)
    flat = AffineVarianceSurface(
        t_nodes=T_NODES, x_nodes=X_NODES, theta=np.full((T_NODES.size, X_NODES.size), 0.04)
    )
    return flat, options, np.array(clean_prices), i_out


KW = dict(reg_lambda=50.0, bounds=(0.005, 0.20), theta_ref=REF)


def test_off_is_byte_identical_to_calibrate_affine():
    flat, options, _, _ = _case()
    plain = calibrate_affine(flat, options, X_GRID, T_GRID, **KW)
    off = calibrate_affine_robust(flat, options, X_GRID, T_GRID, robust_loss="off", **KW)
    assert np.array_equal(off.surface.theta, plain.surface.theta)
    assert off.n_evals == plain.n_evals
    assert np.array_equal(off.option_prices, plain.option_prices)


def test_huber_irls_downweights_the_outlier():
    flat, options, clean, i_out = _case()
    assert i_out is not None
    plain = calibrate_affine(flat, options, X_GRID, T_GRID, **KW)
    robust = calibrate_affine_robust(
        flat, options, X_GRID, T_GRID, robust_loss="huber", robust_f_scale=0.005, **KW
    )
    inv_vega = quote_inv_vega(options)
    mask = np.ones(len(options), dtype=bool)
    mask[i_out] = False
    # vol-unit errors against the CLEAN (true) prices on the clean quotes
    err_plain = np.abs(plain.option_prices - clean) * inv_vega
    err_robust = np.abs(robust.option_prices - clean) * inv_vega
    rms_plain = float(np.sqrt(np.mean(err_plain[mask] ** 2)))
    rms_robust = float(np.sqrt(np.mean(err_robust[mask] ** 2)))
    assert rms_robust < rms_plain
    # the outlier is down-weighted, not fitted: its own residual grows
    quoted = np.array([o.price for o in options])
    assert abs(robust.option_prices[i_out] - quoted[i_out]) > abs(plain.option_prices[i_out] - quoted[i_out])
    # two warm-started passes ride on top of the base solve
    assert robust.n_evals > plain.n_evals
    # the reported errors stay the raw per-quote price residuals (no weights leak)
    assert np.allclose(robust.option_errors, robust.option_prices - quoted)


def test_multipliers_and_magnitudes_are_the_parametric_conventions():
    flat, options, _, i_out = _case()
    plain = calibrate_affine(flat, options, X_GRID, T_GRID, **KW)
    mag = option_block_magnitudes(plain, options, 0.0)
    # mid mode: |P_model − P_mid| / vega (vol units) — the outlier is several vol points
    quoted = np.array([o.price for o in options])
    assert np.allclose(mag, np.abs(plain.option_prices - quoted) * quote_inv_vega(options))
    assert mag[i_out] > 0.02 and mag[i_out] == mag.max()
    m = irls_multipliers(mag, "huber", 0.005)
    assert np.array_equal(m, robust_multipliers(mag, "huber", 0.005))  # reused, not duplicated
    assert m[i_out] < 0.25 and m.max() <= 1.0
    assert np.array_equal(irls_multipliers(mag, "off", 0.005), np.ones_like(mag))
    # tol_i / sqrt(m_i): the squared residual then carries m_i
    rw = reweighted_quotes(options, m)
    for o, r, mi in zip(options, rw, m):
        assert r.tol == pytest.approx(o.tol / np.sqrt(mi))
        assert r.price == o.price and r.x == o.x and r.t == o.t
