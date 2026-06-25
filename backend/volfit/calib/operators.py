"""Quote-operator prior anchors (design note §5; roadmap Phase 2).

Instead of anchoring individual strike prices to a prior (the legacy data-gap
``calib/prior.py``), persist the trader-readable *quote operators* of the smile —

    ATM         = sigma(0)
    RR_d        = sigma(k_call_d) - sigma(k_put_d)            (risk reversal / skew)
    BF_d        = 0.5*(sigma(k_call_d) + sigma(k_put_d)) - sigma(0)   (butterfly)
    VarSwapVol  = sqrt(K_var / tau)                           (handled by the caller
                  via the existing var-swap penalty; see VarSwapPriorRec)

and persist each operator ONLY where the live quotes do not already identify it
(the §9.3 activation gate, shared via ``calib/precision.py``). This is the fix for
"a tight ATM quote moves the level but the prior drags yesterday's level back":
ATM is well-observed so its prior turns off, while an unquoted skew/curvature
stays anchored to yesterday's shape.

The operators are evaluated from a model's total-variance curve ``w(k)`` and are
therefore **model-agnostic** — the same target drives the LQD / SVI / Multi-Core
SIV residual blocks (roadmap Phase 3). The residual stacked into the optimizer is

    sqrt(lambda_j) * (O_j(model) - O_j(prior)) / scale_j           (design note §3)

with a constant length (one row per active operator) so scipy's numeric Jacobian
is happy, mirroring ``calib/prior.prior_anchor_residuals``.

Leg strikes are located ONCE on the (transported) prior smile and frozen, so the
residual compares prior and model at the same log-moneyness. The variance-time
rescale that re-expresses the prior at the node's ``tau`` cancels in vol space
(sigma = sqrt(w/tau)), so an operator's prior value is just the prior smile's own
vol there — the level/skew/curvature shape is what persists, not the variance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy.special import ndtri  # inverse standard-normal CDF (delta -> strike)

from volfit.calib.precision import activation_gap
from volfit.calib.varswap import varswap_total_variance

_W_FLOOR = 1e-12
_EPS = 1e-9

#: Per-side forward delta implied by each named operator (ATM/VarSwap have none).
OPERATOR_DELTAS: dict[str, float] = {
    "RR25": 0.25, "BF25": 0.25, "RR10": 0.10, "BF10": 0.10,
}
#: Operators known to the registry (mirrors OptionsSettings._clean_operators).
KNOWN_OPERATORS = ("ATM", "RR25", "BF25", "RR10", "BF10", "VarSwap")


def hybrid_tail_deltas(op_set: list[str], anchor_deltas) -> tuple[float, ...]:
    """Deep-tail deltas for the hybrid residual strike anchor (design note §7).

    The ``anchor_deltas`` below the shallowest active RR/BF operator delta — i.e.
    where no quote operator reaches — so the tail anchor only persists the deep
    unquoted wing. Falls back to (0.02, 0.05) when the operator set has no wing
    operator (only ATM / VarSwap)."""
    op_deltas = [OPERATOR_DELTAS[op] for op in op_set if op in OPERATOR_DELTAS]
    floor = min(op_deltas) if op_deltas else 0.10
    tail = tuple(float(d) for d in anchor_deltas if d < floor)
    return tail or (0.02, 0.05)


@dataclass(frozen=True)
class OperatorPriorTarget:
    """A resolved set of active operator-prior penalties for one slice fit.

    ``legs_k`` are the (frozen) log-moneyness leg locations; ``coeff`` the signed
    basket coefficients (one row per operator over the legs); ``prior_value`` the
    operator value on the transported prior; ``scale`` the per-operator normalizer;
    ``active_lambda`` the LSQ weight after the activation gate; ``tau`` the node's
    variance time (so the residual reads the model vol consistently)."""

    names: list[str]
    legs_k: np.ndarray  # (n_legs,)
    coeff: np.ndarray  # (n_op, n_legs)
    prior_value: np.ndarray  # (n_op,)
    scale: np.ndarray  # (n_op,)
    active_lambda: np.ndarray  # (n_op,)
    tau: float
    diagnostics: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class VarSwapPriorRec:
    """The var-swap operator recommendation (the caller maps it to the existing
    var-swap penalty target — roadmap Phase 5). ``active`` is False when the smile
    is sufficiently covered for the var-swap level (gap 0) or the operator is off."""

    active: bool
    prior_total_var: float  # fair var-swap total variance re-expressed at the node tau
    weight: float  # the LSQ weight after the activation gate
    gap: float


# ----------------------------------------------------------- leg location
def delta_strike(w_fn: Callable[[np.ndarray], np.ndarray], tau: float, call_delta: float) -> float:
    """Log-moneyness of a forward Black ``call_delta`` strike on the smile ``w_fn``.

    Same convention as ``calib/prior.delta_anchor_strikes``: ``k = ½σ²τ −
    σ√τ·Φ⁻¹(c)`` with ``σ`` the LOCAL vol there, resolved by a two-step fixed
    point from the ATM vol. A put at delta ``d`` is the call-delta ``1 − d``."""
    sig_atm = math.sqrt(max(float(w_fn(np.array([0.0]))[0]), _W_FLOOR) / tau)
    d1 = float(ndtri(call_delta))
    root_tau = math.sqrt(tau)
    sig = sig_atm
    k = 0.0
    for _ in range(2):
        k = 0.5 * sig * sig * tau - sig * root_tau * d1
        sig = math.sqrt(max(float(w_fn(np.array([k]))[0]), _W_FLOOR) / tau)
    return k


def _resolve_legs(
    w_fn: Callable[[np.ndarray], np.ndarray], tau: float, names: list[str], collar_sign: str
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Locate every vol operator's legs on ``w_fn`` and build the coefficient rows.

    Returns ``(legs_k, coeff, op_names)`` where ``coeff`` is ``(n_op, n_legs)`` of
    signed basket weights. ATM sits at log-moneyness 0; RR/BF legs at the call /
    put delta strikes. ``VarSwap`` is excluded here (handled separately)."""
    legs: dict[float, int] = {}

    def col(k: float) -> int:
        key = round(float(k), 6)
        if key not in legs:
            legs[key] = len(legs)
        return legs[key]

    rows: list[dict[int, float]] = []
    op_names: list[str] = []
    rr_call = 1.0 if collar_sign == "call_put" else -1.0  # call-minus-put vs put-minus-call
    for name in names:
        if name == "VarSwap":
            continue
        if name == "ATM":
            rows.append({col(0.0): 1.0})
            op_names.append(name)
            continue
        d = OPERATOR_DELTAS.get(name)
        if d is None:
            continue
        k_call = delta_strike(w_fn, tau, d)  # OTM call (k > 0)
        k_put = delta_strike(w_fn, tau, 1.0 - d)  # OTM put (k < 0)
        if name.startswith("RR"):
            rows.append({col(k_call): rr_call, col(k_put): -rr_call})
        else:  # BF
            rows.append({col(k_call): 0.5, col(k_put): 0.5, col(0.0): -1.0})
        op_names.append(name)

    n_legs = len(legs)
    coeff = np.zeros((len(rows), n_legs))
    for r, row in enumerate(rows):
        for c, v in row.items():
            coeff[r, c] = v
    legs_k = np.empty(n_legs)
    for key, idx in legs.items():
        legs_k[idx] = key
    return legs_k, coeff, op_names


