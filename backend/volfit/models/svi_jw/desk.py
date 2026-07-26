"""Desk-unit ticket for a fitted slice (committee R5, challenge 11).

The JW handles are model coordinates in model units — v is a variance, psi a
total-volatility slope, p/c normalized variance slopes. A desk quotes none of
those. This module converts any smile (SmileModel: RawSVI, LQD, MCS) into the
instruments a desk actually trades:

  * ATM vol (the quoted convention: sqrt(w(0)/t));
  * 25-delta and 10-delta risk reversals and butterflies, strikes solved on
    the model smile via the FORWARD Black delta N(d1) (no rates convention —
    the fitter works in forward measure throughout);
  * the ACTUAL asymptotic wing slopes (the Lee/moment objects, not the
    normalized p/c indicators);
  * the var-swap vol (log-contract replication).

Plus the committee's missing derivative: ``forward_bump`` re-reads the SAME
ticket after a relative forward error dF/F — a wrong forward shifts every
log-moneyness by -dF/F and is easily misread as skew or wing movement; the
bump row shows exactly which desk quantities a pure forward mistake moves.

Analytics layer only: no UI ships JW handles (the note's product caution),
so this is the conversion layer any future JW workflow is REQUIRED to sit
behind, test-locked now rather than designed later.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.special import ndtr

from volfit.models.base import SmileModel
from volfit.models.diagnostics import numeric_lee_slopes, numeric_var_swap_w


@dataclass(frozen=True)
class DeskTicket:
    """One slice in desk units (decimal vol except the slopes)."""

    atm_vol: float
    rr25: float  # sigma(25d call) - sigma(25d put)
    bf25: float  # mean of the 25d vols minus ATM
    rr10: float
    bf10: float
    beta_left: float  # ACTUAL asymptotic total-variance slopes
    beta_right: float
    var_swap_vol: float


def delta_strike(slice_: SmileModel, delta: float, is_call: bool) -> float:
    """Log-moneyness where the forward Black delta of the MODEL smile equals
    ``delta`` (call) / ``-delta`` (put): bisection on N(d1), monotone in k."""
    target = delta if is_call else 1.0 - delta
    lo, hi = -3.0, 3.0
    for _ in range(90):
        mid = 0.5 * (lo + hi)
        w = max(float(slice_.implied_w(mid)), 1e-12)
        d1 = (-mid + 0.5 * w) / np.sqrt(w)
        if ndtr(d1) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _shifted(slice_: SmileModel, dk: float) -> SmileModel:
    """The same smile read with every log-moneyness shifted by ``dk`` — what
    a relative forward error dF/F = -dk does to every lookup."""

    class _S:
        def implied_w(self, k):
            return slice_.implied_w(np.asarray(k, dtype=float) + dk)

    return _S()


def desk_ticket(slice_: SmileModel, t: float) -> DeskTicket:
    """Read a slice in desk units (see the module docstring)."""
    sig = lambda k: float(np.sqrt(max(float(slice_.implied_w(k)), 1e-12) / t))  # noqa: E731
    atm = sig(0.0)
    out = {"atm_vol": atm}
    for d, tag in ((0.25, "25"), (0.10, "10")):
        kc = delta_strike(slice_, d, True)
        kp = delta_strike(slice_, d, False)
        out[f"rr{tag}"] = sig(kc) - sig(kp)
        out[f"bf{tag}"] = 0.5 * (sig(kc) + sig(kp)) - atm
    beta_left, beta_right = numeric_lee_slopes(slice_)
    vs_w = numeric_var_swap_w(slice_)
    return DeskTicket(
        beta_left=beta_left,
        beta_right=beta_right,
        var_swap_vol=float(np.sqrt(max(vs_w, 0.0) / t)),
        **out,
    )


def forward_bump(slice_: SmileModel, t: float, rel_bump: float = 0.01) -> DeskTicket:
    """The committee's missing derivative: the SAME ticket re-read after a
    relative forward error ``rel_bump`` (default +1%). Every log-moneyness
    shifts by -log(1 + rel_bump); on a skewed smile that reads as an ATM,
    RR and wing move even though the smile itself never changed — which is
    exactly why a forward mistake is misread as m/rho/psi movement."""
    return desk_ticket(_shifted(slice_, -float(np.log1p(rel_bump))), t)


def ticket_delta(base: DeskTicket, bumped: DeskTicket) -> DeskTicket:
    """Component-wise difference (bumped - base) — the bump-response row."""
    return replace(
        base,
        **{
            f: getattr(bumped, f) - getattr(base, f)
            for f in base.__dataclass_fields__
        },
    )
