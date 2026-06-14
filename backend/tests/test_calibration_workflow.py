"""Trigger-gated calibration model: autoCalibrate ON refits, OFF freezes + stale.

A change to the inputs (a hyperparameter, a fresh options fetch) must NOT silently
recalibrate when Auto-calibrate is OFF: the displayed fit stays frozen at the last
calibration and reports `stale=True` until an explicit Calibrate.
"""

from __future__ import annotations

from datetime import date


from volfit.api import service
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _state(auto: bool) -> AppState:
    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={"autoCalibrate": auto}))
    return state


def _iso(state: AppState) -> str:
    return [e.isoformat() for e in sorted(state.forwards(TICKER))][1]


def _bump_setting(state: AppState) -> None:
    fs = state.fit_settings()
    state.set_fit_settings(fs.model_copy(update={"regLambda": fs.regLambda * 2 + 1e-9}))


def test_autocal_off_freezes_until_calibrate():
    state = _state(auto=False)
    iso = _iso(state)
    s0 = service.smile_payload(state, TICKER, iso, "mid")
    assert s0.stale is False  # bootstrap fit is current

    _bump_setting(state)  # a hyperparameter change
    s1 = service.smile_payload(state, TICKER, iso, "mid")
    assert s1.stale is True  # inputs drifted, NOT recalibrated
    assert s1.diagnostics.atmVol == s0.diagnostics.atmVol  # frozen at last fit

    service.calibrate_node(state, TICKER, iso, "mid")  # explicit Calibrate
    s2 = service.smile_payload(state, TICKER, iso, "mid")
    assert s2.stale is False


def test_autocal_on_refits_immediately():
    state = _state(auto=True)
    iso = _iso(state)
    service.smile_payload(state, TICKER, iso, "mid")
    _bump_setting(state)
    s1 = service.smile_payload(state, TICKER, iso, "mid")
    assert s1.stale is False  # auto-calibrate keeps it current


def test_options_fetch_marks_stale_when_auto_off():
    state = _state(auto=False)
    iso = _iso(state)
    service.smile_payload(state, TICKER, iso, "mid")  # bootstrap calibrate
    state.bump_data_version(TICKER)  # a fresh options fetch
    assert service.smile_payload(state, TICKER, iso, "mid").stale is True


def test_quote_edit_does_not_refit_when_auto_off():
    """An exclude edit bumps the session version (=> stale) but must not refit."""
    from volfit.api import edits
    from volfit.api.schemas import QuoteEditRequest

    state = _state(auto=False)
    iso = _iso(state)
    before = service.smile_payload(state, TICKER, iso, "mid")
    edits.apply_quote_edit(state, TICKER, iso, "mid", QuoteEditRequest(action="exclude", index=0))
    after = service.smile_payload(state, TICKER, iso, "mid")
    assert after.stale is True
    assert after.diagnostics.atmVol == before.diagnostics.atmVol  # frozen
