"""Matrix-free Gauss-Newton solver for the affine local-vol calibration (Stage 5).

STATUS (2026-06-20): **explored, NOT viable as a production speed-up at the current
tensor-grid sizes — kept gated off (``calibrate_affine(gn=...)`` only, no app wiring)
as a seed for the future ≳1000-vertex non-tensor "bowtie" regime.** On the real
SPY/NVDA Bloomberg benchmark this LOSES to dense TRF: both solvers run to the
200-eval cap, so the SVD is *not* the bottleneck at ≤440 vertices (the per-eval PDE
sensitivity march is, shared by both), and GN's stiff, bound-constrained projected-LM
needs ~1.7× TRF's evals to reach the same surface (≈339 vs the 200 cap) while its
tight inner-lsmr makes each eval costlier — net ~1.4× slower (it converges in 8 evals
only on the clean, zero-residual, in-bounds synthetic case). See
``Docs/localvol_calibration_perf_roadmap.md`` Stage 5. The robust per-eval win is
Stage 6 (Numba march). The module + tests below remain correct and are the starting
point should the bowtie grid (where the SVD genuinely dominates) be built.

The dense ``scipy.optimize.least_squares(method="trf")`` path (affine_calib) does a
trust-region **dense SVD of the (M_resid x m) Jacobian every iteration** —
O(m^3) at large vertex counts, the documented ~86 s / 533-vertex wall. The
roughness / convex / front-tie blocks that swell M_resid are 3-nnz-per-row band
stencils, so the SVD throws away the structure.

This module replaces that outer solver with a **projected Levenberg-Marquardt
Gauss-Newton** loop whose step is solved **matrix-free** by ``scipy.sparse.linalg
.lsmr`` — only Jacobian-vector products, never JᵀJ, never an SVD. The badly-scaled
problem (ATM/front nodes strongly identified, far-wing/late-time nodes weakly) is
handled by a **column-equilibration (Jacobi) preconditioner**: lsmr solves in the
scaled variable y = θ/s with s_j = 1/‖J_·j‖, so the columns are ~unit norm and the
inner solve converges in a handful of iterations. (This is the missing ingredient
behind the earlier ``tr_solver='lsmr'`` failure — that was unpreconditioned lsmr
inside trf's machinery; see memory/calibration-perf.md.)

Box bounds [v_lo, v_hi] are enforced by **active-set projection**: the trial step
is clipped to the box and the projected-gradient norm gates convergence
(preferred over a sigmoid reparameterisation, which worsens conditioning in the
bound-binding wings — roadmap Stage 5).

The dense Jacobian from one sensitivity-carrying PDE solve is reused as the
linear-operator oracle (``LinearizedJacobian``), so the GN step is provably
consistent with the dense path; the win is purely in the linear algebra (no SVD).
``apply_jacobian`` / ``apply_jacobian_transpose`` expose the tangent / adjoint
matvecs the note's Stage 5 specifies, validated by three identity tests
(test_affine_gn): Jv vs finite differences, ⟨Jv, w⟩ = ⟨v, Jᵀw⟩, and a gradient
α-test.

The solver returns a small ``GNResult`` mirroring the ``scipy`` OptimizeResult
fields ``calibrate_affine`` consumes (x / nfev / njev / status / cost / optimality
/ active_mask / message), plus a ``converged`` flag the caller uses to **fall back
to dense TRF** when the iterative solve stalls.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse.linalg import LinearOperator, lsmr


@dataclass
class LinearizedJacobian:
    """The Jacobian J of one linearisation as a matrix-free linear operator.

    Exposes the products an inexact-Newton step needs without forming JᵀJ or an
    SVD: ``apply_jacobian(v) = J·v`` (tangent), ``apply_jacobian_transpose(w) = Jᵀ·w``
    (adjoint / gradient), and ``column_scale`` (the Jacobi preconditioner 1/‖col‖).

    J is stored as a top **dense data block** ``jac`` (the option/var-swap rows,
    dense in the vertices their expiry touches) optionally stacked over a **sparse
    regularisation block** ``reg`` (the roughness / convex / front-tie rows, 3-nnz
    per row). Keeping ``reg`` sparse makes both the matvec (O(nnz) not O(M_reg·n))
    and the assembly (no dense reg materialisation) cheap — the bulk of the GN
    per-eval cost after the SVD is gone. ``reg=None`` ⇒ ``jac`` IS the whole matrix
    (the legacy dense path; the identity tests cover both).
    """

    jac: np.ndarray  # dense (M_data, n) data block (or the whole matrix if reg None)
    reg: object = None  # optional sparse (M_reg, n) regularisation block, stacked below

    @property
    def shape(self) -> tuple[int, int]:
        m = self.jac.shape[0] + (self.reg.shape[0] if self.reg is not None else 0)
        return (m, self.jac.shape[1])

    def to_dense(self) -> np.ndarray:
        """The full dense Jacobian (data over reg) — for a scipy TRF fallback."""
        if self.reg is None:
            return self.jac
        return np.vstack([self.jac, np.asarray(self.reg.todense())])

    def apply_jacobian(self, v: np.ndarray) -> np.ndarray:
        """Tangent action J·v (directional derivative of the residual in v)."""
        v = np.asarray(v, dtype=float)
        dv = self.jac @ v
        if self.reg is None:
            return dv
        return np.concatenate([dv, self.reg @ v])

    def apply_jacobian_transpose(self, w: np.ndarray) -> np.ndarray:
        """Adjoint action Jᵀ·w (e.g. the gradient Jᵀr of ½‖r‖²)."""
        w = np.asarray(w, dtype=float)
        if self.reg is None:
            return self.jac.T @ w
        md = self.jac.shape[0]
        return self.jac.T @ w[:md] + self.reg.T @ w[md:]

    def column_scale(self, floor: float = 1e-12) -> np.ndarray:
        """Jacobi preconditioner s_j = 1/‖J_·j‖ (equilibrates column norms).

        Columns with a vanishing norm (a vertex no quote/penalty touches) get the
        floor so the scaled column stays finite; the bound projection keeps such a
        parameter pinned anyway.
        """
        col2 = np.einsum("ij,ij->j", self.jac, self.jac)
        if self.reg is not None:
            col2 = col2 + np.asarray(self.reg.power(2).sum(axis=0)).ravel()
        return 1.0 / np.sqrt(np.maximum(col2, floor))

    def scaled_operator(self, scale: np.ndarray) -> LinearOperator:
        """``A = J·diag(scale)`` as a SciPy LinearOperator (for the lsmr step).

        lsmr sees only the matvec ``J(scale·y)`` and the rmatvec ``scale·(Jᵀw)`` —
        no dense factorisation. Solving in y = θ/scale is the preconditioning.
        """
        m, n = self.shape
        s = np.asarray(scale, dtype=float)
        return LinearOperator(
            (m, n),
            matvec=lambda y: self.apply_jacobian(s * y),
            rmatvec=lambda w: s * self.apply_jacobian_transpose(w),
        )


@dataclass
class GNResult:
    """Outcome of ``gauss_newton`` in the subset of ``scipy`` OptimizeResult fields
    ``calibrate_affine`` reads, plus ``converged`` (drives the TRF fallback)."""

    x: np.ndarray
    cost: float
    optimality: float
    nfev: int
    njev: int
    status: int
    active_mask: np.ndarray
    message: str
    converged: bool


def _as_bounds(
    lb: float | np.ndarray, ub: float | np.ndarray, n: int
) -> tuple[np.ndarray, np.ndarray]:
    """Broadcast scalar / array box bounds to length-n vectors."""
    lo = np.full(n, lb, dtype=float) if np.isscalar(lb) else np.asarray(lb, dtype=float)
    hi = np.full(n, ub, dtype=float) if np.isscalar(ub) else np.asarray(ub, dtype=float)
    return lo, hi


def _projected_gradient(
    g: np.ndarray, p: np.ndarray, lb: np.ndarray, ub: np.ndarray, tol: float = 1e-12
) -> np.ndarray:
    """Bound-projected gradient: zero the components pushing INTO an active bound.

    At a box minimum the free components vanish and the bound-active components
    only push outward, so ‖proj grad‖ is the correct first-order stationarity
    measure for the active-set method (matches scipy trf's ``optimality``).
    """
    pg = g.copy()
    pg[(p <= lb + tol) & (g > 0.0)] = 0.0
    pg[(p >= ub - tol) & (g < 0.0)] = 0.0
    return pg


def _active_mask(
    p: np.ndarray, lb: np.ndarray, ub: np.ndarray, tol: float = 1e-12
) -> np.ndarray:
    """-1 at the lower bound, +1 at the upper, 0 free (scipy's convention)."""
    mask = np.zeros(p.size, dtype=int)
    mask[p <= lb + tol] = -1
    mask[p >= ub - tol] = 1
    return mask


def gauss_newton(
    evaluate,
    p0: np.ndarray,
    lb: float | np.ndarray,
    ub: float | np.ndarray,
    *,
    max_nfev: int = 200,
    gtol: float = 1e-8,
    xtol: float = 1e-8,
    ftol: float = 1e-8,
    lsmr_tol: float = 1e-10,
    max_outer: int | None = None,
    stall_window: int = 0,
    stall_rtol: float = 5e-3,
    n_opt_rows: int = 0,
) -> GNResult:
    """Projected Levenberg-Marquardt Gauss-Newton with a matrix-free lsmr step.

    ``evaluate(p)`` returns a tuple whose first two entries are the residual
    vector ``r(p)`` and the dense Jacobian ``J(p)`` (the same callback the dense
    TRF path uses, so the two solvers see an identical model). Minimises
    ½‖r(p)‖² subject to ``lb <= p <= ub``.

    Each outer step solves the LM-damped, column-preconditioned linear least
    squares  min_y ‖J·diag(s)·y + r‖² + μ‖y‖²  by lsmr (matrix-free), sets the
    trial step Δ = s·y, projects p+Δ onto the box, and accepts/rejects on the
    actual-vs-predicted reduction ratio (Nielsen damping update).

    ``lsmr_tol`` is deliberately TIGHT (1e-10): the expensive unit is each outer
    iteration's sensitivity PDE solve, while the inner lsmr does only cheap dense
    matvecs, so solving the step accurately to take a near-full Newton step (and
    thus minimise outer PDE solves) is the right trade — a loose inner tol crawls
    in tiny steps and inflates the outer count many-fold.

    Convergence:
    projected-gradient (``gtol``), cost decrease (``ftol``), or step size
    (``xtol``). ``converged`` is False if the loop exhausts its budget or the
    damping diverges, signalling the caller to fall back to dense TRF.
    """
    p = np.asarray(p0, dtype=float).copy()
    n = p.size
    lo, hi = _as_bounds(lb, ub, n)
    p = np.clip(p, lo, hi)
    if max_outer is None:
        max_outer = max(50, 2 * max_nfev)

    def _as_lin(j):
        return j if isinstance(j, LinearizedJacobian) else LinearizedJacobian(j)

    res, jac = evaluate(p)[:2]
    lin = _as_lin(jac)
    nfev = njev = 1
    cost = 0.5 * float(res @ res)
    g = lin.apply_jacobian_transpose(res)

    # Stage 8 early-stop, GN flavour: track the best OPTION-BLOCK misfit and stop
    # once it has not improved by ``stall_rtol`` over ``stall_window`` evals, returning
    # the best iterate. GN converges slowly on stiff names (and would otherwise grind
    # to the eval cap then fall back to TRF); stopping at the stall point gives the
    # good surface cheaply — the whole point of the cheap-march + no-SVD GN path.
    def _opt_rms(r):
        block = r[:n_opt_rows] if n_opt_rows else r
        return float(np.sqrt(np.mean(block * block)))

    stall = {"best": _opt_rms(res), "since": 0, "x": p.copy()}
    # LM damping lives in the COLUMN-EQUILIBRATED space: after preconditioning the
    # scaled Hessian AᵀA has a ~unit diagonal, so a dimensionless O(1e-3) damping is
    # the natural seed (a raw max-diag(JᵀJ) seed would be orders of magnitude too
    # stiff here and stall every step). Nielsen's update then adapts it.
    mu = 1e-3
    nu = 2.0
    status = 0
    converged = False

    for _ in range(max_outer):
        optimality = float(np.max(np.abs(_projected_gradient(g, p, lo, hi)))) if n else 0.0
        if optimality < gtol:
            status, converged = 1, True
            break
        if nfev >= max_nfev:
            break

        scale = lin.column_scale()
        a_op = lin.scaled_operator(scale)
        # lsmr solves min ‖A y - b‖² + damp²‖y‖² with A = J·diag(scale), b = -r;
        # the damping ½μ‖y‖² is Marquardt scaling (∝ diag(JᵀJ)) in real units.
        sol = lsmr(
            a_op, -res, damp=np.sqrt(mu),
            atol=lsmr_tol, btol=lsmr_tol, maxiter=4 * n + 50, conlim=0.0,
        )
        step = scale * sol[0]
        if not np.all(np.isfinite(step)):
            break  # numerical breakdown -> caller falls back to TRF

        p_trial = np.clip(p + step, lo, hi)
        actual_step = p_trial - p
        res_t, jac_t = evaluate(p_trial)[:2]
        nfev += 1
        cost_t = 0.5 * float(res_t @ res_t)

        # Gauss-Newton model reduction along the PROJECTED step (exact for the
        # linearised residual r + J·Δ): predicted = cost - ½‖r + J·Δ‖².
        j_step = lin.apply_jacobian(actual_step)
        predicted = -float(res @ j_step) - 0.5 * float(j_step @ j_step)
        actual = cost - cost_t
        rho = actual / predicted if predicted > 0.0 else -1.0

        if rho > 1e-4 and cost_t < cost:
            step_norm = float(np.linalg.norm(actual_step))
            p, res, lin = p_trial, res_t, _as_lin(jac_t)  # accept the trial linearisation
            njev += 1
            g = lin.apply_jacobian_transpose(res)
            # Nielsen: shrink damping by the step quality, reset the rejection ramp.
            mu *= max(1.0 / 3.0, 1.0 - (2.0 * rho - 1.0) ** 3)
            nu = 2.0
            # GN early-stop bookkeeping: only ACCEPTED iterates (legitimate, monotone
            # in total cost) move ``stall["x"]`` — never a noisy rejected lsmr trial —
            # so a too-loose inner solve can't latch the stop onto a fluke point. A
            # genuine option-block improvement resets the counter.
            q = _opt_rms(res)
            if q < stall["best"] * (1.0 - stall_rtol):
                stall["best"] = q
                stall["since"] = 0
                stall["x"] = p.copy()
            else:
                stall["since"] += 1
            if actual < ftol * cost:
                status, converged = 2, True
                break
            if step_norm < xtol * (xtol + float(np.linalg.norm(p))):
                status, converged = 3, True
                break
            cost = cost_t
        else:
            stall["since"] += 1  # a rejected step is also "no progress"
            mu *= nu
            nu *= 2.0
            if not np.isfinite(mu) or mu > 1e16:
                break  # damping diverged -> TRF fallback

        # Stall: the best accepted option-block misfit has not improved by
        # ``stall_rtol`` for ``stall_window`` iterations (accepts-with-tiny-gain or
        # rejects) -> return the best accepted iterate; do NOT fall back to TRF.
        if stall_window > 0 and stall["since"] >= stall_window:
            p = stall["x"]
            res, jac = evaluate(p)[:2]
            g = _as_lin(jac).apply_jacobian_transpose(res)
            cost = 0.5 * float(res @ res)
            status, converged = 4, True
            break

    return GNResult(
        x=p,
        cost=cost,
        optimality=float(np.max(np.abs(_projected_gradient(g, p, lo, hi)))) if n else 0.0,
        nfev=nfev,
        njev=njev,
        status=status,
        active_mask=_active_mask(p, lo, hi),
        message=(
            "matrix-free Gauss-Newton converged"
            if converged
            else "matrix-free Gauss-Newton did not converge (TRF fallback)"
        ),
        converged=converged,
    )
