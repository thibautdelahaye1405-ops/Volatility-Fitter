"""Data-derived observation / baseline precision for the extrapolation graph
(plan Phase 4, Amendment F).

The graph is Bayesian, so precision is part of the product truth, not a constant:
a dense, tight, fresh, well-fitted chain must enter the solver with materially
more observation precision than a sparse, wide, stale one. Phase 4 plumbs the
sources and exposes every factor in diagnostics BEFORE any autotune, so tuning
does not chase a hard-coded artifact.

Three precision concepts are kept separate (plan Q5):
  * **observation precision** (lit nodes) — confidence in today's calibrated
    innovation: 1/rms² scaled by near-ATM quote density, bid-ask width / haircut
    mode, and as-of freshness;
  * **baseline/prior precision** (all nodes) — confidence in the transported
    prior level: a provenance tier scaled by prior age and transport distance;
  * **edge precision/conductance** — left as the graph conductance for v1
    (Phase 6 adds beta; a learned edge confidence is a later follow-up).

All formulas are conservative and bounded by explicit per-handle FLOORS and CAPS
(mirroring the ``MAX_INV_VEGA_RATIO`` pattern in ``calib/prior.py``) so a single
great fit cannot dominate and a degenerate input cannot zero a precision. The
per-handle confidence makes the ATM level the most precise coordinate and the
curvature the least — at the design point (active prior, dense/tight/fresh) the
result reproduces the legacy ``GRAPH_PRECISION = [1e6, 1e6, 1e4]`` regime exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Relative per-handle confidence (atm_vol, skew, curvature). Anchored so an
#: active/dense/tight/fresh node lands on the legacy [1e6, 1e6, 1e4] regime.
HANDLE_CONFIDENCE = np.array([1.0, 1.0, 0.01])

#: Observation-precision per-handle floor / cap.
OBS_PRECISION_FLOOR = np.array([1.0e2, 1.0e2, 1.0])
OBS_PRECISION_CAP = np.array([1.0e7, 1.0e7, 1.0e5])

#: Baseline-precision per-handle floor / cap.
BASE_PRECISION_FLOOR = np.array([1.0e2, 1.0e2, 1.0])
BASE_PRECISION_CAP = np.array([2.0e6, 2.0e6, 2.0e4])

#: 1/rms² base: a 1bp-vol fit is excellent but not infinitely precise.
RMS_FLOOR = 1.0e-4  # 1 vol bp

#: Near-ATM quote count giving full density credit; fewer scales precision down.
REF_ATM_QUOTES = 8.0
MIN_DENSITY_FACTOR = 0.15

#: Relative bid-ask spread (band width / ATM vol) at which precision halves.
SPREAD_HALF = 0.05

#: As-of / prior freshness half-lives (days).
OBS_FRESHNESS_HALFLIFE = 3.0
PRIOR_AGE_HALFLIFE = 30.0

#: Transport-distance scale: |h = log(F_now/F_prior)| of this size halves-ish the
#: prior precision (further transport ⇒ less trustworthy baseline).
TRANSPORT_SCALE = 0.10

#: Provenance tier base precision (atm-vol units; per-handle via HANDLE_CONFIDENCE).
SOURCE_BASE = {
    "active_transported": 1.0e6,
    "nearest_expiry_transported": 2.5e5,
    "today_bootstrap": 5.0e4,
    "flat_atm": 1.0e4,
    "none": 1.0e4,
}


@dataclass(frozen=True)
class PrecisionBreakdown:
    """A resolved per-handle precision plus the scalar factors that produced it
    (surfaced in node diagnostics so every result is explainable)."""

    precision: np.ndarray  # (3,)
    factors: dict[str, float] = field(default_factory=dict)


def quote_density_factor(n_atm_quotes: float) -> float:
    """More near-ATM quotes ⇒ higher precision, saturating at REF_ATM_QUOTES."""
    return float(np.clip(n_atm_quotes / REF_ATM_QUOTES, MIN_DENSITY_FACTOR, 1.0))


def spread_factor(rel_spread: float) -> float:
    """Wider bid-ask (relative to ATM vol) ⇒ lower precision, in (0, 1]."""
    return float(1.0 / (1.0 + max(rel_spread, 0.0) / SPREAD_HALF))


def freshness_factor(age_days: float, half_life: float = OBS_FRESHNESS_HALFLIFE) -> float:
    """Exponential decay with age (an as-of mismatch / stale quote)."""
    return float(0.5 ** (max(age_days, 0.0) / half_life))


def transport_factor(transport_distance: float) -> float:
    """Further forward transport ⇒ less precise baseline, in (0, 1]."""
    return float(np.exp(-abs(transport_distance) / TRANSPORT_SCALE))


def observation_precision(
    rms_vol: float,
    n_atm_quotes: float,
    rel_spread: float,
    age_days: float = 0.0,
) -> PrecisionBreakdown:
    """Lit-node observation precision from fit quality + data coverage (plan Q5)."""
    base = 1.0 / max(float(rms_vol), RMS_FLOOR) ** 2
    qf = quote_density_factor(n_atm_quotes)
    sf = spread_factor(rel_spread)
    ff = freshness_factor(age_days)
    precision = np.clip(
        base * qf * sf * ff * HANDLE_CONFIDENCE, OBS_PRECISION_FLOOR, OBS_PRECISION_CAP
    )
    return PrecisionBreakdown(
        precision=precision,
        factors={
            "rmsBase": float(base),
            "quoteDensity": qf,
            "spread": sf,
            "freshness": ff,
        },
    )


def baseline_precision(
    source: str,
    age_days: float = 0.0,
    transport_distance: float = 0.0,
) -> PrecisionBreakdown:
    """All-node baseline precision from provenance tier + age + transport (plan Q5).

    At the design point (active_transported, age 0, no transport) this returns the
    legacy ``[1e6, 1e6, 1e4]`` so the Phase-2 provenance tiers are reproduced."""
    base = SOURCE_BASE.get(source, SOURCE_BASE["none"])
    af = freshness_factor(age_days, half_life=PRIOR_AGE_HALFLIFE)
    tf = transport_factor(transport_distance)
    precision = np.clip(
        base * af * tf * HANDLE_CONFIDENCE, BASE_PRECISION_FLOOR, BASE_PRECISION_CAP
    )
    return PrecisionBreakdown(
        precision=precision,
        factors={"sourceBase": float(base), "priorAge": af, "transport": tf},
    )
