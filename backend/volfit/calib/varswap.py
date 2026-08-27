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
option-quote weight of the node (see volfit.api.service.varswap_target):

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

#: Hard-pin escalation for the MARKET var-swap quote row (OptionsSettings.
#: varSwapHardPin): the row weight becomes VARSWAP_PIN_MULT x the summed
#: option-quote weights — the codebase's stiff-row idiom (cf. the 1e6 calendar
#: rows). 1e4 makes the single row ~100x the whole data block in residual
#: units, forcing the fitted var-swap onto the quote to SOLVER tolerance —
#: this is equality-to-tolerance, NOT a true constraint (trf/lm still trade it
#: off, the trade just never wins). Kept below the 1e6 calendar weight so a
#: pinned quote cannot override the arbitrage rows.
VARSWAP_PIN_MULT = 1e4


@dataclass(frozen=True)
class VarSwapTarget:
    """A resolved var-swap penalty for one slice fit.

    ``total_var`` is the quoted fair *total* variance (sigma_vs^2 * t);
    ``weight`` is the LSQ weight of the single var-swap residual, set by the
    caller to a fraction of the node's summed option-quote weights.

    ``mode`` selects the residual carrier (tail-persistence arc). "absolute"
    (the default — byte-identical) compares var-swap VOL levels. "atm_spread"
    compares the var-swap-minus-ATM vol SPREAD instead:
    ``(sigma_vs(model) - sigma_atm(model)) - (sigma_vs_ref - sigma_atm_ref)``
    with ``sigma_atm_ref = sqrt(atm_total_var / t)`` — the tail-mass-over-body
    carrier, so an ATM level move carries the tail along rather than fighting
    a stale absolute level. Only PRIOR companion rows ever set it (see
    volfit.api.service): market var-swap quotes are always absolute.
    ``atm_total_var`` is the reference ATM total variance at ``t`` (read only
    in atm_spread mode).
    """

    total_var: float
    weight: float
    t: float
    mode: str = "absolute"  # "absolute" | "atm_spread"
    atm_total_var: float = 0.0


def _replication_integrand(
    implied_w: Callable[[np.ndarray], np.ndarray], half_width: float, points: int
) -> tuple[np.ndarray, np.ndarray]:
    """The log-contract replication grid ``k`` and its OTM integrand.

    Shared by ``varswap_total_variance`` (one trapezoid over the whole grid)
    and ``varswap_decomposition`` (the same trapezoid cells, partitioned by
    strike region) so both read the SAME numbers: this is exactly the body
    the total-variance function always had, moved verbatim — same operations
    in the same order, so its float is bit-identical to before.

    On the call side (k >= 0) the integrand is B(k, w) e^{-k}; on the put side
    the parity term (e^k - 1) e^{-k} is added POINTWISE, which turns the ITM
    call into the OTM put: (B - (1 - e^k)) e^{-k} = P(k, w) e^{-k}. The parity
    term is therefore not a lump constant but part of every put-side cell's
    integrand (see ``varswap_decomposition`` for what that means for the split).
    """
    k = np.linspace(-half_width, half_width, points)
    w = np.maximum(np.asarray(implied_w(k), dtype=float), _W_FLOOR)
    call = black_call(k, w)  # normalized OTM call price B(k, w)
    integrand = call * np.exp(-k)
    put_side = k < 0.0
    integrand[put_side] += 1.0 - np.exp(-k[put_side])  # (e^k - 1) e^{-k}
    return k, integrand


def varswap_total_variance(
    implied_w: Callable[[np.ndarray], np.ndarray],
    half_width: float = VS_HALF_WIDTH,
    points: int = VS_POINTS,
) -> float:
    """Fair var-swap total variance of a smile curve by log-contract replication.

    ``implied_w(k)`` returns total implied variance on a log-moneyness array;
    that is the only thing the integral needs, so this works for any model.
    """
    k, integrand = _replication_integrand(implied_w, half_width, points)
    return 2.0 * float(np.trapezoid(integrand, k))


@dataclass(frozen=True)
class VarSwapDecomposition:
    """Strip-vs-tails split of the replicated var-swap total variance.

    ``strip_w`` is the mass replicated from the quoted strike span
    [``k_lo``, ``k_hi``], ``tail_left_w`` / ``tail_right_w`` the mass from the
    extrapolated wings below / above it, and ``total_w`` the whole replication
    (== ``varswap_total_variance`` bit-for-bit). By construction
    ``strip_w + tail_left_w + tail_right_w == total_w`` to rounding.
    READ-ONLY diagnostic (roadmap V3.6 rider): nothing here enters an objective.
    """

    strip_w: float
    tail_left_w: float
    tail_right_w: float
    total_w: float
    k_lo: float
    k_hi: float

    def shares(self) -> tuple[float, float, float] | None:
        """(strip, left, right) fractions of ``total_w``; None when it is <= 0."""
        if not (self.total_w > 0.0) or not np.isfinite(self.total_w):
            return None
        return (
            self.strip_w / self.total_w,
            self.tail_left_w / self.total_w,
            self.tail_right_w / self.total_w,
        )


