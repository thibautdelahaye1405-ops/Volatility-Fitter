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
    fit. Items carry the coarse phase used by the UI status. The LV items form
    their own STAGE (a barrier after the concurrent parametric groups)."""
    from volfit.api import workflow

    state = _state(auto=True)
    captured: dict = {}
    monkeypatch.setattr(
        state.calibration_jobs, "start_stages",
        lambda stages, workers=1: (captured.__setitem__("stages", stages) or True),
    )

    def phases(stages):
        return {
            phase
            for groups in stages
            for _name, items in groups
            for _label, phase, _thunk in items
        }

    state.set_options(state.options().model_copy(update={"localVolEnabled": True}))
    workflow.calibrate_all(state)
    assert phases(captured["stages"]) == {"Parametric", "LV"}
    assert len(captured["stages"]) == 2  # LV runs as its own barrier stage

    state.set_options(state.options().model_copy(update={"localVolEnabled": False}))
    workflow.calibrate_all(state)
    assert phases(captured["stages"]) == {"Parametric"}  # LV skipped when disabled
    assert len(captured["stages"]) == 1


def test_enforce_calendar_threads_prev_into_parametric_items(monkeypatch):
    """enforceCalendar ON: calibrate_all's parametric items are calendar-coupled
    per ticker — each expiry but the first (ascending T) is fitted with the
    previous, shorter expiry's slice threaded in as the convex-order floor. OFF:
    the items are INDEPENDENT per node (the coupled helper is never used)."""
    from volfit.api import workflow

    seen: list[tuple[str, bool, bool]] = []  # (iso, prev_is_none, enforce)
    real = service.fit_and_commit_slice

    def spy(
        st, tk, iso, prepared, prev, enforce, fit_mode="mid", prev_display=None,
        prev_k=None,
    ):
        seen.append((iso, prev is None, enforce))
        return real(st, tk, iso, prepared, prev, enforce, fit_mode, prev_display, prev_k)

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


def test_enforce_calendar_threads_prev_overlay_for_non_lqd(monkeypatch):
    """With a non-LQD model + enforceCalendar, the coupled path threads each
    expiry's overlay into the next as the (model-agnostic) calendar floor: the
    first slice has no prior overlay, the rest do, and all carry enforce=True.
    This is the SVI/sigmoid analogue of the LQD prev-threading above."""
    from volfit.api import workflow

    state = _state(auto=False)
    state.set_options(state.options().model_copy(update={"enforceCalendar": True}))
    state.set_fit_settings(state.fit_settings().model_copy(update={"model": "svi"}))

    seen: list[tuple[bool, bool]] = []  # (prev_display_is_none, enforce)
    real = service._slice_task

    def spy(st, tk, iso, prepared, fit_mode, **kw):
        # The coupled commit path builds ONE combined task (LQD + overlay);
        # its overlay floor comes from the threaded prev_display.
        seen.append((kw.get("prev_display") is None, kw.get("enforce_calendar", False)))
        return real(st, tk, iso, prepared, fit_mode, **kw)

    monkeypatch.setattr(service, "_slice_task", spy)

    nodes = workflow.lit_nodes(state, [TICKER])
    assert len(nodes) >= 2
    for _label, _phase, thunk in workflow._parametric_items(state, nodes, "mid"):
        thunk()
    assert len(seen) == len(nodes)
    assert all(enforce for _none, enforce in seen)
    assert seen[0][0] is True  # first expiry: no prior overlay
    assert all(not none for none, _e in seen[1:])  # rest: prev overlay threaded


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


def test_calib_epoch_advances_only_on_real_recalibration():
    """The calibration epoch advances ONLY when an already-calibrated node moves
    onto a new fit (the level-triggered frontend-refetch signal): a first-ever
    bootstrap does not advance it, a genuine recalibration does, and a re-point
    that changes nothing (cache-hit Calibrate) does not."""
    state = _state(auto=False)
    iso = _iso(state)
    e0 = state.calib_epoch
    service.smile_payload(state, TICKER, iso, "mid")  # bootstrap: prev None, no bump
    assert state.calib_epoch == e0

    _bump_setting(state)  # node goes stale (key drifts)
    service.calibrate_node(state, TICKER, iso, "mid")  # genuine recalibration
    e1 = state.calib_epoch
    assert e1 == e0 + 1

    service.calibrate_node(state, TICKER, iso, "mid")  # nothing changed -> same key
    assert state.calib_epoch == e1  # no spurious advance


def test_calib_epoch_no_churn_on_repeated_reads_auto_on():
    """Under autoCalibrate ON, repeated GETs of an unchanged node must NOT advance
    the epoch — otherwise the frontend's epoch-refetch would loop forever."""
    state = _state(auto=True)
    iso = _iso(state)
    service.smile_payload(state, TICKER, iso, "mid")  # bootstrap
    e = state.calib_epoch
    for _ in range(3):
        service.smile_payload(state, TICKER, iso, "mid")  # no input change
    assert state.calib_epoch == e


