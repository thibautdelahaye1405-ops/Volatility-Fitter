"""GET /quality — universe fit-quality dashboard (cached-state read, never fits).

Locks the three contracts: (1) reading the report NEVER triggers a
calibration (gated and ungated alike — it must stay as cheap as a status
poll); (2) rows faithfully mirror the cached fits (hasFit / stale / RMS /
readiness and the per-ticker + LV rollups); (3) the arb flags fire (calendar
convex-order via a reversed-slice injection, RMS budget via a tiny budget).
"""

from __future__ import annotations

from datetime import date

from volfit.api import quality, service, workflow
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _isos(state: AppState, ticker: str = TICKER) -> list[str]:
    return [e.isoformat() for e in sorted(state.forwards(ticker))]


def _bump_setting(state: AppState) -> None:
    fs = state.fit_settings()
    state.set_fit_settings(fs.model_copy(update={"regLambda": fs.regLambda * 2 + 1e-9}))


def test_report_never_fits_and_shows_no_fit_rows():
    """Before any Calibrate the report lists every lit node as hasFit=False —
    and building it must not have created a single calibrated pointer."""
    state = AppState(REF_DATE)
    for t in state.active_tickers():
        state.ensure_chain(t)
    report = quality.build_quality_report(state)
    assert report.summary.litNodes > 0
    assert report.summary.fitted == 0
    assert report.summary.noFit == report.summary.litNodes
    assert report.summary.readyNodes == 0
    assert all(not n.hasFit and n.issues == ["no fit"] for n in report.nodes)
    for t, iso in workflow.lit_nodes(state):
        assert state.get_calibrated_ptr(t, iso, "mid") is None  # nothing was fit


def test_rows_mirror_cached_fits_and_staleness():
    state = AppState(REF_DATE)
    isos = _isos(state)
    for iso in isos[:2]:
        service.calibrate_node(state, TICKER, iso, "mid")

    report = quality.build_quality_report(state)
    rows = {(n.ticker, n.expiry): n for n in report.nodes}
    for iso in isos[:2]:
        row = rows[(TICKER, iso)]
        assert row.hasFit and not row.stale and row.ready
        assert 0.0 < row.rmsBp < 50.0  # synthetic mids fit tightly
        assert row.nQuotes > 0 and row.tau > 0.0 and row.atmVol > 0.0
        assert row.leeOk and row.calendarOk and row.model == "lqd"
    for iso in isos[2:]:
        assert rows[(TICKER, iso)].hasFit is False
    assert report.summary.fitted == 2

    _bump_setting(state)  # inputs drift -> the two fitted nodes go stale
    report2 = quality.build_quality_report(state)
    stale_rows = [n for n in report2.nodes if n.hasFit]
    assert len(stale_rows) == 2
    assert all(n.stale and not n.ready and "stale" in n.issues for n in stale_rows)
    assert report2.summary.stale == 2 and report2.summary.readyNodes == 0


def test_ticker_rollup_and_lv_quality():
    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={"localVolEnabled": True}))
    workflow.calibrate_ticker(state, TICKER)  # all expiries + the LV surface

    report = quality.build_quality_report(state)
    row = next(t for t in report.tickers if t.ticker == TICKER)
    assert row.fitted == row.nodes == len(_isos(state))
    assert row.stale == 0 and row.arbFlags == 0 and row.ready == row.nodes
    assert row.surfaceRmsBp > 0.0 and row.worstNodeRmsBp >= row.surfaceRmsBp / 2
    assert row.lv is not None and row.lv.hasFit and not row.lv.stale
    assert row.lv.rmsIvErrorBp > 0.0
    assert isinstance(row.lv.arbitrageFree, bool)
    assert report.summary.lvTickers == 1
    # Other tickers were never LV-calibrated: no LV rollup, and reading the
    # report must not have created one.
    for t in report.tickers:
        if t.ticker != TICKER:
            assert t.lv is None
            assert state.get_affine_ptr(t.ticker) is None


def test_calendar_flag_fires_on_reversed_slices():
    """Injecting the LONGER expiry's slice as the 'previous' floor makes the
    shorter slice violate convex order -> the row is flagged not-ready."""
    state = AppState(REF_DATE)
    isos = _isos(state)
    near = service.calibrate_node(state, TICKER, isos[0], "mid")
    far = service.calibrate_node(state, TICKER, isos[2], "mid")

    ok_node, _ = quality._node_row(
        state, TICKER, isos[2], "mid", far, near.result.slice, None, None, 50.0, False
    )
    assert ok_node.calendarOk and ok_node.ready

    bad_node, _ = quality._node_row(
        state, TICKER, isos[0], "mid", near, far.result.slice, None, None, 50.0, False
    )
    assert bad_node.calendarViolation > 0.0
    assert not bad_node.calendarOk and not bad_node.ready
    assert "calendar arb vs previous expiry" in bad_node.issues


def test_extrap_measurement_is_advisory_and_populated():
    """Extrapolated-region fields are measured on fitted rows and NEVER gate
    readiness (Notes 09/10 Phase 1: measure first, enforce later)."""
    state = AppState(REF_DATE)
    isos = _isos(state)
    service.calibrate_node(state, TICKER, isos[0], "mid")
    service.calibrate_node(state, TICKER, isos[1], "mid")
    report = quality.build_quality_report(state)
    fitted = [n for n in report.nodes if n.hasFit]
    assert len(fitted) == 2
    # the first fitted row has no previous expiry: no calendar / wing-order info
    assert fitted[0].extrapCalBp is None and fitted[0].wingOrderOk is None
    # the second row is measured against the first (displayed family)
    assert fitted[1].extrapCalBp is not None
    assert fitted[1].wingOrderOk is not None
    # the synthetic chain's quoted edges are already worthless (OTM value below
    # the 1 bp floor), so the envelope is empty by design: g unmeasured, clean
    assert fitted[1].extrapMinG is None and fitted[1].extrapOk
    # advisory contract: extrap flags never appear in issues / readiness
    for n in fitted:
        assert not any("extrap" in issue.lower() for issue in n.issues)
    assert report.summary.extrapFlags == sum(t.extrapFlags for t in report.tickers)


def test_rms_budget_drives_readiness():
    state = AppState(REF_DATE)
    iso = _isos(state)[1]
    service.calibrate_node(state, TICKER, iso, "mid")
    report = quality.build_quality_report(state, rms_budget_bp=1e-6)
    row = next(n for n in report.nodes if n.hasFit)
    assert not row.ready and any("budget" in issue for issue in row.issues)


def test_quality_route_over_http():
    from fastapi.testclient import TestClient

    from volfit.api.app import create_app

    client = TestClient(create_app(reference_date=REF_DATE))
    body = client.get("/quality").json()
    assert body["fitMode"] == "mid"
    assert body["summary"]["litNodes"] == len(body["nodes"])
    assert body["summary"]["tickers"] == len(body["tickers"])
    assert body["rmsBudgetBp"] == quality.DEFAULT_RMS_BUDGET_BP
    # The report is a pure read: no node may have been calibrated by GET.
    assert body["summary"]["fitted"] == 0

    body2 = client.get("/quality", params={"rms_budget_bp": 10.0}).json()
    assert body2["rmsBudgetBp"] == 10.0
