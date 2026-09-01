"""Exact-equality locks for the 2026-09 calibration-perf batchings.

The perf arc replaced per-point / per-row / per-core numpy dispatches in the
calibration hot paths with batched evaluations of the SAME elementwise
operations, and scipy's uniform-step cumulative Simpson with a compiled
replica of its exact arithmetic. None of these are gated behind a toggle
precisely because they are bit-identical; this suite pins that contract
directly (the golden fit suites lock it end-to-end):

  * volfit.core.cumsimp vs scipy.integrate.cumulative_simpson;
  * hermite_eval_rows vs a per-row hermite_eval loop;
  * the single-dispatch hat stencils (hat / hat_p / hat_pp) vs the
    historical separate-call formulas;
  * the cross-core batched _model_v_grad / _eval_v vs the historical
    per-core implementations (reproduced verbatim below as references).
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.integrate import cumulative_simpson

from volfit.core import cumsimp
from volfit.models.lqd.interp import hermite_eval, hermite_eval_rows
from volfit.models.sigmoid.jacobian import _base_grad, _model_v_grad
from volfit.models.sigmoid.kernels import hat, hat_p, hat_pp, phi, phi_p, phi_pp
from volfit.models.sigmoid.seeding import _eval_v

rng = np.random.default_rng(20260902)


# ------------------------------------------------------------------ cumsimp
@pytest.mark.parametrize("shape", [(1, 3), (2, 4), (3, 5), (7, 50), (5, 2001)])
def test_cumsimp_matches_scipy_2d(shape):
    y = rng.standard_normal(shape)
    ours = cumsimp.cumulative_simpson_uniform(y, dx=0.037, initial=0.0)
    ref = cumulative_simpson(y, dx=0.037, initial=0.0)
    assert np.array_equal(ours, ref)


@pytest.mark.parametrize("m", [3, 4, 401, 2001, 8001])
def test_cumsimp_matches_scipy_1d(m):
    y = rng.standard_normal(m)
    ours = cumsimp.cumulative_simpson_uniform(y, dx=0.01, initial=0.0)
    ref = cumulative_simpson(y, dx=0.01, initial=0.0)
    assert ours.shape == ref.shape
    assert np.array_equal(ours, ref)


def test_cumsimp_matches_scipy_on_reversed_view():
    """The asset-share pass integrates a [:, ::-1] view — strides included."""
    y = rng.standard_normal((6, 301))
    view = y[:, ::-1]
    ours = cumsimp.cumulative_simpson_uniform(view, dx=0.2, initial=0.0)[:, ::-1]
    ref = np.array(
        [cumulative_simpson(row[::-1], dx=0.2, initial=0.0)[::-1] for row in y]
    )
    assert np.array_equal(ours, ref)


def test_cumsimp_delegates_outside_the_fast_path(monkeypatch):
    """No numba, < 3 samples, or a non-zero initial all fall through to scipy."""
    y = rng.standard_normal((4, 101))
    monkeypatch.setattr(cumsimp, "_HAVE_NUMBA", False)
    assert np.array_equal(
        cumsimp.cumulative_simpson_uniform(y, dx=0.5, initial=0.0),
        cumulative_simpson(y, dx=0.5, initial=0.0),
    )
    monkeypatch.undo()
    short = rng.standard_normal(2)
    assert np.array_equal(
        cumsimp.cumulative_simpson_uniform(short, dx=0.5, initial=0.0),
        cumulative_simpson(short, dx=0.5, initial=0.0),
    )
    assert np.array_equal(
        cumsimp.cumulative_simpson_uniform(y, dx=0.5, initial=1.25),
        cumulative_simpson(y, dx=0.5, initial=1.25),
    )


# --------------------------------------------------------- hermite_eval_rows
def test_hermite_eval_rows_matches_per_row_loop():
    p, m = 19, 2001
    vals = rng.standard_normal((p, m))
    ders = rng.standard_normal((p, m))
    x0, step = -40.0, 80.0 / (m - 1)
    x = rng.uniform(-45.0, 45.0, 87)  # includes out-of-range clamped queries
    rows = hermite_eval_rows(x, x0, step, vals, ders)
    ref = np.array([hermite_eval(x, x0, step, vals[j], ders[j]) for j in range(p)])
    assert np.array_equal(rows, ref)


# ------------------------------------------------------------- hat stencils
def _ref_hat(z, c, h, kappa):
    u = np.asarray(z, dtype=float) - c
    raw = phi(u - h, kappa) - 2.0 * phi(u, kappa) + phi(u + h, kappa)
    return raw / float(2.0 * phi(h, kappa))


def _ref_hat_p(z, c, h, kappa):
    u = np.asarray(z, dtype=float) - c
    raw = phi_p(u - h, kappa) - 2.0 * phi_p(u, kappa) + phi_p(u + h, kappa)
    return raw / float(2.0 * phi(h, kappa))


def _ref_hat_pp(z, c, h, kappa):
    u = np.asarray(z, dtype=float) - c
    raw = phi_pp(u - h, kappa) - 2.0 * phi_pp(u, kappa) + phi_pp(u + h, kappa)
    return raw / float(2.0 * phi(h, kappa))


def test_hat_stencils_match_separate_calls():
    z = rng.uniform(-3.0, 3.0, 64)
    for c, h, kappa in [(0.1, 0.4, 5.0), (-0.7, 0.15, 1.0), (1.3, 1.5, 12.0)]:
        assert np.array_equal(hat(z, c, h, kappa), _ref_hat(z, c, h, kappa))
        assert np.array_equal(hat_p(z, c, h, kappa), _ref_hat_p(z, c, h, kappa))
        assert np.array_equal(hat_pp(z, c, h, kappa), _ref_hat_pp(z, c, h, kappa))


def test_hat_stencils_accept_scalar_z():
    for fn, ref in [(hat, _ref_hat), (hat_p, _ref_hat_p), (hat_pp, _ref_hat_pp)]:
        got, want = fn(0.37, 0.1, 0.4, 5.0), ref(0.37, 0.1, 0.4, 5.0)
        assert float(got) == float(want)
    assert float(hat(0.1, 0.1, 0.4, 5.0)) == 1.0  # unit height at the centre


# ------------------------------------- cross-core batched gradient / eval_v
def _ref_hat_grad(z, c, h, kappa):
    """The historical per-core _hat_grad, reproduced verbatim (pre-batching)."""
    u = np.asarray(z, float) - c
    norm = float(2.0 * phi(h, kappa))
    b = _ref_hat(z, c, h, kappa)
    db_dc = -_ref_hat_p(z, c, h, kappa)
    db_dh = (
        (-phi_p(u - h, kappa) + phi_p(u + h, kappa)) / norm
        - b * (2.0 * phi_p(h, kappa)) / norm
    )

    def dpk(x):
        return (-2.0 * phi(x, kappa) + np.asarray(x, float) * phi_p(x, kappa)) / kappa

    draw_dk = dpk(u - h) - 2.0 * dpk(u) + dpk(u + h)
    db_dk = draw_dk / norm - b * (2.0 * dpk(h)) / norm
    return b, db_dc, db_dh, db_dk


def _random_theta(n_cores):
    base = np.array([0.04, -0.02, 0.6, 0.05, 4.0, 3.0])
    cores = []
    for _ in range(n_cores):
        cores.append(
            [
                float(rng.uniform(-0.5, 0.5)),
                float(rng.uniform(-1.5, 1.5)),
                float(rng.uniform(0.15, 1.5)),
                float(rng.uniform(1.0, 12.0)),
            ]
        )
    return np.concatenate([base, np.asarray(cores, dtype=float).ravel()]) if n_cores else base


@pytest.mark.parametrize("n_cores", [0, 1, 2, 3])
def test_model_v_grad_matches_percore_reference(n_cores):
    z = rng.uniform(-2.5, 2.5, 53)
    theta = _random_theta(n_cores)
    v, dv = _model_v_grad(theta, z, n_cores)
    v_ref, dv_ref = _base_grad(z, *theta[:6])
    dv_full = np.zeros((z.size, 6 + 4 * n_cores))
    dv_full[:, :6] = dv_ref
    for r in range(n_cores):
        alpha, c, h, kappa = theta[6 + 4 * r : 10 + 4 * r]
        b, db_dc, db_dh, db_dk = _ref_hat_grad(z, c, h, kappa)
        v_ref = v_ref + alpha * b
        dv_full[:, 6 + 4 * r] = b
        dv_full[:, 7 + 4 * r] = alpha * db_dc
        dv_full[:, 8 + 4 * r] = alpha * db_dh
        dv_full[:, 9 + 4 * r] = alpha * db_dk
    assert np.array_equal(v, v_ref)
    assert np.array_equal(dv, dv_full)


@pytest.mark.parametrize("n_cores", [0, 1, 3])
def test_eval_v_matches_percore_reference(n_cores):
    from volfit.models.sigmoid.kernels import siv_base

    z = rng.uniform(-2.5, 2.5, 41)
    theta = _random_theta(n_cores)
    got = _eval_v(theta, z, n_cores)
    v0, s0, k0, z0, kp, kc = theta[:6]
    ref, _, _ = siv_base(z, v0, s0, k0, z0, kp, kc)
    for r in range(n_cores):
        alpha, c, h, kappa = theta[6 + 4 * r : 10 + 4 * r]
        ref = ref + alpha * _ref_hat(z, c, h, kappa)
    assert np.array_equal(got, ref)


def test_eval_v_scalar_z():
    theta = _random_theta(2)
    got = _eval_v(theta, 0.31, 2)
    ref = _eval_v(theta, np.array([0.31]), 2)[0]
    assert float(got) == float(ref)
