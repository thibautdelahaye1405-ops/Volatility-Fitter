"""Quote-band relaxation infeasibility diagnostic (V3.0 rider, opt-in).

Book chapter 2, Papers/book/chapters/02_lqd/07_calendar.tex (the passage
after eq. tailscalecalendar): "If the hard constraints are inconsistent with
the quote bands, no law stack can satisfy both those bands and the selected
tail policy. The meaningful diagnostic is the smallest quote-band relaxation
needed for feasibility. Shrinking the calendar domain would merely hide the
inconsistency outside the chosen interval."

The active-set exchange (volfit.calib.symmetric_exchange) reports a pair it
cannot certify as irreducible and leaves the accepted surface alone; this
module answers the book's follow-up question for such a pair: by how much
would BOTH slices' quote bands have to widen — symmetrically, delta vol
points on each edge, mids kept — for the exchange to certify them under the
selected tail policy? ``relax_pair`` bisects delta on (0, delta_max]: each
trial widens the two ``BandTarget``s carried by the specs' ``fit_kwargs``
(fresh SliceSpec copies — the caller's specs are never mutated), rebuilds
the pair's interface exactly as ``exchange_ladder`` does (tail contract
armed) and runs ``exchange_refit`` from the pair's current thetas; the trial
is feasible when the exchange converges, i.e. the full-line certificate
passes (tail clause included when the tail-order gate is armed).

Reading the result: ``delta_vol = 0`` means the pair certifies as it stands
(or a re-solve of the pair alone certifies it — no relaxation needed);
``feasible=False`` means not even ``delta_max`` suffices — the hard
constraints and the bands are inconsistent beyond the search ceiling, or
the tail clause is decided by unequal exponents (``tail_irreducible``: no
band width can move an exponent, so no solve is spent). ADVISORY: nothing
here changes a fit; api.surface_symmetric records the result per pair and
api.quality / api.export display it.

Import discipline: pool-worker importable — depends only on volfit.calib /
volfit.models / volfit.core (see volfit.calib.fit_task).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.calib.band import BandTarget
from volfit.calib.symmetric import IFACE_BASE_WEIGHT, SliceSpec, build_interface
from volfit.calib.symmetric_exchange import certify_ladder, exchange_refit, pair_ok

#: Search ceiling of the symmetric band widening, in vol units (5 vol points
#: per edge): a pair needing more is inconsistent for any practical purpose.
DELTA_MAX = 0.05

#: Bisection depth: the returned delta is resolved to delta_max / 2**rounds
#: (~2 vol bp at the defaults).
RELAX_ROUNDS = 8


@dataclass(frozen=True)
class BandRelaxation:
    """Outcome of ``relax_pair`` for one adjacent pair.

    ``delta_vol`` is the smallest feasible symmetric band widening found
    (vol units; 0.0 = no relaxation needed; None when infeasible up to
    ``delta_max``). ``feasible`` says whether any delta <= delta_max
    certified. ``rounds`` counts the exchange SOLVES spent (0 = decided by
    the certificate alone). ``certificate_gap_at_delta`` is the pair's
    min ledger gap at the returned delta (at delta_max when infeasible).
    ``delta_infeasible`` is the bisection bracket's failing end (the largest
    delta tried that did NOT certify; None when no trial failed) — the
    bisection invariant a test can check. ``tail_gated`` records whether
    the tail clause was part of the feasibility predicate.
    """

    delta_vol: float | None
    feasible: bool
    rounds: int
    certificate_gap_at_delta: float
    delta_infeasible: float | None = None
    delta_max: float = DELTA_MAX
    tail_gated: bool = False


def widen_spec(spec: SliceSpec, delta: float) -> SliceSpec:
    """A copy of ``spec`` whose band is widened by ``delta`` on each edge
    (mid kept; the lower edge floors at 0). Specs without a band, or a zero
    delta, come back as the caller's very object."""
    band = spec.fit_kwargs.get("band")
    if band is None or delta == 0.0:
        return spec
    kw = dict(spec.fit_kwargs)
    kw["band"] = BandTarget(
        iv_lo=np.maximum(np.asarray(band.iv_lo, dtype=float) - delta, 0.0),
        iv_mid=np.asarray(band.iv_mid, dtype=float),
        iv_hi=np.asarray(band.iv_hi, dtype=float) + delta,
    )
    return SliceSpec(t=spec.t, k=spec.k, w=spec.w, fit_kwargs=kw)


