"""Strip-vs-tails split of the var-swap replication for the VarSwapInfo wire.

Roadmap V3.6 rider (Docs/forward_roadmap_v3.md, item 14): "strip vs tail
decomposition of the replication (varswap.py truncates at +-6)". The var-swap
fair variance is a log-contract replication over ALL strikes, but only the
quoted strike span [k_lo, k_hi] is observed — everything outside it is the
model's extrapolated wing. This module reports how much of the replicated
variance comes from each region, so the desk can see whether a var-swap level
is a market fact or a wing assumption. READ-ONLY: nothing here enters any
objective (fits are byte-identical).

Two model paths, both partitioning the model's OWN replication cell by cell:

  * parametric nodes (``parametric_varswap_split``): the displayed slice's
    ``implied_w`` on the standard +-6 / 801-point grid of
    volfit.calib.varswap.varswap_decomposition;
  * Local-Vol expiries (``lattice_varswap_split``): the static replication on
    the PDE strike lattice — the SAME trapezoid the LV var-swap level is read
    from (affine_calib.varswap_weights / varswap_const, recombined per cell) —
    which is truncated at the lattice: left at x = affine_fit._VARSWAP_K_LO
    (k = ln 0.01 ~ -4.6), right at x_max (the Dupire prices cannot be evaluated
    beyond the lattice: ``price_at`` clamps, and inverting clamped prices
    manufactures numbers). The split's ``total_w`` is therefore the LV
    "static" level to rounding; under the "source_pde" var-swap method the
    displayed level comes from the source PDE while the SHARES still describe
    the static replication (a display twin — the only strike-resolved form).

``split_fields`` maps a decomposition onto the five optional VarSwapInfo
fields (``stripVarShare``, ``tailVarShareLeft``, ``tailVarShareRight``,
``stripKLo``, ``stripKHi``); None everywhere when there is nothing to report.
"""

from __future__ import annotations

import numpy as np

from volfit.api.displayed import displayed_slice
from volfit.api.state import FitRecord
from volfit.calib.varswap import VarSwapDecomposition, varswap_decomposition

#: The five optional VarSwapInfo fields this module owns, all None.
_EMPTY_FIELDS: dict[str, float | None] = {
    "stripVarShare": None,
    "tailVarShareLeft": None,
    "tailVarShareRight": None,
    "stripKLo": None,
    "stripKHi": None,
}


def split_fields(decomp: VarSwapDecomposition | None) -> dict[str, float | None]:
    """VarSwapInfo keyword arguments for a decomposition (all None if absent
    or if the replicated total is not positive — no share can be formed)."""
    if decomp is None:
        return dict(_EMPTY_FIELDS)
    shares = decomp.shares()
    if shares is None:
        return dict(_EMPTY_FIELDS)
    strip, left, right = shares
    return {
        "stripVarShare": float(strip),
        "tailVarShareLeft": float(left),
        "tailVarShareRight": float(right),
        "stripKLo": float(decomp.k_lo),
        "stripKHi": float(decomp.k_hi),
    }


def quoted_span(k: np.ndarray | None) -> tuple[float, float] | None:
    """[min, max] log-moneyness of the INCLUDED quotes (None when < 1 quote
    or non-finite) — the strip the split is measured on."""
    if k is None:
        return None
    k = np.asarray(k, dtype=float)
    if k.size == 0:
        return None
    lo, hi = float(k.min()), float(k.max())
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return None
    return lo, hi


def parametric_varswap_split(
    record: FitRecord, k_included: np.ndarray | None
) -> VarSwapDecomposition | None:
    """Split of a parametric node's replication (displayed slice: LQD or the
    overlay) on the standard +-6 grid, over the included quotes' k span.

    Note the total is the REPLICATION (varswap_total_variance's number), which
    for an LQD node differs from the displayed closed-form level
    (LQDSlice.var_swap_strike) by the +-6 truncation and the 801-point rule —
    well under a basis point; the shares are of the replication.
    """
    span = quoted_span(k_included)
    if span is None:
        return None
    try:
        return varswap_decomposition(displayed_slice(record).implied_w, span[0], span[1])
    except (ValueError, FloatingPointError):  # a degenerate curve: report nothing
        return None


def lattice_varswap_split(
    x_grid: np.ndarray,
    prices: np.ndarray,
    k_lo: float,
    k_hi: float,
    x_lo: float,
) -> VarSwapDecomposition | None:
    """Split of the Local-Vol static var-swap replication on the PDE lattice.

    Rebuilds affine_calib.varswap_weights / varswap_const cell by cell —
    trapezoid in x = K/F over the put leg [x_lo, 1] with integrand
    2 (C + x - 1) / x^2 = 2 P / x^2 and the call leg [1, x_max] with
    2 C / x^2 (the parity constant is recombined pointwise, so every cell
    carries the OTM option it replicates, exactly as in the +-6 form) — and
    assigns each cell whole to a region by its midpoint's log-moneyness
    ln(x_mid): left tail below ``k_lo``, strip on [k_lo, k_hi], right tail
    above. The sum of the cells is ``varswap_weights @ prices + varswap_const``
    to rounding. Truncation is the lattice's own (see the module docstring).
    None when the lattice lacks the x = 1 anchor or has fewer than two usable
    points per leg (the replication itself is undefined there).
    """
    x = np.asarray(x_grid, dtype=float)
    c = np.asarray(prices, dtype=float)
    if x.size < 2 or c.shape != x.shape:
        return None
    i1 = int(np.searchsorted(x, 1.0))
    if i1 >= x.size or x[i1] != 1.0:
        return None
    mask = x >= max(float(x_lo), 1e-12)
    put_idx = np.nonzero(mask & (x <= 1.0))[0]
    call_idx = np.nonzero(x >= 1.0)[0]
    if put_idx.size < 2 or call_idx.size < 2:
        return None
    xp, xc = x[put_idx], x[call_idx]
    f_put = 2.0 * (c[put_idx] + xp - 1.0) / (xp * xp)  # 2 P / x^2 (parity, pointwise)
    f_call = 2.0 * c[call_idx] / (xc * xc)  # 2 C / x^2
    cells = np.concatenate([
        0.5 * np.diff(xp) * (f_put[1:] + f_put[:-1]),
        0.5 * np.diff(xc) * (f_call[1:] + f_call[:-1]),
    ])
    mid_x = np.concatenate([0.5 * (xp[1:] + xp[:-1]), 0.5 * (xc[1:] + xc[:-1])])
    k_mid = np.log(mid_x)
    left = k_mid < k_lo
    right = (k_mid > k_hi) & ~left
    strip = ~left & ~right
    return VarSwapDecomposition(
        strip_w=float(cells[strip].sum()),
        tail_left_w=float(cells[left].sum()),
        tail_right_w=float(cells[right].sum()),
        total_w=float(cells.sum()),
        k_lo=float(k_lo),
        k_hi=float(k_hi),
    )