def test_model_info_reflects_displayed_model():
    """The diagnostics model info names the family + hyperparameters of the
    DISPLAYED fit: LQD reports its Legendre degree; the Multi-Core Sigmoid
    overlay reports its fitted core count."""
    state = _state(auto=False)
    iso = _iso(state)
    s = service.smile_payload(state, TICKER, iso, "mid")
    assert s.modelInfo.id == "lqd" and s.modelInfo.label == "LQD"
    assert s.modelInfo.params[0].label == "Degree N"
    assert int(s.modelInfo.params[0].value) >= 4  # the fitted LQD order

    fs = state.fit_settings()
    state.set_fit_settings(fs.model_copy(update={"model": "sigmoid", "nCores": 3}))
    service.calibrate_node(state, TICKER, iso, "mid")
    s2 = service.smile_payload(state, TICKER, iso, "mid")
    assert s2.modelInfo.id == "sigmoid" and s2.modelInfo.label == "Multi-Core Sigmoid"
    assert s2.modelInfo.params[0].label == "Cores R"
    # Reported R is the EFFECTIVE core count of the displayed slice (capped by the
    # quote budget), so it is always faithful to what the chart draws.
    rec = service.fit_or_get(state, TICKER, iso, "mid")
    assert s2.modelInfo.params[0].value == str(len(rec.display.slice.cores))
    assert int(s2.modelInfo.params[0].value) >= 1


def test_calibrate_repoints_the_viewed_fit_mode_not_just_mid():
    """The calibrated pointer is per (ticker, iso, MODE). A node viewed in a
    non-mid mode (bid-ask / haircut) must be re-pointed by a Calibrate run in THAT
    mode — calibrating only "mid" left a viewed bid-ask smile frozen/STALE forever
    (the never-visualized-updates-but-visualized-stuck symptom)."""
    state = _state(auto=False)
    iso = _iso(state)
    mode = "bidask"
    s0 = service.smile_payload(state, TICKER, iso, mode)  # visualize in bid-ask
    assert s0.stale is False

    _bump_setting(state)  # a hyperparameter change -> the bid-ask node goes stale
    assert service.smile_payload(state, TICKER, iso, mode).stale is True

    # Calibrating "mid" must NOT clear the bid-ask staleness (different pointer)...
    service.calibrate_node(state, TICKER, iso, "mid")
    assert service.smile_payload(state, TICKER, iso, mode).stale is True

    # ...but calibrating the VIEWED mode does.
    service.calibrate_node(state, TICKER, iso, mode)
    assert service.smile_payload(state, TICKER, iso, mode).stale is False


def test_workflow_calibrate_targets_last_viewed_mode_over_http():
    """End-to-end: the backend records the last-viewed fit mode and a bare
    POST /calibrate targets it, so a bid-ask smile clears STALE without the caller
    having to know the mode (the scheduler / a bare button benefit too)."""
    from datetime import date

    from fastapi.testclient import TestClient

    from volfit.api.app import create_app

    client = TestClient(create_app(reference_date=date(2026, 6, 10)))
    o = client.get("/settings/options").json()
    o["autoCalibrate"] = False
    client.put("/settings/options", json=o)

    u = client.get("/universe").json()
    tk = next(t for t in u["tickers"] if u["expiries"].get(t))
    exp = u["expiries"][tk][1]["expiry"]

    client.get(f"/smiles/{tk}/{exp}", params={"fit_mode": "haircut"})  # view in haircut
    fs = client.get("/settings/fit").json()
    fs["model"] = "svi"
    client.put("/settings/fit", json=fs)  # model switch -> haircut node stale
    assert client.get(f"/smiles/{tk}/{exp}", params={"fit_mode": "haircut"}).json()["stale"]

    client.post("/calibrate")  # NO fit_mode -> resolves to the last-viewed (haircut)
    client.app.state.volfit.calibration_jobs.join(timeout=30)  # background job
    s = client.get(f"/smiles/{tk}/{exp}", params={"fit_mode": "haircut"}).json()
    assert s["stale"] is False and s["modelInfo"]["id"] == "svi"


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
