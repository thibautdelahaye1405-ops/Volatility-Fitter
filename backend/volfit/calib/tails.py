"""Tail matching (the Compare view's three toggles): pull a straight-wing
family's extrapolation onto a REFERENCE slice's — LQD's — so every displayed
family shares similar tails and the comparison isolates belly expressiveness.

Three constraints, any subset, each a STIFF residual block (the hard-pin idiom
of volfit.calib.varswap.VARSWAP_PIN_MULT: equality to solver tolerance, not a
true constraint — trf / lm still trade it off, the trade just never wins):

  varswap  the family's fair var-swap (log-contract replication) onto the
           reference's. For fits to the SAME quotes the var-swap differs only
           through the extrapolated region (1/K^2-weighted, so mostly the left
           wing): a tail LEVEL constraint.
  lee      the asymptotic total-variance slopes (beta_L, beta_R) onto the
           reference's Lee slopes — the wing DIRECTION. Only defined when the
           reference is in the exponential class (LQD alpha = 0: a positive
           tail exponent makes the Lee slope exactly 0, unreachable for a
           straight-wing family); clamped strictly under the family's Lee cap.
  edge     value AND slope of total variance at the last quoted strike on
           each side — a C^1 match of the extrapolation ONSET, closest to what
           a trader sees: the models agree where the quotes end and each wing
           law governs beyond.

With all three on, SVI-JW (five handles) is over-determined by seven stiff
rows: the constraints are then met in the least-squares sense and the
Compare table's Lee / var-swap columns show how close. The target carries
the reference's numbers only; each calibrator appends ``tail_match_residuals``
as its LAST block — SVI (five parameters) FD-differentiated like its extrap
block, MCS through the closed-form ``tail_match_jacobian`` (sigmoid/tail_rows)
plus an anchor ridge and a stiffness ramp (see calibrate_sigmoid): the far
wings a var-swap row reads are parameters the quotes never pin, and without
those the bounded solver crawled for tens of seconds. ``None`` is
byte-identical everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from volfit.calib.varswap import (
    VARSWAP_PIN_MULT,
    VarSwapTarget,
    varswap_residual_w,
    varswap_total_variance,
)

#: The three toggles, in wire order.
TAIL_FLAGS = ("varswap", "lee", "edge")
#: Replication grid of the var-swap row: the DIAGNOSTICS grid (4001 points,
#: volfit.models.diagnostics.numeric_var_swap_w), not the coarser in-loop
#: grid of the market var-swap penalty — the pin must land on the number the
#: Compare table reports (on a one-month node the two grids differ by ~10 bp
#: of vol through the kink at k = 0). Cheap: these rows are FD'd only.
VS_MATCH_POINTS = 4001

#: One unit of slope difference (dw/dk) reads as this many vol points in the
#: residual — the extrap block's convention for its dimensionless hinges.
LEE_SCALE = 0.05
EDGE_SLOPE_SCALE = 0.05
#: Reference Lee slopes are clamped this far under the family's cap: the
#: structural charts lift the wings strictly INSIDE (0, cap), so a target at
#: the cap itself is unreachable (the eSSVI "held at 4 - 0.02" precedent).
LEE_CLAMP_MARGIN = 0.02
#: Floor on a target slope (a straight-wing family needs a rising wing).
LEE_FLOOR = 1e-3
#: Central-difference step for dw/dk at the quoted edges (log-moneyness).
_SLOPE_H = 1e-4
_W_FLOOR = 1e-12

WFn = Callable[[np.ndarray], np.ndarray]


@dataclass(frozen=True)
class EdgePoint:
    """Reference total variance and its k-slope at one quoted edge."""

    k: float
    w: float
    dw: float


@dataclass(frozen=True)
class TailReference:
    """What the reference slice offers, read ONCE per compare: its fair
    var-swap total variance, its Lee slopes (None when its tails are
    generalized — the asymptotic slope is then 0) and the two edge points."""

    var_swap_w: float
    lee: tuple[float, float] | None
    edge_left: EdgePoint
    edge_right: EdgePoint


@dataclass(frozen=True)
class TailMatchTarget:
    """The resolved rows for one family fit (picklable). ``weight`` is the
    stiff LSQ weight every row carries (sqrt applied per row)."""

    t: float
    weight: float
    var_swap: VarSwapTarget | None
    lee: tuple[float, float] | None
    edge: tuple[EdgePoint, EdgePoint] | None
    #: True when a reference Lee slope had to be pulled under the cap.
    lee_clamped: bool = False

    @property
    def applied(self) -> tuple[str, ...]:
        """The active constraints, in wire order."""
        return tuple(
            f for f, on in zip(TAIL_FLAGS, (self.var_swap, self.lee, self.edge)) if on is not None
        )


def slope_fd(implied_w: WFn, k: float, h: float = _SLOPE_H) -> float:
    """Central-difference dw/dk of a total-variance curve at ``k``."""
    w = np.asarray(implied_w(np.array([k - h, k + h])), dtype=float)
    return float((w[1] - w[0]) / (2.0 * h))


def tail_reference(slice_, k_lo: float, k_hi: float, lee: tuple[float, float] | None) -> TailReference:
    """Read the reference numbers off a fitted slice: the exact var-swap when
    the family has one (LQD's closed form), else the replication; the two
    edge points at the quoted extremes; ``lee`` as the caller resolved it."""
    implied_w = slice_.implied_w
    vs = getattr(slice_, "var_swap_strike", None)
    var_swap_w = (
        float(vs()) if callable(vs) else varswap_total_variance(implied_w, points=VS_MATCH_POINTS)
    )
    ends = np.asarray(implied_w(np.array([k_lo, k_hi])), dtype=float)
    return TailReference(
        var_swap_w=var_swap_w,
        lee=None if lee is None else (float(lee[0]), float(lee[1])),
        edge_left=EdgePoint(k=float(k_lo), w=float(ends[0]), dw=slope_fd(implied_w, k_lo)),
        edge_right=EdgePoint(k=float(k_hi), w=float(ends[1]), dw=slope_fd(implied_w, k_hi)),
    )


def build_tail_match(
    reference: TailReference,
    flags: tuple[str, ...] | frozenset[str],
    t: float,
    sum_weights: float,
    lee_cap: float,
) -> TailMatchTarget | None:
    """Resolve the requested flags against a reference into a fit target, or
    None when nothing applies (e.g. only ``lee`` asked of a generalized-tail
    reference). ``sum_weights`` is the node's summed option-quote weights (the
    stiff-row budget); ``lee_cap`` the family's Lee slope cap."""
    weight = VARSWAP_PIN_MULT * max(float(sum_weights), 1.0)
    var_swap = (
        VarSwapTarget(total_var=reference.var_swap_w, weight=weight, t=t)
        if "varswap" in flags
        else None
    )
    lee = None
    clamped = False
    if "lee" in flags and reference.lee is not None:
        hi = lee_cap - LEE_CLAMP_MARGIN
        pair = tuple(float(min(max(b, LEE_FLOOR), hi)) for b in reference.lee)
        clamped = pair != tuple(float(b) for b in reference.lee)
        lee = (pair[0], pair[1])
    edge = (reference.edge_left, reference.edge_right) if "edge" in flags else None
    if var_swap is None and lee is None and edge is None:
        return None
    return TailMatchTarget(t=t, weight=weight, var_swap=var_swap, lee=lee, edge=edge, lee_clamped=clamped)


