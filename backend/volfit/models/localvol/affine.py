"""P1 piecewise-affine local-variance surface and implicit-Euler Dupire pricer.

Implements the parameterization and pricing map of
Docs/piecewise_affine_local_variance_calibration.tex:

- ``AffineVarianceSurface``: continuous piecewise-affine local *variance*
  nu_theta(t, x) = sum_l theta_l phi_l(t, x) (eq. (p1_lv)) on a tensor-product
  vertex set.  ``interp`` picks the triangulation: "delaunay" (scipy/qhull
  Delaunay of the vertices -- this is the convention that reproduces the
  note's quote table to every published decimal, see tests), "tri_lower" /
  "tri_upper" (every rectangle split along the (t0,x0)-(t1,x1) resp.
  (t0,x1)-(t1,x0) diagonal), or "bilinear" (not affine; kept for comparison).
  Nodal bounds imply surface bounds by barycentric positivity (note app. B).
- ``solve_affine_dupire``: fully implicit Euler march of the forward Dupire
  equation in normalized strike x = K/F (eq. (forward_dupire_normalized)),
  dC/dT = 1/2 nu(T,x) x^2 d2C/dx2, C(0,x) = (1-x)^+, Dirichlet C(.,0) = 1 and
  C(., x_max) = 0, on a (possibly nonuniform) x grid with the central stencil
  of eq. (nonuniform_second_derivative) and the step of eq. (implicit_step).
  Optional forward sensitivities dU/dtheta per eq. (discrete_sensitivity) --
  every column shares the step's tridiagonal factor via a multi-RHS solve.

Coordinates here are *normalized strike* x (the note's convention), not the
log-moneyness k of volfit.models.localvol.pde: x = e^k, and prices are the
same normalized undiscounted forward calls as volfit.core.black.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.linalg import solve_banded
from scipy.spatial import Delaunay

_INTERP_MODES = ("delaunay", "tri_lower", "tri_upper", "bilinear")


@dataclass(frozen=True)
class AffineVarianceSurface:
    """Nodal local variances theta[i, j] at vertices (t_nodes[i], x_nodes[j]).

    The flat parameter vector (for calibration) is theta.ravel(): t-major,
    matching the note's tables (one row per tau, one column per xi).
    """

    t_nodes: np.ndarray  # vertex times, increasing, t_nodes[0] >= 0, shape (n_t,)
    x_nodes: np.ndarray  # vertex strikes, increasing, x_nodes[0] >= 0, shape (n_x,)
    theta: np.ndarray  # nodal local VARIANCES, shape (n_t, n_x)
    interp: str = "delaunay"

    def __post_init__(self) -> None:
        t = np.atleast_1d(np.asarray(self.t_nodes, dtype=float))
        x = np.atleast_1d(np.asarray(self.x_nodes, dtype=float))
        th = np.asarray(self.theta, dtype=float)
        object.__setattr__(self, "t_nodes", t)
        object.__setattr__(self, "x_nodes", x)
        object.__setattr__(self, "theta", th)
        if self.interp not in _INTERP_MODES:
            raise ValueError(f"interp must be one of {_INTERP_MODES}, got {self.interp!r}")
        if t.ndim != 1 or t.size < 2 or np.any(np.diff(t) <= 0):
            raise ValueError("t_nodes must be 1-D, >= 2 entries, strictly increasing")
        if x.ndim != 1 or x.size < 2 or np.any(np.diff(x) <= 0):
            raise ValueError("x_nodes must be 1-D, >= 2 entries, strictly increasing")
        if th.shape != (t.size, x.size):
            raise ValueError(f"theta must have shape {(t.size, x.size)}, got {th.shape}")
        if not np.all(np.isfinite(th)) or np.any(th <= 0.0):
            raise ValueError("nodal local variances must be finite and strictly positive")

    @property
    def n_params(self) -> int:
        return int(self.theta.size)

    def with_theta(self, theta_flat: np.ndarray) -> "AffineVarianceSurface":
        """Same vertex set / interp with new nodal values (calibration step)."""
        return AffineVarianceSurface(
            t_nodes=self.t_nodes,
            x_nodes=self.x_nodes,
            theta=np.asarray(theta_flat, dtype=float).reshape(self.theta.shape),
            interp=self.interp,
        )

    def _delaunay(self) -> Delaunay:
        """Cached qhull triangulation of the vertex set, in theta.ravel() order."""
        tri = getattr(self, "_tri_cache", None)
        if tri is None:
            tt, xx = np.meshgrid(self.t_nodes, self.x_nodes, indexing="ij")
            tri = Delaunay(np.column_stack([tt.ravel(), xx.ravel()]))
            object.__setattr__(self, "_tri_cache", tri)
        return tri

    # ----------------------------------------------------------- basis rows
    def basis(self, x: np.ndarray, t: float) -> np.ndarray:
        """Hat-function weights Phi[i, l]: nu(t, x_i) = Phi @ theta.ravel().

        Vectorized in x for scalar t; coordinates are clamped to the vertex
        hull (flat extrapolation), so PDE meshes may touch the boundary.
        Each row has <= 3 nonzeros for triangle modes, <= 4 for bilinear.
        """
        tn, xn = self.t_nodes, self.x_nodes
        x = np.asarray(x, dtype=float)
        t = float(min(max(t, tn[0]), tn[-1]))
        xc = np.clip(x, xn[0], xn[-1])

        if self.interp == "delaunay":
            tri = self._delaunay()
            pts = np.column_stack([np.full(xc.size, t), xc])
            simp = tri.find_simplex(pts, tol=1e-12)
            if np.any(simp < 0):  # clamped points lie in the hull; fuzz only
                raise RuntimeError("Delaunay point location failed inside the hull")
            tm = tri.transform[simp]
            b2 = np.einsum("nij,nj->ni", tm[:, :2], pts - tm[:, 2])
            lam = np.column_stack([b2, 1.0 - b2.sum(axis=1)])
            out = np.zeros((x.size, self.n_params))
            out[np.arange(x.size)[:, None], tri.simplices[simp]] = lam
            return out

        it = min(int(np.searchsorted(tn, t, side="right")) - 1, tn.size - 2)
        it = max(it, 0)
        u = (t - tn[it]) / (tn[it + 1] - tn[it])  # local time coordinate in [0, 1]
        ix = np.clip(np.searchsorted(xn, xc, side="right") - 1, 0, xn.size - 2)
        s = (xc - xn[ix]) / (xn[ix + 1] - xn[ix])  # local strike coordinate

        m = self.n_params
        n_x = xn.size
        out = np.zeros((x.size, m))
        rows = np.arange(x.size)
        # Flat-index columns of the 4 surrounding vertices (t-major ravel).
        c_aa = it * n_x + ix  # (t_lo, x_lo)
        c_ab = c_aa + 1  # (t_lo, x_hi)
        c_ba = c_aa + n_x  # (t_hi, x_lo)
        c_bb = c_ba + 1  # (t_hi, x_hi)

        if self.interp == "bilinear":
            out[rows, c_aa] += (1.0 - u) * (1.0 - s)
            out[rows, c_ab] += (1.0 - u) * s
            out[rows, c_ba] += u * (1.0 - s)
            out[rows, c_bb] += u * s
        elif self.interp == "tri_lower":
            # Diagonal (0,0)-(1,1): lower triangle has s <= u.
            lower = s <= u
            out[rows, c_aa] += np.where(lower, 1.0 - u, 1.0 - s)
            out[rows, c_ba] += np.where(lower, u - s, 0.0)
            out[rows, c_ab] += np.where(lower, 0.0, s - u)
            out[rows, c_bb] += np.where(lower, s, u)
        else:  # tri_upper, diagonal (0,1)-(1,0): lower triangle has u + s <= 1.
            lower = u + s <= 1.0
            out[rows, c_aa] += np.where(lower, 1.0 - u - s, 0.0)
            out[rows, c_ba] += np.where(lower, u, 1.0 - s)
            out[rows, c_ab] += np.where(lower, s, 1.0 - u)
            out[rows, c_bb] += np.where(lower, 0.0, u + s - 1.0)
        return out

    def variance(self, x: np.ndarray, t: float) -> np.ndarray:
        """Local variance nu_theta(t, x), vectorized in x for scalar t."""
        return self.basis(x, t) @ self.theta.ravel()


@dataclass(frozen=True)
class AffinePDESolution:
    """Forward solution U(t_req, x) (and sensitivities) at requested expiries."""

    x_grid: np.ndarray  # full strike grid incl. boundaries, shape (n_x,)
    expiries: np.ndarray  # sorted unique requested expiries, shape (n_exp,)
    prices: np.ndarray  # normalized calls, shape (n_exp, n_x)
    sens: np.ndarray | None  # dU/dtheta, shape (n_exp, n_x, m), or None

    def price_at(self, i_exp: int, x: np.ndarray | float) -> np.ndarray:
        """Observation operator R_j: linear interpolation in strike."""
        return np.interp(np.asarray(x, dtype=float), self.x_grid, self.prices[i_exp])

    def sens_at(self, i_exp: int, x: np.ndarray) -> np.ndarray:
        """d(price_at)/dtheta, shape (len(x), m), by the same linear rows."""
        if self.sens is None:
            raise ValueError("solution was computed without sensitivities")
        x = np.asarray(x, dtype=float)
        j = np.clip(np.searchsorted(self.x_grid, x) - 1, 0, self.x_grid.size - 2)
        wgt = (x - self.x_grid[j]) / (self.x_grid[j + 1] - self.x_grid[j])
        s = self.sens[i_exp]
        return (1.0 - wgt)[:, None] * s[j] + wgt[:, None] * s[j + 1]


def solve_affine_dupire(
    surface: AffineVarianceSurface,
    x_grid: np.ndarray,
    t_grid: np.ndarray,
    expiries,
    *,
    sensitivities: bool = False,
) -> AffinePDESolution:
    """Fully implicit Euler march of eq. (implicit_step) on the given grids.

    ``t_grid`` must start at 0 and contain every requested expiry exactly
    (the note: "force all quoted expiries to be time steps").  The local
    variance enters each step at the *new* time level t_{n+1} (matrix
    A^{n+1}), exactly as written in the note.  With ``sensitivities`` the
    full dU/dtheta is propagated per eq. (discrete_sensitivity); the source
    term uses the just-solved U^{n+1} including its boundary values, which
    folds the boundary derivative b^{n+1} contribution in for free.
    """
    x = np.asarray(x_grid, dtype=float)
    t = np.asarray(t_grid, dtype=float)
    if t[0] != 0.0 or np.any(np.diff(t) <= 0):
        raise ValueError("t_grid must start at 0 and increase strictly")
    exps = np.array(sorted({float(e) for e in expiries}))
    pos = np.searchsorted(t, exps)
    if np.any(pos >= t.size) or not np.allclose(t[pos], exps, rtol=0.0, atol=1e-12):
        raise ValueError("every requested expiry must be a t_grid point")
    want = {int(p): i for i, p in enumerate(pos)}

    n_x = x.size
    h = np.diff(x)  # h[i] = x[i+1] - x[i]
    hm, hp = h[:-1], h[1:]  # spacings around interior node i = 1..n_x-2
    xi2 = x[1:-1] ** 2
    a_m = xi2 / ((hm + hp) * hm)  # eq. (nonuniform_second_derivative) coeffs
    a_p = xi2 / ((hm + hp) * hp)
    a_0 = -(a_m + a_p)

    m = surface.n_params
    u = np.maximum(1.0 - x, 0.0)  # payoff (1 - x)^+, includes boundary values
    sens = np.zeros((n_x, m)) if sensitivities else None
    prices = np.empty((exps.size, n_x))
    out_sens = np.empty((exps.size, n_x, m)) if sensitivities else None
    if 0 in want:  # expiry 0 is not allowed by searchsorted above (t[0]=0 < exps)
        raise ValueError("expiries must be positive")

    for n in range(t.size - 1):
        dt = t[n + 1] - t[n]
        phi = surface.basis(x[1:-1], float(t[n + 1]))  # hat weights at new level
        nu = phi @ surface.theta.ravel()
        lo, di, up = nu * a_m, nu * a_0, nu * a_p

        ab = np.zeros((3, n_x - 2))  # banded I - dt A for solve_banded
        ab[0, 1:] = -dt * up[:-1]
        ab[1, :] = 1.0 - dt * di
        ab[2, :-1] = -dt * lo[1:]

        rhs = u[1:-1].copy()
        rhs[0] += dt * lo[0] * 1.0  # boundary U_0 = 1 (b^{n+1} of the note)
        if sensitivities:
            # Solve U and all m sensitivity columns against one factorization:
            # the sensitivity source needs U^{n+1}, which equals the first
            # solved column because the source enters the RHS additively.
            sol_u = solve_banded((1, 1), ab.copy(), rhs, check_finite=False)
            u_new = np.concatenate(([1.0], sol_u, [0.0]))
            # Source G[i, l] = phi_l(t_{n+1}, x_i) * (a- U_{i-1} + a0 U_i + a+ U_{i+1}).
            au = a_m * u_new[:-2] + a_0 * u_new[1:-1] + a_p * u_new[2:]
            rhs_s = sens[1:-1] + dt * phi * au[:, None]
            sens[1:-1] = solve_banded((1, 1), ab, rhs_s, check_finite=False)
            u = u_new
        else:
            sol_u = solve_banded(
                (1, 1), ab, rhs, overwrite_ab=True, overwrite_b=True, check_finite=False
            )
            u = np.concatenate(([1.0], sol_u, [0.0]))

        i_out = want.get(n + 1)
        if i_out is not None:
            prices[i_out] = u
            if sensitivities:
                out_sens[i_out] = sens

    return AffinePDESolution(x_grid=x, expiries=exps, prices=prices, sens=out_sens)
