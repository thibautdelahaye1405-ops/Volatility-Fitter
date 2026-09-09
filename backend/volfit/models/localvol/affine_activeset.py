"""Active-set step for the matrix-free Gauss-Newton LV solver (box + band aware).

The projected LM step of ``affine_gn.gauss_newton`` used to be ONE lsmr solve
followed by a clip onto the variance box, and the linear model was then scored
along the CLIPPED step it never solved for. On stiff real data the early steps
push far-wing vertices well outside the box, the clip rewrites the step, and
the model predicts an INCREASE while the true cost drops — traced 2026-09-09
on the Bloomberg SPY haircut fit: iteration 2 predicted −3608, actual +1419,
REJECTED; 59 of its 119 steps went that way, each one a wasted PDE solve. The
bid-ask / haircut objectives add a second discontinuity: the hinge rows are
zero inside the band, so the model ignores every quote about to cross an edge
(SPY weekly bid-ask: 30–250 quotes crossed per step; predicted +516, actual
−87).

Both are active-set effects, and both are handled here without a single extra
PDE solve. The step is refined by cheap lsmr re-solves (dense matvecs only)
until its active set is self-consistent:

  * box — components the clip cut are PINNED at their bound (zero column
    scale; their displacement moves to the right-hand side) and the free
    components are re-solved around them;
  * hinge — the option rows are re-linearised on the side of the band the
    linearised prices land on: a quote predicted to leave the band gets its
    signed distance to that edge as residual and its price row as Jacobian, a
    quote predicted to enter gets a zero row — the piecewise-linear model of
    the hinge on top of the linearised PDE prices;

and the predicted reduction is read from that same piecewise model (the exact
hinge on the linearised prices), so the accept / reject decision and the
Levenberg-Marquardt damping see the objective the step will actually meet.

``StepModel`` is the small protocol the solver uses; ``LinearStepModel`` is
the mid objective (no hinge, the box handling alone) and ``BandStepModel`` the
bid-ask / haircut block of ``affine_calib`` (volfit.calib.band conventions:
residual rows ``[violation (n) | anchor (n) | …]``, sign +1 above hi, −1
below lo, 0 inside). Locks: tests/test_affine_gn.py (the clipped step's
prediction is exact on a linear problem; the band model reproduces the band
residual; GN lands the TRF band surface on the golden case).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from scipy.sparse.linalg import lsmr

from volfit.calib.band import band_violation, band_violation_sign

#: Re-solve passes per outer step: 1 = the plain projected step; the second
#: pins the components the box clipped and flips the hinge rows the first
#: step crossed. A third pass bought nothing measurable on the fixtures and
#: cost a full lsmr solve per step.
MAX_PASSES = 2
#: Safety box in REAL units: a vertex's local variance moves by at most this
#: factor (up or down) per outer step. The Jacobi-equilibrated lsmr step is
#: O(1) in every direction that reduces the model, so on the first cold steps
#: a weakly identified far-wing / late-time vertex (tiny column) would fly by
#: orders of magnitude for a negligible model gain — traced 2026-09-09: step
#: norms of 10–12 in variance units from a 0.04 seed, 20+ vertices parked on
#: the variance cap, a converged-operator error three times TRF's. The box is
#: deliberately WIDE (vol ×2 per step): a tight adaptive one (tried at 1.5
#: down to 1.01) clipped dozens of vertices per step in the crawl phase, the
#: pinning passes never settled, and every rejected step carried a negative
#: predicted reduction — the LM damping μ is the step controller, this is the
#: guard rail, pinned like any bound inside the passes.
TRUST_RATIO = 4.0
#: Hinge rows still flipping between passes that the loop tolerates (a quote
#: oscillating on an edge has a ~zero residual either way): max(1, n / 200).
STATUS_SLACK = 200


class StepModel(Protocol):
    """What the solver needs to know about the residual's piecewise structure.

    ``cur`` is the caller's evaluate tuple at the current iterate (its first two
    entries are the residual and the Jacobian); ``lin`` the current
    ``LinearizedJacobian`` (the solver's wrapped operator).
    """

    def status(self, cur: tuple, step: np.ndarray | None) -> np.ndarray:
        """Active-set label per hinge row at ``p + step`` under the linearised
        prices (``step`` None = the current point). Empty when there is no hinge."""

    def linearize(self, cur: tuple, lin, status: np.ndarray) -> tuple[np.ndarray, object]:
        """(residual, operator) of the piecewise model linearised at ``status``."""

    def predict(self, cur: tuple, lin, step: np.ndarray) -> np.ndarray:
        """The model residual at ``p + step`` (exact hinge on linearised prices)."""


class LinearStepModel:
    """The smooth objective: the residual is linear in the step (no hinge)."""

    _EMPTY = np.zeros(0)

    def status(self, cur: tuple, step: np.ndarray | None) -> np.ndarray:
        return self._EMPTY

    def linearize(self, cur: tuple, lin, status: np.ndarray) -> tuple[np.ndarray, object]:
        return cur[0], lin

    def predict(self, cur: tuple, lin, step: np.ndarray) -> np.ndarray:
        return cur[0] + lin.apply_jacobian(step)


@dataclass(frozen=True)
class BandStepModel:
    """The band objective's option block as a piecewise-linear step model.

    ``cur`` is calibrate_affine's evaluate tuple ``(res, jac, sol, p, z, jp)``:
    ``p`` the normalized call prices of the quotes, ``jp`` their price
    sensitivities (n × m). The residual's first ``n`` rows are the
    vega-normalized violations ``band_violation(p, lo, hi) / eta`` and the next
    ``n`` the soft mid anchor ``sqrt_anchor · (p − mid) / eta`` — linear in
    ``p``, so only the violation rows carry the hinge.
    """

    eta: np.ndarray
    p_lo: np.ndarray
    p_hi: np.ndarray

    @property
    def n(self) -> int:
        return int(self.eta.size)

    def _prices(self, cur: tuple, step: np.ndarray | None) -> np.ndarray:
        p, jp = cur[3], cur[5]
        return p if step is None else p + jp @ step

    def status(self, cur: tuple, step: np.ndarray | None) -> np.ndarray:
        """+1 above the band, −1 below, 0 inside — except on a COLLAPSED band
        (lo == hi: a haircut wider than the quote's half-spread, the common SPY
        case): there both sides give the same least-squares row, (p − mid)²,
        so the side label is fixed at +1 and never counts as a change (it
        flipped for every quote crossing mid and kept the passes from
        settling)."""
        sign = band_violation_sign(self._prices(cur, step), self.p_lo, self.p_hi)
        return np.where(self.p_hi > self.p_lo, sign, 1.0)

    def linearize(self, cur: tuple, lin, status: np.ndarray) -> tuple[np.ndarray, object]:
        """Violation rows on the side ``status`` names: residual = the signed
        distance to that edge (negative while the quote is still inside — the
        room it has before the hinge engages), Jacobian = ± its price row."""
        res, p, jp = cur[0], cur[3], cur[5]
        if np.array_equal(status, self.status(cur, None)):
            return res, lin  # the current linearisation IS the one at this status
        n = self.n
        edge = np.where(status > 0.0, self.p_hi, np.where(status < 0.0, self.p_lo, p))
        r_eff = res.copy()
        r_eff[:n] = status * (p - edge) / self.eta
        if lin.row_scales is not None:  # the shared-block operator: re-scale, no copy
            scales = (status / self.eta,) + tuple(lin.row_scales[1:])
            return r_eff, type(lin)(lin.jac, lin.reg, row_scales=scales, extra=lin.extra)
        jac_eff = lin.jac.copy()  # the dense data block (rows [:n] are the violations)
        jac_eff[:n] = (status / self.eta)[:, None] * jp
        return r_eff, type(lin)(jac_eff, lin.reg)

    def predict(self, cur: tuple, lin, step: np.ndarray) -> np.ndarray:
        """Every row linear in the step, except the violations: the exact hinge
        of the linearised prices."""
        res, p, jp = cur[0], cur[3], cur[5]
        out = res + lin.apply_jacobian(step)
        out[: self.n] = band_violation(p + jp @ step, self.p_lo, self.p_hi) / self.eta
        return out


def active_set_step(
    cur: tuple,
    lin,
    p: np.ndarray,
    lo: np.ndarray,
    hi: np.ndarray,
    mu: float,
    lsmr_tol: float,
    model: StepModel,
    max_passes: int = MAX_PASSES,
    trust_ratio: float = TRUST_RATIO,
) -> tuple[np.ndarray | None, np.ndarray | None, dict]:
    """One LM step, refined until its box + hinge active sets are self-consistent.

    Solves ``min_y ‖A y + r_eff‖² + μ‖y‖²`` matrix-free (A = J_eff·diag(scale),
    the Jacobi-preconditioned operator) and projects onto the step box — the
    variance box ``[lo, hi]`` intersected with ``[p / trust_ratio, p ·
    trust_ratio]``; components the projection cut are pinned at their edge and
    the hinge rows flipped to the side the linearised prices predict, then the
    free part is re-solved (lsmr warm-started from the previous pass) — up to
    ``max_passes`` lsmr solves, no PDE evaluation. Returns ``(step,
    predicted_residual, info)`` with ``info = {passes, itn}``; ``step`` is
    None on a non-finite solve (the caller falls back to TRF). (A Coleman-Li
    interior scaling of the columns — TRF's asymptotic approach to a bound —
    was tried and dropped: it slowed every fit and parked MORE vertices on
    the cap on the synthetic chain; ROADMAP wrap 2026-09-09b.)
    """
    n = p.size
    # The safety box is multiplicative (local VARIANCES are positive); a
    # non-positive parameter keeps the plain bounds so the box never collapses.
    positive = p > 0.0
    lo_s = np.where(positive, np.maximum(lo, p / trust_ratio), lo)
    hi_s = np.where(positive, np.minimum(hi, p * trust_ratio), hi)
    fixed = np.zeros(n, dtype=bool)
    delta_fixed = np.zeros(n)
    status = model.status(cur, None)
    slack = max(1, status.size // STATUS_SLACK)
    step = None
    y0 = None
    passes = 0
    itn = 0
    for passes in range(1, max_passes + 1):
        r_eff, lin_eff = model.linearize(cur, lin, status)
        scale = lin_eff.column_scale()
        scale[fixed] = 0.0  # a pinned component has no column: lsmr leaves it at 0
        rhs = -(r_eff + lin_eff.apply_jacobian(delta_fixed))
        if y0 is not None:
            y0[fixed] = 0.0
        sol = lsmr(
            lin_eff.scaled_operator(scale), rhs, damp=np.sqrt(mu),
            atol=lsmr_tol, btol=lsmr_tol, maxiter=4 * n + 50, conlim=0.0, x0=y0,
        )
        itn += int(sol[2])
        y0 = sol[0]
        raw = delta_fixed + scale * y0
        if not np.all(np.isfinite(raw)):
            return None, None, {"passes": passes, "itn": itn}
        target = p + raw
        clipped = ~fixed & ((target < lo_s) | (target > hi_s))
        step = np.clip(target, lo_s, hi_s) - p
        new_status = model.status(cur, step)
        if not clipped.any() and int(np.count_nonzero(new_status != status)) <= slack:
            break
        fixed |= clipped
        delta_fixed[clipped] = step[clipped]
        status = new_status
    return step, model.predict(cur, lin, step), {"passes": passes, "itn": itn}
