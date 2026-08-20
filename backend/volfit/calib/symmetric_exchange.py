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
silently flattened (the book's feasibility diagnostic is a recorded rider).

Import discipline: pool-worker importable — depends only on volfit.calib /
volfit.models / volfit.core (see volfit.calib.fit_task).
"""

from __future__ import annotations

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


def exchange_refit(
    specs: list[SliceSpec],
    thetas0: list[np.ndarray],
    ifaces: list[Interface | None],
    iface_weight: float,
) -> ExchangeResult:
    """Run the book's exchange loop on one component until it certifies.

    ``specs``/``thetas0``/``ifaces`` are exactly ``joint_refit``'s inputs
    (the penalty rows stay as the smooth in-loop screen at ``iface_weight``);
    the certificate is checked FIRST, so an already-certified stack returns
    round 0 with its thetas untouched (idempotence). Non-convergence after
    MAX_EXCHANGE_ROUNDS (or an irreducible minimizer on every failing pair)
    returns the best iterate by worst ledger gap plus its failing
    certificates — the caller decides; publish remains blocked downstream.
    """
    m = len(specs)
    thetas = [np.asarray(t, dtype=float).copy() for t in thetas0]
    certs = _full_grid_certificates(specs, thetas)
    active: list[list[float]] = [[] for _ in range(m - 1)]
    irreducible: set[int] = set()
    best = (thetas, certs)
    rounds = 0

    while rounds < MAX_EXCHANGE_ROUNDS:
        failing = [j for j, c in enumerate(certs) if not c.certified(_CAL_TOL)]
        if not failing:
            return ExchangeResult(
                thetas=thetas, certificates=certs, converged=True,
                rounds=rounds, active_ranks=_rank_arrays(active),
                irreducible=tuple(sorted(irreducible)),
            )
        # Exchange step: each failing pair's certificate minimizer enters its
        # active set ("active[worst.pair].add(worst.rank)"); a repeat within
        # Z_DEDUPE marks the pair irreducible instead of re-adding forever.
        progressed = False
        for j in failing:
            if j in irreducible:
                continue
            z_star = float(certs[j].z_star)
            if any(abs(z_star - z) <= Z_DEDUPE for z in active[j]):
                irreducible.add(j)
                continue
            active[j].append(z_star)
            progressed = True
        if not progressed:
            break
        rounds += 1
        thetas, _ok = joint_refit(
            specs, thetas, ifaces, iface_weight,
            active_ranks=_rank_arrays(active), rank_weight=EXCHANGE_W,
        )
        certs = _full_grid_certificates(specs, thetas)
        if _worst_gap(certs) > _worst_gap(best[1]):
            best = (thetas, certs)

    thetas, certs = best
    return ExchangeResult(
        thetas=thetas, certificates=certs,
        converged=all(c.certified(_CAL_TOL) for c in certs),
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
    chase marches down the tail instead of reordering it).
    Returns ``(thetas, exchanged_mask, certificates)``.
    """
    n = len(specs)
    certs = certify_ladder(specs, thetas)
    failing = [not c.certified(_CAL_TOL) for c in certs]
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
            specs[lo: hi + 1], out[lo: hi + 1], comp_ifaces, IFACE_BASE_WEIGHT
        )
        for i, idx in enumerate(range(lo, hi + 1)):
            out[idx] = res.thetas[i]
            touched[idx] = True
        for i, cert in enumerate(res.certificates):
            certs[lo + i] = cert
    return out, touched, certs
