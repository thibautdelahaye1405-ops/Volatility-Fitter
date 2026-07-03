"""Resolve the observation-filter mode into the set of live behaviours.

One place maps ``OptionsSettings.observationFilterMode`` (Docs/
kalman_filtering.tex, Note 15 §6) to *what* the filter layer should do, so the
app layer / calibration path branch on a small struct instead of re-deriving
mode semantics — the same pattern as :mod:`volfit.api.prior_mode`.

The three modes (note §6):

    off       feature absent: no state kept, nothing drawn, fits byte-identical
    overlay   predict/update the per-node handle state on every new observation
              and DRAW prediction/posterior; calibration is untouched (the
              recommended pilot — it cannot double-count quotes because the
              posterior never feeds back into the fit)
    active    one-stage MAP: the Kalman prediction prior (m^-, P^-) enters the
              fit as a whitened residual block (note eq. active-map); the same
              quotes are never also refit against the posterior

``owned_handles`` names the state coordinates the filter carries. In ``active``
mode :func:`volfit.api.prior_mode.resolve_prior_mode` consumers must drop
prior-persistence terms overlapping these coordinates (the note §6.3 split:
Kalman = temporal prior on the observed latent state, persistence = gap prior
on unobserved functionals — anchoring both to the same previous state would
count it twice). The deep-tail strike anchor, the var-swap companion and dark
graph nodes are outside the handle state and keep persistence.
"""

from __future__ import annotations

from dataclasses import dataclass

from volfit.api.schemas import OptionsSettings

#: v1 filter state coordinates, in the canonical handle order shared with the
#: graph layer (graph/precision.py): ATM vol, ATM skew, ATM curvature.
FILTER_HANDLES: tuple[str, ...] = ("ATM", "skew", "curvature")


@dataclass(frozen=True)
class FilterModePlan:
    """Which observation-filter behaviours are live under the resolved mode.

    ``enabled`` gates state-keeping + updates; ``draw_overlay`` is the display
    flag; ``active`` gates the calibration prediction-prior block (and thereby
    the persistence auto-exclusion on ``owned_handles``)."""

    mode: str
    enabled: bool  # keep per-node state and update it on new observations
    active: bool  # the prediction prior enters calibration (one-stage MAP)
    draw_overlay: bool  # draw prediction/posterior in the smile viewer
    owned_handles: tuple[str, ...]  # coordinates the filter carries (v1: 3)


def resolve_filter_mode(options: OptionsSettings) -> FilterModePlan:
    """Map the persisted mode to the live-behaviour flags (note §6)."""
    mode = options.observationFilterMode
    enabled = mode != "off"
    return FilterModePlan(
        mode=mode,
        enabled=enabled,
        active=mode == "active",
        draw_overlay=enabled,
        owned_handles=FILTER_HANDLES if enabled else (),
    )
