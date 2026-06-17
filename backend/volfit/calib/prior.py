"""Bayesian data-gap prior anchor — pull a fit toward a prior where data is thin.

When a prior has been fetched (the active, spot-updated prior of the prior
framework) and ``autoLoadPrior`` is on, the calibration is anchored toward that
prior at a spread of **delta-locations** (plus the var-swap level, handled by the
caller), with a per-location precision that follows the *gap* between how densely
the strike axis is observed and how densely we would like it covered:

    precision_j  ∝  λ · max( ρ_desired(x_j) − ρ_observed(x_j), 0 ) · Δx_j

  * ``ρ_observed`` is a Gaussian kernel density of the live quote log-moneyness
    (total mass = #quotes): where quotes cluster it is large.
  * ``ρ_desired`` is how densely we want the smile pinned over the anchor span —
    ``uniform`` or ``time-value`` shaped (reusing the FitSettings weight scheme),
    total mass also = #quotes, but spread over the WIDER delta span so it reaches
    into the wings the quotes do not.
  * the positive part means a region already sampled to the desired density gets
    **zero** prior weight (the data wins); only the deficit (sparse wings, gaps)
    is filled. ``Δx_j`` is the anchor's Voronoi cell width, so the weight is the
    missing quote-mass in its cell.

The per-anchor weights are normalised to a total budget = ``λ`` (a percentage of
the summed quote weights, like the var-swap penalty), so the prior competes with
the data at a controlled strength and vanishes smoothly as the data fills in.

The residual itself is the same vega-normalized call-price residual as the LQD
data block (so it reads as a vol error and stacks directly), evaluated against the
prior's prices at the anchor strikes. Passing ``prior_anchor=None`` leaves every
calibrator byte-identical — the golden tests are untouched.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.special import ndtri  # inverse standard-normal CDF (delta -> strike)

from volfit.calib.weights import otm_time_value
from volfit.core.black import black_call, black_vega_sigma

_VEGA_FLOOR = 1e-4
_W_FLOOR = 1e-12

#: Per-side delta-locations the prior is anchored at (puts AND calls), plus ATM.
#: 10/25/40-delta spans the smile from the wings to near the money.
DEFAULT_DELTAS = (0.10, 0.25, 0.40)
#: Gaussian-kernel bandwidth (log-moneyness) for the observed-quote density.
DEFAULT_BANDWIDTH = 0.06


@dataclass(frozen=True)
class PriorAnchorTarget:
    """A resolved prior-anchor penalty for one slice fit.

    ``k`` are the anchor log-moneyness points; ``target_price`` the prior's
    normalized Black call price there; ``inv_vega`` the prior's 1/(vega+floor)
    vega-normalizer; ``weights`` the PER-POINT LSQ weights (the data-gap budget,
    already distributed across the anchors)."""

    k: np.ndarray
    target_price: np.ndarray
    inv_vega: np.ndarray
    weights: np.ndarray


def delta_anchor_strikes(
    prior_w: Callable[[np.ndarray], np.ndarray], tau: float, deltas=DEFAULT_DELTAS
) -> np.ndarray:
    """Log-moneyness of the prior's delta-locations (puts, ATM, calls), ascending.

    Forward Black delta: a call-delta ``c`` sits at ``k = ½σ²τ − σ√τ·Φ⁻¹(c)`` with
    ``σ`` the prior's LOCAL vol there; a put at delta ``d`` is the call-delta
    ``1−d``. ``σ`` is resolved by a two-step fixed point from the ATM vol."""
    call_deltas = sorted({0.5, *[1.0 - d for d in deltas], *deltas})
    sig_atm = math.sqrt(max(float(prior_w(np.array([0.0]))[0]), _W_FLOOR) / tau)
    root_tau = math.sqrt(tau)
    out: list[float] = []
    for c in call_deltas:
        d1 = float(ndtri(c))
        sig = sig_atm
        k = 0.0
        for _ in range(2):  # local-vol fixed point (anchor placement only)
            k = 0.5 * sig * sig * tau - sig * root_tau * d1
            sig = math.sqrt(max(float(prior_w(np.array([k]))[0]), _W_FLOOR) / tau)
        out.append(k)
    return np.array(sorted(out))


def _cell_widths(x: np.ndarray) -> np.ndarray:
    """1-D Voronoi cell widths of sorted points (one-sided at the ends)."""
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return np.array([])
    if x.size == 1:
        return np.array([1.0])
    s = np.empty(x.size)
    s[0] = x[1] - x[0]
    s[-1] = x[-1] - x[-2]
    if x.size > 2:
        s[1:-1] = 0.5 * (x[2:] - x[:-2])
    return np.maximum(s, _W_FLOOR)


def _observed_density(k_quotes: np.ndarray, x: np.ndarray, bandwidth: float) -> np.ndarray:
    """Gaussian kernel density of the quote log-moneyness at ``x`` (mass=#quotes)."""
    k_quotes = np.asarray(k_quotes, dtype=float)
    x = np.asarray(x, dtype=float)
    if k_quotes.size == 0:
        return np.zeros_like(x)
    z = (x[:, None] - k_quotes[None, :]) / bandwidth
    return np.exp(-0.5 * z * z).sum(axis=1) / (bandwidth * math.sqrt(2.0 * math.pi))


def _desired_density(
    x: np.ndarray, scheme: str, prior_w: Callable[[np.ndarray], np.ndarray], n: int
) -> np.ndarray:
    """Target coverage density at ``x`` (total mass = ``n``), uniform or TV-shaped.

    Spread over the FULL anchor span (so it reaches the wings the quotes miss).
    ``tv_density`` shapes it by the prior's time value (more pins where there is
    more economic value); any other scheme is uniform."""
    x = np.asarray(x, dtype=float)
    span = max(float(x.max() - x.min()), _W_FLOOR) if x.size > 1 else 1.0
    if scheme == "tv_density" and x.size > 1:
        tv = np.maximum(otm_time_value(x, np.maximum(prior_w(x), _W_FLOOR)), _W_FLOOR)
        widths = _cell_widths(x)
        integral = float(np.sum(tv * widths))
        if integral > 0.0:
            return n * tv / integral  # mass n, shaped by time value
    return np.full_like(x, n / span)  # uniform: mass n over the span


def build_prior_anchor(
    prior_w: Callable[[np.ndarray], np.ndarray],
    prior_tau: float,
    k_quotes: np.ndarray,
    tau: float,
    total_budget: float,
    scheme: str = "equal",
    deltas=DEFAULT_DELTAS,
    bandwidth: float = DEFAULT_BANDWIDTH,
) -> tuple[PriorAnchorTarget | None, float]:
    """Resolve the data-gap anchor from a (transported) prior, or (None, 0).

    ``prior_w(k)`` is the prior's total implied variance at log-moneyness ``k``
    (the spot-updated active prior); ``prior_tau`` its variance time and ``tau``
    the current node's. ``k_quotes`` are the live quote log-moneyness, ``scheme``
    the desired-density shape, ``total_budget`` the LSQ weight to distribute across
    the anchors. Returns the target and the **unmet-density fraction** (0 when the
    data already meets the desired coverage, →1 when the smile is unobserved) so
    the caller can scale a companion var-swap prior. None when nothing to anchor."""
    k_quotes = np.asarray(k_quotes, dtype=float)
    if total_budget <= 0.0 or tau <= 0.0 or prior_tau <= 0.0 or k_quotes.size == 0:
        return None, 0.0
    anchors = delta_anchor_strikes(prior_w, prior_tau, deltas)
    if anchors.size == 0:
        return None, 0.0

    rho_obs = _observed_density(k_quotes, anchors, bandwidth)
    rho_des = _desired_density(anchors, scheme, prior_w, k_quotes.size)
    dx = _cell_widths(anchors)
    gap = np.maximum(rho_des - rho_obs, 0.0)
    raw = gap * dx  # missing quote-mass per anchor cell
    raw_sum = float(raw.sum())
    desired_mass = float(np.sum(rho_des * dx))
    unmet_fraction = raw_sum / desired_mass if desired_mass > 0.0 else 0.0
    if raw_sum <= 0.0:
        return None, 0.0  # data already meets the desired coverage everywhere
    weights = total_budget * raw / raw_sum

    # Anchor the prior's vol SHAPE re-expressed at the current variance time, in the
    # same vega-normalized call-price space as the data block.
    w_prior = np.maximum(np.asarray(prior_w(anchors), dtype=float), _W_FLOOR)
    w_target = w_prior * (tau / prior_tau)
    target_price = black_call(anchors, w_target)
    sigma = np.sqrt(w_target / tau)
    inv_vega = 1.0 / (black_vega_sigma(anchors, sigma, tau) + _VEGA_FLOOR)
    keep = weights > 0.0  # drop fully-satisfied anchors (zero weight)
    if not keep.any():
        return None, unmet_fraction
    target = PriorAnchorTarget(
        k=anchors[keep],
        target_price=target_price[keep],
        inv_vega=inv_vega[keep],
        weights=weights[keep],
    )
    return target, unmet_fraction


def prior_anchor_residuals(model_call_prices: np.ndarray, target: PriorAnchorTarget) -> np.ndarray:
    """Per-anchor vega-normalized residuals pulling the model toward the prior.

    ``sqrt(weight_j) · (C_model(k_j) − C_prior(k_j)) / (vega_prior_j + eta)`` — the
    LQD data-block form, so it reads as a vol error. Length is constant across
    iterations, so scipy's numerical Jacobian handles it."""
    diff = np.asarray(model_call_prices, dtype=float) - target.target_price
    return np.sqrt(np.maximum(target.weights, 0.0)) * diff * target.inv_vega
