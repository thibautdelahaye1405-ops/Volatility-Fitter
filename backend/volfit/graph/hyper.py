"""Hyperparameter evidence: Gaussian marginal likelihood (note section 9).

Under the linear-Gaussian model the observations are
y | xbar^0, theta ~ N(H mu^-, S_y) with S_y = H K^- H^T + R^{-1}
(eq. marginal-y), so hyperparameters (kappa, eta, lambda, nu, ...) can be
scored by the exact log marginal likelihood (eq. log-marginal). S_y is only
n x n, so evaluation stays cheap even on large universes. Held-out
standardized residuals (eq. standardized-residual-final) complement it as a
calibration check.
"""

from __future__ import annotations

import numpy as np


def marginal_log_likelihood(
    innovation_cov: np.ndarray,
    innovation: np.ndarray,
) -> float:
    """log p(y | xbar^0, theta) for innovation d = y - H mu^- and S_y.

    ell = -1/2 d^T S^{-1} d - 1/2 log det S - n/2 log 2 pi.
    Uses a Cholesky factorization for the determinant and the solve.
    """
    s_y = np.asarray(innovation_cov, dtype=float)
    d = np.asarray(innovation, dtype=float)
    chol = np.linalg.cholesky(s_y)
    white = np.linalg.solve(chol, d)
    log_det = 2.0 * float(np.sum(np.log(np.diag(chol))))
    n = d.size
    return float(-0.5 * white @ white - 0.5 * log_det - 0.5 * n * np.log(2.0 * np.pi))


def standardized_residuals(
    held_out_values: np.ndarray,
    posterior_mean: np.ndarray,
    posterior_variance: np.ndarray,
    observation_precision: np.ndarray,
) -> np.ndarray:
    """zeta_i = (y_i - mu_i^+) / sqrt(K^+_{ii} + r_i^{-1}) for held-out nodes.

    Should look like standard normal draws when the model is calibrated:
    systematically large |zeta| = overconfident, small = underconfident.
    """
    y = np.asarray(held_out_values, dtype=float)
    mu = np.asarray(posterior_mean, dtype=float)
    var = np.asarray(posterior_variance, dtype=float)
    r = np.asarray(observation_precision, dtype=float)
    return (y - mu) / np.sqrt(var + 1.0 / r)
