"""Model-agnostic wing-law descriptors: every family's tail contract, comparable.

Choosing a smile family is choosing an extrapolation law (book ch. 5, "the wing
as a stated choice"): LQD spans the full generalized-tail spectrum alpha in
[0, 1/2] (exponential -> intermediate -> Gaussian rate); SVI-JW and the
Multi-Core Sigmoid are STRUCTURALLY exponential (asymptotically straight
total-variance wings, w(k) ~ beta |k|); the bounded local-vol field is
STRUCTURALLY Gaussian-class (w(k, tau) <= v_max * tau on the whole strike
line, so the Lee slope is 0 — book ch. 4 rem. lvlee). This module only READS
the law off a fitted slice — it never changes a tail — so the three contracts
become one comparable ``WingLaw`` pair (left, right) per fit, reusing the
descriptor LQD introduced (volfit.models.lqd.basis.WingLaw).
"""

from __future__ import annotations

import numpy as np

from volfit.models.lqd.basis import WingLaw
from volfit.models.lqd.basis import wing_law as lqd_wing_law


def wing_laws_of(family: str, slice_) -> tuple[WingLaw, WingLaw] | None:
    """The (left, right) asymptotic wing laws of one fitted slice.

    ``family`` follows the compare/dispatch ids: "lqd" reads the generalized
    descriptor off its params; "svi" is exponential with the closed-form raw
    slopes b(1 -/+ rho); "sigmoid" is exponential with the analytic k-space
    Lee slopes (V3.1). Unknown families return None (no contract claimed).
    """
    if family == "lqd":
        return lqd_wing_law(slice_.params)
    if family == "svi":
        beta_l = float(slice_.b * (1.0 - slice_.rho))
        beta_r = float(slice_.b * (1.0 + slice_.rho))
        return (
            WingLaw(tail_class="exponential", exponent=1.0, coeff=beta_l),
            WingLaw(tail_class="exponential", exponent=1.0, coeff=beta_r),
        )
    if family == "sigmoid":
        beta_l, beta_r = slice_.lee_slopes()
        return (
            WingLaw(tail_class="exponential", exponent=1.0, coeff=float(beta_l)),
            WingLaw(tail_class="exponential", exponent=1.0, coeff=float(beta_r)),
        )
    return None


def lv_wing_laws(theta: np.ndarray, tau: float) -> tuple[WingLaw, WingLaw]:
    """The bounded local-vol sheet's wing contract at variance time ``tau``.

    With flat-clamped wings the marched field satisfies v <= max(theta), so
    total implied variance is bounded by ``max(theta) * tau`` on the whole
    strike line (book ch. 4 rem. lvlee) — the Gaussian-class constant, both
    sides. ``theta`` are the nodal local variances (AffineVarianceSurface).
    """
    cap = float(np.max(np.asarray(theta, dtype=float))) * float(tau)
    law = WingLaw(tail_class="gaussian", exponent=0.0, coeff=cap)
    return (law, law)
