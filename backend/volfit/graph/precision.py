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

# The model-agnostic scalar factors + half-lives live in the shared precision
# vocabulary (volfit.calib.precision, design note §9) so the operator/factor prior
# builders and the graph baseline gate on the SAME quantities. Re-exported here so
# the graph-specific helpers below (and any caller of gprec.spread_factor) keep
# their import surface; values are byte-identical to the originals.
from volfit.calib.precision import (  # noqa: F401  (re-export)
    OBS_FRESHNESS_HALFLIFE,
    PRIOR_AGE_HALFLIFE,
    RMS_FLOOR,
    TRANSPORT_SCALE,
    freshness_factor,
    quote_density_factor,
    spread_factor,
    transport_factor,
)

#: Relative per-handle confidence (atm_vol, skew, curvature). Anchored so an
#: active/dense/tight/fresh node lands on the legacy [1e6, 1e6, 1e4] regime.
HANDLE_CONFIDENCE = np.array([1.0, 1.0, 0.01])

#: Observation-precision per-handle floor / cap.
OBS_PRECISION_FLOOR = np.array([1.0e2, 1.0e2, 1.0])
OBS_PRECISION_CAP = np.array([1.0e7, 1.0e7, 1.0e5])

#: Baseline-precision per-handle floor / cap.
BASE_PRECISION_FLOOR = np.array([1.0e2, 1.0e2, 1.0])
BASE_PRECISION_CAP = np.array([2.0e6, 2.0e6, 2.0e4])

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


#: Baseline-precision multiplier for DARK nodes (graph-LOO follow-up): a dark
#: node's transported prior is a TARGET to be moved by propagated signal, not
#: a lit prior corroborated by today's quotes — at full tier precision it
#: pinned the posterior (measured: a 96 bp SPX innovation moved a dark AAPL
#: node 0.01 bp). 0.25 mirrors the nearest-expiry tier scale; validate on the
#: 25-asset capture before tuning further.
DARK_BASE_SCALE = 0.25


def baseline_precision(
    source: str,
    age_days: float = 0.0,
    transport_distance: float = 0.0,
    dark: bool = False,
) -> PrecisionBreakdown:
    """All-node baseline precision from provenance tier + age + transport (plan Q5).

    At the design point (active_transported, age 0, no transport, lit) this
    returns the legacy ``[1e6, 1e6, 1e4]`` so the Phase-2 provenance tiers are
    reproduced; ``dark=True`` scales the tier by ``DARK_BASE_SCALE`` so a dark
    target does not pin the posterior against its lit neighbours."""
    base = SOURCE_BASE.get(source, SOURCE_BASE["none"])
    df = DARK_BASE_SCALE if dark else 1.0
    af = freshness_factor(age_days, half_life=PRIOR_AGE_HALFLIFE)
    tf = transport_factor(transport_distance)
    precision = np.clip(
        base * df * af * tf * HANDLE_CONFIDENCE, BASE_PRECISION_FLOOR, BASE_PRECISION_CAP
    )
    return PrecisionBreakdown(
        precision=precision,
        factors={"sourceBase": float(base), "priorAge": af, "transport": tf, "dark": df},
    )
