"""Chapter 10's self-contained estimation routines.

Implements exactly the objects the chapter displays -- nothing more:

  * quote support Q(k): the Gaussian-kernel effective quote count
    (book eq. support), bandwidth 0.06 in log-moneyness;
  * the harmonic information price of a signed basket (book eq. harmonic);
  * the activation gate with its dead zone (book eq. gate);
  * the scalar filter update: precision-weighted average, gain, posterior
    variance (book eq. filterupdate);
  * a natural-cubic-spline smile family (linear in its knot values) with
    whitened least squares, gated prior rows, and the observed information
    matrix -- the delta-method variance of any linear handle is exact here.

Everything is deterministic; the seeded walk lives in fig_audit.py,
not here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline

BANDWIDTH = 0.06  # log-moneyness kernel width; also the factor stencil step


# ------------------------------------------------------------------ support
def support(k_eval: np.ndarray, k_quotes: np.ndarray,
            weights: np.ndarray | None = None) -> np.ndarray:
    """Effective quote count at each location (mean-one weights)."""
    k_eval = np.atleast_1d(np.asarray(k_eval, dtype=float))
    k_quotes = np.asarray(k_quotes, dtype=float)
    if weights is None:
        weights = np.ones_like(k_quotes)
    weights = weights / weights.mean()
    z = (k_eval[:, None] - k_quotes[None, :]) / BANDWIDTH
    return (weights[None, :] * np.exp(-0.5 * z * z)).sum(axis=1)


def basket_precision(coeffs: np.ndarray, supports: np.ndarray,
                     eps: float = 1e-9) -> float:
    """The harmonic law: precision of sum_a omega_a sigma(k_a)."""
    coeffs = np.asarray(coeffs, dtype=float)
    supports = np.asarray(supports, dtype=float)
    nz = coeffs != 0.0
    return float(1.0 / np.sum(coeffs[nz] ** 2 / (supports[nz] + eps)))


def gate(precision, required: float = 1.0, gamma: float = 1.0) -> np.ndarray:
    """The activation gate: 1 where data is silent, exactly 0 past required."""
    ratio = np.asarray(precision, dtype=float) / max(required, 1e-12)
    return np.clip(1.0 - ratio, 0.0, 1.0) ** gamma


# ------------------------------------------------------------------- filter
def filter_update(m_pred: float, v_pred: float, z_obs: float,
                  v_obs: float) -> tuple[float, float, float]:
    """Scalar update: posterior mean, posterior variance, gain."""
    gain = v_pred / (v_pred + v_obs)
    m_post = m_pred + gain * (z_obs - m_pred)
    v_post = (1.0 - gain) * v_pred
    return m_post, v_post, gain


# ------------------------------------------------- spline smile family (lsq)
@dataclass(frozen=True)
class SplineFamily:
    """A natural cubic spline in k, linear in its knot values theta."""

    knots: np.ndarray

    def design(self, k: np.ndarray) -> np.ndarray:
        """Design matrix: column j is the cardinal spline of knot j at k."""
        k = np.asarray(k, dtype=float)
        cols = []
        for j in range(self.knots.size):
            unit = np.zeros(self.knots.size)
            unit[j] = 1.0
            cols.append(CubicSpline(self.knots, unit, bc_type="natural")(k))
        return np.column_stack(cols)

    def second_difference(self) -> np.ndarray:
        """Interior second-difference rows (the mild smoothness ridge)."""
        n = self.knots.size
        rows = []
        for j in range(1, n - 1):
            dl = self.knots[j] - self.knots[j - 1]
            dr = self.knots[j + 1] - self.knots[j]
            row = np.zeros(n)
            row[j - 1] = 2.0 / (dl * (dl + dr))
            row[j] = -2.0 / (dl * dr)
            row[j + 1] = 2.0 / (dr * (dl + dr))
            rows.append(row)
        return np.vstack(rows)


@dataclass
class FitResult:
    """A solved whitened least-squares fit of the spline family."""

    family: SplineFamily
    theta: np.ndarray
    information: np.ndarray     # I_theta = A_w^T A_w over ALL rows
    chi2_data: float            # sum of squared whitened DATA residuals
    n_data: int

    def vol(self, k: np.ndarray) -> np.ndarray:
        return self.family.design(k) @ self.theta

    def handle_variance(self, grad: np.ndarray) -> float:
        """Delta method: Var(O) = grad^T I^-1 grad (exact, linear family)."""
        sol = np.linalg.solve(self.information, np.asarray(grad, dtype=float))
        return float(np.asarray(grad, dtype=float) @ sol)


def fit_spline(family: SplineFamily, k_quotes: np.ndarray, vols: np.ndarray,
               noise_sd: float | np.ndarray,
               prior_rows: np.ndarray | None = None,
               prior_targets: np.ndarray | None = None,
               prior_weights: np.ndarray | None = None,
               ridge: float = 3.0) -> FitResult:
    """Whitened least squares: data rows / smoothness rows / prior rows.

    Data rows are divided by their stated noise sd (the units discipline the
    chapter insists on); each prior row j enters at sqrt(lambda_j).  The
    returned information matrix is the Gauss-Newton information of the full
    whitened stack.
    """
    k_quotes = np.asarray(k_quotes, dtype=float)
    vols = np.asarray(vols, dtype=float)
    sd = np.broadcast_to(np.asarray(noise_sd, dtype=float), vols.shape)

    a_data = family.design(k_quotes) / sd[:, None]
    b_data = vols / sd
    blocks_a = [a_data]
    blocks_b = [b_data]

    smooth = ridge * family.second_difference()
    blocks_a.append(smooth)
    blocks_b.append(np.zeros(smooth.shape[0]))

    if prior_rows is not None and len(prior_rows):
        w = np.sqrt(np.asarray(prior_weights, dtype=float))
        blocks_a.append(np.asarray(prior_rows, dtype=float) * w[:, None])
        blocks_b.append(np.asarray(prior_targets, dtype=float) * w)

    a_full = np.vstack(blocks_a)
    b_full = np.concatenate(blocks_b)
    theta, *_ = np.linalg.lstsq(a_full, b_full, rcond=None)
    chi2 = float(np.sum((a_data @ theta - b_data) ** 2))
    return FitResult(family, theta, a_full.T @ a_full, chi2, k_quotes.size)
