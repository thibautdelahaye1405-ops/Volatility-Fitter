"""Observation-filter mode plumbing (Phase 0 of Docs/observation_filter_roadmap.md).

Covers the bits that exist before any filter numerics are touched:
  * the mode -> live-behaviour resolver (api/filter_mode.resolve_filter_mode);
  * options round-trip through the persisted-settings migration path;
  * the version-bump matrix — overlay knob changes bump ONLY the lightweight
    filter version (no fit-cache bust); active-mode changes bump the options
    version (they change the MAP fit);
  * ``off`` is the schema default (the feature ships dormant).
"""

from datetime import date

from volfit.api.filter_mode import FILTER_HANDLES, resolve_filter_mode
from volfit.api.schemas import OptionsSettings
from volfit.api.settings_persist import _migrate_options
from volfit.api.state import AppState

REF_DATE = date(2026, 7, 3)

#: Every surfaced filter knob with a non-default probe value (used to sweep the
#: version-bump matrix; keep in sync with the schema fields).
KNOB_PROBES = [
    {"filterCovarianceMode": "factors"},
    {"filterProcessVolBpSqrtDay": 20.0},
    {"filterProcessSkewSqrtDay": 0.04},
    {"filterProcessCurvSqrtDay": 0.10},
    {"filterTransportNoiseScale": 0.25},
    {"filterResidualInflation": False},
    {"filterMaxGain": 0.8},
    {"filterResetHours": 24.0},
    {"filterDataOnlyPrepass": True},
]


# --------------------------------------------------------------- mode resolver
def test_resolver_flags_per_mode():
    """Each mode lights exactly the right behaviours (note §6)."""
    cases = {
        "off": dict(enabled=False, active=False, draw=False, handles=()),
        "overlay": dict(enabled=True, active=False, draw=True, handles=FILTER_HANDLES),
        "active": dict(enabled=True, active=True, draw=True, handles=FILTER_HANDLES),
    }
    for mode, want in cases.items():
        plan = resolve_filter_mode(OptionsSettings(observationFilterMode=mode))
        assert plan.mode == mode
        assert plan.enabled is want["enabled"]
        assert plan.active is want["active"]
        assert plan.draw_overlay is want["draw"]
        assert plan.owned_handles == want["handles"]


def test_default_mode_is_off():
    """The feature ships dormant: a fresh OptionsSettings resolves to off."""
    plan = resolve_filter_mode(OptionsSettings())
    assert plan.mode == "off"
    assert not plan.enabled


def test_handles_match_graph_order():
    """The v1 state coordinates are the canonical 3-handle set, in the graph
    layer's order (ATM, skew, curvature) — the filter and graph share vectors."""
    assert FILTER_HANDLES == ("ATM", "skew", "curvature")


# ----------------------------------------------------------- persisted blobs
def test_migration_fills_filter_defaults():
    """A pre-filter persisted blob loads cleanly with the filter off (Pydantic
    defaults; no explicit migration entry needed)."""
    migrated = _migrate_options({"priorPersistenceMode": "hybrid"})
    settings = OptionsSettings(**migrated)
    assert settings.observationFilterMode == "off"
    assert settings.filterCovarianceMode == "jacobian"


def test_options_roundtrip_filter_fields():
    """Filter fields survive a model_dump -> reconstruct round trip."""
    s = OptionsSettings(
        observationFilterMode="overlay",
        filterCovarianceMode="factors",
        filterProcessVolBpSqrtDay=15.0,
        filterResetHours=48.0,
    )
    s2 = OptionsSettings(**s.model_dump())
    assert s2 == s


# ------------------------------------------------------------- version bumps
def test_overlay_knobs_bump_filter_version_only():
    """In off/overlay mode a filter knob refreshes the overlay (filter version)
    but must NOT bust the fit cache (options version) — the filter only READS
    fits outside active mode."""
    state = AppState(reference_date=REF_DATE)
    base = state.options().model_copy(update={"observationFilterMode": "overlay"})
    state.set_options(base)
    for upd in KNOB_PROBES:
        ov0, fv0 = state.options_version, state.filter_version
        state.set_options(base.model_copy(update=upd))
        assert state.filter_version == fv0 + 1, f"{upd} did not bump filter_version"
        assert state.options_version == ov0, f"{upd} bust the fit cache in overlay"
        state.set_options(base)  # reset for the next probe


def test_active_transition_bumps_options_version():
    """off/overlay <-> active transitions change the MAP fit => options version."""
    state = AppState(reference_date=REF_DATE)
    base = state.options()
    for src, dst in [("off", "active"), ("active", "overlay"), ("overlay", "active")]:
        state.set_options(base.model_copy(update={"observationFilterMode": src}))
        v0 = state.options_version
        state.set_options(base.model_copy(update={"observationFilterMode": dst}))
        assert state.options_version == v0 + 1, f"{src}->{dst} did not bump"


def test_active_knobs_bump_options_version():
    """While active, every filter knob changes the MAP objective => fit-cache bust."""
    state = AppState(reference_date=REF_DATE)
    base = state.options().model_copy(update={"observationFilterMode": "active"})
    state.set_options(base)
    for upd in KNOB_PROBES:
        v0 = state.options_version
        state.set_options(base.model_copy(update=upd))
        assert state.options_version == v0 + 1, f"{upd} did not bump while active"
        state.set_options(base)  # reset (also bumps; only the forward bump asserted)


def test_off_to_overlay_no_fit_bust():
    """Turning the OVERLAY on/off never busts fits (it is a pure display layer)."""
    state = AppState(reference_date=REF_DATE)
    base = state.options()
    v0 = state.options_version
    state.set_options(base.model_copy(update={"observationFilterMode": "overlay"}))
    state.set_options(base.model_copy(update={"observationFilterMode": "off"}))
    assert state.options_version == v0
    assert state.filter_version >= 2  # but the overlay payload refreshed both times
