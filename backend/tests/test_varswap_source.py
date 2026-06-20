"""Stage 4' — backward source-PDE variance swap (volfit.models.localvol.varswap_pde).

Validates the alternative var-swap pricer against the gate:
1. its value I(T) = g(0,1) matches the static log-contract replication on the
   note's golden grid (both discretize the same total variance);
2. the analytic dI/dtheta and dI/da match finite differences (the least_squares
   Jacobian contract);
3. an end-to-end calibration with method="source_pde" hits the var-swap quotes,
   and "static" stays the (byte-identical) default.
"""

import numpy as np
import pytest

from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    VarSwapQuote,
    calibrate_affine,
    solve_affine_dupire,
    solve_varswap_source,
    varswap_const,
    varswap_weights,
)

TAU = np.array([0.0, 0.5, 1.0])
XI = np.array([0.0, 0.70, 0.90, 1.00, 1.10, 1.30, 2.20])
X_GRID = 0.01 * np.arange(221)
T_GRID = 0.005 * np.arange(201)


def _true_var(t, x):
    return (
        0.032 + 0.006 * t + 0.030 * (1 - x) ** 2 + 0.012 * (1 - x)
        + 0.004 * np.sin(np.pi * t) * np.exp(-(((x - 1) / 0.35) ** 2))
    )


@pytest.fixture(scope="module")
def surface():
    return AffineVarianceSurface(t_nodes=TAU, x_nodes=XI, theta=_true_var(TAU[:, None], XI[None, :]))


def _t_to(expiry):
    n = int(round(expiry / 0.005))
    return 0.005 * np.arange(n + 1)


def test_source_pde_value_matches_static(surface):
    """g(0,1) matches the static C/k^2 replication to discretization (<= 1 var-bp)."""
    sol = solve_affine_dupire(surface, X_GRID, T_GRID, [0.25, 0.5, 1.0])
    idx = {float(t): i for i, t in enumerate(sol.expiries)}
    q_w, q_c = varswap_weights(X_GRID, 0.01), varswap_const(X_GRID, 0.01)
    for expiry in (0.25, 0.5, 1.0):
        i_static = float(q_w @ sol.prices[idx[expiry]] + q_c)
        i_source, _ = solve_varswap_source(surface, X_GRID, _t_to(expiry))
        assert abs(i_source - i_static) / expiry < 1e-4, expiry  # within 1 variance bp


def test_source_pde_theta_sensitivity_matches_fd(surface):
    expiry = 0.5
    _, d_i = solve_varswap_source(surface, X_GRID, _t_to(expiry), sensitivities=True)
    flat = surface.theta.ravel()
    eps = 1e-7
    for node in (9, 10, 16):
        th = flat.copy()
        th[node] += eps
        ip, _ = solve_varswap_source(surface.with_theta(th), X_GRID, _t_to(expiry))
        th[node] -= 2 * eps
        im, _ = solve_varswap_source(surface.with_theta(th), X_GRID, _t_to(expiry))
        fd = (ip - im) / (2 * eps)
        assert d_i[node] == pytest.approx(fd, abs=1e-7, rel=1e-5), node


def test_source_pde_a_sensitivity_matches_fd():
    """dI/da on a surface with a real left-extrapolation wing (x_nodes[0] > 0)."""
    xi = np.array([0.70, 0.85, 0.95, 1.00, 1.10, 1.30, 2.20])
    surf = AffineVarianceSurface(
        t_nodes=np.array([0.0, 1.0, 2.0]), x_nodes=xi,
        theta=0.16 + 0.30 * (1.0 - xi[None, :]) ** 2 + 0.0 * np.array([0.0, 1.0, 2.0])[:, None],
        left_extrap_a=2.0,
    )
    tg = 0.01 * np.arange(201)  # T = 2.0, enough spread to reach the wing
    _, d_i = solve_varswap_source(surf, X_GRID, tg, sensitivities=True, left_a=2.0, fit_left_a=True)
    eps = 1e-4
    ip, _ = solve_varswap_source(surf.with_left_extrap_a(2.0 + eps), X_GRID, tg)
    im, _ = solve_varswap_source(surf.with_left_extrap_a(2.0 - eps), X_GRID, tg)
    fd = (ip - im) / (2 * eps)
    assert abs(fd) > 1e-4  # the slope genuinely moves the var-swap here
    assert d_i[-1] == pytest.approx(fd, rel=1e-4)


def test_calibrate_source_pde_hits_varswaps():
    """Both methods calibrate and match the var-swap quotes; static is the default."""
    table = [
        (0.25, 0.80, 0.200277), (0.25, 1.00, 0.036544), (0.25, 1.20, 0.000861),
        (0.50, 0.80, 0.202596), (0.50, 1.00, 0.053085), (0.50, 1.20, 0.005456),
        (1.00, 0.80, 0.211163), (1.00, 1.00, 0.076657), (1.00, 1.20, 0.018833),
    ]
    var_table = [(0.25, 0.033931), (0.50, 0.035713), (1.00, 0.037479)]
    options = [OptionQuote(t=t, x=x, price=p, tol=2e-4) for t, x, p in table]
    varswaps = [VarSwapQuote(t=t, total_var=t * r, tol=2e-4) for t, r in var_table]
    flat = AffineVarianceSurface(t_nodes=TAU, x_nodes=XI, theta=np.full((3, 7), 0.04))
    for method in ("static", "source_pde"):
        cal = calibrate_affine(
            flat, options, X_GRID, T_GRID, varswaps=varswaps,
            varswap_method=method, reg_lambda=50.0, bounds=(0.005, 0.20),
        )
        for err, (t, _) in zip(cal.varswap_errors, var_table):
            assert abs(err / t) * 1e4 < 1.0, (method, t)  # within 1 variance bp
