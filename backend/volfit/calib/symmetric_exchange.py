"""In-solver active-set exchange for hard LQD calendar constraints.

Tails+calendar arc Phase 4 (Docs/generalized_tails_calendar_roadmap.md;
forward roadmap V3.0). Book chapter 2 (Papers/book/chapters/02_lqd): the
accepted maturity stack must satisfy the FULL-LINE ledger order

    G_{j+1}(z) - G_j(z) >= 0   for every z in R
                                    (eq. globalledgerconstraint)

for every adjacent pair, as a HARD constraint — "not residuals whose
violation can be traded against a slightly better quote fit" (section
"Full-line constraints in calibration"). The least-squares implementation is
the book's active-set exchange (B_implementation.tex, "Exchange algorithm
for global calendar order"):

    active = initial_calendar_ranks(nodes)
    while True:
        surface = constrained_joint_solve(nodes, active)
        worst = full_line_calendar_minima(surface)
        if worst.value >= -calendar_tol: return surface
        active[worst.pair].add(worst.rank)

Here ``constrained_joint_solve`` is ``symmetric_stack.joint_refit`` with the
per-rank ledger rows sqrt(EXCHANGE_W) * max(A_near(z_r) - A_far(z_r), 0)
(analytic ``asset_share_rows`` Jacobian), and
``full_line_calendar_minima`` is the EXACT Phase 0 certificate
(volfit.calib.calendar_certificate) run per adjacent pair on slices rebuilt
at the FULL acceptance quadrature grid (N_POINTS — the certificate refuses
mismatched grids, and certifying at the acceptance grid closes the
optimizer-vs-exit-gate resolution mismatch; cf. the appendix's "the final
certificate is rerun on the publication grid"). In practice the active
ranks are few: adjacent smooth quantile curves cross only a few times
(eq. calgapderivative), so the loop terminates in a handful of rounds.

Seeding: the exchange enters AFTER the penalty+escalation repair
(volfit.calib.symmetric.repair_surface — round "1" of the book loop, the
empty active set), so the first refit here already carries the failing
certificates' minimizers. A pair whose certificate minimizer repeats to
within the dedupe tolerance makes no progress under more rows and is
recorded IRREDUCIBLE — genuinely inconsistent inputs, reported, never
silently flattened (the book's feasibility diagnostic lives in
volfit.calib.band_relaxation, opt-in).

Tail-order gate (V3.0 rider, ``tail_gate``): with the gate armed the
failing-pair predicate also requires the certificate's tolerance-aware tail
clause (``LedgerCertificate.tail_certified`` — eq. tailscalecalendar,
Papers/book/chapters/02_lqd/07_calendar.tex "These inequalities are imposed
in the endpoint chart"). Its repair path is the lambda_+- seam rows every
exchange interface already carries: a tail-only failure at common alpha
escalates THAT pair's interface weight x TAIL_ESCALATION per round (capped
at TAIL_ESCALATION_CAP) so the soft rows tighten, while a pair whose tail
clause is decided by unequal exponents (``tail_irreducible``) is marked
irreducible at once — no round can move an exponent. ``tail_gate=False``
(the default) is byte-identical to the pre-rider driver.

Import discipline: pool-worker importable — depends only on volfit.calib /
volfit.models / volfit.core (see volfit.calib.fit_task).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from volfit.calib.calendar_certificate import LedgerCertificate, ledger_certificate
from volfit.calib.symmetric import (
    ESCALATION_FACTOR,
    IFACE_BASE_WEIGHT,
    MAX_ESCALATIONS,
    Interface,
    SliceSpec,
    _components,
    _spec_params,
    build_interface,
    joint_refit,
)
from volfit.models.lqd.quadrature import build_slice

#: Full-line certificate tolerance the exchange converges to — MIRROR of
#: volfit.api.quality._CAL_TOL (the acceptance/publish gate; calib modules
#: may not import volfit.api, so the constant is mirrored with this note).
_CAL_TOL = 1e-6

#: Book: "in practice the active ranks are few" — adjacent smooth quantile
#: curves cross only a few times, so a violating pair certifies within a few
#: exchanged ranks; 8 rounds is generous headroom before declaring the pair
#: irreducible and returning the best iterate.
MAX_EXCHANGE_ROUNDS = 8

#: Per-rank ledger row weight. Scale anchor: the escalated interface weight
#: IFACE_BASE_WEIGHT * ESCALATION_FACTOR**MAX_ESCALATIONS (= 1e3) times one
#: more escalation step, because the interface hinge rows also carry a
#: ~1/vega normalizer (>> 1 in the wings) that the raw ledger rows do not —
#: this lands on the same 1e6 scale as the in-slice full-grid ledger floor's
#: ``calendar_weight`` default (models.lqd.calibrate), which reliably pins
#: ledger hinges below the certificate tolerance. Tuned on the rigged
#: out-of-support dip fixture (tests/test_symmetric_exchange.py): the
#: exchange clears it to certified(_CAL_TOL) in <= 2 rounds at this weight.
EXCHANGE_W = IFACE_BASE_WEIGHT * ESCALATION_FACTOR ** (MAX_ESCALATIONS + 3)

#: Rank dedupe tolerance: a certificate minimizer that returns within this
#: distance of an already-active rank is the SAME turning point (the full
#: acceptance grid step is 1e-2), so re-adding it cannot make progress —
#: the pair is recorded irreducible instead of looping.
Z_DEDUPE = 1e-3

#: Tail-order gate repair: per-round multiplier on a tail-failing pair's
#: interface weight (its lambda_+- seam rows tighten with it) and the cap on
#: the cumulative boost — mirrors the screen phase's ESCALATION_FACTOR with
#: one more step of headroom (10^4 = MAX_ESCALATIONS + 1 steps).
TAIL_ESCALATION = ESCALATION_FACTOR
TAIL_ESCALATION_CAP = ESCALATION_FACTOR ** (MAX_ESCALATIONS + 1)


def pair_ok(cert: LedgerCertificate, tail_gate: bool = False) -> bool:
    """The exchange's per-pair acceptance predicate: the ledger gap clause at
    the acceptance tolerance, plus the tolerance-aware tail clause when the
    tail-order gate is armed (``tail_gate=False`` = the Phase-0 predicate)."""
    return cert.certified(_CAL_TOL) and (not tail_gate or cert.tail_certified())


@dataclass(frozen=True)
class ExchangeResult:
    """Outcome of the active-set exchange over one violation component.

    ``thetas`` is the best iterate (the converged one when ``converged``);
    ``certificates`` are its full-grid per-pair certificates; ``rounds``
    counts the joint refits performed (0 = the input stack already
    certified — the exchange never entered); ``active_ranks`` are the
    exchanged ranks per adjacent pair; ``irreducible`` lists pair indices
    whose certificate minimizer repeated (no progress possible — the caller
    decides, and publish stays blocked by the certificate downstream).
    """

    thetas: list[np.ndarray]
    certificates: list[LedgerCertificate]
    converged: bool
    rounds: int
    active_ranks: list[np.ndarray]
    irreducible: tuple[int, ...]


def _full_grid_certificates(
    specs: list[SliceSpec], thetas: list[np.ndarray]
) -> list[LedgerCertificate]:
    """Per-adjacent-pair certificates of a theta ladder at the acceptance
    grid — every slice rebuilt through the same ``build_slice`` default
    (N_POINTS) path ``result_from_theta`` / calibrate_slice use, so the
    certified object IS the one quality/export will consume."""
    slices = [
        build_slice(_spec_params(np.asarray(t, dtype=float), s.fit_kwargs))
        for t, s in zip(thetas, specs)
    ]
    return [
        ledger_certificate(slices[j], slices[j + 1])
        for j in range(len(slices) - 1)
    ]


def _worst_gap(certs: list[LedgerCertificate]) -> float:
    return min((c.min_gap for c in certs), default=0.0)


def _rank_arrays(active: list[list[float]]) -> list[np.ndarray]:
    return [np.array(sorted(a), dtype=float) for a in active]


def _score(certs: list[LedgerCertificate], tail_gate: bool) -> tuple[float, float]:
    """Best-iterate ordering key. Gate off: the worst ledger gap alone (the
    Phase-0 semantics — the leading key is a constant, so the comparison is
    byte-identical to the historical one). Gate on: the worst tail deficit
    (capped at 0 — an ordered tail earns nothing extra) ranks first, then
    the worst ledger gap."""
    worst = _worst_gap(certs)
    if not tail_gate:
        return (0.0, worst)
    deficit = min((c.tail_gap_min for c in certs), default=0.0)
    return (min(deficit, 0.0), worst)


def _boosted(
    ifaces: list[Interface | None], boost: list[float]
) -> list[Interface | None]:
    """Interfaces with the tail-gate escalation applied (the interface weight
    scales every row of that pair: hinge grid, seam and lambda_+- slope
    rows). A unit boost returns the caller's very objects — byte-identity."""
    return [
        f if (f is None or b == 1.0) else dataclasses.replace(f, weight=f.weight * b)
        for f, b in zip(ifaces, boost)
    ]


