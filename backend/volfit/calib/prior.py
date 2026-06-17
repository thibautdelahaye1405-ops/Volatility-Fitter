"""Prior-anchor penalty (the autoLoadPrior feature), shared by the slice fit.

When the user turns ``autoLoadPrior`` on, a node's *saved prior* (yesterday's
fit, or any prior the user pinned) is fed into the calibration as a soft anchor
in the **quote-free wings**: where there are no quotes the fit relaxes toward the
prior's shape instead of toward the model's unconstrained extrapolation. Inside
the quoted strike range the data dominates, so the prior never fights live quotes
— it only fills the gaps the quotes leave.

The penalty is written in the same vega-normalized call-price space as the LQD
data residual (eq. vega_resid), so it stacks directly onto the fit residuals and
costs only one extra ``LQDSlice.call_price`` evaluation per iteration (cheap, no
per-point implied-vol root like a vol-space anchor would need):

    residual_j = sqrt(weight_j) * (C_model(k_j) - C_prior(k_j)) / (vega_prior_j + eta)

with ``k_j`` the wing log-moneyness points, ``C_prior`` the prior's normalized
Black call price there, and ``vega_prior`` the prior's Black vega at the current
node's variance time (so the residual reads as an approximate vol error, matching
the data block's scaling).

The anchor is in TOTAL VARIANCE: the prior's own ``implied_w(k)`` is priced
directly. Because the saved prior is the *same node* (yesterday's fit of this
underlying/expiry), its variance time is within a day of today's, so a total-
variance anchor is a same-vol-shape anchor to well under the soft wing pull's
resolution — no fragile time rescale needed. Passing ``prior_anchor=None`` (the
default) leaves every calibrator byte-identical — the golden tests are untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from volfit.core.black import black_call, black_vega_sigma

#: Vega floor mirrors the LQD data block (volfit.models.lqd.calibrate._VEGA_FLOOR)
#: so the wing residual scales identically to the in-sample one.
_VEGA_FLOOR = 1e-4

#: Default wing geometry: anchor points sit strictly OUTSIDE the quoted strike
#: range, from a small gap past each edge out to ``WING_SPAN`` in log-moneyness,
#: ``N_WING_PER_SIDE`` points each side. Kept to the NEAR wing on purpose: deep in
#: the tail Black vega collapses, so the vega-normalizer (1/vega, which turns the
#: price residual into a vol error) explodes and would let a far anchor point
#: dominate the global LQD fit. The near wing is also where a prior is genuinely
#: informative — the deep tail is pinned by the LQD asymptotics (A_L / A_R), not
#: by anchor points.
WING_GAP = 0.05
WING_SPAN = 0.25
N_WING_PER_SIDE = 3


@dataclass(frozen=True)
class PriorAnchorTarget:
    """A resolved prior-anchor penalty for one slice fit.

    ``k`` are the wing log-moneyness anchor points; ``target_price`` the prior's
    normalized Black call price there; ``inv_vega`` the prior's 1/(vega + floor)
    (the vega-normalizer, frozen during the fit); ``weight`` the per-point LSQ
    weight (already split across the points by the caller).
    """

    k: np.ndarray
    target_price: np.ndarray
    inv_vega: np.ndarray
    weight: float


def wing_points(
    k_quotes: np.ndarray,
    span: float = WING_SPAN,
    gap: float = WING_GAP,
    n_per_side: int = N_WING_PER_SIDE,
) -> np.ndarray:
    """Log-moneyness anchor points strictly outside the quoted strike range.

    ``n_per_side`` points on each side, spanning ``[edge + gap, edge + span]``
    away from the quote min/max. Empty if there are no quotes.
    """
    k_quotes = np.asarray(k_quotes, dtype=float)
    if k_quotes.size == 0 or n_per_side <= 0 or span <= gap:
        return np.empty(0)
    lo = k_quotes.min() - np.linspace(gap, span, n_per_side)  # left wing (deep puts)
    hi = k_quotes.max() + np.linspace(gap, span, n_per_side)  # right wing (deep calls)
    return np.sort(np.concatenate((lo, hi)))


def build_prior_anchor(
    prior_implied_w: Callable[[np.ndarray], np.ndarray],
    k_quotes: np.ndarray,
    tau: float,
    total_weight: float,
    span: float = WING_SPAN,
    gap: float = WING_GAP,
    n_per_side: int = N_WING_PER_SIDE,
) -> PriorAnchorTarget | None:
    """Resolve the wing anchor from a prior curve, or None if it would be inert.

    ``prior_implied_w(k)`` returns the prior's TOTAL implied variance on a log-
    moneyness array (e.g. ``build_slice(prior.params).implied_w``); ``tau`` is the
    current node's variance time (used only for the vega-normalizer scale, to match
    the data block). ``total_weight`` is the LSQ weight spread across all anchor
    points. Returns None when there are no wing points, no quotes, or a
    non-positive weight (=> a byte-identical fit).
    """
    if total_weight <= 0.0 or tau <= 0.0:
        return None
    k = wing_points(k_quotes, span=span, gap=gap, n_per_side=n_per_side)
    if k.size == 0:
        return None
    w_prior = np.asarray(prior_implied_w(k), dtype=float)
    finite = np.isfinite(w_prior) & (w_prior > 0.0)
    if not finite.any():
        return None
    k = k[finite]
    w_prior = w_prior[finite]
    target_price = black_call(k, w_prior)  # anchor the prior's total variance
    sigma_prior = np.sqrt(w_prior / tau)  # vega-normalizer at the current tau
    inv_vega = 1.0 / (black_vega_sigma(k, sigma_prior, tau) + _VEGA_FLOOR)
    per_point = total_weight / k.size  # spread the chosen weight across the points
    return PriorAnchorTarget(k=k, target_price=target_price, inv_vega=inv_vega, weight=per_point)


def prior_anchor_residuals(model_call_prices: np.ndarray, target: PriorAnchorTarget) -> np.ndarray:
    """Vega-normalized wing residuals pulling the model toward the prior.

    ``model_call_prices`` is the fitted slice's normalized Black call price at
    ``target.k`` (``LQDSlice.call_price``); the residual mirrors the LQD data block
    so it reads as an approximate vol error. Length is constant across iterations,
    so scipy's numerical Jacobian handles it.
    """
    diff = np.asarray(model_call_prices, dtype=float) - target.target_price
    return np.sqrt(max(target.weight, 0.0)) * diff * target.inv_vega
