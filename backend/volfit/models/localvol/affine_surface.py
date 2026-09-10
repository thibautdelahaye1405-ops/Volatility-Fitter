"""P1 piecewise-affine local-variance surface (Docs/piecewise_affine_local_variance_calibration.tex).

``AffineVarianceSurface``: continuous piecewise-affine local *variance*
nu_theta(t, x) = sum_l theta_l phi_l(t, x) (eq. (p1_lv)) on a tensor-product
vertex set.  ``interp`` picks the triangulation: "delaunay" (scipy/qhull
Delaunay of the vertices -- the convention that reproduces the note's quote
table to every published decimal, see tests), "tri_lower" / "tri_upper"
(every rectangle split along the (t0,x0)-(t1,x1) resp. (t0,x1)-(t1,x0)
diagonal), or "bilinear" (not affine; kept for comparison).  Nodal bounds
imply surface bounds by barycentric positivity (note app. B).

``sparse_dot`` / ``_sequential_nu`` are the row-sparse basis contractions the
surface and the Dupire march share (summation order matters: they reproduce
``phi @ theta`` bit for bit where the march must match the surface).

Split out of ``affine.py`` on 2026-09-10 (the 400-line policy); ``affine``
re-exports every name, so imports through it are unchanged.

Coordinates are *normalized strike* x (the note's convention), not the
log-moneyness k of volfit.models.localvol.pde: x = e^k, and prices are the
same normalized undiscounted forward calls as volfit.core.black.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
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

    def cell_diag_main(self) -> np.ndarray:
        """Per-cell diagonal orientation of the cached triangulation.

        On a tensor grid every cell's four corners are cocircular, so qhull
        tie-breaks each rectangle's split; this exposes the choice so a
        renderer can draw THE pricing triangulation instead of a convention
        of its own (note rem. degenerate-Delaunay).  Entry [i, j] is True
        when cell (i, j) is split along the 'main' diagonal
        (t_i, x_j) -- (t_{i+1}, x_{j+1}), False for the anti diagonal.
        """
        n_t, n_x = self.t_nodes.size, self.x_nodes.size
        edges: set[tuple[int, int]] = set()
        for s in self._delaunay().simplices:
            a, b, c = int(s[0]), int(s[1]), int(s[2])
            edges.add((min(a, b), max(a, b)))
            edges.add((min(a, c), max(a, c)))
            edges.add((min(b, c), max(b, c)))
        out = np.zeros((n_t - 1, n_x - 1), dtype=bool)
        for i in range(n_t - 1):
            for j in range(n_x - 1):
                out[i, j] = (i * n_x + j, (i + 1) * n_x + j + 1) in edges
        return out

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

    # ------------------------------------------------- row-sparse evaluation
    def _sparse_clamped(self, xc: np.ndarray, t: float) -> tuple[np.ndarray, np.ndarray]:
        """``(cols, vals)`` of the hat weights at ALREADY clamped coordinates:
        the (<= 4) vertices of each point's containing simplex / cell, columns
        ascending per row — the row-sparse twin of ``_basis_clamped`` with the
        same float per entry (the dense matrix is these weights scattered)."""
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
            cols = tri.simplices[simp]
            order = np.argsort(cols, axis=1, kind="stable")
            return np.take_along_axis(cols, order, 1), np.take_along_axis(lam, order, 1)
        it = min(int(np.searchsorted(tn, t, side="right")) - 1, tn.size - 2)
        it = max(it, 0)
        u = (t - tn[it]) / (tn[it + 1] - tn[it])
        ix = np.clip(np.searchsorted(xn, xc, side="right") - 1, 0, xn.size - 2)
        s = (xc - xn[ix]) / (xn[ix + 1] - xn[ix])
        n_x = xn.size
        c_aa = it * n_x + ix
        cols = np.column_stack([c_aa, c_aa + 1, c_aa + n_x, c_aa + n_x + 1])  # ascending
        if self.interp == "bilinear":
            vals = np.column_stack([(1.0 - u) * (1.0 - s), (1.0 - u) * s, u * (1.0 - s), u * s])
        elif self.interp == "tri_lower":
            lower = s <= u
            vals = np.column_stack([
                np.where(lower, 1.0 - u, 1.0 - s), np.where(lower, 0.0, s - u),
                np.where(lower, u - s, 0.0), np.where(lower, s, u),
            ])
        else:  # tri_upper
            lower = u + s <= 1.0
            vals = np.column_stack([
                np.where(lower, 1.0 - u - s, 0.0), np.where(lower, s, 1.0 - u),
                np.where(lower, u, 1.0 - s), np.where(lower, 0.0, u + s - 1.0),
            ])
        return cols, vals

    def _sparse_weights(self, x: np.ndarray, t: float) -> tuple[np.ndarray, np.ndarray]:
        """Row-sparse ``(cols, vals)`` of the FULL basis (left-wing linear
        continuation included), entries equal to the dense ``basis`` rows.

        Below x_nodes[0] the dense row is ``pb + a·(d·(b1 − pb))`` per column
        (basis_components), so each such point's entries are formed with
        exactly those operations over the union of its own simplex and the
        x_nodes[1] simplex; a vertex missing from one side enters as 0.0.
        Unused slots are (col 0, 0.0): they contribute exactly nothing."""
        tn, xn = self.t_nodes, self.x_nodes
        x = np.asarray(x, dtype=float)
        t = float(min(max(t, tn[0]), tn[-1]))
        cols, vals = self._sparse_clamped(np.clip(x, xn[0], xn[-1]), t)
        a = self.left_extrap_a
        below = x < xn[0]
        if a == 0.0 or not np.any(below):
            return cols, vals
        c1, v1 = self._sparse_clamped(np.array([xn[1]]), t)  # basis at x_nodes[1]
        c1, v1 = c1[0], v1[0]
        cb, vb = cols[below], vals[below]  # (n_b, k) base rows (all clamped to x0)
        d = (x[below] - xn[0]) / (xn[1] - xn[0])  # < 0
        # b1 looked up at the base columns (0.0 where the x1 simplex lacks them).
        b1_at_base = np.zeros_like(vb)
        for q in range(c1.size):
            b1_at_base += np.where(cb == c1[q], v1[q], 0.0)
        w_base = vb + a * (d[:, None] * (b1_at_base - vb))
        # x1-simplex columns absent from the base row: pb = 0.0 there.
        new = np.ones((cb.shape[0], c1.size), dtype=bool)
        for p in range(cb.shape[1]):
            new &= cb[:, [p]] != c1[None, :]
        w_new = np.where(new, 0.0 + a * (d[:, None] * (v1[None, :] - 0.0)), 0.0)
        c_new = np.where(new, c1[None, :], 0)
        cols_b = np.concatenate([cb, c_new], axis=1)
        vals_b = np.concatenate([w_base, w_new], axis=1)
        order = np.argsort(cols_b, axis=1, kind="stable")
        cols_b = np.take_along_axis(cols_b, order, 1)
        vals_b = np.take_along_axis(vals_b, order, 1)
        k = cols_b.shape[1]
        out_c = np.zeros((x.size, k), dtype=cols_b.dtype)
        out_v = np.zeros((x.size, k))
        out_c[:, : cols.shape[1]] = cols
        out_v[:, : cols.shape[1]] = vals
        out_c[below] = cols_b
        out_v[below] = vals_b
        return out_c, out_v

    def variance(self, x: np.ndarray, t: float) -> np.ndarray:
        """Local variance nu_theta(t, x), vectorized in x for scalar t.

        Row-sparse: the (<= 8) nonzero hat weights per point, accumulated in
        ASCENDING column order from 0.0 — the summation the Numba march kernels
        perform (a sequential ``s += phi[j]·theta[j]`` over all columns, where
        the zeros add exactly nothing), so a value-only reprice reproduces the
        calibrated march's local variance bit-for-bit without materializing
        the (n_x × m) dense basis every step (the pre-2026-09-03 cost driver of
        the display / converged-operator reprices: ~40 % of an LV fit)."""
        cols, vals = self._sparse_weights(x, t)
        return sparse_dot(cols, vals, self.theta.ravel())


def _sequential_nu(phi: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """``phi @ theta`` accumulated over each row's nonzeros in ascending column
    order from 0.0 (``sparse_dot`` on the row-sparse view of the dense basis)
    — the sequential sum the Numba kernels and ``variance`` perform, so a
    value-only banded march and a reprice agree bit-for-bit."""
    r, c = np.nonzero(phi)  # row-major: ascending column within each row
    n = phi.shape[0]
    counts = np.bincount(r, minlength=n)
    nnz = int(counts.max(initial=0))
    if nnz == 0:
        return np.zeros(n)
    starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    slot = np.arange(r.size) - starts[r]
    vals = np.zeros((n, nnz))
    cols = np.zeros((n, nnz), dtype=np.int64)
    vals[r, slot] = phi[r, c]
    cols[r, slot] = c
    return sparse_dot(cols, vals, theta)


def sparse_dot(cols: np.ndarray, vals: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """``sum_slot vals[:, slot] * theta[cols[:, slot]]`` accumulated slot by slot
    from 0.0 — with columns ascending per row this is exactly the sequential
    dense dot the march kernels compute (zero entries add nothing)."""
    out = np.zeros(cols.shape[0])
    for slot in range(cols.shape[1]):
        out += vals[:, slot] * theta[cols[:, slot]]
    return out


