"""Per-slice quote weighting schemes for calibration (a given maturity).

Four schemes, selectable by the FitSettings.weightScheme hyperparameter:

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
  * ``"vega_density"`` — same density correction, economic shape = Black vega:
    ``raw_i = phi(d_plus(k_i, w_i))``. The per-slice ``sqrt(t)`` factor of the
    true vega is a constant and cancels under the mean-1 normalization. The
    natural scheme when the target metric is vol error: each quote counts by
    how much option value one vol point moves at its strike.
  * ``"delta_density"`` — same density correction, economic shape = the OTM
    option's forward |delta|: ``N(d_plus)`` for k >= 0 (OTM call),
    ``1 - N(d_plus)`` for k < 0 (OTM put) — weight by the hedge size the
    strike commands.

    Wing behaviour orders the three shapes (large |d| asymptotics): vega
    ~ phi(d) is the flattest, delta ~ phi(d)/d one power faster, time value
    ~ phi(d)/d^2 fastest — so vega keeps the most relative wing weight and
    tv_density the least, with delta in between. All three keep the note's
    density correction ``s_i / s_bar`` — a pure delta or vega weight would
    re-introduce exactly the strike-crowding bias the note argues against.

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

from dataclasses import dataclass

import numpy as np

from volfit.core.black import W_MIN, black_call, norm_cdf, norm_pdf

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


def _d_plus(k: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Black d_plus from log-moneyness and total variance (w floored at W_MIN)."""
    k = np.asarray(k, dtype=float)
    sq = np.sqrt(np.maximum(np.asarray(w, dtype=float), W_MIN))
    return -k / sq + 0.5 * sq


