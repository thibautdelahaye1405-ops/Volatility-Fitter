"""Quote-operator prior -> Local-Vol signed-basket targets (roadmap Phase 4).

The affine LV surface prices through the Dupire PDE and fits linear functionals of
the call-price grid (option quotes, the var-swap replication). The quote-operator
prior (``calib/operators``) reaches it the SAME way, as ``BasketQuote`` rows that
KEEP the signed-basket coupling — each active operator (ATM / RR / BF) is one
residual that pins the skew / curvature toward the prior WITHOUT pinning the
absolute wing level (so a genuine ATM-level move is not damped). This is the
faithful LV analogue of the parametric models' direct operator residuals, not the
per-leg projection that drops the coupling.

The coupling is preserved by a first-order linearization about the prior: on the
PDE surface

    sigma_model(x_a) ≈ sigma_prior(x_a) + (P_model(x_a) − P_prior(x_a)) / vega_a,

so the signed basket O = Σ_a c_a sigma(x_a) becomes a linear functional of the leg
call prices with weights ``w_a = c_a / vega_a`` (vega frozen at the prior) and
target ``Σ_a w_a P_prior(x_a)``. The residual ``(Σ_a w_a P_model − target)/tol``
with ``tol = 1/√λ`` equals ``√λ (O_model − O_prior)`` to first order — the same
object the parametric calibrators stack. The var-swap operator is already a
coupled basket (replication), so it stays a ``VarSwapQuote``.

Phase 5 wires this into ``affine_fit._fit``'s mode dispatch; here it is a pure,
independently-tested builder.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from volfit.api.schemas import OptionsSettings
from volfit.calib.operators import build_operator_prior
from volfit.core.black import black_call, black_vega_sigma
from volfit.models.localvol import BasketQuote, VarSwapQuote

#: Vol tolerance unit (1 vol point), matching affine_fit._VOL_TOL.
_VOL_TOL = 0.01
_VEGA_FLOOR = 1e-4
_W_FLOOR = 1e-12


def build_operator_lv_targets(
    prior_w: Callable[[np.ndarray], np.ndarray],
    prior_tau: float,
    tau: float,
    k_quotes: np.ndarray,
    weights: np.ndarray | None,
    options: OptionsSettings,
) -> tuple[list[BasketQuote], list[VarSwapQuote]]:
    """Signed-basket LV targets for the quote-operator prior at one expiry node.

    ``prior_w`` is the (already transported) prior total-variance curve, ``prior_tau``
    its variance time, ``tau`` the node's. ``k_quotes`` / ``weights`` are the live
    quote log-moneyness and LSQ weights (drive the activation gate and the budget).
    Returns ``([], [])`` when no operator is under-observed (the data wins)."""
    k_quotes = np.asarray(k_quotes, dtype=float)
    if tau <= 0.0 or prior_tau <= 0.0 or k_quotes.size == 0:
        return [], []
    sum_w = float(np.sum(weights)) if weights is not None else float(k_quotes.size)
    budget = (options.priorOperatorStrengthPct / 100.0) * sum_w
    target, vs = build_operator_prior(
        prior_w, prior_tau, tau, k_quotes, weights, budget,
        op_set=list(options.priorOperatorSet),
        collar_sign=options.collarSign,
        required_precision=options.priorOperatorRequiredPrecision,
        gap_exponent=options.priorOperatorGapExponent,
        bandwidth=options.priorOperatorBandwidth,
    )

    baskets: list[BasketQuote] = []
    if target is not None:
        legs_k = target.legs_k
        # Prior leg vols (preserved across the variance-time rescale) and the prior
        # leg call prices re-expressed at the node tau; vega frozen at the prior
        # vols (the linearization point that makes the basket a price functional).
        sigma = np.sqrt(np.maximum(np.asarray(prior_w(legs_k), float), _W_FLOOR) / prior_tau)
        w_node = sigma * sigma * tau
        p_prior = black_call(legs_k, w_node)
        inv_vega = 1.0 / np.maximum(black_vega_sigma(legs_k, sigma, tau), _VEGA_FLOOR)
        xs_all = np.exp(legs_k)
        for r, name in enumerate(target.names):
            coeff = target.coeff[r]
            active = coeff != 0.0
            w_a = coeff[active] * inv_vega[active]  # signed price-functional weights
            xs = xs_all[active]
            tgt = float(w_a @ p_prior[active])
            tol = 1.0 / np.sqrt(max(float(target.active_lambda[r]), _W_FLOOR))
            baskets.append(
                BasketQuote(t=tau, xs=xs, weights=w_a, target=tgt, tol=tol)
            )

    vs_quotes: list[VarSwapQuote] = []
    if vs.active and vs.weight > 0.0:
        sigma_vs = float(np.sqrt(max(vs.prior_total_var, _W_FLOOR) / tau))
        zeta = 2.0 * sigma_vs * tau * _VOL_TOL / np.sqrt(vs.weight)
        vs_quotes.append(VarSwapQuote(t=tau, total_var=float(vs.prior_total_var), tol=float(zeta)))
    return baskets, vs_quotes
