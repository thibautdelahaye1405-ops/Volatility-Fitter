"""Matrix-free Gauss-Newton solver for the affine local-vol calibration (Stage 5).

STATUS (2026-09-09): **SHIPPED as the production DEFAULT** — ``OptionsSettings.lvSolver
= "gn"`` — for the MID and the BID-ASK / HAIRCUT fit targets alike, with the Numba
march active and no free-left-slope var-swap path (var-swap fits, the robust IRLS
re-solves and the banded-march fallback run TRF). Two loops in one function: the
mid target runs the SHIPPED loop (projected step, Nielsen damping, data-only stall
— byte-identical since 2026-06-20); the band targets run the ACTIVE-SET loop of
``affine_activeset`` — box and hinge aware, the model scores the step it actually
takes, a trial is accepted when the true cost drops — on the shared-block operator
of ``affine_operator``. On the SPY weekly / Bloomberg SPY / NVDA fixtures under the
desk options (haircut, 20 nodes, convex wing) a band fit runs 2.5–4× faster than
TRF at the same or a better target fit (rms to target within 0.03 bp, converged rms
within 1 bp) — ROADMAP wrap 2026-09-09b. Before that loop the band objective was
gated to TRF: the old projected step clipped to the box AFTER the solve and scored
the linear model along the clipped step, so half its steps were rejected on a
negative predicted reduction while the cost fell, and the hinge rows were blind to
every quote about to cross a band edge. The same loop on the mid target is a
benchmark-pack adjudication candidate (2–2.5× faster, a lower objective, the
1-year far-wing plateau repricing ~1.5 bp worse on the refined operator) — not
shipped. Automatic TRF fallback on breakdown.

HISTORY (2026-06-20, kept because the lesson generalizes): the FIRST verdict was
"not viable" — before the compiled march, both solvers ran to the 200-eval cap, the
per-eval PDE sensitivity march (not the SVD) was the bottleneck at <=440 vertices,
and GN's stiff projected-LM needed ~1.7x TRF's evals while its tight inner-lsmr made
each eval costlier (net ~1.4x slower; it converged in 8 evals only on the clean
zero-residual synthetic). Stage 6' (the Numba march) collapsed the per-eval cost,
the dense-SVD share came to dominate, and the same solver won — promoted to default
the same day it re-shipped. See ``Docs/localvol_calibration_perf_roadmap.md``
Stage 5.

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

Box bounds [v_lo, v_hi] are enforced by **active-set projection** — since
2026-09-09 inside the step itself: a component the projection cuts is pinned at
its bound and the free part re-solved (``affine_activeset.active_set_step``,
which also flips the band hinge rows to the side the step predicts), so the
model reduction is read along the step taken; the projected-gradient norm gates
convergence (preferred over a sigmoid reparameterisation, which worsens
conditioning in the bound-binding wings — roadmap Stage 5).

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
from scipy.sparse.linalg import lsmr

from volfit.models.localvol.affine_activeset import active_set_step
from volfit.models.localvol.affine_operator import LinearizedJacobian

__all__ = ["GNResult", "LinearizedJacobian", "gauss_newton"]


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
    model=None,
    trace: list | None = None,
) -> GNResult:
    """Projected Levenberg-Marquardt Gauss-Newton with a matrix-free lsmr step.

    ``evaluate(p)`` returns a tuple whose first two entries are the residual
    vector ``r(p)`` and the dense Jacobian ``J(p)`` (the same callback the dense
    TRF path uses, so the two solvers see an identical model). Minimises
    ½‖r(p)‖² subject to ``lb <= p <= ub``.

    Each outer step solves the LM-damped, column-preconditioned linear least
    squares  min_y ‖J·diag(s)·y + r‖² + μ‖y‖²  by lsmr (matrix-free), sets the
    trial step Δ = s·y, projects p+Δ onto the box, and accepts/rejects on the
    actual-vs-predicted reduction ratio (Nielsen damping update). That is the
    SHIPPED loop of the mid target (``model`` None), byte-identical since
    2026-06-20.

    ``model`` (a ``StepModel``, the band objectives — 2026-09-09) switches to
    the ACTIVE-SET loop: the step is refined by ``affine_activeset.
    active_set_step`` (clipped components pinned and the free ones re-solved,
    the hinge rows re-linearised on the side the step predicts), the model
    scores the step it actually takes, a trial is ACCEPTED when the true cost
    decreases, the damping follows a three-band rule (÷3 above ρ 0.75, ×2
    below 0.25) and a total-cost improvement counts as stall progress. The
    same loop on the mid target is a benchmark-pack adjudication candidate
    (ROADMAP wrap 2026-09-09b: 2–2.5× faster, a lower objective, the far-wing
    plateau of the 1-year row repricing ~1.5 bp worse on the refined
    operator), so the mid target keeps the shipped loop.

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

    active = model is not None  # the band objectives ride the active-set loop
    cur = evaluate(p)
    res, jac = cur[:2]
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

    # The active-set loop also counts a TOTAL-COST improvement by ``stall_rtol``
    # as progress: a band fit warm-started from a mid surface sits at its
    # data-block minimum from the outset — the band objective's optimum is
    # SMOOTHER, every descent step raises the anchor misfit — and the data-only
    # rule stalled it at the start point, returning the mid surface unchanged.
    stall = {"best": _opt_rms(res), "best_cost": cost, "since": 0, "x": p.copy()}
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

        if active:
            # The LM-damped lsmr step, projected onto the box and refined until
            # its box / hinge active set is self-consistent (no PDE solve).
            actual_step, r_pred, info = active_set_step(cur, lin, p, lo, hi, mu, lsmr_tol, model)
            if actual_step is None:
                break  # numerical breakdown -> caller falls back to TRF
            p_trial = p + actual_step
        else:
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
            info = {}

        cur_t = evaluate(p_trial)
        res_t, jac_t = cur_t[:2]
        nfev += 1
        cost_t = 0.5 * float(res_t @ res_t)

        if active:
            # Model reduction along the step actually taken: the piecewise model's
            # residual at p + Δ (exact hinge on the linearised prices; linear
            # elsewhere), so a clipped or edge-crossing step is scored correctly.
            predicted = cost - 0.5 * float(r_pred @ r_pred)
            actual = cost - cost_t
            accepted = cost_t < cost
            # The ratio drives the damping only: a decreasing step the model did
            # not foresee (predicted <= 0) is accepted with the damping left as is.
            rho = actual / predicted if predicted > 0.0 else (0.5 if accepted else -1.0)
        else:
            # Gauss-Newton model reduction along the PROJECTED step (exact for the
            # linearised residual r + J·Δ): predicted = cost - ½‖r + J·Δ‖².
            j_step = lin.apply_jacobian(actual_step)
            predicted = -float(res @ j_step) - 0.5 * float(j_step @ j_step)
            actual = cost - cost_t
            rho = actual / predicted if predicted > 0.0 else -1.0
            accepted = rho > 1e-4 and cost_t < cost
        if trace is not None:  # per-iteration record (diagnostics only)
            trace.append(dict(
                nfev=nfev, cost=cost, cost_t=cost_t, predicted=predicted, actual=actual, rho=rho, mu=mu,
                step=float(np.linalg.norm(actual_step)), accepted=accepted, **info,
                res=res, res_t=res_t, opt_rms=_opt_rms(res), opt_rms_t=_opt_rms(res_t),
            ))

        if accepted:
            step_norm = float(np.linalg.norm(actual_step))
            p, res, lin, cur = p_trial, res_t, _as_lin(jac_t), cur_t  # accept the trial linearisation
            njev += 1
            g = lin.apply_jacobian_transpose(res)
            if active:
                # Three-band trust rule: a well-predicted step earns a lighter
                # damping, a poorly predicted one a heavier, a middling one leaves
                # it alone (Nielsen's continuous shrink loosened the damping after
                # EVERY decent step and settled the crawl into a one-accept-one-
                # reject cycle on the band fits).
                if rho > 0.75:
                    mu /= 3.0
                elif rho < 0.25:
                    mu *= 2.0
            else:
                # Nielsen: shrink damping by the step quality.
                mu *= max(1.0 / 3.0, 1.0 - (2.0 * rho - 1.0) ** 3)
            nu = 2.0  # reset the rejection ramp
            # GN early-stop bookkeeping: only ACCEPTED iterates (legitimate, monotone
            # in total cost) move ``stall["x"]`` — never a noisy rejected lsmr trial —
            # so a too-loose inner solve can't latch the stop onto a fluke point. A
            # genuine option-block improvement resets the counter.
            q = _opt_rms(res)
            progress = q < stall["best"] * (1.0 - stall_rtol)
            if active and cost_t < stall["best_cost"] * (1.0 - stall_rtol):
                progress = True
            if progress:
                stall["best"] = min(stall["best"], q)
                stall["best_cost"] = cost_t
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
            cur = evaluate(p)
            res, jac = cur[:2]
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
