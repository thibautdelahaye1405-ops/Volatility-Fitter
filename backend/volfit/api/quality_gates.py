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
from volfit.calib.calendar_certificate import TAIL_ORDER_TOL, LedgerCertificate


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
