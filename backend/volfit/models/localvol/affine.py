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


@dataclass(frozen=True)
class DupireSteps:
    """Theta-INDEPENDENT per-step data for the forward Dupire march.

    The hat-basis weights ``phi`` at each new time level depend only on the
    vertex set, the triangulation and the strike/time grids — never on the nodal
    values — so a calibration that solves the PDE for hundreds of trial thetas
    can build these once and reuse them every evaluation (see calibrate_affine).

    ``active_k[n]`` is the number of leading sensitivity columns that can be
    non-zero after step ``n``. A vertex's sensitivity column stays exactly zero
    until the march reaches the support of its hat, and the time vertices
    activate in increasing order, so the live columns are always a prefix
    ``[0:active_k]``; solving only that prefix is bit-for-bit identical to the
    full multi-RHS solve while skipping the structurally-zero tail.
    """

    interior_x: np.ndarray  # x[1:-1], the PDE interior nodes
    phi: list  # phi[n] = hat weights (n_interior x m) at level t[n+1]
    active_k: np.ndarray  # active_k[n] = live sensitivity-column count after step n


def precompute_dupire_steps(
    surface: AffineVarianceSurface, x_grid: np.ndarray, t_grid: np.ndarray
) -> DupireSteps:
    """Build the theta-independent per-step basis + active-column schedule.

    ``active_k`` is the running maximum of "highest non-zero basis column + 1"
    over the steps so far — derived from the actual basis sparsity, so it stays
    correct for every interpolation mode (delaunay/triangle/bilinear).
    """
    x = np.asarray(x_grid, dtype=float)
    t = np.asarray(t_grid, dtype=float)
    interior = x[1:-1]
    m = surface.n_params
    phi: list = []
    active_k = np.empty(t.size - 1, dtype=int)
    running_max = -1
    for n in range(t.size - 1):
        ph = surface.basis(interior, float(t[n + 1]))
        phi.append(ph)
        touched = np.flatnonzero(np.any(ph != 0.0, axis=0))
        if touched.size:
            running_max = max(running_max, int(touched[-1]))
        active_k[n] = min(running_max + 1, m)
    return DupireSteps(interior_x=interior, phi=phi, active_k=active_k)


def solve_affine_dupire(
    surface: AffineVarianceSurface,
    x_grid: np.ndarray,
    t_grid: np.ndarray,
    expiries,
    *,
    sensitivities: bool = False,
    steps: DupireSteps | None = None,
) -> AffinePDESolution:
    """Fully implicit Euler march of eq. (implicit_step) on the given grids.

    ``t_grid`` must start at 0 and contain every requested expiry exactly
    (the note: "force all quoted expiries to be time steps").  The local
    variance enters each step at the *new* time level t_{n+1} (matrix
    A^{n+1}), exactly as written in the note.  With ``sensitivities`` the
    full dU/dtheta is propagated per eq. (discrete_sensitivity); the source
    term uses the just-solved U^{n+1} including its boundary values, which
    folds the boundary derivative b^{n+1} contribution in for free.

    ``steps`` supplies precomputed theta-independent per-step basis weights and
    the active-column schedule (precompute_dupire_steps); a calibration reuses
    one ``DupireSteps`` across every trial theta. When omitted it is built here,
    so a standalone solve is unchanged. The sensitivity solve is restricted to
    the live column prefix ``[:active_k]`` — the tail columns are provably zero,
    so the result is bit-for-bit identical to solving all m columns.
    """
    x = np.asarray(x_grid, dtype=float)
    t = np.asarray(t_grid, dtype=float)
    if t[0] != 0.0 or np.any(np.diff(t) <= 0):
        raise ValueError("t_grid must start at 0 and increase strictly")
    if steps is None:
        steps = precompute_dupire_steps(surface, x, t)
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

    phis = steps.phi
    active_k = steps.active_k
    for n in range(t.size - 1):
        dt = t[n + 1] - t[n]
        phi = phis[n]  # theta-independent hat weights at the new level (cached)
        nu = phi @ surface.theta.ravel()
        lo, di, up = nu * a_m, nu * a_0, nu * a_p

        ab = np.zeros((3, n_x - 2))  # banded I - dt A for solve_banded
        ab[0, 1:] = -dt * up[:-1]
        ab[1, :] = 1.0 - dt * di
        ab[2, :-1] = -dt * lo[1:]

        rhs = u[1:-1].copy()
        rhs[0] += dt * lo[0] * 1.0  # boundary U_0 = 1 (b^{n+1} of the note)
        if sensitivities:
            sol_u = solve_banded((1, 1), ab.copy(), rhs, check_finite=False)
            u_new = np.concatenate(([1.0], sol_u, [0.0]))
            # Source G[i, l] = phi_l(t_{n+1}, x_i) * (a- U_{i-1} + a0 U_i + a+ U_{i+1}).
            # Only the first ``k`` sensitivity columns can be non-zero so far
            # (the rest stay at their zero initialization); solving the prefix
            # against the single step factorization is identical but cheaper.
            k = int(active_k[n])
            au = a_m * u_new[:-2] + a_0 * u_new[1:-1] + a_p * u_new[2:]
            rhs_s = sens[1:-1, :k] + dt * phi[:, :k] * au[:, None]
            sens[1:-1, :k] = solve_banded((1, 1), ab, rhs_s, check_finite=False)
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
