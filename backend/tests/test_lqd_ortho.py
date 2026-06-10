"""ATM-orthogonal coordinates: kernel invariance and exact retargeting."""

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.models.lqd.ortho import build_atm_coordinates, handles_vector


@pytest.fixture(scope="module")
def chart():
    return build_atm_coordinates(bm.SVI_LQD_PARAMS, bm.SVI_T)


def test_jacobian_full_rank(chart):
    assert np.linalg.matrix_rank(chart.jacobian, tol=1e-10) == 3
    # U is an exact right inverse: J U = I_3.
    np.testing.assert_allclose(chart.jacobian @ chart.primary, np.eye(3), atol=1e-10)


def test_shape_directions_kill_jacobian(chart):
    """J V = 0 and V orthonormal: shape modes are ATM-neutral to first order."""
    np.testing.assert_allclose(chart.jacobian @ chart.shape, 0.0, atol=1e-9)
    np.testing.assert_allclose(chart.shape.T @ chart.shape, np.eye(4), atol=1e-12)


def test_shape_move_leaves_handles_nearly_unchanged(chart):
    """A finite shape move changes handles only at second order, while the
    matching primary move changes them at first order."""
    eps = 1e-3
    for j in range(chart.shape.shape[1]):
        params_shape = chart.theta(np.zeros(3), eps * np.eye(chart.shape.shape[1])[j])
        dh_shape = handles_vector(params_shape, chart.t) - chart.handles0
        # Second-order: O(eps^2) with a curvature-scale constant.
        assert np.max(np.abs(dh_shape)) < 50 * eps**2

    params_primary = chart.theta(np.array([eps, 0.0, 0.0]))
    dh_primary = handles_vector(params_primary, chart.t) - chart.handles0
    assert abs(dh_primary[0] - eps) < 5e-2 * eps  # first-order move of w0 by eps


def test_retarget_hits_exact_handles(chart):
    """Bump the skew handle by +0.02 and the level by +10% variance, exactly."""
    target = chart.handles0 + np.array([0.1 * chart.handles0[0], 0.02, 0.0])
    params = chart.retarget(target)
    achieved = handles_vector(params, chart.t)
    np.testing.assert_allclose(achieved, target, rtol=0, atol=1e-10)


def test_retarget_preserves_shape_coordinates(chart):
    """Retargeting with xi = 0 should not leak into shape coordinates."""
    target = chart.handles0 + np.array([0.0, 0.01, 0.0])
    params = chart.retarget(target)
    _, xi = chart.decompose(params)
    assert np.max(np.abs(xi)) < 1e-12
