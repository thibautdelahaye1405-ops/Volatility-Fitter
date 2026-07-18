"""Information-form posterior for the precision-message operator (Phase 2).

Implements the precision-form solve of Docs/graph_precision_message_framework.md:

* §15.1  ``Q⁺ = Q_msg + D_κ + Hᵀ R_d H (+ optional extra term)``,
  ``b⁺ = Hᵀ R_d d``, ``ẑ = (Q⁺)⁻¹ b⁺``, ``Σ⁺ = (Q⁺)⁻¹`` — solved per
  connected component of the factor support.
* §14.3  components without a lit observation stay at ZERO innovation (the
  transported prior), tagged ``no_lit_path`` with an explicitly broad
  variance — no artificial precision is invented to make the system proper.
* §15.2  the caller passes the COMBINED innovation observation precision
  ``r_s^d`` (calibration + baseline, harmonic); §15.3 keeps dark-node
  baseline uncertainty out of this field entirely (it enters at
  reconstruction), so nothing is counted twice.
* §17    exact lit-source attribution: ``ẑ = Σ⁺ Hᵀ R d`` gives per-node gain
  rows whose contributions sum to the shift by construction.

Informer-reachability guard (§23 Phase 2): a zero-beta factor couples ONLY
its receiver (``p·(z_i − 0·z_j)²`` involves no ``z_j``), so support
components are built on ``β ≠ 0`` edges — an information-free informer can
never destabilize an observed component, and with that guard every observed
component is symmetric positive definite (verified by Cholesky).

``MessagePosterior`` mirrors the ``GraphPosterior`` consumer surface —
``mean``, ``marginal_variance``/``marginal_precision``, ``credible_band``,
``observed``, ``attribution(i)`` with the same return contract — so Phase 3
hands it to the existing reconstruction/diagnostic layers unchanged. The
covariance-form internals (``observed_columns``/``innovation_cov``) have no
improper-prior equivalent; the select/backtest closed forms port through
``posterior_covariance`` columns instead (identical rank-one algebra on Σ⁺).

Dense per-component inverses, matching the engine's O(10²–10³)-node design
point; the Phase-7 scale pass owns selected inverses and sparsity.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.graph.message import MessageOperator

#: §14.3 — the honest "no lit path" variance: infinitely broad at this layer;
#: the production layer maps it through baseline provenance + the idio floor.
NO_LIT_VARIANCE = np.inf


@dataclass(frozen=True)
class MessagePosterior:
    """Posterior innovation field over all nodes, information form."""

    mean: np.ndarray                  # ẑ (N,) — zero on no-lit components
    marginal_variance: np.ndarray     # diag Σ⁺ (N,) — NO_LIT_VARIANCE when dark
    observed: np.ndarray              # indices of lit nodes (n_obs,)
    innovations: np.ndarray           # d_s (n_obs,)
    innovation_precision: np.ndarray  # r_s^d (n_obs,) — §15.2 combined
    gain: np.ndarray                  # G = Σ⁺ Hᵀ R (N, n_obs); ẑ_i = Σ_s G_is d_s
    posterior_covariance: np.ndarray  # Σ⁺ (N, N); zero across components
    no_lit_path: np.ndarray           # bool (N,) — §14.3 diagnostic
    component: np.ndarray             # int labels (N,) of the factor support

    @property
    def marginal_precision(self) -> np.ndarray:
        """1 / Σ⁺_ii — the marginal, never the precision-matrix diagonal."""
        return 1.0 / self.marginal_variance

    def credible_band(self, z_score: float = 1.96) -> tuple[np.ndarray, np.ndarray]:
        half = z_score * np.sqrt(self.marginal_variance)
        return self.mean - half, self.mean + half

    def attribution(self, i: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(gain_row, innovation, contributions) — node ``i``'s shift decomposed
        EXACTLY over the observed lit sources (same contract as
        ``GraphPosterior.attribution``): contributions sum to ``mean[i]``
        because the prior innovation mean is zero."""
        row = self.gain[i]
        return row, self.innovations, row * self.innovations


