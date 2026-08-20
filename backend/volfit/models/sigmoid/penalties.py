"""No-butterfly penalty blocks of the Multi-Core SIV calibrator.

Split out of ``calibrate.py`` (V3.1 file split — the 400-line policy): the
penalty-path Durrleman g evaluator, the put-wing regularizer grid
(FINDINGS_calibration_arb R6), the belly-repair hinge rows (V3.1 leg 2 — the
sigmoid mirror of the SVI committee-R2 repair rider), and the central-FD
helper the calibrator uses for its hybrid analytic+FD Jacobian blocks.
``calibrate.py`` re-exports the historical names (``WING_PENALTY_BASE``,
``_eval_g``) so the public import surface is unchanged.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from volfit.models.sigmoid.kernels import gatheral_g_from_z, hat, hat_p, hat_pp, siv_base
from volfit.models.sigmoid.seeding import _V_FLOOR

#: Put-wing no-butterfly regularizer (FINDINGS_calibration_arb R6). The zero-wing
#: hats can break convexity (Durrleman g < 0) in the UNQUOTED tail; a soft penalty
#: sqrt(lambda_j) * max(-g(z_j), 0) on a grid extending past the traded range pushes
#: g >= 0 where no quote disciplines it. Zero on an arb-free slice ⇒ byte-identical.
#: ``WING_PENALTY_BASE`` is the base strength (variance² units, like the SVI penalty),
#: scaled by ``OptionsSettings.sivWingPenaltyPct`` at the service; the put side is
#: weighted ``_WING_PUT_FACTOR`` heavier (F4: ~64% of violations are put-side).
WING_PENALTY_BASE = 1e3
_WING_PAD = 2.0  # how far past the quoted z-range the penalty grid extends (z units)
_WING_GRID = 49  # grid points over the extended range
_WING_PUT_FACTOR = 2.0

#: Belly-repair hinge margin (V3.1 leg 2): rows sqrt(WING_PENALTY_BASE) *
#: max(-g + margin, 0) on a grid over the TRADED range — zero on a certified
#: slice, and the margin pushes a repaired dip slightly PAST zero so the belly
#: certificate's own numerical tolerance (diagnostics.CERT_G_TOL) passes
#: cleanly. Mirrors ``svi_jw.calibrate._BELLY_MARGIN`` exactly (committee R2).
BELLY_MARGIN = 2e-4


def _eval_g(theta: np.ndarray, z: np.ndarray, n_cores: int, t: float, sigma_ref: float) -> np.ndarray:
    """Durrleman/Gatheral g(z) of the model slice (>= 0 ⇔ no butterfly arb).

    PENALTY-path g, deliberately different from the diagnostic
    ``MultiCoreSiv.gatheral_g``: here a trial theta whose raw variance collapses
    to (or below) the floor keeps its RAW derivatives against the floored value,
    which makes 1/w huge and g massively negative — a harsh de-facto barrier
    that charges the wing penalty exactly where a hat is driving variance
    through zero. The diagnostic instead reports the priced (floored) curve's
    own functional; collapsed slices fail its separate positivity check."""
    v0, s0, k0, z0, kp, kc = theta[:6]
    v, vz, vzz = siv_base(z, v0, s0, k0, z0, kp, kc)
    for r in range(n_cores):
        alpha, c, h, kappa = theta[6 + 4 * r : 10 + 4 * r]
        v = v + alpha * hat(z, c, h, kappa)
        vz = vz + alpha * hat_p(z, c, h, kappa)
        vzz = vzz + alpha * hat_pp(z, c, h, kappa)
    return gatheral_g_from_z(z, np.maximum(v, _V_FLOOR), vz, vzz, t, sigma_ref)


def wing_penalty_grid(
    z: np.ndarray, wing_penalty: float
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """(wing_z, wing_sqrt_lambda) of the put-wing regularizer, or (None, None).

    The grid extends ``_WING_PAD`` z-units past the traded range into the
    unquoted tails, weighted heavier on the put side. None ⇒ off ⇒
    byte-identical (applied only in the refine stage, never the base seeding)."""
    if wing_penalty <= 0.0 or not z.size:
        return None, None
    wing_z = np.linspace(z.min() - _WING_PAD, z.max() + _WING_PAD, _WING_GRID)
    put_factor = np.where(wing_z < 0.0, _WING_PUT_FACTOR, 1.0)
    return wing_z, np.sqrt(wing_penalty * put_factor)


def belly_rows(
    theta: np.ndarray, belly_z: np.ndarray, n_cores: int, t: float, sigma_ref: float
) -> np.ndarray:
    """Belly-repair hinge rows WING_PENALTY_BASE * max(-g + margin, 0).

    The sigmoid mirror of the SVI R2 repair rider — the row multiplier is
    WING_PENALTY_BASE itself (weight 1e6 in the squared cost), exactly the
    ``penalty_weight``-multiplied hinge of ``svi_jw.calibrate``: deliberately
    STRONGER than the wing regularizer's sqrt-lambda rows, because these rows
    only ever run on a REPAIR refit after a failed certificate — dominating
    the residual dip is the point. Passed only by the display repair path
    (models/display.py), so a clean first fit never sees them — byte-identical."""
    g = _eval_g(theta, belly_z, n_cores, t, sigma_ref)
    return WING_PENALTY_BASE * np.maximum(-g + BELLY_MARGIN, 0.0)


def fd_rows(
    fn: Callable[[np.ndarray], np.ndarray], theta: np.ndarray, eps: float = 1e-6
) -> np.ndarray:
    """Central finite difference of one residual block — the hybrid-Jacobian
    pattern: the dominant fit/ridge/calendar blocks stay analytic while the
    small penalty blocks (wing g, belly g, extrap) are FD'd cheaply."""
    base = fn(theta)
    jac = np.empty((base.size, theta.size))
    for p in range(theta.size):
        d = np.zeros_like(theta)
        d[p] = eps
        jac[:, p] = (fn(theta + d) - fn(theta - d)) / (2.0 * eps)
    return jac