def _sigma_at(w_fn: Callable[[np.ndarray], np.ndarray], k: np.ndarray, tau: float) -> np.ndarray:
    """Black vol of the smile at log-moneyness ``k`` (floored)."""
    return np.sqrt(np.maximum(np.asarray(w_fn(k), dtype=float), _W_FLOOR) / tau)


def evaluate_operators(
    w_fn: Callable[[np.ndarray], np.ndarray], tau: float, names: list[str], collar_sign: str = "call_put"
) -> dict[str, float]:
    """Operator values on a smile (test/diagnostic convenience; legs located here).

    Includes ``VarSwap`` (the fair var-swap vol by replication) when requested."""
    legs_k, coeff, op_names = _resolve_legs(w_fn, tau, names, collar_sign)
    out: dict[str, float] = {}
    if op_names:
        vals = coeff @ _sigma_at(w_fn, legs_k, tau)
        out.update({n: float(v) for n, v in zip(op_names, vals)})
    if "VarSwap" in names:
        out["VarSwap"] = float(math.sqrt(max(varswap_total_variance(w_fn), _W_FLOOR) / tau))
    return out


# ----------------------------------------------------------- quote support
def _quote_support(
    k_quotes: np.ndarray, weights: np.ndarray | None, k_legs: np.ndarray, bandwidth: float
) -> np.ndarray:
    """Effective # of weighted quotes supporting each leg (Gaussian kernel, §5.3).

    Quote weights are normalized to mean 1 so the support reads as "effective
    quote count" regardless of the weighting scheme; one quote exactly on a leg
    contributes ~1."""
    k_quotes = np.asarray(k_quotes, dtype=float)
    if k_quotes.size == 0:
        return np.zeros(k_legs.size)
    if weights is None:
        w = np.ones(k_quotes.size)
    else:
        w = np.asarray(weights, dtype=float)
        mean = float(np.mean(w)) if w.size else 1.0
        w = w / mean if mean > 0.0 else np.ones_like(w)
    z = (k_legs[:, None] - k_quotes[None, :]) / bandwidth
    return (np.exp(-0.5 * z * z) * w[None, :]).sum(axis=1)


