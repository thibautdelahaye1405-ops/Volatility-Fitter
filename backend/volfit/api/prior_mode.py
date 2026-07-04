"""Resolve the active prior-persistence mode into the set of live builders.

One place maps ``OptionsSettings.priorPersistenceMode`` (Docs/
prior_persistence_design_options.md §10) to *which* prior builders the
calibration path should run, so ``service.py`` / ``affine_fit.py`` branch on a
small struct instead of re-deriving the mode semantics in several places.

The seven modes (design note §10):

    off          no overlay, no calibration penalty (pure current market)
    overlay      draw the dotted transported prior, no calibration penalty
    strike_gap   the legacy data-gap synthetic strike anchor (calib/prior.py)
    quote_operator  persist ATM/RR/BF/var-swap operators only where under-observed
    smile_factor    penalize factor distance (level/skew/curvature/var-swap)
    hybrid       operators + residual deep-tail strike anchors (the recommended
                 default)
    graph_only   disable calibration anchors; the graph baseline carries the prior
                 for dark nodes, lit nodes stay market-pure

Phases 3-6 consume :class:`PriorModePlan`; Phase 0 only needs the resolver so the
flags exist for the later dispatch wiring.
"""

from __future__ import annotations

from dataclasses import dataclass

from volfit.api.schemas import OptionsSettings


@dataclass(frozen=True)
class PriorModePlan:
    """Which prior builders are active under the resolved persistence mode.

    ``draw_overlay`` is a display flag (show the dotted transported prior);
    the rest gate calibration penalties. Exactly one of the calibration families
    is active per mode (``hybrid`` runs both ``operators`` and ``tail_anchor``)."""

    mode: str
    draw_overlay: bool  # draw the dotted transported prior in the viewers
    strike_anchor: bool  # the legacy data-gap strike anchor (calib/prior.py)
    operators: bool  # quote-operator priors (ATM/RR/BF/var-swap)
    factors: bool  # smile-factor priors (level/skew/curvature/var-swap)
    tail_anchor: bool  # hybrid residual deep-tail strike anchor
    graph_only: bool  # no calibration anchors; graph carries the dark-node prior

    @property
    def any_calibration_prior(self) -> bool:
        """True when SOME prior penalty enters the calibration (drives caching /
        the data-only prepass eligibility)."""
        return self.strike_anchor or self.operators or self.factors or self.tail_anchor


def resolve_prior_mode(options: OptionsSettings) -> PriorModePlan:
    """Map the persisted mode to the live-builder flags (design note §10).

    Observation-filter auto-exclusion (Note 15 §6.3, hard-coded by design):
    when ``observationFilterMode == "active"`` the Kalman prediction prior
    already anchors the ATM level and local shape, so every persistence
    builder overlapping those coordinates is DROPPED — operators (ATM/RR/BF),
    smile factors, and the near-ATM strike anchor. Anchoring both to the same
    previous state would count it twice (the note's invariant 3). What
    survives is exactly what the filter state does not carry: the DEEP-TAIL
    strike anchor (kept for any mode that had a calibration prior) and the
    graph's dark-node baseline. There is deliberately no knob."""
    mode = options.priorPersistenceMode
    filter_active = options.observationFilterMode == "active"
    had_calibration_prior = mode in (
        "strike_gap", "quote_operator", "smile_factor", "hybrid"
    )
    return PriorModePlan(
        mode=mode,
        draw_overlay=mode != "off",
        strike_anchor=mode == "strike_gap" and not filter_active,
        operators=mode in ("quote_operator", "hybrid") and not filter_active,
        factors=mode == "smile_factor" and not filter_active,
        tail_anchor=mode == "hybrid" or (filter_active and had_calibration_prior),
        graph_only=mode == "graph_only",
    )