def _support_components(operator: MessageOperator) -> np.ndarray:
    """Connected components of the factor support, coupling receiver and
    informer only when the factor's beta is nonzero (the reachability guard)."""
    n = len(operator.nodes)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j, _p, b in operator.factors:
        if b != 0.0:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri
    labels = np.fromiter((find(k) for k in range(n)), dtype=int, count=n)
    _, dense = np.unique(labels, return_inverse=True)
    return dense


def message_posterior_update(
    operator: MessageOperator,
    observed: np.ndarray,
    innovations: np.ndarray,
    observation_precision: np.ndarray,
    *,
    anchor_precision: np.ndarray | None = None,
    extra_precision: np.ndarray | None = None,
    no_lit_variance: float = NO_LIT_VARIANCE,
) -> MessagePosterior:
    """Solve the information-form posterior for ONE handle.

    ``observed``/``innovations``/``observation_precision`` are the lit node
    indices, their innovations ``d = calibrated − transported prior``, and the
    §15.2 combined precisions. ``anchor_precision`` is the §14.2 node-linked
    κ vector (zeros in desk mode); ``extra_precision`` is an optional PSD
    matrix for the explicitly-enabled hybrid mode (§15.4)."""
    n = len(operator.nodes)
    obs = np.asarray(observed, dtype=int)
    d = np.asarray(innovations, dtype=float)
    r = np.asarray(observation_precision, dtype=float)
    if obs.size != d.size or obs.size != r.size:
        raise ValueError("observed/innovations/precision lengths differ")
    if np.any(r <= 0.0) or not np.all(np.isfinite(r)):
        raise ValueError("observation precisions must be finite and > 0")
    if obs.size and (obs.min() < 0 or obs.max() >= n):
        raise ValueError("observed index out of range")
    if np.unique(obs).size != obs.size:
        raise ValueError("duplicate observed node")

    q_full = operator.q_matrix.copy()
    if anchor_precision is not None:
        kappa = np.asarray(anchor_precision, dtype=float)
        if np.any(kappa < 0.0):
            raise ValueError("anchor precisions must be >= 0")
        q_full[np.diag_indices(n)] += kappa
    if extra_precision is not None:
        q_full += np.asarray(extra_precision, dtype=float)
    b = np.zeros(n)
    q_full[obs, obs] += r
    b[obs] += r * d

    component = _support_components(operator)
    lit_components = set(component[obs].tolist())

    mean = np.zeros(n)
    variance = np.full(n, no_lit_variance)
    covariance = np.zeros((n, n))
    gain = np.zeros((n, obs.size))
    no_lit = np.ones(n, dtype=bool)

    for label in range(component.max() + 1 if n else 0):
        idx = np.flatnonzero(component == label)
        if label not in lit_components:
            covariance[idx, idx] = no_lit_variance
            continue
        qc = q_full[np.ix_(idx, idx)]
        try:
            np.linalg.cholesky(qc)  # PD guard: raises LinAlgError otherwise
        except np.linalg.LinAlgError as exc:
            names = [operator.nodes[k] for k in idx[:6]]
            raise np.linalg.LinAlgError(
                f"observed component {names}... is not positive definite — "
                "check zero-beta informers or conflicting anchors"
            ) from exc
        sigma = np.linalg.inv(qc)
        mean[idx] = sigma @ b[idx]
        var = np.diag(sigma)
        if np.any(var <= 0.0):
            raise FloatingPointError("posterior variance must stay positive")
        variance[idx] = var
        covariance[np.ix_(idx, idx)] = sigma
        obs_pos = np.flatnonzero(component[obs] == label)
        if obs_pos.size:
            local = {k: t for t, k in enumerate(idx)}
            local_obs = [local[obs[p]] for p in obs_pos]
            gain[np.ix_(idx, obs_pos)] = sigma[:, local_obs] * r[obs_pos]
        no_lit[idx] = False

    return MessagePosterior(
        mean=mean,
        marginal_variance=variance,
        observed=obs,
        innovations=d,
        innovation_precision=r,
        gain=gain,
        posterior_covariance=covariance,
        no_lit_path=no_lit,
        component=component,
    )