def vega_profile(k: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Black vega shape phi(d_plus): the true vega up to the per-slice sqrt(t).

    The omitted sqrt(t) is constant across a slice, so under the mean-1
    normalization the weights are exactly those of the true Black vega.
    """
    return norm_pdf(_d_plus(k, w))


def otm_delta(k: np.ndarray, w: np.ndarray) -> np.ndarray:
    """|forward delta| of each OTM quote: N(d+) for k >= 0, 1 - N(d+) for k < 0.

    The OTM convention matches ``otm_time_value``: strikes above the forward are
    calls (delta N(d+), ~0.5 at the money decaying to 0 in the right wing),
    below are puts (|delta| = 1 - N(d+), symmetric story on the left).
    """
    d = _d_plus(k, w)
    return np.where(np.asarray(k, dtype=float) >= 0.0, norm_cdf(d), 1.0 - norm_cdf(d))


def scheme_raw(scheme: str, k: np.ndarray, w_mid: np.ndarray) -> np.ndarray:
    """The pre-normalization economic weight of each density scheme (eps-floored).

    Single source of truth for the scheme -> shape mapping, shared by
    ``resolve_weights``, ``weight_components`` and the prior data-gap anchor's
    desired-density shape (volfit.calib.prior), so they can never disagree.
    Raises on an unknown or non-density scheme ("equal" has no raw shape).
    """
    if scheme == "tv_density":
        return np.maximum(otm_time_value(k, w_mid), _EPS)
    if scheme == "vega_density":
        return np.maximum(vega_profile(k, w_mid), _EPS)
    if scheme == "delta_density":
        return np.maximum(otm_delta(k, w_mid), _EPS)
    raise ValueError(f"unknown weight scheme {scheme!r}")


def _voronoi_spacing(k: np.ndarray, eps: float) -> tuple[np.ndarray, np.ndarray]:
    """(spacing, order): 1-D Voronoi cell widths of ``k`` in ASCENDING order.

    Half the gap to the neighbours on each side, one-sided at the ends, floored
    at ``eps``. ``order = argsort(k)`` maps the sorted rows back to the input
    order (``spacing_input[order] = spacing``). Requires k.size >= 2 (callers
    guard the degenerate sizes). Extracted from ``tv_density_weights`` so the
    weight-inspection endpoint reports the exact cell widths the scheme uses.
    """
    m = k.size
    order = np.argsort(k)
    xs = k[order]
    s = np.empty(m)
    s[0] = xs[1] - xs[0]
    s[-1] = xs[-1] - xs[-2]
    if m > 2:
        s[1:-1] = 0.5 * (xs[2:] - xs[:-2])
    return np.maximum(s, eps), order


def tv_density_weights(
    k: np.ndarray, tv: np.ndarray, eps: float = _EPS, max_mult: float | None = DEFAULT_MAX_MULT
) -> np.ndarray:
    """Density-corrected weights w_i = max(raw_i, eps) * s_i / s_bar.

    The shared density-correction engine of every non-equal scheme: ``tv`` is
    the scheme's economic raw shape (time value, vega profile or OTM delta —
    the name predates the extra schemes). ``s_i`` is the 1-D Voronoi cell width
    in normalized log-strike ``k`` (half the gap to the neighbours on each
    side; one-sided at the ends). Returns weights in the input order;
    ``max_mult`` caps the spacing multiplier.
    """
    k = np.asarray(k, dtype=float)
    tv = np.maximum(np.asarray(tv, dtype=float), eps)
    m = k.size
    if m == 0:
        return np.array([], dtype=float)
    if m == 1:
        return np.array([tv[0]], dtype=float)

    s, order = _voronoi_spacing(k, eps)

    mult = s / s.mean()
    if max_mult is not None:
        mult = np.minimum(mult, max_mult)
    weights = np.empty(m)
    weights[order] = tv[order] * mult
    return weights


@dataclass(frozen=True)
class WeightComponents:
    """Decomposition of one slice's quote weights (V3.4 weight inspection).

    All arrays are in the INPUT quote order, aligned with ``k``:

      * ``spacing`` — the Voronoi cell width s_i actually used by tv_density
        (0.0 with fewer than 2 quotes, where no cell exists);
      * ``raw`` — the pre-normalization economic weight: max(TV_i, eps) for
        tv_density, 1.0 for equal;
      * ``weights`` — the final mean-1 weights the LSQ uses, byte-identical to
        ``resolve_weights`` (ones materialized for "equal" / degenerate sizes).

    Invariant (>= 2 quotes, tv_density): mean-normalizing
    ``raw * min(spacing / spacing.mean(), max_mult)`` reproduces ``weights``.
    """

    scheme: str
    max_mult: float
    spacing: np.ndarray
    raw: np.ndarray
    weights: np.ndarray


def weight_components(scheme: str, k: np.ndarray, w_mid: np.ndarray) -> WeightComponents:
    """``resolve_weights`` plus its pre-normalization pieces (never re-derived).

    The final ``weights`` come from ``resolve_weights`` itself (the single
    implementation of the scheme); ``spacing`` reuses the same ``_voronoi_
    spacing`` helper tv_density is built on, remapped to input order.
    """
    k = np.asarray(k, dtype=float)
    m = int(k.size)
    spacing = np.zeros(m, dtype=float)
    if m >= 2:
        s, order = _voronoi_spacing(k, _EPS)
        spacing[order] = s
    if scheme == "equal":
        return WeightComponents(
            "equal", DEFAULT_MAX_MULT, spacing, np.ones(m), np.ones(m)
        )
    raw = scheme_raw(scheme, k, np.asarray(w_mid, dtype=float))  # raises if unknown
    resolved = resolve_weights(scheme, k, w_mid)
    weights = np.ones(m, dtype=float) if resolved is None else resolved
    return WeightComponents(scheme, DEFAULT_MAX_MULT, spacing, raw, weights)


def resolve_weights(scheme: str, k: np.ndarray, w_mid: np.ndarray) -> np.ndarray | None:
    """Per-quote calibration weights for the chosen scheme (None = equal).

    ``None`` means unit weights (the calibrators' default). Every density
    scheme is mean-normalized so the data-vs-regularization balance matches the
    equal scheme. ``k``/``w_mid`` are the edited slice quotes actually fitted.
    Raises ValueError on an unknown scheme.
    """
    if scheme == "equal" or np.asarray(k).size == 0:
        return None
    weights = tv_density_weights(k, scheme_raw(scheme, k, w_mid))
    mean = float(weights.mean())
    return weights / mean if mean > 0.0 else None
