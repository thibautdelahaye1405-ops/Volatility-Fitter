"""LQD parameter vector, Legendre basis and endpoint diagnostics.

Equation references are to Docs/lqd_model_note.tex:
  - basis definition        eq. (lqd_main)
  - smooth part g(u)        eq. (g_def)
  - endpoint scales A_L/A_R eqs. (AL), (AR)
  - Lee wing slopes         eqs. (lee_psi), (betaL), (betaR)
Generalized tails (book ch. 2, Papers/book/chapters/02_lqd):
  - tail exponents alpha_-/alpha_+  eqs. (skeleton), (xspeed)
  - sublinear wing law              eq. (rightsublinearwing)
  - moment boundaries               eq. (momentboundaries)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class LQDParams:
    """Coefficients (L, R, a_2, ..., a_N) of one LQD slice.

    `a[i]` holds the Legendre coefficient a_{i+2}; the model order is
    N = len(a) + 1 (so seven parameters means N = 6).

    ``alpha_left``/``alpha_right`` are the per-side tail exponents of the
    generalized family (book ch. 2 eq. skeleton): 0 keeps the exponential
    tail exactly (today's model), 1/2 is Gaussian rate. They are MODEL
    CONFIG, not theta components — ``to_vector``/``from_vector`` do not
    carry them, so the observation-filter state dimension, prior wire
    vectors and graph handle Jacobians are untouched at any alpha, and they
    are never estimated in-solver (the alpha -> 0 limit is nonuniform; the
    arc's ratified fixed-alpha scenario policy).
    """

    L: float
    R: float
    a: np.ndarray = field(default_factory=lambda: np.zeros(5))
    alpha_left: float = 0.0
    alpha_right: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "a", np.asarray(self.a, dtype=float))
        for name in ("alpha_left", "alpha_right"):
            alpha = getattr(self, name)
            if not (0.0 <= alpha <= 0.5):  # also rejects NaN
                raise ValueError(f"{name} = {alpha!r} outside the tail range [0, 1/2]")

    @property
    def order(self) -> int:
        """Highest Legendre degree N in the expansion."""
        return len(self.a) + 1

    def to_vector(self) -> np.ndarray:
        """Flatten to the optimizer vector theta = (L, R, a_2..a_N)."""
        return np.concatenate(([self.L, self.R], self.a))

    @staticmethod
    def from_vector(theta: np.ndarray) -> "LQDParams":
        theta = np.asarray(theta, dtype=float)
        return LQDParams(L=float(theta[0]), R=float(theta[1]), a=theta[2:].copy())


def legendre_matrix(n_max: int, x: np.ndarray) -> np.ndarray:
    """P_0(x) .. P_{n_max}(x) stacked as rows, via the stable three-term
    recursion (n+1) P_{n+1} = (2n+1) x P_n - n P_{n-1}  (eq. leg_recursion)."""
    x = np.asarray(x, dtype=float)
    out = np.empty((n_max + 1, x.size))
    out[0] = 1.0
    if n_max >= 1:
        out[1] = x
    for n in range(1, n_max):
        out[n + 1] = ((2 * n + 1) * x * out[n] - n * out[n - 1]) / (n + 1)
    return out


def g_eval(params: LQDParams, u: np.ndarray) -> np.ndarray:
    """Smooth part g(u) = (1-u)L + uR + sum a_n P_n(1-2u)  (eq. g_def)."""
    u = np.asarray(u, dtype=float)
    g = (1.0 - u) * params.L + u * params.R
    if params.a.size:
        legendre = legendre_matrix(params.order, 1.0 - 2.0 * u)
        g = g + params.a @ legendre[2:]
    return g


def endpoint_scales(params: LQDParams) -> tuple[float, float]:
    """Tail scales (A_L, A_R) = (e^{g(0)}, e^{g(1)})  (eqs. AL, AR).

    P_n(1) = 1 and P_n(-1) = (-1)^n, so the sums are over signed coefficients.
    The right scale must satisfy A_R < 1 for a finite forward (eq. AR_condition).
    """
    n = np.arange(2, params.order + 1)
    a_l = float(np.exp(params.L + params.a.sum()))
    a_r = float(np.exp(params.R + ((-1.0) ** n * params.a).sum()))
    return a_l, a_r


def lee_psi(p: np.ndarray | float) -> np.ndarray | float:
    """Lee moment function psi(p) = 2 - 4 (sqrt(p^2 + p) - p)  (eq. lee_psi).

    Evaluated in the algebraically identical form 2 - 4 / (sqrt(1 + 1/p) + 1),
    which is stable for extreme p: the naive form loses the +p under the root
    once p^2 + p rounds to p^2 (p > ~1e15, i.e. a tiny tail scale A) and then
    returns psi ~ 2 — the model-free ceiling — where the true limit is
    psi -> 0. p = 0 maps to psi = 2 exactly (1/p = inf -> the correction
    vanishes), matching the original form."""
    p = np.asarray(p, dtype=float)
    with np.errstate(divide="ignore"):
        return 2.0 - 4.0 / (np.sqrt(1.0 + 1.0 / p) + 1.0)


def lee_slopes(params: LQDParams) -> tuple[float, float]:
    """Asymptotic total-variance wing slopes (beta_L, beta_R).

    beta_L = psi(1 / A_L), beta_R = psi(1 / A_R - 1)  (eqs. betaL, betaR) in
    the exponential subclass. A POSITIVE tail exponent makes every moment on
    that side finite (book ch. 2 prop. strip), so its Lee slope is exactly 0
    — the wing then grows sublinearly per ``wing_law``.

    A_L / A_R are exp(...) so mathematically > 0, but a degenerate sparse-data
    fit (e.g. a far-dated node with few quotes) can drive the exponent extreme
    enough to UNDERFLOW to 0.0. Guard the reciprocals so the slopes take their
    finite limits — psi(1/A - ...) -> 0 as A -> 0 — instead of raising
    ZeroDivisionError, which 500s the smile endpoint on an otherwise-usable fit.
    """
    a_l, a_r = endpoint_scales(params)
    if params.alpha_left > 0.0:
        beta_l = 0.0
    else:
        beta_l = float(lee_psi(1.0 / a_l)) if a_l > 0.0 else 0.0
    if params.alpha_right > 0.0:
        beta_r = 0.0
    elif a_r >= 1.0:
        beta_r = 2.0
    elif a_r > 0.0:
        beta_r = float(lee_psi(1.0 / a_r - 1.0))
    else:  # A_R underflowed to 0: psi(+inf) -> 0
        beta_r = 0.0
    return beta_l, beta_r


@dataclass(frozen=True)
class WingLaw:
    """Asymptotic law of one total-variance wing (book ch. 2).

    ``exponential`` (alpha = 0):      w(k) ~ coeff * |k|   (coeff = the Lee
    slope, eq. leeclosed); ``intermediate`` (0 < alpha < 1/2):
    w(k) ~ coeff * |k|^exponent with exponent = (1-2a)/(1-a) in (0, 1)
    (eq. rightsublinearwing); ``gaussian`` (alpha = 1/2): w(k) -> coeff
    = 2 lambda^2, the variance of the matching Gaussian tail.
    """

    tail_class: str  # "exponential" | "intermediate" | "gaussian"
    exponent: float  # (1 - 2 alpha) / (1 - alpha); 1 at alpha = 0, 0 at 1/2
    coeff: float


def _one_wing_law(alpha: float, lam: float, lee_beta: float) -> WingLaw:
    if alpha == 0.0:
        return WingLaw(tail_class="exponential", exponent=1.0, coeff=lee_beta)
    exponent = (1.0 - 2.0 * alpha) / (1.0 - alpha)
    coeff = 0.5 * (lam / (1.0 - alpha)) ** (1.0 / (1.0 - alpha))
    cls = "gaussian" if alpha == 0.5 else "intermediate"
    return WingLaw(tail_class=cls, exponent=exponent, coeff=coeff)


def wing_law(params: LQDParams) -> tuple[WingLaw, WingLaw]:
    """Per-side asymptotic wing descriptors (left, right).

    The plotting / symmetric-tail-row abstraction over the alpha branches:
    everything downstream that used to reason from the Lee slopes alone can
    read (class, exponent, coefficient) instead — eq. rightsublinearwing
    evaluated at this slice's tail scales, collapsing to the exact Lee
    conversion (eq. leeclosed) in the exponential subclass and to the
    constant 2 lambda^2 at Gaussian rate.
    """
    a_l, a_r = endpoint_scales(params)
    beta_l, beta_r = lee_slopes(params)
    return (
        _one_wing_law(params.alpha_left, a_l, beta_l),
        _one_wing_law(params.alpha_right, a_r, beta_r),
    )
