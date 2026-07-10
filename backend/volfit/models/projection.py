"""Publish-time wing projection onto the discrete arbitrage-free set
(Notes 09/10, Phase 3 — the "publish-time wing-only projection, core pinned").

The displayed model's wings can carry stated arbitrage past the traded strikes
(negative Durrleman g, calendar crossings vs the adjacent published expiry) —
measured by Phase 1 (``models.diagnostics.extrapolated_arb``) and optionally
leaned on during fits by Phase 2 (``calib.extrap``). Phase 3 acts at PUBLISH
time only: the exported curve samples are projected so the published artifact
itself is free of stated wing arbitrage, while

  * the TRADED CORE is pinned exactly (Note 09's confinement principle: a
    projection moves prices, so — like the de-Am repair — its authority must
    be confined away from the data even though the constraints it restores
    extend into the wings);
  * fits, cached calibrations and every in-app view stay untouched (the
    projection lives in the export path; quality's Phase-1 columns keep
    reporting the MODEL's own wings);
  * a clean pair is an exact no-op (the house additive-feature invariant) —
    the caller gets the original array back, byte-identical.

Mechanics: each wing is repaired in OTM-price space, where the discrete
arb-free set is simple — going OUTWARD from the pinned traded edge, the OTM
price must be non-increasing, convex in the (signed) strike coordinate with
its first slope no flatter than the core's edge slope (discrete butterfly-
freedom including the seam), and pointwise at or above the previous PUBLISHED
expiry's price at the same log-moneyness (calendar order in total variance;
expiries are projected in ascending maturity so the published surface is
jointly ordered). The repair only ever RAISES wing prices: floors are
propagated inward by a reverse running max (a later floor lifts everything
before it, since prices decrease outward), then one outward sweep lifts each
slope to at least its predecessor and caps it at zero. One floor pass + one
convexify pass is feasible by construction; prices then invert back to total
variance through the vectorized Black inversion. If the previous expiry's
published wing exceeds THIS expiry's pinned core edge, the crossing is the
core's business (the fit / quality gate), not the wing's — the floor is
capped at the edge value and the node is reported not fully clean.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.core.black import black_call, implied_total_variance

#: Absolute price tolerance below which the projection reports "unchanged"
#: and returns the caller's original array (exact no-op contract).
_PRICE_TOL = 1e-12


@dataclass(frozen=True)
class ProjectedWings:
    """Result of ``project_published_wings`` on one slice's sampled curve."""

    w: np.ndarray  # total variance on the same k grid (original object if unchanged)
    changed: bool  # any wing sample moved beyond _PRICE_TOL
    fully_clean: bool  # False when the pinned core edge made a calendar floor unreachable


