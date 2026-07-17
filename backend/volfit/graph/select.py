"""Active observation selection (roadmap R3 item 13; Note 14 sec. posterior).

"Which dark node should be quoted next?" — answered in closed form on the
covariance-form posterior of Note 14 (eqs. sy--kp), no refit and no re-solve.
Observing candidate ``c`` with precision ``r`` is a rank-one Schur update of
the posterior covariance:

    K' = K+  -  K+[:,c] K+[c,:] / (K+_cc + 1/r)         (eq. rank-one)

so node ``i``'s variance drops by (K+_ic)^2 / (K+_cc + 1/r) and the
exposure-weighted total gain of quoting ``c`` is

    G(c) = sum_i  w_i (K+_ic)^2 / (K+_cc + 1/r_c).

The candidate columns K+[:,c] come from the same identity the solver already
uses: K+[:,c] = K-[:,c] - C S^-1 (C[c,:])^T with C = K-[:,obs] and S the
innovation system, both stored on GraphPosterior — one m x c solve for the
whole candidate set. With no observations at all K+ = K- and the gain is the
prior-variance column squared over its own diagonal.

Honesty note: gains live in MODEL variance units. The idio band floor
(volfit.graph.idio) is deliberately NOT folded into cross-node gains — idio
variance is exactly the part observing OTHER nodes cannot remove; quoting the
node itself removes it, which the caller surfaces separately.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.graph.posterior import GraphPosterior


@dataclass(frozen=True)
class ObservationGain:
    """One candidate's closed-form value as the next observation."""

    index: int  # node index in the universe ordering
    total_gain: float  # sum_i w_i * delta_var_i  (model variance units)
    self_var_before: float  # K+_cc
    self_var_after: float  # K+_cc after observing c itself
    per_node_var_drop: np.ndarray  # delta_var_i, shape (N,)


def observation_gains(
    prior_covariance: np.ndarray,
    baseline_precision: np.ndarray,
    posterior: GraphPosterior | None,
    candidates: np.ndarray,
    candidate_precision: np.ndarray,
    weights: np.ndarray | None = None,
) -> list[ObservationGain]:
    """Score every candidate node as the next observation (eq. rank-one).

    ``prior_covariance``/``baseline_precision`` are the increment prior's
    K_Delta and p0 for ONE handle coordinate (the solver builds K- from them);
    ``posterior`` is that coordinate's solved GraphPosterior, or None when
    today has no observations (the predictive prior). ``candidates`` are node
    indices that must NOT already be observed. ``candidate_precision`` is the
    observation precision each candidate would carry if quoted (r_c > 0).
    ``weights`` (default all-ones) is the exposure vector w >= 0.
    """
    cand = np.asarray(candidates, dtype=int)
    r = np.asarray(candidate_precision, dtype=float)
    if cand.size == 0:
        return []
    if r.shape != (cand.size,) or np.any(r <= 0):
        raise ValueError("candidate_precision must be positive, one per candidate")
    n = prior_covariance.shape[0]
    p0 = np.asarray(baseline_precision, dtype=float)
    w = np.ones(n) if weights is None else np.asarray(weights, dtype=float)
    if np.any(w < 0):
        raise ValueError("exposure weights must be non-negative")

    # K- candidate columns: K_Delta[:, c] plus the baseline variance on the
    # candidate's own row (K- = K_Delta + P0^{-1}).
    km_cols = prior_covariance[:, cand].copy()
    km_cols[cand, np.arange(cand.size)] += 1.0 / p0[cand]

    if posterior is not None:
        if np.intersect1d(cand, posterior.observed).size:
            raise ValueError("candidates must not already be observed")
        # K+[:, c] = K-[:, c] - C S^-1 C[c, :]^T ; C[c, :] = K-[c, obs] which
        # (candidates being unobserved) is the observed-row block of km_cols.
        b = km_cols[posterior.observed, :]
        kp_cols = km_cols - posterior.observed_columns @ np.linalg.solve(
            posterior.innovation_cov, b
        )
        kp_cc = posterior.marginal_variance[cand]
    else:  # no observations today: the posterior IS the predictive prior
        kp_cols = km_cols
        kp_cc = 1.0 / p0[cand] + np.diag(prior_covariance)[cand]

    out: list[ObservationGain] = []
    for j, c in enumerate(cand):
        denom = kp_cc[j] + 1.0 / r[j]
        drop = kp_cols[:, j] ** 2 / denom
        self_after = kp_cc[j] - drop[c]
        out.append(
            ObservationGain(
                index=int(c),
                total_gain=float(w @ drop),
                self_var_before=float(kp_cc[j]),
                self_var_after=float(max(self_after, 0.0)),
                per_node_var_drop=drop,
            )
        )
    return out
