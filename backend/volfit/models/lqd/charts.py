"""LQD optimization charts: (L, R, a), endpoint, and logistic coordinates.

Three charts over the SAME model family — the chart changes the optimizer's
trust-region geometry, never the objective, so the fitted optimum is
chart-independent and the canonical storage/wire format stays
theta = (L, R, a_2..a_N) everywhere:

- "lr"        the historical raw vector theta itself (identity chart).
- "endpoint"  phi = (log A_L, log A_R, a_2..a_N), theta = M phi with M the
              exact unit-determinant linear map of ``endpoint_transform``.
              Body modes at fixed (phi_0, phi_1) are endpoint-neutral, so
              acute central convexity can no longer mechanically drag the
              asymptotic wings while the solver moves (note eq. endpoint_chart).
- "logistic"  psi = (log A_L, rho, a_2..a_N) with A_R = expit(rho): the
              endpoint chart with the right tail scale pushed through the
              logistic. The admissibility wall A_R < 1 becomes unreachable —
              every psi in R^d maps to an admissible slice — so the chart is
              genuinely unconstrained. Near the wall it compresses
              (d log A_R / d rho = 1 - A_R -> 0), damping trust-region steps
              exactly where the raw charts need the soft barrier; far below
              the wall rho ~ log A_R and it agrees with the endpoint chart
              to first order.

Numerical footnote (committee point 5): the logistic removes the
*mathematical* wall, not the floating-point one — beyond rho ~ 36,
exp(-softplus(-rho)) rounds A_R to exactly 1.0 in double precision, so
``build_slice``'s EPS_AR buffer remains the hard numerical guard and the
soft barrier (part of the objective in every chart) keeps the optimizer
clear of that region.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import expit

from volfit.models.lqd.quadrature import EPS_AR

#: Warm-start clamp: log A_R mapped through ``from_theta`` is kept strictly
#: below the wall (mirrors build_slice's admissibility buffer) so an
#: infeasible seed still yields a finite logistic coordinate.
_LOG_AR_CEIL = float(np.log1p(-EPS_AR))


def endpoint_transform(n_order: int) -> np.ndarray:
    """The endpoint-coordinate chart theta = M @ phi (symmetric-surface
    Phase 5), with phi = (log A_L, log A_R, a_2..a_N).

    log A_L = L + sum a_n and log A_R = R + sum (-1)^n a_n are linear in
    theta, so the chart is an exact, unit-determinant linear map: holding
    (phi_0, phi_1) fixed while moving a body mode a_n automatically
    counter-adjusts (L, R) to keep both endpoint scales — the coefficients
    that fit acute central convexity can no longer mechanically drag the
    asymptotic wings. Same model family, same optimum; only the optimizer's
    trust-region geometry changes.
    """
    p = n_order + 1
    m = np.eye(p)
    n = np.arange(2, n_order + 1)
    m[0, 2:] = -1.0
    m[1, 2:] = -((-1.0) ** n)
    return m


@dataclass(frozen=True)
class OptimizationChart:
    """Bijection x <-> theta plus the chain-rule factors calibrate_slice needs.

    ``name`` is "endpoint" or "logistic"; the identity "lr" chart is
    represented by ``build_chart`` returning None (callers keep their raw
    fast path). ``m``/``m_inv`` are the endpoint map and its inverse.
    """

    name: str
    m: np.ndarray
    m_inv: np.ndarray

    def _dphi1_dx1(self, x1: float) -> float:
        """d(log A_R)/d(chart coordinate 1): 1 - A_R = expit(-rho) for the
        logistic chart, 1 for the (linear) endpoint chart."""
        return float(expit(-x1)) if self.name == "logistic" else 1.0

    def to_theta(self, x: np.ndarray) -> np.ndarray:
        """Map chart coordinates to the canonical theta = (L, R, a)."""
        phi = np.asarray(x, dtype=float).copy()
        if self.name == "logistic":
            # log A_R = log expit(rho) = -softplus(-rho), stable for all rho.
            phi[1] = -np.logaddexp(0.0, -phi[1])
        return self.m @ phi

    def from_theta(self, theta: np.ndarray) -> np.ndarray:
        """Map a canonical vector into the chart (warm starts, seeds)."""
        phi = np.linalg.solve(self.m, np.asarray(theta, dtype=float))
        if self.name == "logistic":
            # rho = logit(A_R) evaluated from log A_R without forming A_R:
            # rho = log A_R - log(1 - A_R) = la - log(-expm1(la)).
            la = min(phi[1], _LOG_AR_CEIL)
            phi[1] = la - np.log(-np.expm1(la))
        return phi

    def dtheta_dx(self, x: np.ndarray) -> np.ndarray:
        """Chart Jacobian d theta / d x = M @ diag(1, dphi1/dx1, 1, ..)."""
        d = np.ones(np.asarray(x).size)
        d[1] = self._dphi1_dx1(float(np.asarray(x, dtype=float)[1]))
        return self.m * d

    def pull_jacobian(self, jac_x: np.ndarray, x: np.ndarray) -> np.ndarray:
        """Residual Jacobian in canonical coordinates from the chart one:
        J_theta = J_x (dtheta/dx)^{-1} = (J_x diag(1/d)) M^{-1}."""
        d = np.ones(np.asarray(x).size)
        d[1] = self._dphi1_dx1(float(np.asarray(x, dtype=float)[1]))
        return (jac_x / d) @ self.m_inv


def build_chart(n_order: int, coords: str) -> OptimizationChart | None:
    """Chart factory for ``calibrate_slice(coords=...)``.

    Returns None for the identity "lr" chart (callers keep the raw path);
    raises on an unknown name so a typo cannot silently fit in the wrong
    coordinates.
    """
    if coords == "lr":
        return None
    if coords not in ("endpoint", "logistic"):
        raise ValueError(f"unknown LQD coords chart: {coords!r}")
    m = endpoint_transform(n_order)
    return OptimizationChart(name=coords, m=m, m_inv=np.linalg.inv(m))
