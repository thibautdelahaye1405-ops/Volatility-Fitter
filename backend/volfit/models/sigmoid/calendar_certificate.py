"""Polished-dense calendar certificate for smooth w(k) slice pairs (V3.1 leg 4b).

Gatheral's surface condition: absence of calendar arbitrage between two
expiries is w_far(k) >= w_near(k) at every fixed log-moneyness. For the
Multi-Core Sigmoid family (and any closed-form w(k) overlay) the gap
w_far − w_near is a smooth function whose interior minima can be located to
solver tolerance, and whose FAR FIELD is decided in closed form by the
asymptotic Lee slope order (eq mcsbetak + lem zerowing: the kernels are
silent in the tails, so the gap is eventually monotone on each side whenever
the slopes differ).

The certificate therefore has three clauses:

  1. a dense scan (``_SCAN_POINTS`` over a wide range) of the gap;
  2. a scipy Brent polish of EVERY interior local minimum of the scan — each
     polished minimum is exact to tolerance on the smooth closed-form gap;
  3. the analytic wing-order clause: β_far >= β_near on both sides (up to
     ``_SLOPE_TOL``), which decides the far field the finite scan cannot
     reach — a lighter far wing means the gap eventually turns negative,
     failing the certificate regardless of the scanned minimum.

HONEST LABELING: this is a POLISHED-DENSE certificate — the interior minima
are found by sampling and refined, not isolated on a finite exhaustive
candidate set. It is NOT the sample-free exact object the LQD ledger
certificate is (volfit.calib.calendar_certificate: piecewise-cubic turning
points in closed form + analytic tail candidates). For smooth low-parameter
curves the practical gap between the two is the scan resolution, but the
epistemic class differs and the name says so. Advisory in v1: quality.py
reports it for sigmoid-displayed nodes without gating readiness/publish —
there is no MCS calendar REPAIR path yet, and a gate a fit cannot be asked
to satisfy would block publishes with no way out (the Phase-0 ledger
precedent).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize_scalar

from volfit.models.base import SmileModel
from volfit.models.diagnostics import numeric_lee_slopes

#: Dense-scan resolution over the certification range (the belly-certificate
#: density, dense enough that no smooth two-slice gap dip fits between nodes
#: without leaving a scan signature for the polish to refine).
_SCAN_POINTS = 801
#: Default certification half-width: ±_Z_SPAN "ATM standard deviations"
#: sqrt(w(0)) of the wider slice (for an MCS slice sqrt(w(0)) ≈ sigma_ref
#: sqrt(t), so this is a z-range), floored/capped to sane absolutes in k.
_Z_SPAN = 8.0
_HALF_MIN = 1.0
_HALF_MAX = 6.0
#: Wing-order tolerance on the asymptotic slope comparison (slope units).
_SLOPE_TOL = 1e-9


@dataclass(frozen=True)
class McsCalendarCertificate:
    """Outcome of the polished-dense calendar certificate for one pair.

    ``min_gap`` is the polished minimum of w_far(k) − w_near(k) over the
    certification range (total-variance units; < 0 = calendar arbitrage at
    ``k_star``). ``wing_order_ok`` is the analytic far-field clause: both
    asymptotic Lee slopes of the far slice at or above the near slice's
    (eq mcsbetak decides the tails the scan cannot reach). ``n_minima``
    counts the interior scan minima that were Brent-polished."""

    min_gap: float
    k_star: float
    wing_order_ok: bool
    n_minima: int
    k_lo: float
    k_hi: float

    def certified(self, tol: float = 0.0) -> bool:
        """Nonnegative gap to ``tol`` over the range AND far-field order —
        the two clauses that together cover the whole line for slope-ordered
        smooth pairs (interior by polish, tails by eq mcsbetak)."""
        return self.min_gap >= -tol and self.wing_order_ok


def _lee(slice_: SmileModel) -> tuple[float, float]:
    """Asymptotic (left, right) total-variance slopes: analytic when the model
    carries them (MultiCoreSiv.lee_slopes, V3.1 leg 1), numeric FD otherwise."""
    fn = getattr(slice_, "lee_slopes", None)
    if callable(fn):
        left, right = fn()
        return float(left), float(right)
    return numeric_lee_slopes(slice_)


def _default_range(near: SmileModel, far: SmileModel) -> tuple[float, float]:
    """Symmetric certification range from the wider slice's ATM sd scale."""
    sd = max(
        float(np.sqrt(max(float(near.implied_w(0.0)), 1e-8))),
        float(np.sqrt(max(float(far.implied_w(0.0)), 1e-8))),
    )
    half = float(np.clip(_Z_SPAN * sd, _HALF_MIN, _HALF_MAX))
    return -half, half


def mcs_calendar_certificate(
    near: SmileModel,
    far: SmileModel,
    k_lo: float | None = None,
    k_hi: float | None = None,
    near_lee: tuple[float, float] | None = None,
    far_lee: tuple[float, float] | None = None,
) -> McsCalendarCertificate:
    """Certify calendar order of an adjacent smooth-w(k) pair (see module
    docstring). ``near_lee``/``far_lee`` override the asymptotic slopes when
    the caller has them in closed form (the backtest's SVI arm passes
    b(1∓ρ)); by default they come from ``lee_slopes()`` / numeric FD."""
    if k_lo is None or k_hi is None:
        lo_d, hi_d = _default_range(near, far)
        k_lo = lo_d if k_lo is None else float(k_lo)
        k_hi = hi_d if k_hi is None else float(k_hi)

    def gap(k):
        k = np.asarray(k, dtype=float)
        g = np.asarray(far.implied_w(k), float) - np.asarray(near.implied_w(k), float)
        return np.where(np.isfinite(g), g, np.inf)  # overflow: no signal there

    # Clause 1: the dense scan.
    ks = np.linspace(k_lo, k_hi, _SCAN_POINTS)
    gs = gap(ks)
    j = int(np.argmin(gs))
    min_gap, k_star = float(gs[j]), float(ks[j])

    # Clause 2: Brent-polish every interior local minimum of the scan — each
    # is bracketed by its neighbours, so bounded Brent converges to the smooth
    # gap's true local minimum to solver tolerance.
    interior = np.flatnonzero((gs[1:-1] <= gs[:-2]) & (gs[1:-1] <= gs[2:])) + 1
    for i in interior:
        res = minimize_scalar(
            lambda x: float(gap(x)), bounds=(float(ks[i - 1]), float(ks[i + 1])),
            method="bounded", options={"xatol": 1e-12},
        )
        if np.isfinite(res.fun) and float(res.fun) < min_gap:
            min_gap, k_star = float(res.fun), float(res.x)

    # Clause 3: the analytic far field (eq mcsbetak) — slope order both sides.
    n_lee = _lee(near) if near_lee is None else (float(near_lee[0]), float(near_lee[1]))
    f_lee = _lee(far) if far_lee is None else (float(far_lee[0]), float(far_lee[1]))
    wing_ok = (
        f_lee[0] >= n_lee[0] - _SLOPE_TOL and f_lee[1] >= n_lee[1] - _SLOPE_TOL
    )

    return McsCalendarCertificate(
        min_gap=min_gap,
        k_star=k_star,
        wing_order_ok=bool(wing_ok),
        n_minima=int(interior.size),
        k_lo=float(k_lo),
        k_hi=float(k_hi),
    )
