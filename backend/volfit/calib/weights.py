"""Per-slice quote weighting schemes for calibration (a given maturity).

Two schemes today, selectable by the FitSettings.weightScheme hyperparameter
(a third may be added later):

  * ``"equal"`` — unit weights, the historical scheme (the calibrators' default
    when ``weights is None``); every quote's IV residual counts the same.
  * ``"tv_density"`` — the time-value density weights of
    ``Docs/iv_time_value_density_weights.tex``:

        w_i = max(TV_i, eps) * s_i / s_bar,

    where TV_i is the quote's time value (its OTM option price level), and s_i is
    the one-dimensional Voronoi cell width of the quote in normalized log-strike
    x = log(K/F). Dividing the economic weight TV by the local quote density
    1/s_i removes the accidental oversampling of dense strike regions, so the
    *aggregate* weight distribution over strike space follows TV(x) rather than
    the raw quote histogram. On a uniform x-grid all s_i are equal and the rule
    reduces to w_i = TV_i (the doc's benchmark property).

This weighting is orthogonal to the mid / bid-ask / haircut fit mode: the mode
chooses each quote's target, the scheme chooses how much each quote matters, and
the weight multiplies the residual in every mode (volfit.calib.band scales its
band-violation + anchor terms by sqrt(weight) just like the mid residual).

The returned weights are NORMALIZED to mean 1. Scaling all weights by a constant
leaves the unregularized least-squares solution unchanged but keeps the
data-vs-regularization balance identical to the equal scheme, so switching
schemes never silently over- or under-regularizes (LQD damping, the sigmoid
ridge, etc. are tuned against unit-mean weights).
"""

from __future__ import annotations

import numpy as np

from volfit.core.black import black_call

#: Cap on the spacing multiplier s_i / s_bar (doc "Practical notes"): stops a
#: single isolated far-wing quote from dominating the fit.
DEFAULT_MAX_MULT = 10.0
_EPS = 1e-12


def otm_time_value(k: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Time value of each OTM quote: its normalized forward option price.

    In forward-normalized (undiscounted, F = 1) units the OTM option carries no
    intrinsic value, so its whole price is time value: the call price for
    k >= 0, the put price (= call - (1 - e^k) by parity) for k < 0. ``w`` is the
    quote's total implied variance (so this is the *observed* time value).
    """
    k = np.asarray(k, dtype=float)
    call = black_call(k, np.maximum(np.asarray(w, dtype=float), _EPS))
    return np.where(k >= 0.0, call, call - (1.0 - np.exp(k)))


def tv_density_weights(
    k: np.ndarray, tv: np.ndarray, eps: float = _EPS, max_mult: float | None = DEFAULT_MAX_MULT
) -> np.ndarray:
    """Density-corrected time-value weights w_i = max(TV_i, eps) * s_i / s_bar.

    ``s_i`` is the 1-D Voronoi cell width in normalized log-strike ``k`` (half
    the gap to the neighbours on each side; one-sided at the ends). Returns
    weights in the input order; ``max_mult`` caps the spacing multiplier.
    """
    k = np.asarray(k, dtype=float)
    tv = np.maximum(np.asarray(tv, dtype=float), eps)
    m = k.size
    if m == 0:
        return np.array([], dtype=float)
    if m == 1:
        return np.array([tv[0]], dtype=float)

    order = np.argsort(k)
    xs = k[order]
    s = np.empty(m)
    s[0] = xs[1] - xs[0]
    s[-1] = xs[-1] - xs[-2]
    if m > 2:
        s[1:-1] = 0.5 * (xs[2:] - xs[:-2])
    s = np.maximum(s, eps)

    mult = s / s.mean()
    if max_mult is not None:
        mult = np.minimum(mult, max_mult)
    weights = np.empty(m)
    weights[order] = tv[order] * mult
    return weights


def resolve_weights(scheme: str, k: np.ndarray, w_mid: np.ndarray) -> np.ndarray | None:
    """Per-quote calibration weights for the chosen scheme (None = equal).

    ``None`` means unit weights (the calibrators' default). For "tv_density" the
    weights are mean-normalized so the data-vs-regularization balance matches the
    equal scheme. ``k``/``w_mid`` are the edited slice quotes actually fitted.
    """
    if scheme == "equal" or np.asarray(k).size == 0:
        return None
    if scheme == "tv_density":
        weights = tv_density_weights(k, otm_time_value(k, w_mid))
        mean = float(weights.mean())
        return weights / mean if mean > 0.0 else None
    raise ValueError(f"unknown weight scheme {scheme!r}")