def exchange_refit(
    specs: list[SliceSpec],
    thetas0: list[np.ndarray],
    ifaces: list[Interface | None],
    iface_weight: float,
    tail_gate: bool = False,
) -> ExchangeResult:
    """Run the book's exchange loop on one component until it certifies.

    ``specs``/``thetas0``/``ifaces`` are exactly ``joint_refit``'s inputs
    (the penalty rows stay as the smooth in-loop screen at ``iface_weight``);
    the certificate is checked FIRST, so an already-certified stack returns
    round 0 with its thetas untouched (idempotence). Non-convergence after
    MAX_EXCHANGE_ROUNDS (or an irreducible minimizer on every failing pair)
    returns the best iterate by worst ledger gap plus its failing
    certificates — the caller decides; publish remains blocked downstream.

    ``tail_gate`` (V3.0 rider) adds the certificate's tolerance-aware tail
    clause to the acceptance predicate (``pair_ok``). A pair failing ONLY
    that clause at common alpha has its interface weight escalated
    x TAIL_ESCALATION per round (cap TAIL_ESCALATION_CAP) so its lambda_+-
    seam rows tighten; a pair whose tail clause is decided by unequal
    exponents (``tail_irreducible``), or that has no interface to tighten,
    or that is already at the cap, is marked irreducible at once. Off (the
    default) the driver is byte-identical to the pre-rider one.
    """
    m = len(specs)
    thetas = [np.asarray(t, dtype=float).copy() for t in thetas0]
    certs = _full_grid_certificates(specs, thetas)
    active: list[list[float]] = [[] for _ in range(m - 1)]
    boost = [1.0] * (m - 1)  # tail-gate interface escalation per pair
    irreducible: set[int] = set()
    best = (thetas, certs)
    rounds = 0

    while rounds < MAX_EXCHANGE_ROUNDS:
        failing = [j for j, c in enumerate(certs) if not pair_ok(c, tail_gate)]
        if not failing:
            return ExchangeResult(
                thetas=thetas, certificates=certs, converged=True,
                rounds=rounds, active_ranks=_rank_arrays(active),
                irreducible=tuple(sorted(irreducible)),
            )
        # Exchange step: each failing pair's certificate minimizer enters its
        # active set ("active[worst.pair].add(worst.rank)"); a repeat within
        # Z_DEDUPE marks the pair irreducible instead of re-adding forever.
        # Gated tail-only failures escalate the pair's interface instead.
        progressed = False
        for j in failing:
            if j in irreducible:
                continue
            if tail_gate and certs[j].tail_irreducible:
                irreducible.add(j)  # unequal exponents: no row moves it
                continue
            if not certs[j].certified(_CAL_TOL):
                z_star = float(certs[j].z_star)
                if any(abs(z_star - z) <= Z_DEDUPE for z in active[j]):
                    irreducible.add(j)
                    continue
                active[j].append(z_star)
                progressed = True
            elif tail_gate:  # tail-only failure at common alpha
                if ifaces[j] is None or boost[j] >= TAIL_ESCALATION_CAP:
                    irreducible.add(j)
                    continue
                boost[j] = min(boost[j] * TAIL_ESCALATION, TAIL_ESCALATION_CAP)
                progressed = True
        if not progressed:
            break
        rounds += 1
        thetas, _ok = joint_refit(
            specs, thetas, _boosted(ifaces, boost), iface_weight,
            active_ranks=_rank_arrays(active), rank_weight=EXCHANGE_W,
        )
        certs = _full_grid_certificates(specs, thetas)
        if _score(certs, tail_gate) > _score(best[1], tail_gate):
            best = (thetas, certs)

    thetas, certs = best
    return ExchangeResult(
        thetas=thetas, certificates=certs,
        converged=all(pair_ok(c, tail_gate) for c in certs),
        rounds=rounds, active_ranks=_rank_arrays(active),
        irreducible=tuple(sorted(irreducible)),
    )


