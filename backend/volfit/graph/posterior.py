"""Gaussian conditioning on the observed time-1 nodes (note section 7).

Covariance form, exploiting n_observed << n_nodes (eqs. muplus-covariance,
Kplus-covariance): only the observed columns of the predictive covariance
K^- = P_0^{-1} + K_Delta and a small n x n innovation system are needed.
Reports *marginal* posterior precisions 1 / K^+_{ii} — never the diagonal of
the precision matrix (the note's "frequent precision mistake" warning).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.graph.prior import IncrementPrior


@dataclass(frozen=True)
class GraphPosterior:
    """Posterior field over all nodes after seeing the lit subset."""

    mean: np.ndarray  # mu^+
    marginal_variance: np.ndarray  # diag K^+
    innovation_cov: np.ndarray  # S_y
    innovation_weights: np.ndarray  # alpha = S_y^{-1} (y - H mu^-)
    observed: np.ndarray  # indices of lit nodes

    @property
    def marginal_precision(self) -> np.ndarray:
        """pi_i^+ = 1 / K^+_{ii}  (eq. marginal-precision-final)."""
        return 1.0 / self.marginal_variance

    def credible_band(self, z_score: float = 1.96) -> tuple[np.ndarray, np.ndarray]:
        """(lo, hi) pointwise credible interval (eq. credible-interval)."""
        half = z_score * np.sqrt(self.marginal_variance)
        return self.mean - half, self.mean + half


def posterior_update(
    prior: IncrementPrior,
    baseline: np.ndarray,
    baseline_precision: np.ndarray,
    observed: np.ndarray,
    observations: np.ndarray,
    observation_precision: np.ndarray,
    drift: np.ndarray | None = None,
) -> GraphPosterior:
    """Condition the predictive prior on observations at ``observed`` nodes.

    ``baseline``/``baseline_precision`` are xbar^0 and p^0 (finite baseline
    precision adds P_0^{-1} to the predictive covariance, eq. predictive-prior);
    ``observations``/``observation_precision`` are y and r at the lit nodes;
    ``drift`` is the optional m_Delta.
    """
    baseline = np.asarray(baseline, dtype=float)
    p0 = np.asarray(baseline_precision, dtype=float)
    obs_idx = np.asarray(observed, dtype=int)
    y = np.asarray(observations, dtype=float)
    r = np.asarray(observation_precision, dtype=float)
    if np.any(p0 <= 0) or np.any(r <= 0):
        raise ValueError("precisions must be strictly positive")

    # Predictive moments: mu^- = xbar^0 + m_Delta, K^- = P_0^{-1} + K_Delta.
    mu_minus = baseline if drift is None else baseline + np.asarray(drift, dtype=float)
    k_minus_diag = 1.0 / p0 + np.diag(prior.covariance)

    # Observed columns of K^-: K_Delta columns plus the baseline-variance
    # contribution on the matching rows.
    cols = prior.covariance[:, obs_idx].copy()
    cols[obs_idx, np.arange(obs_idx.size)] += 1.0 / p0[obs_idx]

    # Innovation system S_y alpha = y - mu^-_S  (eqs. small-Sy, small-alpha).
    s_y = cols[obs_idx, :] + np.diag(1.0 / r)
    innovation = y - mu_minus[obs_idx]
    alpha = np.linalg.solve(s_y, innovation)

    # Posterior mean and marginal variances (eqs. large-mu, posterior-diag-formula).
    mean = mu_minus + cols @ alpha
    correction = np.einsum("ij,ij->i", cols @ np.linalg.inv(s_y), cols)
    marginal_variance = k_minus_diag - correction
    if np.any(marginal_variance <= 0):
        raise FloatingPointError("posterior variance must stay positive")

    return GraphPosterior(
        mean=mean,
        marginal_variance=marginal_variance,
        innovation_cov=s_y,
        innovation_weights=alpha,
        observed=obs_idx,
    )
