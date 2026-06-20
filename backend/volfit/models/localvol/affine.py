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
from time import perf_counter

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
    #: Left-wing extrapolation: for x < x_nodes[0] the local variance continues
    #: LINEARLY with slope ``left_extrap_a`` x the slope of the first cell
    #: (between the two lowest vertices). 0.0 = flat (clamp to the x_min vertex,
    #: the default and the historical behavior); 1.0 = plain linear continuation;
    #: > 1 = steeper (a convex left wing keeps rising toward x = 0). The right wing
    #: stays flat-clamped. The cap is NOT applied here — variance rises freely.
    left_extrap_a: float = 0.0

    def __post_init__(self) -> None:
        t = np.atleast_1d(np.asarray(self.t_nodes, dtype=float))
        x = np.atleast_1d(np.asarray(self.x_nodes, dtype=float))
        th = np.asarray(self.theta, dtype=float)
        object.__setattr__(self, "t_nodes", t)
        object.__setattr__(self, "x_nodes", x)
        object.__setattr__(self, "theta", th)
        object.__setattr__(self, "left_extrap_a", float(self.left_extrap_a))
        if self.left_extrap_a < 0.0:
            raise ValueError("left_extrap_a must be >= 0")
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
            left_extrap_a=self.left_extrap_a,
        )

    def with_left_extrap_a(self, a: float) -> "AffineVarianceSurface":
        """Same surface with a different left-wing extrapolation slope multiple."""
        return AffineVarianceSurface(
            t_nodes=self.t_nodes, x_nodes=self.x_nodes, theta=self.theta,
            interp=self.interp, left_extrap_a=float(a),
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
    def _basis_clamped(self, xc: np.ndarray, t: float) -> np.ndarray:
        """Hat-function weights at coordinates ALREADY clamped to the hull.

        ``xc`` must lie in [x_nodes[0], x_nodes[-1]] and ``t`` in the t-node range
        (the callers clamp). This is the in-hull point location; left-wing linear
        extrapolation is layered on top by ``basis`` / ``basis_components``.
        """
        tn, xn = self.t_nodes, self.x_nodes
        xc = np.asarray(xc, dtype=float)

        if self.interp == "delaunay":
            tri = self._delaunay()
            pts = np.column_stack([np.full(xc.size, t), xc])
            simp = tri.find_simplex(pts, tol=1e-12)
            if np.any(simp < 0):  # clamped points lie in the hull; fuzz only
                raise RuntimeError("Delaunay point location failed inside the hull")
            tm = tri.transform[simp]
            b2 = np.einsum("nij,nj->ni", tm[:, :2], pts - tm[:, 2])
            lam = np.column_stack([b2, 1.0 - b2.sum(axis=1)])
            out = np.zeros((xc.size, self.n_params))
            out[np.arange(xc.size)[:, None], tri.simplices[simp]] = lam
            return out

        it = min(int(np.searchsorted(tn, t, side="right")) - 1, tn.size - 2)
        it = max(it, 0)
        u = (t - tn[it]) / (tn[it + 1] - tn[it])  # local time coordinate in [0, 1]
        ix = np.clip(np.searchsorted(xn, xc, side="right") - 1, 0, xn.size - 2)
        s = (xc - xn[ix]) / (xn[ix + 1] - xn[ix])  # local strike coordinate

        m = self.n_params
        n_x = xn.size
        out = np.zeros((xc.size, m))
        rows = np.arange(xc.size)
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

    def basis_components(
        self, x: np.ndarray, t: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """``(phi_base, phi_lin)`` such that nu(x, t) = (phi_base + a phi_lin) @ theta.

        ``phi_base`` is the flat-extrapolation basis (a = 0, the historical
        clamp); ``phi_lin`` is the per-point LEFT-wing linear-continuation delta:
        for x < x_nodes[0], d = (x − x0)/(x1 − x0) (< 0) and the row is
        d·(basis(x1) − basis(x0)), zero elsewhere. So nu picks up
        a·d·(nu(x1) − nu(x0)) below x0 — a linear wing with slope a × the first
        cell's slope. Both are linear in theta, so the calibration can treat ``a``
        as a free parameter with an analytic sensitivity (= phi_lin @ theta).
        """
        tn, xn = self.t_nodes, self.x_nodes
        x = np.asarray(x, dtype=float)
        t = float(min(max(t, tn[0]), tn[-1]))
        xc = np.clip(x, xn[0], xn[-1])
        phi_base = self._basis_clamped(xc, t)
        phi_lin = np.zeros_like(phi_base)
        below = x < xn[0]
        if np.any(below):
            b1 = self._basis_clamped(np.array([xn[1]]), t)[0]  # basis at x_nodes[1]
            d = (x[below] - xn[0]) / (xn[1] - xn[0])  # < 0
            phi_lin[below] = d[:, None] * (b1[None, :] - phi_base[below])
        return phi_base, phi_lin

    def basis(self, x: np.ndarray, t: float) -> np.ndarray:
        """Hat-function weights Phi[i, l]: nu(t, x_i) = Phi @ theta.ravel().

        Vectorized in x for scalar t. In-hull points use the triangulation /
        tensor interpolation; the right wing is flat-clamped; the LEFT wing
        (x < x_nodes[0]) continues linearly with slope ``left_extrap_a`` x the
        first cell's slope (``left_extrap_a`` = 0 ⇒ flat, the default).
        """
        if self.left_extrap_a == 0.0:  # flat: skip the phi_lin work (hot path)
            tn, xn = self.t_nodes, self.x_nodes
            x = np.asarray(x, dtype=float)
            t = float(min(max(t, tn[0]), tn[-1]))
            return self._basis_clamped(np.clip(x, xn[0], xn[-1]), t)
        phi_base, phi_lin = self.basis_components(x, t)
        return phi_base + self.left_extrap_a * phi_lin

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
    #: When the left-wing slope ``a`` is a free parameter, ``phi`` holds the
    #: flat-extrap base (a = 0) and ``phi_lin[n]`` the linear-continuation delta,
    #: so the solver forms phi(a) = phi + a * phi_lin per step (and an analytic
    #: a-sensitivity = phi_lin @ theta). None ⇒ ``a`` is baked into ``phi``.
    phi_lin: list | None = None


def precompute_dupire_steps(
    surface: AffineVarianceSurface,
    x_grid: np.ndarray,
    t_grid: np.ndarray,
    with_left_lin: bool = False,
) -> DupireSteps:
    """Build the theta-independent per-step basis + active-column schedule.

    ``active_k`` is the running maximum of "highest non-zero basis column + 1"
    over the steps so far — derived from the actual basis sparsity, so it stays
    correct for every interpolation mode (delaunay/triangle/bilinear).

    ``with_left_lin`` splits the basis into the flat-extrap base + the left-wing
    linear-continuation delta (``basis_components``) so the solver can treat the
    slope multiple ``a`` as a free parameter; otherwise ``a`` is baked into the
    stored basis via ``surface.basis`` (the default / fixed-a path).
    """
    x = np.asarray(x_grid, dtype=float)
    t = np.asarray(t_grid, dtype=float)
    interior = x[1:-1]
    m = surface.n_params
    n_steps = t.size - 1
    # Without the left-wing split, store the per-step basis as ONE contiguous
    # (n_steps, n_int, m) array: the banded march indexes ``phi[n]`` (a 2-D view, so
    # byte-identical), and the Numba vectorized-Thomas march (affine_march) consumes
    # the whole array directly. With the split (fit_left_a) keep the legacy lists.
    phi: list | np.ndarray = [] if with_left_lin else np.empty((n_steps, interior.size, m))
    phi_lin: list | None = [] if with_left_lin else None
    active_k = np.empty(n_steps, dtype=int)
    running_max = -1
    for n in range(n_steps):
        if with_left_lin:
            pb, pl = surface.basis_components(interior, float(t[n + 1]))
            phi.append(pb)
            phi_lin.append(pl)
            touched_arr = (pb != 0.0) | (pl != 0.0)
        else:
            pb = surface.basis(interior, float(t[n + 1]))
            phi[n] = pb
            touched_arr = pb != 0.0
        touched = np.flatnonzero(np.any(touched_arr, axis=0))
        if touched.size:
            running_max = max(running_max, int(touched[-1]))
        active_k[n] = min(running_max + 1, m)
    return DupireSteps(interior_x=interior, phi=phi, active_k=active_k, phi_lin=phi_lin)


def solve_affine_dupire(
    surface: AffineVarianceSurface,
    x_grid: np.ndarray,
    t_grid: np.ndarray,
    expiries,
    *,
    sensitivities: bool = False,
    steps: DupireSteps | None = None,
    left_a: float | None = None,
    fit_left_a: bool = False,
    timing: dict | None = None,
    time_scheme: str = "implicit",
    rannacher_steps: int = 2,
    engine: str = "banded",
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

    ``left_a`` overrides the surface's left-wing slope multiple for this solve;
    with ``fit_left_a`` an extra sensitivity column dU/da is propagated
    (analytically, source = (phi_lin @ theta) * gamma), appended after the m theta
    columns — so the calibration can optimise ``a`` jointly. Both need a
    ``steps`` built with ``with_left_lin=True`` (or steps=None here, which builds
    one); otherwise ``a`` is whatever is baked into ``steps.phi``.

    ``timing``, when a dict, accumulates wall seconds of the per-step banded
    solves into ``timing["value_s"]`` (the value march) and ``timing["sens_s"]``
    (the multi-RHS sensitivity march) — the Stage-0 instrumentation split. None
    (the default) is the zero-overhead hot path; standalone callers pass nothing.

    ``time_scheme`` (Stage 7) selects the time discretisation: "implicit" (the
    default — fully implicit Euler, 1st order, the byte-identical golden scheme),
    or "rannacher" — Crank-Nicolson (2nd order) after ``rannacher_steps`` implicit-
    Euler start-up steps that damp the payoff kink at x = 1 (plain CN would
    oscillate). 2nd order means a given accuracy is reached at a several-fold larger
    dt, so the live fit marches far fewer time steps per evaluation at equal
    accuracy (note "higher-order time stepping"). Rannacher is only applied when
    ``fit_left_a`` is False (the free-left-slope dU/da column keeps the implicit
    recursion); a "rannacher" request with ``fit_left_a`` falls back to implicit.
    """
    timed = timing is not None
    x = np.asarray(x_grid, dtype=float)
    t = np.asarray(t_grid, dtype=float)
    if t[0] != 0.0 or np.any(np.diff(t) <= 0):
        raise ValueError("t_grid must start at 0 and increase strictly")
    if steps is None:
        steps = precompute_dupire_steps(surface, x, t, with_left_lin=fit_left_a)
    a = float(left_a) if left_a is not None else surface.left_extrap_a
    use_lin = steps.phi_lin is not None
    # Crank-Nicolson is used only without the free-left-slope column (which keeps the
    # implicit dU/da recursion); the first ``rann`` steps stay implicit Euler to damp
    # the payoff kink (Rannacher start-up), so CN begins at step index ``rann`` >= 1.
    cn_enabled = time_scheme == "rannacher" and not fit_left_a
    rann = max(int(rannacher_steps), 1)
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
    n_cols = m + 1 if fit_left_a else m  # extra dU/da sensitivity column
    theta = surface.theta.ravel()
    u = np.maximum(1.0 - x, 0.0)  # payoff (1 - x)^+, includes boundary values
    sens = np.zeros((n_x, n_cols)) if sensitivities else None
    prices = np.empty((exps.size, n_x))
    out_sens = np.empty((exps.size, n_x, n_cols)) if sensitivities else None
    if 0 in want:  # expiry 0 is not allowed by searchsorted above (t[0]=0 < exps)
        raise ValueError("expiries must be positive")

    # Stage 6′: the Numba vectorized-Thomas march (~6× the banded path) handles the
    # common hot path — value + theta-sensitivities, implicit Euler, no free left
    # slope, with the contiguous (n_steps, n_int, m) basis. Everything else (value-
    # only, Rannacher CN, fit_left_a, or numba unavailable) keeps the banded march.
    if engine == "numba" and sensitivities and not fit_left_a and not use_lin \
            and time_scheme == "implicit" and isinstance(steps.phi, np.ndarray):
        from volfit.models.localvol.affine_march import march_value_sens, numba_available

        if numba_available():
            want_step = np.full(t.size - 1, -1, dtype=np.int64)
            for p, i in want.items():
                want_step[p - 1] = i
            pr, se = march_value_sens(
                steps.phi, theta, a_m, a_p, a_0, np.diff(t), steps.active_k,
                want_step, u, exps.size,
            )
            return AffinePDESolution(x_grid=x, expiries=exps, prices=pr, sens=se)

    phis = steps.phi
    active_k = steps.active_k
    nu_prev = None  # nu at the current (old) time level, carried for the CN explicit half
    phi_prev = None  # basis at the old level (= phis[n-1]), for the CN dA^n source
    for n in range(t.size - 1):
        dt = t[n + 1] - t[n]
        phi_base = phis[n]  # cached hat weights at the new level (flat-extrap base)
        phi = phi_base + a * steps.phi_lin[n] if use_lin else phi_base
        nu = phi @ theta
        # Crank-Nicolson on this step? (Rannacher: implicit for the first ``rann``.)
        is_cn = cn_enabled and n >= rann
        frac = 0.5 if is_cn else 1.0  # theta-weight on the IMPLICIT (new-level) operator
        lo, di, up = nu * a_m, nu * a_0, nu * a_p

        ab = np.zeros((3, n_x - 2))  # banded (I - frac*dt*A^{n+1}) for solve_banded
        ab[0, 1:] = -frac * dt * up[:-1]
        ab[1, :] = 1.0 - frac * dt * di
        ab[2, :-1] = -frac * dt * lo[1:]

        u_old = u  # full array at the old level (boundaries included), for the CN half
        rhs = u[1:-1].copy()
        au_old = None
        if is_cn:
            # explicit (old-level) half: + (1-frac)*dt * A^n U^n on the full stencil
            # (au_old[0] already carries the U_0 = 1 left boundary at level n).
            au_old = a_m * u_old[:-2] + a_0 * u_old[1:-1] + a_p * u_old[2:]
            rhs += (1.0 - frac) * dt * nu_prev * au_old
        rhs[0] += frac * dt * lo[0] * 1.0  # implicit (new-level) U_0 = 1 boundary
        if sensitivities:
            _t0 = perf_counter() if timed else 0.0
            sol_u = solve_banded((1, 1), ab.copy(), rhs, check_finite=False)
            if timed:
                timing["value_s"] += perf_counter() - _t0
            u_new = np.concatenate(([1.0], sol_u, [0.0]))
            # Source G[i, l] = phi_l(t_{n+1}, x_i) * (a- U_{i-1} + a0 U_i + a+ U_{i+1}).
            # Only the first ``k`` sensitivity columns can be non-zero so far
            # (the rest stay at their zero initialization); solving the prefix
            # against the single step factorization is identical but cheaper.
            k = int(active_k[n])
            au = a_m * u_new[:-2] + a_0 * u_new[1:-1] + a_p * u_new[2:]
            _t0 = perf_counter() if timed else 0.0
            if fit_left_a:
                # dU/da: same recursion, source (phi_lin @ theta) * gamma; appended
                # as the m-th column (always live once the wing region is touched).
                glin = steps.phi_lin[n] @ theta
                idx = np.concatenate([np.arange(k), [m]])
                src = np.concatenate(
                    [phi[:, :k] * au[:, None], (glin * au)[:, None]], axis=1
                )
                rhs_s = sens[1:-1, idx] + dt * src
                sens[1:-1, idx] = solve_banded((1, 1), ab, rhs_s, check_finite=False)
            elif is_cn:
                # Differentiate the CN step: (I - frac dt A^{n+1}) dU^{n+1} =
                #   (I + (1-frac) dt A^n) dU^n          [explicit half on the old sens]
                #   + frac dt (dA^{n+1}_l) U^{n+1}      [new-level source, phi @ au]
                #   + (1-frac) dt (dA^n_l) U^n          [old-level source, phi_prev @ au_old]
                old = sens[:, :k]
                expl = old[1:-1] + (1.0 - frac) * dt * nu_prev[:, None] * (
                    a_m[:, None] * old[:-2] + a_0[:, None] * old[1:-1] + a_p[:, None] * old[2:]
                )
                rhs_s = (
                    expl
                    + frac * dt * phi[:, :k] * au[:, None]
                    + (1.0 - frac) * dt * phi_prev[:, :k] * au_old[:, None]
                )
                sens[1:-1, :k] = solve_banded((1, 1), ab, rhs_s, check_finite=False)
            else:
                rhs_s = sens[1:-1, :k] + dt * phi[:, :k] * au[:, None]
                sens[1:-1, :k] = solve_banded((1, 1), ab, rhs_s, check_finite=False)
            if timed:
                timing["sens_s"] += perf_counter() - _t0
            u = u_new
        else:
            _t0 = perf_counter() if timed else 0.0
            sol_u = solve_banded(
                (1, 1), ab, rhs, overwrite_ab=True, overwrite_b=True, check_finite=False
            )
            if timed:
                timing["value_s"] += perf_counter() - _t0
            u = np.concatenate(([1.0], sol_u, [0.0]))

        nu_prev = nu  # becomes the old-level nu for the next step's CN half
        phi_prev = phi
        i_out = want.get(n + 1)
        if i_out is not None:
            prices[i_out] = u
            if sensitivities:
                out_sens[i_out] = sens

    return AffinePDESolution(x_grid=x, expiries=exps, prices=prices, sens=out_sens)
