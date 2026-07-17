"""LQD endpoint-coordinate optimization chart (symmetric-surface Phase 5).

theta = M @ phi with phi = (log A_L, log A_R, a_2..a_N): an exact linear
reparameterization of the SAME family — the fit must reach the same optimum
as the historical (L, R, a) chart, and body modes at fixed (phi_0, phi_1)
must be endpoint-neutral by construction (the decoupling that stops acute
central convexity from mechanically dragging the asymptotic wings).
"""

import numpy as np
import pytest

from volfit.models.lqd.basis import LQDParams, endpoint_scales
from volfit.models.lqd.calibrate import (
    calibrate_slice,
    endpoint_transform,
    logistic_init,
)

T = 0.5
K = np.linspace(-0.30, 0.30, 21)
W = 0.20**2 * T * (1.0 + 0.6 * K**2 - 0.12 * K)


def test_transform_is_the_exact_endpoint_chart():
    n_order = 6
    m = endpoint_transform(n_order)
    assert abs(np.linalg.det(m) - 1.0) < 1e-12  # unit-determinant linear map
    phi = np.array([-2.0, -2.4, 0.3, -0.1, 0.05, 0.02, -0.01])
    params = LQDParams.from_vector(m @ phi)
    a_left, a_right = endpoint_scales(params)
    # phi_0 / phi_1 ARE the log endpoint scales.
    assert np.log(a_left) == pytest.approx(phi[0], abs=1e-12)
    assert np.log(a_right) == pytest.approx(phi[1], abs=1e-12)


def test_body_modes_are_endpoint_neutral():
    n_order = 6
    m = endpoint_transform(n_order)
    phi = np.linalg.solve(m, logistic_init(0.02, n_order).to_vector())
    bumped = phi.copy()
    bumped[3] += 0.4  # a strong body-convexity move at fixed (phi_0, phi_1)
    base = endpoint_scales(LQDParams.from_vector(m @ phi))
    after = endpoint_scales(LQDParams.from_vector(m @ bumped))
    assert after[0] == pytest.approx(base[0], rel=1e-12)
    assert after[1] == pytest.approx(base[1], rel=1e-12)


def test_endpoint_fit_reaches_the_lr_optimum():
    """Same family, same objective, different chart: the converged parameters
    (and diagnostics) must agree with the historical chart to solver tol."""
    diag_lr: dict = {}
    diag_ep: dict = {}
    lr = calibrate_slice(K, W, t=T, solver_diag=diag_lr)
    ep = calibrate_slice(K, W, t=T, solver_diag=diag_ep, coords="endpoint")
    assert ep.success
    assert ep.params.to_vector() == pytest.approx(lr.params.to_vector(), abs=1e-5)
    assert ep.max_iv_error == pytest.approx(lr.max_iv_error, abs=1e-6)
    # The side-channel is recorded in canonical (L, R, a) coordinates: the
    # information matrices agree between charts at the shared optimum.
    info_lr = diag_lr["jac"].T @ diag_lr["jac"]
    info_ep = diag_ep["jac"].T @ diag_ep["jac"]
    assert np.max(np.abs(info_ep - info_lr)) < 1e-3 * np.abs(info_lr).max()
    assert diag_ep["theta"] == pytest.approx(diag_lr["theta"], abs=1e-5)