def has_band(specs: list[SliceSpec]) -> bool:
    """Whether any spec carries a band target (a band fit mode)."""
    return any(s.fit_kwargs.get("band") is not None for s in specs)


def pair_feasible_at(
    spec_near: SliceSpec,
    spec_far: SliceSpec,
    thetas: list[np.ndarray],
    delta: float,
    tail_gate: bool = False,
) -> tuple[bool, float]:
    """One trial: widen both bands by ``delta`` and run the exchange on the
    pair from ``thetas``. Returns (certified, min ledger gap) — the exchange
    interface is built as ``exchange_ladder`` builds it (tail contract on,
    base weight), so a trial answers exactly the production question."""
    specs = [widen_spec(spec_near, delta), widen_spec(spec_far, delta)]
    iface = build_interface(specs[0], specs[1], tail_contract=True)
    res = exchange_refit(
        specs, thetas, [iface], IFACE_BASE_WEIGHT, tail_gate=tail_gate
    )
    return bool(res.converged), float(res.certificates[0].min_gap)


def relax_pair(
    spec_near: SliceSpec,
    spec_far: SliceSpec,
    theta_near: np.ndarray,
    theta_far: np.ndarray,
    *,
    tail_gate: bool = False,
    delta_max: float = DELTA_MAX,
    rounds: int = RELAX_ROUNDS,
) -> BandRelaxation:
    """Smallest symmetric band widening under which the pair certifies.

    Order of business: (1) the certificate of the pair as it stands — a
    certified pair returns delta 0.0 with no solve; a gated tail clause
    decided by unequal exponents returns infeasible with no solve; a pair
    without bands has nothing to widen and returns infeasible with no solve;
    (2) one exchange at delta = 0 (the pair alone may certify where its
    component did not); (3) one exchange at ``delta_max`` — failing it, the
    pair is infeasible; (4) ``rounds`` bisection steps on the bracket, each
    a fresh exchange from the INPUT thetas (trial order never leaks into a
    trial's answer). The returned delta is the bracket's passing end.
    """
    thetas = [
        np.asarray(theta_near, dtype=float).copy(),
        np.asarray(theta_far, dtype=float).copy(),
    ]
    specs = [spec_near, spec_far]
    cert = certify_ladder(specs, thetas)[0]
    if pair_ok(cert, tail_gate):
        return BandRelaxation(
            delta_vol=0.0, feasible=True, rounds=0,
            certificate_gap_at_delta=float(cert.min_gap),
            delta_max=delta_max, tail_gated=tail_gate,
        )
    if (tail_gate and cert.tail_irreducible) or not has_band(specs):
        return BandRelaxation(
            delta_vol=None, feasible=False, rounds=0,
            certificate_gap_at_delta=float(cert.min_gap),
            delta_infeasible=delta_max, delta_max=delta_max, tail_gated=tail_gate,
        )
    solves = 0
    ok, gap = pair_feasible_at(spec_near, spec_far, thetas, 0.0, tail_gate)
    solves += 1
    if ok:
        return BandRelaxation(
            delta_vol=0.0, feasible=True, rounds=solves,
            certificate_gap_at_delta=gap, delta_max=delta_max, tail_gated=tail_gate,
        )
    ok, gap = pair_feasible_at(spec_near, spec_far, thetas, delta_max, tail_gate)
    solves += 1
    if not ok:
        return BandRelaxation(
            delta_vol=None, feasible=False, rounds=solves,
            certificate_gap_at_delta=gap, delta_infeasible=delta_max,
            delta_max=delta_max, tail_gated=tail_gate,
        )
    lo, hi, gap_hi = 0.0, delta_max, gap
    for _ in range(rounds):
        mid = 0.5 * (lo + hi)
        ok, gap = pair_feasible_at(spec_near, spec_far, thetas, mid, tail_gate)
        solves += 1
        if ok:
            hi, gap_hi = mid, gap
        else:
            lo = mid
    return BandRelaxation(
        delta_vol=hi, feasible=True, rounds=solves,
        certificate_gap_at_delta=gap_hi, delta_infeasible=lo,
        delta_max=delta_max, tail_gated=tail_gate,
    )
