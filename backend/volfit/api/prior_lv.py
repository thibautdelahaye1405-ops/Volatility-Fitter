"""Quote-operator prior -> Local-Vol synthetic quotes (roadmap Phase 4).

The affine LV surface prices through the Dupire PDE and ingests ``OptionQuote`` /
``VarSwapQuote`` targets, not vol-space residuals, so the quote-operator prior
(``calib/operators``) reaches it as SYNTHETIC LEG QUOTES: each active operator
leg (ATM / RR / BF) becomes a prior-vol option quote at that leg's strike,
weighted by the operator's activation, and the var-swap operator becomes one
``VarSwapQuote``.

The signed-basket coupling (RR = call - put, BF = wings - ATM) is necessarily
LOST in this projection — the PDE has no "vol at k" residual, so each leg enters
as an independent quote. Coherent activation (a basket's legs gate on/off
together via ``build_operator_prior``) plus the var-swap leg preserve the intent;
the parametric models keep the exact signed residual (``fit_models`` /
``calibrate_*``). This is the LV-only adapter.

Tolerances mirror ``affine_fit._option_quotes`` / ``_varswap_quotes`` exactly:
``tol = vega * VOL_TOL / sqrt(weight)`` for option quotes (so the squared residual
carries the weight as a vol error in units of ``VOL_TOL``) and
``zeta = 2 sigma_vs t VOL_TOL / sqrt(weight)`` for the var-swap.

Phase 5 wires this into ``affine_fit._fit``'s mode dispatch; here it is a pure,
independently-tested builder.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from volfit.api.schemas import OptionsSettings
from volfit.calib.operators import build_operator_prior
from volfit.core.black import black_call, black_vega_sigma
from volfit.models.localvol import OptionQuote, VarSwapQuote

#: Vol tolerance unit (1 vol point), matching affine_fit._VOL_TOL.
_VOL_TOL = 0.01
_VEGA_FLOOR = 1e-4
_W_FLOOR = 1e-12


def build_operator_lv_quotes(
    prior_w: Callable[[np.ndarray], np.ndarray],
    prior_tau: float,
    tau: float,
    k_quotes: np.ndarray,
    weights: np.ndarray | None,
    options: OptionsSettings,
) -> tuple[list[OptionQuote], list[VarSwapQuote]]:
    """Synthetic LV quotes for the quote-operator prior at one expiry node.

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

    option_quotes: list[OptionQuote] = []
    if target is not None:
        # Distribute each operator's activation budget to its legs by |coefficient|,
        # so an active RR/BF tightens the prior-vol quotes at its wing strikes.
        leg_weight = (np.abs(target.coeff) * target.active_lambda[:, None]).sum(axis=0)
        # Operator vols are preserved across the variance-time rescale: the prior's
        # vol at the leg IS the synthetic quote's vol; re-express it at the node tau.
        sigma = np.sqrt(np.maximum(np.asarray(prior_w(target.legs_k), float), _W_FLOOR) / prior_tau)
        w_target = sigma * sigma * tau
        price = black_call(target.legs_k, w_target)
        vega = np.maximum(black_vega_sigma(target.legs_k, sigma, tau), _VEGA_FLOOR)
        for kj, pj, vj, wj in zip(target.legs_k, price, vega, leg_weight):
            if wj <= 0.0:
                continue
            option_quotes.append(
                OptionQuote(
                    t=tau,
                    x=float(np.exp(kj)),
                    price=float(pj),
                    tol=float(vj * _VOL_TOL / np.sqrt(wj)),
                )
            )

    vs_quotes: list[VarSwapQuote] = []
    if vs.active and vs.weight > 0.0:
        sigma_vs = float(np.sqrt(max(vs.prior_total_var, _W_FLOOR) / tau))
        zeta = 2.0 * sigma_vs * tau * _VOL_TOL / np.sqrt(vs.weight)
        vs_quotes.append(VarSwapQuote(t=tau, total_var=float(vs.prior_total_var), tol=float(zeta)))
    return option_quotes, vs_quotes
