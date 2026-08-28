"""Merge two operator-prior blocks into ONE residual block.

The Note 15 §6.3 carve-out (Docs/handoff/notes/15_kalman_computed_trust.md
:268-278 — "Persistence auto-exclusion is hard-coded" — and the survivors row
of the lock table at :378): under an ACTIVE observation filter the Kalman
prediction prior enters the fit as the ungated ``filterATM`` / ``filterSkew``
/ ``filterCurv`` stencil rows (legs at k ∈ {−h, 0, h}, h = 0.06), and every
persistence builder overlapping those three handles is dropped so the previous
state is never counted twice. The tail-persistence WingL / WingR rows
(volfit.calib.operators) measure each side's deep-wing vol SLOPE between the
two outermost anchor-delta strikes — a quantity DISJOINT from the filtered
handles — so with ``OptionsSettings.wingOperatorsUnderActiveFilter`` they may
persist alongside the MAP rows (the "separate wing path" of the tail-
persistence design; the historical switch keeps them OFF with ATM/RR/BF).

Every parametric calibrator consumes a single ``OperatorPriorTarget`` block,
so the two blocks are STACKED here: names / prior values / scales / weights /
diagnostics concatenated, the leg vectors concatenated, and the coefficient
matrix block-diagonal (zero-padded). Each row still reads only its own legs
and ``operator_residuals`` is row-wise, so the merged block reproduces both
blocks' residual rows unchanged. The two blocks must share the node's ``tau``.
"""

from __future__ import annotations

import numpy as np

from volfit.calib.operators import OperatorPriorTarget


def merge_operator_targets(
    left: OperatorPriorTarget | None, right: OperatorPriorTarget | None
) -> OperatorPriorTarget | None:
    """Stack ``left`` over ``right`` into one block; identity on a missing side.

    ``right is None`` returns ``left`` itself (the SAME object, no copy — the
    flag-OFF path stays byte-identical); ``left is None`` returns ``right``.
    Rows keep their order (``left`` first), legs are concatenated in the same
    order and ``coeff`` is block-diagonal so a row never touches the other
    block's legs. Raises ``ValueError`` when the blocks disagree on ``tau``."""
    if right is None:
        return left
    if left is None:
        return right
    if float(left.tau) != float(right.tau):
        raise ValueError(
            f"operator blocks disagree on tau: {left.tau!r} vs {right.tau!r}"
        )
    n_l, m_l = left.coeff.shape
    n_r, m_r = right.coeff.shape
    coeff = np.zeros((n_l + n_r, m_l + m_r))
    coeff[:n_l, :m_l] = left.coeff
    coeff[n_l:, m_l:] = right.coeff
    return OperatorPriorTarget(
        names=list(left.names) + list(right.names),
        legs_k=np.concatenate([left.legs_k, right.legs_k]),
        coeff=coeff,
        prior_value=np.concatenate([left.prior_value, right.prior_value]),
        scale=np.concatenate([left.scale, right.scale]),
        active_lambda=np.concatenate([left.active_lambda, right.active_lambda]),
        tau=float(left.tau),
        diagnostics=list(left.diagnostics) + list(right.diagnostics),
    )
