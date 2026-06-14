"""Variance-swap quote penalty, shared by every slice calibrator.

A variance-swap quote is one scalar per smile node: the market's fair var-swap
volatility for that (underlying, expiry). When the user adds one, the slice fit
gains a soft penalty pulling the model's *own* fair var-swap toward the quote.

The fair var-swap total variance is the model-free OTM log-contract replication
(same integral as volfit.models.diagnostics.numeric_var_swap_w; a coarser grid
is used here because it runs inside the optimizer loop, not once per fit):

    w_vs = 2 [ int_0^inf  B(k, w) e^{-k} dk
             + int_{-inf}^0 (B(k, w) + e^k - 1) e^{-k} dk ],

with B the normalized Black call at total variance w(k). The penalty residual is
written in *volatility* units (var-swap vol = sqrt(w_vs / t)), so it stacks
directly onto the data residuals of SVI / sigmoid (already vol-space) and of LQD
(vega-normalized price ~= vol error). The residual carries sqrt(weight); the
caller sets ``weight`` so the var-swap contributes a chosen fraction of the total
option-quote weight of the node (see volfit.api.varswap.varswap_target):

    residual = sqrt(weight) * (sigma_vs_model - sigma_vs_quote).

All three parametric calibrators differentiate this by scipy's numerical
Jacobian, so no analytic gradient is needed; passing ``var_swap=None`` leaves
every calibrator byte-identical to before (the golden tests are untouched).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from volfit.core.black import black_call

#: Replication grid for the in-loop var-swap integral. Coarser than the 4001-pt
#: diagnostics grid (this runs every optimizer iteration); +-6 in log-moneyness
#: still captures the OTM mass to well under a basis point for any sane smile.
VS_HALF_WIDTH = 6.0
VS_POINTS = 801

#: Floor on total variance / expiry so sqrt() and the integrand stay finite.
_W_FLOOR = 1e-12


@dataclass(frozen=True)
class VarSwapTarget:
    """A resolved var-swap penalty for one slice fit.

    ``total_var`` is the quoted fair *total* variance (sigma_vs^2 * t);
    ``weight`` is the LSQ weight of the single var-swap residual, set by the
    caller to a fraction of the node's summed option-quote weights.
    """

    total_var: float
    weight: float
    t: float


def varswap_total_variance(
    implied_w: Callable[[np.ndarray], np.ndarray],
    half_width: float = VS_HALF_WIDTH,
    points: int = VS_POINTS,
) -> float:
    """Fair var-swap total variance of a smile curve by log-contract replication.

    ``implied_w(k)`` returns total implied variance on a log-moneyness array;
    that is the only thing the integral needs, so this works for any model.
    """
    k = np.linspace(-half_width, half_width, points)
    w = np.maximum(np.asarray(implied_w(k), dtype=float), _W_FLOOR)
    call = black_call(k, w)  # normalized OTM call price B(k, w)
    integrand = call * np.exp(-k)
    put_side = k < 0.0
    integrand[put_side] += 1.0 - np.exp(-k[put_side])  # (e^k - 1) e^{-k}
    return 2.0 * float(np.trapezoid(integrand, k))


def varswap_residual_w(w_model: float, target: VarSwapTarget) -> float:
    """The single vol-space var-swap penalty residual from a model var-swap w.

    sqrt(weight) * (sigma_vs_model - sigma_vs_quote), both var-swap vols. Take
    ``w_model`` (the model's fair var-swap TOTAL variance) from whatever is
    cheapest for the model: LQD's exact closed form (LQDSlice.var_swap_strike)
    or ``varswap_total_variance`` for SVI / sigmoid (cheap arithmetic curves).
    The caller appends this scalar to its residual vector (length is constant
    across iterations, so scipy's numerical Jacobian handles it).

    Using the model's own cheap var-swap is essential for speed: evaluating the
    generic replication on an LQD curve (whose implied_w solves a per-point root)
    every Jacobian column makes a single fit take minutes.
    """
    vol_model = float(np.sqrt(max(w_model, _W_FLOOR) / target.t))
    vol_quote = float(np.sqrt(max(target.total_var, _W_FLOOR) / target.t))
    return float(np.sqrt(max(target.weight, 0.0)) * (vol_model - vol_quote))


def varswap_residual(
    implied_w: Callable[[np.ndarray], np.ndarray],
    target: VarSwapTarget,
) -> float:
    """Var-swap penalty residual for a model exposing only ``implied_w(k)``.

    Computes the model var-swap by replication, then defers to
    ``varswap_residual_w``. Suitable for SVI / sigmoid (cheap closed-form total
    variance); LQD should pass its exact var-swap via ``varswap_residual_w``.
    """
    return varswap_residual_w(varswap_total_variance(implied_w), target)
