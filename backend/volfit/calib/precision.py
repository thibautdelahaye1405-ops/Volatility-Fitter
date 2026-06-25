"""Shared precision vocabulary for prior persistence (design note §9).

Every prior-persistence mode (strike gaps, quote operators, smile factors, the
graph baseline) needs the SAME notion of "how strongly do the current quotes
identify this thing, and how trustworthy is the prior?" so the activation gate

    gap_j = max(1 - obs_precision_j / required_precision_j, 0) ^ gamma

means the same in every mode (§9.3): a well-observed coordinate (obs >= required)
receives **zero** prior weight — the "do not damp the signal" rule.

This module holds the model-agnostic scalar FACTORS that scale a raw precision
(fit quality, quote support, bid-ask width, age, transport distance) plus the
gate itself. ``graph/precision.py`` re-uses these so the graph baseline and the
operator/factor builders share one vocabulary; the graph keeps its own per-handle
confidence / floors / caps on top. The factor formulas were originally written
for the graph (Phase 4 of the extrapolation plan) and are lifted here verbatim,
so the graph design point is byte-identical (golden-guarded).
"""

from __future__ import annotations

import numpy as np

_EPS = 1e-12

#: 1/rms^2 base floor: a 1bp-vol fit is excellent but not infinitely precise.
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
#: prior precision (further transport => less trustworthy baseline).
TRANSPORT_SCALE = 0.10


def quote_density_factor(n_quotes: float, ref: float = REF_ATM_QUOTES) -> float:
    """More supporting quotes => higher precision, saturating at ``ref``."""
    return float(np.clip(n_quotes / ref, MIN_DENSITY_FACTOR, 1.0))


def spread_factor(rel_spread: float) -> float:
    """Wider bid-ask (relative to ATM vol) => lower precision, in (0, 1]."""
    return float(1.0 / (1.0 + max(rel_spread, 0.0) / SPREAD_HALF))


def freshness_factor(age_days: float, half_life: float = OBS_FRESHNESS_HALFLIFE) -> float:
    """Exponential decay with age (an as-of mismatch / stale quote / old prior)."""
    return float(0.5 ** (max(age_days, 0.0) / half_life))


def transport_factor(transport_distance: float) -> float:
    """Further forward transport => less precise baseline, in (0, 1]."""
    return float(np.exp(-abs(transport_distance) / TRANSPORT_SCALE))


def activation_gap(
    obs_precision, required_precision, gamma: float = 1.0
):
    """The universal activation gate ``max(1 - obs/req, 0) ^ gamma`` (§9.3).

    Elementwise; accepts scalars or arrays. ``gap -> 1`` where the current quotes
    say nothing about a coordinate (turn the prior fully on), ``gap = 0`` where
    they identify it at/above the required precision (turn the prior fully off).
    ``gamma`` sharpens the transition (>1 = a harder on/off edge)."""
    obs = np.asarray(obs_precision, dtype=float)
    req = np.maximum(np.asarray(required_precision, dtype=float), _EPS)
    gap = np.clip(1.0 - obs / req, 0.0, 1.0)
    return gap ** max(float(gamma), 0.0)


def active_prior_precision(base_precision, gap):
    """The prior precision actually entering calibration: ``base * gap`` (§9.3).

    ``base_precision`` is the prior's own confidence (provenance/age/transport);
    multiplying by the gate yields ~0 where the data is sufficient."""
    return np.asarray(base_precision, dtype=float) * np.asarray(gap, dtype=float)