def _operator_obs_info(coeff_row: np.ndarray, support: np.ndarray) -> float:
    """Harmonic-style aggregation: an operator is well-observed only if EVERY
    non-zero leg has support (a missing put leg keeps an RR precision low, §5.3)."""
    active = coeff_row != 0.0
    if not active.any():
        return 0.0
    denom = float(np.sum(coeff_row[active] ** 2 / (support[active] + _EPS)))
    return 1.0 / denom if denom > 0.0 else 0.0


# ----------------------------------------------------------- builder (shared)
def assemble_target(
    names: list[str],
    legs_k: np.ndarray,
    coeff: np.ndarray,
    prior_w: Callable[[np.ndarray], np.ndarray],
    prior_tau: float,
    tau: float,
    k_quotes: np.ndarray,
    weights: np.ndarray | None,
    total_budget: float,
    required_precision: float,
    gap_exponent: float,
    bandwidth: float,
) -> OperatorPriorTarget | None:
    """Gate a set of signed σ-baskets into an OperatorPriorTarget, or None.

    Shared by the quote operators (delta strikes) and the smile factors (ATM-local
    finite-difference stencils): both are signed baskets ``O = Σ_a c_a σ(k_a)``, so
    the gate (§9.3) / budget split / diagnostics are identical — only the leg
    placement differs. Prior value is in VOL space (the variance-time rescale
    cancels: ``σ_prior(k) = sqrt(prior_w(k)/prior_tau)``). ``total_budget`` is split
    across the under-observed baskets in proportion to their activation gap; a
    fully-observed set returns None."""
    if not names:
        return None
    sigma_prior = _sigma_at(prior_w, legs_k, prior_tau)
    prior_value = coeff @ sigma_prior
    support = _quote_support(k_quotes, weights, legs_k, bandwidth)
    obs = np.array([_operator_obs_info(coeff[r], support) for r in range(len(names))])
    gap = np.asarray(activation_gap(obs, max(required_precision, _EPS), gap_exponent), dtype=float)
    gsum = float(gap.sum())
    if gsum <= 0.0:
        return None
    lam = total_budget * gap / gsum
    keep = lam > 0.0
    if not keep.any():
        return None
    scale = np.ones(len(names))  # vol-error units (reserved for future tuning)
    diags = [
        {
            "operator": names[r],
            "priorValue": float(prior_value[r]),
            "obsPrecision": float(obs[r]),
            "requiredPrecision": float(required_precision),
            "gap": float(gap[r]),
            "activeLambda": float(lam[r]),
        }
        for r in range(len(names))
        if keep[r]
    ]
    return OperatorPriorTarget(
        names=[names[r] for r in range(len(names)) if keep[r]],
        legs_k=legs_k,
        coeff=coeff[keep],
        prior_value=prior_value[keep],
        scale=scale[keep],
        active_lambda=lam[keep],
        tau=float(tau),
        diagnostics=diags,
    )


