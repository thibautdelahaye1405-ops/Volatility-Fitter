"""Quote-derived fit error bars (api/fit_uncertainty + SmileDiagnostics stds).

Every calibration retains its solver Jacobian, so the smile payload reports
(σ_atm, σ_skew, σ_curv) from the fit's own information matrix + bid-ask noise
— WITHOUT the observation filter being on, and without ever creating filter
state. Advisory throughout: a missing measurement degrades to the factors
route, a no-fit node reports None.
"""

from __future__ import annotations

from datetime import date

from volfit.api import fit_uncertainty, service
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _iso(state: AppState, n: int = 1) -> str:
    return [e.isoformat() for e in sorted(state.forwards(TICKER))][n]


def test_error_bars_present_via_the_jacobian_route_with_filter_off():
    state = AppState(REF_DATE)
    assert state.options().observationFilterMode == "off"
    iso = _iso(state)
    service.calibrate_node(state, TICKER, iso, "mid")

    payload = service.smile_payload(state, TICKER, iso, "mid")
    d = payload.diagnostics
    assert d.atmVolStd is not None and 0.0 < d.atmVolStd < 0.05  # sane vol σ
    assert d.skewStd is not None and d.skewStd > 0.0
    assert d.curvStd is not None and d.curvStd > 0.0

    # The measurement was stored AT COMMIT off the retained solver Jacobian.
    ptr = state.get_calibrated_ptr(TICKER, iso, "mid")
    meas = fit_uncertainty._cache(state)[ptr[0]]
    assert meas.breakdown.get("route") == 1.0  # 1 = jacobian
    # And the always-on diag did NOT switch the filter on.
    assert state.filter_node((TICKER, iso, "mid")) is None


def test_lazy_factors_fallback_for_records_without_a_stored_measurement():
    state = AppState(REF_DATE)
    iso = _iso(state)
    service.calibrate_node(state, TICKER, iso, "mid")
    delattr(state, "_fit_uncertainty")  # simulate a pre-feature cache entry

    stds = fit_uncertainty.handle_stds(state, TICKER, iso, "mid")
    assert stds is not None and all(s > 0.0 for s in stds)
    ptr = state.get_calibrated_ptr(TICKER, iso, "mid")
    assert fit_uncertainty._cache(state)[ptr[0]].breakdown.get("route") == 0.0  # factors


def test_stale_node_reports_the_displayed_fits_uncertainty():
    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={"autoCalibrate": False}))
    iso = _iso(state)
    service.calibrate_node(state, TICKER, iso, "mid")
    before = service.smile_payload(state, TICKER, iso, "mid").diagnostics.atmVolStd

    fs = state.fit_settings()
    state.set_fit_settings(fs.model_copy(update={"regLambda": fs.regLambda * 2 + 1e-9}))
    payload = service.smile_payload(state, TICKER, iso, "mid")
    assert payload.stale is True
    assert payload.diagnostics.atmVolStd == before  # keyed by the frozen pointer


def test_no_fit_node_reports_none():
    state = AppState(REF_DATE, gated=True)
    state.ensure_chain(TICKER)
    iso = _iso(state)
    payload = service.smile_payload(state, TICKER, iso, "mid")
    assert payload.hasFit is False
    assert payload.diagnostics.atmVolStd is None


def test_overlay_model_carries_the_backbone_stds_too():
    state = AppState(REF_DATE)
    iso = _iso(state)
    state.set_fit_settings(state.fit_settings().model_copy(update={"model": "svi"}))
    service.calibrate_node(state, TICKER, iso, "mid")
    d = service.smile_payload(state, TICKER, iso, "mid").diagnostics
    assert d.atmVolStd is not None and d.atmVolStd > 0.0
