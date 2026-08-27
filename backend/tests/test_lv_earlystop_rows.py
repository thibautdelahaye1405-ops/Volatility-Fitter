"""Stage 8 early stop — the stall block is EVERY data row (2026-08-27 fix).

``calibrate_affine(stall_window > 0)`` stops once the tracked misfit stalls and
returns the best iterate. The tracked block used to be the OPTION rows only, so
a warm-started fit whose options already fit stalled at its START point without
ever moving toward a var-swap quote: the LV var-swap row was inert under
``lvEarlyStop`` (measured live: soft 10 %, soft 50 % and hard pin all returned
the model unchanged). The block is now the whole data prefix — options +
var-swaps + baskets (volfit.models.localvol.affine_stall).

Locks:
* ``stall_block_size`` returns exactly the option-block length when there are no
  extra rows — and a fit without var-swap / basket rows is byte-identical to one
  run with the pre-fix (option-only) block;
* the regression itself: warm start at the option optimum + a stiff var-swap
  quote; with the pre-fix block the early-stopped fit returns the start point
  (the inertness), with the fixed block it honours the row.
"""

import numpy as np
import pytest

import volfit.models.localvol.affine_calib as ac
from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    VarSwapQuote,
    calibrate_affine,
    solve_affine_dupire,
    varswap_const,
    varswap_weights,
)
from volfit.models.localvol.affine_stall import stall_block_size, stall_metric


def test_stall_block_is_the_whole_data_prefix():
    assert stall_block_size(15, 0, 0) == 15  # no extra rows: the historical option block
    assert stall_block_size(30, 3, 0) == 33  # band mode (2 rows/quote) + 3 var-swaps
    assert stall_block_size(15, 3, 4) == 22  # + 4 operator baskets
    assert stall_block_size(0, 0, 0) == 0


def test_stall_metric_is_the_block_rms():
    r = np.array([3.0, 4.0, 100.0])
    assert stall_metric(r, 2) == pytest.approx(np.sqrt(12.5))
    assert stall_metric(r, 0) == pytest.approx(np.sqrt(np.mean(r * r)))  # 0 -> whole vector


# ----------------------------------------------------------------- fixture
T_NODES = np.linspace(0.0, 1.0, 5)
X_NODES = np.linspace(0.7, 1.3, 9)
X_GRID = 0.01 * np.arange(221)
T_GRID = 0.01 * np.arange(101)
EXPIRIES = [0.25, 0.5, 0.75, 1.0]
STRIKES = np.linspace(0.8, 1.2, 7)
REF = np.full(T_NODES.size * X_NODES.size, 0.04)


def _case():
    """Self-consistent quotes from a smooth 5x9 surface (no noise, so the option
    block has a clean optimum the warm start can sit on)."""
    tt, xx = np.meshgrid(T_NODES, X_NODES, indexing="ij")
    theta = 0.04 + 0.01 * tt + 0.03 * (1.0 - xx) ** 2 + 0.01 * (1.0 - xx)
    surf = AffineVarianceSurface(t_nodes=T_NODES, x_nodes=X_NODES, theta=theta)
    sol = solve_affine_dupire(surf, X_GRID, T_GRID, EXPIRIES)
    idx = {float(e): i for i, e in enumerate(sol.expiries)}
    options = [
        OptionQuote(t=float(e), x=float(x), price=float(sol.price_at(idx[float(e)], x)), tol=2e-4)
        for e in EXPIRIES for x in STRIKES
    ]
    flat = AffineVarianceSurface(
        t_nodes=T_NODES, x_nodes=X_NODES, theta=np.full((T_NODES.size, X_NODES.size), 0.04)
    )
    return flat, options


def _option_only_block(n_opt_rows, n_varswaps, n_baskets):
    """The pre-2026-08-27 stall block: option rows only."""
    return n_opt_rows


def test_no_extra_rows_is_byte_identical_to_the_option_only_block(monkeypatch):
    """Without var-swap / basket rows the fixed block IS the option block, so the
    early-stopped fit is byte-identical to one run with the pre-fix criterion."""
    flat, options = _case()
    kw = dict(
        reg_lambda=50.0, bounds=(0.005, 0.20), theta_ref=REF,
        stall_window=6, stall_rtol=1e-3, xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=60,
    )
    fixed = calibrate_affine(flat, options, X_GRID, T_GRID, **kw)
    monkeypatch.setattr(ac, "stall_block_size", _option_only_block)
    legacy = calibrate_affine(flat, options, X_GRID, T_GRID, **kw)
    assert np.array_equal(fixed.surface.theta, legacy.surface.theta)
    assert fixed.n_evals == legacy.n_evals
    assert fixed.diagnostics.status == legacy.diagnostics.status


def test_varswap_row_is_not_inert_under_early_stop(monkeypatch):
    """Warm start at the option optimum + a stiff var-swap quote 5 vol pts above
    the model: the pre-fix (option-only) block stalls immediately and hands back
    the START point; the data-block criterion keeps the fit moving until the
    var-swap row is honoured."""
    flat, options = _case()
    kw = dict(reg_lambda=50.0, bounds=(0.005, 0.20), theta_ref=REF)
    base = calibrate_affine(flat, options, X_GRID, T_GRID, **kw)  # the option optimum
    warm = base.surface
    t = 1.0
    idx = {float(e): i for i, e in enumerate(base.solution.expiries)}
    q, c = varswap_weights(X_GRID, 0.01), varswap_const(X_GRID, 0.01)
    z_model = float(q @ base.solution.prices[idx[t]] + c)
    sigma_model = np.sqrt(z_model / t)
    z_mkt = (sigma_model + 0.05) ** 2 * t
    # a pin-like tolerance (the hard-pin idiom): the row must win against the options
    vs = [VarSwapQuote(t=t, total_var=float(z_mkt), tol=1e-6)]
    start_err = z_model - z_mkt
    # Tight scipy tolerances so the stall window — not ftol/xtol — is the binding
    # terminator on both paths (the idiom of test_affine_early_stop).
    stall_kw = dict(
        kw, varswaps=vs, stall_window=6, stall_rtol=5e-3,
        xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=200,
    )

    fixed = calibrate_affine(warm, options, X_GRID, T_GRID, **stall_kw)
    monkeypatch.setattr(ac, "stall_block_size", _option_only_block)
    legacy = calibrate_affine(warm, options, X_GRID, T_GRID, **stall_kw)

    # the inertness: the option block cannot improve from its optimum, so the
    # option-only criterion stalls and returns the warm-start surface verbatim
    assert legacy.diagnostics.status == 99
    assert np.array_equal(legacy.surface.theta, warm.theta)
    assert abs(legacy.varswap_errors[0]) == pytest.approx(abs(start_err), rel=1e-9)
    # the fix: the var-swap row is in the tracked block, so the fit moves toward it
    assert not np.array_equal(fixed.surface.theta, warm.theta)
    assert abs(fixed.varswap_errors[0]) < 0.2 * abs(start_err)
    assert np.sqrt(fixed.varswap_totals[0] / t) > sigma_model + 0.03  # toward the +5 vol quote