def varswap_rec(
    prior_w: Callable[[np.ndarray], np.ndarray],
    prior_tau: float,
    tau: float,
    k_quotes: np.ndarray,
    weights: np.ndarray | None,
    total_budget: float,
    required_precision: float,
    gap_exponent: float,
    bandwidth: float,
) -> VarSwapPriorRec:
    """The var-swap operator rec: coverage measured over a broad ATM+wings probe.

    Shared by operator and factor modes. The var-swap level (tail-aware) is
    under-observed unless quotes reach ~2 ATM-std into the wings; its prior value is
    the fair var-swap re-expressed at the node tau."""
    no_vs = VarSwapPriorRec(active=False, prior_total_var=0.0, weight=0.0, gap=0.0)
    sig_atm = float(_sigma_at(prior_w, np.array([0.0]), prior_tau)[0])
    wing = 2.0 * sig_atm * math.sqrt(prior_tau)
    probe = np.array([-wing, 0.0, wing])
    psup = _quote_support(k_quotes, weights, probe, bandwidth)
    vs_obs = 1.0 / float(np.sum(1.0 / (psup + _EPS)))  # harmonic over the probe
    vs_gap = float(activation_gap(vs_obs, max(required_precision, _EPS), gap_exponent))
    if vs_gap <= 0.0:
        return no_vs
    w_vs = varswap_total_variance(prior_w) * (tau / prior_tau)
    return VarSwapPriorRec(
        active=True, prior_total_var=float(w_vs), weight=total_budget * vs_gap, gap=vs_gap
    )


def build_operator_prior(
    prior_w: Callable[[np.ndarray], np.ndarray],
    prior_tau: float,
    tau: float,
    k_quotes: np.ndarray,
    weights: np.ndarray | None,
    total_budget: float,
    *,
    op_set: list[str],
    collar_sign: str = "call_put",
    required_precision: float = 1.0,
    gap_exponent: float = 1.0,
    bandwidth: float = 0.06,
) -> tuple[OperatorPriorTarget | None, VarSwapPriorRec]:
    """Resolve the active quote-operator prior (ATM/RR/BF) + var-swap rec.

    ``prior_w(k)`` is the (transported) prior total variance, ``prior_tau`` its
    variance time, ``tau`` the node's. ``k_quotes`` / ``weights`` are the live
    quotes (drive the §9.3 gate). ``total_budget`` is split across the
    under-observed operators by activation gap. Returns ``(target | None,
    varswap_rec)`` — None when nothing is under-observed."""
    no_vs = VarSwapPriorRec(active=False, prior_total_var=0.0, weight=0.0, gap=0.0)
    k_quotes = np.asarray(k_quotes, dtype=float)
    if total_budget <= 0.0 or tau <= 0.0 or prior_tau <= 0.0 or k_quotes.size == 0:
        return None, no_vs
    legs_k, coeff, names = _resolve_legs(prior_w, prior_tau, op_set, collar_sign)
    target = assemble_target(
        names, legs_k, coeff, prior_w, prior_tau, tau, k_quotes, weights,
        total_budget, required_precision, gap_exponent, bandwidth,
    )
    vs = (
        varswap_rec(prior_w, prior_tau, tau, k_quotes, weights, total_budget,
                    required_precision, gap_exponent, bandwidth)
        if "VarSwap" in op_set
        else no_vs
    )
    return target, vs


def operator_residuals(
    model_w: Callable[[np.ndarray], np.ndarray], target: OperatorPriorTarget
) -> np.ndarray:
    """Per-operator residuals pulling the model operators toward the prior's.

    ``sqrt(lambda_j)·(O_j(model) − O_j(prior))/scale_j`` — a vol-error residual,
    constant length (one row per active operator)."""
    sigma_model = _sigma_at(model_w, target.legs_k, target.tau)
    o_model = target.coeff @ sigma_model
    diff = (o_model - target.prior_value) / target.scale
    return np.sqrt(np.maximum(target.active_lambda, 0.0)) * diff
