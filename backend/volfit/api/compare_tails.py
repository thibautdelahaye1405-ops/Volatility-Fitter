"""Tail matching in the compare endpoint (the Compare view's three toggles).

Plumbing between the wire and volfit.calib.tails: parse the ``tail_match``
CSV, read the REFERENCE numbers off the LQD row's slice (its closed-form
var-swap, its Lee slopes when its tails are exponential, the value + slope of
total variance at the two quoted edges), resolve them into the stiff
``TailMatchTarget`` the SVI-JW / MCS ad-hoc fits append, and report what
happened on the wire (``TailMatchInfo``). LQD is the reference by choice: the
arbitrage-free backbone with analytic tails and var-swap. The eSSVI yardstick
is never constrained (its wings are tied to all three of its handles), and
neither is the reference itself.
"""

from __future__ import annotations

import numpy as np

from volfit.api.schemas_compare import TailMatchInfo
from volfit.calib.tails import (
    TAIL_FLAGS,
    TailMatchTarget,
    TailReference,
    build_tail_match,
    tail_reference,
)
from volfit.models.lqd.basis import lee_slopes

#: The straight-wing families the toggles constrain.
TAIL_FAMILIES = ("svi", "sigmoid")

_NOTE_LEE_GENERALIZED = (
    "LQD's tails are generalized on this name (alpha > 0): its asymptotic Lee "
    "slope is 0, which no straight-wing family can match — use Edge match"
)


def parse_tail_flags(csv: str) -> tuple[str, ...]:
    """The requested toggles as a deduplicated tuple in wire order; a ValueError
    names any unknown flag (the router turns it into a 422)."""
    wanted = {f.strip().lower() for f in csv.split(",") if f.strip()}
    unknown = sorted(wanted - set(TAIL_FLAGS))
    if unknown:
        raise ValueError(f"tail_match must be a CSV subset of {list(TAIL_FLAGS)}; unknown: {unknown}")
    return tuple(f for f in TAIL_FLAGS if f in wanted)


def reference_of(lqd_slice, k: np.ndarray) -> TailReference:
    """The reference numbers of a fitted LQD slice over the quoted range
    [min k, max k]: Lee slopes only in the exponential class (a positive tail
    exponent on either side makes that side's slope 0 — unmatchable)."""
    p = lqd_slice.params
    exponential = float(p.alpha_left) <= 0.0 and float(p.alpha_right) <= 0.0
    lee = lee_slopes(p) if exponential else None
    return tail_reference(lqd_slice, float(np.min(k)), float(np.max(k)), lee)


def resolve_tail_match(
    flags: tuple[str, ...],
    lqd_slice,
    lqd_error: str | None,
    k: np.ndarray,
    tau: float,
    weights: np.ndarray | None,
    lee_cap: float,
) -> tuple[TailMatchTarget | None, TailMatchInfo]:
    """Turn the requested flags into the per-family target (None when nothing
    can apply) plus the wire info explaining any dropped flag."""
    info = TailMatchInfo(requested=list(flags))
    if not flags:
        return None, info
    if lqd_slice is None or k.size == 0:
        info.note = (
            f"tail matching needs the LQD reference fit: {lqd_error}"
            if lqd_error
            else "tail matching needs the LQD reference fit (no quotes)"
        )
        return None, info
    ref = reference_of(lqd_slice, k)
    sum_w = float(np.sum(weights)) if weights is not None else float(k.size)
    target = build_tail_match(ref, flags, tau, sum_w, lee_cap)
    info.leeAvailable = ref.lee is not None
    info.referenceVarSwapVol = float(np.sqrt(max(ref.var_swap_w, 0.0) / tau)) if tau > 0.0 else None
    info.referenceLeeLeft = None if ref.lee is None else float(ref.lee[0])
    info.referenceLeeRight = None if ref.lee is None else float(ref.lee[1])
    info.edgeKLeft = ref.edge_left.k
    info.edgeKRight = ref.edge_right.k
    if "lee" in flags and ref.lee is None:
        info.note = _NOTE_LEE_GENERALIZED
    if target is not None:
        info.applied = list(target.applied)
        info.leeClamped = target.lee_clamped
        if target.lee_clamped:
            info.note = (
                f"LQD's Lee slopes exceed the family cap {lee_cap:.2f}: matched at the cap"
            )
    return target, info