def tail_match_residuals(
    implied_w: WFn, lee_fn: Callable[[], tuple[float, float]], target: TailMatchTarget
) -> np.ndarray:
    """The stiff tail-matching rows of one iterate, in wire order:
    [var-swap] [beta_L, beta_R] [left value, left slope, right value, right
    slope]. Values are vol-space differences; slopes are scaled by the
    vol-equivalent constants above. Zero when the iterate IS the reference."""
    sw = float(np.sqrt(target.weight))
    rows: list[float] = []
    if target.var_swap is not None:
        w_vs = varswap_total_variance(implied_w, points=VS_MATCH_POINTS)
        rows.append(varswap_residual_w(w_vs, target.var_swap))
    if target.lee is not None:
        b_l, b_r = lee_fn()
        rows.append(sw * LEE_SCALE * (float(b_l) - target.lee[0]))
        rows.append(sw * LEE_SCALE * (float(b_r) - target.lee[1]))
    if target.edge is not None:
        for e in target.edge:
            w_m = float(np.asarray(implied_w(np.array([e.k])), dtype=float)[0])
            vol_m = np.sqrt(max(w_m, _W_FLOOR) / target.t)
            vol_r = np.sqrt(max(e.w, _W_FLOOR) / target.t)
            rows.append(sw * (vol_m - vol_r))
            rows.append(sw * EDGE_SLOPE_SCALE * (slope_fd(implied_w, e.k) - e.dw))
    return np.asarray(rows, dtype=float)


