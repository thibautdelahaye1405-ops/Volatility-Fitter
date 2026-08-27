"""Publish gate of the surface export (split out of volfit.api.export).

The R2 item-10 exit gate: a publish set carrying UNRESOLVED arbitrage
inconsistency must FAIL HARD (``PublishBlockedError``, HTTP 409 at the
router) rather than stamp a warning into metadata a downstream consumer may
never read. ``_node_blockers`` lists one node's hard blockers from its
quality row + exported curve; ``_projection_calendar_audit`` proves on
every artifact that the publish-time wing projection introduced no calendar
crossing. ``volfit.api.export`` re-exports all three (plus the audit
tolerance) so ``export.PublishBlockedError`` / ``export._node_blockers``
keep resolving for the router and the tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from volfit.api.quality_gates import relaxation_hint, tail_side_text
from volfit.api.schemas_quality import QualityNode

if TYPE_CHECKING:  # type-only: export imports this module
    from volfit.api.export import ExportNode


class PublishBlockedError(ValueError):
    """The publish set carries UNRESOLVED arbitrage inconsistency (R2 item 10
    exit gate): publishing must FAIL HARD, not stamp a warning into metadata a
    downstream consumer may never read. ``blockers`` lists every offending
    node with its reason; the router maps this to HTTP 409."""

    def __init__(self, blockers: list[str]):
        self.blockers = list(blockers)
        super().__init__(
            "publish blocked: " + "; ".join(self.blockers)
            + " (pass allow_dirty=true to export a draft artifact anyway)"
        )


def _node_blockers(ticker: str, row: QualityNode, node: ExportNode) -> list[str]:
    """The HARD publish blockers of one exported node: calendar inconsistency
    beyond tolerance (quality's two-curve check), a core calendar conflict the
    wing projection must not repair, an unpriceable curve region (w <= 0 or
    non-finite = below intrinsic), and — committee R2, the acceptance rule —
    an UNCERTIFIED belly (negative Durrleman g inside the traded range, which
    no wing projection can repair), plus — under the as-of mismatch gate — a
    chain served off the requested as-of session. An uncertified slice cannot
    become a mark: repair it at the fit (enforcement / refit) or it is
    rejected here; ``allow_dirty`` still exports a DRAFT artifact with the
    defect stamped."""
    where = f"{ticker} {row.expiry}"
    out: list[str] = []
    # The exact full-line certificate is the calendar authority (tails+
    # calendar arc Phase 0); the sampled message backstops only the
    # defensive path where the certificate could not run. The band
    # relaxation hint (V3.0 rider) rides the first calendar blocker.
    hint = relaxation_hint(row.bandRelaxationVol, row.bandRelaxationFeasible)
    cal: list[str] = []
    if not row.ledgerCertified and row.ledgerGapMin is not None:
        cal.append(
            f"{where}: calendar certificate failed"
            f" (min ledger gap {row.ledgerGapMin * 1e4:.1f}bp)"
        )
    elif not row.calendarOk:
        cal.append(f"{where}: calendar inconsistency ({row.calendarViolation * 1e4:.0f}bp)")
    # Tail-order gate (V3.0 rider): blocks only when the gate applied to the
    # row (advisory otherwise — the Phase-0 policy).
    if row.ledgerTailGated and not row.ledgerTailCertified:
        cal.append(
            f"{where}: tail order failed ("
            + tail_side_text(
                row.ledgerTailGapLeft, row.ledgerTailGapRight, row.ledgerTailIrreducible
            )
            + ")"
        )
    if cal and hint:
        cal[0] += hint
    out.extend(cal)
    if not node.wingsClean:
        out.append(f"{where}: core calendar conflict at the traded edge")
    if not row.butterflyCertified:
        min_g = row.bellyMinG if row.bellyMinG is not None else float("nan")
        out.append(f"{where}: uncertified belly butterfly (min g {min_g:.4f})")
    # As-of mismatch gate (OptionsSettings.asOfMismatchGate): the serving
    # chain is not in the requested as-of session — a DATA blocker, only when
    # the gate applied to the row (advisory otherwise; the Nodes pane flags it).
    if row.asOfGated and row.asOfExact is False:
        out.append(f"{where}: as-of mismatch (chain stamped {row.effectiveAsOf})")
    w = np.array([p.w for p in node.curve])
    iv = np.array([p.iv for p in node.curve])
    if w.size and (not np.all(np.isfinite(w)) or not np.all(np.isfinite(iv)) or np.any(w <= 0.0)):
        out.append(f"{where}: unpriceable curve region (intrinsic)")
    return out


#: Tolerance for the post-projection calendar audit (vol bp) — matches the
#: extrapolated-region advisory tolerance; the projection floors each node on
#: the previous PUBLISHED curve, so the audit should read ~0 by construction.
_PROJECTION_CAL_TOL_BP = 1.0


def _projection_calendar_audit(
    published: list[tuple[np.ndarray, np.ndarray, float]],
) -> float:
    """Worst calendar crossing across adjacent PUBLISHED curves of one ticker
    (vol bp at the far expiry's maturity), answering the committee's audit
    question directly: can the wing projection introduce calendar crossings?
    The projection's floor construction makes this 0 by design — this audit
    PROVES it on every artifact rather than asserting it."""
    worst = 0.0
    for (k_near, w_near, _t_near), (k_far, w_far, t_far) in zip(published, published[1:]):
        lo = max(float(k_near.min()), float(k_far.min()))
        hi = min(float(k_near.max()), float(k_far.max()))
        if hi <= lo or t_far <= 0.0:
            continue
        sel = (k_far >= lo) & (k_far <= hi)
        if not sel.any():
            continue
        w_n = np.interp(k_far[sel], k_near, w_near)
        gap = (
            np.sqrt(np.maximum(w_n, 0.0) / t_far)
            - np.sqrt(np.maximum(w_far[sel], 0.0) / t_far)
        ) * 1e4
        gap = gap[np.isfinite(gap)]
        if gap.size:
            worst = max(worst, float(gap.max()))
    return worst