def varswap_decomposition(
    implied_w: Callable[[np.ndarray], np.ndarray],
    k_lo: float,
    k_hi: float,
    half_width: float = VS_HALF_WIDTH,
    points: int = VS_POINTS,
) -> VarSwapDecomposition:
    """Partition the log-contract replication into left tail / strip / right tail.

    The SAME integrand on the SAME grid as ``varswap_total_variance`` (one
    shared helper), so ``total_w`` is that function's value bit-for-bit. Each
    trapezoid cell [k_i, k_{i+1}] is assigned WHOLE to one region by its
    midpoint m_i = (k_i + k_{i+1}) / 2:

        left tail   m_i <  k_lo
        strip       k_lo <= m_i <= k_hi     (the quoted strike span)
        right tail  m_i >  k_hi

    so the three parts sum to the total exactly (up to summation rounding);
    no cell is split or counted twice. ``k_lo``/``k_hi`` are the log-moneyness
    span of the INCLUDED quotes; a degenerate span (k_lo == k_hi, or k_lo >
    k_hi) yields an empty strip and every cell falls in a tail.

    Attribution of the put-parity term: in this formulation the parity term
    (e^k - 1) e^{-k} is applied pointwise on k < 0 (it converts the ITM call
    into the OTM put — see ``_replication_integrand``), so it is NOT a lump
    constant that could be handed to one region; every cell carries the OTM
    option integrand 2 P e^{-k} (puts) or 2 C e^{-k} (calls) and the parity
    part is attributed cell-by-cell with the strike it belongs to. Concretely,
    the strip receives the parity mass on [k_lo, 0] whenever it contains k = 0
    and the left tail receives the rest on [-half_width, k_lo]; when the strip
    sits entirely on one side of k = 0, the tail containing k = 0 takes all of
    the parity mass on its side. (Assigning the raw lump 2 * int_{-6}^0 (1 -
    e^{-k}) dk ~ -793 to a single region would put the shares far outside
    [0, 1] — the pointwise form is the only meaningful attribution.)
    """
    k, integrand = _replication_integrand(implied_w, half_width, points)
    # np.trapezoid's own cells: d * (y[1:] + y[:-1]) / 2 — the same arithmetic,
    # so summing every cell reproduces the total to rounding.
    cells = 2.0 * (np.diff(k) * (integrand[1:] + integrand[:-1]) / 2.0)
    mid = 0.5 * (k[1:] + k[:-1])
    left = mid < k_lo
    right = (mid > k_hi) & ~left  # mutually exclusive even for an inverted span
    strip = ~left & ~right
    return VarSwapDecomposition(
        strip_w=float(cells[strip].sum()),
        tail_left_w=float(cells[left].sum()),
        tail_right_w=float(cells[right].sum()),
        total_w=2.0 * float(np.trapezoid(integrand, k)),
        k_lo=float(k_lo),
        k_hi=float(k_hi),
    )


def varswap_residual_w(
    w_model: float, target: VarSwapTarget, w_atm_model: float | None = None
) -> float:
    """The single vol-space var-swap penalty residual from a model var-swap w.

    sqrt(weight) * (sigma_vs_model - sigma_vs_quote), both var-swap vols. Take
    ``w_model`` (the model's fair var-swap TOTAL variance) from whatever is
    cheapest for the model: LQD's exact closed form (LQDSlice.var_swap_strike)
    or ``varswap_total_variance`` for SVI / sigmoid (cheap arithmetic curves).
    The caller appends this scalar to its residual vector (length is constant
    across iterations, so scipy's numerical Jacobian handles it).

    In ``atm_spread`` mode the caller must also pass ``w_atm_model`` — the
    model's ATM total variance ``w(0)`` — and the residual becomes the spread
    difference (see VarSwapTarget). A missing ``w_atm_model`` silently falls
    back to the absolute carrier (the LV path relies on this).

    Using the model's own cheap var-swap is essential for speed: evaluating the
    generic replication on an LQD curve (whose implied_w solves a per-point root)
    every Jacobian column makes a single fit take minutes.
    """
    vol_model = float(np.sqrt(max(w_model, _W_FLOOR) / target.t))
    vol_quote = float(np.sqrt(max(target.total_var, _W_FLOOR) / target.t))
    if target.mode == "atm_spread" and w_atm_model is not None:
        # Spread carrier: subtract each side's own ATM vol so the row compares
        # (sigma_vs - sigma_atm) model-vs-reference instead of absolute levels.
        vol_model -= float(np.sqrt(max(w_atm_model, _W_FLOOR) / target.t))
        vol_quote -= float(np.sqrt(max(target.atm_total_var, _W_FLOOR) / target.t))
    return float(np.sqrt(max(target.weight, 0.0)) * (vol_model - vol_quote))


def varswap_residual(
    implied_w: Callable[[np.ndarray], np.ndarray],
    target: VarSwapTarget,
) -> float:
    """Var-swap penalty residual for a model exposing only ``implied_w(k)``.

    Computes the model var-swap by replication, then defers to
    ``varswap_residual_w``. Suitable for SVI / sigmoid (cheap closed-form total
    variance); LQD should pass its exact var-swap via ``varswap_residual_w``.
    In ``atm_spread`` mode the model's ATM total variance ``w(0)`` is read off
    the same curve (one extra evaluation; absolute mode stays byte-identical).
    """
    w_atm = None
    if target.mode == "atm_spread":
        w_atm = float(np.asarray(implied_w(np.array([0.0])), dtype=float)[0])
    return varswap_residual_w(varswap_total_variance(implied_w), target, w_atm)