WGradFn = Callable[[np.ndarray], tuple[np.ndarray, np.ndarray]]
LeeGradFn = Callable[[], tuple[tuple[float, float], tuple[np.ndarray, np.ndarray]]]


def tail_match_jacobian(w_grad: WGradFn, lee_grad: LeeGradFn, target: TailMatchTarget) -> np.ndarray:
    """ANALYTIC Jacobian of ``tail_match_residuals`` (same row order), for a
    model exposing ``w_grad(k) -> (w(k), dw/dtheta)`` (shapes (N,), (N, P))
    and ``lee_grad() -> ((beta_L, beta_R), (dbeta_L/dtheta, dbeta_R/dtheta))``.

    The var-swap row differentiates the log-contract replication under the
    integral: d w_vs / d theta = 2 int e^{-k} (dB/dw)(k, w) dw/dtheta dk on
    the SAME grid as the residual, then the vol chain 1 / (2 sigma_vs t);
    the edge slope row differentiates the residual's own central difference
    in k. Why it matters: the FD gradient of these rows costs 2P replications
    per Jacobian, and a stiff row on a many-parameter family (MCS, 6 + 4R)
    made the bounded solver crawl for tens of seconds — with the closed form
    the block costs one replication."""
    from volfit.core.black import black_call, black_vega_w  # local: keep calib light

    sw = float(np.sqrt(target.weight))
    blocks: list[np.ndarray] = []
    if target.var_swap is not None:
        k = np.linspace(-6.0, 6.0, VS_MATCH_POINTS)
        w, dw = w_grad(k)
        w = np.maximum(np.asarray(w, dtype=float), _W_FLOOR)
        call = black_call(k, w)
        integrand = call * np.exp(-k)
        put_side = k < 0.0
        integrand[put_side] += 1.0 - np.exp(-k[put_side])
        w_vs = 2.0 * float(np.trapezoid(integrand, k))
        d_w_vs = 2.0 * np.trapezoid((black_vega_w(k, w) * np.exp(-k))[:, None] * dw, k, axis=0)
        vol_vs = float(np.sqrt(max(w_vs, _W_FLOOR) / target.t))
        blocks.append(sw * d_w_vs / (2.0 * vol_vs * target.t))
    if target.lee is not None:
        _, (g_l, g_r) = lee_grad()
        blocks.append(sw * LEE_SCALE * np.asarray(g_l, dtype=float))
        blocks.append(sw * LEE_SCALE * np.asarray(g_r, dtype=float))
    if target.edge is not None:
        for e in target.edge:
            w3, dw3 = w_grad(np.array([e.k - _SLOPE_H, e.k, e.k + _SLOPE_H]))
            vol_m = float(np.sqrt(max(float(w3[1]), _W_FLOOR) / target.t))
            blocks.append(sw * dw3[1] / (2.0 * vol_m * target.t))
            blocks.append(sw * EDGE_SLOPE_SCALE * (dw3[2] - dw3[0]) / (2.0 * _SLOPE_H))
    return np.vstack(blocks) if blocks else np.zeros((0, 0))
