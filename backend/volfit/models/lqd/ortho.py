"""ATM-orthogonal coordinates for the LQD slice (note sections 6.2-6.3).

Splits the coefficient space around a reference slice theta* into
  - three *primary* directions U that move exactly (and minimally, in the
    least-norm sense) the trader handles H = (w0, skew, curvature), and
  - shape directions V spanning ker J that leave the handles unchanged to
    first order (eqs. atm_pinv, projector, ortho_param).

`retarget` makes the mapping exact with a 3-d Newton solve on the primary
coordinates (eq. implicit_atm): traders move ATM level/skew/curvature
directly while shape modes keep wings and event convexity untouched.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.quadrature import build_slice


def handles_vector(params: LQDParams, t: float) -> np.ndarray:
    """H(theta) = (w0, skew, curvature) for the slice at expiry ``t``."""
    h = atm_handles(build_slice(params), t)
    return np.array([h.w0, h.skew, h.curvature])


def atm_jacobian(params: LQDParams, t: float, step: float = 1e-6) -> np.ndarray:
    """3 x d Jacobian dH/dtheta by central finite differences.

    The quadrature is deterministic and smooth, so central differences with a
    relative step are accurate to ~1e-9 here (note Appendix B remark).
    """
    theta = params.to_vector()
    d = theta.size
    jac = np.empty((3, d))
    for j in range(d):
        h_j = step * max(1.0, abs(theta[j]))
        up, down = theta.copy(), theta.copy()
        up[j] += h_j
        down[j] -= h_j
        jac[:, j] = (
            handles_vector(LQDParams.from_vector(up), t)
            - handles_vector(LQDParams.from_vector(down), t)
        ) / (2.0 * h_j)
    return jac


@dataclass(frozen=True)
class ATMCoordinates:
    """Local coordinate chart theta = theta* + U alpha + V xi around theta*.

    U (d x 3) are least-norm primary directions with J U = I_3 — least-norm
    in the chart's ``metric`` (Euclidean by default; the Gauss--Newton
    information matrix when the caller supplies one, so "cheapest handle
    move" is priced by fit impact rather than raw coefficient units).  The
    columns of V (d x (d-3)) are an orthonormal basis of ker J; note the
    kernel SUBSPACE is metric-independent, but the basis is unique only up
    to rotation — shape-direction labels are session-local, never persistent
    trader coordinates.  ``condition`` is the SVD condition number of the
    3x3 handle Gram matrix: a large value means the handle Jacobian is
    near-degenerate (thin boards) and primary moves are unreliable.
    """

    reference: LQDParams
    t: float
    handles0: np.ndarray
    jacobian: np.ndarray
    primary: np.ndarray  # U
    shape: np.ndarray  # V
    condition: float = float("nan")

    def theta(self, alpha: np.ndarray, xi: np.ndarray | None = None) -> LQDParams:
        """Map local coordinates (alpha, xi) to a parameter vector."""
        vec = self.reference.to_vector() + self.primary @ np.asarray(alpha, dtype=float)
        if xi is not None:
            vec = vec + self.shape @ np.asarray(xi, dtype=float)
        return LQDParams.from_vector(vec)

    def decompose(self, params: LQDParams) -> tuple[np.ndarray, np.ndarray]:
        """First-order coordinates of ``params``: alpha = J dtheta, xi = V^T dtheta."""
        delta = params.to_vector() - self.reference.to_vector()
        return self.jacobian @ delta, self.shape.T @ delta

    def retarget(
        self,
        target_handles: np.ndarray,
        xi: np.ndarray | None = None,
        tol: float = 1e-12,
        max_iter: int = 20,
    ) -> LQDParams:
        """Exact ATM targeting: solve H(theta(alpha, xi)) = target for alpha.

        Newton iteration on the 3-d system (eq. implicit_atm); the alpha
        Jacobian is J U = I_3 at the reference, so the identity is an
        excellent preconditioner and refreshing it is rarely needed.
        """
        target = np.asarray(target_handles, dtype=float)
        alpha = target - self.handles0  # first-order seed, since J U = I
        jac_alpha = np.eye(3)
        for iteration in range(max_iter):
            residual = handles_vector(self.theta(alpha, xi), self.t) - target
            if np.max(np.abs(residual)) < tol:
                return self.theta(alpha, xi)
            if iteration == 3:  # slow convergence: refresh the 3x3 Jacobian
                jac_alpha = self._alpha_jacobian(alpha, xi)
            alpha = alpha - np.linalg.solve(jac_alpha, residual)
        raise RuntimeError("ATM retargeting Newton did not converge")

    def _alpha_jacobian(self, alpha: np.ndarray, xi: np.ndarray | None) -> np.ndarray:
        """3x3 Jacobian of H with respect to alpha at the current point."""
        jac = np.empty((3, 3))
        for j in range(3):
            h_j = 1e-6
            up, down = alpha.copy(), alpha.copy()
            up[j] += h_j
            down[j] -= h_j
            jac[:, j] = (
                handles_vector(self.theta(up, xi), self.t)
                - handles_vector(self.theta(down, xi), self.t)
            ) / (2.0 * h_j)
        return jac


def gauss_newton_metric(residual_jacobian_rows: np.ndarray) -> np.ndarray:
    """The Gauss--Newton (Fisher) metric G = J_r^T J_r from the calibration
    residual Jacobian at convergence (weights/vega scaling already folded
    into the rows — the solver_diag side-channel of calibrate_slice).  Under
    this metric a "cheapest" handle move is the one that disturbs the fitted
    quotes least, which is the economically defensible reading."""
    j = np.asarray(residual_jacobian_rows, dtype=float)
    return j.T @ j


def build_atm_coordinates(
    params: LQDParams, t: float, metric: np.ndarray | None = None
) -> ATMCoordinates:
    """Construct the ATM-orthogonal chart at a reference slice.

    Default (``metric=None``): U = J^T (J J^T)^{-1}, the Euclidean
    least-norm right inverse (eq. atm_pinv) — byte-identical to the
    historical chart.  With a PSD ``metric`` G (d x d): U = G^{-1} J^T
    (J G^{-1} J^T)^{-1}, the G-least-norm right inverse — pass
    ``gauss_newton_metric(solver_diag["jac"])`` to price moves by fit
    impact.  V from the QR factorization of the projector onto ker J
    (eq. projector); the handle Gram's SVD condition number is reported on
    the chart either way.
    """
    jac = atm_jacobian(params, t)
    d = jac.shape[1]
    if metric is None:
        gram = jac @ jac.T
        primary = jac.T @ np.linalg.solve(gram, np.eye(3))
    else:
        g = 0.5 * (np.asarray(metric, dtype=float) + np.asarray(metric, dtype=float).T)
        # Tikhonov floor: the GN metric is singular along data-flat
        # directions (that is the POINT of the ridge/prior machinery), so
        # regularize before inverting — the floor only touches directions
        # the fit does not see.
        g = g + (1e-8 * max(float(np.trace(g)) / d, 1e-30)) * np.eye(d)
        ginv_jt = np.linalg.solve(g, jac.T)
        gram = jac @ ginv_jt
        primary = ginv_jt @ np.linalg.solve(gram, np.eye(3))

    # Orthonormal kernel basis: project out row(J), keep the d-3 significant
    # directions of the projector's QR factorization.  (Euclidean projector
    # regardless of the metric: ker J is the same subspace, and an
    # orthonormal basis of it is all V promises.)
    e_gram = jac @ jac.T
    projector = np.eye(d) - jac.T @ np.linalg.solve(e_gram, jac)
    q, r = np.linalg.qr(projector)
    keep = np.abs(np.diag(r)) > 1e-10
    shape = q[:, keep][:, : d - 3]

    sing = np.linalg.svd(gram, compute_uv=False)
    return ATMCoordinates(
        reference=params,
        t=t,
        handles0=handles_vector(params, t),
        jacobian=jac,
        primary=primary,
        shape=shape,
        condition=float(sing[0] / max(sing[-1], 1e-300)),
    )
