"""Time-stepping plans for the affine Dupire march (implicit Euler, Rannacher, BDF2).

Every scheme the march supports is one instance of the same two-level step on
the interior unknowns (Docs/piecewise_affine_local_variance_calibration.tex,
eq. (generic_two_level_step)):

    (I − γ_n Δt_n A^{n+1}) U^{n+1}
        = α_n U^n − β_n U^{n−1} + ε_n Δt_n A^n U^n + boundary terms,

with the per-step coefficients

    implicit Euler        (γ, α, β, ε) = (1, 1, 0, 0)          eq. (implicit_step)
    Crank–Nicolson        (γ, α, β, ε) = (½, 1, 0, ½)          (Rannacher after start-up)
    BDF2, ω = Δt_n/Δt_{n−1}:
        γ = (1+ω)/(1+2ω),  α = (1+ω)²/(1+2ω),  β = ω²/(1+2ω),  ε = 0
                                                                eq. (bdf2_step)

and α − β = 1 for every scheme (constants are preserved). The sensitivities
follow by differentiating the same relation (eq. (generic_sensitivity_step)):
the θ-source is γ Δt (∂A^{n+1}) U^{n+1} + ε Δt (∂A^n) U^n, so a scheme with
ε = 0 keeps the implicit kernel's single fused source — the reason BDF2 costs
an implicit step plus one axpy per level, where Crank–Nicolson's explicit half
doubles the sensitivity work (the Stage-7 finding).

Why BDF2 for the calibration march (2026-09-08, the front-operator arc):
implicit Euler's payoff-kink error at the ATM of a front expiry is ~0.15 σ / N
for N steps on any front (2-day SPY, 27-day SPY, 27-day NVDA: 82 / 86 / 217 bp
at 2 steps, 6 / 8 / 15 at 32; several times that over the quoted strikes) —
first order, and the calibration then bends θ to cancel it. BDF2 is
second order AND L-stable (its amplification factor vanishes for the stiffest
modes), so it damps the kink like implicit Euler where Crank–Nicolson lets
the stiffest modes oscillate with amplification → −1 (the non-monotone
finding on coarse-x grids). ``build_plan`` starts every BDF2 march with one
implicit Euler step (no U^{−1}) and RESTARTS with one whenever the step grows
by more than ``BDF2_MAX_RATIO`` — the per-interval time grid jumps from a
short front's fine steps to the next interval's ceiling, and variable-step
BDF2 is only zero-stable for growth ratios below 1 + √2.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SCHEMES = ("implicit", "rannacher", "bdf2")

#: Step-growth ratio above which a BDF2 march restarts with an implicit Euler
#: step (variable-step BDF2 is zero-stable for ω < 1 + √2 ≈ 2.41; 2 keeps a
#: margin). Shrinking steps (ω < 1) never restart: β → 0 and the step tends
#: to implicit Euler smoothly.
BDF2_MAX_RATIO = 2.0


@dataclass(frozen=True)
class StepPlan:
    """Per-step coefficients (γ, α, β, ε) of the generic two-level step."""

    gamma: np.ndarray  # implicit weight on A^{n+1}
    alpha: np.ndarray  # weight on U^n
    beta: np.ndarray  # weight on U^{n-1} (subtracted); 0 ⇒ single-level
    eps: np.ndarray  # explicit weight on A^n U^n; 0 ⇒ no old-level operator

    @property
    def n_steps(self) -> int:
        return int(self.gamma.size)

    @property
    def is_implicit(self) -> bool:
        """True when every step is a plain implicit Euler step."""
        return bool(
            np.all(self.gamma == 1.0) and np.all(self.alpha == 1.0)
            and np.all(self.beta == 0.0) and np.all(self.eps == 0.0)
        )

    @property
    def uses_old_operator(self) -> bool:
        """True when some step applies A^n to the old level (Crank–Nicolson)."""
        return bool(np.any(self.eps != 0.0))

    @property
    def uses_two_levels(self) -> bool:
        """True when some step reads U^{n−1} (BDF2)."""
        return bool(np.any(self.beta != 0.0))


def bdf2_coefficients(dt_prev: float, dt: float) -> tuple[float, float, float]:
    """``(gamma, alpha, beta)`` of the variable-step BDF2 step, eq. (bdf2_step)."""
    w = float(dt) / float(dt_prev)
    den = 1.0 + 2.0 * w
    return (1.0 + w) / den, (1.0 + w) ** 2 / den, w * w / den


def build_plan(
    t_grid: np.ndarray,
    scheme: str = "implicit",
    rannacher_steps: int = 2,
    bdf2_max_ratio: float = BDF2_MAX_RATIO,
) -> StepPlan:
    """The per-step coefficient plan of ``scheme`` on ``t_grid``.

    "implicit": every step (1, 1, 0, 0). "rannacher": implicit Euler for the
    first ``rannacher_steps`` steps (the payoff-kink damping), Crank–Nicolson
    (½, 1, 0, ½) after. "bdf2": implicit Euler on step 0 and on every step whose
    length exceeds ``bdf2_max_ratio`` × the previous step (a restart), the
    variable-step BDF2 coefficients elsewhere.
    """
    if scheme not in SCHEMES:
        raise ValueError(f"time_scheme must be one of {SCHEMES}, got {scheme!r}")
    t = np.asarray(t_grid, dtype=float)
    dt = np.diff(t)
    n = dt.size
    gamma = np.ones(n)
    alpha = np.ones(n)
    beta = np.zeros(n)
    eps = np.zeros(n)
    if scheme == "rannacher":
        rann = max(int(rannacher_steps), 1)
        gamma[rann:] = 0.5
        eps[rann:] = 0.5
    elif scheme == "bdf2":
        for i in range(1, n):
            if dt[i] > bdf2_max_ratio * dt[i - 1]:
                continue  # restart: keep the implicit Euler coefficients
            gamma[i], alpha[i], beta[i] = bdf2_coefficients(dt[i - 1], dt[i])
    return StepPlan(gamma=gamma, alpha=alpha, beta=beta, eps=eps)
