"""Prior-persistence mode plumbing (Phase 0 of Docs/prior_persistence_roadmap.md).

Covers the bits that exist before any calibrator is touched:
  * the mode -> live-builder resolver (api/prior_mode.resolve_prior_mode);
  * the persisted-blob migration (legacy autoLoadPrior -> mode), store-load only;
  * every new operator/factor/tail knob bumping the options version (so a changed
    knob busts the fit cache once wired);
  * the operator/factor set validators dropping unknown names.
"""

from datetime import date

from volfit.api.prior_mode import resolve_prior_mode
from volfit.api.schemas import OptionsSettings
from volfit.api.settings_persist import _migrate_options
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)


# --------------------------------------------------------------- mode resolver
def test_resolver_flags_per_mode():
    """Each mode lights up exactly the right builders (design note §10)."""
    cases = {
        "off": dict(draw_overlay=False, strike=False, ops=False, fac=False, tail=False, graph=False),
        "overlay": dict(draw_overlay=True, strike=False, ops=False, fac=False, tail=False, graph=False),
        "strike_gap": dict(draw_overlay=True, strike=True, ops=False, fac=False, tail=False, graph=False),
        "quote_operator": dict(draw_overlay=True, strike=False, ops=True, fac=False, tail=False, graph=False),
        "smile_factor": dict(draw_overlay=True, strike=False, ops=False, fac=True, tail=False, graph=False),
        "hybrid": dict(draw_overlay=True, strike=False, ops=True, fac=False, tail=True, graph=False),
        "graph_only": dict(draw_overlay=True, strike=False, ops=False, fac=False, tail=False, graph=True),
    }
    for mode, want in cases.items():
        plan = resolve_prior_mode(OptionsSettings(priorPersistenceMode=mode))
        assert plan.mode == mode
        assert plan.draw_overlay is want["draw_overlay"]
        assert plan.strike_anchor is want["strike"]
        assert plan.operators is want["ops"]
        assert plan.factors is want["fac"]
        assert plan.tail_anchor is want["tail"]
        assert plan.graph_only is want["graph"]


def test_any_calibration_prior():
    """The convenience flag is True only when a calibration penalty is active."""
    assert not resolve_prior_mode(OptionsSettings(priorPersistenceMode="off")).any_calibration_prior
    assert not resolve_prior_mode(OptionsSettings(priorPersistenceMode="overlay")).any_calibration_prior
    assert not resolve_prior_mode(OptionsSettings(priorPersistenceMode="graph_only")).any_calibration_prior
    for mode in ("strike_gap", "quote_operator", "smile_factor", "hybrid"):
        assert resolve_prior_mode(OptionsSettings(priorPersistenceMode=mode)).any_calibration_prior


# ----------------------------------------------------------------- migration
def test_migration_legacy_autoloadprior_on():
    """A pre-mode blob with autoLoadPrior on becomes strike_gap (exact behaviour)."""
    raw = {"autoLoadPrior": True, "priorAnchorWeightPct": 30.0}
    migrated = _migrate_options(raw)
    assert migrated["priorPersistenceMode"] == "strike_gap"
    assert OptionsSettings(**migrated).priorPersistenceMode == "strike_gap"
    # input dict is not mutated in place
    assert "priorPersistenceMode" not in raw


def test_migration_legacy_autoloadprior_off():
    """A pre-mode blob with the prior off becomes off (no calibration penalty)."""
    assert _migrate_options({"autoLoadPrior": False})["priorPersistenceMode"] == "off"
    assert _migrate_options({})["priorPersistenceMode"] == "off"


def test_migration_keeps_explicit_mode():
    """A blob already carrying a mode is left as-is (no clobber on re-save)."""
    raw = {"priorPersistenceMode": "hybrid", "autoLoadPrior": True}
    assert _migrate_options(raw)["priorPersistenceMode"] == "hybrid"


# ---------------------------------------------------------------- validators
def test_operator_set_drops_unknown_and_orders():
    s = OptionsSettings(priorOperatorSet=["VarSwap", "bogus", "ATM", "RR25"])
    assert s.priorOperatorSet == ["ATM", "RR25", "VarSwap"]  # canonical order, deduped
    assert OptionsSettings(priorOperatorSet=["nope"]).priorOperatorSet == [
        "ATM", "RR25", "BF25", "VarSwap",
    ]  # empty -> default


def test_factor_set_drops_unknown_and_orders():
    s = OptionsSettings(priorFactorSet=["VarSwap", "curvature", "xx", "ATM"])
    assert s.priorFactorSet == ["ATM", "curvature", "VarSwap"]
    assert OptionsSettings(priorFactorSet=[]).priorFactorSet == [
        "ATM", "skew", "curvature", "VarSwap",
    ]


# ------------------------------------------------------------- version bumps
def test_prior_knobs_bump_options_version():
    """Each new calibration-affecting knob busts the fit cache (options version)."""
    state = AppState(reference_date=REF_DATE)
    base = state.options()
    changes = [
        {"priorPersistenceMode": "quote_operator"},
        {"priorOperatorSet": ["ATM"]},
        {"priorOperatorStrengthPct": 70.0},
        {"priorOperatorRequiredPrecision": 2.0},
        {"priorOperatorGapExponent": 2.0},
        {"priorOperatorBandwidth": 0.1},
        {"priorOperatorCovarianceMode": "full"},
        {"priorDataOnlyPrepass": True},
        {"collarSign": "put_call"},
        {"priorFactorSet": ["ATM"]},
        {"priorFactorStrengthPct": 40.0},
        {"priorTailAnchorStrengthPct": 10.0},
    ]
    for upd in changes:
        v0 = state.options_version
        state.set_options(base.model_copy(update=upd))
        assert state.options_version == v0 + 1, f"{upd} did not bump the version"
        state.set_options(base)  # reset (also bumps; we only assert the forward bump)