def _prices(k: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(normalized call, normalized put) curves — one consistent instrument
    per wing: calls are non-increasing in k everywhere (any moneyness), puts
    non-decreasing, and both are convex in strike, so each wing's repair cone
    is well-defined without OTM-side switching inside a wing."""
    call = np.asarray(black_call(k, np.maximum(w, 1e-12)), dtype=float)
    put = call - (1.0 - np.exp(k))  # European parity, normalized by forward
    return call, put


def _repair_outward(
    coord: np.ndarray,
    values: np.ndarray,
    anchor_coord: float,
    anchor_value: float,
    anchor_slope: float,
    floors: np.ndarray,
) -> tuple[np.ndarray, bool]:
    """Lift outward-ordered OTM prices onto the discrete arb-free cone.

    ``coord`` is strictly increasing OUTWARD (x = e^k on the right wing, -x on
    the left), ``values`` the wing prices in that order, the anchor the pinned
    traded-edge sample with the core-side slope. Feasible set: slopes
    non-decreasing from ``anchor_slope``, capped at 0, values >= floors.
    Returns (repaired values, fully_clean).
    """
    v = np.asarray(values, dtype=float).copy()
    f = np.asarray(floors, dtype=float)
    clean = True
    # Prices decrease outward, so a floor at j lifts every point before it:
    # propagate floors inward (reverse running max), then cap at the pinned
    # anchor (slopes <= 0 make anything above it unreachable — core business).
    f_eff = np.maximum.accumulate(f[::-1])[::-1]
    over = f_eff > anchor_value + _PRICE_TOL
    if over.any():
        clean = False
        f_eff = np.minimum(f_eff, anchor_value)
    v = np.maximum(v, f_eff)
    # One outward convexify sweep: each slope at least its predecessor (lifts
    # v, never below the effective floor) and at most 0 (sets v to the
    # previous value, itself >= the inward-propagated floor).
    s_prev = min(anchor_slope, 0.0)
    c_prev, v_prev = anchor_coord, anchor_value
    for i in range(v.size):
        d = coord[i] - c_prev
        s = np.clip((v[i] - v_prev) / d, s_prev, 0.0)
        v[i] = v_prev + s * d
        s_prev, c_prev, v_prev = s, coord[i], v[i]
    return v, clean


def _wing_indices(k: np.ndarray, lo: float, hi: float) -> tuple[np.ndarray, np.ndarray]:
    core = (k >= lo - 1e-12) & (k <= hi + 1e-12)
    return np.flatnonzero(~core & (k < lo)), np.flatnonzero(~core & (k > hi))


def project_published_wings(
    k: np.ndarray,
    w: np.ndarray,
    k_lo_traded: float,
    k_hi_traded: float,
    prev_k: np.ndarray | None = None,
    prev_w: np.ndarray | None = None,
) -> ProjectedWings:
    """Project one sampled curve's wings; core samples byte-identical.

    ``prev_k``/``prev_w`` is the previous expiry's PUBLISHED curve (already
    projected — call in ascending maturity); None means no calendar floor.
    """
    k = np.asarray(k, dtype=float)
    w_in = np.asarray(w, dtype=float)
    left, right = _wing_indices(k, float(k_lo_traded), float(k_hi_traded))
    if left.size == 0 and right.size == 0:
        return ProjectedWings(w=w_in, changed=False, fully_clean=True)

    call, put = _prices(k, w_in)
    if prev_k is not None and prev_w is not None:
        prev_k = np.asarray(prev_k, dtype=float)
        prev_w = np.asarray(prev_w, dtype=float)

    def _floors(kw: np.ndarray, is_call: bool) -> np.ndarray:
        if prev_k is None or prev_w is None or kw.size == 0:
            return np.full(kw.size, -np.inf)
        inside = (kw >= prev_k[0]) & (kw <= prev_k[-1])  # no floor past the
        w_prev = np.interp(kw, prev_k, prev_w)           # prev STATED grid
        c, p = _prices(kw, w_prev)
        return np.where(inside, c if is_call else p, -np.inf)

    changed_call = call.copy()  # repaired values, in CALL terms throughout
    clean = True
    for idx, sign in ((right, 1.0), (left, -1.0)):
        if idx.size == 0:
            continue
        price = call if sign > 0 else put  # one instrument per wing
        outward = idx if sign > 0 else idx[::-1]
        edge = idx[0] - 1 if sign > 0 else idx[-1] + 1  # last core sample
        inner = edge - 1 if sign > 0 else edge + 1  # its core-side neighbour
        # Outward coordinate: x on the right, -x on the left — both ascending,
        # both giving a non-increasing convex wing price with slopes in [-1, 0].
        coord = sign * np.exp(k[outward])
        a_coord = sign * float(np.exp(k[edge]))
        a_value = float(price[edge])
        if 0 <= inner < k.size:
            i_coord = sign * float(np.exp(k[inner]))
            a_slope = (a_value - float(price[inner])) / (a_coord - i_coord)
        else:
            a_slope = -1.0  # single-sample core: loosest admissible slope
        floors = _floors(k[outward], is_call=sign > 0)
        repaired, wing_clean = _repair_outward(
            coord, price[outward], a_coord, a_value, max(a_slope, -1.0), floors
        )
        if sign > 0:
            changed_call[outward] = repaired
        else:  # puts back to calls by parity
            changed_call[outward] = repaired + (1.0 - np.exp(k[outward]))
        clean = clean and wing_clean

    changed_idx = np.abs(changed_call - call) > _PRICE_TOL
    if not changed_idx.any():
        return ProjectedWings(w=w_in, changed=False, fully_clean=clean)

    # Back to total variance through the vectorized Black inversion; only the
    # samples that moved are re-inverted (the core stays byte-identical).
    w_out = w_in.copy()
    idx = np.flatnonzero(changed_idx)
    w_new = implied_total_variance(k[idx], changed_call[idx])
    valid = np.isfinite(w_new)
    w_out[idx[valid]] = np.maximum(w_new[valid], 1e-12)
    return ProjectedWings(w=w_out, changed=True, fully_clean=clean)
