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


def test_calibrate_all_skips_lv_when_localvol_disabled(monkeypatch):
    """localVolEnabled gates the LV (affine) work items; parametric nodes always
    fit. Items carry the coarse phase used by the UI status."""
    from volfit.api import workflow

    state = _state(auto=True)
    captured: dict = {}
    monkeypatch.setattr(
        state.calibration_jobs, "start",
        lambda items: (captured.__setitem__("items", items) or True),
    )

    state.set_options(state.options().model_copy(update={"localVolEnabled": True}))
    workflow.calibrate_all(state)
    phases_on = {phase for _label, phase, _thunk in captured["items"]}
    assert "Parametric" in phases_on and "LV" in phases_on

    state.set_options(state.options().model_copy(update={"localVolEnabled": False}))
    workflow.calibrate_all(state)
    phases_off = {phase for _label, phase, _thunk in captured["items"]}
    assert phases_off == {"Parametric"}  # LV items skipped when disabled


def test_enforce_calendar_threads_prev_into_parametric_items(monkeypatch):
    """enforceCalendar ON: calibrate_all's parametric items are calendar-coupled
    per ticker — each expiry but the first (ascending T) is fitted with the
    previous, shorter expiry's slice threaded in as the convex-order floor. OFF:
    the items are INDEPENDENT per node (the coupled helper is never used)."""
    from volfit.api import workflow

    seen: list[tuple[str, bool, bool]] = []  # (iso, prev_is_none, enforce)
    real = service.fit_and_commit_slice

    def spy(st, tk, iso, prepared, prev, enforce, fit_mode="mid"):
        seen.append((iso, prev is None, enforce))
        return real(st, tk, iso, prepared, prev, enforce, fit_mode)

    monkeypatch.setattr(service, "fit_and_commit_slice", spy)

    # ON: coupled. The first expiry has no prior slice; the rest are threaded.
    state = _state(auto=False)
    state.set_options(state.options().model_copy(update={"enforceCalendar": True}))
    nodes = workflow.lit_nodes(state, [TICKER])
    assert len(nodes) >= 2  # otherwise the coupling is vacuous
    for _label, _phase, thunk in workflow._parametric_items(state, nodes, "mid"):
        thunk()
    assert len(seen) == len(nodes)
    assert all(enforce for _iso, _none, enforce in seen)
    assert seen[0][1] is True  # first expiry: prev is None
    assert all(not none for _iso, none, _e in seen[1:])  # rest: prev threaded

    # OFF: independent per-node — the coupled commit helper is never called.
    seen.clear()
    off = _state(auto=False)
    off.set_options(off.options().model_copy(update={"enforceCalendar": False}))
    for _label, _phase, thunk in workflow._parametric_items(
        off, workflow.lit_nodes(off, [TICKER]), "mid"
    ):
        thunk()
    assert seen == []


def test_enforce_calendar_surface_is_arbitrage_free():
    """Running the coupled parametric items yields a calendar-arbitrage-free
    surface: no convex-order violation between consecutive lit expiries."""
    from volfit.api import workflow
    from volfit.calib.calendar import calendar_violation

    state = _state(auto=False)
    state.set_options(state.options().model_copy(update={"enforceCalendar": True}))
    nodes = workflow.lit_nodes(state, [TICKER])
    for _label, _phase, thunk in workflow._parametric_items(state, nodes, "mid"):
        thunk()

    isos = [iso for t, iso in nodes if t == TICKER]
    slices = [service.fit_or_get(state, TICKER, iso, "mid").result.slice for iso in isos]
    for prev, cur in zip(slices, slices[1:]):
        assert calendar_violation(prev, cur) <= 1e-6


def test_stream_refit_respects_autocalibrate(monkeypatch):
    """The streaming throttled refit obeys autoCalibrate (the master switch for
    unattended refits): ON refetches the book + recalibrates, OFF is a no-op."""
    from volfit.api import workflow

    started = {"n": 0}
    monkeypatch.setattr(
        workflow,
        "calibrate_all",
        lambda s, fit_mode="mid": (started.__setitem__("n", started["n"] + 1) or True),
    )

    # OFF: no refetch, no calibration.
    off = _state(auto=False)
    v0 = off.data_version(TICKER)
    assert workflow.stream_refit(off) is False
    assert off.data_version(TICKER) == v0 and started["n"] == 0

    # ON: refetch the chain (book read) and calibrate all lit nodes.
    on = _state(auto=True)
    w0 = on.data_version(TICKER)
    assert workflow.stream_refit(on) is True
    assert on.data_version(TICKER) == w0 + 1 and started["n"] == 1


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
