"""Quote-operator / smile-factor prior -> Local-Vol signed-basket targets (Phase 4/6).

The affine LV surface prices through the Dupire PDE and fits linear functionals of
the call-price grid (option quotes, the var-swap replication). The quote-operator
prior (``calib/operators``) and the smile-factor prior (``calib/factors``) reach it
the SAME way, as ``BasketQuote`` rows that KEEP the signed-basket coupling — each
active basket (ATM / RR / BF, or level / skew / curvature) is one residual that
pins that shape factor toward the prior WITHOUT pinning the absolute wing level
(so a genuine ATM-level move is not damped). This is the faithful LV analogue of
the parametric models' direct operator/factor residuals.

The coupling is preserved by a first-order linearization about the prior: on the
PDE surface

    sigma_model(x_a) ≈ sigma_prior(x_a) + (P_model(x_a) − P_prior(x_a)) / vega_a,

so a signed basket O = Σ_a c_a sigma(x_a) becomes a linear functional of the leg
call prices with weights ``w_a = c_a / vega_a`` (vega frozen at the prior) and
target ``Σ_a w_a P_prior(x_a)``. The residual ``(Σ_a w_a P_model − target)/tol``
with ``tol = 1/√λ`` equals ``√λ (O_model − O_prior)`` to first order. The var-swap
operator is already a coupled basket (replication), so it stays a ``VarSwapQuote``
— under either carrier: the absolute level, or since 2026-08-27 the prior's
(σ_vs − σ_atm) SPREAD when ``priorVarSwapMode="atm_spread"`` (the row form lives
in volfit.models.localvol.varswap_rows; the weights in volfit.api.affine_varswap).

Both builders share the conversion (``lv_targets_from_operator_prior``) since the
operator and factor builders return the same ``OperatorPriorTarget``.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from volfit.api.affine_varswap import prior_varswap_quote
from volfit.api.schemas import OptionsSettings
from volfit.calib.factors import build_factor_prior
from volfit.calib.operators import (
    OperatorPriorTarget,
    VarSwapPriorRec,
    build_operator_prior,
)
from volfit.core.black import black_call, black_vega_sigma
from volfit.models.localvol import BasketQuote, VarSwapQuote

_VEGA_FLOOR = 1e-4
_W_FLOOR = 1e-12


def lv_targets_from_operator_prior(
    target: OperatorPriorTarget | None,
    vs: VarSwapPriorRec,
    prior_w: Callable[[np.ndarray], np.ndarray],
    prior_tau: float,
    tau: float,
    varswap_mode: str = "absolute",
) -> tuple[list[BasketQuote], list[VarSwapQuote]]:
    """Convert a resolved operator/factor prior into LV baskets + a var-swap quote.

    Each active basket's legs become a signed price-functional ``BasketQuote`` with
    frozen-vega weights ``c_a / vega_a`` and ``tol = 1/√λ``; the var-swap rec becomes
    one ``VarSwapQuote`` (``affine_varswap.prior_varswap_quote``: the absolute
    carrier, byte-identical, or under ``varswap_mode == "atm_spread"`` the
    (σ_vs − σ_atm) spread carrier with the prior's ATM total variance re-expressed
    at ``tau`` exactly like the var-swap level — service._prior_varswap's rescale)."""
    baskets: list[BasketQuote] = []
    if target is not None:
        legs_k = target.legs_k
        sigma = np.sqrt(np.maximum(np.asarray(prior_w(legs_k), float), _W_FLOOR) / prior_tau)
        p_prior = black_call(legs_k, sigma * sigma * tau)  # prior leg prices at node tau
        inv_vega = 1.0 / np.maximum(black_vega_sigma(legs_k, sigma, tau), _VEGA_FLOOR)
        xs_all = np.exp(legs_k)
        for r in range(len(target.names)):
            coeff = target.coeff[r]
            active = coeff != 0.0
            w_a = coeff[active] * inv_vega[active]  # signed price-functional weights
            baskets.append(
                BasketQuote(
                    t=tau,
                    xs=xs_all[active],
                    weights=w_a,
                    target=float(w_a @ p_prior[active]),
                    tol=1.0 / np.sqrt(max(float(target.active_lambda[r]), _W_FLOOR)),
                )
            )

    vs_quotes: list[VarSwapQuote] = []
    if vs.active and vs.weight > 0.0:
        # The spread carrier needs the prior's ATM total variance at the node
        # tau (w(0) · tau/prior_tau — the same rescale as the var-swap level, it
        # cancels in vol space); the LV row then compares (σ_vs − σ_atm) model vs
        # prior through the closed-form ATM inversion (varswap_rows).
        w_atm = None
        if varswap_mode == "atm_spread":
            w_atm = float(
                np.maximum(np.asarray(prior_w(np.array([0.0])), dtype=float), _W_FLOOR)[0]
            ) * (tau / prior_tau)
        vs_quotes.append(prior_varswap_quote(vs.prior_total_var, tau, vs.weight, w_atm))
    return baskets, vs_quotes


def _sum_w(k_quotes: np.ndarray, weights: np.ndarray | None) -> float:
    return float(np.sum(weights)) if weights is not None else float(k_quotes.size)


def build_operator_lv_targets(
    prior_w: Callable[[np.ndarray], np.ndarray],
    prior_tau: float,
    tau: float,
    k_quotes: np.ndarray,
    weights: np.ndarray | None,
    options: OptionsSettings,
) -> tuple[list[BasketQuote], list[VarSwapQuote]]:
    """Signed-basket LV targets for the QUOTE-OPERATOR prior at one expiry node."""
    k_quotes = np.asarray(k_quotes, dtype=float)
    if tau <= 0.0 or prior_tau <= 0.0 or k_quotes.size == 0:
        return [], []
    budget = (options.priorOperatorStrengthPct / 100.0) * _sum_w(k_quotes, weights)
    target, vs = build_operator_prior(
        prior_w, prior_tau, tau, k_quotes, weights, budget,
        op_set=list(options.priorOperatorSet),
        collar_sign=options.collarSign,
        required_precision=options.priorOperatorRequiredPrecision,
        gap_exponent=options.priorOperatorGapExponent,
        bandwidth=options.priorOperatorBandwidth,
        # WingL/WingR slope baskets reach the LV surface through the SAME
        # frozen-vega price-basket conversion as RR/BF (any signed sigma-basket
        # linearizes); inert unless a Wing op is in the set.
        anchor_deltas=tuple(options.priorAnchorDeltas),
        wing_scale=options.priorWingSlopeScale,
    )
    return lv_targets_from_operator_prior(
        target, vs, prior_w, prior_tau, tau, varswap_mode=options.priorVarSwapMode
    )


def build_factor_lv_targets(
    prior_w: Callable[[np.ndarray], np.ndarray],
    prior_tau: float,
    tau: float,
    k_quotes: np.ndarray,
    weights: np.ndarray | None,
    options: OptionsSettings,
) -> tuple[list[BasketQuote], list[VarSwapQuote]]:
    """Signed-basket LV targets for the SMILE-FACTOR prior at one expiry node."""
    k_quotes = np.asarray(k_quotes, dtype=float)
    if tau <= 0.0 or prior_tau <= 0.0 or k_quotes.size == 0:
        return [], []
    budget = (options.priorFactorStrengthPct / 100.0) * _sum_w(k_quotes, weights)
    target, vs = build_factor_prior(
        prior_w, prior_tau, tau, k_quotes, weights, budget,
        factor_set=list(options.priorFactorSet),
        step=options.priorOperatorBandwidth,
        required_precision=options.priorOperatorRequiredPrecision,
        gap_exponent=options.priorOperatorGapExponent,
        bandwidth=options.priorOperatorBandwidth,
    )
    return lv_targets_from_operator_prior(
        target, vs, prior_w, prior_tau, tau, varswap_mode=options.priorVarSwapMode
    )
