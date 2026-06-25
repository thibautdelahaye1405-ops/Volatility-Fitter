"""Smile-factor prior anchors (design note §6; roadmap Phase 6, Option C).

The ``smile_factor`` persistence mode anchors the prior in a small basis of
LOCAL smile factors instead of trader wing operators:

    ATM        = sigma(0)
    skew       = sigma(+h) - sigma(-h)            (ATM-local up/down vol difference)
    curvature  = sigma(+h) - 2 sigma(0) + sigma(-h)
    leftWing   = sigma(-W) - sigma(0)             (a put-side slope proxy, off by default)
    rightWing  = sigma(+W) - sigma(0)
    VarSwapVol = sqrt(K_var / tau)

Each factor is a SIGNED basket of the model vol at a few ATM-local log-moneyness
points — structurally identical to the quote operators (``calib/operators``), only
the leg placement differs (ATM-local finite-difference stencils vs delta strikes).
So this module reuses the operators' ``assemble_target`` / ``varswap_rec`` (the
§9.3 activation gate, budget split, diagnostics) and returns the SAME
``OperatorPriorTarget`` — every downstream consumer (the parametric residual block,
the LV basket adapter) works unchanged.

The factors use RAW differences (not divided by the step ``h``) so they stay
vol-difference magnitudes comparable to the ATM level, and prior/model use the same
``h`` — so matching the raw difference matches the local skew/curvature. Where the
near-ATM quotes already identify the local shape the gate turns the factor off
(``smile_factor`` therefore bites on genuinely sparse smiles, unlike operator mode
which bites on sparse wings).
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from volfit.calib.operators import (
    OperatorPriorTarget,
    VarSwapPriorRec,
    assemble_target,
    varswap_rec,
)

#: Factors known to the registry (mirrors OptionsSettings._clean_factors).
KNOWN_FACTORS = ("ATM", "skew", "curvature", "leftWing", "rightWing", "VarSwap")
#: Wing-slope probe distance as a multiple of the step ``h`` (leftWing/rightWing).
_WING_MULT = 3.0


def _resolve_factor_legs(step: float, factor_set: list[str]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Locate the factor legs (ATM-local FD stencils) and build the coefficient rows.

    ``step`` ``h`` is the near-ATM finite-difference half-width (log-moneyness).
    Returns ``(legs_k, coeff, names)``; ``VarSwap`` is handled separately."""
    h = max(float(step), 1e-3)
    legs: dict[float, int] = {}

    def col(k: float) -> int:
        key = round(float(k), 6)
        if key not in legs:
            legs[key] = len(legs)
        return legs[key]

    rows: list[dict[int, float]] = []
    names: list[str] = []
    for name in factor_set:
        if name == "ATM":
            rows.append({col(0.0): 1.0})
        elif name == "skew":
            rows.append({col(h): 1.0, col(-h): -1.0})
        elif name == "curvature":
            rows.append({col(h): 1.0, col(0.0): -2.0, col(-h): 1.0})
        elif name == "leftWing":
            rows.append({col(-_WING_MULT * h): 1.0, col(0.0): -1.0})
        elif name == "rightWing":
            rows.append({col(_WING_MULT * h): 1.0, col(0.0): -1.0})
        else:  # VarSwap (separate) or unknown
            continue
        names.append(name)

    n_legs = len(legs)
    coeff = np.zeros((len(rows), n_legs))
    for r, row in enumerate(rows):
        for c, v in row.items():
            coeff[r, c] = v
    legs_k = np.empty(n_legs)
    for key, idx in legs.items():
        legs_k[idx] = key
    return legs_k, coeff, names


def build_factor_prior(
    prior_w: Callable[[np.ndarray], np.ndarray],
    prior_tau: float,
    tau: float,
    k_quotes: np.ndarray,
    weights: np.ndarray | None,
    total_budget: float,
    *,
    factor_set: list[str],
    step: float = 0.06,
    required_precision: float = 1.0,
    gap_exponent: float = 1.0,
    bandwidth: float = 0.06,
) -> tuple[OperatorPriorTarget | None, VarSwapPriorRec]:
    """Resolve the active smile-factor prior + var-swap rec from a prior smile.

    Same contract as ``operators.build_operator_prior`` (returns the SAME types),
    so the parametric residual block and the LV basket adapter consume it
    unchanged. ``step`` is the ATM-local FD half-width ``h``."""
    no_vs = VarSwapPriorRec(active=False, prior_total_var=0.0, weight=0.0, gap=0.0)
    k_quotes = np.asarray(k_quotes, dtype=float)
    if total_budget <= 0.0 or tau <= 0.0 or prior_tau <= 0.0 or k_quotes.size == 0:
        return None, no_vs
    legs_k, coeff, names = _resolve_factor_legs(step, factor_set)
    target = assemble_target(
        names, legs_k, coeff, prior_w, prior_tau, tau, k_quotes, weights,
        total_budget, required_precision, gap_exponent, bandwidth,
    )
    vs = (
        varswap_rec(prior_w, prior_tau, tau, k_quotes, weights, total_budget,
                    required_precision, gap_exponent, bandwidth)
        if "VarSwap" in factor_set
        else no_vs
    )
    return target, vs
