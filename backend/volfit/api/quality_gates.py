"""Quality-row helpers for the two V3.0 riders (shared by api.quality and
api.export): the tail-order GATE reading of the full-line certificate and
the quote-band relaxation hint.

Tail-order gate (OptionsSettings.ledgerTailOrderGate): the certificate's
limiting-order clause — eq. tailscalecalendar, book ch. 2 (07_calendar.tex:
"With common tail exponents, eventual calendar order requires
lambda_{-,j+1} >= lambda_{-,j}, lambda_{+,j+1} >= lambda_{+,j} ... These
inequalities are imposed in the endpoint chart. If exponents vary by
expiry, the farther law cannot have a lighter asymptotic tail") — read
through ``LedgerCertificate.tail_certified`` (tolerance-aware) rather than
the raw tie-band clause, with the failing side(s) named in desk language.

Band relaxation (OptionsSettings.bandRelaxationDiagnostic): the recorded
``calib.band_relaxation.BandRelaxation`` of an uncertified pair, rendered
as the hint the book asks for ("the smallest quote-band relaxation needed
for feasibility") next to the calendar issue that carries it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from volfit.calib.band_relaxation import DELTA_MAX
from volfit.calib.calendar_certificate import (
    TAIL_ORDER_TOL,
    LedgerCertificate,
    ledger_certificate,
)


@dataclass(frozen=True)
class TailClause:
    """The wire-ready reading of one certificate's tail clause: per-side
    signed gaps (None on a side decided by unequal exponents — the +-inf
    sentinel is not JSON), the tolerance-aware verdict, irreducibility and
    the names of the failing sides."""

    gap_left: float | None
    gap_right: float | None
    certified: bool
    irreducible: bool
    sides: tuple[str, ...]

    @property
    def gap_min(self) -> float | None:
        gaps = [g for g in (self.gap_left, self.gap_right) if g is not None]
        return min(gaps) if gaps else None


def _finite_or_none(x: float) -> float | None:
    return float(x) if math.isfinite(x) else None


def tail_clause(cert: LedgerCertificate) -> TailClause:
    """Read the tail clause off a certificate (sides fail at TAIL_ORDER_TOL)."""
    sides = tuple(
        name for name, gap in (("left", cert.tail_gap_left), ("right", cert.tail_gap_right))
        if gap < -TAIL_ORDER_TOL
    )
    return TailClause(
        gap_left=_finite_or_none(cert.tail_gap_left),
        gap_right=_finite_or_none(cert.tail_gap_right),
        certified=bool(cert.tail_certified()),
        irreducible=bool(cert.tail_irreducible),
        sides=sides,
    )


def tail_side_text(
    gap_left: float | None, gap_right: float | None, irreducible: bool
) -> str:
    """'left gap -1.2e-05, right gap ...' from wire fields (a side with a
    None gap and an irreducible flag is the unequal-exponent reversal)."""
    parts = [
        f"{name} gap {gap:.1e}"
        for name, gap in (("left", gap_left), ("right", gap_right))
        if gap is not None and gap < -TAIL_ORDER_TOL
    ]
    if irreducible:
        parts.append("unequal tail exponents, irreducible")
    return ", ".join(parts) if parts else "tail clause failed"


def tail_issue(clause: TailClause) -> str:
    """The Quality issue line of a gated tail-clause failure."""
    sides = "/".join(clause.sides) if clause.sides else "unequal exponents"
    text = f"tail order: far-slice tail decays faster than the near one ({sides})"
    if clause.irreducible:
        text += " - unequal tail exponents, irreducible"
    return text


def relaxation_hint(
    delta_vol: float | None, feasible: bool | None, delta_max: float = DELTA_MAX
) -> str:
    """The band-relaxation hint appended to a calendar issue / blocker: empty
    when no diagnostic was recorded for the pair."""
    if feasible is None:
        return ""
    if feasible and delta_vol is not None:
        return f" (certifies with +-{delta_vol * 100:.2f} vol-pt band widening)"
    return f" (infeasible even at +-{delta_max * 100:.0f} vol-pt widening)"


@dataclass(frozen=True)
class CertificateFields:
    """The quality row's certificate-derived fields (api.quality._node_row
    unpacks these): the exact full-line ledger certificate vs the previous
    fitted expiry, its tail clause + gate, and the recorded band-relaxation
    diagnostic with the hint that rides the calendar issue."""

    ledger_gap: float | None
    ledger_z: float | None
    ledger_k: float | None
    ledger_tail_ok: bool
    ledger_certified: bool
    tail_gate: bool
    tail: TailClause
    relax_vol: float | None
    relax_ok: bool | None
    relax_hint: str


def certificate_fields(
    state, ticker: str, iso: str, fit_mode: str, record, prev_slice, cal_tol: float
) -> CertificateFields:
    """Exact full-line calendar certificate (book ch. 2 "A complete calendar
    certificate"; tails+calendar arc Phase 0) on the LQD backbone pair: the
    ACCEPTANCE authority. The windowed screen (api.quality) stays as the
    support-confined desk diagnostic; the certificate additionally proves
    (or refutes) ledger order between and beyond its samples, tails
    included. Its limiting-tail-order clause is advisory by default; the
    V3.0 rider's ledgerTailOrderGate promotes the tolerance-aware reading
    (``tail_clause``) to an issue / readiness / publish gate. The quote-band
    relaxation diagnostic (V3.0 rider) is read off the last surface pass's
    record for pairs the exchange could not certify; advisory.
    """
    ledger_gap = ledger_z = ledger_k = None
    ledger_tail_ok = True
    ledger_certified = True
    tail_gate = bool(state.options().ledgerTailOrderGate)
    tail = TailClause(None, None, True, False, ())
    if prev_slice is not None:
        try:
            cert = ledger_certificate(prev_slice, record.result.slice)
            ledger_gap, ledger_z, ledger_k = cert.min_gap, cert.z_star, cert.k_star
            ledger_tail_ok = cert.tail_order_ok
            ledger_certified = cert.certified(cal_tol)
            tail = tail_clause(cert)
        except Exception:  # the certificate must never break a status read
            pass
    relax = getattr(state, "_band_relaxation", {}).get((ticker, iso, fit_mode))
    relax_vol = relax.delta_vol if relax is not None else None
    relax_ok = relax.feasible if relax is not None else None
    relax_hint = (
        "" if relax is None else relaxation_hint(relax_vol, relax_ok, relax.delta_max)
    )
    return CertificateFields(
        ledger_gap=ledger_gap, ledger_z=ledger_z, ledger_k=ledger_k,
        ledger_tail_ok=ledger_tail_ok, ledger_certified=ledger_certified,
        tail_gate=tail_gate, tail=tail,
        relax_vol=relax_vol, relax_ok=relax_ok, relax_hint=relax_hint,
    )


def calendar_issues(cal_ok: bool, cf: CertificateFields) -> list[str]:
    """The calendar issue lines of one quality row: the sampled screen, else
    the exact certificate (one line, never two for the same defect), plus
    the gated tail clause; the band-relaxation hint rides the first."""
    issues: list[str] = []
    if not cal_ok:
        issues.append("calendar arb vs previous expiry")
    elif not cf.ledger_certified:
        # The sampled screen passed but the exact certificate refutes full-
        # line order (a between-node or out-of-support dip).
        issues.append(
            f"calendar certificate: min ledger gap {cf.ledger_gap * 1e4:.1f}bp"
            f" at k {cf.ledger_k:+.2f}"
        )
    if cf.tail_gate and not cf.tail.certified:
        issues.append(tail_issue(cf.tail))
    if issues and cf.relax_hint:
        issues[0] += cf.relax_hint  # the book's diagnostic rides the calendar issue
    return issues