def certify_ladder(
    specs: list[SliceSpec], thetas: list[np.ndarray]
) -> list[LedgerCertificate]:
    """Full-grid certificates for every adjacent pair of a whole ladder."""
    return _full_grid_certificates(specs, thetas)


def exchange_ladder(
    specs: list[SliceSpec],
    thetas: list[np.ndarray],
    tail_gate: bool = False,
) -> tuple[list[np.ndarray], list[bool], list[LedgerCertificate]]:
    """Certify a repaired ladder; exchange only its FAILING components.

    The phase-B entry point (volfit.api.surface_symmetric): after the
    penalty+escalation repair, every adjacent pair is certified at the
    acceptance grid; contiguous failing pairs form components (the calendar
    coupling is a chain) solved by ``exchange_refit`` with freshly built
    interfaces at the BASE weight (escalation already had its turn — the
    hard rank rows carry the enforcement now). A fully certified ladder
    returns its thetas untouched: byte-identity of the clean path.

    The exchange interfaces are ALWAYS built with the tail contract armed,
    regardless of the screen-phase extrapolation toggle: the wing-slope rows
    are eq. tailscalecalendar's lambda_+- monotonicity — which the book
    imposes in the same constrained solve ("these inequalities are imposed
    in the endpoint chart") and without which an asymptotic tail-order
    violation cannot be repaired by finitely many exchanged ranks (the rank
    chase marches down the tail instead of reordering it). ``tail_gate``
    (OptionsSettings.ledgerTailOrderGate) makes the tail clause part of the
    failing-pair predicate — see ``exchange_refit``.
    Returns ``(thetas, exchanged_mask, certificates)``.
    """
    n = len(specs)
    certs = certify_ladder(specs, thetas)
    failing = [not pair_ok(c, tail_gate) for c in certs]
    if not any(failing):
        return list(thetas), [False] * n, certs
    out = [np.asarray(t, dtype=float) for t in thetas]
    touched = [False] * n
    for lo, hi in _components(failing):
        comp_ifaces = [
            build_interface(specs[i], specs[i + 1], tail_contract=True)
            for i in range(lo, hi)
        ]
        res = exchange_refit(
            specs[lo: hi + 1], out[lo: hi + 1], comp_ifaces, IFACE_BASE_WEIGHT,
            tail_gate=tail_gate,
        )
        for i, idx in enumerate(range(lo, hi + 1)):
            out[idx] = res.thetas[i]
            touched[idx] = True
        for i, cert in enumerate(res.certificates):
            certs[lo + i] = cert
    return out, touched, certs
