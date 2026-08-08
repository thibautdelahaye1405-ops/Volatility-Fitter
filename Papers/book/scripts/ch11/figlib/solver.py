"""The chapter's graph solver, implementing exactly the displayed equations.

One quadratic objective over the innovation field Theta (eq. grjoint of the
chapter):

    sum_edges   p_ij (Theta_i - beta_ij Theta_j - c_ij)^2      (contracts,
                                                                offset c_ij
                                                                carries a
                                                                residual mean)
  + sum_nodes   kappa_i (Theta_i - a_i)^2                      (anchors)
  + sum_lit     (Theta_s - obs_s)^2 / V_obs_s                  (observations)

Its Hessian (times one half) is the universe's posterior information matrix
I+; the posterior mean solves the normal equations; marginal variances are
the diagonal of the inverse; the attribution gains K_is are the posterior's
exact per-source decomposition.  Everything is plain dense numpy -- the
chapter's universes are tens of nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Factor:
    """One relation contract: receiver i hears informer j at amplitude beta,
    precision p; the optional offset shifts the contract's target (used to
    carry a persisted residual mean)."""

    i: int
    j: int
    p: float
    beta: float
    offset: float = 0.0


@dataclass
class Problem:
    """One solve: n nodes, contracts, anchors, and lit observations."""

    n: int
    factors: list[Factor] = field(default_factory=list)
    kappa: np.ndarray | None = None       # anchor precisions (default 0)
    anchor_mean: np.ndarray | None = None  # anchor targets (default 0)
    obs: list[tuple[int, float, float]] = field(default_factory=list)
    # obs entries: (node, measured innovation, observation variance)

    def edge(self, i: int, j: int, p: float, beta: float = 1.0,
             offset: float = 0.0) -> None:
        self.factors.append(Factor(i, j, p, beta, offset))

    def observe(self, s: int, value: float, var: float) -> None:
        self.obs.append((s, value, var))


@dataclass(frozen=True)
class Posterior:
    """Posterior mean, marginal variances, and exact per-source attribution."""

    mean: np.ndarray          # Theta-hat-plus, per node
    var: np.ndarray           # marginal posterior variance, per node
    info: np.ndarray          # the information matrix I+ (Hessian / 2)
    cov: np.ndarray           # its full inverse
    gains: np.ndarray         # (n, n_obs): K_is, columns per lit source
    obs_nodes: np.ndarray     # the lit node indices, in gain-column order

    def sd(self) -> np.ndarray:
        return np.sqrt(self.var)


def solve(prob: Problem) -> Posterior:
    """Assemble the information form and solve it (one connected component).

    Raises if the information matrix is singular -- the chapter's honest
    no-lit-path components are handled by the caller, which reports the
    baseline and a stated broad band instead of solving.
    """
    n = prob.n
    info = np.zeros((n, n))
    rhs = np.zeros(n)
    for f in prob.factors:
        # p (Theta_i - beta Theta_j - c)^2 contributes to the quadratic and
        # linear parts; offsets land on the right-hand side.
        info[f.i, f.i] += f.p
        info[f.j, f.j] += f.p * f.beta**2
        info[f.i, f.j] -= f.p * f.beta
        info[f.j, f.i] -= f.p * f.beta
        rhs[f.i] += f.p * f.offset
        rhs[f.j] -= f.p * f.beta * f.offset
    if prob.kappa is not None:
        mean0 = (prob.anchor_mean if prob.anchor_mean is not None
                 else np.zeros(n))
        info[np.diag_indices(n)] += prob.kappa
        rhs += prob.kappa * mean0
    obs_nodes = np.array([s for s, _, _ in prob.obs], dtype=int)
    for s, value, var in prob.obs:
        info[s, s] += 1.0 / var
        rhs[s] += value / var
    cov = np.linalg.inv(info)
    mean = cov @ rhs
    # Attribution: Theta-hat-plus_i = sum_s K_is obs_s (+ anchor/offset part);
    # the gain of source s is the posterior's exact derivative in obs_s.
    gains = np.column_stack(
        [cov[:, s] / var for s, _, var in prob.obs]
    ) if prob.obs else np.zeros((n, 0))
    return Posterior(mean=mean, var=np.diag(cov).copy(), info=info, cov=cov,
                     gains=gains, obs_nodes=obs_nodes)


def averaging_solve(n: int, factors: list[Factor],
                    obs: list[tuple[int, float, float]],
                    tiny_anchor: float = 1e-8) -> np.ndarray:
    """The row-normalized ALTERNATIVE assembly (the dead-informer foil).

    Each receiver is charged once, at its total incoming precision q_i, for
    deviating from its precision-weighted forecast.  A tiny anchor keeps the
    solve proper (the alternative is improper whenever an informer is free).
    Returns the posterior mean only -- the foil never earns a band.
    """
    info = np.full((n, n), 0.0)
    rhs = np.zeros(n)
    by_receiver: dict[int, list[Factor]] = {}
    for f in factors:
        by_receiver.setdefault(f.i, []).append(f)
    for i, fs in by_receiver.items():
        q = sum(f.p for f in fs)
        # q_i (Theta_i - sum_j (p_ij/q_i) beta_ij Theta_j)^2
        coef = np.zeros(n)
        coef[i] = 1.0
        for f in fs:
            coef[f.j] -= (f.p / q) * f.beta
        info += q * np.outer(coef, coef)
    info[np.diag_indices(n)] += tiny_anchor
    for s, value, var in obs:
        info[s, s] += 1.0 / var
        rhs[s] += value / var
    return np.linalg.solve(info, rhs)


def residual_decay(u0: float, dt_days: float, half_life_days: float) -> float:
    """The carried residual mean: u0 * 2^(-dt / t_half)."""
    if np.isinf(half_life_days):
        return u0
    return float(u0 * 2.0 ** (-dt_days / half_life_days))
