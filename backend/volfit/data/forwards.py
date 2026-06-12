"""Implied forwards via put-call parity regression.

Design intent (ROADMAP Phase 3, decision recorded there): forwards are
implied *robustly from quotes* before any model is fitted — explicit
dividend curves come later as a fallback.  For each expiry, parity gives

    C(K) - P(K) = D (F - K),

linear in K.  Regressing y = C_mid - P_mid on K by least squares,

    y = a + b K   with   a = D F,  b = -D
    =>  D = -b,   F = a / D,

which uses every paired strike at once and averages out quote noise.  The
residual RMS of the regression is reported as a quality diagnostic; expiries
with fewer than three paired strikes (or a non-positive implied discount)
are skipped — too little data to trust a two-parameter fit.

Stale-quote robustness ([REQ 2026-06-12]): live chains carry stale deep-wing
mids whose parity residuals are dollars, not cents (observed rms 2-30 on a
few live expiries), and plain least squares lets one such pair tilt the
whole forward.  The regression therefore iterates: fit, measure residuals,
drop pairs beyond OUTLIER_NSIGMA robust standard deviations (1.4826 x MAD,
floored at OUTLIER_FLOOR_BP of spot so clean tight chains never trim), and
refit — at most MAX_TRIM_ROUNDS rounds and never below MIN_PAIRED_STRIKES
survivors.  Dropped pairs are reported as ``n_outliers``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np

from volfit.data.types import ChainSnapshot

#: Minimum number of strikes with both call and put mids for a valid fit.
MIN_PAIRED_STRIKES = 3

#: Outlier rejection: drop parity pairs beyond this many robust sigmas …
OUTLIER_NSIGMA = 4.0
#: … with the robust sigma floored at this fraction of spot (1 bp), so a
#: clean chain whose residuals are all sub-cent never trims anything.
OUTLIER_FLOOR_BP = 1e-4
#: Trim/refit rounds (each round can only shrink the active set).
MAX_TRIM_ROUNDS = 3


@dataclass(frozen=True)
class ImpliedForward:
    """Parity-implied forward and discount factor for one expiry."""

    expiry: date
    forward: float
    discount: float
    n_strikes: int
    residual_rms: float
    n_outliers: int = 0  # parity pairs dropped by the stale-quote filter


#: Where a fitting forward comes from ([REQ 2026-06-12] forward modes):
#: the parity regression above, the dividend-model theoretical forward
#: (volfit.data.dividends), or a user-entered manual override.
ForwardSource = Literal["parity", "theoretical", "manual"]


@dataclass(frozen=True)
class ResolvedForward:
    """The (forward, discount) pair calibration actually uses for one expiry.

    Quote prep only needs `.forward`/`.discount`, so an `ImpliedForward` and
    a `ResolvedForward` are interchangeable there; `source` records which
    `ForwardSource` the per-expiry policy selected (diagnostics/UI).
    """

    expiry: date
    forward: float
    discount: float
    source: str  # a ForwardSource value


def implied_forward(snapshot: ChainSnapshot, expiry: date) -> ImpliedForward | None:
    """Imply the forward for one expiry, or None if the data is insufficient.

    Only strikes carrying *both* a usable call mid and put mid enter the
    regression; one-sided or crossed quotes are excluded via `OptionQuote.mid`.
    """
    call_mids: dict[float, float] = {}
    put_mids: dict[float, float] = {}
    for quote in snapshot.quotes_for(expiry):
        mid = quote.mid
        if mid is None:
            continue
        side = call_mids if quote.call_put == "C" else put_mids
        side[quote.strike] = mid

    paired = sorted(set(call_mids) & set(put_mids))
    if len(paired) < MIN_PAIRED_STRIKES:
        return None

    strikes = np.array(paired)
    y = np.array([call_mids[s] - put_mids[s] for s in paired])

    def fit(k: np.ndarray, v: np.ndarray) -> tuple[float, float, np.ndarray]:
        """Least squares v = a + b k; returns (a, b, residuals)."""
        design = np.column_stack([np.ones_like(k), k])
        (a, b), *_ = np.linalg.lstsq(design, v, rcond=None)
        return float(a), float(b), v - (a + b * k)

    # Robust loop: trim pairs whose parity residual is a stale-quote outlier.
    active = np.ones(strikes.size, dtype=bool)
    a, b, residuals = fit(strikes, y)
    for _ in range(MAX_TRIM_ROUNDS):
        scale = max(
            1.4826 * float(np.median(np.abs(residuals))),  # robust sigma (MAD)
            OUTLIER_FLOOR_BP * snapshot.spot,
        )
        keep = np.abs(residuals) <= OUTLIER_NSIGMA * scale
        if keep.all() or keep.sum() < MIN_PAIRED_STRIKES:
            break
        active[np.nonzero(active)[0][~keep]] = False
        a, b, residuals = fit(strikes[active], y[active])

    discount = -b
    if discount <= 0.0:
        return None  # nonsensical fit (e.g. corrupt quotes)
    forward = a / discount

    rms = float(np.sqrt(np.mean(residuals * residuals)))
    return ImpliedForward(
        expiry=expiry,
        forward=forward,
        discount=discount,
        n_strikes=int(active.sum()),
        residual_rms=rms,
        n_outliers=int((~active).sum()),
    )


def implied_forwards(snapshot: ChainSnapshot) -> dict[date, ImpliedForward]:
    """Imply forwards for every expiry in the chain that has enough pairs."""
    out: dict[date, ImpliedForward] = {}
    for expiry in snapshot.expiries():
        result = implied_forward(snapshot, expiry)
        if result is not None:
            out[expiry] = result
    return out
